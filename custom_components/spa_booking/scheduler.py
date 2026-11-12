"""Internal timers of the SPA Booking integration.

Until 2.0.15 every timed job (offer expiry, reminders, review requests,
loyalty vouchers, voucher expiry, daily promo, monthly report) only ran when
an automation in ``packages/spa_booking.yaml`` called the matching service.
That package is not part of the repository, so a fresh installation never
sent anything on its own. The jobs now run here.

Every job is safe to run twice: appointments and vouchers carry their own
"already sent" flags, and the daily promo and the monthly report stamp the
day/month they went out. An old automation still calling the services keeps
working and cannot cause a double send; it can simply be removed.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import datetime
import logging
from typing import TYPE_CHECKING, Any

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.event import async_track_time_change
from homeassistant.util import dt as dt_util

from .const import (
    DEFAULT_QUIET_HOURS_END,
    DEFAULT_QUIET_HOURS_START,
    KEY_SETTINGS,
    SCHEDULER_INTERVAL_MIN,
)

if TYPE_CHECKING:
    from .coordinator import SpaBookingCoordinator

_LOGGER = logging.getLogger(__name__)


def _minutes(clock: str, fallback: str) -> int:
    """Minutes since midnight of "HH:MM", or of ``fallback`` when malformed."""
    for value in (clock, fallback):
        try:
            hour, minute = str(value).split(":")
            return int(hour) * 60 + int(minute)
        except (TypeError, ValueError):
            continue
    return 0


def in_quiet_hours(now: datetime, start: str, end: str) -> bool:
    """Whether ``now`` (local) falls in the quiet window ``start``-``end``.

    A window whose start is after its end spans midnight (21:00-08:00); equal
    clocks mean no quiet window at all.
    """
    current = now.hour * 60 + now.minute
    begin = _minutes(start, DEFAULT_QUIET_HOURS_START)
    finish = _minutes(end, DEFAULT_QUIET_HOURS_END)
    if begin == finish:
        return False
    if begin < finish:
        return begin <= current < finish
    return current >= begin or current < finish


class SpaBookingScheduler:
    """Run the periodic jobs of one installation."""

    def __init__(self, hass: HomeAssistant, coordinator: SpaBookingCoordinator) -> None:
        """Keep the coordinator; nothing runs until ``async_start``."""
        self._hass = hass
        self._coordinator = coordinator
        self._unsub: Callable[[], None] | None = None
        self._running = False
        self.last_run: dict[str, Any] = {}

    @callback
    def async_start(self) -> Callable[[], None]:
        """Start the minute tick; return the function that stops it."""
        self._unsub = async_track_time_change(self._hass, self._async_tick, second=0)
        return self.async_stop

    @callback
    def async_stop(self) -> None:
        """Stop the tick (entry unloaded)."""
        if self._unsub is not None:
            self._unsub()
            self._unsub = None

    @property
    def _settings(self) -> dict[str, Any]:
        return self._coordinator.data.get(KEY_SETTINGS, {}) if self._coordinator.data else {}

    async def _async_tick(self, now: datetime) -> None:
        """Run what is due this minute; never two ticks at the same time."""
        if self._running or not self._settings.get("scheduler_enabled", True):
            return
        self._running = True
        try:
            await self.async_run(dt_util.as_local(now))
        finally:
            self._running = False

    async def async_run(self, now_local: datetime, *, force: bool = False) -> dict[str, Any]:
        """Run the jobs due at ``now_local``. ``force`` runs every periodic job."""
        results: dict[str, Any] = {}
        coordinator = self._coordinator

        # The daily promo checks its own time and day; it is cheap to ask.
        await self._job(results, "promo", coordinator.async_scheduled_promo)

        if not force and now_local.minute % SCHEDULER_INTERVAL_MIN:
            return results

        # Offers to the operators: always, they are part of running the day.
        await self._job(results, "offers", coordinator.async_expire_offers)
        await self._job(results, "monthly_report", coordinator.async_monthly_report_tick)

        settings = self._settings
        if in_quiet_hours(
            now_local,
            str(settings.get("quiet_hours_start") or ""),
            str(settings.get("quiet_hours_end") or ""),
        ):
            results["guest_messages"] = "orario di silenzio"
            return results

        await self._job(results, "reminders", coordinator.async_send_reminders)
        await self._job(results, "reviews", coordinator.async_send_review_requests)
        await self._job(results, "promo_vouchers", coordinator.async_promo_voucher_tick)
        await self._job(results, "loyalty", coordinator.async_loyalty_tick)
        await self._job(
            results, "voucher_expiry", coordinator.async_send_voucher_expiry_reminders
        )
        return results

    async def _job(
        self,
        results: dict[str, Any],
        name: str,
        job: Callable[[], Awaitable[dict[str, Any]]],
    ) -> None:
        """Run one job; a failure is logged and never stops the others."""
        try:
            results[name] = await job()
        except Exception:  # noqa: BLE001 - one broken job must not stop the rest
            _LOGGER.exception("Attività pianificata '%s' non riuscita", name)
            results[name] = {"error": True}
        self.last_run[name] = {
            "at": dt_util.utcnow().isoformat(),
            "result": results[name],
        }


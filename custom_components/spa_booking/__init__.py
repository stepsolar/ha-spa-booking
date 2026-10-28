"""The SPA Booking integration.

Manages SPA appointments: treatments with their duration, operators, client
cards and a day agenda grouped by operator and category.
"""

from __future__ import annotations

import logging

from homeassistant.components.frontend import add_extra_js_url
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import Event, HomeAssistant

from .const import DOMAIN, EVENT_ANSWER_REQUEST, EVENT_EXTERNAL_MESSAGE
from .coordinator import SpaBookingCoordinator
from .exceptions import SpaBookingError
from . import messaging
from .services import async_register_services, async_unregister_services

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.SENSOR, Platform.CALENDAR]

SpaBookingConfigEntry = ConfigEntry[SpaBookingCoordinator]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up the coordinator, platforms and services."""
    coordinator = SpaBookingCoordinator(hass, entry)
    await coordinator.async_load()

    entry.runtime_data = coordinator
    hass.data.setdefault(DOMAIN, coordinator)

    # Serve the management card to every Lovelace dashboard, so no manual
    # resource has to be added in the UI. It comes from our own HTTP view
    # (no-cache + ETag) instead of /local, whose month-long cache is why a
    # phone could keep showing an old card. The version comes from the settings
    # (fallback constant) so it can be bumped at runtime.
    if not hass.data.get(f"{DOMAIN}_card_view"):
        from .card_view import SpaBookingCardView

        hass.http.register_view(
            SpaBookingCardView(
                hass.config.path("www", "spa_booking", "spa-booking-card.js")
            )
        )
        hass.data[f"{DOMAIN}_card_view"] = True

    # Serve the standalone HTML page for the SPA Booking interface
    if not hass.data.get(f"{DOMAIN}_page_view"):
        from .card_view import SpaBookingPageView

        hass.http.register_view(
            SpaBookingPageView(
                hass.config.path("www", "spa_booking", "spa-booking-card.js")
            )
        )
        hass.data[f"{DOMAIN}_page_view"] = True

    # The hotel website's booking API: three unauthenticated views, guarded by
    # the shared token and by the switch in the card instead of by a session
    # (a foreign origin has none). Registered once, like the card view, so a
    # second config entry cannot claim the same paths twice.
    if not hass.data.get(f"{DOMAIN}_public_views"):
        from .public import (
            SpaBookingPublicAvailabilityView,
            SpaBookingPublicRequestView,
            SpaBookingPublicTreatmentsView,
        )

        hass.http.register_view(SpaBookingPublicTreatmentsView)
        hass.http.register_view(SpaBookingPublicAvailabilityView)
        hass.http.register_view(SpaBookingPublicRequestView)
        hass.data[f"{DOMAIN}_public_views"] = True

    add_extra_js_url(hass, coordinator.card_js_url())
    await coordinator._async_sync_card_resource()

    # The reply automations in packages/spa_booking.yaml translate an inbound
    # WhatsApp message, a WhatsApp reaction and a Telegram button press into
    # this one event, so the answer parsing lives here rather than in YAML.
    async def _on_answer_request(event: Event) -> None:
        data = dict(event.data)
        # An informational word (AIUTO, OGGI, DOMANI, …) is not an answer:
        # it sends the operator the matching message instead.
        text = str(data.get("text") or "")
        if text:
            try:
                handled = await coordinator.async_send_operator_info(
                    str(data.get("channel") or ""), data.get("chat_id"), text
                )
            except SpaBookingError as err:
                _LOGGER.warning("Invio messaggio informativo fallito: %s", err)
                handled = False
            if handled:
                return
        answer = str(data.get("answer") or "")
        if not answer:
            answer = messaging.parse_reaction(str(data.get("emoji") or "")) or ""
        if not answer:
            answer = messaging.parse_answer(str(data.get("text") or "")) or ""
        if not answer:
            # A message that is not an answer is normal (chat between
            # operators), but when the desk wonders why a confirmation was
            # not read, a DEBUG line is invisible: log the sender and the
            # truncated text at WARNING so the cause is findable.
            _LOGGER.warning(
                "Messaggio %s da %s non riconosciuto come risposta: %r",
                data.get("source") or "sconosciuto",
                data.get("chat_id") or "?",
                (data.get("text") or data.get("emoji") or "")[:80],
            )
            # A WhatsApp message from a number that is not an operator is an
            # external request: save it for the sensor and fire the event
            # for the notification automation.
            if (
                str(data.get("channel") or "") == "whatsapp"
                and not data.get("operator_id")
            ):
                text = str(data.get("text") or "").strip()
                if text:
                    try:
                        await coordinator.async_add_external_message(
                            str(data.get("chat_id") or ""), text
                        )
                    except Exception:  # noqa: BLE001 - sensor update must not break the handler
                        _LOGGER.exception("Salvataggio messaggio esterno fallito")
            return
        try:
            result = await coordinator.async_answer_from_operator(
                answer,
                operator_id=data.get("operator_id"),
                chat_id=data.get("chat_id"),
                channel=data.get("channel"),
                appointment_id=data.get("appointment_id"),
                source=str(data.get("source") or "evento"),
                text=str(data.get("text") or ""),
            )
        except SpaBookingError as err:
            _LOGGER.warning("Risposta a un'offerta rifiutata: %s", err)
            return
        if not result.get("handled"):
            reason = str(result.get("reason") or "")
            if (
                str(data.get("channel") or "") == "whatsapp"
                and reason.startswith("Nessuna operatrice collegata")
            ):
                # A WAHA inbound event is only published for configured
                # recipients, so an unknown sender is usually an operator not
                # yet added as a WAHA recipient.
                _LOGGER.warning(
                    "Messaggio WhatsApp da %s: nessuna operatrice riconosciuta "
                    "(aggiungerla come destinatario nell'integrazione WAHA)",
                    data.get("chat_id") or "sconosciuto",
                )
            else:
                _LOGGER.warning("Risposta offerta non applicata: %s", reason)

    entry.async_on_unload(
        hass.bus.async_listen(EVENT_ANSWER_REQUEST, _on_answer_request)
    )

    # Inbound WhatsApp answers: the webhook is claimed now when the gateway
    # already has its id, so a restart keeps receiving them. The first
    # activation (or a move to another WAHA) still needs the card's button,
    # because only then is the session told where to post.
    coordinator._async_register_waha_inbound()
    entry.async_on_unload(coordinator.async_unregister_waha_inbound)

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    async_register_services(hass)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry and its services."""
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        async_unregister_services(hass)
        hass.data.pop(DOMAIN, None)
    return unloaded
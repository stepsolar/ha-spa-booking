"""The public booking API the hotel website calls.

The website lives on another origin: it has no Lovelace session and cannot
use the websocket the card talks through. Three views answer it instead, all
under ``/api/spa_booking/public``:

``GET treatments``
    the treatments the site may show — name, category and duration. No price:
    the website never shows it. Nothing about who works here. Only the ones
    the reception left visible on the website; a treatment hidden from the
    site is not listed here.
``GET availability``
    the start times still free for one treatment on one day.
``POST requests``
    the guest's request, filed straight into the Richieste tab of the card.

None of them is authenticated by Home Assistant: a browser on a foreign
domain cannot send its auth headers. What guards them is the shared token
from the settings — compared in constant time, so a guess does not get faster
as it gets closer — and the master switch: while the website is off in the
card, every view answers 404 as if it had never existed.

A request never becomes an appointment from here. It reaches the desk as
pending, exactly like a request taken by phone, and the reception confirms it
from the card: the site may propose a free hour, but the desk is still the one
that says yes.
"""

from __future__ import annotations

from collections import deque
import hashlib
import json
import logging
import time
from datetime import date
from pathlib import Path
from typing import Any

from aiohttp import web

from homeassistant.components.http import KEY_HASS, HomeAssistantView
from homeassistant.util import dt as dt_util

from .const import DOMAIN, REQUEST_SOURCE_WEB, VOUCHER_ACTIVE, WEB_API_BASE
from .coordinator import SpaBookingCoordinator
from .normalize import _norm_clock, _norm_date
from .exceptions import SpaBookingError, ValidationError

_LOGGER = logging.getLogger(__name__)

TREATMENTS_URL = f"{WEB_API_BASE}/treatments"
AVAILABILITY_URL = f"{WEB_API_BASE}/availability"
REQUESTS_URL = f"{WEB_API_BASE}/requests"
FORM_JS_URL = f"{WEB_API_BASE}/form.js"
FORM_JS_FILE = Path(__file__).parent / "frontend" / "spa-booking-form.js"

#: Longest strings the site may send. They are not business rules — they are
#: what keeps a public endpoint from filling the client cards with megabytes.
_MAX_NAME = 60
_MAX_PHONE = 30
_MAX_EMAIL = 120
_MAX_NOTES = 1000
#: Voucher codes are short (VCH-XXXXXXXX); anything longer is not a code.
_MAX_VOUCHER = 32


#: Requests one address may make in the window, per kind of call. Generous
#: for a guest clicking through the form (and behind a reverse proxy without
#: ``use_x_forwarded_for`` every guest shares the proxy's address), tight
#: enough that nobody can probe voucher codes or flood the Richieste list.
_RATE_WINDOW_SECONDS = 600
_RATE_LIMITS = {"read": 600, "voucher": 30, "request": 20}
_MAX_TRACKED_ADDRESSES = 2048


class RateLimiter:
    """A sliding-window counter per (kind, client address), in memory."""

    def __init__(self, limits: dict[str, int], window: float) -> None:
        self._limits = limits
        self._window = window
        self._hits: dict[tuple[str, str], deque[float]] = {}

    def allow(self, kind: str, address: str, now: float | None = None) -> bool:
        """Record one hit; False when the address is over its limit."""
        now = time.monotonic() if now is None else now
        key = (kind, address or "?")
        hits = self._hits.get(key)
        if hits is None:
            if len(self._hits) >= _MAX_TRACKED_ADDRESSES:
                self._prune(now)
            hits = self._hits[key] = deque()
        while hits and now - hits[0] > self._window:
            hits.popleft()
        if len(hits) >= self._limits.get(kind, 60):
            return False
        hits.append(now)
        return True

    def _prune(self, now: float) -> None:
        """Forget the addresses that have been quiet for a whole window."""
        for key in [k for k, v in self._hits.items() if not v or now - v[-1] > self._window]:
            del self._hits[key]
        if len(self._hits) >= _MAX_TRACKED_ADDRESSES:
            self._hits.clear()


RATE_LIMITER = RateLimiter(_RATE_LIMITS, _RATE_WINDOW_SECONDS)


def _bearer(request: web.Request) -> str:
    """The token from ``Authorization: Bearer …``, empty when absent.

    The header only: a token in the query string would land in the access
    log of every proxy in between, and this one is meant to be rotated the
    moment it leaks.
    """
    header = str(request.headers.get("Authorization") or "")
    if header[:7].lower() != "bearer ":
        return ""
    return header[7:].strip()


class _PublicView(HomeAssistantView):
    """Base for the three views the website calls.

    Not authenticated by Home Assistant (the site has no session), CORS
    allowed (it is a foreign origin), and gated by the token instead.
    """

    requires_auth = False
    #: The website runs on another domain, so its browser would refuse the
    #: answer without this. HA's own CORS middleware then adds the headers
    #: and answers the preflight, because ``cors_allowed`` opts us in.
    cors_allowed = True

    def _gate(
        self, request: web.Request, kind: str = "read"
    ) -> SpaBookingCoordinator | web.Response:
        """Return the coordinator when the site may answer, else the refusal.

        A switched-off site must look nonexistent: a stranger must not be
        able to probe this path and learn that Home Assistant runs a booking
        API behind it. A wrong token is a plain 401 with nothing to go on.
        """
        hass = request.app[KEY_HASS]
        coordinator = hass.data.get(DOMAIN)
        if not isinstance(coordinator, SpaBookingCoordinator):
            return web.Response(status=404, text="Not found")
        if not coordinator.web_enabled:
            return web.Response(status=404, text="Not found")
        if not RATE_LIMITER.allow(kind, str(request.remote or "")):
            return self.json(
                {"message": "Troppe richieste: riprova tra qualche minuto"},
                status_code=429,
            )
        if not coordinator.web_token_ok(_bearer(request)):
            return self.json({"message": "Token non valido"}, status_code=401)
        return coordinator

    @classmethod
    def _failure(cls, err: Exception) -> web.Response:
        """Turn a business error into the message the site can show.

        ``SpaBookingError`` carries an Italian sentence written for a person,
        so it goes out as it is; anything else is ours to log and theirs to
        see as a generic failure — a stack trace on a public endpoint teaches
        an attacker how the code is laid out.
        """
        if isinstance(err, SpaBookingError):
            return cls.json({"message": str(err)}, status_code=400)
        _LOGGER.error("Richiesta pubblica fallita: %s", err, exc_info=True)
        return cls.json({"message": "Errore interno"}, status_code=500)

    @staticmethod
    async def _payload(request: web.Request) -> dict[str, Any]:
        """Read the body as JSON, whatever content type the site sends.

        Parsed by hand rather than with ``request.json()`` so a form posting
        ``text/plain`` — which some plugins rewrite on the way out — still
        works instead of failing on the header check.
        """
        try:
            raw = await request.text()
            data = json.loads(raw) if raw.strip() else {}
        except (ValueError, UnicodeDecodeError) as err:
            raise ValidationError("Corpo della richiesta non valido") from err
        if not isinstance(data, dict):
            raise ValidationError("Corpo della richiesta non valido")
        return data


class SpaBookingPublicTreatmentsView(_PublicView):
    """List the active treatments, as the website shows them."""

    url = TREATMENTS_URL
    name = "api:spa_booking:public_treatments"

    async def get(self, request: web.Request) -> web.Response:
        """Return name, category and duration of every visible one.

        The price is deliberately absent: the site never shows it, so it does
        not travel either — hiding it on screen would still leave it in the
        browser's network tab.

        A treatment the reception kept off the site never leaves this list:
        the site cannot offer what it cannot see.
        """
        kind = "voucher" if request.query.get("code") else "read"
        coordinator = self._gate(request, kind)
        if isinstance(coordinator, web.Response):
            return coordinator
        try:
            settings = coordinator._web_settings
            show_prices = bool(settings.get("web_show_prices"))
            items = []
            for treatment in coordinator.treatments:
                if not treatment.get("active", True):
                    continue
                if not treatment.get("web_visible", True):
                    continue
                payload = coordinator.treatment_payload(treatment)
                item = {
                    "id": payload["id"],
                    "name": payload["name"],
                    # The category is what the site groups its list by;
                    # the ids behind it stay inside.
                    "category_name": payload.get("category_name") or "",
                    "duration_min": payload["duration_min"],
                }
                # The price only when the reception chose to show it.
                if show_prices and payload.get("price") is not None:
                    item["price"] = payload["price"]
                items.append(item)
            items.sort(key=lambda item: (item["category_name"], item["name"]))
            # What the form needs to draw itself (2.2.0b3).
            site = {
                "show_prices": show_prices,
                "accent": settings.get("web_accent") or "",
                "max_days_ahead": settings.get("web_max_days_ahead") or 60,
            }

            code = str(request.query.get("code") or "").strip().upper()
            if not code:
                return self.json({"treatments": items, "site": site})

            voucher = next(
                (v for v in coordinator.vouchers if str(v.get("code") or "").upper() == code),
                None,
            )
            # One answer for unknown and used codes: telling them apart would
            # let a stranger learn which codes exist.
            if voucher is None or str(voucher.get("status") or "") != VOUCHER_ACTIVE:
                raise ValidationError(f"Il voucher {code} non è valido")
            expires = _norm_date(voucher.get("expires_on"))
            if expires and date.fromisoformat(expires) < dt_util.now().date():
                raise ValidationError(f"Il voucher {code} è scaduto")

            payload_people = []
            for person in voucher.get("people") or []:
                treatment_ids = [str(t) for t in person.get("treatment_ids") or [] if t]
                treatments = []
                for treatment_id in treatment_ids:
                    t = next(
                        (x for x in coordinator.treatments if x.get("id") == treatment_id),
                        None,
                    )
                    treatments.append(
                        {
                            "treatment_id": treatment_id,
                            "name": str(t.get("name") or "") if t else "",
                            "duration_min": int(t.get("duration_min") or 0) if t else 0,
                        }
                    )
                payload_people.append(
                    {
                        "name": str(person.get("name") or "").strip(),
                        "treatment_ids": treatment_ids,
                        "treatments": treatments,
                    }
                )
            return self.json(
                {
                    "treatments": items,
                    "site": site,
                    "voucher": {
                        "code": code,
                        # The name only pre-fills the form; the phone number
                        # is never handed out to whoever types a code.
                        "recipient_name": str(voucher.get("recipient_name") or "").strip(),
                        "expires_on": expires,
                        "people": payload_people,
                    },
                }
            )
        except Exception as err:  # noqa: BLE001 — one place for every failure
            return self._failure(err)


class SpaBookingPublicAvailabilityView(_PublicView):
    """Offer the start times still free for one treatment on one day."""

    url = AVAILABILITY_URL
    name = "api:spa_booking:public_availability"

    async def get(self, request: web.Request) -> web.Response:
        """Return the day's free slots for ``treatment_id`` on ``date``."""
        coordinator = self._gate(request)
        if isinstance(coordinator, web.Response):
            return coordinator
        try:
            treatment_id = str(request.query.get("treatment_id") or "").strip()
            if not treatment_id:
                raise ValidationError("Manca il trattamento richiesto")
            day_raw = str(request.query.get("date") or "").strip()
            if not day_raw:
                raise ValidationError("Manca la data richiesta")
            try:
                day = date.fromisoformat(day_raw)
            except ValueError as err:
                raise ValidationError("Data non valida") from err

            result = await coordinator.async_public_availability(day, treatment_id)
            return self.json(result)
        except Exception as err:  # noqa: BLE001 — one place for every failure
            return self._failure(err)


class SpaBookingPublicRequestView(_PublicView):
    """Take a guest's request from the website into the card's list."""

    url = REQUESTS_URL
    name = "api:spa_booking:public_request"

    async def post(self, request: web.Request) -> web.Response:
        """File the request as pending, and tell the guest its code."""
        coordinator = self._gate(request, "request")
        if isinstance(coordinator, web.Response):
            return coordinator
        try:
            data = await self._payload(request)

            day_raw = str(data.get("date") or "").strip()
            try:
                day = date.fromisoformat(day_raw)
            except ValueError as err:
                raise ValidationError("Indica una data valida") from err

            entries = data.get("entries")
            if not isinstance(entries, list) or not entries:
                raise ValidationError("Aggiungi almeno un trattamento")
            clean_entries: list[dict[str, Any]] = []
            # The entries already placed, so two people cannot both be
            # promised the one operator who is free at that hour.
            planned: list[dict[str, Any]] = []
            for entry in entries:
                if not isinstance(entry, dict):
                    continue
                treatment_id = str(entry.get("treatment_id") or "").strip()
                # Normalized exactly as the card does it, so "9:00" from the
                # site and "09:00" from the agenda are the same hour.
                clock = _norm_clock(entry.get("time"))
                if not treatment_id or not clock:
                    continue
                # Re-ask the agenda for every entry: the hour the site showed
                # was computed a moment ago, and somebody may have taken it
                # since. A request does not hold a slot, but offering an hour
                # that is already gone would only make the desk's first call
                # an awkward one.
                availability = await coordinator.async_public_availability(
                    day, treatment_id, planned
                )
                offered = {slot["time"] for slot in availability["slots"]}
                if clock not in offered:
                    raise ValidationError(
                        f"L'orario {clock} non è più disponibile per "
                        f"{availability['treatment_name']}"
                    )
                planned.append(
                    coordinator.plan_public_entry(day, treatment_id, clock, planned)
                )
                item: dict[str, Any] = {"treatment_id": treatment_id, "time": clock}
                # The form books person by person: keep who each entry is for,
                # so confirming creates one appointment per entry.
                person = entry.get("person")
                if isinstance(person, int) and 0 <= person < 50:
                    item["person"] = person
                clean_entries.append(item)
            if not clean_entries:
                raise ValidationError("Trattamento non valido nella richiesta")

            first_name = str(data.get("first_name") or "").strip()[:_MAX_NAME]
            last_name = str(data.get("last_name") or "").strip()[:_MAX_NAME]
            phone = str(data.get("phone") or "").strip()[:_MAX_PHONE]
            email = str(data.get("email") or "").strip()[:_MAX_EMAIL]
            notes = str(data.get("notes") or "").strip()[:_MAX_NOTES]
            # Optional: a guest who has a gift voucher types its code. The
            # coordinator checks it if it matches a real one and records it
            # otherwise, exactly as the desk does.
            voucher_code = (
                str(data.get("voucher_code") or "").strip().upper()[:_MAX_VOUCHER]
            )
            if not (first_name or last_name):
                raise ValidationError("Indica il nome dell'ospite")
            # Without a number the reception cannot call back and the
            # acknowledgement has nowhere to go, so the site asks for it.
            if not phone:
                raise ValidationError("Indica un numero di telefono")

            result = await coordinator.async_create_request(
                first_name=first_name,
                last_name=last_name,
                phone=phone,
                email=email,
                date=day_raw,
                people=data.get("people", 1),
                entries=clean_entries,
                notes=notes,
                voucher_code=voucher_code,
                source=REQUEST_SOURCE_WEB,
            )
            # The payload carries the guest's own card back; the site only
            # needs what it can show as a receipt.
            return self.json(
                {
                    "code": result.get("code"),
                    "date": result.get("date"),
                    "status": result.get("status"),
                },
                status_code=201,
            )
        except Exception as err:  # noqa: BLE001 — one place for every failure
            return self._failure(err)


class SpaBookingPublicFormView(_PublicView):
    """The form of the website, loaded by the two-line code on the site.

    No token is needed to read it: the file holds no secret, the token is in
    the page of the site and every call the form makes is gated as before.
    A site switched off in the card still answers 404. The browser asks
    again every time (no-cache) but gets a 304 while the file is unchanged,
    so a new version of Spa Booking reaches the site at once.
    """

    url = FORM_JS_URL
    name = "api:spa_booking:public_form"

    _cache: tuple[float, str, str] | None = None

    async def get(self, request: web.Request) -> web.Response:
        """Serve frontend/spa-booking-form.js."""
        hass = request.app[KEY_HASS]
        coordinator = hass.data.get(DOMAIN)
        if not isinstance(coordinator, SpaBookingCoordinator) or not coordinator.web_enabled:
            return web.Response(status=404, text="Not found")
        if not RATE_LIMITER.allow("read", str(request.remote or "")):
            return web.Response(status=429, text="Too many requests")
        body, etag = await hass.async_add_executor_job(self._read)
        if not body:
            return web.Response(status=404, text="Not found")
        headers = {
            "Cache-Control": "no-cache",
            "ETag": etag,
        }
        if request.headers.get("If-None-Match") == etag:
            return web.Response(status=304, headers=headers)
        return web.Response(
            body=body.encode("utf-8"),
            content_type="application/javascript",
            charset="utf-8",
            headers=headers,
        )

    @classmethod
    def _read(cls) -> tuple[str, str]:
        """The file and its ETag, read again only when it changes on disk."""
        path = FORM_JS_FILE
        try:
            mtime = path.stat().st_mtime
        except OSError:
            return "", ""
        if cls._cache is None or cls._cache[0] != mtime:
            text = path.read_text(encoding="utf-8")
            digest = hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]
            cls._cache = (mtime, text, f'"{digest}"')
        return cls._cache[1], cls._cache[2]

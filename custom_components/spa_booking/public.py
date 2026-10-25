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

import json
import logging
from datetime import date
from typing import Any

from aiohttp import web

from homeassistant.components.http import KEY_HASS, HomeAssistantView

from .const import DOMAIN, REQUEST_SOURCE_WEB, WEB_API_BASE
from .coordinator import SpaBookingCoordinator, _norm_clock
from .exceptions import SpaBookingError, ValidationError

_LOGGER = logging.getLogger(__name__)

TREATMENTS_URL = f"{WEB_API_BASE}/treatments"
AVAILABILITY_URL = f"{WEB_API_BASE}/availability"
REQUESTS_URL = f"{WEB_API_BASE}/requests"

#: Longest strings the site may send. They are not business rules — they are
#: what keeps a public endpoint from filling the client cards with megabytes.
_MAX_NAME = 60
_MAX_PHONE = 30
_MAX_EMAIL = 120
_MAX_NOTES = 1000
#: Voucher codes are short (VCH-XXXXXXXX); anything longer is not a code.
_MAX_VOUCHER = 32


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
        self, request: web.Request
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
        coordinator = self._gate(request)
        if isinstance(coordinator, web.Response):
            return coordinator
        try:
            items = []
            for treatment in coordinator.treatments:
                if not treatment.get("active", True):
                    continue
                if not treatment.get("web_visible", True):
                    continue
                payload = coordinator.treatment_payload(treatment)
                items.append(
                    {
                        "id": payload["id"],
                        "name": payload["name"],
                        # The category is what the site groups its list by;
                        # the ids behind it stay inside.
                        "category_name": payload.get("category_name") or "",
                        "duration_min": payload["duration_min"],
                    }
                )
            items.sort(key=lambda item: (item["category_name"], item["name"]))
            return self.json({"treatments": items})
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
        coordinator = self._gate(request)
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
                    day, treatment_id
                )
                offered = {slot["time"] for slot in availability["slots"]}
                if clock not in offered:
                    raise ValidationError(
                        f"L'orario {clock} non è più disponibile per "
                        f"{availability['treatment_name']}"
                    )
                clean_entries.append({"treatment_id": treatment_id, "time": clock})
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

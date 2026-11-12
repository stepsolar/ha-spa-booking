"""The WordPress shop (2.7.0): vouchers sold online with «Buoni PDF».

Spa Booking reads the voucher codes sold on the hotel's WooCommerce shop
through the small «Spa Booking Connector» plugin, turns each into a gift
voucher with the treatments the product is paired with, and tells the shop
when a voucher is redeemed at the spa (on the guest's arrival).

The plugin answers only with the shared key (header ``X-Spa-Booking-Key``),
and it can also ping ``/api/spa_booking/wp/notify`` when an order is paid so
the voucher appears at once instead of at the next check.
"""

from __future__ import annotations

from datetime import datetime
import hmac
from typing import Any

from aiohttp import ClientError, web

from homeassistant.components.http import KEY_HASS, HomeAssistantView

from .const import DOMAIN

API = "/wp-json/spa-booking/v1"
NOTIFY_PATH = "/api/spa_booking/wp/notify"
#: How far back the shop is read: the vouchers last 180 days.
SYNC_DAYS = 200


class WpShopError(Exception):
    """The shop could not be reached, already in words for the desk."""


def product_key(product_id: Any, variation_id: Any = 0) -> str:
    """The key of a product (or of one of its variations) in the pairing."""
    return f"{int(product_id or 0)}:{int(variation_id or 0)}"


def mapping_for(mapping: dict[str, Any], product_id: Any, variation_id: Any) -> dict[str, Any] | None:
    """The pairing of a variation, else of its whole product."""
    for key in (product_key(product_id, variation_id), product_key(product_id, 0)):
        entry = mapping.get(key)
        if isinstance(entry, dict) and (entry.get("treatment_ids") or entry.get("extras") or entry.get("note")
                                        or entry.get("gift_card_mode")):
            return entry
    return None


def gift_card_of(entry: dict[str, Any] | None, paid: Any = None) -> float | None:
    """The gift card in euro a product carries (2.7.2), or None."""
    mode = str((entry or {}).get("gift_card_mode") or "")
    try:
        if mode == "paid":
            return round(float(paid), 2) if paid not in (None, "") and float(paid) > 0 else None
        if mode == "fixed":
            amount = float((entry or {}).get("gift_card_amount") or 0)
            return round(amount, 2) if amount > 0 else None
    except (TypeError, ValueError):
        return None
    return None


def people_of(entry: dict[str, Any] | None, paid: Any = None) -> list[dict[str, Any]]:
    """The voucher's people: each one gets every paired treatment and accessory.

    A gift card goes once, on the first person: it is the voucher's credit.
    """
    gift = gift_card_of(entry, paid)
    if not entry or not (entry.get("treatment_ids") or entry.get("extras") or gift):
        return []
    count = max(1, min(10, int(entry.get("people") or 1)))
    treatments = [str(t) for t in entry.get("treatment_ids") or [] if t]
    extras = [str(e) for e in entry.get("extras") or [] if e]
    return [{"name": "", "treatment_ids": list(treatments), "extras": list(extras),
             "gift_card_amount": gift if index == 0 else None} for index in range(count)]


def note_of(entry: dict[str, Any] | None) -> str:
    """What the package also includes, in words (what has no record here)."""
    return str((entry or {}).get("note") or "").strip()


async def _request(session: Any, method: str, base: str, secret: str, path: str, **kwargs: Any) -> dict[str, Any]:
    url = base.rstrip("/") + API + path
    try:
        async with session.request(method, url, timeout=25,
                                   headers={"X-Spa-Booking-Key": secret, "Accept": "application/json"}, **kwargs) as response:
            try:
                body = await response.json(content_type=None)
            except ValueError:
                body = {}
            if response.status == 404 and path != "/redeem":
                raise WpShopError("Sul sito manca il plugin «Spa Booking Connector» (o non è attivo).")
            if response.status in (401, 403):
                raise WpShopError("Il sito ha rifiutato la chiave: copia di nuovo la chiave nel plugin su WordPress.")
            if response.status >= 400:
                message = body.get("message") if isinstance(body, dict) else ""
                raise WpShopError(f"Il sito ha risposto {response.status}: {message or 'errore'}")
            return body if isinstance(body, dict) else {}
    except (ClientError, TimeoutError) as err:
        raise WpShopError(f"Sito non raggiungibile: {err}") from err


async def status(session: Any, base: str, secret: str) -> dict[str, Any]:
    return await _request(session, "GET", base, secret, "/status")


async def products(session: Any, base: str, secret: str) -> list[dict[str, Any]]:
    body = await _request(session, "GET", base, secret, "/products")
    return [p for p in body.get("products") or [] if isinstance(p, dict)]


async def vouchers(session: Any, base: str, secret: str, days: int = SYNC_DAYS) -> list[dict[str, Any]]:
    body = await _request(session, "GET", base, secret, "/vouchers", params={"days": str(days)})
    return [v for v in body.get("vouchers") or [] if isinstance(v, dict) and v.get("code")]


async def redeem(session: Any, base: str, secret: str, code: str, note: str = "") -> dict[str, Any]:
    return await _request(session, "POST", base, secret, "/redeem", json={"code": code, "note": note})


def expiry_of(item: dict[str, Any]) -> str:
    """The voucher's last day as YYYY-MM-DD, or ""."""
    text = str(item.get("expires") or "")[:10]
    try:
        datetime.strptime(text, "%Y-%m-%d")
    except ValueError:
        return ""
    return text


class WpNotifyView(HomeAssistantView):
    """The shop's ping when an order is paid: check the shop now."""

    url = NOTIFY_PATH
    name = "api:spa_booking:wp_notify"
    requires_auth = False

    async def post(self, request: web.Request) -> web.Response:
        hass = request.app[KEY_HASS]
        coordinator = hass.data.get(DOMAIN)
        if coordinator is None:
            return web.Response(status=404, text="Not found")
        settings = coordinator._data.get("settings", {})
        secret = str(settings.get("wp_secret") or "")
        given = str(request.headers.get("X-Spa-Booking-Key") or "")
        if not settings.get("wp_enabled") or not secret or not hmac.compare_digest(secret, given):
            return web.Response(status=404, text="Not found")
        hass.async_create_task(coordinator.async_wp_sync(reason="notifica dal sito"))
        return web.json_response({"ok": True})

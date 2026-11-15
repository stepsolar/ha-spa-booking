"""The people of the website (3.3.0): newsletter, shop buyers, web bookings.

Spa Booking reads them through the «Spa Booking Connector» plugin (1.2.0)
and keeps one card per person, keyed by e-mail (or by phone for a web
booking without e-mail), with where she came from. The newsletter discount
codes (Coupon Box) become loyalty-style vouchers with ``source`` newsletter.

Who may receive a campaign: a confirmed newsletter subscriber, a buyer of the
shop (offers on similar services, art. 130 c. 4 Codice Privacy), or a guest
who ticked «Voglio ricevere le offerte» on the booking form; never anybody
who unsubscribed.
"""

from __future__ import annotations

import re
import secrets
from typing import Any

#: The groups a campaign can be sent to.
GROUPS = ("newsletter", "shop", "web", "coupon")
#: How often the site is read again (seconds).
SYNC_EVERY = 3600


def _new_id() -> str:
    return "sit_" + secrets.token_hex(5)


def key_of(email: str = "", phone: str = "") -> str:
    """One person: the e-mail, else the phone's digits."""
    email = str(email or "").strip().lower()
    if "@" in email:
        return email
    digits = re.sub(r"\D", "", str(phone or ""))
    if digits.startswith("00"):
        digits = digits[2:]
    if len(digits) == 10 and digits.startswith("3"):
        digits = "39" + digits
    return f"tel:{digits}" if len(digits) >= 8 else ""


def norm_contact(raw: Any) -> dict[str, Any]:
    raw = raw if isinstance(raw, dict) else {}

    def num(value: Any, cast: Any = int) -> Any:
        try:
            return max(0, cast(value or 0))
        except (TypeError, ValueError):
            return cast(0)

    return {
        "id": str(raw.get("id") or _new_id()),
        "key": str(raw.get("key") or key_of(raw.get("email"), raw.get("phone"))),
        "email": str(raw.get("email") or "").strip().lower(),
        "first_name": str(raw.get("first_name") or "").strip(),
        "last_name": str(raw.get("last_name") or "").strip(),
        "phone": str(raw.get("phone") or "").strip(),
        "client_id": str(raw.get("client_id") or ""),
        # «Newsletter» plugin status: C confirmed, S waiting, U unsubscribed, B bounced.
        "newsletter": str(raw.get("newsletter") or "")[:1].upper(),
        "newsletter_at": str(raw.get("newsletter_at") or ""),
        "shop_orders": num(raw.get("shop_orders")),
        "shop_total": round(num(raw.get("shop_total"), float), 2),
        "shop_last_at": str(raw.get("shop_last_at") or ""),
        "web_bookings": num(raw.get("web_bookings")),
        "web_last_at": str(raw.get("web_last_at") or ""),
        "web_consent": bool(raw.get("web_consent", False)),
        "unsubscribed": bool(raw.get("unsubscribed", False)),
        "unsubscribed_at": str(raw.get("unsubscribed_at") or ""),
        "unsub_token": str(raw.get("unsub_token") or secrets.token_urlsafe(18)),
        "campaigns_sent": num(raw.get("campaigns_sent")),
        "campaign_last_at": str(raw.get("campaign_last_at") or ""),
        "created_at": str(raw.get("created_at") or ""),
    }


def can_mail(contact: dict[str, Any]) -> bool:
    """Whether promotional e-mails may go to her."""
    if contact.get("unsubscribed") or "@" not in str(contact.get("email") or ""):
        return False
    return (contact.get("newsletter") == "C" or int(contact.get("shop_orders") or 0) > 0
            or bool(contact.get("web_consent")))


def in_group(contact: dict[str, Any], group: str, valid_codes: set[str]) -> bool:
    if group == "newsletter":
        return contact.get("newsletter") == "C"
    if group == "shop":
        return int(contact.get("shop_orders") or 0) > 0
    if group == "web":
        return int(contact.get("web_bookings") or 0) > 0 and bool(contact.get("web_consent"))
    if group == "coupon":
        return str(contact.get("email") or "") in valid_codes
    return False


def _pick(old: str, new: Any) -> str:
    new = str(new or "").strip()
    return new or old


def merge(existing: list[dict[str, Any]], newsletter: list[dict[str, Any]], buyers: list[dict[str, Any]],
          web: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The list again from what the site and the web bookings say now.

    What only Spa Booking knows (the unsubscribe, the campaigns sent, the
    token of the link) is kept; what the site says is taken fresh, so a
    person who left the newsletter there is no subscriber here either.
    """
    old = {c["key"]: c for c in (norm_contact(c) for c in existing) if c["key"]}
    out: dict[str, dict[str, Any]] = {}

    def card(email: str = "", phone: str = "", when: str = "") -> dict[str, Any] | None:
        key = key_of(email, phone)
        if not key:
            return None
        if key not in out:
            base = old.get(key)
            if base is None and "@" in key and phone:
                # Known so far only by the phone (a web booking without e-mail).
                base = old.get(key_of("", phone))
            contact = dict(base) if base else norm_contact({"key": key, "created_at": when})
            contact.update({"key": key, "newsletter": "", "newsletter_at": "", "shop_orders": 0, "shop_total": 0.0,
                            "shop_last_at": "", "web_bookings": 0, "web_last_at": "", "web_consent": False})
            if "@" in key:
                contact["email"] = key
            out[key] = contact
        return out[key]

    for row in newsletter:
        contact = card(row.get("email"), row.get("phone"), str(row.get("created") or ""))
        if contact is None:
            continue
        contact["first_name"] = _pick(contact["first_name"], row.get("first"))
        contact["last_name"] = _pick(contact["last_name"], row.get("last"))
        contact["phone"] = _pick(contact["phone"], row.get("phone"))
        contact["newsletter"] = str(row.get("status") or "")[:1].upper()
        contact["newsletter_at"] = str(row.get("created") or "")
    for row in buyers:
        contact = card(row.get("email"), row.get("phone"), str(row.get("first_order") or ""))
        if contact is None:
            continue
        contact["first_name"] = _pick(contact["first_name"], row.get("first"))
        contact["last_name"] = _pick(contact["last_name"], row.get("last"))
        contact["phone"] = _pick(contact["phone"], row.get("phone"))
        contact["shop_orders"] += int(row.get("orders") or 0)
        contact["shop_total"] = round(contact["shop_total"] + float(row.get("total") or 0), 2)
        contact["shop_last_at"] = max(contact["shop_last_at"], str(row.get("last_order") or ""))
    for row in web:
        contact = card(row.get("email"), row.get("phone"), str(row.get("at") or ""))
        if contact is None:
            continue
        contact["first_name"] = _pick(contact["first_name"], row.get("first_name"))
        contact["last_name"] = _pick(contact["last_name"], row.get("last_name"))
        contact["phone"] = _pick(contact["phone"], row.get("phone"))
        contact["client_id"] = _pick(contact["client_id"], row.get("client_id"))
        contact["web_bookings"] += 1
        contact["web_last_at"] = max(contact["web_last_at"], str(row.get("at") or ""))
        contact["web_consent"] = contact["web_consent"] or bool(row.get("marketing"))
    for contact in out.values():
        if not contact["created_at"]:
            contact["created_at"] = min(x for x in (contact["newsletter_at"], contact["shop_last_at"],
                                                    contact["web_last_at"]) if x) if any(
                (contact["newsletter_at"], contact["shop_last_at"], contact["web_last_at"])) else ""
    return sorted(out.values(), key=lambda c: c["created_at"], reverse=True)

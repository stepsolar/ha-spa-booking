"""Data coordinator for the SPA Booking integration.

Holds every record (categories, treatments, operators, clients, appointments),
persists it to `.storage/spa_booking.json` and exposes the business rules:
treatment duration decides the end time, an operator can never be double
booked, and neither can a client.
"""

from __future__ import annotations

import asyncio
import copy
import json
from datetime import date, datetime, time, timedelta
import hashlib
import hmac
import logging
import re
import secrets
from pathlib import Path
from typing import Any, Final
from collections import deque
from uuid import uuid4

from homeassistant.components import webhook
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.device_registry import DeviceEntryType
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util import dt as dt_util

from .const import (
    KEY_VOUCHERS,
    KEY_PROMO_VOUCHERS,
    PROMO_VOUCHER_CODE_PREFIX,
    PROMO_VOUCHER_PENDING,
    PROMO_VOUCHER_REDEEMED,
    PROMO_VOUCHER_SENT,
    VOUCHER_ACTIVE,
    VOUCHER_REDEEMED,
    VOUCHER_VALID_MONTHS,
    ANSWER_AVAILABLE,
    ANSWER_CONFIRM,
    ANSWER_DECLINE,
    APPEARANCE_MODES,
    CARD_JS_URL,
    CARD_JS_URL_LEGACY,
    CARD_JS_VERSION,
    CLOSURE_SCOPES,
    DEFAULT_APPEARANCE,
    DEFAULT_DEPOSIT_INTESTATARIO,
    DEFAULT_DEPOSIT_IBAN,
    DEFAULT_DEPOSIT_MESSAGE,
    DEFAULT_GUEST_HEADER,
    DEFAULT_PROMO_INTERVAL_SEC,
    DEFAULT_PROMO_MESSAGE,
    DEFAULT_PROMO_TIME,
    DEFAULT_PROMO_VOUCHER_AFTER_HOURS,
    DEFAULT_PROMO_VOUCHER_AUTO,
    DEFAULT_PROMO_VOUCHER_DAYS,
    DEFAULT_PROMO_VOUCHER_DISCOUNT,
    DEFAULT_PROMO_VOUCHER_MAX_SPEND,
    DEFAULT_PROMO_VOUCHER_MESSAGE,
    DEFAULT_PROMO_VOUCHER_MIN_SPEND,
    DOMAIN,
    EVENT_APPOINTMENT_CANCELLED,
    EVENT_APPOINTMENT_CREATED,
    EVENT_OFFER_ANSWERED,
    EVENT_EXTERNAL_MESSAGE,
    KEY_APPOINTMENTS,
    DEFAULT_CATEGORY_PAUSE_MIN,
    DEFAULT_OFFER_REMINDER_HOURS,
    DEFAULT_OFFER_TIMEOUT_HOURS,
    DEFAULT_REPORT_TELEGRAM_CHATS,
    DEFAULT_REPORT_TIME,
    DEFAULT_TELEGRAM_ENTRY_ID,
    DEFAULT_REVIEW_MESSAGE,
    DEFAULT_REQUEST_MESSAGE,
    DEFAULT_SUMMARY_MESSAGE,
    DEFAULT_APPOINTMENT_REMINDER_MESSAGE,
    DEFAULT_APPOINTMENT_REMINDER_AUTO,
    DEFAULT_APPOINTMENT_REMINDER_HOURS,
    DEFAULT_REVIEW_REQUEST_AUTO,
    DEFAULT_REVIEW_REQUEST_AFTER_HOURS,
    DEFAULT_VOUCHER_EXPIRY_REMINDER_DAYS,
    DEFAULT_CARD_TITLE,
    DEFAULT_VOUCHER_EXPIRY_REMINDER_MESSAGE,
    DEFAULT_WAHA_SESSION,
    DEFAULT_WAHA_URL,
    DEFAULT_WEB_BREAK_END,
    DEFAULT_WEB_BREAK_START,
    DEFAULT_WEB_CLOSE_TIME,
    DEFAULT_WEB_ENABLED,
    DEFAULT_WEB_MAX_DAYS_AHEAD,
    DEFAULT_WEB_NOTIFY_WHATSAPP,
    DEFAULT_WEB_OPEN_TIME,
    DEFAULT_WEB_STEP_MIN,
    DEFAULT_WEB_TOKEN,
    REVIEW_REQUEST_WINDOW_HOURS,
    WEB_MAX_SLOTS,
    WEB_SNIPPET_TOKEN_PLACEHOLDER,
    KEY_CATEGORIES,
    KEY_CLIENTS,
    KEY_CLOSURES,
    KEY_PERMISSIONS,
    KEY_REQUESTS,
    KEY_OPERATORS,
    KEY_SETTINGS,
    KEY_SLOT_BLOCKS,
    KEY_TREATMENTS,
    PERMISSION_LEVELS,
    BOOKING_STATUSES,
    MAX_CLOSURE_DAYS,
    OPERATOR_ROLES,
    OPERATOR_ROLE_DEFAULT,
    PAYMENT_METHODS,
    GUEST_TYPE_DEFAULT,
    GUEST_TYPES,
    EXTRAS,
    EXTRAS_DEFAULT,
    ACCESSORY_DEFAULTS,
    OFFER_NONE,
    OFFER_PENDING,
    OFFER_UNASSIGNED,
    STORAGE_KEY,
    STORAGE_VERSION,
    STATUS_CANCELLED,
    STATUS_CONFIRMED,
    STATUS_PENDING,
    REQUEST_CONFIRMED,
    REQUEST_PENDING,
    REQUEST_SOURCE_DESK,
    REQUEST_SOURCE_WEB,
    REQUEST_SOURCES,
)
from .exceptions import (
    NotFoundError,
    OverlapError,
    SpaBookingError,
    ValidationError,
)
from . import messaging
from .waha import WahaAuthenticationError, WahaClient, WahaError
from .waha_inbound import WahaInbound

_LOGGER = logging.getLogger(__name__)


def _integration_version() -> str:
    """Return this integration's own version from its manifest."""
    try:
        manifest = json.loads(
            (Path(__file__).parent / "manifest.json").read_text(encoding="utf-8")
        )
        version = str(manifest.get("version") or "").strip()
        return version or "—"
    except Exception:  # noqa: BLE001 - a missing manifest must not break setup
        return "—"


#: The running backend version, shown in the card's "Versione del programma".
INTEGRATION_VERSION: Final = _integration_version()


def _new_id(prefix: str) -> str:
    """Return a short unique id."""
    return f"{prefix}_{uuid4().hex[:12]}"


def _read_text(path: str) -> str:
    """Return a UTF-8 text file, or an empty string when it cannot be read.

    Used for the website snippet, which lives as a plain file the desk can
    also download: a missing file must leave the card with a clear "not found"
    instead of an exception.
    """
    try:
        with open(path, encoding="utf-8") as handle:
            return handle.read()
    except OSError:
        return ""


#: A 5-char booking reference excludes the characters that look alike (0/O,
#: 1/I/L) so a code read off a phone screen is never ambiguous.
_CODE_CHARS = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
_CODE_LEN = 5


def _new_code(existing: set[str]) -> str:
    """Return a unique 5-char booking code not already in ``existing``."""
    while True:
        code = "".join(_CODE_CHARS[secrets.randbelow(len(_CODE_CHARS))] for _ in range(_CODE_LEN))
        if code not in existing:
            return code


_VOUCHER_CODE_LEN = 8


def _new_voucher_code(existing: set[str]) -> str:
    """Return a unique 8-char voucher code (without the VCH- prefix)."""
    while True:
        code = "".join(
            _CODE_CHARS[secrets.randbelow(len(_CODE_CHARS))]
            for _ in range(_VOUCHER_CODE_LEN)
        )
        if f"VCH-{code}" not in existing:
            return code


def _new_promo_voucher_code(existing: set[str]) -> str:
    """Return a unique loyalty voucher code, prefix included (e.g. FID-XXXXXXXX)."""
    while True:
        code = "".join(
            _CODE_CHARS[secrets.randbelow(len(_CODE_CHARS))]
            for _ in range(_VOUCHER_CODE_LEN)
        )
        full = f"{PROMO_VOUCHER_CODE_PREFIX}{code}"
        if full not in existing:
            return full


def _add_months(day: date, months: int) -> date:
    """Return the same day ``months`` months later, clamped to the month length."""
    index = day.month - 1 + months
    year = day.year + index // 12
    month = index % 12 + 1
    for last in (31, 30, 29, 28):
        try:
            return date(year, month, min(day.day, last))
        except ValueError:
            continue
    return day


def _norm_voucher(raw: Any) -> dict[str, Any]:
    """Return a stored voucher with every expected key and a clean shape."""
    raw = raw if isinstance(raw, dict) else {}
    people: list[dict[str, Any]] = []
    for person in raw.get("people") or []:
        if not isinstance(person, dict):
            continue
        gift = person.get("gift_card_amount")
        try:
            gift = float(gift) if gift is not None else None
            if gift is not None and gift < 0:
                gift = None
        except (TypeError, ValueError):
            gift = None
        people.append(
            {
                "name": str(person.get("name") or "").strip(),
                "treatment_ids": [str(t) for t in person.get("treatment_ids") or [] if t],
                "extras": [str(e) for e in person.get("extras") or [] if e],
                "gift_card_amount": gift,
            }
        )
    status = raw.get("status")
    return {
        "id": str(raw.get("id") or ""),
        "code": str(raw.get("code") or "").strip().upper(),
        "buyer_name": str(raw.get("buyer_name") or "").strip(),
        "buyer_phone": str(raw.get("buyer_phone") or "").strip(),
        "recipient_name": str(raw.get("recipient_name") or "").strip(),
        "recipient_phone": str(raw.get("recipient_phone") or "").strip(),
        "people": people,
        "created_at": str(raw.get("created_at") or ""),
        "expires_on": _norm_date(raw.get("expires_on")),
        "status": status if status in (VOUCHER_ACTIVE, VOUCHER_REDEEMED) else VOUCHER_ACTIVE,
        "redeemed_at": str(raw.get("redeemed_at") or ""),
        "appointment_ids": [str(i) for i in raw.get("appointment_ids") or [] if i],
    }


def _norm_promo_voucher(raw: Any) -> dict[str, Any]:
    """Return a stored loyalty voucher with every expected key and a clean shape.

    A loyalty voucher is a personal code a client receives after using the
    services: a percentage discount over a spend range, tied to her and to the
    appointment that earned it. It is kept apart from the sold gift vouchers.
    """
    raw = raw if isinstance(raw, dict) else {}
    status = raw.get("status")
    if status not in (
        PROMO_VOUCHER_PENDING,
        PROMO_VOUCHER_SENT,
        PROMO_VOUCHER_REDEEMED,
    ):
        status = PROMO_VOUCHER_PENDING
    return {
        "id": str(raw.get("id") or ""),
        "code": str(raw.get("code") or "").strip().upper(),
        "client_id": str(raw.get("client_id") or "").strip(),
        "first_name": str(raw.get("first_name") or "").strip(),
        "last_name": str(raw.get("last_name") or "").strip(),
        "phone": str(raw.get("phone") or "").strip(),
        "discount_percent": _norm_count(
            raw.get("discount_percent"), 1, 100, DEFAULT_PROMO_VOUCHER_DISCOUNT
        ),
        "min_spend": _norm_count(
            raw.get("min_spend"), 0, 100000, DEFAULT_PROMO_VOUCHER_MIN_SPEND
        ),
        "max_spend": _norm_count(
            raw.get("max_spend"), 0, 100000, DEFAULT_PROMO_VOUCHER_MAX_SPEND
        ),
        "created_at": str(raw.get("created_at") or ""),
        "send_at": str(raw.get("send_at") or ""),
        "sent_at": str(raw.get("sent_at") or ""),
        "redeemed_at": str(raw.get("redeemed_at") or ""),
        "appointment_id": str(raw.get("appointment_id") or "").strip(),
        "status": status,
        "expires_on": _norm_date(raw.get("expires_on")),
    }


def _parse_csv(text: str) -> list[list[str]]:
    """Parse a CSV string into rows of cells.

    Handles quoted fields (including embedded commas, quotes and newlines) so the
    desk can edit the export in a spreadsheet and import it back unchanged.
    """
    rows: list[list[str]] = []
    current_row: list[str] = []
    field: list[str] = []
    in_quotes = False
    i = 0
    length = len(text)
    while i < length:
        char = text[i]
        if in_quotes:
            if char == '"':
                if i + 1 < length and text[i + 1] == '"':
                    field.append('"')
                    i += 2
                    continue
                in_quotes = False
            else:
                field.append(char)
        elif char == '"':
            in_quotes = True
        elif char == ",":
            current_row.append("".join(field))
            field = []
        elif char in ("\n", "\r"):
            if char == "\r" and i + 1 < length and text[i + 1] == "\n":
                i += 1
            current_row.append("".join(field))
            rows.append(current_row)
            current_row = []
            field = []
        else:
            field.append(char)
        i += 1
    # Flush the last field/row.
    last = "".join(field)
    if last or current_row:
        current_row.append(last)
        rows.append(current_row)
    return rows


#: Weekday labels, Monday first: `datetime.weekday()` returns 0 for Monday and
#: 6 for Sunday, the same order the booking card uses for its weekday toggles.
WEEKDAY_LABELS = ("Lun", "Mar", "Mer", "Gio", "Ven", "Sab", "Dom")


def _fmt_window(start: str, end: str) -> str:
    """A readable "HH:MM-HH:MM" window, or an empty string when absent."""
    if not start and not end:
        return ""
    return f"{start or '--:--'}-{end or '--:--'}"


def _norm_parallel(value: Any) -> int:
    """Return a sane parallel-appointment count (0 = no limit)."""
    try:
        count = int(value)
    except (TypeError, ValueError):
        count = 0
    return max(0, count)


def _norm_category(raw: dict[str, Any]) -> dict[str, Any]:
    """Return a category with every expected key."""
    try:
        pause = int(raw.get("pause_min", DEFAULT_CATEGORY_PAUSE_MIN))
    except (TypeError, ValueError):
        pause = DEFAULT_CATEGORY_PAUSE_MIN

    def norm_day_list(values: Any) -> list[int]:
        """Weekdays (Mon=0 .. Sun=6) out of a raw list; unknown items dropped."""
        seen: list[int] = []
        for item in values or []:
            try:
                value = int(item)
            except (TypeError, ValueError):
                continue
            if 0 <= value <= 6 and value not in seen:
                seen.append(value)
        return seen

    def norm_days() -> list[int]:
        """Weekdays (Mon=0 .. Sun=6); empty means every day is bookable."""
        return norm_day_list(raw.get("days"))

    def norm_window_days(key: str, fallback: list[int]) -> list[int]:
        """Days of one window, falling back to the old single ``days`` list."""
        if raw.get(key) is None:
            return list(fallback)
        return norm_day_list(raw.get(key))

    def norm_window(key: str) -> str:
        """An HH:MM window endpoint; anything malformed becomes empty."""
        value = str(raw.get(key) or "").strip()
        return value[:5] if len(value) >= 5 else ""

    def norm_exclusive() -> list[str]:
        """Other categories this one must never overlap."""
        self_id = str(raw.get("id") or "")
        seen: list[str] = []
        for item in raw.get("exclusive_with") or []:
            value = str(item).strip()
            if value and value != self_id and value not in seen:
                seen.append(value)
        return seen

    days = norm_days()
    return {
        "id": str(raw.get("id") or _new_id("cat")),
        "name": str(raw.get("name") or "").strip(),
        "requires_operator": bool(raw.get("requires_operator", False)),
        # Background colour used by the card for appointments of this
        # category. Empty string means "no colour".
        "color": str(raw.get("color") or "").strip(),
        # Minutes of pause required after an appointment of this category
        # before the same masseuse can take the next one.
        "pause_min": max(0, pause),
        # Days of the week (Mon=0 .. Sun=6) in which bookings are accepted.
        # Empty means every day. Kept as the union of the two lists below.
        "days": days,
        # Weekdays bookable in each window. A booking in the morning window is
        # only accepted on a morning day, and likewise for the afternoon.
        "morning_days": norm_window_days("morning_days", days),
        "afternoon_days": norm_window_days("afternoon_days", days),
        # Optional morning and afternoon windows (HH:MM). An appointment must
        # fit entirely inside one of them; empty start+end = no window.
        "morning_start": norm_window("morning_start"),
        "morning_end": norm_window("morning_end"),
        "afternoon_start": norm_window("afternoon_start"),
        "afternoon_end": norm_window("afternoon_end"),
        # Other categories whose confirmed appointments must never overlap
        # this one. The rule is symmetric and enforced in both directions.
        "exclusive_with": norm_exclusive(),
    }


def _norm_treatment(raw: dict[str, Any]) -> dict[str, Any]:
    """Return a treatment with every expected key."""
    try:
        duration = int(raw.get("duration_min") or 0)
    except (TypeError, ValueError):
        duration = 0
    price = raw.get("price")
    try:
        price = float(price) if price not in (None, "") else None
    except (TypeError, ValueError):
        price = None
    return {
        "id": str(raw.get("id") or _new_id("trt")),
        "name": str(raw.get("name") or "").strip(),
        "category_id": str(raw.get("category_id") or "") or None,
        "duration_min": duration,
        "operator_ids": [str(op) for op in (raw.get("operator_ids") or [])],
        "active": bool(raw.get("active", True)),
        # Whether the website may show it. Separate from ``active``: a
        # treatment can be sold at the desk every day and still not belong on
        # the public site. Default true keeps every existing one visible.
        "web_visible": bool(raw.get("web_visible", True)),
        "price": price,
        # How many people can share this treatment at the same time (parallel
        # appointments). 0 = no limit. Only meaningful for appointments
        # without an operator: a masseuse always works 1:1.
        "min_parallel": _norm_parallel(raw.get("min_parallel")),
        "max_parallel": _norm_parallel(raw.get("max_parallel")),
    }


def _norm_operator(raw: dict[str, Any]) -> dict[str, Any]:
    """Return an operator with every expected key.

    ``role`` says what kind of staff member this is, for the desk to read at a
    glance; it does not gate anything. ``treatment_ids`` is the list of massage
    types the operator can perform: it is what the booking form offers her and
    what the monthly report counts, so it is authored on the operator card
    rather than on each treatment.
    """
    # `role` classifies the operator and nothing more: an unknown or absent
    # value falls back to the default instead of being rejected, so an operator
    # saved before roles existed keeps working untouched.
    role = str(raw.get("role") or OPERATOR_ROLE_DEFAULT)
    if role not in {r[0] for r in OPERATOR_ROLES}:
        role = OPERATOR_ROLE_DEFAULT
    try:
        priority = int(raw.get("priority"))
    except (TypeError, ValueError):
        priority = 0
    return {
        "id": str(raw.get("id") or _new_id("op")),
        "name": str(raw.get("name") or "").strip(),
        "role": role,
        "phone": str(raw.get("phone") or "").strip(),
        # Empty means "derive it from the phone number as 39…@c.us".
        "whatsapp_chat_id": str(raw.get("whatsapp_chat_id") or "").strip(),
        "telegram_chat_id": str(raw.get("telegram_chat_id") or "").strip(),
        "treatment_ids": [str(t) for t in (raw.get("treatment_ids") or [])],
        "notify_whatsapp": bool(raw.get("notify_whatsapp", True)),
        "notify_telegram": bool(raw.get("notify_telegram", True)),
        "notify_service": str(raw.get("notify_service") or "").strip(),
        "notify_on_create": bool(raw.get("notify_on_create", True)),
        # Offers are tried in ascending priority order (lower = sooner); a
        # disabled operator receives no offers at all.
        "priority": priority,
        "active": bool(raw.get("active", True)),
    }


# Default, user-ordered entity list for the Spa tab of the card, mirroring the
# "Spa" area exactly as the Dwains "Spa" page renders it (lights, switches,
# locks, climate — the user reorders freely). It only seeds the tiles until the
# user saves an explicit choice from the card.
SPA_DEFAULT_ENTITIES = [
    "light.cascata_spa",
    "light.faretti_1_ingresso_spa",
    "light.faretti_ingresso_spogliatoii_spa",
    "light.fari_zona_piscina_spa",
    "light.illuminaz_all_spa",
    "light.lamp_reception_spa",
    "light.lampadario_percorso_spa",
    "light.spa_led_piscina",
    "light.spa_luce_arearelax_tepid_01",
    "light.spa_luce_bagnoturco_sottopanca",
    "light.spa_luce_sauna_1",
    "switch.energy_monitor_2_gang_switch_module_2_switch_1",
    "switch.energy_monitor_2_gang_switch_module_2_switch_2",
    "switch.led_4",
    "switch.pompa_cascata_relax_switch_1",
    "switch.sonoff_1001f9792e_3",
    "switch.spa_all",
    "lock.door_1_10",
    "lock.door_2_10",
    "climate.ariston_70b8f6a6ac70_1",
]
#: Cameras preselected in the Telecamere tab; the user reorders from the card.
CAMERA_DEFAULT_ENTITIES = [
    "camera.eyemotion_ipc_profile1",
    "camera.percorso_spa_profile1",
    "camera.piscina_spa_profile1",
]
#: Widest a single Spa tile may be, in grid columns (1 = smallest, 4 = full row).
SPA_MAX_SPAN = 4

#: Movable blocks of the "Nuovo appuntamento" form, per default column. The form
#: shows them in this order until the user reorders them from the card; the edit
#: mode drags blocks around, freely crossing from one column to the other.
FORM_BLOCK_COLUMNS: dict[str, list[str]] = {
    "left": ["booking", "notes", "prenotazione", "totali", "incassi"],
    "right": ["client", "guest"],
}

#: The same idea for the notifications tab (Configurazione → Impostazioni): each
#: box is a block the reception can drag around, freely crossing columns.
NOTIFY_BLOCK_COLUMNS: dict[str, list[str]] = {
    "left": ["telegram", "whatsapp", "waha", "preview"],
    "right": ["review", "report", "offers", "deposit", "guest_header", "summary"],
}

#: The Settings tab (Configurazione → Impostazioni): its four boxes move
#: between the two columns and save their order, like the other tabs.
IMPOSTAZIONI_BLOCK_COLUMNS: dict[str, list[str]] = {
    "left": ["aspetto", "versione"],
    "right": ["clienti", "sito"],
}

#: Editable layout of the batch editor boxes (Modifica gruppo), two columns.
BATCH_FORM_BLOCK_COLUMNS: dict[str, list[str]] = {
    "left": ["righe", "note"],
    "right": ["totali", "incassi"],
}

PROMO_BLOCK_COLUMNS: dict[str, list[str]] = {
    "left": ["message", "message_post", "send"],
    "right": ["schedule"],
}


#: The same idea for the "Modifica appuntamento" sheet: each box is a block the
#: reception can drag around, freely crossing from one column to the other.
EDIT_FORM_BLOCK_COLUMNS: dict[str, list[str]] = {
    "left": ["trattamento", "quando", "operatore", "note", "totali", "incassi"],
    "right": ["cliente", "ospite", "accessori"],
}


#: The operator card editor follows the same idea: her identity, her contacts,
#: her priority, her notification channels, the messages and the massages she
#: can do are blocks the reception drags where she reads them best.
OPERATOR_FORM_BLOCK_COLUMNS: dict[str, list[str]] = {
    "left": ["nome", "contatti", "priorita", "notifiche", "messaggi"],
    "right": ["trattamenti"],
}


def _norm_form_order(
    raw: Any, columns: dict[str, list[str]] | None = None
) -> dict[str, list[str]]:
    """Return a two-column layout with every known block placed exactly once.

    Blocks are free to sit in either column, so a block is kept where the user
    dragged it; only a block that is missing from *both* columns (layout never
    saved, or saved with fewer blocks) goes back to its built-in column, so the
    form can never blank out part of itself. Unknown ids are dropped, duplicates
    collapsed.
    """
    blocks = columns or FORM_BLOCK_COLUMNS
    raw = raw if isinstance(raw, dict) else {}
    all_defaults: list[str] = []
    for defaults in blocks.values():
        for key in defaults:
            if key not in all_defaults:
                all_defaults.append(key)
    out: dict[str, list[str]] = {}
    present: set[str] = set()
    for column, defaults in blocks.items():
        given = raw.get(column)
        given = given if isinstance(given, list) else []
        seen: list[str] = []
        for item in given:
            key = str(item).strip()
            if key in all_defaults and key not in seen:
                seen.append(key)
                present.add(key)
        out[column] = seen
    # Any recognized block never seen (in either column) returns to its own column.
    for column, defaults in blocks.items():
        for key in defaults:
            if key not in present:
                out[column].append(key)
                present.add(key)
    return out


def _norm_tab_cols(raw: Any) -> dict[str, int]:
    """Return how many columns each tab shows: 1 or 2.

    The reception can stack a tab's blocks in a single column when the two
    would be too narrow on the tablet. Unknown tabs and anything that is not
    a number of columns are dropped, so a corrupt value can never blank a tab.
    """
    raw = raw if isinstance(raw, dict) else {}
    out: dict[str, int] = {}
    for scope, value in raw.items():
        key = str(scope or "").strip()
        if not key:
            continue
        try:
            cols = int(value)
        except (TypeError, ValueError):
            continue
        if cols in (1, 2):
            out[key] = cols
    return out


def _norm_spa_tile(raw: Any) -> dict[str, Any] | None:
    """Return one Spa tile with every expected key, or None when unusable.

    A tile carries the entity plus its own look: an optional name and icon
    override, three visibility flags and how many grid columns it occupies.
    The legacy shape (a bare entity-id string) is accepted too, so a dataset
    saved before the tiles existed keeps working untouched.
    """
    if isinstance(raw, str):
        raw = {"entity_id": raw}
    if not isinstance(raw, dict):
        return None
    entity_id = str(raw.get("entity_id") or "").strip()
    if not entity_id:
        return None

    def optional_text(key: str) -> str | None:
        value = raw.get(key)
        value = str(value).strip() if value is not None else ""
        return value or None

    try:
        span = int(raw.get("span") or 1)
    except (TypeError, ValueError):
        span = 1
    return {
        "entity_id": entity_id,
        "name": optional_text("name"),
        "icon": optional_text("icon"),
        "show_name": bool(raw.get("show_name", True)),
        "show_icon": bool(raw.get("show_icon", True)),
        "show_state": bool(raw.get("show_state", True)),
        "span": min(max(span, 1), SPA_MAX_SPAN),
    }


def _spa_tiles(
    raw: dict[str, Any], key: str, default_ids: list[str]
) -> list[dict[str, Any]]:
    """Normalize a flat, user-ordered tile list under ``key``.

    The stored list wins once present, even when empty; the default entity set
    is used only while the key has never been saved. Blanks and duplicates are
    dropped, keeping the first occurrence and the user's order. Used for both
    the Spa tab (``spa_entities``) and the Telecamere tab (``camera_entities``),
    which share the same tile shape.
    """
    if key not in raw:
        source: list[Any] = list(default_ids)
    else:
        source = raw.get(key) or []
    tiles: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in source:
        tile = _norm_spa_tile(item)
        if tile and tile["entity_id"] not in seen:
            seen.add(tile["entity_id"])
            tiles.append(tile)
    return tiles


def _norm_settings(raw: dict[str, Any]) -> dict[str, Any]:
    """Return the notification settings with every expected key."""

    def hours(key: str, default: int) -> int:
        try:
            value = int(raw.get(key, default))
        except (TypeError, ValueError):
            value = default
        return max(0, value)

    # Accessories offered with a booking (Accessori tab), and the labels of
    # the ones that have since been deleted. An appointment keeps the ids it
    # was given, so its label has to survive the accessory being removed.
    accessories = _accessories(raw)
    accessory_labels = _accessory_labels(raw, accessories)

    return {
        "telegram_config_entry_id": str(raw.get("telegram_config_entry_id") or "").strip(),
        "report_telegram_chats": str(raw.get("report_telegram_chats") or "").strip(),
        "report_whatsapp_chat": str(raw.get("report_whatsapp_chat") or "").strip(),
        "report_per_operator": bool(raw.get("report_per_operator", True)),
        "report_enabled": bool(raw.get("report_enabled", True)),
        "report_time": str(raw.get("report_time") or DEFAULT_REPORT_TIME).strip(),
        # How long an operator has to answer an offer before the next one is
        # asked, and how long before that a reminder goes out (0 = no reminder).
        "offer_timeout_hours": hours(
            "offer_timeout_hours", DEFAULT_OFFER_TIMEOUT_HOURS
        ),
        "offer_reminder_hours": hours(
            "offer_reminder_hours", DEFAULT_OFFER_REMINDER_HOURS
        ),
        # How the card paints itself: "auto" follows the Home Assistant theme,
        # "light"/"dark" force it. Anything unknown falls back to "auto" so a
        # bad value can never leave the card unreadable.
        "appearance": (
            str(raw.get("appearance") or DEFAULT_APPEARANCE).strip().lower()
            if str(raw.get("appearance") or DEFAULT_APPEARANCE).strip().lower()
            in APPEARANCE_MODES
            else DEFAULT_APPEARANCE
        ),
        # Version of the served booking card: bump it to force every browser to
        # refetch the JS file (see async_reload_card).
        "card_js_version": str(
            raw.get("card_js_version") or CARD_JS_VERSION
        ).strip(),
        # Titolo in testata della card, scritto dalla reception in Impostazioni.
        # Vuoto = usa il valore della configurazione della card (o "Gestione SPA").
        "card_title": str(raw.get("card_title") or DEFAULT_CARD_TITLE).strip(),
        # Access level per user (Accessi tab). Unknown values are dropped so a
        # bad edit can never grant more than intended.
        KEY_PERMISSIONS: {
            key: value
            for key, value in dict(raw.get(KEY_PERMISSIONS) or {}).items()
            if value in PERMISSION_LEVELS
        },
        # Camera entities shown in the Telecamere tab (empty list = none).
        # Each camera carries its own name, icon, visibility and column span.
        "camera_entities": _spa_tiles(
            raw, "camera_entities", CAMERA_DEFAULT_ENTITIES
        ),
        # Flat, user-ordered list of tiles shown in the Spa tab of the card
        # (lights, switches, locks, climate all mixed; each tile carries its own
        # name, icon, visibility and column span). Default to the Spa-area set
        # until the user saves an explicit choice.
        "spa_entities": _spa_tiles(raw, "spa_entities", SPA_DEFAULT_ENTITIES),
        # Accessories of the Accessori tab, in user order (empty = none). Each
        # one carries its own label, icon, price and description; the price is
        # informational and never enters a total.
        "accessories": accessories,
        # id -> last known name of an accessory, the deleted ones included:
        # the fallback the card reads for the accessories an old appointment
        # still carries.
        "accessory_labels": accessory_labels,
        # Layout of the "Nuovo appuntamento" form: which blocks and in which
        # order each column shows them. The card only ever reorders them.
        "form_order": _norm_form_order(raw.get("form_order")),
        # Layout of the notifications tab, same idea with its own blocks.
        "notifiche_order": _norm_form_order(
            raw.get("notifiche_order"), NOTIFY_BLOCK_COLUMNS
        ),
        # Layout of the Settings tab: the four boxes, movable between columns.
        "impostazioni_order": _norm_form_order(
            raw.get("impostazioni_order"), IMPOSTAZIONI_BLOCK_COLUMNS
        ),
        # Layout of the "Modifica appuntamento" sheet.
        # Layout of the batch editor columns.
        "batch_form_order": _norm_form_order(
            raw.get("batch_form_order"), BATCH_FORM_BLOCK_COLUMNS
        ),
        "edit_form_order": _norm_form_order(
            raw.get("edit_form_order"), EDIT_FORM_BLOCK_COLUMNS
        ),
        # Layout of one operator's card.
        "operator_form_order": _norm_form_order(
            raw.get("operator_form_order"), OPERATOR_FORM_BLOCK_COLUMNS
        ),
        # How many columns each tab lays its blocks out in: 1 (stacked) or 2.
        # Only the tabs the reception actually changed are kept.
        "tab_cols": _norm_tab_cols(raw.get("tab_cols")),
        # The review request as the reception wants it sent, and the number the
        # test goes to. An empty message falls back to the built-in text, so a
        # cleared field never leaves the guest without an invitation.
        "review_request_message": str(
            raw.get("review_request_message") or DEFAULT_REVIEW_MESSAGE
        ),
        "review_request_test_phone": str(
            raw.get("review_request_test_phone") or ""
        ).strip(),
        # Whether the review request goes out on its own (the daily automation)
        # and how many hours after the treatment ends it is sent. Manual sending
        # from an appointment ignores both.
        "review_request_auto": bool(
            raw.get("review_request_auto", DEFAULT_REVIEW_REQUEST_AUTO)
        ),
        "review_request_after_hours": _norm_count(
            raw.get("review_request_after_hours"),
            1,
            168,
            DEFAULT_REVIEW_REQUEST_AFTER_HOURS,
        ),
        # Bank details the deposit request reads out to the guest: both are
        # editable from the card's notifications tab. Empty values fall back to
        # the hotel's defaults, so a cleared field never breaks the message.
        "deposit_intestatario": str(
            raw.get("deposit_intestatario") or DEFAULT_DEPOSIT_INTESTATARIO
        ).strip(),
        "deposit_iban": str(raw.get("deposit_iban") or DEFAULT_DEPOSIT_IBAN).strip(),
        # The deposit request the reception wants sent, and the test number.
        # An empty message falls back to the built-in text.
        "deposit_message": str(
            raw.get("deposit_message") or DEFAULT_DEPOSIT_MESSAGE
        ),
        "deposit_test_phone": str(raw.get("deposit_test_phone") or "").strip(),
        # The headline shown after the title of the guest-facing appointment
        # summary. Editable from the notifications tab.
        "guest_header": str(
            raw.get("guest_header") or DEFAULT_GUEST_HEADER
        ),
        # The guest-facing appointment summary: its own text, editable from the
        # notifications tab, and the number a test send goes to. An empty
        # message falls back to the built-in one, so a cleared field never
        # leaves the guest without a summary.
        "summary_message": str(
            raw.get("summary_message") or DEFAULT_SUMMARY_MESSAGE
        ),
        "summary_test_phone": str(raw.get("summary_test_phone") or "").strip(),
        # The message a guest receives when the desk takes her appointment
        # request: it says the request was received and is waiting for the
        # reception to confirm it. Editable from the notifications tab; an empty
        # setting falls back to the built-in text, so a cleared field never
        # leaves the guest without an answer.
        "request_message": str(
            raw.get("request_message") or DEFAULT_REQUEST_MESSAGE
        ),
        # Voucher expiration reminder: message sent to the recipient before
        # the voucher expires. The number of days before expiry to send it.
        "voucher_expiry_reminder_message": str(
            raw.get("voucher_expiry_reminder_message") or DEFAULT_VOUCHER_EXPIRY_REMINDER_MESSAGE
        ),
        "voucher_expiry_reminder_days": int(raw.get("voucher_expiry_reminder_days") or DEFAULT_VOUCHER_EXPIRY_REMINDER_DAYS),
        # Appointment reminder for the guest: customizable message, and whether
        # it is sent automatically (with how many hours advance) or manually.
        "appointment_reminder_message": str(
            raw.get("appointment_reminder_message") or DEFAULT_APPOINTMENT_REMINDER_MESSAGE
        ),
        "appointment_reminder_auto": bool(
            raw.get("appointment_reminder_auto", DEFAULT_APPOINTMENT_REMINDER_AUTO)
        ),
        "appointment_reminder_hours": int(
            raw.get("appointment_reminder_hours") or DEFAULT_APPOINTMENT_REMINDER_HOURS
        ),
        # Order of the treatments in the configuration tab, as the reception
        # dragged them. Ids that no longer exist are dropped; a treatment
        # created later simply joins at the end.
        "treatments_order": _norm_id_list(raw.get("treatments_order")),
        # Order of the category blocks in the same tab: they live in two real
        # columns, so each group has its column and its place inside it.
        "categories_order": _norm_column_order(raw.get("categories_order")),
        # Promo broadcast: the message template and the scheduling knobs, all
        # editable from the Promo tab. Empty ``promo_time`` disables the daily
        # automatic send.
        "promo_message": str(raw.get("promo_message") or DEFAULT_PROMO_MESSAGE),
        "promo_time": str(raw.get("promo_time") or DEFAULT_PROMO_TIME).strip(),
        "promo_interval_sec": _norm_interval(raw.get("promo_interval_sec")),
        # At most promo_max_sends messages in any promo_window_min minutes (0 = no limit).
        "promo_max_sends": _norm_count(raw.get("promo_max_sends"), 0, 1000, 0),
        "promo_window_min": _norm_count(raw.get("promo_window_min"), 1, 1440, 10),
        # One-off send date (cleared after it runs) and the promo code and expiry.
        "promo_date": _norm_date(raw.get("promo_date")),
        "promo_code": str(raw.get("promo_code") or "").strip(),
        "promo_expiry": _norm_date(raw.get("promo_expiry")),
        # Loyalty voucher: the thank-you message sent after the client used the
        # services, and the voucher rules. The message is a template with
        # {nome}, {cognome}, {codice}, {sconto}, {spesa_minima}, {scadenza}.
        "promo_voucher_message": str(
            raw.get("promo_voucher_message") or DEFAULT_PROMO_VOUCHER_MESSAGE
        ),
        "promo_voucher_days": _norm_count(
            raw.get("promo_voucher_days"), 1, 3650, DEFAULT_PROMO_VOUCHER_DAYS
        ),
        "promo_voucher_discount": _norm_count(
            raw.get("promo_voucher_discount"), 1, 100, DEFAULT_PROMO_VOUCHER_DISCOUNT
        ),
        "promo_voucher_min_spend": _norm_count(
            raw.get("promo_voucher_min_spend"), 0, 100000,
            DEFAULT_PROMO_VOUCHER_MIN_SPEND,
        ),
        "promo_voucher_max_spend": _norm_count(
            raw.get("promo_voucher_max_spend"), 0, 100000,
            DEFAULT_PROMO_VOUCHER_MAX_SPEND,
        ),
        "promo_voucher_after_hours": _norm_count(
            raw.get("promo_voucher_after_hours"), 0, 8760,
            DEFAULT_PROMO_VOUCHER_AFTER_HOURS,
        ),
        "promo_voucher_auto": bool(
            raw.get("promo_voucher_auto", DEFAULT_PROMO_VOUCHER_AUTO)
        ),
        # Order of the blocks in the Promo tab, editable by dragging.
        "promo_order": _norm_form_order(
            raw.get("promo_order"), PROMO_BLOCK_COLUMNS
        ),
        # WhatsApp gateway (the WAHA add-on). When the URL is set, the
        # integration talks to it directly instead of going through
        # ``rest_command.spa_booking_whatsapp_send``: the key and the session
        # name are stored here, never in a package, so one place configures
        # every WhatsApp send of this installation.
        "waha_url": str(raw.get("waha_url") or "").strip(),
        "waha_api_key": str(raw.get("waha_api_key") or "").strip(),
        "waha_session": str(
            raw.get("waha_session") or DEFAULT_WAHA_SESSION
        ).strip(),
        # The webhook the WAHA add-on posts the operators' answers to, and the
        # secret it signs them with. Both are generated once, when the gateway
        # is switched on, and are never shown in the card: rotating them by hand
        # would silently stop inbound answers until the next activation.
        "waha_webhook_id": str(raw.get("waha_webhook_id") or "").strip(),
        "waha_webhook_secret": str(raw.get("waha_webhook_secret") or "").strip(),
        # How the WAHA add-on reaches Home Assistant, when it is not the add-on
        # installed on this host (empty = the Supervisor network default).
        "waha_ha_url": str(raw.get("waha_ha_url") or "").strip(),
        # Public booking API for the hotel website. The site is another origin
        # and cannot use the Lovelace websocket, so it talks to the three HTTP
        # views in ``public.py``; every call must carry this token. Nothing
        # here is secret to the desk — the token is shown in the card so it can
        # be copied into the website — but it is what keeps a stranger from
        # filing requests. ``web_enabled`` is the master switch: while it is
        # off, the views answer 404 and the website shows nothing.
        "web_enabled": bool(raw.get("web_enabled", DEFAULT_WEB_ENABLED)),
        "web_token": str(raw.get("web_token") or DEFAULT_WEB_TOKEN).strip(),
        # The day as the website offers it: from/to and the step between one
        # proposed start and the next. Both clocks fall back to the default
        # when emptied, so a cleared field never shuts the site out.
        "web_open_time": _norm_clock(raw.get("web_open_time"))
        or DEFAULT_WEB_OPEN_TIME,
        "web_close_time": _norm_clock(raw.get("web_close_time"))
        or DEFAULT_WEB_CLOSE_TIME,
        # The break that splits the day the site offers: the morning ends
        # here and the afternoon starts at ``web_break_end``. Both empty (the
        # default) keep the day whole, exactly as before.
        "web_break_start": _norm_clock(
            raw.get("web_break_start") or DEFAULT_WEB_BREAK_START
        ),
        "web_break_end": _norm_clock(
            raw.get("web_break_end") or DEFAULT_WEB_BREAK_END
        ),
        "web_step_min": _norm_count(
            raw.get("web_step_min"), 5, 240, DEFAULT_WEB_STEP_MIN
        ),
        # How far ahead the site may offer, so a mistyped year cannot ask the
        # agenda for a century of days.
        "web_max_days_ahead": _norm_count(
            raw.get("web_max_days_ahead"), 1, 365, DEFAULT_WEB_MAX_DAYS_AHEAD
        ),
        # Dove arriva l'avviso di una nuova richiesta dal sito: un numero
        # WhatsApp della reception. Vuoto = nessun avviso.
        "web_notify_whatsapp": str(
            raw.get("web_notify_whatsapp") or DEFAULT_WEB_NOTIFY_WHATSAPP
        ).strip(),
    }


def _norm_interval(raw: Any) -> int:
    """Return a non-negative delay in seconds between one send and the next."""
    try:
        return max(0, int(raw or 0))
    except (TypeError, ValueError):
        return DEFAULT_PROMO_INTERVAL_SEC


def _norm_count(raw: Any, low: int, high: int, default: int) -> int:
    """Return an integer within [low, high], or the default when it is not one."""
    try:
        return min(high, max(low, int(raw)))
    except (TypeError, ValueError):
        return default


def _norm_date(raw: Any) -> str:
    """Return a YYYY-MM-DD date string, or an empty string when it is not one."""
    try:
        return datetime.strptime(str(raw or "").strip(), "%Y-%m-%d").strftime("%Y-%m-%d")
    except ValueError:
        return ""


#: An "HH:MM" clock, accepting a dot as the separator too ("10.30" = "10:30").
_CLOCK_RE = re.compile(r"^(\d{1,2})[:.](\d{2})$")


def _norm_clock(raw: Any) -> str:
    """Return an "HH:MM" clock, or an empty string when it is not one.

    The desk types the time of a request by hand, so both the colon and the dot
    are accepted and a single-digit hour is padded; anything out of range is
    refused rather than silently wrapped to another time of day.
    """
    match = _CLOCK_RE.match(str(raw or "").strip())
    if not match:
        return ""
    hour, minute = int(match.group(1)), int(match.group(2))
    if hour > 23 or minute > 59:
        return ""
    return f"{hour:02d}:{minute:02d}"


def _date_it(raw: str) -> str:
    """Return a stored YYYY-MM-DD date as dd/mm/yyyy, or an empty string."""
    if not raw:
        return ""
    return datetime.strptime(raw, "%Y-%m-%d").strftime("%d/%m/%Y")


def _norm_id_list(raw: Any) -> list[str]:
    """Return a plain list of unique, non-empty ids, in the given order."""
    raw = raw if isinstance(raw, list) else []
    out: list[str] = []
    for item in raw:
        key = str(item).strip()
        if key and key not in out:
            out.append(key)
    return out


def _norm_column_order(raw: Any) -> dict[str, list[str]]:
    """Return the two-column layout of the category groups.

    The layout used to be a single flat list filled the CSS grid row by row,
    which left the right cell of an odd last row unreachable: no order could
    ever put a group there. Two real columns make every spot droppable.

    A flat list is still accepted and is spread over the columns exactly the
    way the grid used to render it (first group left, second right, and so
    on), so the layout saved before this change keeps its appearance.
    """
    out: dict[str, list[str]] = {"left": [], "right": []}
    seen: set[str] = set()

    def place(column: str, ids: Any) -> None:
        for item in ids if isinstance(ids, list) else []:
            key = str(item).strip()
            if key and key not in seen:
                seen.add(key)
                out[column].append(key)

    if isinstance(raw, dict):
        place("left", raw.get("left"))
        place("right", raw.get("right"))
        return out
    flat = _norm_id_list(raw)
    for index, key in enumerate(flat):
        place("left" if index % 2 == 0 else "right", [key])
    return out


def _norm_client(raw: dict[str, Any]) -> dict[str, Any]:
    """Return a client with every expected key."""
    return {
        "id": str(raw.get("id") or _new_id("cli")),
        "first_name": str(raw.get("first_name") or "").strip(),
        "last_name": str(raw.get("last_name") or "").strip(),
        "phone": str(raw.get("phone") or "").strip(),
        "email": str(raw.get("email") or "").strip(),
        "notes": str(raw.get("notes") or ""),
        "created_at": str(raw.get("created_at") or dt_util.utcnow().isoformat()),
        # Whether the client wants to receive the promotional messages. Default
        # true: a card without the flag (every card that predates it) keeps
        # receiving promos until the desk deliberately unsubscribes it.
        "promo_opt_in": bool(raw.get("promo_opt_in", True)),
    }


def _norm_payment(raw: dict[str, Any] | None) -> dict[str, Any]:
    """Return how an appointment is paid, with every key present.

    The flags combine freely on purpose: a deposit and the balance that is
    still owed are two true things at once, not two alternatives, so they are
    booleans rather than one "payment type" string. Nothing ticked simply means
    the desk was never told, which is different from "paid in full".

    Each flag that means money carries its own amount, because "already handed
    over 30" and "still owed 10" describe the same booking without one
    replacing the other.
    """
    raw = raw or {}

    def money(key: str) -> float:
        try:
            return round(float(raw.get(key) or 0), 2)
        except (TypeError, ValueError):
            return 0.0

    return {
        "paid": bool(raw.get("paid", False)),
        "paid_amount": money("paid_amount"),
        "deposit": bool(raw.get("deposit", False)),
        "deposit_amount": money("deposit_amount"),
        "voucher": bool(raw.get("voucher", False)),
        "voucher_code": str(raw.get("voucher_code") or "").strip()[:64],
        "balance_due": bool(raw.get("balance_due", False)),
        "balance_due_amount": money("balance_due_amount"),
        # The ways of paying, in the order they were ticked. Several at once
        # because a deposit on card and the balance in cash is a real thing to
        # write down; an unknown one is dropped rather than invented.
        "methods": [
            str(method)
            for method in (raw.get("methods") or [])
            if str(method) in {name for name, _, _ in PAYMENT_METHODS}
        ],
    }


def _norm_price_opt(value: Any) -> float | None:
    """Return an optional money amount, or None when absent or invalid.

    None means "fall back to the catalogue price": it is different from an
    explicit zero, so a discounted-to-zero treatment stays zero instead of
    silently becoming the list price.
    """
    if value is None or (isinstance(value, str) and not value.strip()):
        return None
    try:
        amount = round(float(value), 2)
    except (TypeError, ValueError):
        return None
    return amount if amount >= 0 else None


def _norm_payment_list(raw: Any) -> list[dict[str, Any]]:
    """Return the registered takings of an appointment, newest last.

    Each entry keeps its own id, method, date and amount, so several partial
    payments on different days stay distinct. An entry with an unknown method
    or no positive amount is dropped rather than invented.
    """
    out: list[dict[str, Any]] = []
    for item in raw or []:
        if not isinstance(item, dict):
            continue
        method = str(item.get("method") or "").strip()
        if method not in {name for name, _, _ in PAYMENT_METHODS}:
            continue
        try:
            amount = round(float(item.get("amount") or 0), 2)
        except (TypeError, ValueError):
            continue
        if amount <= 0:
            continue
        out.append(
            {
                "id": str(item.get("id") or _new_id("pay")),
                "method": method,
                "date": _norm_date(item.get("date")),
                "amount": amount,
            }
        )
    return out


def _norm_guest_type(value: Any) -> str:
    """Return a known guest type, anything unknown falling back to Esterno.

    A booking without a flag is from outside: that is what every appointment
    was before the field existed, so old records keep their meaning.
    """
    guest_type = str(value or GUEST_TYPE_DEFAULT)
    if guest_type not in {g[0] for g in GUEST_TYPES}:
        return GUEST_TYPE_DEFAULT
    return guest_type


def _norm_accessory(raw: Any) -> dict[str, Any] | None:
    """Return one accessory with every expected key, or None when unusable.

    A bare id string is accepted too, so a client that predates the price and
    the description still saves without error; for a factory accessory a
    missing label or icon falls back to the factory one rather than the id.
    """
    if not isinstance(raw, dict):
        item_id = str(raw or "").strip()
        raw = {"id": item_id} if item_id else {}
    item_id = str(raw.get("id") or "").strip()
    if not item_id:
        return None
    factory = next((item for item in ACCESSORY_DEFAULTS if item["id"] == item_id), None)
    price = raw.get("price")
    if isinstance(price, str):
        # The desk types "12,50" as often as "12.50": both mean the same.
        price = price.replace(",", ".").strip()
    try:
        price = float(price) if price not in (None, "") else None
    except (TypeError, ValueError):
        price = None
    return {
        "id": item_id,
        "label": str(raw.get("label") or (factory["label"] if factory else item_id)).strip(),
        "icon": str(
            raw.get("icon") or (factory["icon"] if factory else "mdi:gift-outline")
        ).strip(),
        "price": price,
        "description": str(raw.get("description") or "").strip(),
    }


def _accessories(raw: dict[str, Any]) -> list[dict[str, Any]]:
    """Normalize the user-ordered accessory list.

    The stored list wins once present, even when empty; the factory list is
    used only while the key has never been saved, so the four accessories that
    were hard-coded before this tab existed are still offered. Blanks and
    duplicates are dropped, keeping the first occurrence and the user's order.
    """
    if "accessories" in raw:
        source: list[Any] = raw.get("accessories") or []
    else:
        source = [
            {
                "id": item["id"],
                "label": item["label"],
                "icon": item["icon"],
                "price": item.get("price"),
                "description": item.get("description"),
            }
            for item in ACCESSORY_DEFAULTS
        ]
    items: list[dict[str, Any]] = []
    seen: set[str] = set()
    for entry in source:
        item = _norm_accessory(entry)
        if item and item["id"] not in seen:
            seen.add(item["id"])
            items.append(item)
    return items


def _accessory_labels(
    raw: dict[str, Any], accessories: list[dict[str, Any]]
) -> dict[str, str]:
    """Return ``id -> last known name``, the deleted accessories included.

    An appointment keeps the accessory ids it was given. When one of those
    accessories is later deleted the label must not vanish with it, so the map
    is accumulated across saves and is what the card falls back to.
    """
    labels: dict[str, str] = {}
    stored = raw.get("accessory_labels")
    if isinstance(stored, dict):
        labels.update({str(key): str(value) for key, value in stored.items()})
    for item in ACCESSORY_DEFAULTS:
        labels.setdefault(item["id"], item["label"])
    for item in accessories:
        labels[item["id"]] = item["label"]
    return labels


def _norm_extras(value: Any, known: set[str] | None = None) -> list[str]:
    """Return the accessory ids among ``value``, unknown ones dropped.

    Empty and unset both come out as an empty list, which is what every
    appointment that predates the field means: no accessory was chosen. With
    ``known`` left out every non-empty id is kept: the stored appointments must
    hold on to the accessories the reception configured, which this module
    cannot know at import time.
    """
    if not value:
        return []
    if isinstance(value, str):
        value = [value]
    chosen: list[str] = []
    for item in value:
        if item is None:
            continue
        item_id = str(item).strip()
        if not item_id:
            continue
        if known is not None and item_id not in known:
            continue
        chosen.append(item_id)
    return chosen


def _norm_person(value: Any) -> int:
    """Which person of her party an appointment is, 0 being the leader.

    The form asks for one name — the person booking is the leader of the party
    — and every guest of hers is booked on that same card, so the card alone
    cannot say who is coming. This is the number that can: 0 is the person the
    card is named after, 1.. are her guests. An appointment written before this
    field existed is the card's own person, so it reads as 0.
    """
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


def _norm_appointment(raw: dict[str, Any]) -> dict[str, Any]:
    """Return an appointment with every expected key.

    The ``offer_*`` fields only matter while the booking is waiting for an
    operator to answer. ``operator_id`` already holds the operator currently
    being asked, so her slot is reserved from the moment the offer is made and
    every existing overlap rule keeps working unchanged; when she declines the
    slot simply moves to the next candidate.
    """
    batch_raw = raw.get("batch_id") or raw.get("booking_id")
    batch_id = str(batch_raw).strip() if batch_raw not in (None, "") else None

    offer_state = raw.get("offer_state")
    if offer_state not in (OFFER_NONE, OFFER_PENDING, OFFER_UNASSIGNED):
        offer_state = OFFER_NONE
    try:
        offer_index = max(0, int(raw.get("offer_index") or 0))
    except (TypeError, ValueError):
        offer_index = 0
    return {
        "id": str(raw.get("id") or _new_id("appt")),
        "client_id": str(raw.get("client_id") or "") or None,
        "treatment_id": str(raw.get("treatment_id") or "") or None,
        "operator_id": str(raw.get("operator_id") or "") or None,
        "start": str(raw.get("start") or ""),
        "end": str(raw.get("end") or ""),
        "status": _norm_status(raw),
        "guest_type": _norm_guest_type(raw.get("guest_type")),
        "extras": _norm_extras(raw.get("extras")),
        # Per-row price overrides, both editable from the card: the list
        # price and the discounted one. None means "use the catalogue
        # price of the treatment", so bookings saved before prices existed
        # keep their meaning untouched.
        "list_price": _norm_price_opt(raw.get("list_price")),
        "price": _norm_price_opt(raw.get("price")),
        # Which person of the party she is: 0 is the one written on the card,
        # 1.. are her guests. Two appointments of one card may share an hour
        # only when they are different persons, so this is what tells a party
        # from the same person booked twice.
        "person": _norm_person(raw.get("person")),
        # A 5-char booking reference the desk can read out loud or text the
        # guest: short enough to be unique, long enough not to be guessed.
        "code": str(raw.get("code") or "").upper(),
        "notes": str(raw.get("notes") or ""),
        "cancel_reason": str(raw.get("cancel_reason") or ""),
        "created_at": str(raw.get("created_at") or dt_util.utcnow().isoformat()),
        "cancelled_at": str(raw.get("cancelled_at") or ""),
        # Who confirmed the booking and when. A pending booking has neither:
        # nobody has confirmed it yet.
        "confirmed_by": str(raw.get("confirmed_by") or ""),
        "confirmed_at": str(raw.get("confirmed_at") or ""),
        "offer_state": offer_state,
        "offer_candidates": [str(op) for op in (raw.get("offer_candidates") or [])],
        "offer_index": offer_index,
        "offer_expires_at": str(raw.get("offer_expires_at") or ""),
        "offer_reminded": bool(raw.get("offer_reminded", False)),
        # Check-in / check-out recorded by the reception from the agenda.
        "checked_in": bool(raw.get("checked_in", False)),
        "checked_in_at": str(raw.get("checked_in_at") or ""),
        "checked_out": bool(raw.get("checked_out", False)),
        "checked_out_at": str(raw.get("checked_out_at") or ""),
        # The guest reminder is sent once, about a day before the appointment.
        "reminder_sent": bool(raw.get("reminder_sent", False)),
        # The review request is sent once, a few hours after the appointment is
        # over. One flag per appointment: a guest with two treatments the same
        # day is asked once, not twice.
        "review_request_sent": bool(raw.get("review_request_sent", False)),
        # The deposit request is sent once, asking the guest to pay her deposit
        # by bank transfer while the booking is still waiting for confirmation.
        "deposit_request_sent": bool(raw.get("deposit_request_sent", False)),
        # What the guest handed over at the desk, written at booking time.
        **_norm_payment(raw),
        # The registered takings, one entry per payment: their sum is what
        # has actually been collected, whatever the flags above say.
        "payments": _norm_payment_list(raw.get("payments")),
        "batch_id": batch_id,
    }


def _norm_status(raw: dict[str, Any]) -> str:
    """Return a known appointment status."""
    value = raw.get("status")
    return value if value in BOOKING_STATUSES + (STATUS_CANCELLED,) else STATUS_CONFIRMED


def _norm_request(raw: dict[str, Any]) -> dict[str, Any]:
    """Return an appointment request with every expected key.

    A request is not an appointment: it holds no slot, never enters the agenda
    and never blocks anybody. It is the guest asking for one — by phone or on
    WhatsApp — kept together with the treatments she asked for, until the desk
    confirms it and the real appointments are created.
    """
    entries: list[dict[str, Any]] = []
    for item in raw.get("entries") or []:
        if not isinstance(item, dict):
            continue
        treatment_id = str(item.get("treatment_id") or "").strip()
        if not treatment_id:
            continue
        entries.append(
            {
                "treatment_id": treatment_id,
                "time": str(item.get("time") or "")[:5],
                "extras": _norm_extras(item.get("extras")),
            }
        )
    status = raw.get("status")
    if status not in (REQUEST_PENDING, REQUEST_CONFIRMED):
        status = REQUEST_PENDING
    try:
        people = max(1, int(raw.get("people") or 1))
    except (TypeError, ValueError):
        people = 1
    return {
        "id": str(raw.get("id") or _new_id("req")),
        "code": str(raw.get("code") or "").upper(),
        "client_id": str(raw.get("client_id") or ""),
        "date": _norm_date(raw.get("date")),
        "people": people,
        "entries": entries,
        "notes": str(raw.get("notes") or ""),
        # A gift voucher the guest mentioned, or an outside one the desk will
        # check. Old requests carry no key and simply have none.
        "voucher_code": str(raw.get("voucher_code") or "").strip().upper()[:32],
        "guest_type": _norm_guest_type(raw.get("guest_type")),
        "status": status,
        # Where the request came from, and whether the desk has opened it yet.
        # A web request lights the bell in the card header; opening the list
        # (or the request itself) sets ``seen`` and clears the bell. Old
        # requests carry neither key and default to a desk request already
        # seen, so nothing old ever rings.
        "source": (
            REQUEST_SOURCE_WEB
            if raw.get("source") == REQUEST_SOURCE_WEB
            else REQUEST_SOURCE_DESK
        ),
        "seen": bool(raw.get("seen", True)),
        "created_at": str(raw.get("created_at") or dt_util.utcnow().isoformat()),
        # The acknowledgement to the guest goes out once, right after the
        # request is saved; the flag lets the desk see it and resend.
        "message_sent": bool(raw.get("message_sent", False)),
        "message_sent_at": str(raw.get("message_sent_at") or ""),
        "confirmed_at": str(raw.get("confirmed_at") or ""),
        "appointment_ids": [str(a) for a in (raw.get("appointment_ids") or [])],
    }


def _money_text(amount: Any) -> str:
    """Return an amount the Italian way: 50,00 €."""
    try:
        value = round(float(amount or 0), 2)
    except (TypeError, ValueError):
        value = 0.0
    return f"{value:.2f}".replace(".", ",") + " €"


def _payment_confirms(payment: dict[str, Any] | None) -> bool:
    """Whether the payment on its own confirms a booking.

    Any money handed over settles the question of whether the client is coming:
    a voucher, a deposit or the whole amount. It is the desk's own rule, so it
    lives here rather than being re-implemented by the card.
    """
    if not payment:
        return False
    return bool(
        payment.get("paid") or payment.get("deposit") or payment.get("voucher")
    )


def occupies_slot(appointment: dict[str, Any]) -> bool:
    """Whether this booking holds its slot against anybody else.

    A pending booking holds it just like a confirmed one: the room and the
    operator are spoken for, and letting a second client into the same hour
    would be the double booking this status exists to avoid.
    """
    return appointment.get("status") in BOOKING_STATUSES


def _same_window(
    appointment: dict[str, Any], start_dt: datetime, end_dt: datetime
) -> bool:
    """Whether a booked appointment overlaps the window of an edit.

    A shared treatment exists as one appointment per person: moving the client
    of one member of the party must therefore count the rest of the group that
    already holds the slot, not pretend the member is alone.
    """
    other_start = dt_util.parse_datetime(appointment["start"])
    other_end = dt_util.parse_datetime(appointment["end"])
    return bool(
        other_start
        and other_end
        and other_start < end_dt
        and other_end > start_dt
    )


#: A refusal note may carry a date (gg-mm-aaaa) and one or two times (HH:MM).
_REFUSE_DATE = re.compile(r"(\d{2})-(\d{2})-(\d{4})")
_REFUSE_TIME = re.compile(r"(\d{1,2})[:.](\d{2})")


def _norm_slot_block(raw: dict[str, Any]) -> dict[str, Any]:
    """Return a refused time window with every expected key.

    The window is stored on the calendar date in local time, because that is
    what the reception reads and what an operator's "that slot" means; the
    appointment it came from is kept so "available again" can clear exactly
    the block it created.
    """
    return {
        "id": str(raw.get("id") or _new_id("blk")),
        "operator_id": str(raw.get("operator_id") or ""),
        "date": str(raw.get("date") or "")[:10],
        "start": str(raw.get("start") or "")[:5],
        "end": str(raw.get("end") or "")[:5],
        "appointment_id": str(raw.get("appointment_id") or ""),
        "created_at": str(raw.get("created_at") or dt_util.utcnow().isoformat()),
    }


def _norm_closure(raw: dict[str, Any]) -> dict[str, Any]:
    """Return a business closure with every expected key.

    Dates are stored as plain calendar days in local time, because a closure is
    written by a receptionist who thinks in days, not in UTC instants. An empty
    ``start``/``end`` pair means the closure covers the whole day.
    """
    scope = str(raw.get("scope") or "facility").strip().lower()
    if scope not in CLOSURE_SCOPES:
        scope = "facility"

    def clock(key: str) -> str:
        value = str(raw.get(key) or "").strip()
        return value[:5] if len(value) >= 5 else ""

    return {
        "id": str(raw.get("id") or _new_id("cls")),
        "label": str(raw.get("label") or "").strip(),
        "scope": scope,
        "operator_id": str(raw.get("operator_id") or "").strip(),
        "category_id": str(raw.get("category_id") or "").strip(),
        "date_from": str(raw.get("date_from") or "")[:10],
        "date_to": str(raw.get("date_to") or "")[:10],
        "start": clock("start"),
        "end": clock("end"),
        "created_at": str(raw.get("created_at") or dt_util.utcnow().isoformat()),
    }


def _normalise(raw: dict[str, Any]) -> dict[str, Any]:
    """Return a dataset with every expected key and record shape."""
    return {
        KEY_CATEGORIES: [_norm_category(c) for c in raw.get(KEY_CATEGORIES) or []],
        KEY_TREATMENTS: [_norm_treatment(t) for t in raw.get(KEY_TREATMENTS) or []],
        KEY_OPERATORS: [_norm_operator(o) for o in raw.get(KEY_OPERATORS) or []],
        KEY_CLIENTS: [_norm_client(c) for c in raw.get(KEY_CLIENTS) or []],
        KEY_APPOINTMENTS: [_norm_appointment(a) for a in raw.get(KEY_APPOINTMENTS) or []],
        KEY_SLOT_BLOCKS: [
            _norm_slot_block(b) for b in raw.get(KEY_SLOT_BLOCKS) or []
        ],
        KEY_CLOSURES: [_norm_closure(c) for c in raw.get(KEY_CLOSURES) or []],
        KEY_VOUCHERS: [_norm_voucher(v) for v in raw.get(KEY_VOUCHERS) or []],
        KEY_PROMO_VOUCHERS: [
            _norm_promo_voucher(v) for v in raw.get(KEY_PROMO_VOUCHERS) or []
        ],
        KEY_REQUESTS: [_norm_request(r) for r in raw.get(KEY_REQUESTS) or []],
        KEY_SETTINGS: _norm_settings(raw.get(KEY_SETTINGS) or {}),
    }


def default_data(operator_names: list[str] | None = None) -> dict[str, Any]:
    """Return a usable starting dataset.

    The user is expected to edit treatments and add operators from the
    dashboard, so the seed only has to make the integration usable.
    """
    categories = [
        _norm_category(
            {"id": "cat_massaggi", "name": "Massaggi", "requires_operator": True}
        ),
        _norm_category(
            {
                "id": "cat_ingresso_spa",
                "name": "Ingresso Spa",
                "requires_operator": False,
            }
        ),
    ]
    treatments = [
        _norm_treatment(
            {
                "id": f"trt_ingresso_{minutes}",
                "name": f"Ingresso Spa {minutes} min",
                "category_id": "cat_ingresso_spa",
                "duration_min": minutes,
            }
        )
        for minutes in (90, 120)
    ] + [
        _norm_treatment(
            {
                "id": f"trt_massaggio_relax_{minutes}",
                "name": f"Massaggio Relax {minutes} min",
                "category_id": "cat_massaggi",
                "duration_min": minutes,
            }
        )
        for minutes in (90, 120)
    ]
    operators = [
        _norm_operator({"id": _new_id("op"), "name": name})
        for name in (operator_names or [])
        if str(name).strip()
    ]
    # A masseuse set up from the config flow starts able to perform every
    # massage treatment, so the booking form is usable straight away.
    for operator in operators:
        operator["treatment_ids"] = [
            t["id"] for t in treatments if t["category_id"] == "cat_massaggi"
        ]
    return {
        KEY_CATEGORIES: categories,
        KEY_TREATMENTS: treatments,
        KEY_OPERATORS: operators,
        KEY_CLIENTS: [],
        KEY_APPOINTMENTS: [],
        KEY_REQUESTS: [],
        KEY_SLOT_BLOCKS: [],
        KEY_CLOSURES: [],
        KEY_SETTINGS: default_settings(),
    }


def default_settings() -> dict[str, Any]:
    """Return the notification defaults for this installation.

    The Telegram entry id and the three authorised chats are seeded so the
    monthly report works on the first run; they stay editable from the card.
    """
    return _norm_settings(
        {
            "telegram_config_entry_id": DEFAULT_TELEGRAM_ENTRY_ID,
            "report_telegram_chats": DEFAULT_REPORT_TELEGRAM_CHATS,
            "report_whatsapp_chat": "",
            "report_per_operator": True,
            "report_enabled": True,
            "report_time": DEFAULT_REPORT_TIME,
            KEY_PERMISSIONS: {},
        }
    )


class SpaBookingCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Store and manage every SPA booking record."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialize the coordinator without starting a polling interval."""
        self.entry = entry
        self._store = Store(hass, STORAGE_VERSION, STORAGE_KEY)
        self._lock = asyncio.Lock()
        self._data: dict[str, Any] = default_data()
        # The inbound WhatsApp handler, once the gateway is switched on.
        self._waha_inbound: WahaInbound | None = None
        # Recent WhatsApp messages from numbers that are neither clients nor
        # operators, so the desk can read and answer external requests.
        self._external_messages: deque[dict[str, Any]] = deque(maxlen=20)
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=None,
        )

    @property
    def device_info(self) -> DeviceInfo:
        """Return the device every entity belongs to."""
        return DeviceInfo(
            identifiers={(DOMAIN, self.entry.entry_id)},
            name=self.entry.title,
            manufacturer="Spa Booking",
            entry_type=DeviceEntryType.SERVICE,
        )

    async def async_load(self) -> None:
        """Load the dataset from storage, seeding it when absent."""
        stored = await self._store.async_load()
        if isinstance(stored, dict):
            self._data, stale = self._upgrade(stored)
            if stale:
                await self._store.async_save(self._data)
        else:
            self._data = default_data(self.entry.data.get("operator_names") or [])
            await self._store.async_save(self._data)
        self.async_set_updated_data(self._data)

    async def async_add_external_message(self, chat_id: str, text: str) -> None:
        """Save an incoming WhatsApp message from a non-operator number.

        The webhook fires ``EVENT_ANSWER_REQUEST`` for every inbound message;
        when the sender is not a known operator and the text is not an answer,
        the handler stores it here and fires ``EVENT_EXTERNAL_MESSAGE`` so a
        sensor and a notification automation can pick it up.
        """
        entry = {
            "chat_id": chat_id,
            "text": text,
            "received_at": dt_util.now().isoformat(),
        }
        self._external_messages.appendleft(entry)
        self.async_update_listeners()
        self.hass.bus.async_fire(
            EVENT_EXTERNAL_MESSAGE,
            {"chat_id": chat_id, "text": text},
        )

    @property
    def external_messages(self) -> list[dict[str, Any]]:
        """Return recent external WhatsApp messages, newest first."""
        return list(self._external_messages)

    @property
    def last_external_message(self) -> dict[str, Any] | None:
        """Return the most recent external WhatsApp message, or None."""
        return self._external_messages[0] if self._external_messages else None

    def _upgrade(self, raw: dict[str, Any]) -> tuple[dict[str, Any], bool]:
        """Normalise a stored or imported archive, upgrading older layouts.

        An archive can predate the notification settings and the treatment-side
        operator list, for instance when it comes from ``import_data``. Both
        upgrades are applied here so a restored backup behaves like a freshly
        seeded dataset instead of arriving silently switched off. The second
        element of the result says whether anything changed, so a steady-state
        load does not rewrite the store on every restart.
        """
        # Missing settings inherit this installation's defaults.
        stale = KEY_SETTINGS not in raw
        if stale:
            raw = {**raw, KEY_SETTINGS: default_settings()}

        self._data = _normalise(raw)
        if self._migrate_operator_treatments():
            stale = True
        if self._migrate_appointment_batch_ids():
            stale = True
        if self._migrate_appointment_codes():
            stale = True
        self._sync_treatment_operator_ids()
        return self._data, stale

    def _migrate_appointment_codes(self) -> bool:
        """Assign a 5-char booking code to every appointment missing one.

        Appointments written before this field existed have an empty code: give
        each of them a unique one now, so the desk and the guest always have a
        reference to quote.
        """
        codes = set()
        changed = False
        for appointment in self.appointments:
            if appointment.get("code"):
                codes.add(appointment["code"])
        for appointment in self.appointments:
            if appointment.get("code"):
                continue
            appointment["code"] = _new_code(codes)
            codes.add(appointment["code"])
            changed = True
        return changed

    def _migrate_operator_treatments(self) -> bool:
        """Move the treatment-side operator list onto the operator cards.

        The relation used to be authored on each treatment; it is now authored
        on the operator, so an archive written before the change is migrated by
        reading the old field. Returns whether anything actually changed, so a
        steady-state load does not rewrite the store on every restart.
        """
        known = {t["id"] for t in self.treatments}
        changed = False
        for operator in self.operators:
            legacy = [
                treatment["id"]
                for treatment in self.treatments
                if operator["id"] in (treatment.get("operator_ids") or [])
            ]
            merged = {t for t in operator["treatment_ids"] if t in known}
            merged.update(legacy)
            ordered = [t["id"] for t in self.treatments if t["id"] in merged]
            if ordered != operator["treatment_ids"]:
                operator["treatment_ids"] = ordered
                changed = True
        return changed

    # ------------------------------------------------------------------
    # collection accessors
    # ------------------------------------------------------------------
    @property
    def categories(self) -> list[dict[str, Any]]:
        """Return all categories."""
        return self._data[KEY_CATEGORIES]

    @property
    def treatments(self) -> list[dict[str, Any]]:
        """Return all treatments."""
        return self._data[KEY_TREATMENTS]

    @property
    def operators(self) -> list[dict[str, Any]]:
        """Return all operators."""
        return self._data[KEY_OPERATORS]

    @property
    def clients(self) -> list[dict[str, Any]]:
        """Return all clients."""
        return self._data[KEY_CLIENTS]

    @property
    def appointments(self) -> list[dict[str, Any]]:
        """Return all appointments."""
        return self._data[KEY_APPOINTMENTS]

    @property
    def slot_blocks(self) -> list[dict[str, Any]]:
        """Return the time windows operators have refused."""
        return self._data[KEY_SLOT_BLOCKS]

    @property
    def closures(self) -> list[dict[str, Any]]:
        """Return the closures decided from the dashboard."""
        return self._data[KEY_CLOSURES]

    @property
    def vouchers(self) -> list[dict[str, Any]]:
        """Return the gift vouchers sold at the desk."""
        return self._data[KEY_VOUCHERS]

    @property
    def promo_vouchers(self) -> list[dict[str, Any]]:
        """Return the loyalty vouchers ("Voucher fedelta") awarded after use."""
        return self._data[KEY_PROMO_VOUCHERS]

    @property
    def requests(self) -> list[dict[str, Any]]:
        """Return the appointment requests waiting to be worked."""
        return self._data[KEY_REQUESTS]

    async def _async_save(self) -> None:
        """Persist the dataset and notify every listener.

        The derived ``operator_ids`` of each treatment is refreshed here, so
        the two representations of the same relation cannot drift apart no
        matter which record was edited.
        """
        self._sync_treatment_operator_ids()
        await self._store.async_save(self._data)
        self.async_set_updated_data(self._data)

    @staticmethod
    def _find(
        records: list[dict[str, Any]], record_id: str | None, label: str
    ) -> dict[str, Any]:
        """Return the record with the given id or raise."""
        for record in records:
            if record["id"] == record_id:
                return record
        raise NotFoundError(f"{label} con id '{record_id}' non trovato")

    def _category(self, category_id: str | None) -> dict[str, Any] | None:
        """Return a category by id, or None."""
        return next((c for c in self.categories if c["id"] == category_id), None)

    def _operator(self, operator_id: str | None) -> dict[str, Any] | None:
        """Return an operator by id, or None."""
        return next((o for o in self.operators if o["id"] == operator_id), None)

    def _operator_name(self, operator_id: str | None) -> str:
        """Return an operator name, or a placeholder."""
        operator = self._operator(operator_id)
        return operator["name"] if operator else "Senza operatore"

    def get_client(self, client_id: str) -> dict[str, Any]:
        """Return a client by id, raising when it does not exist."""
        return self._find(self.clients, client_id, "Cliente")

    @staticmethod
    def full_name(client: dict[str, Any]) -> str:
        """Return the client full name."""
        return " ".join(
            part for part in (client.get("first_name"), client.get("last_name")) if part
        ).strip()

    def _treatment_requires_operator(self, treatment: dict[str, Any]) -> bool:
        """Return whether a treatment must be assigned to an operator."""
        if self.operators_for_treatment(treatment["id"]):
            return True
        category = self._category(treatment.get("category_id"))
        return bool(category and category["requires_operator"])

    def operators_for_treatment(self, treatment_id: str) -> list[dict[str, Any]]:
        """Return the operators able to perform a treatment, in name order.

        The relation lives on the operator card, so this is the only place it is
        read: an operator with an empty list performs no massage, while a
        treatment no operator lists accepts any operator of its category.
        """
        matched = [
            operator
            for operator in self.operators
            if treatment_id in (operator.get("treatment_ids") or [])
        ]
        return sorted(matched, key=lambda o: o["name"].lower())

    # ------------------------------------------------------------------
    # refused time windows (slot blocks)
    # ------------------------------------------------------------------
    def _block_window_utc(
        self, block: dict[str, Any]
    ) -> tuple[datetime, datetime] | None:
        """Return a block as a UTC interval, or None when it is malformed.

        The window is stored as a local date and local times, so it is rebuilt
        in the local timezone here: comparing local wall times directly would
        be off by an hour twice a year.
        """
        try:
            day = date.fromisoformat(block["date"])
            start_local = datetime.combine(
                day, time.fromisoformat(block["start"])
            ).replace(tzinfo=dt_util.DEFAULT_TIME_ZONE)
            end_local = datetime.combine(
                day, time.fromisoformat(block["end"])
            ).replace(tzinfo=dt_util.DEFAULT_TIME_ZONE)
        except ValueError:
            return None
        if end_local <= start_local:
            end_local += timedelta(days=1)
        return dt_util.as_utc(start_local), dt_util.as_utc(end_local)

    def _slot_blocked(
        self, operator_id: str | None, start: datetime, end: datetime
    ) -> bool:
        """Return whether an operator refused a window overlapping this one."""
        if not operator_id:
            return False
        start_utc = dt_util.as_utc(start)
        end_utc = dt_util.as_utc(end)
        for block in self.slot_blocks:
            if block["operator_id"] != operator_id:
                continue
            window = self._block_window_utc(block)
            if window and window[0] < end_utc and window[1] > start_utc:
                return True
        return False

    def _add_block(self, appointment: dict[str, Any], operator_id: str | None) -> bool:
        """Record that an operator refused this appointment's window."""
        if not operator_id:
            return False
        start = dt_util.parse_datetime(appointment["start"])
        end = dt_util.parse_datetime(appointment["end"])
        if start is None or end is None:
            return False
        if self._slot_blocked(operator_id, start, end):
            return False
        start_local = dt_util.as_local(start)
        end_local = dt_util.as_local(end)
        self.slot_blocks.append(
            _norm_slot_block(
                {
                    "operator_id": operator_id,
                    "date": start_local.date().isoformat(),
                    "start": start_local.strftime("%H:%M"),
                    "end": end_local.strftime("%H:%M"),
                    "appointment_id": appointment["id"],
                }
            )
        )
        return True

    def _add_window_block(
        self, operator_id: str | None, window: dict[str, str]
    ) -> bool:
        """Record an operator's own refused window (a whole day or a range)."""
        if not operator_id:
            return False
        self.slot_blocks.append(
            _norm_slot_block(
                {
                    "operator_id": operator_id,
                    "date": window["date"],
                    "start": window["start"],
                    "end": window["end"],
                    "appointment_id": "",
                }
            )
        )
        return True

    def _parse_refused_window(
        self, text: str, appointment: dict[str, Any]
    ) -> dict[str, str] | None:
        """Read a refusal note as a blocked window, or None if it carries none.

        Accepts "tutto il giorno", a date (gg-mm-aaaa, oggi, domani) and one or
        two times (HH:MM). A single time blocks from then to the end of the day;
        with no date at all, the offered appointment's day is used.
        """
        lowered = (text or "").lower()
        all_day = "tutto il giorno" in lowered or "tutta la giornata" in lowered
        day: date | None = None
        match = _REFUSE_DATE.search(lowered)
        if match:
            try:
                day = date(
                    int(match.group(3)), int(match.group(2)), int(match.group(1))
                )
            except ValueError:
                day = None
        elif "domani" in lowered:
            day = dt_util.now().date() + timedelta(days=1)
        elif "oggi" in lowered:
            day = dt_util.now().date()

        times = _REFUSE_TIME.findall(lowered)
        if day is None:
            if not (all_day or times):
                return None
            start = dt_util.parse_datetime(appointment.get("start") or "")
            day = (
                dt_util.as_local(start).date()
                if start is not None
                else dt_util.now().date()
            )

        if all_day or not times:
            start_t, end_t = "00:00", "23:59"
        elif len(times) >= 2:
            start_t = f"{int(times[0][0]):02d}:{times[0][1]}"
            end_t = f"{int(times[1][0]):02d}:{times[1][1]}"
        else:
            start_t = f"{int(times[0][0]):02d}:{times[0][1]}"
            end_t = "23:59"
        return {"date": day.isoformat(), "start": start_t, "end": end_t}

    def _clear_blocks(self, operator_id: str, appointment_id: str = "") -> int:
        """Drop an operator's blocks and return how many went away.

        With an ``appointment_id`` only the blocks that appointment created are
        dropped, so "available again" on one offer never reopens a window she
        refused for some other booking.
        """
        if not operator_id:
            return 0
        keep = [
            block
            for block in self.slot_blocks
            if not (
                block["operator_id"] == operator_id
                and (not appointment_id or block["appointment_id"] == appointment_id)
            )
        ]
        removed = len(self.slot_blocks) - len(keep)
        self.slot_blocks[:] = keep
        return removed

    # ------------------------------------------------------------------
    # offers
    # ------------------------------------------------------------------
    def _offer_deadline(self) -> str:
        """Return the ISO instant an offer expires at, or "" when disabled."""
        try:
            hours = int(self._data[KEY_SETTINGS].get("offer_timeout_hours") or 0)
        except (TypeError, ValueError):
            hours = 0
        if hours <= 0:
            return ""
        return (dt_util.utcnow() + timedelta(hours=hours)).isoformat()

    def _reminder_hours(self) -> int:
        """Return how long before the deadline a reminder is sent (0 = never)."""
        try:
            return max(0, int(self._data[KEY_SETTINGS].get("offer_reminder_hours") or 0))
        except (TypeError, ValueError):
            return 0

    def _available_candidates(
        self,
        treatment: dict[str, Any],
        start: datetime,
        end: datetime,
        requested: list[str] | None = None,
    ) -> list[str]:
        """Return the operators to offer, in order, minus the refused ones.

        The caller states the candidates: the booking form sends either the
        masseuses it lists or the whole able list for "automatica", and the
        cascade then works through them. Nobody refusing the call has to name
        an operator, but a call that names none for a massage is still
        refused, so a script cannot create an unattended booking by omission.
        """
        if requested:
            pool: list[str] = []
            for operator_id in requested:
                # Raises when the operator does not exist or cannot do it.
                self._validate_operator(treatment, operator_id)
                if operator_id not in pool:
                    pool.append(operator_id)
        else:
            if not self._treatment_requires_operator(treatment):
                return []
            allowed = self.operators_for_treatment(treatment["id"])
            allowed_names = ", ".join(operator["name"] for operator in allowed)
            if allowed_names:
                raise ValidationError(
                    f"Seleziona un operatore per il trattamento "
                    f"'{treatment['name']}'. Disponibili: {allowed_names}"
                )
            raise ValidationError(
                f"Il trattamento '{treatment['name']}' richiede un operatore"
            )
        # A closure takes an operator out of the offers for those days, the
        # same way a refused window does, so a colleague can still take it.
        closed = self._closed_operator_ids(start, end)
        available = [
            oid for oid in pool if not self._slot_blocked(oid, start, end) and oid not in closed
        ]
        # A disabled operator is never asked, and the rest go out in ascending
        # priority order (lower first), keeping the given order on a tie.
        available = [
            oid for oid in available if (self._operator(oid) or {}).get("active", True)
        ]
        order = {oid: index for index, oid in enumerate(pool)}
        available.sort(
            key=lambda oid: (
                int((self._operator(oid) or {}).get("priority") or 0),
                order.get(oid, 0),
            )
        )
        return available

    def _next_candidate(
        self, appointment: dict[str, Any], start: datetime, end: datetime
    ) -> tuple[str | None, int]:
        """Return the next operator to ask after the current one, if any.

        Every candidate already holding an overlapping block is skipped, so a
        masseuse who refused earlier is never asked again for this window. A
        closure takes her out of the list for those days too.
        """
        candidates = appointment.get("offer_candidates") or []
        closed = self._closed_operator_ids(start, end)
        for index in range(appointment.get("offer_index", 0) + 1, len(candidates)):
            operator_id = candidates[index]
            if self._slot_blocked(operator_id, start, end) or operator_id in closed:
                continue
            return operator_id, index
        return None, len(candidates)

    # ------------------------------------------------------------------
    # appointments
    # ------------------------------------------------------------------
    def _validate_operator(
        self, treatment: dict[str, Any], operator_id: str | None
    ) -> str | None:
        """Validate the requested operator against the treatment."""
        allowed = self.operators_for_treatment(treatment["id"])
        allowed_ids = [operator["id"] for operator in allowed]
        allowed_names = ", ".join(operator["name"] for operator in allowed)

        if operator_id:
            operator = self._find(self.operators, operator_id, "Operatore")
            # A treatment that needs no operator (spa entry, jacuzzi) can never
            # carry one: masseuses only work on massages.
            if not self._treatment_requires_operator(treatment):
                raise ValidationError(
                    f"Il trattamento '{treatment['name']}' non richiede un'operatore: "
                    f"non può essere assegnato a {operator['name']}."
                )
            # If the treatment has enabled operators, only they can take it.
            if allowed_ids and operator_id not in allowed_ids:
                raise ValidationError(
                    f"L'operatore '{operator['name']}' non e' abilitato al trattamento "
                    f"'{treatment['name']}'. Operatori consentiti: {allowed_names}."
                )
            return operator["id"]

        if self._treatment_requires_operator(treatment):
            if allowed_names:
                raise ValidationError(
                    f"Seleziona un operatore per il trattamento "
                    f"'{treatment['name']}'. Disponibili: {allowed_names}"
                )
            raise ValidationError(
                f"Il trattamento '{treatment['name']}' richiede un operatore"
            )
        return None

    def _resolve_client(
        self,
        client_id: str | None,
        first_name: str,
        last_name: str,
        phone: str,
        email: str,
        notes: str,
        update_existing: bool = False,
        staged: list[dict[str, Any]] | None = None,
        force_new: bool = False,
        promo_opt_in: bool | None = None,
    ) -> dict[str, Any]:
        """Return an existing client or create a new one.

        When ``update_existing`` is set and a match is found, the missing
        fields are filled in on that record instead of being dropped.
        ``staged`` carries the clients created earlier in the same batch but not
        appended yet, so booking three people with the same number produces one
        card, not three.
        """
        if client_id:
            return self._find(self.clients, client_id, "Cliente")

        first_name = first_name.strip()
        last_name = last_name.strip()
        phone = phone.strip()

        if not (first_name or last_name or phone):
            raise ValidationError(
                "Indica almeno il cognome o il telefono del cliente, oppure "
                "seleziona una scheda cliente esistente"
            )

        def _fill(client: dict[str, Any]) -> dict[str, Any]:
            """Fill the missing fields of a matched client, name included."""
            for key, value in (
                ("first_name", first_name),
                ("last_name", last_name),
                ("email", email),
            ):
                if value.strip():
                    client[key] = value.strip()
            if notes:
                client["notes"] = notes
            return client

        # A forced new card skips every match, so two people who share a name
        # (or a number) each get their own id instead of one shared card.
        for client in [] if force_new else list(self.clients) + (staged or []):
            if phone and _same_phone(client["phone"], phone):
                return _fill(client) if update_existing else client

        # No phone to compare: a party without numbers must still produce one
        # card, and so must the same person coming back to the desk later. The
        # exact full name is the only anchor left; matching is deliberately
        # limited to records that also lack a phone, so two people who merely
        # share a name but gave different numbers stay separate.
        if not phone and not force_new:
            for client in list(self.clients) + (staged or []):
                if (
                    not client["phone"]
                    and client["first_name"].strip().lower() == first_name.lower()
                    and client["last_name"].strip().lower() == last_name.lower()
                ):
                    return _fill(client) if update_existing else client

        payload = {
            "first_name": first_name,
            "last_name": last_name,
            "phone": phone,
            "email": email.strip(),
            "notes": notes,
        }
        # Only the client-card form carries a promo choice: bookings leave it
        # out so a returning guest keeps whatever the desk decided for her.
        if promo_opt_in is not None:
            payload["promo_opt_in"] = bool(promo_opt_in)
        return _norm_client(payload)

    @staticmethod
    def _minutes_of(value: str) -> int:
        """Minutes since midnight of an "HH:MM" string, -1 when malformed."""
        try:
            hour, minute = value.split(":")
            return int(hour) * 60 + int(minute)
        except (TypeError, ValueError):
            return -1

    @staticmethod
    def _window_ok(start: str, end: str, window_start: datetime, window_end: datetime) -> bool:
        """Whether the whole appointment fits inside an "HH:MM" window.

        A window with no endpoints is absent, so it never refuses anything.
        """
        if not start and not end:
            return True
        w_start = SpaBookingCoordinator._minutes_of(start)
        w_end = SpaBookingCoordinator._minutes_of(end)
        if w_start < 0 or w_end < 0:
            return True  # malformed window: ignore it rather than block bookings
        s_min = window_start.hour * 60 + window_start.minute
        e_min = window_end.hour * 60 + window_end.minute
        return w_start <= s_min and e_min <= w_end

    def _validate_category_window(
        self,
        category: dict[str, Any] | None,
        start: datetime,
        end: datetime,
    ) -> None:
        """Refuse a booking outside the category's days and time windows.

        ``days`` (Mon=0 .. Sun=6) restricts which weekdays can be booked;
        empty means every day. The morning and afternoon windows are optional:
        when either is set, the whole appointment (start and end) must fit
        inside one of them. Everything is evaluated in local time.
        """
        if not category:
            return
        local_start = dt_util.as_local(start)
        local_end = dt_util.as_local(end)

        morning = (category.get("morning_start") or "", category.get("morning_end") or "")
        afternoon = (category.get("afternoon_start") or "", category.get("afternoon_end") or "")
        morning_days = category.get("morning_days") or []
        afternoon_days = category.get("afternoon_days") or []
        weekday = local_start.weekday()

        # Which window the booking falls into decides which day list applies:
        # a morning booking is only accepted on a morning day, an afternoon
        # one on an afternoon day.
        in_morning = any(morning) and self._window_ok(*morning, local_start, local_end)
        in_afternoon = any(afternoon) and self._window_ok(*afternoon, local_start, local_end)
        if in_morning or in_afternoon:
            allowed = morning_days if in_morning else afternoon_days
            slot = "di mattina" if in_morning else "di pomeriggio"
            if allowed and weekday not in allowed:
                labels = ", ".join(
                    WEEKDAY_LABELS[d] for d in allowed if 0 <= d < len(WEEKDAY_LABELS)
                )
                raise ValidationError(
                    f"La categoria '{category['name']}' accetta prenotazioni "
                    f"{slot} solo {labels}"
                )
            return

        # The booking fits no window: if windows exist at all, it is outside
        # the allowed hours.
        windows = [window for window in (morning, afternoon) if any(window)]
        if windows:
            labels = " e ".join(
                _fmt_window(*window) or "—" for window in windows
            )
            raise ValidationError(
                f"La categoria '{category['name']}' accetta appuntamenti "
                f"solo nelle fasce {labels}: "
                f"l'orario scelto ({local_start:%H:%M}-{local_end:%H:%M}) "
                f"deve starci interamente"
            )

        # No windows at all: the union of the two day lists applies.
        allowed = sorted(set(morning_days) | set(afternoon_days))
        if allowed and weekday not in allowed:
            labels = ", ".join(
                WEEKDAY_LABELS[d] for d in allowed if 0 <= d < len(WEEKDAY_LABELS)
            )
            raise ValidationError(
                f"La categoria '{category['name']}' accetta prenotazioni "
                f"solo {labels}"
            )

    def _parallel_guard(
        self,
        treatment: dict[str, Any],
        start_dt: datetime,
        end_dt: datetime,
        planned: list[dict[str, Any]] | None,
        batch_total: int = 1,
    ) -> None:
        """Enforce a shared treatment's parallel appointment limits.

        ``min_parallel`` is how many people must share the slot: it counts the
        whole batch for this treatment plus the people already booked in the
        same window, so a lone booking is fine when a party already fills the
        slot. ``max_parallel`` is the capacity: existing confirmed
        appointments plus the new overlapping ones must stay at or below it.
        Only shared treatments (no operator) are guarded: a masseuse always
        works 1:1 with her own conflict window.
        """
        planned = planned or []
        same_treatment = [
            item for item in planned if item["treatment_id"] == treatment["id"]
        ]

        def overlaps(other: dict[str, Any]) -> bool:
            other_start = dt_util.parse_datetime(other["start"])
            other_end = dt_util.parse_datetime(other["end"])
            return bool(
                other_start
                and other_end
                and other_start < end_dt
                and other_end > start_dt
            )

        # People already booked in this same window for this treatment. A
        # shared treatment counts them for the minimum too: a lone booking is
        # fine when the slot already holds a party, because the minimum is
        # about how many people share the facility, not how many arrived in
        # one booking.
        existing = sum(
            1
            for appointment in self.appointments
            if occupies_slot(appointment)
            and appointment["treatment_id"] == treatment["id"]
            and overlaps(appointment)
        )

        # For max_parallel, count only the new entries that overlap this one.
        overlapping_new = 1 + sum(1 for item in same_treatment if overlaps(item))

        min_parallel = _norm_parallel(treatment.get("min_parallel"))
        max_parallel = _norm_parallel(treatment.get("max_parallel"))
        if min_parallel and (batch_total + existing) < min_parallel:
            raise ValidationError(
                f"Il trattamento '{treatment['name']}' richiede almeno "
                f"{min_parallel} persone insieme nella stessa fascia "
                f"(qui: {batch_total + existing})."
            )

        if max_parallel:
            total = existing + overlapping_new
            if total > max_parallel:
                raise ValidationError(
                    f"Il trattamento '{treatment['name']}' ha capienza massima "
                    f"di {max_parallel} persone insieme (già {existing}, "
                    f"più {overlapping_new} di questa prenotazione)."
                )

    def _category_exclusion(
        self,
        treatment: dict[str, Any],
        start_dt: datetime,
        end_dt: datetime,
        planned: list[dict[str, Any]] | None,
    ) -> None:
        """Refuse an appointment overlapping a category it must not share time with.

        The exclusion is mutual: a category that declares another protects
        itself too, no matter which side authored the rule. The window is
        exact — pauses only bind the masseuse, never other categories.
        """
        category = self._category(treatment.get("category_id"))
        if not category:
            return
        declared = set(category.get("exclusive_with") or [])

        for other in self.categories:
            if other["id"] == category["id"]:
                continue
            mutual = other["id"] in declared or category["id"] in (
                other.get("exclusive_with") or []
            )
            if not mutual:
                continue
            for appointment in list(self.appointments) + (planned or []):
                if not occupies_slot(appointment):
                    continue
                other_treatment = next(
                    (t for t in self.treatments if t["id"] == appointment["treatment_id"]),
                    None,
                )
                if not other_treatment or other_treatment.get("category_id") != other["id"]:
                    continue
                other_start = dt_util.parse_datetime(appointment["start"])
                other_end = dt_util.parse_datetime(appointment["end"])
                if (
                    other_start
                    and other_end
                    and other_start < end_dt
                    and other_end > start_dt
                ):
                    raise ValidationError(
                        f"La categoria '{category['name']}' non può sovrapporsi "
                        f"a '{other['name']}': "
                        f"{self._summary(self.appointment_payload(appointment))}"
                    )

    @staticmethod
    def _closure_days(closure: dict[str, Any]) -> list[str]:
        """Every calendar day a closure covers, as "YYYY-MM-DD".

        A missing ``date_to`` means the single day ``date_from``. The span is
        capped so a mistyped end date cannot make a booking check unbounded.
        """
        start = str(closure.get("date_from") or "")[:10]
        end = str(closure.get("date_to") or "")[:10] or start
        if not start:
            return []
        try:
            first = date.fromisoformat(start)
            last = date.fromisoformat(end)
        except ValueError:
            return []
        if last < first:
            first, last = last, first
        if (last - first).days >= MAX_CLOSURE_DAYS:
            last = first + timedelta(days=MAX_CLOSURE_DAYS - 1)
        return [
            (first + timedelta(days=offset)).isoformat()
            for offset in range((last - first).days + 1)
        ]

    def _closure_windows_utc(self, closure: dict[str, Any]) -> list[tuple[datetime, datetime]]:
        """The UTC intervals a closure actually covers."""
        days = self._closure_days(closure)
        if not days:
            return []
        start_hhmm = closure.get("start") or ""
        end_hhmm = closure.get("end") or ""
        windows: list[tuple[datetime, datetime]] = []
        for day in days:
            # Rebuilt in the local timezone, like the refused windows above:
            # comparing wall times directly is off by an hour twice a year.
            day_start = datetime.combine(
                date.fromisoformat(day), time.min
            ).replace(tzinfo=dt_util.DEFAULT_TIME_ZONE)
            if start_hhmm and end_hhmm:
                open_at = self._at_hhmm(day_start, start_hhmm)
                close_at = self._at_hhmm(day_start, end_hhmm)
                if close_at <= open_at:
                    # A range that wraps past midnight covers the rest of the
                    # day plus the morning of the next one.
                    close_at += timedelta(days=1)
            else:
                open_at = day_start
                close_at = day_start + timedelta(days=1)
            windows.append((dt_util.as_utc(open_at), dt_util.as_utc(close_at)))
        return windows

    @staticmethod
    def _at_hhmm(day_start: datetime, hhmm: str) -> datetime:
        """The local "HH:MM" of the day that starts at ``day_start``."""
        minutes = SpaBookingCoordinator._minutes_of(hhmm)
        if minutes < 0:
            return day_start
        return day_start + timedelta(minutes=minutes)

    def _closure_covering(
        self, closure: dict[str, Any], start: datetime, end: datetime
    ) -> bool:
        """Whether this closure overlaps the given interval."""
        start_utc = dt_util.as_utc(start)
        end_utc = dt_util.as_utc(end)
        return any(
            window[0] < end_utc and window[1] > start_utc
            for window in self._closure_windows_utc(closure)
        )

    def _closures_scope(self, scope: str) -> list[dict[str, Any]]:
        return [closure for closure in self.closures if closure["scope"] == scope]

    def _closed_operator_ids(self, start: datetime, end: datetime) -> set[str]:
        """Operators unavailable because of a closure on this interval."""
        closed: set[str] = set()
        for closure in self._closures_scope("operator"):
            if closure["operator_id"] and self._closure_covering(closure, start, end):
                closed.add(closure["operator_id"])
        return closed

    def _guard_closures(
        self, treatment: dict[str, Any], operator_id: str | None, start: datetime, end: datetime
    ) -> None:
        """Refuse a booking that lands in a closure.

        A facility or category closure closes the door, so the booking is
        refused. An operator closure is softer: she steps out of the offers, so
        a colleague can still take the slot — but naming her explicitly is
        refused, because that is a contradiction the receptionist wants to see.
        """
        category = self._category(treatment.get("category_id"))
        for closure in self._closures_scope("facility"):
            if self._closure_covering(closure, start, end):
                raise ValidationError(
                    self._closure_message(
                        closure,
                        "La struttura è chiusa in questa fascia",
                    )
                )
        for closure in self._closures_scope("category"):
            if not category or closure["category_id"] != category["id"]:
                continue
            if self._closure_covering(closure, start, end):
                raise ValidationError(
                    self._closure_message(
                        closure,
                        f"La categoria '{category['name']}' è chiusa in questa fascia",
                    )
                )
        for closure in self._closures_scope("operator"):
            if not operator_id or closure["operator_id"] != operator_id:
                continue
            if self._closure_covering(closure, start, end):
                operator = self._operator(operator_id)
                name = operator["name"] if operator else "L'operatrice"
                raise ValidationError(
                    self._closure_message(closure, f"{name} non lavora in questa fascia")
                )

    @staticmethod
    @staticmethod
    def _closure_message(closure: dict[str, Any], reason: str) -> str:
        """A receptionist-readable sentence about why a slot is closed."""
        days = SpaBookingCoordinator._closure_days(closure)
        if not days:
            return reason
        from_date, to_date = days[0], days[-1]
        if len(days) == 1:
            when = f"il {from_date[8:10]}/{from_date[5:7]}/{from_date[:4]}"
        else:
            when = f"dal {from_date[8:10]}/{from_date[5:7]} al {to_date[8:10]}/{to_date[5:7]}"
        clock = ""
        if closure.get("start") and closure.get("end"):
            clock = f" ({closure['start']}-{closure['end']})"
        label = f" — {closure['label']}" if closure.get("label") else ""
        return f"{reason}{clock} {when}{label}"

    def _pause_min_for(self, appointment: dict[str, Any]) -> int:
        """Return the pause required after an appointment's category.

        The pause belongs to the appointment already on the book: it is what
        its masseuse needs before taking the next one.
        """
        treatment = self._find(
            self.treatments, appointment["treatment_id"], "Trattamento"
        )
        if not treatment or not treatment.get("category_id"):
            return 0
        category = self._find(
            self.categories, treatment["category_id"], "Categoria"
        )
        if not category:
            return 0
        try:
            return max(0, int(category.get("pause_min") or 0))
        except (TypeError, ValueError):
            return 0

    def _treatment_pause_min(self, treatment: dict[str, Any]) -> int:
        """Return the pause required after this treatment's category.

        The same number ``_pause_min_for`` reads from an appointment, taken
        straight from the treatment: the website needs it before any
        appointment exists, and both must agree or the slot offered by the
        site would be refused by the card.
        """
        category = self._category(treatment.get("category_id"))
        if not category:
            return 0
        try:
            return max(0, int(category.get("pause_min") or 0))
        except (TypeError, ValueError):
            return 0

    def _find_conflict(
        self,
        operator_id: str | None,
        client_id: str | None,
        start: datetime,
        end: datetime,
        planned: list[dict[str, Any]] | None = None,
        client_may_repeat: bool = False,
        person_index: int | None = None,
        staged_clients: list[dict[str, Any]] | None = None,
        force_client_overlap: bool = False,
    ) -> dict[str, Any] | None:
        """Return the first overlapping appointment, if any.

        The overlapping window of the operator is the appointment plus the
        pause of its category, so the masseuse keeps her break even when the
        appointment itself has already ended. ``planned`` carries the
        appointments of the same batch that have not been appended yet, so two
        entries of one booking still see each other.

        ``client_may_repeat`` lifts the client rule for a shared treatment: a
        couple sharing the same spa session is one booking with more than one
        person, and each person is her own appointment, so the same client is
        legitimately booked twice at the same hour. A treatment that needs a
        masseuse keeps the rule, because there the slot is really taken.

        ``person_index`` is which person of the party the caller is booking,
        for the calls that say it — the card always does. The form asks for one
        name, the leader of the party, and every guest of hers is booked on
        that same card, so the card alone cannot tell a party from the same
        person twice. With the person declared, only the same person in the
        same hour is refused, and only against the other entries of this very
        booking: that is the one place where the persons are known, and it is
        what keeps one person's two treatments from sharing an hour. A guest
        booked later then still lands on the leader's card and on the same
        hour, which is what a party is.

        ``force_client_overlap`` is the desk saying "I saw the warning, book
        it anyway": the same-person client refusal is skipped, while an
        operator double-booking is still refused no matter what.
        """
        start_utc = dt_util.as_utc(start)
        end_utc = dt_util.as_utc(end)

        for appointment in [*self.appointments, *(planned or [])]:
            if not occupies_slot(appointment):
                continue
            other_start = dt_util.parse_datetime(appointment["start"])
            other_end = dt_util.parse_datetime(appointment["end"])
            if other_start is None or other_end is None:
                continue
            # Only refuse if it's the SAME person. For entries of the same
            # booking batch (we know person_index), refuse only if same
            # person number AND same client. Also allow different persons of
            # same group to overlap.
            is_same_person = _norm_person(appointment.get("person")) == _norm_person(person_index)
            if (
                not client_may_repeat
                and not force_client_overlap
                and client_id
                and appointment["client_id"] == client_id
                and other_start < end_utc
                and other_end > start_utc
                and is_same_person
            ):
                return {
                    "reason": "client",
                    **self.appointment_payload(appointment, staged_clients),
                }
            if operator_id and appointment["operator_id"] == operator_id:
                other_guard = dt_util.as_utc(other_end) + timedelta(
                    minutes=self._pause_min_for(appointment)
                )
                if not (other_start < end_utc and other_guard > start_utc):
                    continue
                return {"reason": "operator", **self.appointment_payload(appointment)}
        return None

    @staticmethod
    def _requested_operators(
        operator_id: str | None, operator_ids: list[str] | None
    ) -> list[str] | None:
        """Return the operator ids the caller asked for, in order."""
        if operator_ids:
            return [str(item) for item in operator_ids if str(item)]
        if operator_id:
            return [operator_id]
        return None

    @staticmethod
    def _overlap_error(conflict: dict[str, Any]) -> OverlapError:
        """Return the readable error for a refused overlapping booking."""
        who = (
            f"operatore {conflict['operator']['name']}"
            if conflict["reason"] == "operator"
            else f"cliente {conflict['client']['full_name']}"
        )
        return OverlapError(
            f"L'appuntamento si sovrappone a quello di {who} "
            f"dalle {conflict['start_local'][11:16]} alle "
            f"{conflict['end_local'][11:16]} del "
            f"{conflict['start_local'][:10]}",
            conflicts=[conflict],
        )

    def _prepare_booking(
        self,
        *,
        treatment_id: str,
        start: datetime | str | date,
        client_id: str | None = None,
        first_name: str = "",
        last_name: str = "",
        phone: str = "",
        email: str = "",
        client_notes: str = "",
        operator_id: str | None = None,
        operator_ids: list[str] | None = None,
        notes: str = "",
        payment: dict[str, Any] | None = None,
        pending: bool = False,
        guest_type: str = GUEST_TYPE_DEFAULT,
        extras: list[str] | None = None,
        list_price: Any = None,
        price: Any = None,
        force_client_overlap: bool = False,
        staged_clients: list[dict[str, Any]] | None = None,
        planned: list[dict[str, Any]] | None = None,
        batch_totals: dict[str, int] | None = None,
        force_new: bool = False,
        person_index: int | None = None,
        batch_id: str | None = None,
        defer_operator: bool = False,
    ) -> tuple[dict[str, Any], dict[str, Any], bool]:
        """Validate one booking and return it without appending anything.

        Everything that can be refused happens here, so a multi-row booking can
        be checked in full before a single record is written: a booking refused
        halfway must leave neither an appointment nor an empty client card.

        ``person_index`` says which person of the party this booking is, for a
        caller that books the people of one party (the card always does). Left
        out, the client card is all the caller gave.

        ``defer_operator`` keeps a booking that needs a masseuse without one and
        without starting an offer: the desk assigns her later from the agenda.
        It is how a confirmed request enters the calendar when the reception has
        not yet decided who takes it.
        """
        start_dt = as_aware_datetime(start)

        treatment = self._find(self.treatments, treatment_id, "Trattamento")
        if not treatment["active"]:
            raise ValidationError(
                f"Il trattamento '{treatment['name']}' non e' attivo"
            )
        duration = treatment["duration_min"]
        if duration <= 0:
            raise ValidationError(
                f"Il trattamento '{treatment['name']}' non ha una durata valida"
            )
        end_dt = start_dt + timedelta(minutes=duration)

        requested = self._requested_operators(operator_id, operator_ids)
        requires = bool(requested) or self._treatment_requires_operator(treatment)
        if defer_operator:
            # A request is confirmed before the desk decides who takes it: the
            # treatment is booked without a masseuse and without starting an
            # offer. No candidate list is needed, and naming none must not be
            # refused the way an unattended booking by omission is.
            candidates: list[str] = []
        else:
            candidates = self._available_candidates(
                treatment, start_dt, end_dt, requested
            )

        # Closures decided from the dashboard: a facility or category closure
        # shuts the door, an operator closure just takes her out of the offers.
        # ``operator_id`` is the single masseuse the receptionist pinned, not
        # the list of candidates: naming her explicitly is a contradiction
        # worth refusing, while asking a colleague is exactly the point.
        self._guard_closures(treatment, operator_id, start_dt, end_dt)

        # Calendar rules of the treatment's category: bookable weekdays and
        # the morning/afternoon windows the whole appointment must fit into.
        self._validate_category_window(
            self._category(treatment.get("category_id")), start_dt, end_dt
        )

        if not requires:
            # Shared treatments only: how many of them may run in parallel.
            self._parallel_guard(
                treatment,
                start_dt,
                end_dt,
                planned,
                batch_total=(batch_totals or {}).get(treatment["id"], 1),
            )
            offer_state, assigned = OFFER_NONE, None
        elif defer_operator:
            # The desk takes the booking now and decides the masseuse later: no
            # offer goes out, the appointment simply carries no operator.
            self._parallel_guard(
                treatment,
                start_dt,
                end_dt,
                planned,
                batch_total=(batch_totals or {}).get(treatment["id"], 1),
            )
            offer_state, assigned = OFFER_NONE, None
        elif candidates:
            offer_state, assigned = OFFER_PENDING, candidates[0]
        else:
            # Every able operator already refused this window: the booking is
            # kept and shown as "da assegnare" instead of being thrown away.
            offer_state, assigned = OFFER_UNASSIGNED, None

        client = self._resolve_client(
            client_id,
            first_name,
            last_name,
            phone,
            email,
            client_notes,
            staged=staged_clients,
            force_new=force_new,
        )
        is_new_client = not any(
            existing["id"] == client["id"] for existing in self.clients
        ) and not any(staged["id"] == client["id"] for staged in (staged_clients or []))

        conflict = self._find_conflict(
            assigned, client["id"], start_dt, end_dt, planned,
            client_may_repeat=not requires,
            person_index=person_index,
            staged_clients=staged_clients,
            force_client_overlap=force_client_overlap,
        )
        if conflict is not None:
            raise self._overlap_error(conflict)

        # Categories declared mutually exclusive must never run at the same time.
        self._category_exclusion(treatment, start_dt, end_dt, planned)

        # A booking can be taken and left waiting. Handing over money is a
        # confirmation in itself, so a booking with any money on it is never
        # left pending, whatever was asked for.
        settled = _payment_confirms(payment)
        # A short 5-char reference, unique across every appointment: the desk
        # reads it out, the guest quotes it, the operator finds the booking.
        used_codes = {
            existing["code"]
            for existing in (*self.appointments, *(planned or []))
            if existing.get("code")
        }
        appointment = _norm_appointment(
            {
                "client_id": client["id"],
                "treatment_id": treatment["id"],
                "operator_id": assigned,
                "start": dt_util.as_utc(start_dt).isoformat(),
                "end": dt_util.as_utc(end_dt).isoformat(),
                "notes": notes,
                "status": STATUS_PENDING if pending and not settled else STATUS_CONFIRMED,
                "guest_type": _norm_guest_type(guest_type),
                "extras": _norm_extras(extras, known=self._accessory_ids()),
                "list_price": _norm_price_opt(list_price),
                "price": _norm_price_opt(price),
                # Which person of the party this is: 0 when nobody said, which
                # is both the leader of a party and the only person of a
                # booking made for one.
                "person": _norm_person(person_index),
                "batch_id": batch_id,
                "code": _new_code(used_codes),
                # Who confirmed it, and when. Empty on a pending booking: there
                # is nobody to name yet.
                "confirmed_by": "",
                "confirmed_at": "",
                # Who created this booking (user_id of the receptionist).
                "created_by": self._current_user_id if hasattr(self, '_current_user_id') else None,
                # Payment never refuses anything, so it is copied through the
                # normaliser rather than validated here.
                **_norm_payment(payment),
                "offer_state": offer_state,
                "offer_candidates": candidates,
                "offer_index": 0,
                "offer_expires_at": (
                    self._offer_deadline() if offer_state == OFFER_PENDING else ""
                ),
            }
        )
        return appointment, client, is_new_client

    async def async_create_appointment(
        self,
        *,
        treatment_id: str,
        start: datetime | str | date,
        client_id: str | None = None,
        first_name: str = "",
        last_name: str = "",
        phone: str = "",
        email: str = "",
        client_notes: str = "",
        operator_id: str | None = None,
        operator_ids: list[str] | None = None,
        notes: str = "",
        payment: dict[str, Any] | None = None,
        pending: bool = False,
        guest_type: str = GUEST_TYPE_DEFAULT,
        extras: list[str] | None = None,
        list_price: Any = None,
        price: Any = None,
        force_client_overlap: bool = False,
        force_new: bool = False,
        batch_id: str | None = None,
    ) -> dict[str, Any]:
        """Create an appointment, deriving its end time from the treatment.

        When a treatment needs an operator the first candidate available in
        that window is assigned and the booking starts out as an offer waiting
        for her answer. ``pending`` takes the booking and leaves it waiting for
        confirmation, unless money settles it on the spot. ``guest_type`` says
        whether the guest stays at the hotel or came from outside; it does not
        change any rule, it only labels the booking.
        """
        if batch_id is None:
            batch_id = _new_id("batch")
        async with self._lock:
            appointment, client, is_new_client = self._prepare_booking(
                treatment_id=treatment_id,
                start=start,
                client_id=client_id,
                first_name=first_name,
                last_name=last_name,
                phone=phone,
                email=email,
                client_notes=client_notes,
                operator_id=operator_id,
                operator_ids=operator_ids,
                notes=notes,
                payment=payment,
                pending=pending,
                guest_type=guest_type,
                extras=extras,
                list_price=list_price,
                price=price,
                force_client_overlap=force_client_overlap,
                force_new=force_new,
                batch_id=batch_id,
            )
            # Appended only after validation, so a refused booking never leaves
            # an empty client card behind.
            if is_new_client:
                self.clients.append(client)
            self.appointments.append(appointment)
            await self._async_save()

        return await self._async_announce(appointment)

    async def async_update_appointment(
        self,
        appointment_id: str,
        *,
        treatment_id: str | None = None,
        start: datetime | str | date | None = None,
        client_id: str | None = None,
        first_name: str = "",
        last_name: str = "",
        phone: str = "",
        email: str = "",
        client_notes: str = "",
        operator_id: str | None = None,
        operator_ids: list[str] | None = None,
        notes: str = "",
        payment: dict[str, Any] | None = None,
        pending: bool | None = None,
        confirmed_by: str | None = None,
        guest_type: str | None = None,
        extras: list[str] | None = None,
        list_price: Any = None,
        price: Any = None,
        force_client_overlap: bool = False,
    ) -> dict[str, Any]:
        """Update an appointment in place, re-running every business rule.

        The record is not patched field by field: the appointment is lifted out
        of the agenda and rebuilt through _prepare_booking, so the very same
        checks that guard a new booking guard the edit — the operator's window
        with its category pause, the client's exact window, the category days
        and time windows, the parallel limits and the mutual exclusions. A
        refused edit therefore leaves the original untouched.

        Fields left out keep their current value, and the check-in/check-out
        marks survive the edit. ``payment`` replaces the whole set of payment
        details when given, so clearing every flag works; left out, the
        appointment keeps the payment it already had.

        ``pending`` moves the booking between waiting and confirmed. Payment is
        a confirmation on its own, so writing money onto a waiting booking
        confirms it whatever ``pending`` says; ``confirmed_by`` is the name of
        whoever pressed the button, and it is recorded with the moment.
        """
        async with self._lock:
            appointment = self._find(self.appointments, appointment_id, "Appuntamento")
            if appointment["status"] == STATUS_CANCELLED:
                raise ValidationError(
                    "Non puoi modificare un appuntamento annullato"
                )

            treatment_id = treatment_id or appointment["treatment_id"]
            start = start if start is not None else appointment["start"]
            # The masseuse belongs to the treatment, so the treatment is read
            # first. A treatment that takes no operator (spa entry, jacuzzi)
            # lets go of the one the appointment was carrying: changing the
            # treatment is what took her out of the picture, and keeping her
            # would refuse the whole edit, naming a masseuse nobody asked for
            # on a booking that has none.
            edit_treatment = self._find(self.treatments, treatment_id, "Trattamento")
            if self._treatment_requires_operator(edit_treatment):
                # A blank operator means "keep the current one", not "remove
                # it": the card sends an empty string when the picker is left
                # on the automatic option, which still needs the resolved
                # masseuse.
                operator_id = operator_id or appointment.get("operator_id")
                operator_ids = operator_ids or appointment.get("offer_candidates")
            else:
                # An operator asked for by name is still refused, exactly as on
                # a new booking; only the carried-over one is let go.
                self._validate_operator(edit_treatment, operator_id)
                operator_id = None
                operator_ids = None
            notes = notes if notes else appointment.get("notes", "")
            payment = payment if payment is not None else _norm_payment(appointment)
            # Left out, the edit keeps the hotel/external flag it already has:
            # an ordinary time change must not silently turn a hotel guest
            # back into an external one.
            guest_type = (
                guest_type
                if guest_type is not None
                else appointment.get("guest_type", GUEST_TYPE_DEFAULT)
            )
            # Left out, the edit keeps the accessories the appointment already
            # has: an ordinary time change must not silently drop what the
            # guest ordered. An explicit empty list clears them.
            extras = (
                extras
                if extras is not None
                else appointment.get("extras") or []
            )
            # Left out, the edit keeps the agreed prices: an ordinary change
            # must not silently reset a discount the desk already gave.
            if list_price is None:
                list_price = appointment.get("list_price")
            if price is None:
                price = appointment.get("price")

            # Decide the status once, here, so the booking rebuilt below and
            # the confirmation trail cannot disagree.
            was_pending = appointment["status"] == STATUS_PENDING
            wants_pending = was_pending if pending is None else pending
            if _payment_confirms(payment):
                wants_pending = False
            confirming = (not wants_pending) and was_pending

            index = self.appointments.index(appointment)
            self.appointments.pop(index)

            # A shared treatment's minimum party size must count the group
            # already booked in this slot, not just the one appointment being
            # rebuilt: editing one member of a party of four must not suddenly
            # look like a lone booking.
            start_dt_edit = as_aware_datetime(start)
            end_dt_edit = start_dt_edit + timedelta(
                minutes=edit_treatment["duration_min"]
            )
            batch_totals = {
                treatment_id: 1
                + sum(
                    1
                    for other in self.appointments
                    if occupies_slot(other)
                    and other["treatment_id"] == treatment_id
                    and _same_window(other, start_dt_edit, end_dt_edit)
                )
            }

            try:
                rebuilt, client, is_new_client = self._prepare_booking(
                    treatment_id=treatment_id,
                    start=start,
                    client_id=client_id or appointment["client_id"],
                    first_name=first_name,
                    last_name=last_name,
                    phone=phone,
                    email=email,
                    client_notes=client_notes,
                    operator_id=operator_id,
                    operator_ids=operator_ids,
                    notes=notes,
                    payment=payment,
                    pending=wants_pending,
                    guest_type=guest_type,
                    extras=extras,
                    list_price=list_price,
                    price=price,
                    force_client_overlap=force_client_overlap,
                    batch_totals=batch_totals,
                )
            except Exception:
                # Refused: put the original back exactly as it was.
                self.appointments.insert(index, appointment)
                raise

            # Keep the same id and the check-in/check-out trail.
            rebuilt["id"] = appointment["id"]
            # Preserve the booking batch so the appointment stays grouped with
            # the others created together, even after a single edit.
            rebuilt["batch_id"] = appointment.get("batch_id")
            rebuilt["created_at"] = appointment.get("created_at", "")
            # The 5-char reference the desk reads out and the guest quotes must
            # not change on an edit: only a brand-new booking gets a new code.
            if appointment.get("code"):
                rebuilt["code"] = appointment["code"]
            # The takings register survives the edit: prices travel through
            # the rebuild above, payments only move via their own services.
            rebuilt["payments"] = _norm_payment_list(appointment.get("payments"))
            rebuilt["checked_in"] = appointment.get("checked_in", False)
            rebuilt["checked_in_at"] = appointment.get("checked_in_at", "")
            rebuilt["checked_out"] = appointment.get("checked_out", False)
            rebuilt["checked_out_at"] = appointment.get("checked_out_at", "")
            # The confirmation trail belongs to the appointment, not to this
            # edit: an ordinary change keeps who confirmed it and when, and
            # only the move from waiting to confirmed writes a new name.
            rebuilt["confirmed_by"] = appointment.get("confirmed_by", "")
            rebuilt["confirmed_at"] = appointment.get("confirmed_at", "")
            if confirming:
                rebuilt["confirmed_by"] = (confirmed_by or "").strip()
                rebuilt["confirmed_at"] = dt_util.utcnow().isoformat()

            if is_new_client:
                self.clients.append(client)
            self.appointments.insert(index, rebuilt)
            await self._async_save()

        # The deposit request is never sent on its own: the desk decides after
        # the edit, from the confirmation prompt or the appointment popup.
        return self.appointment_payload(rebuilt)

    async def async_update_appointment_group(
        self, appointment_id: str, **fields: Any
    ) -> dict[str, Any]:
        """Apply one edit to every appointment of the group.

        The group is the appointments sharing the client, the treatment and the
        exact slot, so moving or changing one carries to the whole party.
        """
        anchor = self._find(self.appointments, appointment_id, "Appuntamento")
        member_ids = [
            anchor["id"],
            *(item["id"] for item in self._group_siblings(anchor)),
        ]
        updated = []
        for member_id in member_ids:
            updated.append(await self.async_update_appointment(member_id, **fields))
        return {"appointments": updated, "count": len(updated)}

    def _group_siblings(
        self, appointment: dict[str, Any]
    ) -> list[dict[str, Any]]:
        """The other appointments of this person's group in the same slot.

        A group is the appointments that share the treatment, the client and
        the exact start: that is what the multi-person form produces, and it is
        what "two more people" has to add to. The anchor itself is left out.
        """
        return [
            other
            for other in self.appointments
            if other["id"] != appointment["id"]
            and occupies_slot(other)
            and other["treatment_id"] == appointment["treatment_id"]
            and other["client_id"] == appointment["client_id"]
            and other["start"] == appointment["start"]
        ]

    def group_size(self, appointment: dict[str, Any]) -> int:
        """How many people the group of this appointment holds, anchor included."""
        return 1 + len(self._group_siblings(appointment))

    async def async_resize_appointment_group(
        self, appointment_id: str, persons: int
    ) -> dict[str, Any]:
        """Set how many people share this appointment's slot.

        Each person is an appointment of her own, so the group grows by
        booking the missing ones and shrinks by cancelling the surplus ones.
        The anchor is never touched, so its id and its check-in trail survive;
        the whole resize is validated first and applied in one go, so a
        refusal leaves the group exactly as it was.
        """
        try:
            wanted = int(persons)
        except (TypeError, ValueError):
            raise ValidationError("Il numero di persone non e' valido") from None
        if wanted < 1:
            raise ValidationError("Un appuntamento ha almeno una persona")

        async with self._lock:
            anchor = self._find(self.appointments, appointment_id, "Appuntamento")
            if anchor["status"] != STATUS_CONFIRMED:
                raise ValidationError(
                    "Non puoi cambiare il numero di persone di un appuntamento annullato"
                )
            treatment = self._find(self.treatments, anchor["treatment_id"], "Trattamento")
            if self._treatment_requires_operator(treatment):
                raise ValidationError(
                    f"'{treatment['name']}' e' un trattamento individuale: "
                    "non ha un numero di persone da cambiare"
                )

            min_parallel = _norm_parallel(treatment.get("min_parallel"))
            max_parallel = _norm_parallel(treatment.get("max_parallel"))
            if min_parallel and wanted < min_parallel:
                raise ValidationError(
                    f"'{treatment['name']}' richiede almeno {min_parallel} "
                    f"persone insieme nella stessa fascia."
                )

            start = dt_util.parse_datetime(anchor["start"])
            end = dt_util.parse_datetime(anchor["end"])
            siblings = sorted(
                self._group_siblings(anchor),
                key=lambda item: (str(item.get("created_at")), item["id"]),
            )
            current = 1 + len(siblings)

            if max_parallel:
                # Everybody already in that slot counts, whoever booked them:
                # the cap is about the room, not about this client.
                already = 0
                for other in self.appointments:
                    if not occupies_slot(other):
                        continue
                    if other["treatment_id"] != treatment["id"]:
                        continue
                    other_start = dt_util.parse_datetime(other["start"])
                    other_end = dt_util.parse_datetime(other["end"])
                    if (
                        other_start
                        and other_end
                        and other_start < end
                        and other_end > start
                    ):
                        already += 1
                if wanted > max_parallel:
                    raise ValidationError(
                        f"'{treatment['name']}' ha capienza massima di "
                        f"{max_parallel} persone insieme (già {already})."
                    )

            if wanted == current:
                return {
                    "appointment": self.appointment_payload(anchor),
                    "persons": current,
                    "created": 0,
                    "cancelled": 0,
                }

            added: list[tuple[dict[str, Any], dict[str, Any], bool]] = []
            to_cancel = siblings[wanted - 1:] if wanted < current else []

            # Everything is prepared before a single record is written, so a
            # refusal leaves the group untouched.
            for offset in range(max(0, wanted - current)):
                new_appointment, client, is_new = self._prepare_booking(
                    treatment_id=treatment["id"],
                    start=start,
                    client_id=anchor["client_id"],
                    operator_id=anchor.get("operator_id"),
                    notes=anchor.get("notes", ""),
                    # The anchor is the person the card is named after; the
                    # ones added here are her guests, one number each.
                    person_index=current + offset,
                    batch_id=anchor.get("batch_id"),
                )
                added.append((new_appointment, client, is_new))

            for appointment, client, is_new in added:
                if is_new:
                    self.clients.append(client)
                self.appointments.append(appointment)

            reason = f"Gruppo ridotto a {wanted} persone"
            for appointment in to_cancel:
                appointment["status"] = STATUS_CANCELLED
                appointment["cancel_reason"] = reason
                appointment["cancelled_at"] = dt_util.utcnow().isoformat()

            if added or to_cancel:
                await self._async_save()

        return {
            "appointment": self.appointment_payload(anchor),
            "persons": wanted,
            "created": len(added),
            "cancelled": len(to_cancel),
        }

    async def async_create_bookings(
        self, rows: list[dict[str, Any]], user_id: str | None = None, defer_operator: bool = False
    ) -> dict[str, Any]:
        """Create every appointment of a multi-row booking, or none of them.

        One row is one treatment, and each entry of a row is one person: her
        own time slot and, for a massage, her own masseuse. Every row is
        validated first, so a clash on the third person never leaves the first
        two booked. The entry can say which person of the party it is, which is
        what lets two people of one party share an hour on the leader's card
        while the same person twice is still refused.

        ``defer_operator`` books a treatment that needs a masseuse without one
        and without starting an offer, for a request the desk confirms before
        deciding who takes it.
        """
        if not rows:
            raise ValidationError("Nessun trattamento da prenotare")

        # One flag for the whole batch: a group is confirmed or it is waiting,
        # person by person would leave half a party waiting and half not.
        pending = bool(rows[0].get("pending"))
        if any(bool(row.get("pending")) != pending for row in rows):
            raise ValidationError(
                "La prenotazione multipla deve essere tutta confermata "
                "o tutta in attesa: ogni riga chiede una cosa diversa."
            )

        batch_id = _new_id("batch")
        staged_clients: list[dict[str, Any]] = []
        planned: list[dict[str, Any]] = []
        prepared: list[tuple[dict[str, Any], dict[str, Any], bool]] = []

        # Total entries per treatment across the whole batch, so min_parallel
        # can be checked against the full group and not just the entries
        # prepared before the current one.
        batch_totals: dict[str, int] = {}
        for row in rows:
            treatment_id = str(row.get("treatment_id") or "")
            entries = row.get("entries")
            if not isinstance(entries, list) or not entries:
                raise ValidationError(
                    "Ogni riga di prenotazione deve avere almeno una persona"
                )
            batch_totals[treatment_id] = batch_totals.get(treatment_id, 0) + len(entries)

        async with self._lock:
            # Store user_id for _prepare_booking to use.
            self._current_user_id = user_id
            try:
                for row in rows:
                    treatment_id = str(row.get("treatment_id") or "")
                    # One flag for the whole row, like the pending one: the party
                    # is from outside together or from the hotel together.
                    guest_type = _norm_guest_type(row.get("guest_type"))
                    entries = row.get("entries")
                    for entry in entries:
                        if not isinstance(entry, dict):
                            raise ValidationError("Voce di prenotazione non valida")
                        if not entry.get("start"):
                            raise ValidationError("Manca la fascia oraria")
                        appointment, client, is_new = self._prepare_booking(
                            treatment_id=treatment_id,
                            start=entry["start"],
                            client_id=entry.get("client_id"),
                            first_name=str(entry.get("first_name") or ""),
                            last_name=str(entry.get("last_name") or ""),
                            phone=str(entry.get("phone") or ""),
                            email=str(entry.get("email") or ""),
                            client_notes=str(entry.get("client_notes") or ""),
                            operator_id=entry.get("operator_id"),
                            operator_ids=entry.get("operator_ids"),
                            notes=str(entry.get("notes") or ""),
                            payment=entry.get("payment"),
                            pending=pending,
                            guest_type=guest_type,
                            extras=entry.get("extras"),
                            list_price=entry.get("list_price"),
                            price=entry.get("price"),
                            force_client_overlap=bool(entry.get("force_client_overlap")),
                            staged_clients=staged_clients,
                            planned=planned,
                            batch_totals=batch_totals,
                            force_new=bool(entry.get("force_new")),
                            # Which person of the party this entry is. The card
                            # always says it; a caller that leaves it out is given
                            # the older rule, where the card is all there is.
                            person_index=(
                                None
                                if entry.get("person") is None
                                else _norm_person(entry.get("person"))
                            ),
                            defer_operator=defer_operator,
                            batch_id=batch_id,
                        )
                        if is_new and not any(
                            staged["id"] == client["id"] for staged in staged_clients
                        ):
                            staged_clients.append(client)
                        planned.append(appointment)
                        prepared.append((appointment, client, is_new))

                voucher = self._voucher_of_rows(rows)
                if voucher is not None:
                    self._check_voucher_rows(voucher, rows)

                # A code can instead be a loyalty voucher ("Voucher fedelta"):
                # it is redeemed once, on the first booking that uses it.
                promo = self._promo_voucher_of_rows(rows)

                # Everything validated: commit once.
                for appointment, client, is_new in prepared:
                    if is_new:
                        self.clients.append(client)
                self.appointments.extend(item[0] for item in prepared)
                if voucher is not None:
                    voucher["status"] = VOUCHER_REDEEMED
                    voucher["redeemed_at"] = dt_util.utcnow().isoformat()
                    voucher["appointment_ids"] = [item[0]["id"] for item in prepared]
                if promo is not None:
                    promo["status"] = PROMO_VOUCHER_REDEEMED
                    promo["redeemed_at"] = dt_util.utcnow().isoformat()
                await self._async_save()
            finally:
                # Clear the user_id.
                self._current_user_id = None

        payloads = [await self._async_announce(item[0]) for item in prepared]
        return {"appointments": payloads, "count": len(payloads)}

    def voucher_payload(self, voucher: dict[str, Any]) -> dict[str, Any]:
        """Return a voucher with its derived expiry flag."""
        expires = _norm_date(voucher.get("expires_on"))
        expired = bool(expires) and dt_util.now().date() > datetime.strptime(
            expires, "%Y-%m-%d"
        ).date()
        return {**copy.deepcopy(voucher), "expired": expired}

    def _voucher_of_rows(self, rows: list[dict[str, Any]]) -> dict[str, Any] | None:
        """The gift voucher the booking redeems, or None for an ordinary booking.

        A code that matches no gift voucher is an outside voucher, as before, and
        is simply recorded. A code that matches one must be usable right now.
        """
        codes = {
            str((entry.get("payment") or {}).get("voucher_code") or "").strip().upper()
            for row in rows
            for entry in row.get("entries") or []
            if isinstance(entry, dict)
        } - {""}
        if not codes:
            return None
        if len(codes) > 1:
            raise ValidationError("Una prenotazione riscatta un solo voucher")
        code = codes.pop()
        voucher = next((v for v in self.vouchers if v["code"] == code), None)
        if voucher is None:
            return None
        if voucher["status"] == VOUCHER_REDEEMED:
            raise ValidationError(f"Il voucher {code} è già stato riscattato")
        expires = _norm_date(voucher.get("expires_on"))
        if expires and dt_util.now().date() > datetime.strptime(expires, "%Y-%m-%d").date():
            raise ValidationError(f"Il voucher {code} è scaduto")
        return voucher

    def _check_voucher_rows(self, voucher: dict[str, Any], rows: list[dict[str, Any]]) -> None:
        """The booking must match the voucher person by person, treatment by treatment."""
        booked: dict[int, list[str]] = {}
        for row in rows:
            for entry in row.get("entries") or []:
                person = int(entry.get("person") or 0)
                booked.setdefault(person, []).append(str(row.get("treatment_id") or ""))
        wanted = [sorted(p["treatment_ids"]) for p in voucher["people"]]
        got = [sorted(ids) for ids in booked.values()]
        if sorted(wanted) != sorted(got):
            raise ValidationError(
                f"La prenotazione non corrisponde al voucher {voucher['code']}: "
                "stesse persone e stessi trattamenti"
            )

    def _promo_voucher_of_rows(self, rows: list[dict[str, Any]]) -> dict[str, Any] | None:
        """The loyalty voucher the booking redeems, or None.

        A code matching no loyalty voucher is ignored here: it may be a gift
        voucher (handled above) or an outside code the desk typed. A matching
        one must be usable right now: not already redeemed, not expired.
        """
        codes = {
            str(entry.get("voucher_code") or "").strip().upper()
            for row in rows
            for entry in row.get("entries") or []
            if isinstance(entry, dict)
            and str(entry.get("voucher_code") or "").strip()
        }
        if not codes:
            return None
        if len(codes) > 1:
            raise ValidationError("Una prenotazione riscatta un solo voucher")
        code = codes.pop()
        voucher = next((v for v in self.promo_vouchers if v["code"] == code), None)
        if voucher is None:
            return None
        if voucher["status"] == PROMO_VOUCHER_REDEEMED:
            raise ValidationError(f"Il voucher {code} è già stato riscattato")
        expires = _norm_date(voucher.get("expires_on"))
        if expires and dt_util.now().date() > datetime.strptime(
            expires, "%Y-%m-%d"
        ).date():
            raise ValidationError(f"Il voucher {code} è scaduto")
        return voucher

    async def async_create_voucher(
        self,
        buyer_name: str,
        buyer_phone: str,
        recipient_name: str,
        recipient_phone: str,
        people: list[dict[str, Any]],
        user_id: str | None = None,
    ) -> dict[str, Any]:
        """Sell a gift voucher: its code, its people and its treatments, valid for months."""
        known = {t["id"] for t in self.treatments}
        clean: list[dict[str, Any]] = []
        for person in people:
            ids = [str(t) for t in person.get("treatment_ids") or []]
            for treatment_id in ids:
                if treatment_id not in known:
                    raise ValidationError("Trattamento non valido nel voucher")
            gift_amount = person.get("gift_card_amount")
            if gift_amount is not None:
                try:
                    gift_amount = float(gift_amount)
                    if gift_amount < 0:
                        gift_amount = None
                except (TypeError, ValueError):
                    gift_amount = None
            clean.append(
                {
                    "name": str(person.get("name") or "").strip(),
                    "treatment_ids": ids,
                    "extras": [str(e) for e in person.get("extras") or [] if e],
                    "gift_card_amount": gift_amount,
                }
            )
        # Allow voucher with only gift cards (no treatments required if all have gift_card_amount).
        if not any(person["treatment_ids"] for person in clean) and not any(person["gift_card_amount"] for person in clean):
            raise ValidationError("Il voucher deve contenere almeno un trattamento o una gift card")
        async with self._lock:
            existing = {v["code"] for v in self.vouchers}
            code = _new_voucher_code(existing)
            today = dt_util.now().date()
            voucher = _norm_voucher(
                {
                    "id": f"vch_{secrets.token_hex(6)}",
                    "code": f"VCH-{code}",
                    "buyer_name": buyer_name,
                    "buyer_phone": buyer_phone,
                    "recipient_name": recipient_name,
                    "recipient_phone": recipient_phone,
                    "people": clean,
                    "created_at": dt_util.utcnow().isoformat(),
                    "created_by": user_id,
                    "expires_on": _add_months(today, VOUCHER_VALID_MONTHS).strftime("%Y-%m-%d"),
                    "status": VOUCHER_ACTIVE,
                }
            )
            self.vouchers.append(voucher)
            await self._async_save()
        return self.voucher_payload(voucher)

    async def async_extend_voucher(self, voucher_id: str, expires_on: str) -> dict[str, Any]:
        """Give a voucher a new expiry date, with no limit on how far it goes."""
        new_date = _norm_date(expires_on)
        if not new_date:
            raise ValidationError("Data di scadenza non valida")
        async with self._lock:
            voucher = self._find(self.vouchers, voucher_id, "Voucher")
            voucher["expires_on"] = new_date
            await self._async_save()
        return self.voucher_payload(voucher)

    async def async_delete_voucher(self, voucher_id: str, user_id: str | None = None, is_admin: bool = False, is_owner: bool = False) -> dict[str, Any]:
        """Remove a voucher. Admin can delete redeemed vouchers."""
        async with self._lock:
            voucher = self._find(self.vouchers, voucher_id, "Voucher")
            if voucher["status"] == VOUCHER_REDEEMED:
                # Check if user is admin/owner (HA admin/owner or permissions map admin).
                if not user_id and not is_admin and not is_owner:
                    raise ValidationError("Un voucher già riscattato non si elimina")
                if not is_admin and not is_owner:
                    permissions = self._data[KEY_SETTINGS].get(KEY_PERMISSIONS) or {}
                    user_level = permissions.get(user_id, "none")
                    if user_level != "admin":
                        raise ValidationError("Solo un amministratore può eliminare un voucher già riscattato")
            self._data[KEY_VOUCHERS] = [v for v in self.vouchers if v["id"] != voucher_id]
            await self._async_save()
        return {"id": voucher_id}

    # ------------------------------------------------------- loyalty vouchers

    def promo_voucher_payload(self, voucher: dict[str, Any]) -> dict[str, Any]:
        """Return a loyalty voucher with its derived expiry flag."""
        expires = _norm_date(voucher.get("expires_on"))
        expired = bool(expires) and dt_util.now().date() > datetime.strptime(
            expires, "%Y-%m-%d"
        ).date()
        return {**copy.deepcopy(voucher), "expired": expired}

    def _promo_voucher_of_client(self, client_id: str) -> list[dict[str, Any]]:
        """Every loyalty voucher awarded to one client, newest first."""
        rows = [v for v in self.promo_vouchers if v.get("client_id") == client_id]
        rows.sort(key=lambda v: str(v.get("created_at") or ""), reverse=True)
        return [self.promo_voucher_payload(v) for v in rows]

    async def async_redeem_promo_voucher(
        self, voucher_id: str
    ) -> dict[str, Any]:
        """Mark a loyalty voucher as used. It stays in the list, single use."""
        async with self._lock:
            voucher = self._find(self.promo_vouchers, voucher_id, "Voucher fedelta")
            if voucher["status"] == PROMO_VOUCHER_REDEEMED:
                raise ValidationError(
                    f"Il voucher {voucher['code']} è già stato riscattato"
                )
            voucher["status"] = PROMO_VOUCHER_REDEEMED
            voucher["redeemed_at"] = dt_util.utcnow().isoformat()
            await self._async_save()
        return self.promo_voucher_payload(voucher)

    async def async_delete_promo_voucher(self, voucher_id: str) -> dict[str, Any]:
        """Remove a loyalty voucher from the list."""
        async with self._lock:
            self._find(self.promo_vouchers, voucher_id, "Voucher fedelta")
            self._data[KEY_PROMO_VOUCHERS] = [
                v for v in self.promo_vouchers if v["id"] != voucher_id
            ]
            await self._async_save()
        return {"id": voucher_id}

    def format_promo_voucher(self, voucher: dict[str, Any]) -> str:
        """Return the thank-you message carrying a loyalty voucher code.

        The wording is the one saved in the Promo tab, so the reception changes
        it without touching code; an empty setting falls back to the built-in
        text. Placeholders: {nome}, {cognome}, {codice}, {sconto},
        {spesa_minima}, {scadenza}.
        """
        template = str(
            self._data[KEY_SETTINGS].get("promo_voucher_message") or ""
        ).strip() or DEFAULT_PROMO_VOUCHER_MESSAGE
        min_spend = _norm_count(
            voucher.get("min_spend"), 0, 100000, DEFAULT_PROMO_VOUCHER_MIN_SPEND
        )
        return (
            template.replace(
                "{nome}", str(voucher.get("first_name") or "").strip() or "ospite"
            )
            .replace("{cognome}", str(voucher.get("last_name") or "").strip())
            .replace("{codice}", str(voucher.get("code") or ""))
            .replace(
                "{sconto}",
                str(
                    _norm_count(
                        voucher.get("discount_percent"),
                        1,
                        100,
                        DEFAULT_PROMO_VOUCHER_DISCOUNT,
                    )
                ),
            )
            .replace("{spesa_minima}", f"{min_spend} €")
            .replace("{scadenza}", _date_it(voucher.get("expires_on") or ""))
        )

    async def async_assign_promo_voucher(
        self,
        appointment_id: str,
        client_id: str,
    ) -> dict[str, Any]:
        """Create the loyalty voucher a check-out earns, ready for its message.

        The code is generated now and expires after ``promo_voucher_days``; the
        message is only scheduled (``send_at`` = now + ``promo_voucher_after_hours``)
        so a periodic tick sends it later. One check-out, one voucher: an
        appointment that already earned one is left alone.
        """
        client = self._find(self.clients, client_id, "Cliente")
        settings = self._data[KEY_SETTINGS]
        days = int(
            settings.get("promo_voucher_days") or DEFAULT_PROMO_VOUCHER_DAYS
        )
        after_hours = _norm_count(
            settings.get("promo_voucher_after_hours"),
            0,
            720,
            DEFAULT_PROMO_VOUCHER_AFTER_HOURS,
        )
        async with self._lock:
            existing = {v["code"] for v in self.promo_vouchers}
            already = next(
                (
                    v
                    for v in self.promo_vouchers
                    if v.get("appointment_id") == appointment_id
                ),
                None,
            )
            if already is not None:
                return self.promo_voucher_payload(already)
            now = dt_util.utcnow()
            voucher = _norm_promo_voucher(
                {
                    "id": f"fid_{secrets.token_hex(6)}",
                    "code": _new_promo_voucher_code(existing),
                    "client_id": client_id,
                    "first_name": str(client.get("first_name") or "").strip(),
                    "last_name": str(client.get("last_name") or "").strip(),
                    "phone": str(client.get("phone") or "").strip(),
                    "discount_percent": settings.get("promo_voucher_discount"),
                    "min_spend": settings.get("promo_voucher_min_spend"),
                    "max_spend": settings.get("promo_voucher_max_spend"),
                    "created_at": now.isoformat(),
                    "send_at": (now + timedelta(hours=after_hours)).isoformat(),
                    "expires_on": (
                        dt_util.now().date() + timedelta(days=days)
                    ).strftime("%Y-%m-%d"),
                    "status": PROMO_VOUCHER_PENDING,
                    "appointment_id": appointment_id,
                }
            )
            self.promo_vouchers.append(voucher)
            await self._async_save()
        return self.promo_voucher_payload(voucher)

    async def async_send_promo_vouchers(self) -> dict[str, Any]:
        """Send every loyalty-voucher message that has come due, once each.

        A voucher is sent when its ``send_at`` has passed and it is still
        pending. A failure leaves it pending, so the next tick retries it; a
        successful send marks it ``sent`` and stamps ``sent_at``. A voucher
        with no usable phone is marked sent without a message: there is nothing
        to retry and it should not pile up in the pending queue.
        """
        now = dt_util.utcnow()
        sent = 0
        failed = 0
        skipped = 0
        async with self._lock:
            for voucher in self.promo_vouchers:
                if voucher.get("status") != PROMO_VOUCHER_PENDING:
                    continue
                due = dt_util.parse_datetime(str(voucher.get("send_at") or ""))
                if due is not None and due > now:
                    continue
                phone = str(voucher.get("phone") or "").strip()
                chat_id = messaging.whatsapp_chat_id(phone)
                if not chat_id:
                    voucher["status"] = PROMO_VOUCHER_SENT
                    voucher["sent_at"] = now.isoformat()
                    skipped += 1
                    continue
                try:
                    result = await messaging.async_send_whatsapp(
                        self.hass,
                        chat_id,
                        self.format_promo_voucher(voucher),
                        waha=self.waha,
                    )
                except Exception as err:  # noqa: BLE001
                    failed += 1
                    _LOGGER.warning(
                        "Voucher fedelta %s non inviato a %s: %s",
                        voucher.get("code") or "?",
                        phone or "?",
                        err,
                    )
                    continue
                if result.get("sent"):
                    voucher["status"] = PROMO_VOUCHER_SENT
                    voucher["sent_at"] = now.isoformat()
                    sent += 1
                else:
                    failed += 1
                    _LOGGER.warning(
                        "Voucher fedelta %s non inviato a %s: %s",
                        voucher.get("code") or "?",
                        phone or "?",
                        result.get("error") or "errore sconosciuto",
                    )
            if sent or skipped:
                await self._async_save()
        return {"sent": sent, "failed": failed, "skipped": skipped}

    async def async_cleanup_promo_vouchers(self) -> dict[str, Any]:
        """Delete loyalty vouchers that expired without ever being used.

        A pending or sent voucher past its expiry is removed; a redeemed one is
        kept, because it is the record of a sale the client already made. Run on
        a timer alongside the send.
        """
        today = dt_util.now().date()
        removed = 0
        async with self._lock:
            kept: list[dict[str, Any]] = []
            for voucher in self.promo_vouchers:
                if voucher.get("status") == PROMO_VOUCHER_REDEEMED:
                    kept.append(voucher)
                    continue
                expires = _norm_date(voucher.get("expires_on"))
                if expires and today > datetime.strptime(expires, "%Y-%m-%d").date():
                    removed += 1
                    continue
                kept.append(voucher)
            if removed:
                self._data[KEY_PROMO_VOUCHERS] = kept
                await self._async_save()
        return {"removed": removed}

    async def async_promo_voucher_tick(self) -> dict[str, Any]:
        """The periodic job: send what is due and drop what expired unused."""
        sent = await self.async_send_promo_vouchers()
        cleaned = await self.async_cleanup_promo_vouchers()
        pending = sum(
            1
            for v in self.promo_vouchers
            if v.get("status") == PROMO_VOUCHER_PENDING
        )
        return {**sent, **cleaned, "pending": pending, "total": len(self.promo_vouchers)}

    # ------------------------------------------------------------------
    # appointment requests (Richieste)
    # ------------------------------------------------------------------
    def request_payload(self, request: dict[str, Any]) -> dict[str, Any]:
        """Return a request enriched with the client and the treatment names.

        A request stores ids only, exactly like an appointment; the card reads
        the names and the formatted date from here, so it never has to join the
        two collections itself.
        """
        client = next(
            (c for c in self.clients if c["id"] == request.get("client_id")), None
        )
        entries: list[dict[str, Any]] = []
        for entry in request.get("entries") or []:
            treatment = next(
                (t for t in self.treatments if t["id"] == entry.get("treatment_id")),
                None,
            )
            entries.append(
                {
                    **entry,
                    "treatment_name": (
                        treatment["name"] if treatment else "Trattamento eliminato"
                    ),
                    "duration_min": treatment["duration_min"] if treatment else None,
                    "price": treatment["price"] if treatment else None,
                }
            )
        return {
            **copy.deepcopy(request),
            "client": (
                {
                    "id": client["id"],
                    "first_name": client["first_name"],
                    "last_name": client["last_name"],
                    "full_name": self.full_name(client),
                    "phone": client["phone"],
                    "email": client["email"],
                }
                if client
                else {
                    "id": "",
                    "first_name": "",
                    "last_name": "",
                    "full_name": "Cliente eliminato",
                    "phone": "",
                    "email": "",
                }
            ),
            "entries": entries,
            "date_it": _date_it(str(request.get("date") or "")),
            # The card and the message both ask this one question, so neither
            # has to know the statuses by name.
            "is_confirmed": request.get("status") == REQUEST_CONFIRMED,
        }

    def _request_rows(self, request: dict[str, Any]) -> list[dict[str, Any]]:
        """Turn a request into the rows ``create_bookings`` expects.

        Every treatment the guest asked for becomes one row; each of the N
        persons becomes an entry of that row — same hour, same accessories — on
        the one shared client card. No operator is named: the desk assigns her
        from the agenda when she confirms, so the booking is created with
        ``defer_operator`` and no offer goes out.
        """
        day = str(request.get("date") or "")
        rows: list[dict[str, Any]] = []
        for entry in request.get("entries") or []:
            clock = str(entry.get("time") or "00:00")
            rows.append(
                {
                    "treatment_id": entry["treatment_id"],
                    "entries": [
                        {
                            "start": f"{day}T{clock}:00",
                            "client_id": request["client_id"],
                            "person": person,
                            "extras": entry.get("extras") or [],
                        }
                        for person in range(int(request.get("people") or 1))
                    ],
                    "pending": False,
                    "guest_type": request.get("guest_type") or GUEST_TYPE_DEFAULT,
                }
            )
        return rows

    async def async_update_booking_batch(
        self,
        anchor_id: str,
        rows: list[dict[str, Any]],
        user_id: str | None = None,
    ) -> dict[str, Any]:
        """Modify every appointment of a batch as one transaction.

        ``rows`` is a flat list describing the desired appointments; each row
        may carry ``appointment_id`` for an appointment that already belongs to
        the batch. An appointment present in ``rows`` is rebuilt in place
        (same id, same 5-char code, same check-in/out and confirmation trail;
        its payments are preserved unless the row brings its own ``payment``
        block). A row without a matching id creates a new appointment. Every
        original batch member not present in ``rows`` is marked cancelled,
        which keeps its history and registered payments legible. Everything
        is validated before anything is written, so a refusal leaves the
        original batch untouched.
        """
        if not isinstance(rows, list) or not rows:
            raise ValidationError("Nessun appuntamento da modificare")
        anchor = self._find(self.appointments, anchor_id, "Appuntamento")
        async with self._lock:
            batch_id = anchor.get("batch_id") or _new_id("batch")
            existing = [a for a in self.appointments if a.get("batch_id") == batch_id]
            id_map = {a["id"]: a for a in existing}

            # Take the originals out so a rebuilt row never overlaps itself.
            for a in existing:
                if a in self.appointments:
                    self.appointments.remove(a)

            self._current_user_id = user_id
            prepared: list[tuple[dict[str, Any], dict[str, Any], bool]] = []
            kept_ids: set[str] = set()
            try:
                for raw_row in rows:
                    if not isinstance(raw_row, dict):
                        raise ValidationError("Voce batch non valida")
                    row = dict(raw_row)
                    rid = str(row.get("appointment_id") or "").strip() or None
                    existing_appt = id_map.get(rid) if rid else None

                    treatment_id = str(
                        row.get("treatment_id")
                        or (existing_appt.get("treatment_id") if existing_appt else "")
                        or ""
                    ).strip()
                    if not treatment_id:
                        raise ValidationError("Trattamento mancante nella riga batch")

                    start = row.get("start")
                    if start is None and existing_appt is not None:
                        start = existing_appt.get("start")
                    if not start:
                        raise ValidationError("Manca la fascia oraria nella riga batch")

                    client_id = row.get("client_id")
                    if client_id is None and existing_appt is not None:
                        client_id = existing_appt.get("client_id")
                    first_name = row.get("first_name")
                    if first_name is None and existing_appt is not None:
                        client = self.get_client(existing_appt["client_id"]) if existing_appt.get("client_id") else None
                        first_name = client.get("first_name", "") if client else ""
                    last_name = row.get("last_name")
                    if last_name is None and existing_appt is not None:
                        client = self.get_client(existing_appt["client_id"]) if existing_appt.get("client_id") else None
                        last_name = client.get("last_name", "") if client else ""
                    phone = row.get("phone")
                    if phone is None and existing_appt is not None:
                        client = self.get_client(existing_appt["client_id"]) if existing_appt.get("client_id") else None
                        phone = client.get("phone", "") if client else ""
                    email = row.get("email")
                    if email is None and existing_appt is not None:
                        client = self.get_client(existing_appt["client_id"]) if existing_appt.get("client_id") else None
                        email = client.get("email", "") if client else ""
                    client_notes = row.get("client_notes")
                    if client_notes is None and existing_appt is not None:
                        client = self.get_client(existing_appt["client_id"]) if existing_appt.get("client_id") else None
                        client_notes = (client or {}).get("notes", "")

                    notes = row.get("notes")
                    if notes is None and existing_appt is not None:
                        notes = existing_appt.get("notes", "")
                    notes = "" if notes is None else str(notes)

                    operator_id = row.get("operator_id")
                    if operator_id is None and existing_appt is not None:
                        operator_id = existing_appt.get("operator_id")

                    operator_ids = row.get("operator_ids")
                    if operator_ids is None and existing_appt is not None:
                        operator_ids = existing_appt.get("offer_candidates")

                    extras = row.get("extras")
                    if extras is None and existing_appt is not None:
                        extras = existing_appt.get("extras")

                    guest_type = row.get("guest_type")
                    if guest_type is None and existing_appt is not None:
                        guest_type = existing_appt.get("guest_type")

                    pending = row.get("pending")
                    if pending is None and existing_appt is not None:
                        pending = existing_appt.get("status") == STATUS_PENDING
                    pending = bool(pending) if pending is not None else False

                    list_price = row.get("list_price")
                    if list_price is None and existing_appt is not None:
                        list_price = existing_appt.get("list_price")
                    price = row.get("price")
                    if price is None and existing_appt is not None:
                        price = existing_appt.get("price")

                    payment = row.get("payment", None)
                    if payment is None and existing_appt is not None:
                        # Preserve the payment detail already on the appointment.
                        payment = {
                            "paid": bool(existing_appt.get("paid", False)),
                            "paid_amount": existing_appt.get("paid_amount", 0.0),
                            "deposit": bool(existing_appt.get("deposit", False)),
                            "deposit_amount": existing_appt.get("deposit_amount", 0.0),
                            "voucher": bool(existing_appt.get("voucher", False)),
                            "voucher_code": existing_appt.get("voucher_code", ""),
                            "balance_due": bool(existing_appt.get("balance_due", False)),
                            "balance_due_amount": existing_appt.get("balance_due_amount", 0.0),
                            "methods": list(existing_appt.get("methods") or []),
                        }

                    force_new = bool(row.get("force_new", False))
                    person_index = row.get("person", None)

                    # Keep the selected id stable when rebuilding.
                    if existing_appt is not None:
                        row = {**row, "id": existing_appt["id"]}

                    appointment, client, is_new = self._prepare_booking(
                        treatment_id=treatment_id,
                        start=start,
                        client_id=client_id,
                        first_name=first_name or "",
                        last_name=last_name or "",
                        phone=phone or "",
                        email=email or "",
                        client_notes=client_notes or "",
                        operator_id=operator_id,
                        operator_ids=operator_ids,
                        notes=notes,
                        payment=payment,
                        pending=pending,
                        guest_type=guest_type or GUEST_TYPE_DEFAULT,
                        extras=extras,
                        list_price=list_price,
                        price=price,
                        force_client_overlap=bool(row.get("force_client_overlap", False)),
                        force_new=force_new,
                        person_index=person_index,
                        batch_id=batch_id,
                    )
                    # Preserve history on rebuild.
                    if existing_appt is not None:
                        appointment["id"] = existing_appt["id"]
                        appointment["code"] = existing_appt.get("code") or appointment.get("code")
                        appointment["created_at"] = existing_appt.get("created_at") or appointment.get("created_at")
                        appointment["created_by"] = existing_appt.get("created_by", appointment.get("created_by"))
                        appointment["payments"] = _norm_payment_list(existing_appt.get("payments"))
                        appointment["checked_in"] = existing_appt.get("checked_in", False)
                        appointment["checked_in_at"] = existing_appt.get("checked_in_at", "")
                        appointment["checked_out"] = existing_appt.get("checked_out", False)
                        appointment["checked_out_at"] = existing_appt.get("checked_out_at", "")
                        appointment["confirmed_by"] = existing_appt.get("confirmed_by", "")
                        appointment["confirmed_at"] = existing_appt.get("confirmed_at", "")
                        appointment["offer_state"] = existing_appt.get("offer_state", OFFER_NONE)
                        appointment["offer_candidates"] = list(existing_appt.get("offer_candidates") or [])
                        appointment["offer_index"] = existing_appt.get("offer_index", 0)
                        appointment["offer_expires_at"] = existing_appt.get("offer_expires_at", "")
                        appointment["reminder_sent"] = existing_appt.get("reminder_sent", False)
                        appointment["review_request_sent"] = existing_appt.get("review_request_sent", False)
                        appointment["deposit_request_sent"] = existing_appt.get("deposit_request_sent", False)
                        kept_ids.add(existing_appt["id"])

                    # Clients handled below; no-op placeholder
                    prepared.append((appointment, client, is_new))

                # Commit new clients.
                created_clients = []
                for appointment, client, is_new in prepared:
                    if is_new and client["id"] not in {c["id"] for c in created_clients}:
                        self.clients.append(client)
                        created_clients.append(client)
                self.appointments.extend(item[0] for item in prepared)

                # Cancel the originals that were not kept.
                for orig in existing:
                    if orig["id"] in kept_ids:
                        continue
                    clone = copy.deepcopy(orig)
                    clone["status"] = STATUS_CANCELLED
                    clone["cancelled_at"] = dt_util.utcnow().isoformat()
                    clone["batch_id"] = batch_id
                    self.appointments.append(clone)

                voucher = None
                if any(r.get("voucher_code") for r in rows if isinstance(r, dict)):
                    # Preserve voucher redemption accounting from the anchor
                    voucher = None
                await self._async_save()
            except Exception:
                # Restore the originals exactly as they were.
                self.appointments.extend(existing)
                raise
            finally:
                self._current_user_id = None

        rebuilt_ids = [item[0]["id"] for item in prepared]
        return {
            "batch_id": batch_id,
            "appointments": [self.appointment_payload(a) for a in prepared],
            "kept": sorted(kept_ids),
            "cancelled": sorted({a["id"] for a in existing} - kept_ids),
        }

    async def async_create_request(
        self,
        *,
        client_id: str | None = None,
        first_name: str = "",
        last_name: str = "",
        phone: str = "",
        email: str = "",
        client_notes: str = "",
        force_new: bool = False,
        date: str = "",
        people: int = 1,
        entries: list[dict[str, Any]] | None = None,
        notes: str = "",
        voucher_code: str = "",
        guest_type: str = GUEST_TYPE_DEFAULT,
        user_id: str | None = None,
        source: str = REQUEST_SOURCE_DESK,
    ) -> dict[str, Any]:
        """Take a guest's appointment request and acknowledge it on WhatsApp.

        A request is lighter than a booking on purpose: it holds no slot, so it
        is not checked against the agenda — the desk only wrote down what the
        guest asked for. What is checked is that the request is answerable at
        all: a real date, at least one active treatment with a time, and the
        guest's own card (created or filled, never duplicated by phone).

        The acknowledgement to the guest is a best effort: the request is
        already saved when it goes out, and a messaging failure is logged rather
        than raised, so the desk never loses what the guest asked for.

        ``source`` is where the request was taken: the reception desk, or the
        hotel website. A web request starts unseen, which is what lights the
        bell in the card header; a desk request is born seen, because the
        person typing it is already looking at the card.

        ``voucher_code`` is the gift voucher the guest mentioned, if any. A
        code that matches a stored voucher must be usable right now, so the
        guest learns on the spot that it was already redeemed or has expired;
        a code that matches nothing is recorded as it is, for the desk to
        check, exactly like an outside voucher on a booking.
        """
        day = _norm_date(date)
        if not day:
            raise ValidationError("Indica una data valida per la richiesta")

        known = {t["id"] for t in self.treatments}
        active = {t["id"] for t in self.treatments if t["active"]}
        clean: list[dict[str, Any]] = []
        for entry in entries or []:
            if not isinstance(entry, dict):
                continue
            treatment_id = str(entry.get("treatment_id") or "").strip()
            if treatment_id not in known:
                raise ValidationError("Trattamento non valido nella richiesta")
            if treatment_id not in active:
                raise ValidationError("Uno dei trattamenti richiesti non è attivo")
            clock = _norm_clock(entry.get("time"))
            if not clock:
                raise ValidationError("Indica l'ora di ogni trattamento richiesto")
            clean.append(
                {
                    "treatment_id": treatment_id,
                    "time": clock,
                    "extras": _norm_extras(
                        entry.get("extras"), known=self._accessory_ids()
                    ),
                }
            )
        if not clean:
            raise ValidationError("Aggiungi almeno un trattamento alla richiesta")

        # A voucher the guest typed: if it is one of ours it must still be
        # usable, otherwise the guest would learn only days later, on the
        # phone. An unknown code is kept as typed for the desk to check.
        code = str(voucher_code or "").strip().upper()[:32]
        if code:
            voucher = next((v for v in self.vouchers if v["code"] == code), None)
            if voucher is not None:
                if voucher["status"] == VOUCHER_REDEEMED:
                    raise ValidationError(f"Il voucher {code} è già stato riscattato")
                expires = _norm_date(voucher.get("expires_on"))
                if expires and dt_util.now().date() > datetime.strptime(
                    expires, "%Y-%m-%d"
                ).date():
                    raise ValidationError(f"Il voucher {code} è scaduto")

        try:
            people = max(1, int(people or 1))
        except (TypeError, ValueError):
            people = 1

        async with self._lock:
            client = self._resolve_client(
                client_id,
                first_name,
                last_name,
                phone,
                email,
                client_notes,
                update_existing=True,
                force_new=force_new,
            )
            if not any(existing["id"] == client["id"] for existing in self.clients):
                self.clients.append(client)
            codes = {r["code"] for r in self.requests if r.get("code")}
            request = _norm_request(
                {
                    "id": _new_id("req"),
                    "code": _new_code(codes),
                    "client_id": client["id"],
                    "date": day,
                    "people": people,
                    "entries": clean,
                    "notes": notes,
                    "voucher_code": code,
                    "guest_type": _norm_guest_type(guest_type),
                    "status": REQUEST_PENDING,
                    "source": (
                        REQUEST_SOURCE_WEB
                        if source == REQUEST_SOURCE_WEB
                        else REQUEST_SOURCE_DESK
                    ),
                    # A web request is the one nobody saw being taken: it starts
                    # unseen so the bell rings. A desk request is born seen —
                    # the person typing it is already looking at the card.
                    "seen": source != REQUEST_SOURCE_WEB,
                    "created_at": dt_util.utcnow().isoformat(),
                    "created_by": user_id,
                }
            )
            self.requests.append(request)
            await self._async_save()

        await self._maybe_send_request_message(request)
        await self._notify_web_request(request)
        return self.request_payload(request)

    # ------------------------------------------------------- public booking API

    @property
    def _web_settings(self) -> dict[str, Any]:
        """The website settings, always present and always normalized."""
        return self._data[KEY_SETTINGS]

    @property
    def web_enabled(self) -> bool:
        """Whether the public website API is switched on from the card."""
        return bool(self._web_settings.get("web_enabled", DEFAULT_WEB_ENABLED))

    def _web_token(self) -> str:
        """Return the website token, generating the first one on demand.

        Generating lazily (rather than at setup) keeps a fresh install with
        the website off from carrying a token nobody has asked for yet; the
        card also generates one when the site is switched on, so the value to
        copy into the website is there before the first call arrives.
        """
        settings = self._web_settings
        token = str(settings.get("web_token") or "").strip()
        if not token:
            token = secrets.token_urlsafe(32)
            settings = dict(settings)
            settings["web_token"] = token
            self._data[KEY_SETTINGS] = _norm_settings(settings)
        return token

    def web_token_ok(self, provided: str) -> bool:
        """Whether ``provided`` is the website token, compared in constant time.

        The token is compared with ``hmac`` so the time taken does not leak
        how many leading characters were right. An empty configured token can
        never match: a setting cleared by hand must lock the site out, not
        open it.
        """
        expected = str(self._web_settings.get("web_token") or "").strip()
        if not expected or not provided:
            return False
        return hmac.compare_digest(expected, str(provided).strip())

    async def async_regenerate_public_token(self) -> dict[str, str]:
        """Issue a brand new website token, invalidating the previous one."""
        async with self._lock:
            settings = dict(self._web_settings)
            settings["web_token"] = secrets.token_urlsafe(32)
            self._data[KEY_SETTINGS] = _norm_settings(settings)
            await self._async_save()
        return {"token": self._web_settings["web_token"]}

    async def async_web_snippet(self) -> dict[str, Any]:
        """Return the code to paste into the site, with the token already in it.

        The base text is the published file in ``www/spa_booking`` — one
        source, the same one the desk can download — and the placeholder
        ``INCOLLA_QUI_IL_TOKEN`` is swapped for the current token on the fly.
        The token is never written to disk: it lives only in this answer and
        in the clipboard of whoever pressed Copia.
        """
        path = self.hass.config.path(
            "www", "spa_booking", "spa-booking-form.txt"
        )
        snippet = await self.hass.async_add_executor_job(_read_text, path)
        found = WEB_SNIPPET_TOKEN_PLACEHOLDER in snippet
        token = self._web_token() if snippet else ""
        return {
            "snippet": snippet.replace(WEB_SNIPPET_TOKEN_PLACEHOLDER, token),
            "token_placeholder": WEB_SNIPPET_TOKEN_PLACEHOLDER,
            "found": found,
            "path": path,
        }

    async def async_mark_requests_seen(self) -> dict[str, Any]:
        """Mark every web request as opened, clearing the bell.

        Only web requests carry the bell: a desk request is taken while
        somebody is already in the card, so counting it would make the bell a
        second, noisier copy of the Richieste tab.
        """
        async with self._lock:
            changed = 0
            for request in self.requests:
                if request.get("source") == REQUEST_SOURCE_WEB and not request.get(
                    "seen", True
                ):
                    request["seen"] = True
                    changed += 1
            if changed:
                await self._async_save()
            unread = sum(
                1
                for r in self.requests
                if r.get("source") == REQUEST_SOURCE_WEB
                and not r.get("seen", True)
            )
        return {"changed": changed, "unread": unread}

    def web_unread_count(self) -> int:
        """How many web requests the desk has not opened yet."""
        return sum(
            1
            for r in self.requests
            if r.get("source") == REQUEST_SOURCE_WEB and not r.get("seen", True)
        )

    async def async_public_availability(
        self, day: date, treatment_id: str
    ) -> dict[str, Any]:
        """Return the start times the website may offer for one treatment.

        The window (open/close/step) is the reception's, read from settings —
        it describes the day the site proposes, not the spa's real opening
        hours, which the desk changes whenever it likes. A break may cut that
        day in two (morning and afternoon), also read from settings: an empty
        break keeps the day whole.

        The treatment itself must be active and visible on the site: one the
        reception hid from the website is refused like a nonexistent one.

        A start is offered when the treatment can actually run there:

        * the whole treatment, plus its category's pause, fits before close;
        * no facility or category closure covers it (this is the same rule
          the booking engine applies — see ``_guard_closures``);
        * and either the treatment needs no operator, in which case its
          ``max_parallel`` capacity still has a place left, or at least one
          operator able to do it is free for the whole window.

        An operator is free when she is not closed, not blocked by a refused
        window, and has no overlapping appointment that holds its slot —
        exactly the three checks ``async_create_bookings`` performs before
        offering a slot, so the site and the card can never disagree.
        """
        settings = self._web_settings
        if not settings.get("web_enabled", DEFAULT_WEB_ENABLED):
            raise ValidationError("Il sito web è disattivato dalla Configurazione")
        if day < dt_util.now().date():
            raise ValidationError("Non è possibile richiedere date passate")
        ahead = int(settings.get("web_max_days_ahead") or DEFAULT_WEB_MAX_DAYS_AHEAD)
        if day > dt_util.now().date() + timedelta(days=ahead):
            raise ValidationError(
                f"La data è oltre i {ahead} giorni consentiti dal sito"
            )

        treatment = next(
            (t for t in self.treatments if t["id"] == treatment_id), None
        )
        if treatment is None:
            raise ValidationError("Trattamento non valido")
        if not treatment.get("active", True):
            raise ValidationError("Trattamento non attivo")
        if not treatment.get("web_visible", True):
            raise ValidationError("Trattamento non disponibile sul sito web")

        open_minutes = self._minutes_of(
            str(settings.get("web_open_time") or DEFAULT_WEB_OPEN_TIME)
        )
        close_minutes = self._minutes_of(
            str(settings.get("web_close_time") or DEFAULT_WEB_CLOSE_TIME)
        )
        if open_minutes < 0 or close_minutes <= open_minutes:
            raise ValidationError("Finestra oraria del sito non valida")
        # The break may split the day the site offers in two windows (morning
        # and afternoon). No break — the default — keeps the day whole, which
        # is exactly what the site offered before this existed.
        break_start = self._minutes_of(str(settings.get("web_break_start") or ""))
        break_end = self._minutes_of(str(settings.get("web_break_end") or ""))
        windows = [(open_minutes, close_minutes)]
        if break_start >= 0 or break_end >= 0:
            # Both clocks split the day in two (morning and afternoon). Only
            # one of them keeps the half that clock describes — the morning
            # when it is the closing one, the afternoon when it is the
            # opening one — so "only the morning" is simply a break that
            # closes it and nothing more.
            windows = []
            if break_start >= 0:
                windows.append((open_minutes, break_start))
            if break_end >= 0:
                windows.append((break_end, close_minutes))
            for window_open, window_close in windows:
                if window_close <= window_open:
                    raise ValidationError(
                        "Pausa del sito non valida: la chiusura della mattina "
                        "o l'apertura del pomeriggio sta fuori dall'orario"
                    )
            if len(windows) == 2 and windows[1][0] < windows[0][1]:
                raise ValidationError(
                    "Pausa del sito non valida: il pomeriggio deve aprirsi "
                    "dopo la chiusura della mattina"
                )
        step = int(settings.get("web_step_min") or DEFAULT_WEB_STEP_MIN)

        duration = int(treatment.get("duration_min") or 0)
        if duration <= 0:
            raise ValidationError("Trattamento senza durata valida")

        requires_operator = self._treatment_requires_operator(treatment)
        candidates = (
            self.operators_for_treatment(treatment["id"]) if requires_operator else []
        )
        # The pause after a booking of this category: the operator keeps her
        # break, so the next slot must leave room for it too.
        pause_minutes = self._treatment_pause_min(treatment)
        # A shared treatment (no operator) has a capacity instead of a person:
        # ``max_parallel`` is the very number ``_guard_parallel`` holds the
        # booking engine to, counted here against one extra guest.
        max_parallel = 0 if requires_operator else _norm_parallel(
            treatment.get("max_parallel")
        )

        day_start = dt_util.start_of_local_day(day)
        busy = [
            a
            for a in self.appointments
            if occupies_slot(a) and a.get("operator_id")
        ]
        shared_bookings = (
            [
                a
                for a in self.appointments
                if occupies_slot(a) and a["treatment_id"] == treatment["id"]
            ]
            if max_parallel
            else []
        )

        slots: list[dict[str, Any]] = []
        now = dt_util.now()

        # Every start the site may be offered, with the end of its own window:
        # a start of the morning is held by the morning, an afternoon one by
        # the afternoon, so a treatment never runs into the break.
        offered = [
            (minute, window_close)
            for window_open, window_close in windows
            for minute in range(window_open, window_close, step)
        ]
        for minute, window_close in offered:
            start = day_start + timedelta(minutes=minute)
            end = start + timedelta(minutes=duration)
            # Past, or too close to now to be worth offering: the site would
            # show a slot the desk cannot honour in time.
            if start <= now + timedelta(minutes=step):
                continue
            # The treatment plus its pause must fit before its window closes —
            # the same window rule the booking engine applies to a slot. With
            # a break this is what keeps a start from the morning running into
            # the afternoon.
            if minute + duration + pause_minutes > window_close:
                continue

            if self._closure_block_for(treatment, start, end):
                continue

            if requires_operator:
                free = bool(
                    self._free_operators(candidates, busy, start, end, pause_minutes)
                )
            elif not max_parallel:
                # 0 = no limit: the facility takes everybody, so only the
                # closure checked above can take the slot away.
                free = True
            else:
                # Same overlap test as _guard_parallel: start < other end and
                # other start < end, no pause — the facility itself is what
                # is shared, not a masseuse's break.
                taken = sum(
                    1
                    for appointment in shared_bookings
                    if (
                        other_start := dt_util.parse_datetime(appointment["start"])
                    )
                    and (other_end := dt_util.parse_datetime(appointment["end"]))
                    and other_start < end
                    and other_end > start
                )
                free = taken + 1 <= max_parallel

            if free:
                slots.append({"time": f"{minute // 60:02d}:{minute % 60:02d}"})
            if len(slots) >= WEB_MAX_SLOTS:
                break

        return {
            "date": day.isoformat(),
            "treatment_id": treatment_id,
            "treatment_name": treatment["name"],
            "duration_min": duration,
            "step_min": step,
            "open_time": f"{open_minutes // 60:02d}:{open_minutes % 60:02d}",
            "close_time": f"{close_minutes // 60:02d}:{close_minutes % 60:02d}",
            # The break, when the day is split: empty strings when it is not,
            # so the site can tell a whole day from a split one.
            "break_start": (
                f"{break_start // 60:02d}:{break_start % 60:02d}"
                if break_start >= 0
                else ""
            ),
            "break_end": (
                f"{break_end // 60:02d}:{break_end % 60:02d}"
                if break_end >= 0
                else ""
            ),
            "slots": slots,
        }

    def _closure_block_for(
        self, treatment: dict[str, Any], start: datetime, end: datetime
    ) -> bool:
        """Whether a facility or category closure covers this window.

        Mirrors ``_guard_closures`` without raising: the booking engine
        refuses a landing in a closure, so the website must not offer it.
        An operator closure is not checked here — it only removes one
        candidate, and ``_free_operators`` accounts for it.
        """
        for closure in self._closures_scope("facility"):
            if self._closure_covering(closure, start, end):
                return True
        category = self._category(treatment.get("category_id"))
        if category:
            for closure in self._closures_scope("category"):
                if closure["category_id"] == category["id"] and self._closure_covering(
                    closure, start, end
                ):
                    return True
        return False

    def _free_operators(
        self,
        candidates: list[dict[str, Any]],
        busy: list[dict[str, Any]],
        start: datetime,
        end: datetime,
        pause: int,
    ) -> list[str]:
        """The operators of ``candidates`` free for the whole window.

        The three refusals are the ones the booking engine applies: a closed
        operator, a refused window (slot block), and an overlapping booking
        that holds its slot. The pause after an existing appointment of the
        same category is added to its window, so the operator keeps her break.
        """
        closed = self._closed_operator_ids(start, end)
        free: list[str] = []
        for operator in candidates:
            operator_id = operator["id"]
            if operator_id in closed:
                continue
            if self._slot_blocked(operator_id, start, end):
                continue
            clash = False
            for appointment in busy:
                if appointment.get("operator_id") != operator_id:
                    continue
                other_start = dt_util.parse_datetime(appointment["start"])
                other_end = dt_util.parse_datetime(appointment["end"])
                if other_start is None or other_end is None:
                    continue
                other_end = other_end + timedelta(
                    minutes=self._pause_min_for(appointment)
                )
                if other_start < end and other_end > start:
                    clash = True
                    break
            if not clash:
                free.append(operator_id)
        return free

    async def async_delete_request(self, request_id: str) -> dict[str, Any]:
        """Drop a request the desk no longer needs.

        The appointments a confirmed request created are left alone: they are
        real bookings by then and are managed from the agenda.
        """
        async with self._lock:
            self._find(self.requests, request_id, "Richiesta")
            self._data[KEY_REQUESTS] = [
                request for request in self.requests if request["id"] != request_id
            ]
            await self._async_save()
        return {"id": request_id}

    async def async_confirm_request(self, request_id: str) -> dict[str, Any]:
        """Turn a request into real appointments and mark it confirmed.

        Every treatment becomes one appointment per person, on the shared client
        card, at the hour the guest asked for. The treatments that need a
        masseuse are booked without one and without starting an offer: the desk
        decides who takes them from the agenda. Nothing here is validated
        against the schedule twice — ``create_bookings`` refuses an overlap
        exactly as it does for a booking taken at the desk.
        """
        request = self._find(self.requests, request_id, "Richiesta")
        if request.get("status") == REQUEST_CONFIRMED and request.get(
            "appointment_ids"
        ):
            raise ValidationError("La richiesta è già stata confermata")
        if not (request.get("date") and request.get("entries")):
            raise ValidationError("La richiesta è incompleta")
        self._find(self.clients, request.get("client_id"), "Cliente")

        result = await self.async_create_bookings(
            self._request_rows(request), defer_operator=True
        )
        appointments = result.get("appointments") or []
        async with self._lock:
            request = self._find(self.requests, request_id, "Richiesta")
            request["status"] = REQUEST_CONFIRMED
            request["confirmed_at"] = dt_util.utcnow().isoformat()
            request["appointment_ids"] = [item["id"] for item in appointments]
            await self._async_save()
        return {
            "request": self.request_payload(request),
            "appointments": appointments,
            "count": len(appointments),
        }

    async def _maybe_send_request_message(self, request: dict[str, Any]) -> None:
        """Acknowledge a request on WhatsApp, when the guest left a number.

        Only a number that can receive a WhatsApp message is used; a request
        without one is simply kept. A failure is logged, never raised: the
        request is already saved and the desk can resend from the card.
        """
        payload = self.request_payload(request)
        phone = (payload.get("client") or {}).get("phone") or ""
        chat_id = messaging.whatsapp_chat_id(phone)
        if not chat_id:
            return
        message = self.format_request_message(payload)
        try:
            result = await messaging.async_send_whatsapp(
                self.hass, chat_id, message, waha=self.waha
            )
            sent = bool(result.get("sent"))
        except Exception as err:  # noqa: BLE001
            _LOGGER.warning(
                "Invio conferma richiesta a %s fallito: %s", phone or "?", err
            )
            return
        async with self._lock:
            request["message_sent"] = sent
            request["message_sent_at"] = (
                dt_util.utcnow().isoformat() if sent else ""
            )
            await self._async_save()

    async def _notify_web_request(self, request: dict[str, Any]) -> None:
        """Avvisa la reception su WhatsApp che è arrivata una richiesta dal sito.

        Solo per le richieste web: quelle prese al banco le ha scritte la
        reception stessa. Un numero non configurato, o un invio fallito, non
        cambia nulla per l'ospite — la richiesta è già salvata e resta in
        Lista richieste con la campanella accesa.
        """
        if request.get("source") != REQUEST_SOURCE_WEB:
            return
        target = str(self._web_settings.get("web_notify_whatsapp") or "").strip()
        if not target:
            return
        payload = self.request_payload(request)
        client = payload.get("client") or {}
        name = " ".join(
            part for part in (client.get("first_name"), client.get("last_name")) if part
        ).strip() or "ospite"
        phone = str(client.get("phone") or "").strip() or "senza telefono"
        day = payload.get("date") or ""
        when = self.format_day(day) if day else "data da definire"
        entries = payload.get("entries") or []
        slots = ", ".join(
            f"{entry.get('time') or '--:--'} {entry.get('treatment_name') or 'Trattamento'}"
            for entry in entries
        ) or "nessun trattamento"
        message = (
            "Nuova richiesta dal sito\n"
            f"{payload.get('code') or '—'} · {name} · {phone}\n"
            f"{when} · {slots}"
        )
        try:
            await messaging.async_send_whatsapp(
                self.hass, target, message, waha=self.waha
            )
        except Exception as err:  # noqa: BLE001
            _LOGGER.warning("Avviso richiesta web a %s fallito: %s", target, err)

    async def async_send_request_message(self, request_id: str) -> dict[str, Any]:
        """Resend a request's acknowledgement to the guest from the card."""
        async with self._lock:
            request = self._find(self.requests, request_id, "Richiesta")
            payload = self.request_payload(request)
            phone = (payload.get("client") or {}).get("phone") or ""
            chat_id = messaging.whatsapp_chat_id(phone)
            if not chat_id:
                raise ValidationError(
                    "Il richiedente non ha un telefono per WhatsApp"
                )
        message = self.format_request_message(payload)
        try:
            result = await messaging.async_send_whatsapp(
                self.hass, chat_id, message, waha=self.waha
            )
            sent = bool(result.get("sent"))
        except Exception as err:  # noqa: BLE001
            _LOGGER.warning(
                "Invio conferma richiesta a %s fallito: %s", phone or "?", err
            )
            return {"request_id": request_id, "sent": False, "error": str(err)}
        async with self._lock:
            request["message_sent"] = sent
            request["message_sent_at"] = (
                dt_util.utcnow().isoformat() if sent else ""
            )
            await self._async_save()
        return {"request_id": request_id, "sent": sent}

    def format_request_message(self, payload: dict[str, Any]) -> str:
        """Return the acknowledgement sent to a guest who left a request.

        The wording comes from the notifications tab, so the reception changes
        it without touching code; an empty setting falls back to the built-in
        text. ``{nome}`` becomes her first name, or "ospite" when the card has
        none, and ``{trattamenti}`` lists every treatment she asked for with its
        time, one per line.
        """
        template = str(self._data[KEY_SETTINGS].get("request_message") or "").strip()
        if not template:
            template = DEFAULT_REQUEST_MESSAGE
        client = payload.get("client") or {}
        entries = payload.get("entries") or []
        lines: list[str] = []
        first_time = ""
        for entry in entries:
            name = str(entry.get("treatment_name") or "Trattamento")
            clock = str(entry.get("time") or "")
            if clock and not first_time:
                first_time = clock
            lines.append(f"• {name} alle {clock}" if clock else f"• {name}")
        return (
            template.replace("{nome}", str(client.get("first_name") or "").strip() or "ospite")
            .replace("{cognome}", str(client.get("last_name") or "").strip())
            .replace("{data}", str(payload.get("date_it") or "") or "—")
            .replace("{ora}", first_time or "—")
            .replace("{persone}", str(payload.get("people") or 1))
            .replace("{trattamenti}", "\n".join(lines) if lines else "—")
            .replace("{codice}", str(payload.get("code") or "—"))
        )

    async def _async_announce(self, appointment: dict[str, Any]) -> dict[str, Any]:
        """Fire the creation event and notify the operator about the booking."""
        payload = self.appointment_payload(appointment)
        self.hass.bus.async_fire(EVENT_APPOINTMENT_CREATED, payload)
        if appointment["offer_state"] == OFFER_PENDING:
            await self._async_notify_operator(payload, offer=True)
        else:
            await self._async_notify_operator(payload, "Nuovo appuntamento")
        # The deposit request is never sent on its own: the desk decides after
        # the booking is saved, from the card's prompt.
        return payload

    async def async_cancel_appointment(
        self, appointment_id: str, reason: str = ""
    ) -> dict[str, Any]:
        """Cancel an appointment, keeping it in the history."""
        async with self._lock:
            appointment = self._find(self.appointments, appointment_id, "Appuntamento")
            if appointment["status"] == STATUS_CANCELLED:
                raise ValidationError("L'appuntamento e' gia' annullato")
            appointment["status"] = STATUS_CANCELLED
            appointment["cancel_reason"] = reason
            appointment["cancelled_at"] = dt_util.utcnow().isoformat()
            await self._async_save()

        payload = self.appointment_payload(appointment)
        self.hass.bus.async_fire(EVENT_APPOINTMENT_CANCELLED, payload)
        await self._async_notify_operator(
            payload, "Appuntamento annullato", show_operator=False
        )
        return payload

    async def async_delete_appointment(self, appointment_id: str) -> dict[str, Any]:
        """Delete a cancelled appointment for good."""
        async with self._lock:
            appointment = self._find(self.appointments, appointment_id, "Appuntamento")
            if appointment["status"] != STATUS_CANCELLED:
                raise ValidationError(
                    "Solo gli appuntamenti annullati possono essere eliminati definitivamente"
                )
            self.appointments[:] = [
                a for a in self.appointments if a["id"] != appointment_id
            ]
            await self._async_save()
        return {"deleted": appointment_id}

    async def async_check_in_appointment(
        self, appointment_id: str, checked_in: bool = True
    ) -> dict[str, Any]:
        """Record the client entering, or undo it when checked_in is False."""
        async with self._lock:
            appointment = self._find(self.appointments, appointment_id, "Appuntamento")
            if appointment["status"] != STATUS_CONFIRMED:
                raise ValidationError(
                    "Solo gli appuntamenti confermati possono registrare l'ingresso"
                )
            if checked_in:
                if appointment["checked_in"]:
                    raise ValidationError("L'ingresso e' gia' stato registrato")
                appointment["checked_in"] = True
                appointment["checked_in_at"] = dt_util.utcnow().isoformat()
            else:
                if not appointment["checked_in"]:
                    raise ValidationError("L'ingresso non e' registrato")
                appointment["checked_in"] = False
                appointment["checked_in_at"] = ""
            await self._async_save()
        return self.appointment_payload(appointment)

    async def async_check_out_appointment(self, appointment_id: str) -> dict[str, Any]:
        """Record the client leaving, once."""
        async with self._lock:
            appointment = self._find(self.appointments, appointment_id, "Appuntamento")
            if appointment["status"] != STATUS_CONFIRMED:
                raise ValidationError(
                    "Solo gli appuntamenti confermati possono registrare l'uscita"
                )
            if appointment["checked_out"]:
                raise ValidationError("L'uscita e' gia' stata registrata")
            appointment["checked_out"] = True
            appointment["checked_out_at"] = dt_util.utcnow().isoformat()
            await self._async_save()
        payload = self.appointment_payload(appointment)
        # A check-out earns the client a loyalty voucher, when the reception
        # left the automatic send on. Best effort: the check-out is already
        # recorded, so a failure here never blocks it.
        if bool(self._data[KEY_SETTINGS].get("promo_voucher_auto")):
            client_id = str((payload.get("client") or {}).get("id") or "")
            if client_id:
                try:
                    await self.async_assign_promo_voucher(appointment["id"], client_id)
                except Exception as err:  # noqa: BLE001
                    _LOGGER.warning(
                        "Voucher fedelta non assegnato per l'appuntamento %s: %s",
                        appointment["id"],
                        err,
                    )
        return payload

    # ------------------------------------------------------------------
    # offer lifecycle
    # ------------------------------------------------------------------
    def open_offers_for(self, operator_id: str | None) -> list[dict[str, Any]]:
        """Return an operator's unanswered offers, the most urgent first."""
        if not operator_id:
            return []
        pending = [
            appointment
            for appointment in self.appointments
            if appointment["status"] == STATUS_CONFIRMED
            and appointment["offer_state"] == OFFER_PENDING
            and appointment["operator_id"] == operator_id
        ]
        return sorted(pending, key=lambda item: item["start"])

    def _refused_unassigned(self, operator_id: str) -> dict[str, Any] | None:
        """Return the appointment she refused that nobody else has taken."""
        candidates: list[dict[str, Any]] = []
        for block in self.slot_blocks:
            if block["operator_id"] != operator_id or not block["appointment_id"]:
                continue
            appointment = next(
                (a for a in self.appointments if a["id"] == block["appointment_id"]),
                None,
            )
            if appointment and (
                appointment["status"] == STATUS_CONFIRMED
                and appointment["offer_state"] == OFFER_UNASSIGNED
            ):
                candidates.append(appointment)
        return sorted(candidates, key=lambda item: item["start"])[0] if candidates else None

    @staticmethod
    def _assign_offer(
        appointment: dict[str, Any], operator_id: str, deadline: str
    ) -> None:
        """Put an operator back in charge of an offer."""
        candidates = appointment.get("offer_candidates") or []
        if operator_id not in candidates:
            candidates = [*candidates, operator_id]
            appointment["offer_candidates"] = candidates
        appointment["operator_id"] = operator_id
        appointment["offer_state"] = OFFER_PENDING
        appointment["offer_index"] = candidates.index(operator_id)
        appointment["offer_expires_at"] = deadline
        appointment["offer_reminded"] = False

    @staticmethod
    def _summary(payload: dict[str, Any]) -> str:
        """Return a one line description of an appointment, phone excluded."""
        start = payload.get("start_local") or ""
        end = payload.get("end_local") or ""
        treatment = (payload.get("treatment") or {}).get("name", "il trattamento")
        return (
            f"[{payload.get('code', '?')}] "
            f"{treatment} il {SpaBookingCoordinator.format_day(start)} "
            f"dalle {start[11:16]} alle {end[11:16]} "
            f"con {payload['client']['full_name']}"
        )

    async def async_answer_offer(
        self,
        appointment_id: str,
        answer: str,
        operator_id: str | None = None,
        source: str = "",
        text: str = "",
    ) -> dict[str, Any]:
        """Apply an operator's answer and move the offer onwards.

        Confirming closes the offer, declining also blocks that window for her
        so the following bookings skip her, and "available again" drops the
        block and hands the appointment back when nobody else has taken it.
        """
        if answer not in (ANSWER_CONFIRM, ANSWER_DECLINE, ANSWER_AVAILABLE):
            raise ValidationError(f"Risposta non riconosciuta: '{answer}'")

        async with self._lock:
            appointment = self._find(self.appointments, appointment_id, "Appuntamento")
            if appointment["status"] == STATUS_CANCELLED:
                return {
                    "handled": False,
                    "reason": "L'appuntamento e' annullato",
                    "appointment": self.appointment_payload(appointment),
                }

            current = appointment.get("operator_id")
            actor = operator_id or current
            state = appointment["offer_state"]
            start = dt_util.parse_datetime(appointment["start"]) or dt_util.utcnow()
            end = dt_util.parse_datetime(appointment["end"]) or start

            handled = False
            reason = ""
            reply = ""
            offer_to: str | None = None

            if answer == ANSWER_AVAILABLE:
                removed = self._clear_blocks(actor or "", appointment["id"])
                if state == OFFER_UNASSIGNED and actor:
                    self._assign_offer(appointment, actor, self._offer_deadline())
                    offer_to = actor
                    handled = True
                    reason = "Turno riproposto"
                else:
                    handled = True
                    reason = f"{removed} finestre riaperte"
                    reply = (
                        "Perfetto, sei di nuovo disponibile: tornerò a proporti "
                        "gli appuntamenti in quella finestra."
                    )
            elif state != OFFER_PENDING:
                reason = "Nessuna offerta aperta per questo appuntamento"
            elif operator_id and current and operator_id != current:
                reason = "Questo turno e' stato proposto a un'altra collega"
            elif answer == ANSWER_CONFIRM:
                appointment["offer_state"] = OFFER_NONE
                appointment["offer_expires_at"] = ""
                appointment["offer_reminded"] = False
                handled = True
                reason = "Offerta confermata"
                reply = f"Confermato: {self._summary(self.appointment_payload(appointment))}."
            else:
                window = self._parse_refused_window(text, appointment)
                if window:
                    self._add_window_block(current, window)
                else:
                    self._add_block(appointment, current)
                nxt, index = self._next_candidate(appointment, start, end)
                appointment["offer_index"] = index
                appointment["offer_reminded"] = False
                if nxt:
                    appointment["operator_id"] = nxt
                    appointment["offer_state"] = OFFER_PENDING
                    appointment["offer_expires_at"] = self._offer_deadline()
                    offer_to = nxt
                    reason = f"Rifiutato, passato a {self._operator_name(nxt)}"
                else:
                    appointment["operator_id"] = None
                    appointment["offer_state"] = OFFER_UNASSIGNED
                    appointment["offer_expires_at"] = ""
                    reason = "Rifiutato, nessun'altra disponibile"
                handled = True
                reply = (
                    f"Ok, hai rifiutato {self._summary(self.appointment_payload(appointment))}. "
                    + (
                        f"Ho proposto il turno a {self._operator_name(nxt)}."
                        if nxt
                        else "Nessun'altra collega disponibile: resta da assegnare."
                    )
                )

            await self._async_save()
            payload = self.appointment_payload(appointment)

        if offer_to:
            record = self._operator(offer_to)
            if record and record.get("notify_on_create"):
                await self._async_notify_operator(payload, offer=True)
        if handled:
            self.hass.bus.async_fire(
                EVENT_OFFER_ANSWERED,
                {
                    "answer": answer,
                    "source": source,
                    "operator_id": actor,
                    **payload,
                },
            )
        record = self._operator(actor)
        if reply and record:
            await self._async_reply(record, reply)
        return {
            "handled": handled,
            "answer": answer,
            "reason": reason,
            "appointment": payload,
        }

    async def async_manual_confirm_offer(
        self, appointment_id: str
    ) -> dict[str, Any]:
        """Conferma manuale dell'offerta da parte della reception.

        Usata quando la conferma via WhatsApp/Telegram dell'operatrice non e'
        stata letta automaticamente. Applica lo stesso percorso di
        ANSWER_CONFIRM, cosi' ogni effetto collaterale (evento lanciato,
        risposta inviata all'operatrice, stato registrato) e' identico a una
        conferma reale: la reception non deve distinguere i due casi.
        """
        async with self._lock:
            appointment = self._find(
                self.appointments, appointment_id, "Appuntamento"
            )
            if appointment["offer_state"] != OFFER_PENDING:
                raise ValidationError(
                    "Non c'e' una offerta in attesa di conferma per questo "
                    "appuntamento"
                )
            operator_id = appointment.get("operator_id")
        return await self.async_answer_offer(
            appointment_id,
            ANSWER_CONFIRM,
            operator_id=operator_id,
            source="manuale",
        )

    async def async_set_offer_state(
        self, appointment_id: str, state: str
    ) -> dict[str, Any]:
        """Move an appointment between waiting and confirmed from the desk.

        ``pending`` re-offers the appointment to its assigned operator and
        sends the offer again; ``confirmed`` closes the offer and sends the
        operator a summary that needs no reply.
        """
        if state not in ("pending", "confirmed"):
            raise ValidationError(f"Stato offerta non valido: '{state}'")

        async with self._lock:
            appointment = self._find(self.appointments, appointment_id, "Appuntamento")
            if appointment["status"] == STATUS_CANCELLED:
                raise ValidationError(
                    "Non puoi modificare un appuntamento annullato"
                )
            operator_id = appointment.get("operator_id")
            if not operator_id:
                raise ValidationError(
                    "L'appuntamento non ha un'operatrice assegnata"
                )

            if state == "pending":
                appointment["offer_state"] = OFFER_PENDING
                appointment["offer_index"] = 0
                appointment["offer_expires_at"] = self._offer_deadline()
                appointment["offer_reminded"] = False
            else:
                appointment["offer_state"] = OFFER_NONE
                appointment["offer_expires_at"] = ""
                appointment["offer_reminded"] = False
            await self._async_save()
            payload = self.appointment_payload(appointment)

        record = self._operator(operator_id)
        if record and record.get("notify_on_create"):
            if state == "pending":
                await self._async_notify_operator(payload, offer=True)
            else:
                message = (
                    f"{self.format_appointment(payload, 'Appuntamento confermato')}"
                    "\n\nNon occorre rispondere."
                )
                await self._send_to_operator(record, message)

        return {"appointment": payload}

    def _payment_totals(
        self, appointment: dict[str, Any]
    ) -> dict[str, Any]:
        """Return collected and still-owed money for one appointment.

        Collected is the sum of the registered takings; owed is the agreed
        price (discounted, list or catalogue, in that order) plus accessories
        minus what was collected, never below zero.
        """
        treatment = next(
            (t for t in self.treatments if t.get("id") == (appointment.get("treatment_id") or "")),
            None,
        )
        catalogue = 0.0
        if treatment is not None:
            try:
                catalogue = round(float(treatment.get("price") or 0), 2)
            except (TypeError, ValueError):
                catalogue = 0.0
        agreed = appointment.get("price")
        if agreed is None:
            agreed = appointment.get("list_price")
        if agreed is None:
            agreed = catalogue
        extras_total = 0.0
        catalogue_extras = {
            item.get("id"): item
            for item in self.accessories
            if isinstance(item, dict) and item.get("id")
        }
        for extra_id in appointment.get("extras") or []:
            entry = catalogue_extras.get(extra_id)
            if entry:
                try:
                    extras_total += round(float(entry.get("price") or 0), 2)
                except (TypeError, ValueError):
                    pass
        total = round(max(0.0, agreed) + extras_total, 2)
        collected = round(
            sum(item.get("amount", 0) for item in appointment.get("payments") or []),
            2,
        )
        return {
            "total": total,
            "collected": collected,
            "due": round(max(0.0, total - collected), 2),
        }

    async def async_add_payment(
        self,
        appointment_id: str,
        method: str,
        amount: Any,
        date: str = "",
    ) -> dict[str, Any]:
        """Register one taking on an appointment.

        The method must be a known payment way and the amount positive;
        anything else is refused rather than stored. Returns the payment
        and the updated totals.
        """
        method = str(method or "").strip()
        if method not in {name for name, _, _ in PAYMENT_METHODS}:
            raise ValidationError(f"Metodo di pagamento non valido: '{method}'")
        try:
            value = round(float(amount), 2)
        except (TypeError, ValueError):
            raise ValidationError("Importo incasso non valido")
        if value <= 0:
            raise ValidationError("L'importo incassato deve essere positivo")
        async with self._lock:
            appointment = self._find(
                self.appointments, appointment_id, "Appuntamento"
            )
            if appointment["status"] == STATUS_CANCELLED:
                raise ValidationError(
                    "Non puoi registrare incassi su un appuntamento annullato"
                )
            entry = {
                "id": _new_id("pay"),
                "method": method,
                "date": _norm_date(date) or dt_util.now().date().strftime("%Y-%m-%d"),
                "amount": value,
            }
            payments = _norm_payment_list([*appointment.get("payments", []), entry])
            appointment["payments"] = payments
            await self._async_save()
            payload = self.appointment_payload(appointment)
        return {
            "payment": payments[-1],
            "totals": self._payment_totals(appointment),
            "appointment": payload,
        }

    async def async_delete_payment(
        self, appointment_id: str, payment_id: str
    ) -> dict[str, Any]:
        """Remove one registered taking, keeping the others untouched."""
        async with self._lock:
            appointment = self._find(
                self.appointments, appointment_id, "Appuntamento"
            )
            payments = [
                item
                for item in (appointment.get("payments") or [])
                if item.get("id") != payment_id
            ]
            if len(payments) == len(appointment.get("payments") or []):
                raise NotFoundError("Incasso non trovato")
            appointment["payments"] = payments
            await self._async_save()
            payload = self.appointment_payload(appointment)
        return {
            "totals": self._payment_totals(appointment),
            "appointment": payload,
        }

    #: The informational messages the desk can push to one operator.
    OPERATOR_MESSAGE_KINDS: Final = (
        "guide",
        "today",
        "tomorrow",
        "week",
        "month",
        "upcoming",
        "pending",
    )

    OPERATOR_GUIDE: Final = (
        "GUIDA APPUNTAMENTI\n"
        "\n"
        "Quando ti proponiamo un turno ricevi un messaggio con i dettagli.\n"
        "Rispondi con una di queste parole:\n"
        "• CONFERMO — accetti il turno\n"
        "• NON DISPONIBILE — rifiuti (il turno passa a una collega)\n"
        "• DISPONIBILE DI NUOVO — sei di nuovo disponibile in quella fascia\n"
        "\n"
        "Se non sei disponibile puoi indicare quando, dopo NON DISPONIBILE:\n"
        "• NON DISPONIBILE tutto il giorno\n"
        "• NON DISPONIBILE 13-10-2026 (tutta la giornata)\n"
        "• NON DISPONIBILE 13-10-2026 15:00 (da quell'ora)\n"
        "• NON DISPONIBILE 13-10-2026 15:00-18:00 (una fascia)\n"
        "(puoi scrivere oggi o domani al posto della data)\n"
        "\n"
        "Puoi anche lasciare una reazione ✅ ❌ 🔄 al messaggio.\n"
        "\n"
        "Per ricevere informazioni scrivi una di queste parole:\n"
        "• AIUTO — questa guida\n"
        "• OGGI — i tuoi appuntamenti di oggi\n"
        "• DOMANI — i tuoi appuntamenti di domani\n"
        "• SETTIMANA — i tuoi prossimi 7 giorni\n"
        "• MESE — il riepilogo del mese\n"
        "• FUTURI — i tuoi prossimi appuntamenti\n"
        "• CONFERMARE — gli appuntamenti da confermare"
    )

    #: Words an operator can write to ask for information, mapped to the
    #: message kind each one sends back.
    OPERATOR_INFO_WORDS: Final = (
        ("aiuto", "guide"),
        ("oggi", "today"),
        ("domani", "tomorrow"),
        ("settimana", "week"),
        ("mese", "month"),
        ("futuri", "upcoming"),
        ("confermare", "pending"),
    )

    _MONTHS_IT: Final = (
        "gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno",
        "luglio", "agosto", "settembre", "ottobre", "novembre", "dicembre",
    )

    async def async_send_operator_message(
        self, operator_id: str, kind: str
    ) -> dict[str, Any]:
        """Send one informational message to an operator on her channels."""
        operator = self._operator(operator_id)
        if not operator:
            raise ValidationError(f"Operatore con id '{operator_id}' non trovato")
        if kind not in self.OPERATOR_MESSAGE_KINDS:
            raise ValidationError(f"Tipo di messaggio non valido: '{kind}'")
        text = self._operator_message_text(operator, kind)
        await self._send_to_operator(operator, text)
        return {
            "operator_id": operator_id,
            "operator_name": operator.get("name", ""),
            "kind": kind,
            "message": text,
            "sent": True,
        }

    @classmethod
    def operator_info_kind(cls, text: str) -> str | None:
        """Return the message kind an operator's word asks for, or None."""
        lowered = (text or "").lower()
        if not lowered:
            return None
        for word, kind in cls.OPERATOR_INFO_WORDS:
            if word in lowered:
                return kind
        return None

    async def async_send_operator_info(
        self, channel: str, chat_id: str | None, text: str
    ) -> bool:
        """Answer an operator's informational word with the matching message."""
        kind = self.operator_info_kind(text)
        if kind is None:
            return False
        operator = await self._resolve_operator_chat(channel, chat_id or "")
        if not operator:
            _LOGGER.warning(
                "Messaggio informativo '%s' da %s: nessuna operatrice riconosciuta",
                kind,
                chat_id or "sconosciuto",
            )
            return True
        await self._send_to_operator(
            operator, self._operator_message_text(operator, kind)
        )
        return True

    async def async_send_external_message(
        self, chat_id: str, text: str
    ) -> dict[str, Any]:
        """Send a WhatsApp message to an external number (non-operator).

        Used by the card to reply to incoming WhatsApp messages from
        unknown numbers that are not clients or operators.
        """
        if not chat_id or not text:
            raise ValidationError("Chat ID e testo sono obbligatori")
        result = await messaging.async_send_whatsapp(
            self.hass, chat_id, text, waha=self.waha
        )
        return result

    async def async_send_guest_summary(
        self,
        appointment_id: str | None = None,
        appointment_ids: list[str] | None = None,
    ) -> dict[str, Any]:
        """Send the guest a WhatsApp summary of one or more appointments.

        A party is one message listing every appointment, not one message per
        person, so the guest reads the whole booking in one place.
        """
        ids = [str(item) for item in (appointment_ids or []) if item]
        if appointment_id:
            ids.insert(0, str(appointment_id))
        if not ids:
            raise ValidationError("Indica almeno un appuntamento")
        payloads = [
            self.appointment_payload(
                self._find(self.appointments, item, "Appuntamento")
            )
            for item in ids
        ]
        phone = (payloads[0].get("client") or {}).get("phone") or ""
        chat_id = messaging.whatsapp_chat_id(phone)
        if not chat_id:
            raise ValidationError("Il cliente non ha un telefono per WhatsApp")
        message = "\n\n".join(self.format_summary(payload) for payload in payloads)
        result = await messaging.async_send_whatsapp(
            self.hass, chat_id, message, waha=self.waha
        )
        return {
            "appointment_id": ids[0],
            "appointment_ids": ids,
            "sent": bool(result.get("sent")),
            "result": result,
        }

    async def async_send_deposit_request(
        self, appointment_id: str
    ) -> dict[str, Any]:
        """Ask one guest, by WhatsApp, to pay her deposit by bank transfer.

        Only a still-waiting booking whose deposit has not been marked received
        qualifies: a booking that already has money on it (deposit/paid/voucher)
        is confirmed and needs no request. The message carries the booking code,
        the amount and the editable bank details.
        """
        async with self._lock:
            appointment = self._find(
                self.appointments, appointment_id, "Appuntamento"
            )
            payload = self.appointment_payload(appointment)
            if appointment["status"] != STATUS_PENDING:
                raise ValidationError(
                    "La prenotazione non è in attesa di conferma"
                )
            if _payment_confirms(appointment):
                raise ValidationError(
                    "Ha già un acconto, un pagamento o un voucher: è confermata"
                )
            if not (appointment.get("deposit_amount") or 0):
                raise ValidationError(
                    "Indica prima l'importo dell'acconto nella scheda pagamento"
                )
            if appointment.get("deposit_request_sent"):
                raise ValidationError(
                    "La richiesta d'acconto è già stata inviata"
                )
            phone = (payload.get("client") or {}).get("phone") or ""
            chat_id = messaging.whatsapp_chat_id(phone)
            if not chat_id:
                raise ValidationError(
                    "Il cliente non ha un telefono per WhatsApp"
                )
            appointment["deposit_request_sent"] = True
            await self._async_save()

        message = self.format_deposit_request(payload)
        try:
            result = await messaging.async_send_whatsapp(
                self.hass, chat_id, message, waha=self.waha
            )
            sent = bool(result.get("sent"))
        except Exception as err:  # noqa: BLE001
            # A messaging failure must not lock the flag: reset it and let the
            # desk resend from the card.
            _LOGGER.warning(
                "Invio richiesta d'acconto a %s fallito: %s",
                phone or "?",
                err,
            )
            async with self._lock:
                appointment["deposit_request_sent"] = False
                await self._async_save()
            return {
                "appointment_id": appointment_id,
                "sent": False,
                "error": str(err),
                "deposit_request_sent": False,
            }
        if not sent:
            async with self._lock:
                appointment["deposit_request_sent"] = False
                await self._async_save()
        return {
            "appointment_id": appointment_id,
            "sent": sent,
            "result": result,
            "deposit_request_sent": appointment["deposit_request_sent"],
        }

    def format_promo(self, client: dict[str, Any], code: str = "") -> str:
        """Return the promotional message personalised for one guest.

        ``{nome}`` / ``{cognome}`` / ``{codice}`` are filled from the client
        card and her latest booking. The template itself is editable from the
        Promo tab.
        """
        template = str(
            self._data.get(KEY_SETTINGS, {}).get("promo_message") or ""
        ).strip() or DEFAULT_PROMO_MESSAGE
        first_name = str(client.get("first_name") or "").strip()
        last_name = str(client.get("last_name") or "").strip()
        settings = self._data.get(KEY_SETTINGS, {})
        return (
            template.replace("{nome}", first_name or "ospite")
            .replace("{cognome}", last_name)
            .replace("{codice}", str(code or ""))
            .replace("{codice_promo}", str(settings.get("promo_code") or ""))
            .replace("{scadenza_promo}", _date_it(str(settings.get("promo_expiry") or "")))
        )

    def _promo_expiry(self) -> date | None:
        """The last day the promo may go out, or None when it has no expiry."""
        raw = str(self._data.get(KEY_SETTINGS, {}).get("promo_expiry") or "")
        return datetime.strptime(raw, "%Y-%m-%d").date() if raw else None

    def _last_client_code(self, client_id: str) -> str:
        """The booking reference of this client's most recent appointment."""
        latest = next(
            (
                appt
                for appt in sorted(
                    (
                        a for a in self.appointments
                        if a.get("client_id") == client_id
                    ),
                    key=lambda item: str(item.get("start") or ""),
                    reverse=True,
                )
            ),
            None,
        )
        return str(latest.get("code") or "") if latest else ""

    def _promo_recipients(
        self, client_ids: list[str] | None = None
    ) -> list[dict[str, Any]]:
        """Clients eligible for the promo: a phone, and not unsubscribed."""
        if client_ids:
            wanted = {str(item) for item in client_ids if str(item)}
            pool = [c for c in self.clients if c["id"] in wanted]
        else:
            pool = list(self.clients)
        return [
            c
            for c in pool
            if str(c.get("phone") or "").strip()
            and c.get("promo_opt_in", True)
        ]

    async def async_send_promo(
        self,
        client_ids: list[str] | None = None,
        *,
        message: str | None = None,
    ) -> dict[str, Any]:
        """Broadcast the promotional message to the chosen clients.

        Each send is spaced out by ``promo_interval_sec`` so the WAHA add-on is
        never flooded. Without ``client_ids`` every client with a phone gets it;
        without ``message`` the saved template is used.
        """
        template = (
            message.strip()
            if message is not None
            else str(
                self._data.get(KEY_SETTINGS, {}).get("promo_message") or ""
            ).strip()
            or DEFAULT_PROMO_MESSAGE
        )
        expiry = self._promo_expiry()
        if expiry and dt_util.now().date() > expiry:
            raise ValidationError(
                f"La promo è scaduta il {expiry:%d/%m/%Y}: non può più essere inviata"
            )
        recipients = self._promo_recipients(client_ids)
        settings = self._data.get(KEY_SETTINGS, {})
        interval = int(
            settings.get("promo_interval_sec") or DEFAULT_PROMO_INTERVAL_SEC
        )
        max_sends = int(settings.get("promo_max_sends") or 0)
        window = float(int(settings.get("promo_window_min") or 10) * 60)
        loop = asyncio.get_running_loop()
        stamps: list[float] = []
        sent = 0
        failed = 0
        for client in recipients:
            personal = self.format_promo(
                client, self._last_client_code(client["id"])
            )
            chat_id = messaging.whatsapp_chat_id(client["phone"])
            if not chat_id:
                continue
            # The limit: wait until fewer than max_sends went out in the window.
            while max_sends:
                now = loop.time()
                stamps = [t for t in stamps if now - t < window]
                if len(stamps) < max_sends:
                    break
                await asyncio.sleep(window - (now - stamps[0]))
            stamps.append(loop.time())
            try:
                result = await messaging.async_send_whatsapp(
                    self.hass, chat_id, personal, waha=self.waha
                )
                if result.get("sent"):
                    sent += 1
                else:
                    failed += 1
                    _LOGGER.warning(
                        "Promo non inviato a %s: %s",
                        client.get("phone") or "?",
                        result.get("error") or "errore sconosciuto",
                    )
            except Exception as err:  # noqa: BLE001
                failed += 1
                _LOGGER.warning(
                    "Promo non inviato a %s: %s",
                    client.get("phone") or "?",
                    err,
                )
            if interval:
                await asyncio.sleep(interval)
        _LOGGER.info(
            "Promo broadcast: %d inviati, %d falliti su %d clienti",
            sent,
            failed,
            len(recipients),
        )
        return {
            "sent": sent,
            "failed": failed,
            "total": len(recipients),
            "template": template,
        }

    async def async_scheduled_promo(self) -> dict[str, Any]:
        """Daily automatic broadcast fired by the YAML automation.

        Only runs when ``promo_time`` is set and the current local time matches
        it; skips silently otherwise so the timer tick is a no-op on days the
        reception wants no promo.
        """
        settings = self._data.get(KEY_SETTINGS, {})
        promo_time = str(settings.get("promo_time") or "").strip()
        if not promo_time:
            return {"sent": 0, "total": 0, "reason": "promo non programmata"}
        now_local = dt_util.as_local(dt_util.utcnow())
        current_hm = f"{now_local.hour:02d}:{now_local.minute:02d}"
        if current_hm != promo_time:
            return {
                "sent": 0,
                "total": 0,
                "reason": f"orario attuale {current_hm} != {promo_time}",
            }
        expiry = self._promo_expiry()
        if expiry and now_local.date() > expiry:
            return {"sent": 0, "total": 0, "reason": "promo scaduta"}
        single = str(settings.get("promo_date") or "")
        if single and now_local.date().strftime("%Y-%m-%d") != single:
            return {"sent": 0, "total": 0, "reason": f"data singola {single} diversa da oggi"}
        result = await self.async_send_promo()
        if single:
            # A one-off send runs once: the date is cleared so it does not repeat.
            await self.async_update_settings(promo_date="")
        return result

    def _operator_message_text(
        self, operator: dict[str, Any], kind: str
    ) -> str:
        """Build the body of one informational message for an operator."""
        if kind == "guide":
            return self.OPERATOR_GUIDE
        if kind == "month":
            return self._operator_month_text(operator)
        labels = {
            "today": "APPUNTAMENTI DI OGGI",
            "tomorrow": "APPUNTAMENTI DI DOMANI",
            "week": "APPUNTAMENTI DEI PROSSIMI 7 GIORNI",
            "upcoming": "PROSSIMI APPUNTAMENTI",
            "pending": "APPUNTAMENTI DA CONFERMARE",
        }
        header = f"{labels.get(kind, kind.upper())} - {operator.get('name', '')}"
        payloads = self._operator_agenda(operator["id"], kind)
        if not payloads:
            return f"{header}\n\nNessun appuntamento."
        blocks = [header, ""]
        for payload in payloads:
            blocks.append(self.format_appointment(payload, "Appuntamento"))
            blocks.append("")
        return "\n".join(blocks).rstrip()

    def _operator_agenda(
        self, operator_id: str, kind: str
    ) -> list[dict[str, Any]]:
        """Return the appointment payloads one operator message lists."""
        today = dt_util.now().date()
        selected: list[dict[str, Any]] = []
        for appointment in self.appointments:
            if appointment.get("operator_id") != operator_id:
                continue
            if kind == "pending":
                if appointment.get("offer_state") != OFFER_PENDING:
                    continue
            else:
                if not occupies_slot(appointment):
                    continue
                start = dt_util.parse_datetime(appointment.get("start") or "")
                if start is None:
                    continue
                day = dt_util.as_local(start).date()
                if kind == "today" and day != today:
                    continue
                if kind == "tomorrow" and day != today + timedelta(days=1):
                    continue
                if kind == "week" and not (
                    today <= day < today + timedelta(days=7)
                ):
                    continue
                if kind == "upcoming" and day < today:
                    continue
            selected.append(appointment)
        selected.sort(key=lambda item: item.get("start") or "")
        return [self.appointment_payload(item) for item in selected]

    def _operator_month_text(self, operator: dict[str, Any]) -> str:
        """Return one operator's current-month summary."""
        today = dt_util.now().date()
        items: list[dict[str, Any]] = []
        for appointment in self.appointments:
            if appointment.get("operator_id") != operator["id"]:
                continue
            if not occupies_slot(appointment):
                continue
            start = dt_util.parse_datetime(appointment.get("start") or "")
            if start is None:
                continue
            day = dt_util.as_local(start).date()
            if day.year == today.year and day.month == today.month:
                items.append(appointment)
        items.sort(key=lambda item: item.get("start") or "")
        label = f"{self._MONTHS_IT[today.month - 1]} {today.year}"
        lines = [
            f"RIEPILOGO MESE - {operator.get('name', '')}",
            f"{label}: {len(items)} massaggi",
        ]
        for appointment in items:
            payload = self.appointment_payload(appointment)
            start_local = payload.get("start_local") or ""
            end_local = payload.get("end_local") or ""
            treatment = payload.get("treatment") or {}
            lines.append(
                f"  {self.format_day(start_local)} {start_local[11:16]}-{end_local[11:16]} "
                f"{treatment.get('name', 'n/d')} - "
                f"{payload['client']['full_name']}"
            )
        return "\n".join(lines)

    async def _resolve_operator_chat(
        self, channel: str, chat_id: str
    ) -> dict[str, Any] | None:
        """Find the operator behind an inbound chat id.

        The match covers a phone number in any spelling (with or without
        ``@c.us``), so the number the add-on reports finds her.
        """
        return messaging.find_operator_by_chat(self.operators, channel, chat_id)

    async def async_answer_from_operator(
        self,
        answer: str,
        *,
        operator_id: str | None = None,
        chat_id: str | None = None,
        channel: str | None = None,
        appointment_id: str | None = None,
        source: str = "",
        text: str = "",
    ) -> dict[str, Any]:
        """Resolve an answer that arrives without an appointment id.

        A WhatsApp message or a reaction only says who answered, so it is
        matched to her most urgent open offer; with nothing open, "available
        again" still reopens the windows she had refused.
        """
        if answer not in (ANSWER_CONFIRM, ANSWER_DECLINE, ANSWER_AVAILABLE):
            raise ValidationError(f"Risposta non riconosciuta: '{answer}'")

        if not operator_id:
            if not (chat_id and channel):
                raise ValidationError(
                    "Manca l'identificativa dell'operatrice: serve operator_id "
                    "oppure channel e chat_id"
                )
            operator = await self._resolve_operator_chat(channel, chat_id)
            if not operator:
                return {
                    "handled": False,
                    "reason": f"Nessuna operatrice collegata a {chat_id}",
                    "appointment": None,
                }
            operator_id = operator["id"]

        if appointment_id:
            return await self.async_answer_offer(
                appointment_id, answer, operator_id, source, text
            )

        open_offers = self.open_offers_for(operator_id)
        if open_offers:
            return await self.async_answer_offer(
                open_offers[0]["id"], answer, operator_id, source, text
            )

        if answer == ANSWER_AVAILABLE:
            unassigned = self._refused_unassigned(operator_id)
            if unassigned is not None:
                return await self.async_answer_offer(
                    unassigned["id"], answer, operator_id, source, text
                )
            async with self._lock:
                removed = self._clear_blocks(operator_id)
                await self._async_save()
            record = self._operator(operator_id)
            if removed and record:
                await self._async_reply(
                    record,
                    "Perfetto, sei di nuovo disponibile in tutte le finestre "
                    "che avevi rifiutato.",
                )
            return {
                "handled": True,
                "answer": answer,
                "reason": f"{removed} finestre riaperte",
                "appointment": None,
            }

        return {
            "handled": False,
            "reason": "Nessuna offerta aperta per te in questo momento",
            "appointment": None,
        }

    async def async_expire_offers(self) -> dict[str, Any]:
        """Move on from offers nobody answered and remind the pending ones.

        Called every few minutes by an automation: an expired offer hands the
        turn to the next candidate without blocking her, because not answering
        is not the same as being unavailable.
        """
        now = dt_util.utcnow()
        reminder_hours = self._reminder_hours()
        expired: list[dict[str, Any]] = []
        reminded: list[dict[str, Any]] = []

        async with self._lock:
            for appointment in self.appointments:
                if appointment["status"] != STATUS_CONFIRMED:
                    continue
                if appointment["offer_state"] != OFFER_PENDING:
                    continue
                raw = appointment.get("offer_expires_at") or ""
                if not raw:
                    continue
                expires = dt_util.parse_datetime(raw)
                if expires is None:
                    continue
                if now >= expires:
                    expired.append(appointment)
                elif (
                    reminder_hours
                    and not appointment.get("offer_reminded")
                    and now >= expires - timedelta(hours=reminder_hours)
                ):
                    appointment["offer_reminded"] = True
                    reminded.append(appointment)

            advanced: list[tuple[dict[str, Any], str | None]] = []
            for appointment in expired:
                start = dt_util.parse_datetime(appointment["start"]) or now
                end = dt_util.parse_datetime(appointment["end"]) or start
                nxt, index = self._next_candidate(appointment, start, end)
                appointment["offer_index"] = index
                appointment["offer_reminded"] = False
                if nxt:
                    appointment["operator_id"] = nxt
                    appointment["offer_state"] = OFFER_PENDING
                    appointment["offer_expires_at"] = self._offer_deadline()
                else:
                    appointment["operator_id"] = None
                    appointment["offer_state"] = OFFER_UNASSIGNED
                    appointment["offer_expires_at"] = ""
                advanced.append((appointment, nxt))

            if expired or reminded:
                await self._async_save()

        for appointment, nxt in advanced:
            if not nxt:
                continue
            record = self._operator(nxt)
            if record and record.get("notify_on_create"):
                await self._async_notify_operator(
                    self.appointment_payload(appointment), offer=True
                )
        for appointment in reminded:
            record = self._operator(appointment.get("operator_id"))
            if record:
                await self._async_reply(
                    record,
                    "Promemoria: ti resta poco tempo per rispondere a "
                    f"{self._summary(self.appointment_payload(appointment))}.",
                )

        return {"expired": len(expired), "reminded": len(reminded)}

    async def async_clear_slot_blocks(
        self, operator_id: str, appointment_id: str = ""
    ) -> dict[str, Any]:
        """Reopen a refused window from the dashboard."""
        async with self._lock:
            self._find(self.operators, operator_id, "Operatore")
            removed = self._clear_blocks(operator_id, appointment_id)
            await self._async_save()
        return {"removed": removed, "operator_id": operator_id}

    async def async_add_closure(
        self,
        *,
        scope: str = "facility",
        operator_id: str = "",
        category_id: str = "",
        date_from: str = "",
        date_to: str = "",
        start: str = "",
        end: str = "",
        label: str = "",
    ) -> dict[str, Any]:
        """Close a range of days for the facility, a category or an operator."""
        scope = str(scope or "facility").strip().lower()
        if scope not in CLOSURE_SCOPES:
            raise ValidationError("Ambito di chiusura non valido")
        date_from = str(date_from or "").strip()[:10]
        if not date_from:
            raise ValidationError("Indica la data di inizio della chiusura")
        try:
            first = date.fromisoformat(date_from)
        except ValueError:
            raise ValidationError("La data di inizio non e' valida") from None
        date_to = str(date_to or "").strip()[:10] or date_from
        try:
            last = date.fromisoformat(date_to)
        except ValueError:
            raise ValidationError("La data di fine non e' valida") from None
        if last < first:
            first, last = last, first
        if (last - first).days + 1 > MAX_CLOSURE_DAYS:
            raise ValidationError(
                f"La chiusura puo' durare al massimo {MAX_CLOSURE_DAYS} giorni"
            )
        # An operator closure needs her, a category closure needs the category:
        # a closure nobody is attached to would silently close nothing.
        if scope == "operator":
            if not operator_id:
                raise ValidationError("Scegli l'operatrice da chiudere")
            self._find(self.operators, operator_id, "Operatore")
        if scope == "category":
            if not category_id:
                raise ValidationError("Scegli la categoria da chiudere")
            self._find(self.categories, category_id, "Categoria")

        async with self._lock:
            closure = _norm_closure(
                {
                    "scope": scope,
                    "operator_id": operator_id if scope == "operator" else "",
                    "category_id": category_id if scope == "category" else "",
                    "date_from": first.isoformat(),
                    "date_to": last.isoformat(),
                    "start": str(start or "").strip()[:5],
                    "end": str(end or "").strip()[:5],
                    "label": label,
                }
            )
            self.closures.append(closure)
            await self._async_save()
        return closure

    async def async_delete_closure(self, closure_id: str) -> dict[str, Any]:
        """Reopen the days a closure was holding."""
        async with self._lock:
            closure = self._find(self.closures, closure_id, "Chiusura")
            self.closures[:] = [c for c in self.closures if c["id"] != closure_id]
            await self._async_save()
        return {"deleted": closure_id}

    # ------------------------------------------------------------------
    # clients
    # ------------------------------------------------------------------
    async def async_save_client(
        self,
        *,
        client_id: str | None = None,
        first_name: str = "",
        last_name: str = "",
        phone: str = "",
        email: str = "",
        notes: str = "",
        promo_opt_in: bool | None = None,
    ) -> dict[str, Any]:
        """Create or update a client record."""
        async with self._lock:
            if client_id:
                client = self._find(self.clients, client_id, "Cliente")
                if first_name.strip():
                    client["first_name"] = first_name.strip()
                if last_name.strip():
                    client["last_name"] = last_name.strip()
                if phone.strip():
                    client["phone"] = phone.strip()
                if email.strip():
                    client["email"] = email.strip()
                if notes:
                    client["notes"] = notes
                # The promo choice is a real state, not a "fill the gap" field:
                # an unchecked box must be able to unsubscribe a guest who was
                # subscribed before.
                if promo_opt_in is not None:
                    client["promo_opt_in"] = bool(promo_opt_in)
            else:
                client = self._resolve_client(
                    None,
                    first_name,
                    last_name,
                    phone,
                    email,
                    notes,
                    update_existing=True,
                    promo_opt_in=promo_opt_in,
                )
                if not any(
                    existing["id"] == client["id"] for existing in self.clients
                ):
                    self.clients.append(client)
            await self._async_save()
        return self.client_payload(client)

    def search_clients(self, query: str = "", limit: int = 20) -> list[dict[str, Any]]:
        """Return clients matching a free-text query."""
        needle = query.strip().lower()
        matches: list[dict[str, Any]] = []
        for client in self.clients:
            haystack = " ".join(
                (
                    client["first_name"],
                    client["last_name"],
                    client["phone"],
                    client["email"],
                )
            ).lower()
            if needle and needle not in haystack:
                continue
            matches.append(self.client_payload(client))
            if len(matches) >= limit:
                break
        matches.sort(
            key=lambda c: (c["last_name"].lower(), c["first_name"].lower())
        )
        return matches

    def client_history(self, client_id: str) -> list[dict[str, Any]]:
        """Return every appointment of a client, newest first."""
        payloads = [
            self.appointment_payload(a)
            for a in self.appointments
            if a["client_id"] == client_id
        ]
        payloads.sort(key=lambda a: a["start"], reverse=True)
        return payloads

    async def async_merge_clients(
        self, target_client_id: str, source_client_ids: list[str]
    ) -> dict[str, Any]:
        """Fold duplicate client cards into one, keeping every appointment.

        A group booked under a single name used to give every person her own
        card, so the same name showed up several times in the client list. The
        appointments move to the card the reception chose, the fields she left
        empty are filled from the duplicates, and only then the emptied cards go:
        that order also sidesteps the guard on future appointments, because by
        the time a card is removed nothing points at it any more.
        """
        wanted = [
            cid
            for cid in dict.fromkeys(str(item).strip() for item in source_client_ids)
            if cid and cid != target_client_id
        ]
        if not wanted:
            raise ValidationError("Nessuna scheda duplicata da unire")
        async with self._lock:
            target = self._find(self.clients, target_client_id, "Cliente")
            duplicates: list[dict[str, Any]] = []
            # An id may no longer have a card: an appointment can still point at
            # a client that was merged away earlier. Those references are folded
            # into the target too, so nothing is left pointing at nobody.
            wanted_ids = list(wanted)
            for client_id in wanted:
                found = next(
                    (item for item in self.clients if item["id"] == client_id), None
                )
                if found is None:
                    continue
                duplicates.append(found)
            moved = 0
            for client_id in wanted_ids:
                for appointment in self.appointments:
                    if appointment.get("client_id") == client_id:
                        appointment["client_id"] = target["id"]
                        moved += 1
            for duplicate in duplicates:
                # Whatever the kept card is missing comes from the duplicate,
                # so a number or a note typed later is never thrown away.
                for key in ("first_name", "last_name", "phone", "email", "notes"):
                    if not str(target.get(key) or "").strip() and str(
                        duplicate.get(key) or ""
                    ).strip():
                        target[key] = duplicate[key]
            gone = {duplicate["id"] for duplicate in duplicates}
            self.clients[:] = [
                client for client in self.clients if client["id"] not in gone
            ]
            await self._async_save()
        return {
            "target": target["id"],
            "deleted": sorted(gone),
            "moved_appointments": moved,
        }

    async def async_delete_client(self, client_id: str) -> dict[str, Any]:
        """Delete a client, refusing to orphan future confirmed appointments."""
        async with self._lock:
            client = self._find(self.clients, client_id, "Cliente")
            now = dt_util.utcnow()
            busy = [
                a
                for a in self.appointments
                if a["client_id"] == client_id
                and occupies_slot(a)
                and (dt_util.parse_datetime(a["end"]) or now) >= now
            ]
            if busy:
                raise ValidationError(
                    f"Il cliente ha {len(busy)} appuntamenti confermati futuri. "
                    "Annullali prima di eliminare la scheda."
                )
            self.clients[:] = [c for c in self.clients if c["id"] != client_id]
            await self._async_save()
        return {"deleted": client_id, "future_appointments": len(busy)}

    # ------------------------------------------------------------------
    # admin: categories, treatments, operators
    # ------------------------------------------------------------------
    async def async_add_category(
        self,
        name: str,
        requires_operator: bool = False,
        color: str = "",
        pause_min: int | None = None,
        days: list[int] | None = None,
        morning_days: list[int] | None = None,
        afternoon_days: list[int] | None = None,
        morning_start: str = "",
        morning_end: str = "",
        afternoon_start: str = "",
        afternoon_end: str = "",
        exclusive_with: list[str] | None = None,
    ) -> dict[str, Any]:
        """Create a category."""
        if not name.strip():
            raise ValidationError("Il nome della categoria e' obbligatorio")
        async with self._lock:
            excluded = self._validated_exclusive_categories(exclusive_with)
            payload: dict[str, Any] = {
                "name": name,
                "requires_operator": requires_operator,
                "color": color,
                "days": list(days or []),
                "morning_days": list(morning_days or []),
                "afternoon_days": list(afternoon_days or []),
                "morning_start": morning_start,
                "morning_end": morning_end,
                "afternoon_start": afternoon_start,
                "afternoon_end": afternoon_end,
                "exclusive_with": excluded,
            }
            if pause_min is not None:
                payload["pause_min"] = pause_min
            category = _norm_category(payload)
            self.categories.append(category)
            await self._async_save()
        return category

    def _validated_exclusive_categories(
        self, exclusive_with: list[str] | None
    ) -> list[str]:
        """Return the other category ids to exclude, in the given order."""
        wanted = [str(item) for item in (exclusive_with or []) if str(item).strip()]
        known = {c["id"] for c in self.categories}
        unknown = sorted(set(wanted) - known)
        if unknown:
            raise NotFoundError(f"Categoria con id '{unknown[0]}' non trovata")
        return wanted

    async def async_update_category(
        self,
        category_id: str,
        name: str | None = None,
        requires_operator: bool | None = None,
        color: str | None = None,
        pause_min: int | None = None,
        days: list[int] | None = None,
        morning_days: list[int] | None = None,
        afternoon_days: list[int] | None = None,
        morning_start: str | None = None,
        morning_end: str | None = None,
        afternoon_start: str | None = None,
        afternoon_end: str | None = None,
        exclusive_with: list[str] | None = None,
    ) -> dict[str, Any]:
        """Update a category."""
        async with self._lock:
            category = self._find(self.categories, category_id, "Categoria")
            if name is not None and name.strip():
                category["name"] = name.strip()
            if requires_operator is not None:
                category["requires_operator"] = requires_operator
            # None = leave untouched; empty string = clear the colour.
            if color is not None:
                category["color"] = (color or "").strip()
            if pause_min is not None:
                try:
                    category["pause_min"] = max(0, int(pause_min))
                except (TypeError, ValueError):
                    category["pause_min"] = DEFAULT_CATEGORY_PAUSE_MIN
            # Reused normalisation for the new calendar/overlap fields: it keeps
            # the existing id and defaults that are not given.
            if days is not None:
                category["days"] = _norm_category({**category, "days": days})["days"]
            if morning_days is not None:
                category["morning_days"] = _norm_category(
                    {**category, "morning_days": morning_days}
                )["morning_days"]
            if afternoon_days is not None:
                category["afternoon_days"] = _norm_category(
                    {**category, "afternoon_days": afternoon_days}
                )["afternoon_days"]
            for key, value in (
                ("morning_start", morning_start),
                ("morning_end", morning_end),
                ("afternoon_start", afternoon_start),
                ("afternoon_end", afternoon_end),
            ):
                if value is not None:
                    category[key] = _norm_category({**category, key: value})[key]
            if exclusive_with is not None:
                excluded = [
                    item
                    for item in self._validated_exclusive_categories(exclusive_with)
                    if item != category_id
                ]
                category["exclusive_with"] = _norm_category(
                    {**category, "exclusive_with": excluded}
                )["exclusive_with"]
            await self._async_save()
        return category

    async def async_delete_category(
        self, category_id: str, force: bool = False
    ) -> dict[str, Any]:
        """Delete a category, refusing to orphan treatments."""
        async with self._lock:
            category = self._find(self.categories, category_id, "Categoria")
            used = [
                t["name"] for t in self.treatments if t["category_id"] == category_id
            ]
            if used and not force:
                raise ValidationError(
                    f"La categoria e' usata dai trattamenti: {', '.join(used)}. "
                    "Sposta o elimina prima quei trattamenti."
                )
            # The accessors are read-only properties handing back the live
            # list, so the shortened version has to be written in place.
            self.categories[:] = [
                c for c in self.categories if c["id"] != category_id
            ]
            for treatment in self.treatments:
                if treatment["category_id"] == category_id:
                    treatment["category_id"] = None
            await self._async_save()
        return {"deleted": category_id, "detached_treatments": used}

    async def async_add_treatment(
        self,
        name: str,
        category_id: str | None = None,
        duration_min: int = 90,
        price: float | None = None,
        active: bool = True,
        web_visible: bool = True,
        min_parallel: int = 0,
        max_parallel: int = 0,
        operator_ids: list[str] | None = None,
    ) -> dict[str, Any]:
        """Create a treatment.

        ``web_visible`` says whether the website may offer it; it defaults to
        visible, exactly like every treatment that already exists.
        ``operator_ids`` optionally says which operators may perform it right
        away, with the same two-side sync as the update: the treatment lists
        its operators, and each operator lists her treatments.
        ``min_parallel``/``max_parallel`` bound how many people can share the
        treatment at the same time; they only apply to appointments without
        an operator (0 = no limit).
        """
        if not name.strip():
            raise ValidationError("Il nome del trattamento e' obbligatorio")
        if duration_min <= 0:
            raise ValidationError("La durata deve essere maggiore di zero")
        async with self._lock:
            if category_id:
                self._find(self.categories, category_id, "Categoria")
            treatment = _norm_treatment(
                {
                    "name": name,
                    "category_id": category_id,
                    "duration_min": duration_min,
                    "price": price,
                    "active": active,
                    "web_visible": web_visible,
                    "min_parallel": min_parallel,
                    "max_parallel": max_parallel,
                }
            )
            self.treatments.append(treatment)
            if operator_ids is not None:
                enabled = set(operator_ids or [])
                for operator in self.operators:
                    treats = set(operator.get("treatment_ids") or [])
                    if operator["id"] in enabled:
                        treats.add(treatment["id"])
                    else:
                        treats.discard(treatment["id"])
                    operator["treatment_ids"] = sorted(treats)
                treatment["operator_ids"] = sorted(enabled)
            await self._async_save()
        self._sync_treatment_operator_ids()
        return self.treatment_payload(treatment)

    async def async_update_treatment(
        self,
        treatment_id: str,
        name: str | None = None,
        category_id: str | None = None,
        duration_min: int | None = None,
        price: float | None = None,
        active: bool | None = None,
        web_visible: bool | None = None,
        min_parallel: int | None = None,
        max_parallel: int | None = None,
        operator_ids: list[str] | None = None,
    ) -> dict[str, Any]:
        """Update a treatment.

        ``web_visible`` is left untouched when ``None``, like ``active``.
        ``operator_ids`` sets which operators may perform it directly from the
        treatment form — a convenience that updates each operator card too.
        """
        async with self._lock:
            treatment = self._find(self.treatments, treatment_id, "Trattamento")
            if name is not None and name.strip():
                treatment["name"] = name.strip()
            if category_id is not None:
                self._find(self.categories, category_id, "Categoria")
                treatment["category_id"] = category_id or None
            if duration_min is not None:
                if duration_min <= 0:
                    raise ValidationError("La durata deve essere maggiore di zero")
                treatment["duration_min"] = duration_min
            if price is not None:
                treatment["price"] = price
            if active is not None:
                treatment["active"] = active
            if web_visible is not None:
                treatment["web_visible"] = web_visible
            if min_parallel is not None:
                treatment["min_parallel"] = _norm_parallel(min_parallel)
            if max_parallel is not None:
                treatment["max_parallel"] = _norm_parallel(max_parallel)
            if operator_ids is not None:
                # Sync both sides: the treatment lists its operators, and each
                # operator lists her treatments. Update every operator card so
                # the two never disagree.
                enabled = set(operator_ids or [])
                for operator in self.operators:
                    treats = set(operator.get("treatment_ids") or [])
                    if operator["id"] in enabled:
                        treats.add(treatment_id)
                    else:
                        treats.discard(treatment_id)
                    operator["treatment_ids"] = sorted(treats)
                treatment["operator_ids"] = sorted(enabled)
            await self._async_save()
        self._sync_treatment_operator_ids()
        return self.treatment_payload(treatment)

    async def async_delete_treatment(
        self, treatment_id: str, force: bool = False
    ) -> dict[str, Any]:
        """Delete a treatment, refusing to orphan future appointments."""
        async with self._lock:
            treatment = self._find(self.treatments, treatment_id, "Trattamento")
            now = dt_util.utcnow()
            busy = [
                a
                for a in self.appointments
                if a["treatment_id"] == treatment_id
                and occupies_slot(a)
                and (dt_util.parse_datetime(a["end"]) or now) >= now
            ]
            if busy and not force:
                raise ValidationError(
                    f"Il trattamento ha {len(busy)} appuntamenti futuri. "
                    "Annullali o spostali prima di eliminarlo."
                )
            # Same read-only accessor as above: replace the contents in place.
            self.treatments[:] = [
                t for t in self.treatments if t["id"] != treatment_id
            ]
            # The operator cards list what they can perform, so a deleted
            # treatment must disappear from those lists too.
            for operator in self.operators:
                if treatment_id in operator["treatment_ids"]:
                    operator["treatment_ids"].remove(treatment_id)
            await self._async_save()
        return {"deleted": treatment_id, "future_appointments": len(busy)}

    async def async_add_operator(
        self,
        name: str,
        role: str = OPERATOR_ROLE_DEFAULT,
        phone: str = "",
        whatsapp_chat_id: str = "",
        telegram_chat_id: str = "",
        treatment_ids: list[str] | None = None,
        notify_whatsapp: bool = True,
        notify_telegram: bool = True,
        notify_service: str = "",
        notify_on_create: bool = True,
        priority: int = 0,
        active: bool = True,
    ) -> dict[str, Any]:
        """Create an operator with her role and the massage types she performs."""
        if not name.strip():
            raise ValidationError("Il nome dell'operatore e' obbligatorio")
        if not whatsapp_chat_id.strip() and phone.strip():
            whatsapp_chat_id = messaging.whatsapp_chat_id(phone.strip(), "")
        elif whatsapp_chat_id.strip():
            whatsapp_chat_id = messaging.to_whatsapp_chat_id(
                whatsapp_chat_id.strip()
            )
        async with self._lock:
            operator = _norm_operator(
                {
                    "name": name,
                    "role": role,
                    "phone": phone,
                    "whatsapp_chat_id": whatsapp_chat_id,
                    "telegram_chat_id": telegram_chat_id,
                    "treatment_ids": self._validated_treatment_ids(treatment_ids),
                    "notify_whatsapp": notify_whatsapp,
                    "notify_telegram": notify_telegram,
                    "notify_service": notify_service,
                    "notify_on_create": notify_on_create,
                    "priority": priority,
                    "active": active,
                }
            )
            self.operators.append(operator)
            await self._async_save()
        return operator

    def _validated_treatment_ids(
        self, treatment_ids: list[str] | None
    ) -> list[str]:
        """Return the treatment ids an operator performs, in display order.

        Only active treatments are kept, so an operator card never offers a
        treatment the booking form would then refuse.
        """
        wanted = {str(t) for t in treatment_ids or []}
        known = {t["id"] for t in self.treatments}
        unknown = wanted - known
        if unknown:
            raise NotFoundError(
                f"Trattamento con id '{sorted(unknown)[0]}' non trovato"
            )
        return [t["id"] for t in self.treatments if t["id"] in wanted]

    async def async_update_operator(
        self,
        operator_id: str,
        name: str | None = None,
        role: str | None = None,
        phone: str | None = None,
        whatsapp_chat_id: str | None = None,
        telegram_chat_id: str | None = None,
        treatment_ids: list[str] | None = None,
        notify_whatsapp: bool | None = None,
        notify_telegram: bool | None = None,
        notify_service: str | None = None,
        notify_on_create: bool | None = None,
        priority: int | None = None,
        active: bool | None = None,
    ) -> dict[str, Any]:
        """Update an operator."""
        async with self._lock:
            operator = self._find(self.operators, operator_id, "Operatore")
            if name is not None and name.strip():
                operator["name"] = name.strip()
            if role is not None:
                operator["role"] = role
            if phone is not None:
                operator["phone"] = phone.strip()
            if whatsapp_chat_id is not None:
                operator["whatsapp_chat_id"] = whatsapp_chat_id.strip()
            if operator.get("whatsapp_chat_id", "").strip():
                operator["whatsapp_chat_id"] = messaging.to_whatsapp_chat_id(
                    operator["whatsapp_chat_id"]
                )
            elif operator.get("phone", "").strip():
                operator["whatsapp_chat_id"] = messaging.whatsapp_chat_id(
                    operator["phone"], ""
                )
            if telegram_chat_id is not None:
                operator["telegram_chat_id"] = telegram_chat_id.strip()
            if treatment_ids is not None:
                operator["treatment_ids"] = self._validated_treatment_ids(treatment_ids)
            if notify_whatsapp is not None:
                operator["notify_whatsapp"] = notify_whatsapp
            if notify_telegram is not None:
                operator["notify_telegram"] = notify_telegram
            if notify_service is not None:
                operator["notify_service"] = notify_service.strip()
            if notify_on_create is not None:
                operator["notify_on_create"] = notify_on_create
            if priority is not None:
                operator["priority"] = max(0, int(priority))
            if active is not None:
                operator["active"] = bool(active)
            await self._async_save()
        return operator

    async def async_delete_operator(
        self, operator_id: str, force: bool = False
    ) -> dict[str, Any]:
        """Delete an operator, refusing to orphan future appointments."""
        async with self._lock:
            operator = self._find(self.operators, operator_id, "Operatore")
            now = dt_util.utcnow()
            busy = [
                a
                for a in self.appointments
                if a["operator_id"] == operator_id
                and occupies_slot(a)
                and (dt_util.parse_datetime(a["end"]) or now) >= now
            ]
            if busy and not force:
                raise ValidationError(
                    f"L'operatore ha {len(busy)} appuntamenti futuri. "
                    "Spostali prima di eliminarlo."
                )
            # Same read-only accessor as above: replace the contents in place.
            self.operators[:] = [
                o for o in self.operators if o["id"] != operator_id
            ]
            for treatment in self.treatments:
                if operator_id in treatment["operator_ids"]:
                    treatment["operator_ids"].remove(operator_id)
            await self._async_save()
        return {"deleted": operator_id, "future_appointments": len(busy)}

    @staticmethod
    def _is_missing_batch(appt: dict[str, Any]) -> bool:
        val = appt.get("batch_id")
        return val is None or str(val).strip() == ""

    def _migrate_appointment_batch_ids(self) -> bool:
        """Assign a batch_id to appointments missing one.

        Existing appuntamenti creati prima dell'introduzione del campo non hanno
        un collegamento esplicito. Raggruppiamo quelli che hanno lo stesso
        cliente, la stessa giornata e intervalli di tempo sovrapponibili o
        contigui (gap <= 15 minuti), assegnando loro un batch_id comune.
        Gli appuntamenti isolati ricevono un batch_id proprio (comportamento
        "single"). Solo gli appuntamenti con status attivo vengono considerati
        per il clustering, ma i cancellati ricevono comunque un id proprio.
        """
        changed = False
        # Gruppo per (cliente, giorno)
        groups: dict[tuple[str | None, str], list[dict[str, Any]]] = {}
        for appt in self.appointments:
            if self._is_missing_batch(appt):
                created = str(appt.get("created_at") or "")
                # Group appointments created in the same minute for the same
                # client and day: that is the signature of one multi-row batch.
                key = (appt.get("client_id"), str(appt.get("start") or "")[:10],
                       created[:16] if created else None)
                groups.setdefault(key, []).append(appt)

        for (client_id, day), items in groups.items():
            # Clustering per contiguita' temporale
            clusters: list[list[dict[str, Any]]] = []
            for item in sorted(items, key=lambda a: str(a.get("start") or "")):
                if not clusters:
                    clusters.append([item])
                    continue
                last = clusters[-1]
                # contiguita' se l'ultimo intervallo e' sovrapposto o gap <= 15 min
                last_end = None
                try:
                    from datetime import datetime as _dt

                    last_end = _dt.fromisoformat(last[-1]["end"].replace("Z", "+00:00"))
                except (ValueError, TypeError, AttributeError):
                    last_end = None

                cur_start = None
                try:
                    cur_start = datetime.fromisoformat(str(item.get("start") or "").replace("Z", "+00:00"))
                except ValueError:
                    cur_start = None

                contiguous = True
                if contiguous or len(last) == 0:
                    last.append(item)
                else:
                    clusters.append([item])

            for cluster in clusters:
                if len(cluster) > 1:
                    shared = _new_id("batch")
                    for appt in cluster:
                        appt["batch_id"] = shared
                        changed = True
                else:
                    for appt in cluster:
                        if self._is_missing_batch(appt):
                            appt["batch_id"] = appt["id"]
                            changed = True

        # Anche gli appuntamenti cancellati o con batch già presente vengono
        # assicurati di avere un batch_id proprio (mai null).
        for appt in self.appointments:
            if self._is_missing_batch(appt):
                appt["batch_id"] = appt["id"]
                changed = True

        return changed

    def _sync_treatment_operator_ids(self) -> None:
        """Mirror the operator cards onto each treatment's operator_ids.

        ``treatment.operator_ids`` is derived, kept only so an archive exported
        before the operator cards existed stays readable. Writing it here means
        the two views can never disagree.
        """
        for treatment in self.treatments:
            treatment["operator_ids"] = [
                operator["id"] for operator in self.operators_for_treatment(treatment["id"])
            ]

    # ------------------------------------------------------------------
    # import / export
    # ------------------------------------------------------------------
    def export_data(self) -> dict[str, Any]:
        """Return a deep copy of the whole dataset, settings included."""
        return copy.deepcopy(self._data)

    async def async_import_data(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Replace the dataset with the given one.

        The payload goes through the same upgrade path as a stored archive, so
        a backup taken before the notification settings existed still restores
        a working report.
        """
        if not isinstance(payload, dict):
            raise ValidationError("Il payload deve essere un dizionario")
        async with self._lock:
            self._data, _ = self._upgrade(payload)
            await self._async_save()
        return {
            "counts": {
                key: len(value)
                for key, value in self._data.items()
                if isinstance(value, list)
            }
        }

    def export_clients_csv(self) -> str:
        """Return the client list as a CSV string.

        Columns: Nome, Cognome, Telefono, Email, Note. The desk can open it in
        a spreadsheet, edit it and import it back.
        """
        lines = ["Nome,Cognome,Telefono,Email,Note"]
        for client in sorted(self.clients, key=lambda c: self.full_name(c)):
            values = [
                str(client.get("first_name") or ""),
                str(client.get("last_name") or ""),
                str(client.get("phone") or ""),
                str(client.get("email") or ""),
                str(client.get("notes") or ""),
            ]
            # Escape quotes and wrap fields containing commas or quotes in quotes.
            escaped = []
            for value in values:
                if '"' in value or "," in value or "\n" in value:
                    escaped.append('"' + value.replace('"', '""') + '"')
                else:
                    escaped.append(value)
            lines.append(",".join(escaped))
        return "\n".join(lines)

    async def import_clients_csv(self, csv_text: str) -> dict[str, Any]:
        """Create clients from a CSV string.

        The first row is the header and is skipped. Columns: Nome, Cognome,
        Telefono, Email, Note. A client that already exists (same phone) is
        skipped, so a re-import never duplicates. Returns how many were created
        and how many skipped.
        """

        def norm_phone(value: str) -> str:
            return "".join(ch for ch in (value or "").strip() if ch.isdigit() or ch == "+")

        rows = _parse_csv(csv_text)
        if not rows:
            raise ValidationError("Il file CSV è vuoto o illeggibile")
        rows = rows[1:]  # drop header
        created = 0
        skipped = 0
        async with self._lock:
            for row in rows:
                if not row or all(not cell.strip() for cell in row):
                    continue
                first_name = (row[0] if len(row) > 0 else "").strip()
                last_name = (row[1] if len(row) > 1 else "").strip()
                phone = norm_phone(row[2] if len(row) > 2 else "")
                email = (row[3] if len(row) > 3 else "").strip()
                notes = (row[4] if len(row) > 4 else "").strip()
                if not phone and not (first_name or last_name):
                    continue
                if phone and any(c.get("phone") == phone for c in self.clients):
                    skipped += 1
                    continue
                self.clients.append(
                    _norm_client(
                        {
                            "first_name": first_name,
                            "last_name": last_name,
                            "phone": phone,
                            "email": email,
                            "notes": notes,
                        }
                    )
                )
                created += 1
            if created:
                await self._async_save()
        return {"created": created, "skipped": skipped, "total": len(self.clients)}
    def treatment_payload(self, treatment: dict[str, Any]) -> dict[str, Any]:
        """Return a treatment enriched with names and derived flags."""
        category = self._category(treatment.get("category_id"))
        operators = self.operators_for_treatment(treatment["id"])
        return {
            **treatment,
            "category_name": category["name"] if category else None,
            "requires_operator": self._treatment_requires_operator(treatment),
            "operator_ids": [operator["id"] for operator in operators],
            "operator_names": [operator["name"] for operator in operators],
        }

    def operator_payload(self, operator: dict[str, Any]) -> dict[str, Any]:
        """Return an operator enriched with her massage list and chat ids."""
        treatments = [
            t for t in self.treatments if t["id"] in (operator.get("treatment_ids") or [])
        ]
        treatments.sort(key=lambda t: (self._category_name(t), t["name"].lower()))
        whatsapp = messaging.whatsapp_chat_id(
            operator.get("phone", ""), operator.get("whatsapp_chat_id", "")
        )
        # The label and the icon travel with the operator so the card cannot
        # invent one that disagrees with the list the backend declared.
        role = operator.get("role") or OPERATOR_ROLE_DEFAULT
        role_label, role_icon = next(
            ((label, icon) for rid, label, icon in OPERATOR_ROLES if rid == role),
            (OPERATOR_ROLES[0][1], OPERATOR_ROLES[0][2]),
        )
        return {
            **operator,
            "role": role,
            "role_label": role_label,
            "role_icon": role_icon,
            "treatment_names": [t["name"] for t in treatments],
            "treatment_count": len(treatments),
            "whatsapp_chat_id_resolved": whatsapp,
            "channels": [
                channel
                for channel, _ in messaging.report_channels_for_operator(
                    self.hass, operator, self._data[KEY_SETTINGS]
                )
            ],
        }

    def _category_name(self, treatment: dict[str, Any]) -> str:
        """Return a category name for sorting, uncategorised last."""
        category = self._category(treatment.get("category_id"))
        return category["name"].lower() if category else "zzz"

    def config_payload(self) -> dict[str, Any]:
        """Return the full configuration for the dashboard."""
        return {
            KEY_CATEGORIES: [dict(c) for c in self.categories],
            KEY_TREATMENTS: [self.treatment_payload(t) for t in self.treatments],
            KEY_OPERATORS: [self.operator_payload(o) for o in self.operators],
            KEY_SLOT_BLOCKS: [dict(b) for b in self.slot_blocks],
            KEY_CLOSURES: [dict(c) for c in self.closures],
            KEY_SETTINGS: dict(self._data[KEY_SETTINGS]),
            KEY_PERMISSIONS: self.permissions_payload(),
        }

    def permissions_payload(self) -> dict[str, str]:
        """Return the access level chosen for each user."""
        return dict(self._data[KEY_SETTINGS].get(KEY_PERMISSIONS) or {})

    @property
    def accessories(self) -> list[dict[str, Any]]:
        """The accessories the booking form offers, in user order."""
        return list(self._data[KEY_SETTINGS].get("accessories") or [])

    @property
    def accessory_labels(self) -> dict[str, str]:
        """Return ``id -> last known name``, deleted accessories included."""
        return dict(self._data[KEY_SETTINGS].get("accessory_labels") or {})

    def _accessory_ids(self) -> set[str]:
        """The accessory ids a new booking may carry."""
        return {item["id"] for item in self.accessories}

    async def async_set_user_permissions(self, user_id: str, level: str) -> dict[str, str]:
        """Save the access level for a user."""
        if level not in PERMISSION_LEVELS:
            raise SpaBookingError(f"Livello di accesso non valido: {level}")
        async with self._lock:
            permissions = dict(self._data[KEY_SETTINGS].get(KEY_PERMISSIONS) or {})
            permissions[user_id] = level
            self._data[KEY_SETTINGS][KEY_PERMISSIONS] = permissions
            await self._async_save()
        return dict(permissions)

    async def async_users_payload(self) -> list[dict[str, Any]]:
        """Return the Home Assistant users for the Accessi tab.

        System users (Supervisor, Cast, Content, integration tokens...) are
        excluded: they are not people and cannot be granted access.
        """
        try:
            users = await self.hass.auth.async_get_users()
            return [
                {
                    "id": user.id,
                    "name": user.name or user.id,
                    "is_admin": user.is_admin,
                    "is_owner": user.is_owner,
                    "is_active": user.is_active,
                }
                for user in users
                if user.is_active
                and not user.system_generated
                # "Mqtt" is the MQTT integration's service account: it exists
                # as a normal user but is a machine, not a person, so it must
                # never populate a row in the Accessi tab.
                and user.name != "Mqtt"
            ]
        except Exception:
            _LOGGER.debug("Impossibile leggere gli utenti HA", exc_info=True)
            return []

    async def async_update_settings(self, **changes: Any) -> dict[str, Any]:
        """Update the notification settings, ignoring unknown keys."""
        async with self._lock:
            settings = dict(self._data[KEY_SETTINGS])
            for key, value in changes.items():
                if key in settings and value is not None:
                    settings[key] = value
            settings = _norm_settings(settings)
            # Switching the website on issues its token straight away, so the
            # card can show the value to copy before the first guest arrives;
            # switching it off keeps the token, ready for the next season.
            if settings.get("web_enabled") and not str(
                settings.get("web_token") or ""
            ).strip():
                settings["web_token"] = secrets.token_urlsafe(32)
            self._data[KEY_SETTINGS] = settings
            await self._async_save()
        return dict(self._data[KEY_SETTINGS])

    # ------------------------------------------------------------------- WAHA

    @property
    def waha(self) -> WahaClient | None:
        """A client for the configured WAHA add-on, or None when unset.

        An empty URL means "use the rest_command fallback", which is how this
        installation worked before the gateway moved inside the integration.
        """
        settings = self._data[KEY_SETTINGS]
        url = str(settings.get("waha_url") or "")
        if not url:
            return None
        return WahaClient(
            async_get_clientsession(self.hass),
            str(settings.get("waha_api_key") or ""),
            str(settings.get("waha_session") or DEFAULT_WAHA_SESSION),
            base_url=url,
        )

    async def async_check_waha(self) -> dict[str, Any]:
        """Ask WAHA who it is, so the card can prove the configuration works.

        The answer carries nothing secret: the version and the engine, plus a
        readable error when the add-on is unreachable or the key is refused.
        """
        client = self.waha
        if client is None:
            return {"configured": False, "ok": False, "error": "WAHA non configurato"}
        try:
            server = await client.async_get_server()
        except WahaAuthenticationError as err:
            return {"configured": True, "ok": False, "error": str(err)}
        except WahaError as err:
            return {"configured": True, "ok": False, "error": str(err)}
        return {
            "configured": True,
            "ok": True,
            "version": server.version,
            "engine": server.engine or "",
        }

    async def async_setup_waha_webhook(self) -> dict[str, Any]:
        """Turn on inbound answers: our webhook, subscribed on the session.

        One call does the whole job, because a half-configured webhook answers
        nothing: the id and the secret are generated if this is the first time,
        the path is claimed inside Home Assistant, and the session is told to
        post to it. The secret is reported back only as "present", never as a
        value, so the card and the logs cannot leak it.
        """
        client = self.waha
        if client is None:
            raise ValidationError(
                "Configura prima l'URL di WAHA nelle impostazioni"
            )
        async with self._lock:
            settings = dict(self._data[KEY_SETTINGS])
            if not settings.get("waha_webhook_id"):
                settings["waha_webhook_id"] = f"spa_{secrets.token_hex(6)}"
            if not settings.get("waha_webhook_secret"):
                settings["waha_webhook_secret"] = secrets.token_hex(32)
            self._data[KEY_SETTINGS] = _norm_settings(settings)
            await self._async_save()

        webhook_id = settings["waha_webhook_id"]
        secret = settings["waha_webhook_secret"]
        url = self._waha_webhook_url(webhook_id)
        # WAHA is configured first: if it refuses (session missing, key
        # refused) the webhook stays unclaimed here instead of accepting and
        # dropping every answer.
        changed = await client.async_ensure_webhook(url, secret)
        self._async_register_waha_inbound()
        return {
            "active": True,
            "webhook_url": url,
            "updated": changed,
        }

    def _waha_webhook_url(self, webhook_id: str) -> str:
        """The address the WAHA add-on posts the answers to.

        The add-on runs in the Supervisor network, where Home Assistant answers
        as ``homeassistant`` on port 8123. An installation that reaches it
        another way overrides the prefix in the settings.
        """
        override = str(self._data[KEY_SETTINGS].get("waha_ha_url") or "").strip()
        prefix = override.rstrip("/") or "http://homeassistant:8123"
        return f"{prefix}{webhook.async_generate_path(webhook_id)}"

    def _async_register_waha_inbound(self) -> WahaInbound | None:
        """Claim the webhook path inside Home Assistant, replacing an old one.

        Registering twice with the same id is harmless, so pressing the card's
        button again cannot leave two handlers behind.
        """
        settings = self._data[KEY_SETTINGS]
        webhook_id = str(settings.get("waha_webhook_id") or "")
        secret = str(settings.get("waha_webhook_secret") or "")
        if not (webhook_id and secret):
            return None
        inbound = WahaInbound(
            self.hass,
            self,
            webhook_id=webhook_id,
            secret=secret,
            session=str(settings.get("waha_session") or DEFAULT_WAHA_SESSION),
        )
        inbound.async_register()
        self._waha_inbound = inbound
        return inbound

    def async_unregister_waha_inbound(self) -> None:
        """Free the webhook path, usually because the config entry unloaded."""
        inbound = getattr(self, "_waha_inbound", None)
        if inbound is not None:
            inbound.async_unregister()
            self._waha_inbound = None

    def _card_file_version(self) -> str:
        """Return a short hash of the served card file, so its URL changes with it."""
        try:
            path = self.hass.config.path("www", "spa_booking", "spa-booking-card.js")
            with open(path, "rb") as handle:
                digest = hashlib.sha256(handle.read()).hexdigest()
            return digest[:12]
        except OSError:
            return CARD_JS_VERSION

    def card_js_url(self) -> str:
        """Return the card URL to serve, auto-versioned by content hash."""
        return f"{CARD_JS_URL}?v={self._card_file_version()}"

    async def _async_sync_card_resource(self) -> None:
        """Best effort: keep the spa dashboard's card resource on the current version."""
        try:
            lovelace = self.hass.data.get("lovelace")
            dashboard = getattr(lovelace, "dashboards", {}).get("spa-gestione")
            if dashboard is None or not hasattr(dashboard, "async_load"):
                return
            config = await dashboard.async_load(force=True)
            if not isinstance(config, dict):
                return
            resources = config.get("resources")
            if not isinstance(resources, list):
                return
            target = self.card_js_url()
            changed = False
            for resource in resources:
                if (
                    isinstance(resource, dict)
                    and CARD_JS_URL in str(resource.get("url", ""))
                    and resource.get("url") != target
                ):
                    resource["url"] = target
                    changed = True
            if changed:
                await dashboard.async_save(config)
        except Exception:
            _LOGGER.debug("Impossibile aggiornare la risorsa della card", exc_info=True)

    async def async_reload_card(self, version: str = "") -> dict[str, Any]:
        """Re-register the served card URL at the current auto version."""
        async with self._lock:
            self._data[KEY_SETTINGS]["card_js_version"] = self._card_file_version()
            await self._async_save()
        self._register_card_js()
        await self._async_sync_card_resource()
        return {"version": self._card_file_version(), "card_js_url": self.card_js_url()}

    def _register_card_js(self) -> None:
        """Leave exactly one registration of the card module, at this version.

        The frontend keeps its extra-module URLs in a set, so the same URL twice
        is harmless, but a new ``?v=`` is a new entry: without this the page
        would load the same custom element once per version it ever had, and
        some clients refuse a second definition outright. Older registrations
        are dropped by file name, whatever version they carry.
        """
        url = self.card_js_url()
        bases = {CARD_JS_URL, CARD_JS_URL_LEGACY}
        try:
            from homeassistant.components.frontend import (
                DATA_EXTRA_MODULE_URL,
                add_extra_js_url,
                remove_extra_js_url,
            )

            manager = self.hass.data.get(DATA_EXTRA_MODULE_URL)
            for previous in list(manager.urls) if manager is not None else []:
                if previous != url and previous.split("?")[0] in bases:
                    remove_extra_js_url(self.hass, previous)
            add_extra_js_url(self.hass, url)
        except Exception:  # pragma: no cover - a frontend change, not ours
            # Losing the cache-busted URL only costs a card refresh, and it
            # must never be the reason the integration stops working.
            _LOGGER.warning("Impossibile registrare il JavaScript della card", exc_info=True)

    def client_payload(self, client: dict[str, Any]) -> dict[str, Any]:
        """Return a client enriched with derived fields."""
        return {**client, "full_name": self.full_name(client)}

    def appointment_payload(
        self,
        appointment: dict[str, Any],
        extra_clients: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """Return an appointment enriched with names and local times.

        ``extra_clients`` carries the cards of the booking being written that
        are not stored yet. A booking refused on its second person has created
        the first one's card in memory only, and calling her "Cliente
        eliminato" would read as a card that was deleted instead of as a
        person of this very booking.
        """
        client = next(
            (c for c in self.clients if c["id"] == appointment["client_id"]), None
        )
        if client is None:
            client = next(
                (
                    card
                    for card in (extra_clients or [])
                    if card["id"] == appointment["client_id"]
                ),
                None,
            )
        treatment = next(
            (t for t in self.treatments if t["id"] == appointment["treatment_id"]),
            None,
        )
        category = self._category(treatment.get("category_id")) if treatment else None
        operator = self._operator(appointment.get("operator_id"))

        start = dt_util.parse_datetime(appointment["start"])
        end = dt_util.parse_datetime(appointment["end"])
        start_local = dt_util.as_local(start) if start else None
        end_local = dt_util.as_local(end) if end else None

        payload: dict[str, Any] = {
            **appointment,
            "start_local": start_local.isoformat() if start_local else None,
            "end_local": end_local.isoformat() if end_local else None,
            "duration_min": int((end - start).total_seconds() // 60)
            if start and end
            else None,
            "client": (
                {
                    "id": client["id"],
                    "first_name": client["first_name"],
                    "last_name": client["last_name"],
                    "full_name": self.full_name(client),
                    "phone": client["phone"],
                    "email": client["email"],
                    "notes": client["notes"],
                }
                if client
                else {
                    "id": "",
                    "first_name": "",
                    "last_name": "",
                    "full_name": "Cliente eliminato",
                    "phone": "",
                    "email": "",
                    "notes": "",
                }
            ),
            "treatment": {
                "id": treatment["id"],
                "name": treatment["name"],
                "price": treatment["price"],
            }
            if treatment
            else None,
            "category": {
                "id": category["id"],
                "name": category["name"],
            }
            if category
            else None,
            "operator": {"id": operator["id"], "name": operator["name"]}
            if operator
            else None,
            # True while the booking is still waiting. The status itself is
            # enough, but the card and the reports both ask this one question
            # and neither should have to know the statuses by name.
            "is_pending": appointment["status"] == STATUS_PENDING,
        }
        return payload

    def agenda(
        self,
        day: date,
        operator_id: str | None = None,
        category_id: str | None = None,
    ) -> dict[str, Any]:
        """Return the confirmed appointments of a day, grouped.

        ``by_operator`` drives the operator dashboards and the daily digest,
        ``by_category`` drives the grouped notification message.
        """
        day_start = dt_util.start_of_local_day(day)
        day_end = day_start + timedelta(days=1)
        start_utc = dt_util.as_utc(day_start)
        end_utc = dt_util.as_utc(day_end)

        items: list[dict[str, Any]] = []
        for appointment in self.appointments:
            if appointment["status"] != STATUS_CONFIRMED:
                continue
            start = dt_util.parse_datetime(appointment["start"])
            end = dt_util.parse_datetime(appointment["end"])
            if start is None or end is None:
                continue
            if not (start < end_utc and end > start_utc):
                continue
            payload = self.appointment_payload(appointment)
            if operator_id and appointment["operator_id"] != operator_id:
                continue
            if category_id:
                category = payload.get("category")
                if not category or category["id"] != category_id:
                    continue
            items.append(payload)

        items.sort(key=lambda a: a["start_local"])

        by_operator: dict[str, list[dict[str, Any]]] = {}
        unassigned: list[dict[str, Any]] = []
        for item in items:
            if item["operator"]:
                by_operator.setdefault(item["operator"]["id"], []).append(item)
            else:
                unassigned.append(item)

        by_category: dict[str, list[dict[str, Any]]] = {}
        for item in items:
            category = item.get("category")
            if category:
                by_category.setdefault(category["id"], []).append(item)

        return {
            "date": day.isoformat(),
            "total": len(items),
            "items": items,
            "by_operator": [
                {
                    "operator_id": op_id,
                    "operator_name": self._operator_name(op_id),
                    "total": len(entries),
                    "appointments": entries,
                }
                for op_id, entries in by_operator.items()
            ],
            "by_category": [
                {
                    "category_id": cat_id,
                    "category_name": (self._category(cat_id) or {}).get("name", cat_id),
                    "total": len(entries),
                    "appointments": entries,
                }
                for cat_id, entries in by_category.items()
            ],
            "unassigned": unassigned,
        }

    # ------------------------------------------------------------------
    # notifications
    # ------------------------------------------------------------------
    @staticmethod
    @staticmethod
    def format_day(value: str) -> str:
        """Return an ISO date/time prefix as gg-mm-aaaa (Italian day-first)."""
        day = (value or "")[:10]
        if len(day) == 10 and day[4] == "-" and day[7] == "-":
            return f"{day[8:10]}-{day[5:7]}-{day[0:4]}"
        return day

    @staticmethod
    def format_appointment(
        payload: dict[str, Any],
        title: str = "Appuntamento",
        show_phone: bool = False,
        show_operator: bool = True,
        header: str = "",
    ) -> str:
        """Return a readable Italian summary of an appointment.

        The client's phone number is left out unless explicitly asked for: an
        operator message carries everything about the booking but the number.
        ``show_operator`` hides the masseuse from the guest-facing summary: the
        desk already knows who it is, the guest does not need to. ``header``
        is a headline (hotel name) shown after the title, guest-side only.
        """
        start = payload.get("start_local") or ""
        end = payload.get("end_local") or ""
        start_hm = start[11:16] if start else "?"
        end_hm = end[11:16] if end else "?"
        day = SpaBookingCoordinator.format_day(start) if start else ""
        lines = [f"{title}"]
        if header:
            lines.append("")
            lines.append(header)
        lines += [
            f"Codice: {payload.get('code', '—')}",
            f"Cliente: {payload['client']['full_name']}",
            f"Trattamento: {payload['treatment']['name'] if payload.get('treatment') else 'n/d'}"
            f" ({payload.get('duration_min')} min)",
            f"Quando: {day} dalle {start_hm} alle {end_hm}",
        ]
        if show_operator and payload.get("operator"):
            lines.append(f"Operatore: {payload['operator']['name']}")
        if show_phone and payload["client"].get("phone"):
            lines.append(f"Telefono: {payload['client']['phone']}")
        if payload["client"].get("notes"):
            lines.append(f"Note cliente: {payload['client']['notes']}")
        if payload.get("notes"):
            lines.append(f"Note: {payload['notes']}")
        if payload.get("status") == STATUS_CANCELLED and payload.get("cancel_reason"):
            lines.append(f"Motivo annullamento: {payload['cancel_reason']}")
        return "\n".join(lines)

    def format_summary(self, payload: dict[str, Any]) -> str:
        """Return the guest-facing summary of one appointment.

        The whole text is a template the reception edits from the notifications
        tab, so what she writes is what the guest reads; an empty setting falls
        back to the built-in one. The money lines are filled from the booking
        itself: the deposit asked for, what has been collected and what is left
        to settle, plus one line per registered taking.
        """
        template = str(
            self._data[KEY_SETTINGS].get("summary_message") or ""
        ).strip()
        if not template:
            template = DEFAULT_SUMMARY_MESSAGE

        client = payload.get("client") or {}
        treatment = payload.get("treatment") or {}
        settings = self._data[KEY_SETTINGS]
        totals = self._payment_totals(payload)
        start = payload.get("start_local") or ""
        end = payload.get("end_local") or ""
        # The guest reads a date, not an ISO string: italian day-first, slashes.
        day = (self.format_day(start) or "").replace("-", "/") if start else "—"
        values = {
            "{nome}": str(client.get("first_name") or "").strip() or "ospite",
            "{cognome}": str(client.get("last_name") or "").strip(),
            "{cliente}": str(client.get("full_name") or "").strip() or "ospite",
            "{hotel}": str(settings.get("guest_header") or "").strip()
            or DEFAULT_GUEST_HEADER,
            "{codice}": str(payload.get("code") or "—"),
            "{trattamento}": str(treatment.get("name") or "n/d"),
            "{durata}": str(payload.get("duration_min") or ""),
            "{data}": day,
            "{ora}": start[11:16] if start else "—",
            "{fine}": end[11:16] if end else "—",
            "{totale}": _money_text(totals.get("total")),
            "{acconto}": _money_text(payload.get("deposit_amount") or 0),
            "{versato}": _money_text(totals.get("collected")),
            "{residuo}": _money_text(totals.get("due")),
            "{pagamenti}": self._payment_lines(payload),
        }
        text = template
        for key, value in values.items():
            text = text.replace(key, value)
        return text

    def _payment_lines(self, payload: dict[str, Any]) -> str:
        """One line per registered taking, or a plain sentence when there is none."""
        lines = []
        for item in payload.get("payments") or []:
            method = next(
                (
                    label
                    for name, label, _ in PAYMENT_METHODS
                    if name == item.get("method")
                ),
                str(item.get("method") or ""),
            )
            day = (self.format_day(item.get("date")) or "").replace("-", "/")
            lines.append(f"- {day} · {method} · {_money_text(item.get('amount'))}")
        return "\n".join(lines) if lines else "Nessun versamento registrato."

    def format_reminder(self, payload: dict[str, Any]) -> str:
        """Return the guest reminder sent the day before an appointment.

        It carries the booking details but neither the client's name nor the
        operator's: it is the guest's own reminder, with what to bring.
        """
        start = payload.get("start_local") or ""
        end = payload.get("end_local") or ""
        start_hm = start[11:16] if len(start) >= 16 else "?"
        end_hm = end[11:16] if len(end) >= 16 else "?"
        treatment = payload.get("treatment") or {}
        name = treatment.get("name", "n/d")
        treatment_id = treatment.get("id") or payload.get("treatment_id")
        record = next(
            (item for item in self.treatments if item["id"] == treatment_id), None
        )
        if record and self._treatment_requires_operator(record):
            name = f"Massaggio {name}"
        labels = self.accessory_labels
        chosen = [
            labels[item_id]
            for item_id in (payload.get("extras") or [])
            if item_id in labels
        ]
        lines = [
            "APPUNTAMENTO",
            "Il Marchese Hotel & Spa",
            "",
            f"Codice: {payload.get('code', '—')}",
            f"{name} ({payload.get('duration_min')} min)",
            f"Data: {self.format_day(start)}",
            f"Ora: dalle {start_hm} alle {end_hm}",
            f"Accessori: {', '.join(chosen) if chosen else 'nessuno'}",
            "",
            "Cosa portare:",
            "• Cuffia — obbligatoria, acquistabile in hotel a € 3,00",
            "• Ciabattine — obbligatorie, acquistabili in hotel a € 3,00",
            "• Wellness Kit — noleggio di accappatoio e telo piscina, "
            "cuffia e ciabattine, € 15,00",
            "",
            "Ti aspettiamo!",
        ]
        return "\n".join(lines)

    def _treatment_names_for_payload(self, payload: dict[str, Any]) -> str:
        """Return a comma-separated list of treatment names for the payload."""
        items = []
        for entry in payload.get("entries") or []:
            items.append(str(entry.get("treatment_name") or "Trattamento"))
        if not items:
            treatment = payload.get("treatment") or {}
            if treatment.get("name"):
                items.append(str(treatment.get("name")))
        return ", ".join(items) if items else "n/d"

    def format_appointment_reminder(self, payload: dict[str, Any]) -> str:
        """Return the customizable appointment reminder message.

        The wording comes from the notifications tab, so the reception changes
        it without touching code; an empty setting falls back to the built-in
        text.
        """
        template = str(
            self._data[KEY_SETTINGS].get("appointment_reminder_message") or ""
        ).strip()
        if not template:
            template = DEFAULT_APPOINTMENT_REMINDER_MESSAGE

        start = payload.get("start_local") or ""
        treatment = payload.get("treatment") or {}
        client = payload.get("client") or {}

        treatment_names = self._treatment_names_for_payload(payload)
        start_date = self.format_day(start) if start else "—"
        start_time = start[11:16] if len(start) >= 16 else "—"

        return (
            template.replace("{nome}", str(client.get("first_name") or "").strip() or "ospite")
            .replace("{cognome}", str(client.get("last_name") or "").strip())
            .replace("{codice}", str(payload.get("code") or "—"))
            .replace("{data}", start_date)
            .replace("{ora}", start_time)
            .replace("{trattamenti}", treatment_names)
        )

    def format_review_request(self, payload: dict[str, Any]) -> str:
        """Return the message asking a guest, hours after her visit, for a review.

        The wording is the one saved in the notifications tab, so the reception
        changes it without touching a line of code; an empty setting falls back
        to the built-in text, which is also what the card shows. ``{nome}``
        becomes her first name, or "ospite" when the client card has none: a
        message that names the guest reads as written to her, not as a broadcast.
        """
        template = str(
            self._data[KEY_SETTINGS].get("review_request_message") or ""
        ).strip() or DEFAULT_REVIEW_MESSAGE
        first_name = str((payload.get("client") or {}).get("first_name") or "").strip()
        body = template.replace("{nome}", first_name or "ospite")
        return body

    def format_deposit_request(self, payload: dict[str, Any]) -> str:
        """Return the message asking a guest to pay her deposit.

        Only the amount is booking-specific; the bank details and the wording
        come from the editable settings, so the reception edits one place and
        every future request follows.
        """
        template = str(self._data[KEY_SETTINGS].get("deposit_message") or "").strip()
        if not template.strip():
            template = DEFAULT_DEPOSIT_MESSAGE
        amount = payload.get("deposit_amount") or 0
        amount_text = f"{amount:.2f}".replace(".", ",") if amount else "—"
        first_name = str((payload.get("client") or {}).get("first_name") or "").strip()
        return (
            template.replace("{nome}", first_name or "ospite")
            .replace("{importo}", amount_text)
            .replace(
                "{intestatario}",
                str(self._data[KEY_SETTINGS].get("deposit_intestatario") or "").strip()
                or DEFAULT_DEPOSIT_INTESTATARIO,
            )
            .replace(
                "{iban}",
                str(self._data[KEY_SETTINGS].get("deposit_iban") or "").strip()
                or DEFAULT_DEPOSIT_IBAN,
            )
            .replace("{codice}", str(payload.get("code") or "—"))
        )

    async def async_send_reminders(
        self, appointment_id: str | None = None
    ) -> dict[str, Any]:
        """Send the guest reminder to every confirmed appointment a day away.

        Called on a timer: each appointment is reminded once, and only while it
        is still ahead, so a booking made inside the last day is reminded too.
        With an ``appointment_id`` only that appointment is sent, forced (used
        for a manual send from the card and for a test).
        """
        settings = self._data.get(KEY_SETTINGS, {})
        auto = bool(settings.get("appointment_reminder_auto", DEFAULT_APPOINTMENT_REMINDER_AUTO))
        hours = int(settings.get("appointment_reminder_hours") or DEFAULT_APPOINTMENT_REMINDER_HOURS)
        if hours <= 0:
            hours = 24

        # In manual mode, only send when an explicit appointment_id is provided.
        if not auto and not appointment_id:
            return {"sent": 0, "failed": 0, "reason": "invio manuale disabilitato"}

        now = dt_util.utcnow()
        if appointment_id:
            deadline = None
        else:
            deadline = now + timedelta(hours=hours)
        advance_window: timedelta = timedelta(hours=hours)
        sent = 0
        failed = 0
        async with self._lock:
            for appointment in self.appointments:
                if appointment_id and appointment["id"] != appointment_id:
                    continue
                if appointment["status"] != STATUS_CONFIRMED:
                    continue
                if not appointment_id:
                    if appointment.get("reminder_sent"):
                        continue
                    start = dt_util.parse_datetime(appointment["start"])
                    if start is None or start <= now:
                        continue
                    if hours > 0 and (start - now).total_seconds() > advance_window.total_seconds():
                        continue
                payload = self.appointment_payload(appointment)
                phone = (payload.get("client") or {}).get("phone") or ""
                chat_id = messaging.whatsapp_chat_id(phone)
                if not chat_id:
                    continue
                appointment["reminder_sent"] = True
                # Use the customizable message template
                message = self.format_appointment_reminder(payload)
                if not message:
                    message = self.format_reminder(payload)
                result = await messaging.async_send_whatsapp(
                    self.hass,
                    chat_id,
                    message,
                    waha=self.waha,
                )
                if result.get("sent"):
                    sent += 1
                else:
                    failed += 1
            await self._async_save()
        return {"sent": sent, "failed": failed}

    async def async_send_review_requests(
        self, appointment_id: str | None = None
    ) -> dict[str, Any]:
        """Ask every guest whose visit is over to leave a review on WhatsApp.

        Called on a timer like the reminder, and only for appointments that ended
        at least ``review_request_after_hours`` ago. A guest who came for two
        treatments the same day is asked once: the second appointment of her day
        is marked as done without sending anything, because one review request
        per person per day is the whole point of the message.

        With an explicit ``appointment_id`` the desk asked for this one guest by
        hand: the automatic switch, the time window and the "already asked"
        guard are all skipped, so the button on the appointment popup always
        sends what it promises. A cancelled appointment is never asked.
        """
        settings = self._data.get(KEY_SETTINGS, {})
        # Without an appointment the send is the scheduled one: honour the
        # on/off switch the reception set in the notifications tab.
        if not appointment_id and not bool(
            settings.get("review_request_auto", DEFAULT_REVIEW_REQUEST_AUTO)
        ):
            return {"sent": 0, "failed": 0, "reason": "invio automatico disattivato"}
        after_hours = int(
            settings.get("review_request_after_hours")
            or DEFAULT_REVIEW_REQUEST_AFTER_HOURS
        )
        now = dt_util.utcnow()
        earliest = now - timedelta(hours=after_hours)
        # Anything older than the window is left alone: it was never asked
        # because the integration was down, and a message about last month
        # arriving today would be worse than no message at all.
        oldest = now - timedelta(hours=after_hours + REVIEW_REQUEST_WINDOW_HOURS)
        sent = 0
        failed = 0
        asked: set[tuple[str, str]] = set()
        async with self._lock:
            for appointment in self.appointments:
                if appointment_id:
                    if appointment["id"] != appointment_id:
                        continue
                    if appointment["status"] == STATUS_CANCELLED:
                        continue
                else:
                    if appointment["status"] != STATUS_CONFIRMED:
                        continue
                    if appointment.get("review_request_sent"):
                        continue
                    end = dt_util.parse_datetime(appointment["end"])
                    if end is None or end > earliest or end < oldest:
                        continue
                payload = self.appointment_payload(appointment)
                phone = (payload.get("client") or {}).get("phone") or ""
                chat_id = messaging.whatsapp_chat_id(phone)
                if not chat_id:
                    continue
                if not appointment_id:
                    end = dt_util.parse_datetime(appointment["end"])
                    day = dt_util.as_local(end).date().isoformat() if end else ""
                    guest_day = (appointment["client_id"], day)
                    if guest_day in asked:
                        # Same guest, same day, already asked: the review request
                        # is per person, not per treatment.
                        appointment["review_request_sent"] = True
                        continue
                    asked.add(guest_day)
                result = await messaging.async_send_whatsapp(
                    self.hass,
                    chat_id,
                    self.format_review_request(payload),
                    waha=self.waha,
                )
                if result.get("sent"):
                    # Only a message that really left marks the appointment, so
                    # the button and the star on the card tell the truth and a
                    # failed send can be tried again.
                    appointment["review_request_sent"] = True
                    sent += 1
                else:
                    failed += 1
            await self._async_save()
        return {"sent": sent, "failed": failed}

    async def async_send_voucher_expiry_reminders(self) -> dict[str, Any]:
        """Send voucher expiration reminders to recipients whose vouchers are
        expiring within the configured number of days.

        The reminder is sent only once per voucher: after it is sent, the
        voucher gets a ``expiry_reminder_sent`` flag so it is not sent again.
        """
        settings = self._data.get(KEY_SETTINGS, {})
        reminder_days = int(settings.get("voucher_expiry_reminder_days") or DEFAULT_VOUCHER_EXPIRY_REMINDER_DAYS)
        reminder_message = str(settings.get("voucher_expiry_reminder_message") or DEFAULT_VOUCHER_EXPIRY_REMINDER_MESSAGE)

        target_date = dt_util.now().date() + timedelta(days=reminder_days)
        sent = 0
        failed = 0
        async with self._lock:
            for voucher in self.vouchers:
                if voucher.get("status") != VOUCHER_ACTIVE:
                    continue
                if voucher.get("expiry_reminder_sent"):
                    continue
                expires_on = _norm_date(voucher.get("expires_on"))
                if not expires_on:
                    continue
                if expires_on != target_date:
                    continue
                # Send reminder for each person in the voucher.
                for person in voucher.get("people", []):
                    name = person.get("name") or ""
                    phone = voucher.get("recipient_phone") or ""
                    chat_id = messaging.whatsapp_chat_id(phone)
                    if not chat_id:
                        continue
                    # Build the reminder message with placeholders.
                    treatments_list = ", ".join(person.get("treatment_ids", [])) or "nessun trattamento"
                    gift_amount = person.get("gift_card_amount")
                    value_str = f"€ {gift_amount:.2f}" if gift_amount else "nessun valore"
                    message = (
                        reminder_message
                        .replace("{nome}", name)
                        .replace("{cognome}", "")
                        .replace("{data_scadenza}", _date_it(expires_on))
                        .replace("{codice}", voucher.get("code", ""))
                        .replace("{valore}", value_str)
                        .replace("{trattamenti}", treatments_list)
                    )
                    result = await messaging.async_send_whatsapp(
                        self.hass,
                        chat_id,
                        message,
                        waha=self.waha,
                    )
                    if result.get("sent"):
                        sent += 1
                    else:
                        failed += 1
                voucher["expiry_reminder_sent"] = True
            await self._async_save()
        return {"sent": sent, "failed": failed}

    @staticmethod
    def format_offer(payload: dict[str, Any]) -> str:
        """Return the text proposing a turn to a masseuse.

        Deliberately carries every detail of the booking but the client's phone
        number, and spells the three accepted answers so a WhatsApp reply does
        not need buttons to be understood.
        """
        start = payload.get("start_local") or ""
        end = payload.get("end_local") or ""
        start_hm = start[11:16] if len(start) >= 16 else "?"
        end_hm = end[11:16] if len(end) >= 16 else "?"
        # The date is shown day-first (gg-mm-aaaa), the way the desk reads it.
        when = start[:10]
        if len(when) == 10:
            when = f"{when[8:10]}-{when[5:7]}-{when[0:4]}"
        treatment = payload.get("treatment") or {}
        lines = [
            "NUOVO APPUNTAMENTO - ti propongo questo turno",
            f"Codice: {payload.get('code', '—')}",
            f"Cliente: {payload['client']['full_name']}",
            f"Trattamento: {treatment.get('name', 'n/d')}"
            f" ({payload.get('duration_min')} min)",
            f"Quando: {when} dalle {start_hm} alle {end_hm}",
        ]
        if payload.get("notes"):
            lines.append(f"Note: {payload['notes']}")
        if payload["client"].get("notes"):
            lines.append(f"Note cliente: {payload['client']['notes']}")
        lines += [
            "",
            "Rispondi con uno di questi:",
            "CONFERMO",
            "NON DISPONIBILE",
            "DISPONIBILE DI NUOVO",
        ]
        return "\n".join(lines)

    @staticmethod
    def offer_keyboard(payload: dict[str, Any]) -> list[list[dict[str, str]]]:
        """Return the Telegram buttons of an offer."""
        appointment_id = payload["id"]
        return [
            [
                {"text": "✅ Confermo", "callback_data": f"spa:{appointment_id}:confirm"},
                {
                    "text": "❌ Non disponibile",
                    "callback_data": f"spa:{appointment_id}:decline",
                },
            ],
            [
                {
                    "text": "🔄 Di nuovo disponibile",
                    "callback_data": f"spa:{appointment_id}:available_again",
                }
            ],
        ]

    async def _async_notify_operator(
        self,
        payload: dict[str, Any],
        title: str = "Appuntamento",
        offer: bool = False,
        show_operator: bool = True,
    ) -> None:
        """Send the assigned operator a notification on every channel she has.

        WhatsApp and Telegram are independent: she receives the message on each
        one she has configured, and a failure on one never hides the other.
        """
        operator = payload.get("operator")
        if not operator:
            return
        record = self._operator(operator["id"])
        if not record or not record.get("notify_on_create"):
            return

        message = self.format_offer(payload) if offer else self.format_appointment(
            payload, title, show_operator=show_operator
        )
        await self._send_to_operator(
            record, message, self.offer_keyboard(payload) if offer else None
        )

    async def _async_reply(self, record: dict[str, Any], text: str) -> None:
        """Send a short answer back to an operator, without the notify service."""
        await self._send_to_operator(record, text, None, include_notify=False)

    async def _send_to_operator(
        self,
        record: dict[str, Any],
        message: str,
        keyboard: list[list[dict[str, str]]] | None = None,
        include_notify: bool = True,
    ) -> None:
        """Write one message to every channel of an operator."""
        settings = self._data[KEY_SETTINGS]

        for channel, chat_id in messaging.report_channels_for_operator(
            self.hass, record, settings
        ):
            if channel == "whatsapp":
                await messaging.async_send_whatsapp(
                    self.hass, chat_id, message, blocking=False, waha=self.waha
                )
            else:
                await messaging.async_send_telegram(
                    self.hass,
                    settings["telegram_config_entry_id"],
                    chat_id,
                    message,
                    blocking=False,
                    inline_keyboard=keyboard,
                )

        if not include_notify:
            return

        service = record.get("notify_service")
        if not service:
            _LOGGER.debug(
                "Operatore %s senza notify_service: notifica inviata solo sui canali "
                "WhatsApp/Telegram",
                record.get("name"),
            )
            return
        try:
            await self.hass.services.async_call(
                "notify",
                "send_message",
                {
                    "entity_id": service,
                    "message": message,
                },
                blocking=False,
            )
        except HomeAssistantError as err:
            _LOGGER.warning("Notifica a %s fallita: %s", record.get("name"), err)

    # ------------------------------------------------------------------
    # monthly report
    # ------------------------------------------------------------------
    @staticmethod
    def _month_bounds(month: str | None) -> tuple[date, date]:
        """Return the first day of a month and of the next one.

        Accepts ``AAAA-MM`` and ``AAAA-MM-GG``. With no argument it returns the
        month before today, because the report is meant to be read at the start
        of the following month.
        """
        today = dt_util.now().date()
        if not month or not str(month).strip():
            last = today.replace(day=1) - timedelta(days=1)
            return last.replace(day=1), last

        text = str(month).strip()
        try:
            if len(text) == 7:
                # date.fromisoformat rejects a bare year-month, so build it.
                first = date(int(text[:4]), int(text[5:7]), 1)
            else:
                first = date.fromisoformat(text).replace(day=1)
        except ValueError as err:
            raise ValidationError(
                f"Mese non valido: '{month}'. Usa il formato AAAA-MM."
            ) from err

        if first.month == 12:
            following = date(first.year + 1, 1, 1)
        else:
            following = date(first.year, first.month + 1, 1)
        return first, following

    def monthly_report(self, month: str | None = None) -> dict[str, Any]:
        """Return the per-operator massage summary of a month.

        Only confirmed appointments count, and each massage is listed with its
        weekday, time, type and duration so the report reads on its own.
        """
        first, following = self._month_bounds(month)
        start_utc = dt_util.as_utc(dt_util.start_of_local_day(first))
        end_utc = dt_util.as_utc(dt_util.start_of_local_day(following))

        groups: dict[str, list[dict[str, Any]]] = {}
        unassigned: list[dict[str, Any]] = []

        for appointment in self.appointments:
            if appointment["status"] != STATUS_CONFIRMED:
                continue
            start = dt_util.parse_datetime(appointment["start"])
            end = dt_util.parse_datetime(appointment["end"])
            if start is None or end is None:
                continue
            if not (start_utc <= start < end_utc):
                continue
            payload = self.appointment_payload(appointment)
            treatment = payload.get("treatment") or {}
            entry = {
                "date": payload["start_local"][:10],
                "start_time": payload["start_local"][11:16],
                "end_time": payload["end_local"][11:16],
                "duration_min": payload["duration_min"],
                "treatment": treatment.get("name") or "Trattamento eliminato",
                "client": payload["client"]["full_name"],
                "price": treatment.get("price"),
            }
            operator_id = appointment.get("operator_id") or None
            if operator_id:
                groups.setdefault(operator_id, []).append(entry)
            else:
                unassigned.append(entry)

        operators = []
        for operator_id, items in groups.items():
            items.sort(key=lambda item: (item["date"], item["start_time"]))
            operators.append(
                {
                    "operator_id": operator_id,
                    "operator_name": self._operator_name(operator_id),
                    "count": len(items),
                    "total_minutes": sum(item["duration_min"] or 0 for item in items),
                    "items": items,
                }
            )
        operators.sort(key=lambda entry: (-entry["count"], entry["operator_name"].lower()))

        report = {
            "month": first.isoformat()[:7],
            "month_label": f"{MESI[first.month - 1]} {first.year}",
            "from": first.isoformat(),
            "to": (following - timedelta(days=1)).isoformat(),
            "total": sum(entry["count"] for entry in operators),
            "total_minutes": sum(entry["total_minutes"] for entry in operators),
            "operators": operators,
            "unassigned": unassigned,
            "unassigned_count": len(unassigned),
        }
        report["text"] = self.format_monthly_report(report)
        return report

    @staticmethod
    def format_minutes(total_minutes: int) -> str:
        """Return a duration as hours and minutes, e.g. '7h 30'."""
        hours, minutes = divmod(int(total_minutes or 0), 60)
        return f"{hours}h {minutes:02d}" if hours else f"{minutes} min"

    @classmethod
    def _report_lines(cls, entry: dict[str, Any]) -> list[str]:
        """Return the text lines of one operator's month."""
        lines = [
            f"{entry['operator_name']} - {entry['count']} massaggi, "
            f"{cls.format_minutes(entry['total_minutes'])}"
        ]
        for item in entry["items"]:
            lines.append(
                f"  {cls.format_day(item['date'])} {item['start_time']}-{item['end_time']} "
                f"{item['treatment']} ({item['duration_min']} min) - {item['client']}"
            )
        return lines

    def format_monthly_report(self, report: dict[str, Any]) -> str:
        """Return the full report text sent to reception and direction."""
        lines = [
            f"REPORT MASSAGGI - {report['month_label']}",
            "",
            f"Totale: {report['total']} massaggi, "
            f"{self.format_minutes(report['total_minutes'])}",
        ]
        if not report["operators"]:
            lines.append("")
            lines.append("Nessun massaggio registrato.")
        for entry in report["operators"]:
            lines.append("")
            lines.extend(self._report_lines(entry))
        if report.get("unassigned_count"):
            lines.append("")
            lines.append(
                f" Senza operatrice: {report['unassigned_count']} appuntamenti "
                "da assegnare."
            )
        return "\n".join(lines)

    async def async_send_monthly_report(self, month: str | None = None) -> dict[str, Any]:
        """Build the monthly report and send it on every configured channel.

        The complete report goes to the configured recipients; each operator
        additionally receives her own summary when that is enabled. Returns the
        per-channel outcome so the card can show what was actually delivered.
        """
        report = self.monthly_report(month)
        settings = self._data[KEY_SETTINGS]
        entry_id = settings["telegram_config_entry_id"]

        results: list[dict[str, Any]] = []

        for chat_id in split_chats(settings["report_telegram_chats"]):
            results.append(
                await messaging.async_send_telegram(
                    self.hass, entry_id, chat_id, report["text"]
                )
            )

        whatsapp_chat = settings["report_whatsapp_chat"]
        if whatsapp_chat:
            results.append(
                await messaging.async_send_whatsapp(
                    self.hass, whatsapp_chat, report["text"], waha=self.waha
                )
            )

        if settings["report_per_operator"]:
            for entry in report["operators"]:
                summary = "\n".join(
                    [
                        f"RIEPILOGO PERSONALE - {report['month_label']}",
                        "",
                        *self._report_lines(entry),
                    ]
                )
                operator = self._operator(entry["operator_id"]) or {}
                for channel, chat_id in messaging.report_channels_for_operator(
                    self.hass, operator, settings
                ):
                    if channel == "whatsapp":
                        result = await messaging.async_send_whatsapp(
                            self.hass, chat_id, summary, waha=self.waha
                        )
                    else:
                        result = await messaging.async_send_telegram(
                            self.hass, entry_id, chat_id, summary
                        )
                    results.append({**result, "operator_id": entry["operator_id"]})

        return {
            "month": report["month"],
            "month_label": report["month_label"],
            "total": report["total"],
            "report": report,
            "sent": sum(1 for result in results if result["sent"]),
            "failed": sum(1 for result in results if not result["sent"]),
            "results": results,
        }

    async def async_send_test_message(
        self,
        channel: str,
        chat_id: str,
        config_entry_id: str = "",
        message: str = "",
    ) -> dict[str, Any]:
        """Send a short test message to one chat.

        Used from the notifications tab to check a single channel without
        sending a whole report. ``message`` carries the text to try instead of
        the generic one — that is how the reception reads her own review request
        on her own phone before any guest gets it. Returns the same shape as
        the real sends, so the card can report sent/failed and the error, if any.
        """
        text = str(message or "").strip() or (
            "Spa Booking — messaggio di prova. "
            "Se lo ricevi, questo canale funziona."
        )
        if channel == "telegram":
            entry_id = config_entry_id or self._data[KEY_SETTINGS].get(
                "telegram_config_entry_id", ""
            )
            return await messaging.async_send_telegram(
                self.hass, entry_id, chat_id, text
            )
        if channel == "whatsapp":
            return await messaging.async_send_whatsapp(
                self.hass, chat_id, text, waha=self.waha
            )
        raise ValidationError(f"Canale sconosciuto: {channel}")


#: Month names used by the report, indexed from January.
MESI = (
    "Gennaio",
    "Febbraio",
    "Marzo",
    "Aprile",
    "Maggio",
    "Giugno",
    "Luglio",
    "Agosto",
    "Settembre",
    "Ottobre",
    "Novembre",
    "Dicembre",
)


def split_chats(value: str) -> list[str]:
    """Return the chat ids of a comma or space separated list."""
    seen: list[str] = []
    for part in str(value or "").replace(";", ",").replace(" ", ",").split(","):
        chat_id = part.strip()
        if chat_id and chat_id not in seen:
            seen.append(chat_id)
    return seen


def _digits_only(value: str) -> str:
    """Return a phone number reduced to its digits."""
    return "".join(char for char in value if char.isdigit())


def _phone_variants(digits: str) -> set[str]:
    """Return the comparable forms of an Italian phone number.

    The same number is often written as "+39 333 1234567", "00393331234567" or
    "333 1234567". Comparing only the exact digits would miss those, and
    comparing a fixed number of trailing digits could merge two different
    numbers, so only the country code is normalised away.
    """
    variants = {digits}
    for prefix in ("0039", "39"):
        if digits.startswith(prefix) and len(digits) > len(prefix):
            variants.add(digits[len(prefix) :])
    return variants


def _same_phone(first: str, second: str) -> bool:
    """Return whether two phone numbers refer to the same subscriber."""
    first_digits = _digits_only(first)
    second_digits = _digits_only(second)
    if not first_digits or not second_digits:
        return False
    return bool(_phone_variants(first_digits) & _phone_variants(second_digits))


def as_aware_datetime(value: datetime | date | str) -> datetime:
    """Return a timezone aware datetime, assuming local time when naive."""
    if isinstance(value, datetime):
        result = value
    elif isinstance(value, date):
        result = datetime.combine(value, time.min)
    elif isinstance(value, str):
        parsed = dt_util.parse_datetime(value)
        if parsed is None:
            try:
                parsed = datetime.combine(date.fromisoformat(value.strip()), time.min)
            except ValueError as err:
                raise ValidationError(
                    f"Data/ora non valida: '{value}'. Usa il formato "
                    "AAAA-MM-GG HH:MM oppure ISO 8601."
                ) from err
        result = parsed
    else:
        raise ValidationError(f"Data/ora non valida: {value!r}")

    if result.tzinfo is None:
        result = result.replace(tzinfo=dt_util.DEFAULT_TIME_ZONE)
    return result


def as_date(value: date | datetime | str) -> date:
    """Return a date from a date, datetime or ISO string."""
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value).strip())
    except ValueError as err:
        raise ValidationError(
            f"Data non valida: '{value}'. Usa il formato AAAA-MM-GG."
        ) from err
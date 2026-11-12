"""Data shapes of the SPA Booking integration.

Every stored record (category, treatment, operator, client, appointment,
voucher, request, closure and the settings) is normalised here, together
with the small date and phone helpers, so ``coordinator.py`` only holds the
business rules. Moved out of the coordinator in 2.1, unchanged.
"""

from __future__ import annotations

from datetime import date, datetime, time
import re
import secrets
from typing import Any
from uuid import uuid4

from homeassistant.exceptions import HomeAssistantError
from homeassistant.util import dt as dt_util

from .const import (
    DEFAULT_QUIET_HOURS_END,
    DEFAULT_QUIET_HOURS_START,
    KEY_VOUCHERS,
    KEY_PROMO_VOUCHERS,
    KEY_PARTNERS,
    DEFAULT_LOYALTY_POINTS_PER_EURO,
    DEFAULT_LOYALTY_THRESHOLD,
    DEFAULT_LOYALTY_REWARD,
    DEFAULT_LOYALTY_MESSAGE,
    PROMO_VOUCHER_CODE_PREFIX,
    PROMO_VOUCHER_PENDING,
    PROMO_VOUCHER_REDEEMED,
    PROMO_VOUCHER_SENT,
    VOUCHER_ACTIVE,
    VOUCHER_REDEEMED,
    APPEARANCE_MODES,
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
    KEY_APPOINTMENTS,
    DEFAULT_CATEGORY_PAUSE_MIN,
    DEFAULT_OFFER_REMINDER_HOURS,
    DEFAULT_OFFER_TIMEOUT_HOURS,
    DEFAULT_REPORT_TELEGRAM_CHATS,
    DEFAULT_REPORT_TIME,
    DEFAULT_TELEGRAM_ENTRY_ID,
    DEFAULT_REVIEW_MESSAGE,
    DEFAULT_PROPOSE_ALT_INTRO,
    DEFAULT_PROPOSE_ALT_LINE,
    DEFAULT_PROPOSE_MESSAGE,
    LEGACY_APPOINTMENT_REMINDER_MESSAGE,
    LEGACY_DEPOSIT_MESSAGE,
    LEGACY_PROPOSE_MESSAGE,
    LEGACY_REQUEST_MESSAGE,
    LEGACY_SUMMARY_MESSAGE,
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
    DEFAULT_WEB_BREAK_END,
    DEFAULT_WEB_BREAK_START,
    DEFAULT_WEB_CLOSE_TIME,
    DEFAULT_WEB_ENABLED,
    DEFAULT_WEB_MAX_DAYS_AHEAD,
    DEFAULT_WEB_NOTIFY_WHATSAPP,
    DEFAULT_WEB_OPEN_TIME,
    DEFAULT_WEB_STEP_MIN,
    DEFAULT_WEB_TOKEN,
    KEY_CATEGORIES,
    KEY_CLIENTS,
    KEY_CLOSURES,
    KEY_PERMISSIONS,
    KEY_REQUESTS,
    KEY_OPERATORS,
    KEY_SETTINGS,
    KEY_SLOT_BLOCKS,
    KEY_TREATMENTS,
    KEY_PROFILES,
    PERMISSION_LEVELS,
    BOOKING_STATUSES,
    OPERATOR_ROLES,
    OPERATOR_ROLE_DEFAULT,
    PAYMENT_METHODS,
    GUEST_TYPE_DEFAULT,
    GUEST_TYPES,
    ACCESSORY_DEFAULTS,
    EXTRAS_OLD_ICONS,
    OFFER_NONE,
    OFFER_PENDING,
    OFFER_UNASSIGNED,
    STATUS_CANCELLED,
    STATUS_CONFIRMED,
    REQUEST_CONFIRMED,
    REQUEST_PENDING,
    REQUEST_SOURCE_DESK,
    REQUEST_SOURCE_WEB,
)
from .exceptions import (
    ValidationError,
)
from . import messaging



def _new_id(prefix: str) -> str:
    """Return a short unique id."""
    return f"{prefix}_{uuid4().hex[:12]}"


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
        # Who sold it: the Home Assistant user (empty for an automation or a
        # voucher made before 2.2) and the name shown on the voucher.
        "created_by": str(raw.get("created_by") or ""),
        "created_by_name": str(raw.get("created_by_name") or "").strip(),
        "expires_on": _norm_date(raw.get("expires_on")),
        "status": status if status in (VOUCHER_ACTIVE, VOUCHER_REDEEMED) else VOUCHER_ACTIVE,
        "redeemed_at": str(raw.get("redeemed_at") or ""),
        "appointment_ids": [str(i) for i in raw.get("appointment_ids") or [] if i],
        # Kept through normalisation: without it every restart forgot that
        # the expiry reminder had already gone out.
        "expiry_reminder_sent": bool(raw.get("expiry_reminder_sent", False)),
        # Where it came from: sold at the desk (""), or a loyalty reward
        # ("punti", 2.4.0), which earns no points itself.
        "source": str(raw.get("source") or ""),
        "client_id": str(raw.get("client_id") or ""),
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
        # "F" a woman, "M" a man, "" not said: matched to the guest's wish.
        "gender": _norm_preference(raw.get("gender")),
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
    "left": ["telegram", "whatsapp", "whatsapp_engine", "waha", "preview"],
    "right": ["review", "report", "offers", "deposit", "guest_header", "summary",
              "request_message", "request_propose", "appointment_reminder"],
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
    for column in blocks:
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
    allowed_types = {"auto", "tile", "button", "climate", "sensor",
                     "switch", "entity", "thermostat", "gauge"}
    card_type = str(raw.get("card_type") or "auto").strip().lower()
    if card_type not in allowed_types:
        card_type = "auto"
    valid_actions = {"toggle", "more-info", "none", "brightness"}
    allowed_features = {"brightness", "temperature", "power", "hvac", "color", "state"}
    tap_action = str(raw.get("tap_action") or "toggle").strip().lower()
    if tap_action not in valid_actions:
        tap_action = "toggle"
    hold_action = str(raw.get("hold_action") or "more-info").strip().lower()
    if hold_action not in valid_actions:
        hold_action = "more-info"
    features = raw.get("features")
    if not isinstance(features, list):
        features = ["brightness", "state"]
    features = [str(f).strip().lower() for f in features if str(f).strip().lower() in allowed_features]
    if not features:
        features = ["state"]
    return {
        "entity_id": entity_id,
        "name": optional_text("name"),
        "icon": optional_text("icon"),
        "show_name": bool(raw.get("show_name", True)),
        "show_icon": bool(raw.get("show_icon", True)),
        "show_state": bool(raw.get("show_state", True)),
        "span": min(max(span, 1), SPA_MAX_SPAN),
        "card_type": card_type,
        "tap_action": tap_action,
        "hold_action": hold_action,
        "features": features,
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
        # Per user: the agenda operator she is, whether the account is the
        # shared reception tablet, and her PIN (salted hash only).
        KEY_PROFILES: _profiles(raw.get(KEY_PROFILES)),
        # Minutes of inactivity before the shared tablet signs out.
        "pin_idle_minutes": _bounded_int(raw.get("pin_idle_minutes"), 10, 1, 240),
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
        # Spa tab: tiles grouped in sections by kind (lights, climate,
        # services and sensors). False keeps the single grid of 2.1.1.
        "spa_grouped": bool(raw.get("spa_grouped", True)),
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
        "deposit_message": _upgraded(raw.get("deposit_message"), DEFAULT_DEPOSIT_MESSAGE, LEGACY_DEPOSIT_MESSAGE),
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
        "summary_message": _upgraded(raw.get("summary_message"), DEFAULT_SUMMARY_MESSAGE, LEGACY_SUMMARY_MESSAGE),
        "summary_test_phone": str(raw.get("summary_test_phone") or "").strip(),
        # The message a guest receives when the desk takes her appointment
        # request: it says the request was received and is waiting for the
        # reception to confirm it. Editable from the notifications tab; an empty
        # setting falls back to the built-in text, so a cleared field never
        # leaves the guest without an answer.
        "request_propose_message": (
            DEFAULT_PROPOSE_MESSAGE
            if str(raw.get("request_propose_message") or "").strip()
            in ("", LEGACY_PROPOSE_MESSAGE.strip())
            else str(raw.get("request_propose_message"))
        ),
        "request_propose_alt_intro": str(
            raw.get("request_propose_alt_intro") or DEFAULT_PROPOSE_ALT_INTRO
        ),
        "request_propose_alt_line": str(
            raw.get("request_propose_alt_line") or DEFAULT_PROPOSE_ALT_LINE
        ),
        "request_message": _upgraded(raw.get("request_message"), DEFAULT_REQUEST_MESSAGE, LEGACY_REQUEST_MESSAGE),
        # Voucher expiration reminder: message sent to the recipient before
        # the voucher expires. The number of days before expiry to send it.
        "voucher_expiry_reminder_message": str(
            raw.get("voucher_expiry_reminder_message") or DEFAULT_VOUCHER_EXPIRY_REMINDER_MESSAGE
        ),
        "voucher_expiry_reminder_days": int(raw.get("voucher_expiry_reminder_days") or DEFAULT_VOUCHER_EXPIRY_REMINDER_DAYS),
        # Appointment reminder for the guest: customizable message, and whether
        # it is sent automatically (with how many hours advance) or manually.
        "appointment_reminder_message": _upgraded(raw.get("appointment_reminder_message"), DEFAULT_APPOINTMENT_REMINDER_MESSAGE, LEGACY_APPOINTMENT_REMINDER_MESSAGE),
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
        # The saved campaigns (2.3.9): each with its own text, code, expiry and
        # automatic start. The single promo of earlier versions becomes the
        # first one of the list.
        "promos": _norm_promos(raw),
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
        # Loyalty points (2.4.0).
        "loyalty_enabled": bool(raw.get("loyalty_enabled", False)),
        "loyalty_points_per_euro": _norm_rate(raw.get("loyalty_points_per_euro")),
        "loyalty_threshold": _norm_count(raw.get("loyalty_threshold"), 1, 1_000_000, DEFAULT_LOYALTY_THRESHOLD),
        "loyalty_reward": _norm_count(raw.get("loyalty_reward"), 1, 100_000, DEFAULT_LOYALTY_REWARD),
        "loyalty_auto": bool(raw.get("loyalty_auto", True)),
        "loyalty_message": str(raw.get("loyalty_message") or DEFAULT_LOYALTY_MESSAGE),
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
        # Which WhatsApp connection sends and receives: the WAHA add-on, or
        # the one built into the integration ("integrated", beta).
        "whatsapp_engine": "integrated"
        if str(raw.get("whatsapp_engine") or "") == "integrated"
        else "waha",
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
        # The form on the site (2.2.0b3): show the prices and the estimated
        # total, the main colour, and the public address of Home Assistant the
        # two-line code loads the form from ("" = the one of the old snippet).
        "web_show_prices": bool(raw.get("web_show_prices", False)),
        "web_accent": _norm_color(raw.get("web_accent")),
        "web_public_url": str(raw.get("web_public_url") or "").strip().rstrip("/"),
        # Internal timers (scheduler.py): reminders, offer expiry, review
        # requests, loyalty vouchers, voucher expiry, daily promo and monthly
        # report run inside the integration. Switch off only to drive them
        # from your own automations instead.
        "scheduler_enabled": bool(raw.get("scheduler_enabled", True)),
        # Guest messages are not sent in the quiet window (start > end means
        # it spans midnight). The offers to the operators are not affected.
        "quiet_hours_start": _norm_clock(raw.get("quiet_hours_start"))
        or DEFAULT_QUIET_HOURS_START,
        "quiet_hours_end": _norm_clock(raw.get("quiet_hours_end"))
        or DEFAULT_QUIET_HOURS_END,
        # Last runs of the once-only jobs, so a timer and an old automation
        # firing in the same minute never send twice.
        "promo_last_sent_on": _norm_date(raw.get("promo_last_sent_on")),
        "report_last_month": str(raw.get("report_last_month") or "").strip()[:7],
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


PROMO_MODES = ("adesso", "giorno", "ogni")


def _norm_promo(raw: Any) -> dict[str, Any] | None:
    """One saved promo campaign, or None when it is not a mapping.

    ``mode`` is how it starts: ``adesso`` (sent by hand), ``giorno`` (once, on
    ``date`` at ``time``) or ``ogni`` (every day at ``time`` from ``date``,
    until ``expiry``). ``last_sent_on``, ``sent_at`` and ``sent_count`` are
    written by the sends, never by the card.
    """
    if not isinstance(raw, dict):
        return None
    mode = str(raw.get("mode") or "adesso")
    return {
        "id": str(raw.get("id") or "").strip() or uuid4().hex[:12],
        "name": str(raw.get("name") or "").strip() or "Promo",
        "theme": str(raw.get("theme") or "").strip(),
        "code": str(raw.get("code") or "").strip(),
        "expiry": _norm_date(raw.get("expiry")),
        "message": str(raw.get("message") or ""),
        "mode": mode if mode in PROMO_MODES else "adesso",
        "date": _norm_date(raw.get("date")),
        "time": _norm_clock(raw.get("time")),
        "last_sent_on": _norm_date(raw.get("last_sent_on")),
        "sent_at": str(raw.get("sent_at") or ""),
        "sent_count": _norm_count(raw.get("sent_count"), 0, 10**9, 0),
        "created_at": str(raw.get("created_at") or ""),
    }


def _norm_promos(settings: dict[str, Any]) -> list[dict[str, Any]]:
    """The saved promo campaigns; the old single promo becomes the first one."""
    raw = settings.get("promos")
    if isinstance(raw, list):
        promos = [p for p in (_norm_promo(item) for item in raw) if p]
        seen: set[str] = set()
        unique = []
        for promo in promos:
            if promo["id"] in seen:
                promo["id"] = uuid4().hex[:12]
            seen.add(promo["id"])
            unique.append(promo)
        return unique
    message = str(settings.get("promo_message") or "").strip()
    time_ = _norm_clock(settings.get("promo_time"))
    code = str(settings.get("promo_code") or "").strip()
    if not (time_ or code or (message and message != DEFAULT_PROMO_MESSAGE.strip())):
        return []
    day = _norm_date(settings.get("promo_date"))
    legacy = _norm_promo(
        {
            "id": "promo1",
            "name": code or "Promo",
            "code": code,
            "expiry": settings.get("promo_expiry"),
            "message": message or DEFAULT_PROMO_MESSAGE,
            "mode": ("giorno" if day else "ogni") if time_ else "adesso",
            "date": day,
            "time": time_,
            "last_sent_on": settings.get("promo_last_sent_on"),
        }
    )
    return [legacy] if legacy else []


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
        # How many promo messages reached her, and the last one (2.3.2).
        "promo_sent_count": _norm_count(raw.get("promo_sent_count"), 0, 1_000_000, 0),
        "promo_last_sent_at": str(raw.get("promo_last_sent_at") or ""),
        # Loyalty points (2.4.0): what was spent on rewards, the desk's
        # corrections, and the log of both. What was earned is worked out
        # from the takings and the vouchers bought, never stored.
        "loyalty_spent": _norm_count(raw.get("loyalty_spent"), 0, 10**9, 0),
        "loyalty_adjust": _norm_signed(raw.get("loyalty_adjust")),
        "loyalty_log": [
            {
                "at": str(item.get("at") or ""),
                "kind": str(item.get("kind") or ""),
                "points": _norm_signed(item.get("points")),
                "note": str(item.get("note") or ""),
                "code": str(item.get("code") or ""),
                "by": str(item.get("by") or ""),
            }
            for item in raw.get("loyalty_log") or []
            if isinstance(item, dict)
        ][-200:],
    }


def _norm_signed(raw: Any) -> int:
    """A whole number that may be negative (a correction of points)."""
    try:
        return int(round(float(raw)))
    except (TypeError, ValueError):
        return 0


def _norm_rate(raw: Any) -> float:
    """Points per euro: zero or more, two decimals; 1 when unset."""
    if raw is None or raw == "":
        return DEFAULT_LOYALTY_POINTS_PER_EURO
    try:
        return max(0.0, round(float(str(raw).replace(",", ".")), 2))
    except (TypeError, ValueError):
        return DEFAULT_LOYALTY_POINTS_PER_EURO


def _norm_partner(raw: Any) -> dict[str, Any]:
    """A partner who promotes the spa (2.4.0)."""
    raw = raw if isinstance(raw, dict) else {}
    return {
        "id": str(raw.get("id") or _new_id("prt")),
        "first_name": str(raw.get("first_name") or "").strip(),
        "last_name": str(raw.get("last_name") or "").strip(),
        "company": str(raw.get("company") or "").strip(),
        "phone": str(raw.get("phone") or "").strip(),
        "email": str(raw.get("email") or "").strip(),
        "code": str(raw.get("code") or "").strip().upper(),
        "notes": str(raw.get("notes") or ""),
        "active": bool(raw.get("active", True)),
        "source": str(raw.get("source") or "manuale"),
        "created_at": str(raw.get("created_at") or dt_util.utcnow().isoformat()),
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
        "icon": (
            factory["icon"]
            if factory and (item_id, str(raw.get("icon") or "")) in EXTRAS_OLD_ICONS
            else str(raw.get("icon") or (factory["icon"] if factory else "mdi:gift-outline")).strip()
        ),
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
        "reminder_sent_at": str(raw.get("reminder_sent_at") or ""),
        # When the booking confirmation (the summary) last went out on WhatsApp.
        "confirmation_sent_at": str(raw.get("confirmation_sent_at") or ""),
        "deposit_request_sent_at": str(raw.get("deposit_request_sent_at") or ""),
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
        # Which Home Assistant user took the booking: kept across restarts so
        # the audit trail does not vanish at the first reload.
        "created_by": str(raw.get("created_by") or "") or None,
        "created_by_name": str(raw.get("created_by_name") or ""),
        "therapist_preference": _norm_preference(raw.get("therapist_preference")),
        # What changed, when and by whom: only the administrator sees it.
        "history": [dict(item) for item in raw.get("history") or [] if isinstance(item, dict)][-100:],
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
        clean = {
            "treatment_id": treatment_id,
            "time": str(item.get("time") or "")[:5],
            "extras": _norm_extras(item.get("extras")),
        }
        # Which person of the party this entry is for (0 = the one booking).
        # The website asks person by person; a desk request has no such key
        # and every entry is meant for each of the ``people``.
        if item.get("person") is not None:
            clean["person"] = _norm_person(item.get("person"))
        if _norm_preference(item.get("therapist_preference")):
            clean["therapist_preference"] = _norm_preference(item.get("therapist_preference"))
        entries.append(clean)
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
        # The guest would like a woman ("F") or a man ("M"); "" = anybody.
        "therapist_preference": _norm_preference(raw.get("therapist_preference")),
        # Who wrote the request down: a person at the desk, or "Sito web".
        "created_by": str(raw.get("created_by") or ""),
        "created_by_name": str(raw.get("created_by_name") or ""),
        # The acknowledgement to the guest goes out once, right after the
        # request is saved; the flag lets the desk see it and resend.
        "message_sent": bool(raw.get("message_sent", False)),
        "message_sent_at": str(raw.get("message_sent_at") or ""),
        # The other date offered to the guest when hers was full (2.2.1).
        "proposed_date": _norm_date(raw.get("proposed_date")),
        "proposed_time": str(raw.get("proposed_time") or "")[:5],
        "proposed_at": str(raw.get("proposed_at") or ""),
        "proposed_by": str(raw.get("proposed_by") or ""),
        # The treatments offered instead, with their price (2.2.2).
        "proposed_alternatives": [
            {
                "treatment_id": str(item.get("treatment_id") or ""),
                "treatment_name": str(item.get("treatment_name") or ""),
                "price": _price_or_none(item.get("price")),
                "date": _norm_date(item.get("date")),
                "time": str(item.get("time") or "")[:5],
            }
            for item in (raw.get("proposed_alternatives") or [])
            if isinstance(item, dict)
        ],
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


def _same_slot(appointment: dict[str, Any], treatment_id: str, start: Any) -> bool:
    """Whether an edit keeps an appointment's treatment and start time."""
    if appointment.get("treatment_id") != treatment_id:
        return False
    try:
        new_start = dt_util.as_utc(as_aware_datetime(start))
    except (TypeError, ValueError, HomeAssistantError):
        return False
    old_start = dt_util.parse_datetime(str(appointment.get("start") or ""))
    return old_start is not None and dt_util.as_utc(old_start) == new_start


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
        "skip_weekdays": weekdays_list(raw.get("skip_weekdays")),
        "created_at": str(raw.get("created_at") or dt_util.utcnow().isoformat()),
    }


def weekdays_list(value: Any) -> list[int]:
    """Days of the week as sorted unique numbers, Monday = 0 … Sunday = 6."""
    found: set[int] = set()
    for item in value or []:
        try:
            day = int(item)
        except (TypeError, ValueError):
            continue
        if 0 <= day <= 6:
            found.add(day)
    return sorted(found)


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
        KEY_PARTNERS: [_norm_partner(p) for p in raw.get(KEY_PARTNERS) or []],
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
        # Missing until 2.0.16: a fresh installation could not sell a voucher
        # (KeyError) until the first restart normalised the stored file.
        KEY_VOUCHERS: [],
        KEY_PROMO_VOUCHERS: [],
        KEY_PARTNERS: [],
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


def _same_phone(first: str, second: str) -> bool:
    """Return whether two phone numbers refer to the same subscriber.

    Both numbers are brought to their international digits first, so
    "+39 333 1234567", "0039 333 1234567" and "333 1234567" are the same,
    while a 39x TIM mobile or a foreign number is never cut down to a
    shorter number that could belong to somebody else.
    """
    first_digits = messaging.international_digits(first)
    second_digits = messaging.international_digits(second)
    if not first_digits or not second_digits:
        return False
    return first_digits == second_digits


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


def _bounded_int(value: Any, default: int, low: int, high: int) -> int:
    """An integer clamped to ``low..high``, or ``default`` when unreadable."""
    try:
        number = int(value)
    except (TypeError, ValueError):
        return default
    return max(low, min(high, number))


def _profiles(raw: Any) -> dict[str, dict[str, Any]]:
    """The user profiles of the Accessi tab, unknown keys dropped."""
    result: dict[str, dict[str, Any]] = {}
    if not isinstance(raw, dict):
        return result
    for user_id, profile in raw.items():
        if not user_id or not isinstance(profile, dict):
            continue
        salt = str(profile.get("pin_salt") or "")
        digest = str(profile.get("pin_hash") or "")
        result[str(user_id)] = {
            "operator_id": str(profile.get("operator_id") or ""),
            "shared": bool(profile.get("shared")),
            "pin_salt": salt if digest else "",
            "pin_hash": digest if salt else "",
        }
    return result


def _norm_color(value: Any) -> str:
    """A CSS hex colour (#rgb or #rrggbb), or "" for the default."""
    text = str(value or "").strip()
    return text if re.fullmatch(r"#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})", text) else ""


def _price_or_none(value: Any) -> float | None:
    """A price in euro rounded to the cent, or None when it is not a number."""
    try:
        return round(float(value), 2)
    except (TypeError, ValueError):
        return None


def _norm_preference(value: Any) -> str:
    """"F", "M" or "" (a gender, or no preference)."""
    text = str(value or "").strip().upper()[:1]
    return {"F": "F", "D": "F", "W": "F", "M": "M", "U": "M"}.get(text, "")


def _upgraded(value: Any, default: str, legacy: str) -> str:
    """A message text: the new default when empty or still the old default.

    A text the reception wrote herself is kept as it is.
    """
    text = str(value or "")
    if not text.strip() or text.strip() == legacy.strip():
        return default
    return text

"""Data coordinator for the SPA Booking integration.

Holds every record (categories, treatments, operators, clients, appointments),
persists it to `.storage/spa_booking.json` and exposes the business rules:
treatment duration decides the end time, an operator can never be double
booked, and neither can a client.
"""

from __future__ import annotations

from contextvars import ContextVar

import asyncio
import copy
import json
from datetime import date, datetime, time, timedelta
import hmac
import logging
import math
import time as time_module
import re
import secrets
from pathlib import Path
from typing import Any, Final
from collections import deque

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.device_registry import DeviceEntryType
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util import dt as dt_util

from .const import (
    EVENT_ANSWER_REQUEST,
    KEY_VOUCHERS,
    KEY_PROMO_VOUCHERS,
    KEY_PARTNERS,
    DEFAULT_LOYALTY_MESSAGE,
    DEFAULT_PARTNER_REWARD_MESSAGE,
    PROMO_VOUCHER_PENDING,
    PROMO_VOUCHER_REDEEMED,
    PROMO_VOUCHER_SENT,
    VOUCHER_ACTIVE,
    VOUCHER_REDEEMED,
    VOUCHER_VALID_MONTHS,
    ANSWER_AVAILABLE,
    ANSWER_CONFIRM,
    ANSWER_DECLINE,
    CARD_JS_URL,
    CARD_JS_URL_LEGACY,
    CARD_JS_VERSION,
    CLOSURE_SCOPES,
    DEFAULT_DEPOSIT_INTESTATARIO,
    DEFAULT_DEPOSIT_IBAN,
    DEFAULT_DEPOSIT_MESSAGE,
    DEFAULT_GUEST_HEADER,
    DEFAULT_PROMO_INTERVAL_SEC,
    DEFAULT_PROMO_MESSAGE,
    DEFAULT_PROMO_VOUCHER_AFTER_HOURS,
    DEFAULT_PROMO_VOUCHER_DAYS,
    DEFAULT_PROMO_VOUCHER_DISCOUNT,
    DEFAULT_PROMO_VOUCHER_MESSAGE,
    DEFAULT_PROMO_VOUCHER_MIN_SPEND,
    DOMAIN,
    EVENT_APPOINTMENT_CANCELLED,
    EVENT_APPOINTMENT_CREATED,
    EVENT_OFFER_ANSWERED,
    EVENT_EXTERNAL_MESSAGE,
    KEY_APPOINTMENTS,
    DEFAULT_CATEGORY_PAUSE_MIN,
    DEFAULT_REPORT_TIME,
    DEFAULT_REVIEW_MESSAGE,
    DEFAULT_PROPOSE_ALT_INTRO,
    DEFAULT_PROPOSE_ALT_LINE,
    DEFAULT_PROPOSE_MESSAGE,
    DEFAULT_REQUEST_MESSAGE,
    DEFAULT_SUMMARY_MESSAGE,
    DEFAULT_CANCEL_MESSAGE,
    DEFAULT_APPOINTMENT_REMINDER_MESSAGE,
    DEFAULT_APPOINTMENT_REMINDER_AUTO,
    DEFAULT_APPOINTMENT_REMINDER_HOURS,
    DEFAULT_REVIEW_REQUEST_AUTO,
    DEFAULT_REVIEW_REQUEST_AFTER_HOURS,
    DEFAULT_VOUCHER_EXPIRY_REMINDER_DAYS,
    DEFAULT_VOUCHER_EXPIRY_REMINDER_MESSAGE,
    DEFAULT_WEB_CLOSE_TIME,
    DEFAULT_WEB_ENABLED,
    DEFAULT_WEB_MAX_DAYS_AHEAD,
    DEFAULT_WEB_OPEN_TIME,
    DEFAULT_WEB_STEP_MIN,
    REVIEW_REQUEST_WINDOW_HOURS,
    WEB_MAX_SLOTS,
    WEB_API_BASE,
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
    KEY_PROFILES,
    PERMISSION_LEVELS,
    MAX_CLOSURE_DAYS,
    OPERATOR_ROLES,
    OPERATOR_ROLE_DEFAULT,
    PAYMENT_METHODS,
    GUEST_TYPE_DEFAULT,
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
)
from .exceptions import (
    CategoryRuleError,
    NotFoundError,
    OverlapError,
    SpaBookingError,
    ValidationError,
)
from . import access, email_sender, gdrive_backup, google_auth, messaging, wp_shop
from .waha import WahaAuthenticationError, WahaError
from .waha_inbound import WahaInbound
from .wa_bridge import WaBridge
from .normalize import (
    _add_months,
    as_aware_datetime,
    _date_it,
    default_data,
    default_settings,
    _fmt_window,
    MESI,
    _money_text,
    _new_code,
    _new_id,
    _new_promo_voucher_code,
    _new_voucher_code,
    _norm_appointment,
    _norm_category,
    _norm_client,
    _norm_clock,
    _norm_closure,
    _norm_count,
    _norm_partner,
    _norm_signed,
    _norm_vat,
    _norm_date,
    _norm_extras,
    _norm_guest_type,
    _norm_operator,
    _norm_parallel,
    _norm_payment,
    _norm_package_ref,
    _norm_payment_list,
    _norm_person,
    _norm_price_opt,
    _norm_promo_voucher,
    _norm_request,
    _norm_settings,
    _norm_slot_block,
    _norm_treatment,
    _norm_voucher,
    _normalise,
    occupies_slot,
    _parse_csv,
    _payment_confirms,
    _REFUSE_DATE,
    _REFUSE_TIME,
    _same_phone,
    _same_slot,
    _same_window,
    split_chats,
    WEEKDAY_LABELS,
)

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

#: Set by the services for a call where the desk saw the category warning
#: and books anyway: the days, time windows and exclusions of the categories
#: are skipped for that call only. Closures and operator clashes still apply.
FORCE_RULES: ContextVar[bool] = ContextVar("spa_booking_force_rules", default=False)

#: Who is acting in this call, set by the services as ``(user_id, name)``:
#: the person signed in, or the one who typed her PIN on the tablet. Unset
#: for timers, the website and WhatsApp answers, which act as the system.
ACTOR: ContextVar[tuple[str, str] | None] = ContextVar("spa_booking_actor", default=None)

#: The appointment fields whose changes go into its history, with the label
#: the administrator reads. Offer bookkeeping and sent-flags are left out.
HISTORY_FIELDS: Final = (
    ("status", "Stato"),
    ("code", "Codice prenotazione"),
    ("start", "Inizio"),
    ("end", "Fine"),
    ("treatment_id", "Trattamento"),
    ("operator_id", "Operatrice"),
    ("client_id", "Cliente"),
    ("person", "Persona"),
    ("guest_type", "Tipo ospite"),
    ("extras", "Accessori"),
    ("list_price", "Prezzo di listino"),
    ("price", "Prezzo"),
    ("paid", "Pagato"),
    ("paid_amount", "Importo pagato"),
    ("deposit", "Acconto"),
    ("deposit_amount", "Importo acconto"),
    ("payments", "Incassato"),
    ("checked_in", "Entrata"),
    ("checked_out", "Uscita"),
    ("notes", "Note"),
    ("cancel_reason", "Motivo annullamento"),
    ("confirmation_sent_at", "Conferma WhatsApp"),
    ("deposit_request_sent_at", "Richiesta acconto"),
    ("reminder_sent_at", "Promemoria WhatsApp"),
)
#: Entries kept per appointment, the oldest dropped first.
HISTORY_MAX: Final = 100
#: Messages kept per WhatsApp conversation, the oldest dropped first.
CHAT_MAX_MESSAGES: Final = 500


def _group_by(items: list[Any], key: Any) -> dict[Any, list[Any]]:
    """Items grouped by ``key(item)``, in their order."""
    groups: dict[Any, list[Any]] = {}
    for item in items:
        groups.setdefault(key(item), []).append(item)
    return groups


def _pct_text(value: float) -> str:
    """10 → "10", 12.5 → "12,5"."""
    return f"{value:.2f}".rstrip("0").rstrip(".").replace(".", ",")


def acting_person() -> tuple[str, str]:
    """``(user_id, name)`` of whoever is acting; the system when nobody."""
    return ACTOR.get() or ("", "Sistema")


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



def _email_html(text: str) -> str:
    """A plain text as a simple HTML email: escaped, links clickable, lines kept."""
    import html as _html

    safe = _html.escape(text)
    # A link ends before the punctuation that closes the sentence.
    safe = re.sub(r"(https?://[^\s<]+?)(?=[.,;:!?)]*(?:\s|<|$))", r'<a href="\1">\1</a>', safe)
    return (
        '<div style="font-family:Arial,Helvetica,sans-serif;font-size:15px;line-height:1.55;color:#1f2328">'
        + safe.replace("\n", "<br>")
        + "</div>"
    )

class SpaBookingCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Store and manage every SPA booking record."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialize the coordinator without starting a polling interval."""
        self.entry = entry
        self._store = Store(hass, STORAGE_VERSION, STORAGE_KEY)
        self._lock = asyncio.Lock()
        # Serialises the timed sending jobs among themselves, so the data lock
        # is only held to read and mark records, never while WhatsApp answers.
        self._send_lock = asyncio.Lock()
        self._data: dict[str, Any] = default_data()
        # The inbound WhatsApp handler, once the gateway is switched on.
        # Recent WhatsApp messages from numbers that are neither clients nor
        # operators, so the desk can read and answer external requests.
        self._external_messages: deque[dict[str, Any]] = deque(maxlen=20)
        # The WhatsApp conversations of the WhatsApp tab (2.3.5): kept on disk
        # in their own file, so a restart loses nothing; only a manager
        # deletes a chat, or all of them.
        self._chats_store: Store = Store(hass, 1, "spa_booking.chats")
        self._chats: dict[str, list[dict[str, Any]]] = {}
        # When a chat last changed: the WhatsApp sensor carries it, so the card
        # reloads the conversations as soon as a message goes out or comes in.
        self._chat_stamp = ""
        # The tracked fields of every appointment at the last save: what the
        # next save compares against to write the change history.
        self._history_snap: dict[str, dict[str, Any]] | None = None
        # Content hash of the served card, computed in the executor at load.
        self._card_version = ""
        # The internal timers, attached by async_setup_entry.
        self.scheduler: Any = None
        # The built-in WhatsApp connection, when chosen (beta).
        self.wa_bridge: WaBridge | None = None
        #: Who is using each shared reception tablet (in memory only).
        self.pin_sessions = access.PinSessions()
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
            self._data = _normalise(
                default_data(self.entry.data.get("operator_names") or [])
            )
            await self._store.async_save(self._data)
        await self.async_refresh_card_version()
        self._history_snap = {a["id"]: self._history_values(a) for a in self.appointments}
        await self._async_load_chats()
        self.async_set_updated_data(self._data)

    @staticmethod
    def _chat_key(chat_id: str) -> str:
        """One key per person: the same number as @c.us, @s.whatsapp.net or bare."""
        value = str(chat_id or "").strip()
        if value.lower().endswith("@s.whatsapp.net"):
            value = value.split("@")[0] + "@c.us"
        return messaging.to_whatsapp_chat_id(value) or value

    def record_outgoing_whatsapp(self, chat_id: str, message: str) -> None:
        """Note a WhatsApp Spa Booking sent (2.8.4): guest, operator or group.

        Who sent it is the person logged in at the card; a message sent by a
        timer (reminder, report, offer cascade) has nobody and reads
        «Automatico» in the card.
        """
        if not chat_id or not message:
            return
        self._chat_add(chat_id, {
            "dir": "out", "text": message, "at": dt_util.now().isoformat(),
            "by": (ACTOR.get() or ("", ""))[1] or "",
        })
        self._chat_stamp = dt_util.now().isoformat()
        self.async_update_listeners()

    def record_incoming_whatsapp(self, chat_id: str, text: str, operator_id: str = "") -> None:
        """Note a WhatsApp received (2.8.4), operators' answers included."""
        if not chat_id or not text:
            return
        operator = operator_id or (
            messaging.find_operator_by_chat(self.operators, "whatsapp", chat_id) or {}
        ).get("id", "")
        self._chat_add(chat_id, {
            "dir": "in", "text": text, "at": dt_util.now().isoformat(),
            **({"operator_id": operator} if operator else {}),
        })
        self._chat_stamp = dt_util.now().isoformat()
        self.async_update_listeners()

    async def async_add_external_message(self, chat_id: str, text: str, record: bool = True) -> None:
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
        if record:
            self._chat_add(chat_id, {"dir": "in", "text": text, "at": entry["received_at"]})
        self.async_update_listeners()
        self.hass.bus.async_fire(
            EVENT_EXTERNAL_MESSAGE,
            {"chat_id": chat_id, "text": text},
        )

    async def _async_load_chats(self) -> None:
        stored = await self._chats_store.async_load()
        chats = (stored or {}).get("chats") if isinstance(stored, dict) else None
        self._chats = {}
        for chat_id, messages in (chats or {}).items():
            if not isinstance(messages, list):
                continue
            # The same person under two spellings becomes one chat (2.8.4).
            merged = self._chats.setdefault(self._chat_key(chat_id), [])
            merged.extend(dict(m) for m in messages if isinstance(m, dict))
        for key, messages in self._chats.items():
            messages.sort(key=lambda m: str(m.get("at") or ""))
            self._chats[key] = messages[-CHAT_MAX_MESSAGES:]
        # The sensor (and automations) see the latest incoming messages again.
        incoming = sorted(
            (
                {"chat_id": chat_id, "text": m.get("text", ""), "received_at": m.get("at", "")}
                for chat_id, messages in self._chats.items()
                for m in messages
                if m.get("dir") == "in"
            ),
            key=lambda m: m["received_at"],
            reverse=True,
        )
        self._external_messages.clear()
        self._external_messages.extend(incoming[:20])

    def _chat_add(self, chat_id: str, message: dict[str, Any]) -> None:
        """Note a message of a conversation and save it (debounced)."""
        messages = self._chats.setdefault(self._chat_key(chat_id), [])
        messages.append(message)
        messages.sort(key=lambda m: str(m.get("at") or ""))
        del messages[:-CHAT_MAX_MESSAGES]
        self._chats_store.async_delay_save(lambda: {"chats": self._chats}, 2)

    def whatsapp_chats(self) -> list[dict[str, Any]]:
        """Every conversation, the most recent first, with its messages."""
        chats = [
            {"chat_id": chat_id, "messages": messages, "last_at": messages[-1].get("at", "") if messages else ""}
            for chat_id, messages in self._chats.items()
        ]
        return sorted(chats, key=lambda chat: chat["last_at"], reverse=True)

    async def async_delete_chats(self, chat_id: str | None = None) -> int:
        """Delete one conversation, or all of them when ``chat_id`` is None."""
        if chat_id is None:
            removed = len(self._chats)
            self._chats = {}
            self._external_messages.clear()
        else:
            removed = 1 if self._chats.pop(self._chat_key(chat_id), None) is not None else 0
            kept = [m for m in self._external_messages if m.get("chat_id") != chat_id]
            self._external_messages.clear()
            self._external_messages.extend(kept)
        await self._chats_store.async_save({"chats": self._chats})
        self.async_update_listeners()
        return removed

    @property
    def chat_stamp(self) -> str:
        return self._chat_stamp

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
        if self._migrate_operator_chat_ids():
            stale = True
        self._sync_treatment_operator_ids()
        return self._data, stale

    def _migrate_operator_chat_ids(self) -> bool:
        """Recompute operator chat ids derived with the old phone rules.

        Up to 2.0.15 a TIM mobile (390-393, 397) written without +39 lost two
        digits, and a landline lost its trunk zero. An id that equals what the
        old rule derived from the phone was computed, not typed, so it is
        replaced by the correct one; a chat id typed by hand stays untouched.
        """
        changed = False
        for operator in self.operators:
            phone = str(operator.get("phone") or "")
            stored = str(operator.get("whatsapp_chat_id") or "").strip()
            if not phone or not stored:
                continue
            if stored != messaging.legacy_whatsapp_chat_id(phone):
                continue
            correct = messaging.whatsapp_chat_id(phone)
            if correct and correct != stored:
                operator["whatsapp_chat_id"] = correct
                changed = True
        return changed

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
        self._record_history()
        await self._store.async_save(self._data)
        self.async_set_updated_data(self._data)

    @staticmethod
    def _history_values(appointment: dict[str, Any]) -> dict[str, Any]:
        values = {key: appointment.get(key) for key, _ in HISTORY_FIELDS}
        values["payments"] = round(
            sum(float(item.get("amount") or 0) for item in appointment.get("payments") or []), 2
        )
        values["extras"] = sorted(appointment.get("extras") or [])
        return values

    def _record_history(self) -> None:
        """Note on each appointment what changed since the last save, and who.

        Done at save time, so every path is covered (desk, tablet, timers,
        WhatsApp answers) without each method having to remember it. Only
        the administrator sees the history in the card.
        """
        current = {a["id"]: self._history_values(a) for a in self.appointments}
        previous = getattr(self, "_history_snap", None)
        self._history_snap = current
        if previous is None:
            return
        by_id, by = acting_person()
        now = dt_util.utcnow().isoformat()
        for appointment in self.appointments:
            new = current[appointment["id"]]
            old = previous.get(appointment["id"])
            if old is None:
                entry = {"action": "Creata", "changes": []}
            else:
                changes = [
                    {
                        "field": key,
                        "label": label,
                        "old": self._history_text(key, old.get(key)),
                        "new": self._history_text(key, new.get(key)),
                    }
                    for key, label in HISTORY_FIELDS
                    if old.get(key) != new.get(key)
                ]
                changes = [c for c in changes if c["old"] != c["new"]]
                if not changes:
                    continue
                action = "Modificata"
                if old.get("status") != new.get("status"):
                    action = {
                        STATUS_CANCELLED: "Annullata",
                        STATUS_CONFIRMED: "Confermata",
                    }.get(new.get("status"), action)
                entry = {"action": action, "changes": changes}
            history = list(appointment.get("history") or [])
            history.append({"at": now, "by": by, "by_id": by_id, **entry})
            appointment["history"] = history[-HISTORY_MAX:]

    def _history_text(self, key: str, value: Any) -> str:
        """A value of the history as the administrator reads it."""
        if value in (None, "", []):
            return "—"
        if key == "start":
            moment = dt_util.parse_datetime(str(value))
            if moment is None:
                return str(value)
            local = dt_util.as_local(moment)
            return f"{_day_words(local.date().isoformat())} {local.strftime('%H:%M')}"
        if key in ("confirmation_sent_at", "reminder_sent_at", "deposit_request_sent_at"):
            moment = dt_util.parse_datetime(str(value))
            if moment is None:
                return str(value)
            local = dt_util.as_local(moment)
            return f"inviato {local.strftime('%d/%m %H:%M')}"
        if key == "end":
            moment = dt_util.parse_datetime(str(value))
            return dt_util.as_local(moment).strftime("%H:%M") if moment else str(value)
        if key == "treatment_id":
            return next((t["name"] for t in self.treatments if t["id"] == value), str(value))
        if key == "operator_id":
            return (self._operator(value) or {}).get("name") or str(value)
        if key == "client_id":
            client = next((c for c in self.clients if c["id"] == value), None)
            if not client:
                return str(value)
            return " ".join(p for p in (client.get("first_name"), client.get("last_name")) if p) or str(value)
        if key == "status":
            return {STATUS_CONFIRMED: "confermata", STATUS_CANCELLED: "annullata", STATUS_PENDING: "da confermare"}.get(value, str(value))
        if key == "guest_type":
            return {"hotel": "ospite dell'hotel", "external": "esterno"}.get(value, str(value))
        if key == "extras":
            names = {item["id"]: item.get("name") or item["id"] for item in self.accessories}
            return ", ".join(names.get(item, item) for item in value)
        if key == "person":
            return "ospite principale" if not value else f"accompagnatore {value}"
        if isinstance(value, bool):
            return "sì" if value else "no"
        if key in ("list_price", "price", "paid_amount", "deposit_amount", "payments"):
            try:
                return _euro(float(value))
            except (TypeError, ValueError):
                return str(value)
        text = str(value).strip()
        return text if len(text) <= 80 else f"{text[:77]}…"

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
        preference: str = "",
    ) -> list[str]:
        """Return the operators to offer, in order, minus the refused ones.

        ``preference`` ("F" or "M") is the guest's wish for a woman or a man.
        It narrows an automatic choice (more than one candidate) to the
        operators of that gender; when none of them is free the booking is
        refused with a message for the desk rather than given to somebody
        else. A single operator picked by the desk is never second-guessed,
        and operators with no gender written in their card are not filtered.

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
        if preference in ("F", "M") and len(pool) > 1 and any(
            (self._operator(oid) or {}).get("gender") for oid in pool
        ):
            def busy(oid: str) -> bool:
                for other in self.appointments:
                    if other.get("operator_id") != oid or not occupies_slot(other):
                        continue
                    other_start = dt_util.parse_datetime(other["start"])
                    other_end = dt_util.parse_datetime(other["end"])
                    if other_start and other_end and other_start < end and start < other_end:
                        return True
                return False

            wanted = [
                oid
                for oid in available
                if (self._operator(oid) or {}).get("gender") == preference and not busy(oid)
            ]
            if not wanted:
                who = "massaggiatrice" if preference == "F" else "massaggiatore"
                local = dt_util.as_local(start)
                raise ValidationError(
                    f"L'ospite preferisce un{'a' if preference == 'F' else 'o'} {who}, ma nessun{'a' if preference == 'F' else ''} "
                    f"{who} è liber{'a' if preference == 'F' else 'o'} per '{treatment['name']}' "
                    f"alle {local.strftime('%H:%M')}: scegli l'operatore a mano o togli la preferenza"
                )
            return wanted
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
        treatment = next(
            (t for t in self.treatments if t["id"] == appointment.get("treatment_id")),
            None,
        )
        pause = self._treatment_pause_min(treatment) if treatment else 0
        for index in range(appointment.get("offer_index", 0) + 1, len(candidates)):
            operator_id = candidates[index]
            if self._slot_blocked(operator_id, start, end) or operator_id in closed:
                continue
            # Booked elsewhere since the offer started: asking her would only
            # end in a double booking.
            if self._operator_clash(
                operator_id, start, end, pause, exclude_ids={appointment.get("id")}
            ):
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
        if not category or FORCE_RULES.get():
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
                raise CategoryRuleError(
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
            raise CategoryRuleError(
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
            raise CategoryRuleError(
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

        Never forceable (2.9.1): «Prenota comunque» lifts the days and time
        windows of a category, never this rule — two categories that must not
        share time (spa privata and spa condivisa) can never be booked over
        each other.
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
                    raise CategoryRuleError(
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
        # Weekdays left open inside the range ("all November but Saturdays").
        skip = set(closure.get("skip_weekdays") or [])
        return [
            day.isoformat()
            for day in (first + timedelta(days=offset) for offset in range((last - first).days + 1))
            if day.weekday() not in skip
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
        skip = closure.get("skip_weekdays") or []
        if skip and len(days) > 1:
            when += f" ({skipped_days_words(skip)})"
        label = f" — {closure['label']}" if closure.get("label") else ""
        return f"{reason}{clock} {when}{label}"

    def _pause_min_for(self, appointment: dict[str, Any]) -> int:
        """Return the pause required after an appointment's category.

        The pause belongs to the appointment already on the book: it is what
        its masseuse needs before taking the next one. An appointment whose
        treatment was deleted since needs no pause (and must not make every
        later booking fail with "not found").
        """
        treatment = next(
            (t for t in self.treatments if t["id"] == appointment.get("treatment_id")),
            None,
        )
        return self._treatment_pause_min(treatment) if treatment else 0

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

    def _operator_clash(
        self,
        operator_id: str,
        start: datetime,
        end: datetime,
        pause_min: int = 0,
        planned: list[dict[str, Any]] | None = None,
        exclude_ids: set[str] | None = None,
    ) -> dict[str, Any] | None:
        """Return the appointment that keeps ``operator_id`` busy, if any.

        The pause works both ways: an existing appointment keeps the operator
        busy until its end plus its category's pause, and the new one needs
        its own pause before the next appointment starts. Before 2.1 only the
        first half was checked, so a massage ending at 10:00 could be booked
        right before one starting at 10:00.
        """
        start_utc = dt_util.as_utc(start)
        end_utc = dt_util.as_utc(end) + timedelta(minutes=max(0, pause_min))
        for appointment in [*self.appointments, *(planned or [])]:
            if appointment.get("operator_id") != operator_id:
                continue
            if exclude_ids and appointment.get("id") in exclude_ids:
                continue
            if not occupies_slot(appointment):
                continue
            other_start = dt_util.parse_datetime(appointment["start"])
            other_end = dt_util.parse_datetime(appointment["end"])
            if other_start is None or other_end is None:
                continue
            other_guard = dt_util.as_utc(other_end) + timedelta(
                minutes=self._pause_min_for(appointment)
            )
            if dt_util.as_utc(other_start) < end_utc and other_guard > start_utc:
                return appointment
        return None

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
        pause_min: int = 0,
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
        if operator_id:
            clash = self._operator_clash(operator_id, start, end, pause_min, planned)
            if clash is not None:
                return {"reason": "operator", **self.appointment_payload(clash)}
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
        forward_pause: bool = True,
        therapist_preference: str = "",
    ) -> tuple[dict[str, Any], dict[str, Any], bool]:
        """Validate one booking and return it without appending anything.

        ``forward_pause`` applies this treatment's own pause before the next
        appointment of the operator. An edit that keeps the same time and
        treatment passes False, so a back-to-back pair booked before the rule
        existed can still be edited (notes, payment) without being refused.

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
                treatment, start_dt, end_dt, requested, therapist_preference
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
            own_pause = self._treatment_pause_min(treatment) if forward_pause else 0
            # Offer first to whoever is actually free: a busy first choice
            # used to make the whole booking fail even with a colleague free.
            # When everybody is busy the first one stays, so the error below
            # names the appointment in the way.
            free = [
                oid
                for oid in candidates
                if self._operator_clash(oid, start_dt, end_dt, own_pause, planned)
                is None
            ]
            if free:
                candidates = free
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
            pause_min=self._treatment_pause_min(treatment) if forward_pause else 0,
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
        # One code per booking (2.8.8): every person and treatment of the same
        # booking shares the code of the first one.
        group_code = next(
            (
                existing["code"]
                for existing in (*(planned or []), *self.appointments)
                if batch_id and existing.get("batch_id") == batch_id and existing.get("code")
            ),
            "",
        )
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
                "vat_rate": self.vat_rate_of(treatment),
                # Which person of the party this is: 0 when nobody said, which
                # is both the leader of a party and the only person of a
                # booking made for one.
                "person": _norm_person(person_index),
                "batch_id": batch_id,
                "code": group_code or _new_code(used_codes),
                # Who confirmed it, and when. Empty on a pending booking: there
                # is nobody to name yet.
                "confirmed_by": "",
                "confirmed_at": "",
                # Who created this booking (user_id of the receptionist).
                "created_by": acting_person()[0]
                or (self._current_user_id if hasattr(self, "_current_user_id") else None),
                "created_by_name": acting_person()[1],
                "therapist_preference": therapist_preference if therapist_preference in ("F", "M") else "",
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
        therapist_preference: str = "",
        partner_id: str = "",
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
                therapist_preference=therapist_preference,
            )
            appointment["partner_id"] = self._partner_id_of(partner_id)
            self._apply_partner_discount(appointment)
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
        therapist_preference: str | None = None,
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
            previous_operator = appointment.get("operator_id") or ""

            # Memoria dell'offerta: viene conservata intatta se la modifica non
            # tocca fattori che la rendono inutile (trattamento, operatore o
            # orario). In quel caso l'offerta va ricostruita dalla booking rule.
            preserve_offer = (
                (treatment_id is None
                 or treatment_id == appointment.get("treatment_id"))
                and (operator_id is None
                     or str(operator_id) == str(appointment.get("operator_id") or ""))
                and (start is None
                     or str(start) == str(appointment.get("start") or ""))
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
                # A masseuse named by the desk wins over the old candidate
                # list (2.8.3): before, the old list was kept and the change
                # of operator was silently ignored.
                if not operator_ids and operator_id and not str(operator_id).startswith("@") and str(operator_id) != str(appointment.get("operator_id") or ""):
                    operator_ids = [str(operator_id)]
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
                    forward_pause=not _same_slot(appointment, treatment_id, start),
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
                    therapist_preference=(
                        appointment.get("therapist_preference", "")
                        if therapist_preference is None
                        else therapist_preference
                    ),
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

            # Preserve the offer state and candidate list (and deadline) when
            # the modification did not change treatment/operator/time: the
            # reception's "offerta in attesa" for the masseuse must survive an
            # ordinary edit. Otherwise leave the values computed by the booking
            # rules (the offer is rebuilt on its own).
            if preserve_offer:
                rebuilt["offer_state"] = appointment.get("offer_state", OFFER_NONE)
                rebuilt["offer_candidates"] = list(
                    appointment.get("offer_candidates") or []
                )
                rebuilt["offer_index"] = appointment.get("offer_index", 0)
                rebuilt["offer_expires_at"] = appointment.get(
                    "offer_expires_at", ""
                )

            if is_new_client:
                self.clients.append(client)
            self.appointments.insert(index, rebuilt)
            await self._async_save()

        # The deposit request is never sent on its own: the desk decides after
        # the edit, from the confirmation prompt or the appointment popup.
        payload = self.appointment_payload(rebuilt)
        if not preserve_offer:
            await self._async_notify_reassigned(payload, previous_operator)
        return payload

    async def _async_notify_reassigned(
        self, payload: dict[str, Any], previous_operator: str
    ) -> None:
        """Tell the operators when an edit changed who does the treatment (2.8.3).

        The new masseuse gets the request to accept, exactly as for a new
        booking; the one who had it is told it is no longer hers. Before, a
        change of operator (or of time) rebuilt the offer silently and nobody
        was asked.
        """
        current = (payload.get("operator") or {}).get("id") or ""
        if payload.get("offer_state") == OFFER_PENDING and current:
            await self._async_notify_operator(payload, offer=True)
        elif current and current != previous_operator:
            await self._async_notify_operator(payload, "Appuntamento assegnato")
        if previous_operator and previous_operator != current:
            record = self._operator(previous_operator)
            if record:
                await self._async_notify_operator(
                    {**payload, "operator": {"id": previous_operator, "name": record.get("name", "")}},
                    "Appuntamento non più assegnato a te",
                    show_operator=False,
                )

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
        # The masseuse picked in the edit is the anchor's: each person of the
        # party keeps her own (two people cannot share one masseuse).
        others = {key: value for key, value in fields.items() if key not in ("operator_id", "operator_ids")}
        for member_id in member_ids:
            updated.append(await self.async_update_appointment(
                member_id, **(fields if member_id == anchor["id"] else others)))
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
            # 2.8.9: a person split off is a booking of her own.
            and (other.get("batch_id") or "") == (appointment.get("batch_id") or "")
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
                self._voucher_release(appointment)

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
        # Shop packages (2.8.9): each treatment gets its share of the price.
        self._share_package_prices(
            [(str(row.get("treatment_id") or ""), entry) for row in rows for entry in row.get("entries") or []
             if isinstance(entry, dict)]
        )

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
                            therapist_preference=str(entry.get("therapist_preference") or ""),
                        )
                        # The partner who brought the party (2.5.0).
                        appointment["partner_id"] = self._partner_id_of(row.get("partner_id"))
                        self._apply_package(appointment, entry)
                        self._apply_partner_discount(appointment)
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
                for _appointment, client, is_new in prepared:
                    if is_new:
                        self.clients.append(client)
                self.appointments.extend(item[0] for item in prepared)
                if voucher is not None:
                    self._voucher_settle(voucher, [item[0] for item in prepared])
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
        """Return a voucher with its derived expiry flag and the credit left."""
        expires = _norm_date(voucher.get("expires_on"))
        expired = bool(expires) and dt_util.now().date() > datetime.strptime(
            expires, "%Y-%m-%d"
        ).date()
        return {**copy.deepcopy(voucher), "expired": expired, "credit_left": self._voucher_credit(voucher)}

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
        # A voucher from the shop whose product is not paired yet (or paired
        # with accessories only) only records the code: the desk books what
        # the guest bought (2.7.0).
        # A gift card only (or treatments already taken, 2.8.1): it is credit,
        # anything can be booked with it.
        if voucher.get("treatments_redeemed") or not any(p["treatment_ids"] for p in voucher["people"]):
            return
        # Every person of the voucher must find her treatments in one booked
        # person; more treatments, accessories or people are allowed and are
        # paid as balance (2.8.1; before, it had to match exactly).
        free = [list(ids) for ids in booked.values()]
        for person in sorted((p for p in voucher["people"] if p["treatment_ids"]), key=lambda p: -len(p["treatment_ids"])):
            match = next((ids for ids in free if all(ids.count(t) >= person["treatment_ids"].count(t) for t in person["treatment_ids"])), None)
            if match is None:
                names = {t["id"]: t["name"] for t in self.treatments}
                wanted = ", ".join(names.get(t, t) for t in person["treatment_ids"])
                raise ValidationError(
                    f"La prenotazione non corrisponde al voucher {voucher['code']}: manca {wanted}"
                    + (f" per {person['name']}" if person.get("name") else "")
                )
            free.remove(match)

    def _voucher_credit(self, voucher: dict[str, Any]) -> float:
        """The gift card credit still to spend on a voucher."""
        total = sum(float(p.get("gift_card_amount") or 0) for p in voucher.get("people") or [])
        return round(max(0.0, total - float(voucher.get("credit_used") or 0)), 2)

    def _voucher_settle(self, voucher: dict[str, Any], appointments: list[dict[str, Any]]) -> None:
        """The voucher pays the booking (2.8.1), as takings on its appointments.

        Its treatments (and the accessories in the package) are paid in full
        with a «Voucher» taking; then the gift card credit pays what is still
        owed, a «Gift card» taking per appointment, up to the credit. What is
        left is the balance the guest pays at the desk; credit left over stays
        on the voucher for the next visit. Called with the lock held.
        """
        today = dt_util.now().date().isoformat()
        prices = {t["id"]: float(t.get("price") or 0) for t in self.treatments}
        accessories = {a.get("id"): float(a.get("price") or 0) for a in self.accessories if isinstance(a, dict)}
        if not voucher.get("treatments_redeemed"):
            treatments = [t for p in voucher["people"] for t in p["treatment_ids"]]
            extras = [e for p in voucher["people"] for e in p.get("extras") or []]
        else:
            treatments, extras = [], []
        had_treatments = bool(treatments)

        def take(appointment: dict[str, Any], method: str, amount: float) -> None:
            if amount <= 0:
                return
            appointment.setdefault("payments", []).append({
                "id": _new_id("pay"), "method": method, "date": today, "amount": round(amount, 2),
                "voucher_id": voucher["id"], "voucher_code": voucher["code"],
            })

        for appointment in appointments:
            covered = 0.0
            if appointment.get("treatment_id") in treatments:
                treatments.remove(appointment["treatment_id"])
                agreed = appointment.get("price")
                if agreed is None:
                    agreed = appointment.get("list_price")
                covered += float(prices.get(appointment["treatment_id"], 0) if agreed is None else agreed)
            for extra in appointment.get("extras") or []:
                if extra in extras:
                    extras.remove(extra)
                    covered += accessories.get(extra, 0.0)
            take(appointment, "voucher", covered)
        credit = self._voucher_credit(voucher)
        used = 0.0
        for appointment in appointments:
            if credit - used <= 0:
                break
            due = self._payment_totals(appointment)["due"]
            amount = round(min(due, credit - used), 2)
            take(appointment, "gift_card", amount)
            used += amount
        voucher["credit_used"] = round(float(voucher.get("credit_used") or 0) + used, 2)
        if had_treatments:
            voucher["treatments_redeemed"] = True
        voucher["appointment_ids"] = [*voucher.get("appointment_ids", []), *(a["id"] for a in appointments)]
        if self._voucher_credit(voucher) <= 0.004:
            voucher["status"] = VOUCHER_REDEEMED
            voucher["redeemed_at"] = dt_util.utcnow().isoformat()

    def _voucher_release(self, appointment: dict[str, Any]) -> None:
        """A cancelled appointment gives back what its voucher paid (2.8.1)."""
        kept = []
        for item in appointment.get("payments") or []:
            voucher = next((v for v in self.vouchers if v["id"] == item.get("voucher_id")), None) if item.get("voucher_id") else None
            if voucher is None:
                kept.append(item)
                continue
            if item.get("method") == "gift_card":
                voucher["credit_used"] = round(max(0.0, float(voucher.get("credit_used") or 0) - float(item.get("amount") or 0)), 2)
            else:
                voucher["treatments_redeemed"] = False
            voucher["appointment_ids"] = [i for i in voucher.get("appointment_ids", []) if i != appointment["id"]]
            if not voucher.get("wp_redeemed"):
                voucher["status"] = VOUCHER_ACTIVE
                voucher["redeemed_at"] = ""
        appointment["payments"] = kept

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
        created_by_name: str = "",
    ) -> dict[str, Any]:
        """Sell a gift voucher: its code, its people and its treatments, valid for months."""
        created_by_name = str(created_by_name or "").strip()
        if not created_by_name:
            raise ValidationError("Indica chi ha creato il voucher")
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
                    "created_by": user_id or "",
                    "created_by_name": created_by_name,
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

    # ---------------------------------------------------------------- email

    async def async_send_email(
        self, to: list[str] | str, subject: str, body: str, html: str | None = None
    ) -> dict[str, Any]:
        """Send an email with the mailbox of Configurazione › Email (2.4.1)."""
        settings = self._data.get(KEY_SETTINGS, {})
        if not settings.get("email_enabled"):
            raise ValidationError("L'invio email è spento: attivalo in Configurazione › Email")
        result = await self._async_deliver_email(to, subject, body, html)
        if not result.get("sent"):
            _LOGGER.warning("Email non inviata: %s", result.get("error"))
        return result

    async def _async_deliver_email(
        self, to: list[str] | str, subject: str, body: str, html: str | None = None
    ) -> dict[str, Any]:
        """Through Gmail («Accedi con Google», 2.4.2) or through SMTP."""
        settings = self._data.get(KEY_SETTINGS, {})
        if settings.get("email_method") != "google":
            return await email_sender.async_send_email(self.hass, settings, to, subject, body, html)
        recipients = [to] if isinstance(to, str) else list(to)
        recipients = [r.strip() for r in recipients if r and "@" in r]
        if not recipients:
            return {"sent": False, "error": "Nessun indirizzo email valido a cui inviare."}
        account = str(settings.get("google_account") or "")
        if not settings.get("google_refresh_token") or not account:
            return {"sent": False, "error": "Nessun account Google collegato: premi «Accedi con Google»."}
        config = {
            **email_sender.email_config(settings),
            "from_address": str(settings.get("email_from") or "").strip() or account,
        }
        message = email_sender.build_message(config, recipients, subject, body, html)
        try:
            token = await self._async_google_token()
            await google_auth.gmail_send(self._http_session(), token, message.as_bytes())
        except google_auth.GoogleAuthError as err:
            return {"sent": False, "error": str(err)}
        return {"sent": True, "to": recipients}

    async def async_test_email(self, to: str = "") -> dict[str, Any]:
        """A test email, by default to the sender's own mailbox."""
        settings = self._data.get(KEY_SETTINGS, {})
        google = settings.get("email_method") == "google"
        config = email_sender.email_config(settings)
        sender = (str(settings.get("email_from") or "").strip() or str(settings.get("google_account") or "")) if google else config["from_address"]
        target = (to or "").strip() or sender
        how = f"Gmail ({settings.get('google_account')})" if google else f"{config['host']}:{config['port']} ({config['security']})"
        body = "\n".join([
            "Ciao!",
            "",
            "Questa è un'email di prova di Spa Booking: se la leggi, l'invio da",
            f"{sender} funziona.",
            "",
            f"Inviata con: {how}",
        ])
        return await self._async_deliver_email(target, "Prova email Spa Booking", body)

    # ---------------------------------------------------- «Accedi con Google»

    def _http_session(self) -> Any:
        from homeassistant.helpers.aiohttp_client import async_get_clientsession

        return async_get_clientsession(self.hass)

    def _google_pending(self) -> dict[str, Any]:
        if not hasattr(self, "_google_logins"):
            self._google_logins: dict[str, Any] = {}
        return self._google_logins

    async def async_google_auth_url(self, redirect_uri: str, purpose: str = "email") -> dict[str, Any]:
        """Start «Accedi con Google»: the page to open, for this redirect address."""
        settings = self._data.get(KEY_SETTINGS, {})
        client_id = str(settings.get("google_client_id") or "")
        if not client_id or not settings.get("google_client_secret"):
            raise ValidationError("Inserisci e salva Client ID e Client secret del progetto Google")
        redirect_uri = str(redirect_uri or "").strip()
        if not redirect_uri.endswith(google_auth.CALLBACK_PATH):
            raise ValidationError("Indirizzo di ritorno non valido")
        if not (redirect_uri.startswith("https://") or redirect_uri.startswith("http://localhost")
                or redirect_uri.startswith("http://127.0.0.1")):
            raise ValidationError(
                "Google accetta solo indirizzi https: apri Home Assistant dal suo indirizzo esterno "
                "(es. Nabu Casa o il tuo dominio) e riprova"
            )
        drive = purpose == "drive"
        state = google_auth.new_state(self._google_pending(), redirect_uri, "drive" if drive else "email")
        return {
            "url": google_auth.auth_url(client_id, redirect_uri, state, str(settings.get("google_account") or ""),
                                        google_auth.SCOPES_DRIVE if drive else google_auth.SCOPES),
            "redirect_uri": redirect_uri,
        }

    async def async_google_callback(self, state: str, code: str) -> str:
        """Google came back: keep the refresh token and the account. Returns the address."""
        pending = self._google_pending().pop(state, None) if state else None
        if pending is None or pending.expires < time_module.time():
            raise google_auth.GoogleAuthError("Accesso scaduto o non riconosciuto: riprova da Spa Booking.")
        if not code:
            raise google_auth.GoogleAuthError("Google non ha mandato il codice di accesso: riprova.")
        settings = self._data.get(KEY_SETTINGS, {})
        tokens = await google_auth.exchange_code(
            self._http_session(), str(settings.get("google_client_id") or ""),
            str(settings.get("google_client_secret") or ""), code, pending.redirect_uri,
        )
        refresh = str(tokens.get("refresh_token") or "")
        if not refresh:
            raise google_auth.GoogleAuthError("Google non ha dato l'accesso permanente: riprova e accetta tutti i permessi.")
        scope = str(tokens.get("scope") or "")
        drive = pending.purpose == "drive"
        if drive and "drive.file" not in (scope or "drive.file"):
            raise google_auth.GoogleAuthError("Non hai spuntato il permesso Google Drive: riprova e spuntalo.")
        if not drive and "gmail.send" not in (scope or "gmail.send"):
            raise google_auth.GoogleAuthError("Non hai spuntato il permesso «Inviare email per tuo conto»: riprova e spuntalo.")
        account = google_auth.email_of_id_token(str(tokens.get("id_token") or ""))
        async with self._lock:
            current = self._data[KEY_SETTINGS]
            current["google_refresh_token"] = refresh
            current["google_account"] = account
            current["google_scopes"] = scope
            # Connecting Drive does not change how the email goes out (2.8.0).
            if not drive:
                current["email_method"] = "google"
            await self._async_save()
        self._google_access = (str(tokens.get("access_token") or ""), time_module.time() + float(tokens.get("expires_in") or 3600) - 60)
        if drive:
            return "drive:" + (account or "il tuo account Google")
        return account or "il tuo account Google"

    async def _async_google_token(self) -> str:
        """A valid access token, refreshed when needed."""
        cached = getattr(self, "_google_access", None)
        if cached and cached[0] and cached[1] > time_module.time():
            return cached[0]
        settings = self._data.get(KEY_SETTINGS, {})
        token, expires = await google_auth.refresh_access(
            self._http_session(), str(settings.get("google_client_id") or ""),
            str(settings.get("google_client_secret") or ""), str(settings.get("google_refresh_token") or ""),
        )
        self._google_access = (token, expires)
        return token

    async def async_google_disconnect(self) -> dict[str, Any]:
        """Forget the Google account and withdraw the permission on Google."""
        settings = self._data.get(KEY_SETTINGS, {})
        refresh = str(settings.get("google_refresh_token") or "")
        if refresh:
            await google_auth.revoke(self._http_session(), refresh)
        async with self._lock:
            current = self._data[KEY_SETTINGS]
            current["google_refresh_token"] = ""
            current["google_account"] = ""
            current["google_scopes"] = ""
            await self._async_save()
        self._google_access = None
        return {"disconnected": True}

    # ------------------------------------------------- Google Drive backups

    def _gdrive_ready(self) -> None:
        settings = self._data.get(KEY_SETTINGS, {})
        if not settings.get("google_refresh_token"):
            raise ValidationError("Collega prima Google Drive (Impostazioni › Dati e backup)")
        if "drive.file" not in str(settings.get("google_scopes") or ""):
            raise ValidationError("Manca il permesso Google Drive: premi «Collega Google Drive»")

    async def async_gdrive_backup(self, reason: str = "") -> dict[str, Any]:
        """Write today's backup to Drive and keep the newest three."""
        self._gdrive_ready()
        session = self._http_session()
        today = dt_util.now().date().isoformat()
        name = f"{gdrive_backup.PREFIX}{today}.json"
        try:
            token = await self._async_google_token()
            settings = self._data.get(KEY_SETTINGS, {})
            folder = await gdrive_backup.ensure_folder(session, token, str(settings.get("gdrive_folder_id") or ""))
            files = await gdrive_backup.list_backups(session, token, folder)
            same_day = next((f for f in files if f.get("name") == name), None)
            payload = json.dumps(self.export_data(), ensure_ascii=False, indent=1).encode()
            saved = await gdrive_backup.upload(session, token, folder, name, payload, same_day["id"] if same_day else "")
            files = await gdrive_backup.list_backups(session, token, folder)
            removed = []
            for old in gdrive_backup.to_delete(files):
                await gdrive_backup.delete(session, token, old["id"])
                removed.append(old.get("name"))
        except google_auth.GoogleAuthError as err:
            async with self._lock:
                self._data[KEY_SETTINGS]["gdrive_last_error"] = str(err)
                self._data[KEY_SETTINGS]["gdrive_last_try"] = dt_util.utcnow().isoformat()
                await self._async_save()
            raise ValidationError(str(err)) from err
        async with self._lock:
            current = self._data[KEY_SETTINGS]
            current["gdrive_folder_id"] = folder
            current["gdrive_last_backup"] = dt_util.utcnow().isoformat()
            current["gdrive_last_file"] = name
            current["gdrive_last_size"] = len(payload)
            current["gdrive_last_error"] = ""
            current["gdrive_last_try"] = current["gdrive_last_backup"]
            await self._async_save()
        return {"ok": True, "file": saved.get("name") or name, "size": len(payload), "replaced": bool(same_day),
                "removed": removed, "reason": reason}

    async def async_gdrive_list(self) -> dict[str, Any]:
        """The backups on Drive, newest first."""
        self._gdrive_ready()
        folder = str(self._data.get(KEY_SETTINGS, {}).get("gdrive_folder_id") or "")
        if not folder:
            return {"files": []}
        try:
            token = await self._async_google_token()
            files = await gdrive_backup.list_backups(self._http_session(), token, folder)
        except google_auth.GoogleAuthError as err:
            raise ValidationError("La cartella dei backup non c'è più su Drive" if str(err) == "not_found" else str(err)) from err
        files.sort(key=lambda f: str(f.get("name") or ""), reverse=True)
        return {"files": files}

    async def async_gdrive_restore(self, file_id: str) -> dict[str, Any]:
        """Replace the data with a backup from Drive."""
        self._gdrive_ready()
        try:
            token = await self._async_google_token()
            raw = await gdrive_backup.download(self._http_session(), token, file_id)
            payload = json.loads(raw.decode("utf-8"))
        except google_auth.GoogleAuthError as err:
            raise ValidationError(str(err)) from err
        except (ValueError, UnicodeDecodeError) as err:
            raise ValidationError("Il file su Drive non è un backup valido") from err
        return await self.async_import_data(payload)

    async def async_gdrive_tick(self) -> dict[str, Any]:
        """Once a day, at the chosen time (or later the same day if the box was off)."""
        settings = self._data.get(KEY_SETTINGS, {})
        if not settings.get("gdrive_enabled"):
            return {"skipped": "spento"}
        now = dt_util.now()
        if now.strftime("%H:%M") < str(settings.get("gdrive_time") or "03:30"):
            return {"skipped": "non ancora"}
        last = str(settings.get("gdrive_last_backup") or "")
        if last and dt_util.as_local(dt_util.parse_datetime(last)).date() == now.date():
            return {"skipped": "già fatto oggi"}
        # After a failure, try again an hour later, not every five minutes.
        tried = str(settings.get("gdrive_last_try") or "")
        if tried and settings.get("gdrive_last_error"):
            when = dt_util.parse_datetime(tried)
            if when and (dt_util.utcnow() - when).total_seconds() < 3600:
                return {"skipped": "riprovo più tardi"}
        try:
            return await self.async_gdrive_backup(reason="automatico")
        except ValidationError as err:
            return {"error": str(err)}

    # ------------------------------------------------------- loyalty points

    def _voucher_value(self, voucher: dict[str, Any]) -> float:
        """What a sold voucher is worth: its treatments at list price plus gift cards."""
        prices = {t["id"]: float(t.get("price") or 0) for t in self.treatments}
        total = 0.0
        for person in voucher.get("people") or []:
            total += sum(prices.get(tid, 0.0) for tid in person.get("treatment_ids") or [])
            total += float(person.get("gift_card_amount") or 0)
        return round(total, 2)

    def loyalty_of(self, client: dict[str, Any]) -> dict[str, Any]:
        """The points of one client (2.4.0).

        Earned = euro paid on her appointments that are not cancelled (paid by
        voucher or gift card excluded: the purchase earned them already) plus
        the vouchers she bought (matched by phone), times the points per euro.
        Balance = earned + corrections − spent on rewards.
        """
        settings = self._data.get(KEY_SETTINGS, {})
        rate = float(settings.get("loyalty_points_per_euro") or 0)
        paid = 0.0
        for appointment in self.appointments:
            if appointment.get("client_id") != client["id"] or appointment.get("status") == "cancelled":
                continue
            for item in appointment.get("payments") or []:
                if item.get("method") in ("voucher", "gift_card"):
                    continue
                paid += float(item.get("amount") or 0)
        bought = 0.0
        phone = str(client.get("phone") or "")
        if phone:
            for voucher in self.vouchers:
                if voucher.get("source") or not voucher.get("buyer_phone"):
                    continue
                if _same_phone(voucher["buyer_phone"], phone):
                    bought += self._voucher_value(voucher)
        earned = int(math.floor((paid + bought) * rate + 1e-9))
        adjust = int(client.get("loyalty_adjust") or 0)
        spent = int(client.get("loyalty_spent") or 0)
        threshold = int(settings.get("loyalty_threshold") or 0)
        balance = earned + adjust - spent
        return {
            "earned": earned, "adjust": adjust, "spent": spent, "balance": balance,
            "paid": round(paid, 2), "bought": round(bought, 2),
            "threshold": threshold, "ready": bool(threshold) and balance >= threshold,
        }

    def loyalty_summary(self) -> dict[str, dict[str, Any]]:
        """The points of every client with any, for the card."""
        out: dict[str, dict[str, Any]] = {}
        for client in self.clients:
            info = self.loyalty_of(client)
            if info["earned"] or info["adjust"] or info["spent"]:
                out[client["id"]] = info
        return out

    def format_loyalty_message(self, client: dict[str, Any], voucher: dict[str, Any], points: int) -> str:
        """The WhatsApp text that carries the reward voucher."""
        settings = self._data.get(KEY_SETTINGS, {})
        template = str(settings.get("loyalty_message") or "").strip() or DEFAULT_LOYALTY_MESSAGE
        value = self._voucher_value(voucher)
        return (
            template.replace("{nome}", str(client.get("first_name") or "").strip() or "ospite")
            .replace("{cognome}", str(client.get("last_name") or "").strip())
            .replace("{codice}", voucher.get("code") or "")
            .replace("{valore}", f"{value:.2f} €".replace(".", ","))
            .replace("{punti}", str(points))
            .replace("{scadenza}", _date_it(voucher.get("expires_on") or ""))
        )

    async def async_loyalty_reward(
        self, client_id: str, by: str = "", send: bool = True
    ) -> dict[str, Any]:
        """Turn the threshold of points into a voucher worth the reward, and send it.

        The points are taken at once (before the message goes), so a second
        call cannot give two vouchers for the same points.
        """
        settings = self._data.get(KEY_SETTINGS, {})
        client = self._find(self.clients, client_id, "Cliente")
        info = self.loyalty_of(client)
        threshold = int(settings.get("loyalty_threshold") or 0)
        reward = float(settings.get("loyalty_reward") or 0)
        if not threshold or reward <= 0:
            raise ValidationError("Imposta soglia e valore del premio in Promo › Punti fedeltà")
        if info["balance"] < threshold:
            raise ValidationError(
                f"Servono {threshold} punti: {self.full_name(client)} ne ha {info['balance']}"
            )
        voucher = await self.async_create_voucher(
            "Punti fedeltà", "", self.full_name(client), str(client.get("phone") or ""),
            [{"name": self.full_name(client), "treatment_ids": [], "gift_card_amount": reward}],
            None, by or "Punti fedeltà",
        )
        async with self._lock:
            stored = self._find(self.vouchers, voucher["id"], "Voucher")
            stored["source"] = "punti"
            stored["client_id"] = client_id
            client["loyalty_spent"] = int(client.get("loyalty_spent") or 0) + threshold
            client.setdefault("loyalty_log", []).append({
                "at": dt_util.utcnow().isoformat(), "kind": "premio", "points": -threshold,
                "note": f"Buono da {reward:.2f} €".replace(".", ","), "code": stored["code"], "by": by,
            })
            await self._async_save()
        sent = False
        error = ""
        chat_id = messaging.whatsapp_chat_id(str(client.get("phone") or ""))
        if send and chat_id:
            try:
                result = await messaging.async_send_whatsapp(
                    self.hass, chat_id, self.format_loyalty_message(client, stored, threshold), waha=self.waha
                )
                sent = bool(result.get("sent"))
                error = str(result.get("error") or "")
            except Exception as err:  # noqa: BLE001
                error = str(err)
        elif send:
            error = "il cliente non ha un numero WhatsApp"
        return {"voucher": self.voucher_payload(stored), "sent": sent, "error": error,
                "loyalty": self.loyalty_of(client)}

    async def async_loyalty_adjust(
        self, client_id: str, points: int, note: str = "", by: str = ""
    ) -> dict[str, Any]:
        """A correction of points by the desk (a bonus, or points taken back)."""
        points = _norm_signed(points)
        if not points:
            raise ValidationError("Indica quanti punti aggiungere o togliere")
        async with self._lock:
            client = self._find(self.clients, client_id, "Cliente")
            client["loyalty_adjust"] = int(client.get("loyalty_adjust") or 0) + points
            client.setdefault("loyalty_log", []).append({
                "at": dt_util.utcnow().isoformat(), "kind": "rettifica", "points": points,
                "note": str(note or "").strip(), "code": "", "by": by,
            })
            await self._async_save()
        return {"loyalty": self.loyalty_of(client)}

    async def async_loyalty_tick(self) -> dict[str, Any]:
        """Automatic rewards: every client over the threshold gets her voucher."""
        settings = self._data.get(KEY_SETTINGS, {})
        if not settings.get("loyalty_enabled") or not settings.get("loyalty_auto"):
            return {"rewards": 0, "reason": "premi automatici spenti"}
        rewards = 0
        for client in list(self.clients):
            if not client.get("phone"):
                continue
            # One reward per client per tick: the next tick gives the next one.
            if self.loyalty_of(client)["ready"]:
                try:
                    await self.async_loyalty_reward(client["id"], "Automatico")
                    rewards += 1
                except ValidationError:
                    continue
        return {"rewards": rewards}

    # ------------------------------------------------------------- partners

    @property
    def partners(self) -> list[dict[str, Any]]:
        """The partners who promote the spa (2.4.0)."""
        return self._data.setdefault(KEY_PARTNERS, [])

    async def async_save_partner(self, data: dict[str, Any]) -> dict[str, Any]:
        """Add a partner or change one; each gets a code PRT-XXXX."""
        async with self._lock:
            partner_id = str(data.get("id") or "")
            current = next((p for p in self.partners if p["id"] == partner_id), None) if partner_id else None
            if partner_id and current is None:
                raise ValidationError("Partner non trovato")
            merged = {**(current or {}), **data}
            if not str(merged.get("first_name") or "").strip() and not str(merged.get("company") or "").strip():
                raise ValidationError("Indica almeno il nome o l'attività del partner")
            codes = {p["code"] for p in self.partners if p is not current}
            code = str(data.get("code") or (current or {}).get("code") or "").strip().upper()
            if not code:
                while True:
                    code = "PRT-" + secrets.token_hex(2).upper()
                    if code not in codes:
                        break
            elif code in codes:
                raise ValidationError(f"Il codice {code} è già di un altro partner")
            if current is not None and "subscribed" in data and bool(data.get("subscribed")) != current.get("subscribed", True):
                data = {**data, "unsubscribed_at": "" if data.get("subscribed") else dt_util.utcnow().isoformat()}
            record = _norm_partner({**(current or {}), **data, "code": code,
                                    **({"id": current["id"], "created_at": current["created_at"]} if current else {})})
            if current is not None:
                current.clear()
                current.update(record)
            else:
                self.partners.append(record)
            await self._async_save()
        return {"partner": record}

    def vat_rate_of(self, treatment: dict[str, Any] | None) -> float:
        """The VAT rate of a treatment: its own, else the default (2.5.1)."""
        own = (treatment or {}).get("vat_rate")
        if own is not None:
            return float(own)
        return float(self._data.get(KEY_SETTINGS, {}).get("vat_default", 22.0))

    @staticmethod
    def vat_split(gross: float, rate: float) -> tuple[float, float]:
        """Taxable amount and VAT inside a VAT-included price."""
        taxable = round(gross / (1 + rate / 100), 2) if rate else round(gross, 2)
        return taxable, round(gross - taxable, 2)

    def _partner_id_of(self, value: Any) -> str:
        """A partner's id from her id or her code (any case); "" if unknown."""
        key = str(value or "").strip()
        if not key:
            return ""
        for partner in self.partners:
            if partner["id"] == key or partner.get("code", "").upper() == key.upper():
                return partner["id"]
        return ""

    def _booked_value(self, appointment: dict[str, Any]) -> float:
        """What a booking is worth: the agreed price, else the list price."""
        for key in ("price", "list_price"):
            if appointment.get(key) is not None:
                try:
                    return float(appointment[key])
                except (TypeError, ValueError):
                    pass
        treatment = next((t for t in self.treatments if t["id"] == appointment.get("treatment_id")), None)
        return float((treatment or {}).get("price") or 0)

    def partner_points_of(self, partner: dict[str, Any]) -> dict[str, Any]:
        """A partner's points (2.5.0): euro booked by her guests × the rate.

        Worked out from the appointments every time, so a cancelled booking
        loses its points by itself.
        """
        rate = float(self._data.get(KEY_SETTINGS, {}).get("partner_points_per_euro") or 0)
        booked = 0.0
        bookings = 0
        for appointment in self.appointments:
            if appointment.get("partner_id") != partner["id"] or appointment.get("status") == "cancelled":
                continue
            booked += self._booked_value(appointment)
            bookings += 1
        earned = int(math.floor(booked * rate + 1e-9))
        adjust = int(partner.get("points_adjust") or 0)
        spent = int(partner.get("points_spent") or 0)
        return {"earned": earned, "adjust": adjust, "spent": spent, "balance": earned + adjust - spent,
                "booked": round(booked, 2), "bookings": bookings}

    def treatment_rank(self) -> tuple[dict[str, int], dict[str, int]]:
        """Positions of categories and treatments as set in Configurazione › Trattamenti (2.8.12)."""
        settings = self._data.get(KEY_SETTINGS, {})
        columns = settings.get("categories_order") or {}
        cats = [*(columns.get("left") or []), *(columns.get("right") or [])]
        return ({c: i for i, c in enumerate(cats)},
                {t: i for i, t in enumerate(settings.get("treatments_order") or [])})

    def shop_packages(self, min_people: int = 1) -> list[dict[str, Any]]:
        """The shop products paired with treatments, as bookable packages (2.8.9).

        Each has its price (the shop's), how many people it is for, and the
        treatments and accessories every one of them gets.
        """
        settings = self._data.get(KEY_SETTINGS, {})
        mapping = settings.get("wp_product_map") or {}
        known = {t["id"] for t in self.treatments if t.get("active", True)}
        out = []
        hidden_web = set(settings.get("package_hidden_web") or [])
        hidden_desk = set(settings.get("package_hidden_desk") or [])
        # In the order set in Configurazione › Pacchetti (2.8.12).
        order = list(settings.get("package_order") or [])
        rank = {key: index for index, key in enumerate(order)}
        products = sorted(settings.get("wp_products") or [], key=lambda p: rank.get(p.get("key"), len(order)))
        for product in products:
            entry = mapping.get(product.get("key")) or {}
            treatments = [t for t in entry.get("treatment_ids") or [] if t in known]
            if not treatments or len(treatments) != len(entry.get("treatment_ids") or []):
                continue
            people = max(1, int(entry.get("people") or 1))
            if people < min_people:
                continue
            out.append({
                "key": product["key"],
                "name": product.get("name") or "",
                "price": product.get("price"),
                "people": people,
                "treatment_ids": treatments,
                "extras": [e for e in entry.get("extras") or [] if e],
                "note": str(entry.get("note") or ""),
                "image": product.get("image") or "",
                "hidden_web": product["key"] in hidden_web,
                "hidden_desk": product["key"] in hidden_desk,
            })
        return out

    def _share_package_prices(self, items: list[tuple[str, dict[str, Any]]]) -> None:
        """Share each booked package's price among its treatments (2.8.9).

        ``items`` are (treatment id, entry) pairs. Entries of the same
        ``package_group`` without a price of their own split the shop price
        by the weight of each treatment's list price (equal parts when there
        is none); the last one takes the rounding cents.
        """
        packages = {p["key"]: p for p in self.shop_packages()}
        prices = {t["id"]: float(t.get("price") or 0) for t in self.treatments}
        groups: dict[str, list[tuple[str, dict[str, Any]]]] = {}
        for treatment_id, entry in items:
            key = entry.get("package_key")
            if key and entry.get("price") is None:
                groups.setdefault(str(entry.get("package_group") or key), []).append((treatment_id, entry))
        for members in groups.values():
            package = packages.get(members[0][1].get("package_key"))
            if not package or package.get("price") is None:
                continue
            total = float(package["price"])
            weights = [prices.get(t, 0.0) for t, _ in members]
            whole = sum(weights)
            shares = [round(total * (w / whole if whole else 1 / len(members)), 2) for w in weights]
            shares[-1] = round(total - sum(shares[:-1]), 2)
            for (_t, entry), share in zip(members, shares, strict=True):
                entry["price"] = max(0.0, share)

    def _package_extras(self, key: Any) -> list[str]:
        """The accessories included in a shop package (2.8.9)."""
        if not key:
            return []
        entry = (self._data.get(KEY_SETTINGS, {}).get("wp_product_map") or {}).get(str(key)) or {}
        return [str(e) for e in entry.get("extras") or [] if e]

    def _apply_package(self, appointment: dict[str, Any], entry: dict[str, Any]) -> None:
        """Mark a treatment as part of a shop package (2.8.9): name, group, accessories included."""
        key = str(entry.get("package_key") or "")
        if not key:
            for field in ("package_key", "package_group", "package_name", "extras_included"):
                appointment.pop(field, None)
            return
        product = next((p for p in self._data.get(KEY_SETTINGS, {}).get("wp_products") or [] if p.get("key") == key), {})
        appointment["package_key"] = key
        appointment["package_group"] = str(entry.get("package_group") or key)
        appointment["package_name"] = str(product.get("name") or entry.get("package_name") or "Pacchetto")
        appointment["extras_included"] = True

    def partner_discount_of(self, partner_id: str) -> float:
        """The discount (%) of the guests who book with this partner (2.8.6)."""
        partner = next((p for p in self.partners if p["id"] == partner_id), None)
        if partner is None or partner.get("active") is False:
            return 0.0
        own = partner.get("discount_pct")
        if own is not None:
            return float(own)
        return float(self._data.get(KEY_SETTINGS, {}).get("partner_discount_pct") or 0)

    def _apply_partner_discount(self, appointment: dict[str, Any]) -> None:
        """Lower the price of a booking that came with a partner's code (2.8.6).

        Only a price nobody agreed by hand: the list price less the partner
        discount, remembered as ``partner_discount_pct`` so a partner taken
        off the booking gives the list price back. A price the desk typed
        stays as it is.
        """
        pct = self.partner_discount_of(appointment.get("partner_id") or "")
        applied = appointment.get("partner_discount_pct")
        if applied:
            # Undo the previous discount first (partner changed or removed).
            appointment["price"] = None
            appointment.pop("partner_discount_pct", None)
        elif appointment.get("price") is not None:
            return
        if pct <= 0:
            return
        listed = appointment.get("list_price")
        if listed is None:
            treatment = next((t for t in self.treatments if t["id"] == appointment.get("treatment_id")), None)
            listed = (treatment or {}).get("price")
        try:
            listed = float(listed)
        except (TypeError, ValueError):
            return
        if listed <= 0:
            return
        appointment["price"] = round(listed * (1 - pct / 100), 2)
        appointment["partner_discount_pct"] = pct

    def partner_detail(self, partner_id: str) -> dict[str, Any]:
        """Everything behind a partner's points (2.8.6), for her card.

        Each booking her guests made (with what it is worth and the points it
        gave), the corrections by hand and the vouchers she received.
        """
        partner = self._find(self.partners, partner_id, "Partner")
        rate = float(self._data.get(KEY_SETTINGS, {}).get("partner_points_per_euro") or 0)
        clients = {c["id"]: c for c in self.clients}
        treatments = {t["id"]: t for t in self.treatments}
        bookings = []
        for appointment in self.appointments:
            if appointment.get("partner_id") != partner["id"]:
                continue
            cancelled = appointment.get("status") == "cancelled"
            value = 0.0 if cancelled else self._booked_value(appointment)
            client = clients.get(appointment.get("client_id") or "")
            bookings.append({
                "id": appointment["id"],
                "code": appointment.get("code") or "",
                "start": appointment.get("start") or "",
                "status": appointment.get("status") or "",
                "client": self.full_name(client) if client else "",
                "treatment": (treatments.get(appointment.get("treatment_id") or "") or {}).get("name") or "",
                "value": round(value, 2),
                "discount_pct": appointment.get("partner_discount_pct") or 0,
                "points": int(math.floor(value * rate + 1e-9)),
            })
        bookings.sort(key=lambda b: b["start"], reverse=True)
        settings = self._data.get(KEY_SETTINGS, {})
        return {
            "partner_id": partner["id"],
            "points": self.partner_points_of(partner),
            "rate": rate,
            "discount_pct": self.partner_discount_of(partner["id"]),
            "reward_points": int(settings.get("partner_reward_points") or 0),
            "reward_value": float(settings.get("partner_reward_value") or 0),
            "bookings": bookings,
            "log": list(reversed(partner.get("points_log") or [])),
            "rewards": list(reversed(partner.get("rewards") or [])),
            "link": self.partner_link(partner),
        }

    def format_partner_reward(self, partner: dict[str, Any], voucher: dict[str, Any], points: int, value: float) -> str:
        settings = self._data.get(KEY_SETTINGS, {})
        template = str(settings.get("partner_reward_message") or DEFAULT_PARTNER_REWARD_MESSAGE)
        name = str(partner.get("first_name") or partner.get("company") or "").strip()
        return (
            template.replace("{nome}", name or "partner")
            .replace("{attivita}", str(partner.get("company") or ""))
            .replace("{codice}", str(voucher.get("code") or ""))
            .replace("{valore}", _money_text(value))
            .replace("{punti}", str(points))
            .replace("{scadenza}", _date_it(voucher.get("expires_on") or ""))
            .replace("{hotel}", str(settings.get("guest_header") or "Il Marchese Hotel & Spa"))
        )

    async def async_partner_reward(self, partner_id: str, by: str = "", send: bool = True) -> dict[str, Any]:
        """Turn a partner's points into a voucher and send it to her (2.8.6).

        The points of the prize (Programma partner) are taken at once, before
        anything is sent, so a double tap cannot give two vouchers. The
        voucher is a gift card worth the prize; it goes on WhatsApp when the
        partner has a number, else by email.
        """
        settings = self._data.get(KEY_SETTINGS, {})
        partner = self._find(self.partners, partner_id, "Partner")
        threshold = int(settings.get("partner_reward_points") or 0)
        value = float(settings.get("partner_reward_value") or 0)
        if not threshold or value <= 0:
            raise ValidationError("Imposta punti e valore del premio in Promo › Programma partner")
        balance = self.partner_points_of(partner)["balance"]
        if balance < threshold:
            raise ValidationError(f"Servono {threshold} punti: il partner ne ha {balance}")
        name = " ".join(x for x in (partner.get("first_name"), partner.get("last_name")) if x) or partner.get("company") or "Partner"
        voucher = await self.async_create_voucher(
            "Programma partner", str(partner.get("phone") or ""), name, str(partner.get("phone") or ""),
            [{"name": name, "treatment_ids": [], "gift_card_amount": value}],
            None, by or "Programma partner",
        )
        async with self._lock:
            stored = self._find(self.vouchers, voucher["id"], "Voucher")
            stored["source"] = "partner"
            stored["partner_id"] = partner["id"]
            partner["points_spent"] = int(partner.get("points_spent") or 0) + threshold
            reward = {"at": dt_util.utcnow().isoformat(), "points": threshold, "value": value,
                      "voucher_id": stored["id"], "code": stored["code"], "sent": "", "by": by}
            partner.setdefault("rewards", []).append(reward)
            await self._async_save()
        text = self.format_partner_reward(partner, stored, threshold, value)
        sent = ""
        error = ""
        if send:
            chat_id = messaging.whatsapp_chat_id(str(partner.get("phone") or ""))
            if chat_id:
                try:
                    result = await messaging.async_send_whatsapp(self.hass, chat_id, text, waha=self.waha)
                    sent = "whatsapp" if result.get("sent") else ""
                    error = str(result.get("error") or "")
                except Exception as err:  # noqa: BLE001
                    error = str(err)
            if not sent and "@" in str(partner.get("email") or ""):
                try:
                    result = await self._async_deliver_email(
                        str(partner["email"]), f"Il Suo buono da {_money_text(value)}", text)
                    sent = "email" if result.get("sent") else ""
                    error = "" if sent else str(result.get("error") or error)
                except Exception as err:  # noqa: BLE001
                    error = error or str(err)
            if not sent and not error:
                error = "il partner non ha né WhatsApp né email"
        if sent:
            async with self._lock:
                reward["sent"] = sent
                for item in partner.get("rewards") or []:
                    if item.get("voucher_id") == stored["id"]:
                        item["sent"] = sent
                await self._async_save()
        return {"voucher": self.voucher_payload(stored), "sent": sent, "error": error,
                "text": text, "points": self.partner_points_of(partner)}

    def partner_points_summary(self) -> dict[str, dict[str, Any]]:
        """The points of every partner, for the card."""
        return {partner["id"]: self.partner_points_of(partner) for partner in self.partners}

    async def async_partner_points_adjust(self, partner_id: str, points: int, note: str = "", by: str = "") -> dict[str, Any]:
        """Add or take points from a partner by hand (a prize given, a correction)."""
        points = _norm_signed(points)
        if not points:
            raise ValidationError("Indica quanti punti aggiungere o togliere")
        async with self._lock:
            partner = self._find(self.partners, partner_id, "Partner")
            partner["points_adjust"] = int(partner.get("points_adjust") or 0) + points
            partner.setdefault("points_log", []).append(
                {"at": dt_util.utcnow().isoformat(), "points": points, "note": str(note or "").strip(), "by": by})
            await self._async_save()
        return {"points": self.partner_points_of(partner)}

    async def async_set_appointment_partner(self, appointment_id: str, partner_id: str) -> dict[str, Any]:
        """Name (or clear) the partner of a booking and of its whole party."""
        async with self._lock:
            appointment = self._find(self.appointments, appointment_id, "Appuntamento")
            target = self._partner_id_of(partner_id)
            if partner_id and not target:
                raise ValidationError("Partner non trovato")
            batch = appointment.get("batch_id")
            changed = 0
            for item in self.appointments:
                if item is appointment or (batch and item.get("batch_id") == batch):
                    item["partner_id"] = target
                    self._apply_partner_discount(item)
                    changed += 1
            await self._async_save()
        return {"changed": changed, "partner_id": target}

    # ------------------------------------------------ partner email campaigns

    def partner_link(self, partner: dict[str, Any]) -> str:
        """The booking page of the site with the partner's code."""
        base = str(self._data.get(KEY_SETTINGS, {}).get("partner_booking_url") or "").strip()
        if not base:
            return ""
        joiner = "&" if "?" in base else "?"
        return f"{base}{joiner}partner={partner.get('code', '')}"

    def format_partner_campaign(self, campaign: dict[str, Any], partner: dict[str, Any]) -> tuple[str, str, str]:
        """Subject, text and HTML of a campaign for one partner."""
        settings = self._data.get(KEY_SETTINGS, {})
        rate = float(settings.get("partner_points_per_euro") or 0)
        rate_text = (f"{rate:.2f}".rstrip("0").rstrip(".")).replace(".", ",")
        values = {
            "{nome}": partner.get("first_name") or partner.get("company") or "partner",
            "{cognome}": partner.get("last_name") or "",
            "{attivita}": partner.get("company") or "",
            "{codice_partner}": partner.get("code") or "",
            "{link_prenotazione}": self.partner_link(partner),
            "{punti_per_euro}": rate_text,
            "{punti}": str(self.partner_points_of(partner)["balance"]),
        }

        def fill(text: str) -> str:
            for key, value in values.items():
                text = text.replace(key, str(value))
            return text

        subject = fill(str(campaign.get("subject") or campaign.get("name") or "Spa"))
        body = fill(str(campaign.get("message") or ""))
        # Every campaign says how to stop them (2.6.0).
        link = self.partner_unsubscribe_url(partner) if partner.get("id") else ""
        footer = ("Non vuoi più ricevere queste email? Cancella l'iscrizione: " + link) if link else \
            "Non vuoi più ricevere queste email? Rispondi «CANCELLAMI» e ti togliamo dall'elenco."
        body = f"{body.rstrip()}\n\n—\n{footer}"
        return subject, body, _email_html(body)

    async def async_send_partner_campaign(self, campaign_id: str, test_to: str = "") -> dict[str, Any]:
        """Send a campaign to every active partner with an email, or a test to one address."""
        settings = self._data.get(KEY_SETTINGS, {})
        campaign = next((c for c in settings.get("partner_campaigns") or [] if c["id"] == campaign_id), None)
        if campaign is None:
            raise ValidationError("Campagna non trovata: forse è stata eliminata")
        if not settings.get("email_enabled"):
            raise ValidationError("L'invio email è spento: attivalo in Configurazione › Email")
        if "{link_prenotazione}" in str(campaign.get("message") or "") and not settings.get("partner_booking_url"):
            raise ValidationError("Indica la pagina di prenotazione del sito nella campagna (passo «Il link»)")
        if test_to:
            sample = next((p for p in self.partners if p.get("active", True)), None) or {
                "id": "", "first_name": "Giulia", "company": "B&B Esempio", "code": "PRT-TEST"}
            subject, body, html = self.format_partner_campaign(campaign, sample)
            result = await self._async_deliver_email(test_to, f"[PROVA] {subject}", body, html)
            if not result.get("sent"):
                raise ValidationError(result.get("error") or "Email di prova non inviata")
            return {"sent": 1, "test": True, "to": result.get("to")}
        # Unsubscribed partners (2.6.0) receive nothing at all.
        targets = [p for p in self.partners
                   if p.get("active", True) and p.get("subscribed", True) and "@" in str(p.get("email") or "")]
        # Only some towns (2.7.3).
        cities = {str(c).strip().lower() for c in campaign.get("cities") or [] if str(c).strip()}
        if cities:
            targets = [p for p in targets if str(p.get("city") or "").strip().lower() in cities]
        if not targets:
            raise ValidationError("Nessun partner attivo e iscritto con email" + (" nelle città scelte" if cities else ""))
        sent = 0
        errors: list[str] = []
        for index, partner in enumerate(targets):
            subject, body, html = self.format_partner_campaign(campaign, partner)
            result = await self._async_deliver_email(partner["email"], subject, body, html)
            if result.get("sent"):
                sent += 1
                partner["campaigns_sent"] = int(partner.get("campaigns_sent") or 0) + 1
                partner["campaign_last_at"] = dt_util.utcnow().isoformat()
            else:
                errors.append(f"{partner.get('company') or partner.get('first_name')}: {result.get('error')}")
                if len(errors) >= 3 and not sent:
                    break  # the mailbox itself is not working: stop here
            if index + 1 < len(targets):
                await asyncio.sleep(1)
        async with self._lock:
            for stored in self._data[KEY_SETTINGS].get("partner_campaigns") or []:
                if stored["id"] == campaign_id:
                    stored["sent_at"] = dt_util.utcnow().isoformat()
                    stored["sent_count"] = int(stored.get("sent_count") or 0) + sent
                    stored["last_error"] = errors[0] if errors else ""
            await self._async_save()
        return {"sent": sent, "failed": len(errors), "total": len(targets), "errors": errors[:5]}

    async def async_partner_campaign_tick(self) -> dict[str, Any]:
        """Campaigns with a start day and time go out once, within the hour."""
        settings = self._data.get(KEY_SETTINGS, {})
        now_local = dt_util.as_local(dt_util.utcnow())
        today = now_local.date().isoformat()
        minutes_now = now_local.hour * 60 + now_local.minute
        results: dict[str, Any] = {}
        for campaign in list(settings.get("partner_campaigns") or []):
            if campaign.get("mode") != "giorno" or campaign.get("sent_at") or campaign.get("date") != today:
                continue
            target = self._minutes_of(str(campaign.get("time") or ""))
            if target < 0 or not 0 <= minutes_now - target < 60:
                continue
            async with self._lock:
                campaign["sent_at"] = dt_util.utcnow().isoformat()  # once, even if it fails
                await self._async_save()
            try:
                results[campaign["id"]] = await self.async_send_partner_campaign(campaign["id"])
            except ValidationError as err:
                results[campaign["id"]] = {"sent": 0, "reason": str(err)}
                async with self._lock:
                    campaign["last_error"] = str(err)
                    await self._async_save()
        return results or {"sent": 0, "reason": "nessuna campagna partner da inviare ora"}

    async def async_import_partners(self, rows: list[dict[str, Any]]) -> dict[str, Any]:
        """Add many partners at once (2.6.0).

        The same email (or, without one, the same structure in the same town)
        is the same partner: nothing is duplicated, and an existing partner
        only gets the fields it was missing, so an unsubscribed one stays so.
        """
        allowed = ("company", "first_name", "last_name", "city", "structure_type", "phone", "email", "notes")
        added = updated = skipped = 0
        async with self._lock:
            codes = {p["code"] for p in self.partners}
            by_email = {str(p.get("email") or "").strip().lower(): p for p in self.partners if p.get("email")}
            by_name = {(str(p.get("company") or "").strip().lower(), str(p.get("city") or "").strip().lower()): p
                       for p in self.partners if p.get("company")}
            for raw in rows[:5000]:
                if not isinstance(raw, dict):
                    skipped += 1
                    continue
                row = {key: str(raw.get(key) or "").strip() for key in allowed}
                row["email"] = row["email"].lower()
                if row["email"] and not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", row["email"]):
                    row["email"] = ""
                if not (row["company"] or row["first_name"]) or not (row["email"] or row["phone"]):
                    skipped += 1
                    continue
                whatsapp = str(raw.get("whatsapp") or "").strip().lower() in ("1", "si", "sì", "yes", "true", "x", "whatsapp")
                current = by_email.get(row["email"]) if row["email"] else None
                current = current or by_name.get((row["company"].lower(), row["city"].lower())) if row["company"] else current
                if current is not None:
                    changed = False
                    for key, value in row.items():
                        if value and not str(current.get(key) or "").strip():
                            current[key] = value
                            changed = True
                    if whatsapp and not current.get("whatsapp"):
                        current["whatsapp"] = True
                        changed = True
                    updated += 1 if changed else 0
                    skipped += 0 if changed else 1
                    continue
                while True:
                    code = "PRT-" + secrets.token_hex(2).upper()
                    if code not in codes:
                        codes.add(code)
                        break
                record = _norm_partner({**row, "whatsapp": whatsapp, "code": code, "source": "import", "subscribed": True})
                self.partners.append(record)
                if record["email"]:
                    by_email[record["email"]] = record
                if record["company"]:
                    by_name[(record["company"].lower(), record["city"].lower())] = record
                added += 1
            await self._async_save()
        return {"added": added, "updated": updated, "skipped": skipped}

    def partner_unsubscribe_url(self, partner: dict[str, Any]) -> str:
        """The page where a partner stops the emails (2.6.0); "" without a public address."""
        base = str(self._data.get(KEY_SETTINGS, {}).get("web_public_url") or "").strip().rstrip("/")
        if not base:
            try:
                from homeassistant.helpers.network import NoURLAvailableError, get_url

                try:
                    base = get_url(self.hass, allow_internal=False, prefer_external=True).rstrip("/")
                except NoURLAvailableError:
                    base = ""
            except ImportError:  # pragma: no cover - old cores
                base = ""
        if not base or not partner.get("unsub_token"):
            return ""
        return f"{base}/api/spa_booking/partner/unsubscribe?t={partner['unsub_token']}"

    def partner_by_unsub_token(self, token: str) -> dict[str, Any] | None:
        """The partner of an unsubscribe link, if the token is one of ours."""
        token = str(token or "")
        if len(token) < 16:
            return None
        return next((p for p in self.partners if secrets.compare_digest(str(p.get("unsub_token") or ""), token)), None)

    async def async_partner_unsubscribe(self, token: str) -> dict[str, Any] | None:
        """Stop every email and promo to the partner of this link."""
        async with self._lock:
            partner = self.partner_by_unsub_token(token)
            if partner is None:
                return None
            if partner.get("subscribed", True):
                partner["subscribed"] = False
                partner["unsubscribed_at"] = dt_util.utcnow().isoformat()
                await self._async_save()
        return partner

    # ------------------------------------------------------- WordPress shop

    def _wp_settings(self) -> tuple[str, str]:
        settings = self._data.get(KEY_SETTINGS, {})
        url = str(settings.get("wp_url") or "").strip().rstrip("/")
        secret = str(settings.get("wp_secret") or "")
        if not url or not secret:
            raise ValidationError("Indica l'indirizzo del sito e la chiave in Configurazione › Shop online")
        if not url.startswith(("https://", "http://")):
            url = "https://" + url
        return url, secret

    async def async_wp_new_secret(self) -> dict[str, Any]:
        """A new shared key to paste into the WordPress plugin."""
        async with self._lock:
            self._data[KEY_SETTINGS]["wp_secret"] = secrets.token_urlsafe(24)
            await self._async_save()
        return {"wp_secret": self._data[KEY_SETTINGS]["wp_secret"]}

    async def async_wp_test(self) -> dict[str, Any]:
        """Check the plugin answers, and read the products to pair."""
        url, secret = self._wp_settings()
        try:
            info = await wp_shop.status(self._http_session(), url, secret)
            items = await wp_shop.products(self._http_session(), url, secret)
        except wp_shop.WpShopError as err:
            raise ValidationError(str(err)) from err
        async with self._lock:
            self._data[KEY_SETTINGS]["wp_products"] = items
            self._data[KEY_SETTINGS] = _norm_settings(self._data[KEY_SETTINGS])
            await self._async_save()
        return {"ok": True, "buoni_pdf": bool(info.get("buoni_pdf")), "version": info.get("version"),
                "site": info.get("site"), "products": len(items)}

    def _wp_people(self, product_id: Any, variation_id: Any, paid: Any = None) -> list[dict[str, Any]]:
        mapping = self._data.get(KEY_SETTINGS, {}).get("wp_product_map") or {}
        return wp_shop.people_of(wp_shop.mapping_for(mapping, product_id, variation_id), paid)

    def _wp_apply_pairing(self) -> int:
        """Bring every unused voucher from the shop in line with the pairing.

        Run when the pairing is saved (2.7.1) and at every check of the shop:
        a product paired again later, with the treatments or accessories that
        were missing, updates the vouchers already received. Called with the
        lock held.
        """
        mapping = self._data.get(KEY_SETTINGS, {}).get("wp_product_map") or {}
        changed = 0
        for voucher in self.vouchers:
            if voucher.get("source") != "wordpress" or voucher["status"] != VOUCHER_ACTIVE:
                continue
            product_id, _, variation_id = str(voucher.get("wp_product_key") or "0:0").partition(":")
            entry = wp_shop.mapping_for(mapping, product_id, variation_id or 0)
            people = wp_shop.people_of(entry, voucher.get("value"))
            note = wp_shop.note_of(entry)
            if people != voucher["people"] or note != voucher.get("package_note", ""):
                voucher["people"] = people
                voucher["package_note"] = note
                changed += 1
        return changed

    async def async_wp_sync(self, reason: str = "") -> dict[str, Any]:
        """Read the vouchers sold on the shop and bring the list up to date.

        New codes (not expired, not used on the shop) become gift vouchers;
        a code used on the shop is redeemed here too; a voucher booked and
        then cancelled before the guest came is usable again; redemptions
        that could not reach the shop are sent again.
        """
        settings = self._data.get(KEY_SETTINGS, {})
        if not settings.get("wp_enabled"):
            return {"skipped": "collegamento spento"}
        try:
            url, secret = self._wp_settings()
            items = await wp_shop.vouchers(self._http_session(), url, secret)
        except (wp_shop.WpShopError, ValidationError) as err:
            async with self._lock:
                self._data[KEY_SETTINGS]["wp_last_error"] = str(err)
                await self._async_save()
            return {"error": str(err)}
        today = dt_util.now().date().isoformat()
        added = updated = used = 0
        async with self._lock:
            by_code = {v["code"]: v for v in self.vouchers}
            for item in items:
                code = str(item.get("code") or "").strip()
                key = code.upper()
                order_ok = str(item.get("order_status") or "") in ("processing", "completed")
                expires = wp_shop.expiry_of(item)
                people = self._wp_people(item.get("product_id"), item.get("variation_id"), item.get("value"))
                voucher = by_code.get(key)
                if voucher is None:
                    if item.get("used") or not order_ok or (expires and expires < today):
                        continue
                    buyer = " ".join(str(item.get(k) or "").strip() for k in ("buyer_first", "buyer_last")).strip()
                    voucher = _norm_voucher({
                        "id": _new_id("vou"), "code": key, "wp_code": code, "source": "wordpress",
                        "buyer_name": buyer, "buyer_phone": item.get("buyer_phone"), "buyer_email": item.get("buyer_email"),
                        "recipient_name": item.get("recipient_name"), "recipient_email": item.get("recipient_email"),
                        "message": item.get("message"), "people": people, "value": item.get("value"),
                        "wp_order_id": item.get("order_id"),
                        "wp_product_key": wp_shop.product_key(item.get("product_id"), item.get("variation_id")),
                        "wp_product_name": item.get("product_name"), "expires_on": expires,
                        "package_note": wp_shop.note_of(wp_shop.mapping_for(
                            self._data.get(KEY_SETTINGS, {}).get("wp_product_map") or {},
                            item.get("product_id"), item.get("variation_id"))),
                        "created_at": str(item.get("order_date") or dt_util.utcnow().isoformat()),
                        "created_by_name": "Shop online",
                    })
                    self.vouchers.append(voucher)
                    by_code[key] = voucher
                    added += 1
                    continue
                if voucher.get("source") != "wordpress":
                    continue
                changed = False
                if expires and voucher.get("expires_on") != expires:
                    voucher["expires_on"] = expires
                    changed = True
                if item.get("used") and not voucher.get("wp_redeemed"):
                    voucher["wp_redeemed"] = True
                    voucher["wp_redeemed_at"] = str(item.get("used_at") or dt_util.utcnow().isoformat())
                    voucher["wp_redeem_error"] = ""
                    if voucher["status"] != VOUCHER_REDEEMED:
                        voucher["status"] = VOUCHER_REDEEMED
                        voucher["redeemed_at"] = voucher["wp_redeemed_at"]
                        voucher["wp_note"] = "riscattato sul sito"
                    used += 1
                    changed = True
                if not order_ok and voucher["status"] == VOUCHER_ACTIVE:
                    voucher["status"] = VOUCHER_REDEEMED
                    voucher["wp_note"] = "ordine annullato o rimborsato sul sito"
                    changed = True
                updated += 1 if changed else 0
            # The pairing may have changed since: unused vouchers follow it.
            updated += self._wp_apply_pairing()
            # Booked, then every booking cancelled before the guest came: usable again.
            appointments = {a["id"]: a for a in self.appointments}
            for voucher in self.vouchers:
                if voucher.get("source") != "wordpress" or voucher["status"] != VOUCHER_REDEEMED or voucher.get("wp_redeemed"):
                    continue
                linked = [appointments.get(i) for i in voucher.get("appointment_ids") or []]
                if linked and all(a is None or a.get("status") == STATUS_CANCELLED for a in linked):
                    voucher["status"] = VOUCHER_ACTIVE
                    voucher["redeemed_at"] = ""
                    voucher["appointment_ids"] = []
                    updated += 1
            pending = [v["id"] for v in self.vouchers if v.get("source") == "wordpress" and not v.get("wp_redeemed")
                       and any(appointments.get(i, {}).get("checked_in") for i in v.get("appointment_ids") or [])]
            settings = self._data[KEY_SETTINGS]
            settings["wp_last_sync"] = dt_util.utcnow().isoformat()
            settings["wp_last_error"] = ""
            settings["wp_last_result"] = f"{len(items)} codici letti · {added} nuovi · {updated} aggiornati" + (f" ({reason})" if reason else "")
            await self._async_save()
        for voucher_id in pending:
            await self.async_wp_redeem(voucher_id)
        return {"read": len(items), "added": added, "updated": updated, "used_on_site": used, "retried": len(pending)}

    async def async_wp_tick(self) -> dict[str, Any]:
        """Every 15 minutes, when the shop is connected."""
        if not self._data.get(KEY_SETTINGS, {}).get("wp_enabled"):
            return {"skipped": "collegamento spento"}
        if dt_util.now().minute % 15 >= 5:
            return {"skipped": "non ora"}
        return await self.async_wp_sync()

    async def async_wp_redeem(self, voucher_id: str) -> dict[str, Any]:
        """Tell the shop the voucher was used at the spa (on the guest's arrival)."""
        voucher = self._find(self.vouchers, voucher_id, "Voucher")
        if voucher.get("source") != "wordpress":
            raise ValidationError("Questo voucher non viene dal sito")
        if voucher.get("wp_redeemed"):
            return {"ok": True, "already": True}
        try:
            url, secret = self._wp_settings()
            await wp_shop.redeem(self._http_session(), url, secret, voucher.get("wp_code") or voucher["code"],
                                 note=", ".join(voucher.get("appointment_ids") or []))
        except (wp_shop.WpShopError, ValidationError) as err:
            async with self._lock:
                voucher["wp_redeem_error"] = str(err)
                await self._async_save()
            return {"ok": False, "error": str(err)}
        async with self._lock:
            voucher["wp_redeemed"] = True
            voucher["wp_redeemed_at"] = dt_util.utcnow().isoformat()
            voucher["wp_redeem_error"] = ""
            if voucher["status"] != VOUCHER_REDEEMED:
                voucher["status"] = VOUCHER_REDEEMED
                voucher["redeemed_at"] = voucher["wp_redeemed_at"]
            await self._async_save()
        return {"ok": True}

    async def async_delete_all_partners(self) -> dict[str, Any]:
        """Empty the partner list (2.7.3), to import it again from scratch.

        The bookings keep their partner id, which then names nobody.
        """
        async with self._lock:
            count = len(self.partners)
            self._data[KEY_PARTNERS] = []
            await self._async_save()
        return {"deleted": count}

    async def async_delete_partner(self, partner_id: str) -> dict[str, Any]:
        """Remove a partner from the list."""
        async with self._lock:
            self._find(self.partners, partner_id, "Partner")
            self._data[KEY_PARTNERS] = [p for p in self.partners if p["id"] != partner_id]
            await self._async_save()
        return {"id": partner_id}

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
            # One voucher per booking (2.9.0): a group leaving earns its
            # client one voucher, not one per person or treatment.
            anchor = next((a for a in self.appointments if a["id"] == appointment_id), None)
            booking = {a["id"] for a in self._group_members(anchor)} if anchor else {appointment_id}
            already = next(
                (
                    v
                    for v in self.promo_vouchers
                    if v.get("appointment_id") == appointment_id
                    or (v.get("appointment_id") in booking and v.get("client_id") == client_id)
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

    async def async_send_loyalty_voucher(
        self,
        client_id: str = "",
        partner_id: str = "",
        discount_percent: int | None = None,
        days: int | None = None,
        min_spend: int | None = None,
        by: str = "",
    ) -> dict[str, Any]:
        """A loyalty voucher sent by hand, with no booking behind it (2.8.11).

        Same voucher as the one a visit earns (Promo › Voucher fedeltà), with
        its message; sent at once on WhatsApp, or by email to a partner who has
        no number. Sconto, validità and spesa minima default to the settings.
        """
        settings = self._data[KEY_SETTINGS]
        if bool(client_id) == bool(partner_id):
            raise ValidationError("Indica un cliente oppure un partner")
        if client_id:
            person = self._find(self.clients, client_id, "Cliente")
            first, last = str(person.get("first_name") or ""), str(person.get("last_name") or "")
        else:
            person = self._find(self.partners, partner_id, "Partner")
            first = str(person.get("first_name") or person.get("company") or "")
            last = str(person.get("last_name") or "") if person.get("first_name") else ""
        valid_days = int(days or settings.get("promo_voucher_days") or DEFAULT_PROMO_VOUCHER_DAYS)
        async with self._lock:
            existing = {v["code"] for v in self.promo_vouchers}
            now = dt_util.utcnow()
            voucher = _norm_promo_voucher({
                "id": f"fid_{secrets.token_hex(6)}",
                "code": _new_promo_voucher_code(existing),
                "client_id": client_id,
                "partner_id": partner_id,
                "first_name": first.strip(),
                "last_name": last.strip(),
                "phone": str(person.get("phone") or "").strip(),
                "discount_percent": discount_percent or settings.get("promo_voucher_discount"),
                "min_spend": settings.get("promo_voucher_min_spend") if min_spend is None else min_spend,
                "max_spend": settings.get("promo_voucher_max_spend"),
                "created_at": now.isoformat(),
                "send_at": now.isoformat(),
                "expires_on": (dt_util.now().date() + timedelta(days=valid_days)).strftime("%Y-%m-%d"),
                "status": PROMO_VOUCHER_PENDING,
                "appointment_id": "",
                "manual": True,
                "by": by,
            })
            self.promo_vouchers.append(voucher)
            await self._async_save()
        text = self.format_promo_voucher(voucher)
        sent = ""
        error = ""
        chat_id = messaging.whatsapp_chat_id(voucher["phone"])
        if chat_id:
            try:
                result = await messaging.async_send_whatsapp(self.hass, chat_id, text, waha=self.waha)
                sent = "whatsapp" if result.get("sent") else ""
                error = str(result.get("error") or "")
            except Exception as err:  # noqa: BLE001
                error = str(err)
        email = str(person.get("email") or "")
        if not sent and "@" in email:
            try:
                result = await self._async_deliver_email(email, "Il Suo voucher fedeltà", text)
                sent = "email" if result.get("sent") else ""
                error = "" if sent else str(result.get("error") or error)
            except Exception as err:  # noqa: BLE001
                error = error or str(err)
        if not sent and not error:
            error = "nessun numero WhatsApp né email"
        if sent:
            async with self._lock:
                voucher["status"] = PROMO_VOUCHER_SENT
                voucher["sent_at"] = dt_util.utcnow().isoformat()
                await self._async_save()
        return {"voucher": self.promo_voucher_payload(voucher), "sent": sent, "error": error, "text": text}

    async def async_send_promo_vouchers(self) -> dict[str, Any]:
        """Send every loyalty-voucher message that has come due, once each.

        A voucher is sent when its ``send_at`` has passed and it is still
        pending. A failure leaves it pending, so the next tick retries it; a
        successful send marks it ``sent`` and stamps ``sent_at``. A voucher
        with no usable phone is marked sent without a message: there is nothing
        to retry and it should not pile up in the pending queue.
        """
        async with self._send_lock:
            return await self._async_send_promo_vouchers()

    async def _async_send_promo_vouchers(self) -> dict[str, Any]:
        """The body of ``async_send_promo_vouchers``, under the send lock."""
        now = dt_util.utcnow()
        sent_ids: set[str] = set()
        failed = 0
        skipped_ids: set[str] = set()
        due: list[tuple[str, str, str, str]] = []
        for voucher in self.promo_vouchers:
            if voucher.get("status") != PROMO_VOUCHER_PENDING:
                continue
            when = dt_util.parse_datetime(str(voucher.get("send_at") or ""))
            if when is not None and when > now:
                continue
            phone = str(voucher.get("phone") or "").strip()
            chat_id = messaging.whatsapp_chat_id(phone)
            if not chat_id:
                skipped_ids.add(voucher["id"])
                continue
            due.append((voucher["id"], chat_id, self.format_promo_voucher(voucher), phone))

        for voucher_id, chat_id, message, phone in due:
            try:
                result = await messaging.async_send_whatsapp(
                    self.hass, chat_id, message, waha=self.waha
                )
            except Exception as err:  # noqa: BLE001
                result = {"sent": False, "error": str(err)}
            if result.get("sent"):
                sent_ids.add(voucher_id)
            else:
                failed += 1
                _LOGGER.warning(
                    "Voucher fedelta %s non inviato a %s: %s",
                    voucher_id,
                    phone or "?",
                    result.get("error") or "errore sconosciuto",
                )

        if sent_ids or skipped_ids:
            async with self._lock:
                for voucher in self.promo_vouchers:
                    if voucher["id"] in sent_ids | skipped_ids:
                        voucher["status"] = PROMO_VOUCHER_SENT
                        voucher["sent_at"] = now.isoformat()
                await self._async_save()
        sent, skipped = len(sent_ids), len(skipped_ids)
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
            "proposed_date_it": _date_it(str(request.get("proposed_date") or "")),
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
            treatment = next((t for t in self.treatments if t["id"] == entry.get("treatment_id")), None)
            # «Automatica»: every able, active masseuse, asked in order.
            able = (
                [o["id"] for o in self.operators_for_treatment(treatment["id"]) if o.get("active", True)]
                if treatment is not None and self._treatment_requires_operator(treatment)
                else []
            )
            clock = str(entry.get("time") or "00:00")
            # A website entry names its person: one appointment for her. A
            # desk entry does not: one appointment for each of the people.
            persons = (
                [entry["person"]]
                if entry.get("person") is not None
                else range(int(request.get("people") or 1))
            )
            rows.append(
                {
                    "treatment_id": entry["treatment_id"],
                    "entries": [
                        {
                            "start": f"{day}T{clock}:00",
                            "client_id": request["client_id"],
                            "person": person,
                            "extras": entry.get("extras") or self._package_extras(entry.get("package_key")),
                            **({"operator_ids": able} if able else {}),
                            **(
                                {"package_key": entry["package_key"],
                                 "package_group": entry.get("package_group") or entry["package_key"]}
                                if entry.get("package_key") else {}
                            ),
                            # The person's own wish wins over the request's.
                            "therapist_preference": entry.get("therapist_preference")
                            or request.get("therapist_preference")
                            or "",
                        }
                        for person in persons
                    ],
                    "pending": False,
                    "guest_type": request.get("guest_type") or GUEST_TYPE_DEFAULT,
                    "partner_id": request.get("partner_id") or "",
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
            self._share_package_prices(
                [(str(row.get("treatment_id") or ""), row) for row in rows if isinstance(row, dict)]
            )
            # Appointments whose masseuse must hear about the edit (2.8.3).
            reassigned: list[tuple[dict[str, Any], str]] = []

            # Snapshot of the whole data tree, taken before anything is
            # touched, so any failure puts every record back exactly as it was.
            _data_snapshot = copy.deepcopy(self._data)

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
                    if (
                        operator_ids is None
                        and row.get("operator_id")
                        and existing_appt is not None
                        and row.get("operator_id") != existing_appt.get("operator_id")
                    ):
                        # A new masseuse named in the edit (2.8.3).
                        operator_ids = [row["operator_id"]]
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
                        forward_pause=existing_appt is None
                        or not _same_slot(existing_appt, treatment_id, start),
                    )
                    # Preserve history on rebuild.
                    if existing_appt is not None:
                        appointment["id"] = existing_appt["id"]
                        appointment["code"] = existing_appt.get("code") or appointment.get("code")
                        appointment["created_at"] = existing_appt.get("created_at") or appointment.get("created_at")
                        appointment["created_by"] = existing_appt.get("created_by", appointment.get("created_by"))
                        appointment["created_by_name"] = existing_appt.get("created_by_name", "")
                        if not appointment.get("therapist_preference"):
                            appointment["therapist_preference"] = existing_appt.get("therapist_preference", "")
                        appointment["history"] = list(existing_appt.get("history") or [])
                        appointment["payments"] = _norm_payment_list(existing_appt.get("payments"))
                        appointment["checked_in"] = existing_appt.get("checked_in", False)
                        appointment["checked_in_at"] = existing_appt.get("checked_in_at", "")
                        appointment["checked_out"] = existing_appt.get("checked_out", False)
                        appointment["checked_out_at"] = existing_appt.get("checked_out_at", "")
                        appointment["confirmed_by"] = existing_appt.get("confirmed_by", "")
                        appointment["confirmed_at"] = existing_appt.get("confirmed_at", "")
                        # The offer survives an ordinary edit; a new masseuse
                        # or a new time is a new request to her (2.8.3).
                        if (
                            (appointment.get("operator_id") or "") == (existing_appt.get("operator_id") or "")
                            and _same_slot(existing_appt, treatment_id, start)
                        ):
                            appointment["offer_state"] = existing_appt.get("offer_state", OFFER_NONE)
                            appointment["offer_candidates"] = list(existing_appt.get("offer_candidates") or [])
                            appointment["offer_index"] = existing_appt.get("offer_index", 0)
                            appointment["offer_expires_at"] = existing_appt.get("offer_expires_at", "")
                        else:
                            reassigned.append((appointment, existing_appt.get("operator_id") or ""))
                        appointment["reminder_sent"] = existing_appt.get("reminder_sent", False)
                        appointment["reminder_sent_at"] = existing_appt.get("reminder_sent_at", "")
                        appointment["confirmation_sent_at"] = existing_appt.get("confirmation_sent_at", "")
                        appointment["deposit_request_sent_at"] = existing_appt.get("deposit_request_sent_at", "")
                        appointment["review_request_sent"] = existing_appt.get("review_request_sent", False)
                        appointment["deposit_request_sent"] = existing_appt.get("deposit_request_sent", False)
                        kept_ids.add(existing_appt["id"])
                    elif appointment.get("offer_state") == OFFER_PENDING:
                        # A person added to the group: her masseuse is asked.
                        reassigned.append((appointment, ""))

                    # The partner of the booking stays with every person (2.8.9).
                    appointment["partner_id"] = self._partner_id_of(
                        row.get("partner_id") if row.get("partner_id") is not None
                        else (existing_appt or anchor).get("partner_id") or ""
                    )
                    self._apply_package(appointment, row)
                    if existing_appt is not None and existing_appt.get("partner_discount_pct") and appointment.get("price") is not None:
                        appointment["partner_discount_pct"] = existing_appt["partner_discount_pct"]
                    elif existing_appt is None:
                        self._apply_partner_discount(appointment)

                    # Clients handled below; no-op placeholder
                    prepared.append((appointment, client, is_new))

                # Commit new clients.
                created_clients = []
                for _appointment, client, is_new in prepared:
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

                await self._async_save()
            except Exception:
                # Full rollback to the deep copy. (Up to 2.0.15 the copy was
                # then overwritten with shallow lists of the very records the
                # failed edit had already modified, so the "rollback" kept
                # half of the changes.)
                self._data = _data_snapshot
                self.async_set_updated_data(self._data)
                raise
            finally:
                self._current_user_id = None

        for item, previous in reassigned:
            if item.get("status") != STATUS_CANCELLED:
                await self._async_notify_reassigned(self.appointment_payload(item), previous)
        return {
            "batch_id": batch_id,
            "appointments": [self.appointment_payload(item[0]) for item in prepared],
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
        request_id: str | None = None,
        therapist_preference: str = "",
        partner: str | None = None,
    ) -> dict[str, Any]:
        """Take a guest's appointment request and acknowledge it on WhatsApp.

        With ``request_id`` the request already on the list is rewritten in
        place instead (the card's "Modifica"): same id, code, source and
        creation time, and no second acknowledgement to the guest. Up to
        2.1.0 an edit saved a new request and left the old one on the list.
        Only a request still waiting can be changed.

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
            item = {
                "treatment_id": treatment_id,
                "time": clock,
                "extras": _norm_extras(
                    entry.get("extras"), known=self._accessory_ids()
                ),
            }
            if entry.get("person") is not None:
                item["person"] = _norm_person(entry.get("person"))
            if entry.get("therapist_preference") in ("F", "M"):
                item["therapist_preference"] = entry["therapist_preference"]
            # Part of a shop package (2.8.9): its accessories come with it.
            item.update(_norm_package_ref(entry))
            if item.get("package_key") and not item["extras"]:
                item["extras"] = self._package_extras(item["package_key"])
            clean.append(item)
        if not clean:
            raise ValidationError("Aggiungi almeno un trattamento alla richiesta")

        # A voucher the guest typed: if it is one of ours it must still be
        # usable, otherwise the guest would learn only days later, on the
        # phone. An unknown code is kept as typed for the desk to check.
        code = str(voucher_code or "").strip().upper()[:64]
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
            existing_request = None
            if request_id:
                existing_request = next(
                    (r for r in self.requests if r["id"] == request_id), None
                )
                if existing_request is None:
                    raise NotFoundError("Richiesta non trovata")
                if existing_request.get("status") != REQUEST_PENDING:
                    raise ValidationError(
                        "La richiesta è già stata confermata: modifica gli appuntamenti"
                    )
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
            if existing_request is not None:
                updated = _norm_request(
                    {
                        **existing_request,
                        "client_id": client["id"],
                        "date": day,
                        "people": people,
                        "entries": clean,
                        "notes": notes,
                        "voucher_code": code,
                        "guest_type": _norm_guest_type(guest_type),
                        "therapist_preference": therapist_preference,
                        "partner_id": existing_request.get("partner_id", "")
                        if partner is None else self._partner_id_of(partner),
                    }
                )
                existing_request.clear()
                existing_request.update(updated)
                await self._async_save()
                return self.request_payload(existing_request)
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
                    "therapist_preference": therapist_preference,
                    "partner_id": self._partner_id_of(partner),
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
                    "created_by_name": "Sito web"
                    if source == REQUEST_SOURCE_WEB
                    else acting_person()[1],
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

    
    async def async_export_dashboard_yaml(self) -> dict[str, Any]:
        """Return a ready-to-import Lovelace YAML dashboard for the Spa tiles."""
        settings = self.export_data().get("settings", {}) or {}
        tiles = settings.get("spa_entities") or []
        lines = [
            "views:",
            "- path: spa_generated",
            "  title: Spa (generated)",
            "  cards:",
        ]
        for tile in tiles:
            if not isinstance(tile, dict):
                continue
            entity_id = str(tile.get("entity_id") or "").strip()
            if not entity_id:
                continue
            domain = entity_id.split(".", 1)[0]
            card_type = "tile"
            if domain == "climate":
                card_type = "thermostat"
            elif domain == "sensor":
                card_type = "sensor"
            elif domain == "media_player":
                card_type = "media-control"
            lines.append(f"    - type: {card_type}")
            lines.append(f"      entity: {entity_id}")
            name = tile.get("name")
            if name:
                import json as _json
                lines.append(f"      name: {_json.dumps(str(name), ensure_ascii=False)}")
            icon = tile.get("icon")
            if icon:
                lines.append(f"      icon: {icon}")
            features = tile.get("features") or []
            mapped = []
            for feat in features:
                if feat == "brightness":
                    mapped.append("- type: light-brightness")
                elif feat == "temperature":
                    mapped.append("- type: temperature-control")
                elif feat == "power":
                    mapped.append("- type: power")
            if mapped:
                lines.append("      features:")
                for line in mapped:
                    lines.append("        " + line)
        return {"yaml": "\n".join(lines)}

    async def async_web_snippet(self, base_url: str = "") -> dict[str, Any]:
        """Return the code to paste into the site, with the token already in it.

        ``snippet`` is the two-line code of 2.2.0b3: a box and a script that
        loads the form from Home Assistant (``/api/spa_booking/public/form.js``),
        so a new version of the form reaches the site without touching
        WordPress. The address is the public one of the settings, else the one
        the desk is using (``base_url``), else the one written in the full
        form.

        ``snippet_full`` is the whole form of the versions before, from
        ``frontend/spa-booking-form.txt``, for a site that cannot load a
        script from another address. The token is never written to disk: it
        lives only in this answer and in the clipboard of whoever pressed
        Copia.
        """
        from .card_view import FORM_FILE

        path = str(FORM_FILE)
        full = await self.hass.async_add_executor_job(_read_text, path)
        found = WEB_SNIPPET_TOKEN_PLACEHOLDER in full
        token = self._web_token()
        base = str(self._web_settings.get("web_public_url") or "").strip().rstrip("/")
        if not base:
            match = re.search(r'var API_BASE = "(https?://[^"]+?)/api/spa_booking/public"', full or "")
            base = match.group(1) if match else str(base_url or "").strip().rstrip("/")
        short = (
            '<div id="spa-booking"></div>\n'
            f'<script src="{base}{WEB_API_BASE}/form.js" data-token="{token}" async></script>'
        )
        return {
            "snippet": short,
            "snippet_full": full.replace(WEB_SNIPPET_TOKEN_PLACEHOLDER, token),
            "base_url": base,
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

    def plan_public_entry(
        self,
        day: date,
        treatment_id: str,
        clock: str,
        planned: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Place one entry of a web request, so the next entries see it.

        Returns a pseudo-appointment (never stored) holding the first free
        operator, or none for a shared treatment. Call it only for a time
        ``async_public_availability`` has just offered with the same
        ``planned`` list.
        """
        treatment = next(t for t in self.treatments if t["id"] == treatment_id)
        hour, minute = (int(part) for part in clock.split(":"))
        start = dt_util.start_of_local_day(day) + timedelta(hours=hour, minutes=minute)
        end = start + timedelta(minutes=int(treatment.get("duration_min") or 0))
        operator_id = None
        if self._treatment_requires_operator(treatment):
            busy = [
                a
                for a in (*self.appointments, *planned)
                if occupies_slot(a) and a.get("operator_id")
            ]
            free = self._free_operators(
                self.operators_for_treatment(treatment_id),
                busy,
                start,
                end,
                self._treatment_pause_min(treatment),
            )
            operator_id = free[0] if free else None
        return {
            "id": f"web_planned_{len(planned)}",
            "treatment_id": treatment_id,
            "operator_id": operator_id,
            "start": dt_util.as_utc(start).isoformat(),
            "end": dt_util.as_utc(end).isoformat(),
            "status": STATUS_CONFIRMED,
        }

    def _category_allows(
        self,
        treatment: dict[str, Any],
        start: datetime,
        end: datetime,
        planned: list[dict[str, Any]] | None = None,
    ) -> bool:
        """Whether the category rules of the booking engine accept the slot."""
        try:
            self._validate_category_window(
                self._category(treatment.get("category_id")), start, end
            )
            self._category_exclusion(treatment, start, end, planned)
        except ValidationError:
            return False
        return True

    async def async_public_availability(
        self,
        day: date,
        treatment_id: str,
        planned: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """Return the start times the website may offer for one treatment.

        ``planned`` holds the other entries of the same web request, already
        placed (see ``plan_public_entry``): two people asking for a massage
        at the same hour need two free operators, not one free operator
        counted twice.

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
        booked = [*self.appointments, *(planned or [])]
        busy = [
            a
            for a in booked
            if occupies_slot(a) and a.get("operator_id")
        ]
        shared_bookings = (
            [
                a
                for a in booked
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

            # The category's own calendar (bookable weekdays, morning and
            # afternoon windows) and the categories it must never overlap:
            # the desk refuses those bookings, so the site must not offer them.
            if not self._category_allows(treatment, start, end, planned):
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
                if other_start < end + timedelta(minutes=pause) and other_end > start:
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

        # 2.8.3: the masseuse is chosen automatically (the guest's wish for a
        # woman or a man included) and asked at once, as for a booking taken
        # at the desk. Before, the massage was booked with nobody and no
        # operator ever heard of it.
        result = await self.async_create_bookings(self._request_rows(request))
        return await self._mark_request_confirmed(request_id, result)

    async def async_confirm_request_with(
        self, request_id: str, rows: list[dict[str, Any]], user_id: str | None = None
    ) -> dict[str, Any]:
        """Confirm a request with the booking the desk reviewed in the form.

        «Conferma» opens the request in Nuovo appuntamento: the desk can change
        times, treatments, people and the masseuse, then saves. The rows are
        booked exactly like a new booking (offers included) and the request is
        marked confirmed with the appointments it became.
        """
        request = self._find(self.requests, request_id, "Richiesta")
        if request.get("status") == REQUEST_CONFIRMED and request.get("appointment_ids"):
            raise ValidationError("La richiesta è già stata confermata")
        result = await self.async_create_bookings(rows, user_id)
        return await self._mark_request_confirmed(request_id, result)

    async def _mark_request_confirmed(
        self, request_id: str, result: dict[str, Any]
    ) -> dict[str, Any]:
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
        targets = notify_numbers(self._web_settings.get("web_notify_whatsapp"))
        if not targets:
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
        await self._send_web_notice(targets, message)

    async def _send_web_notice(self, targets: list[str], message: str) -> int:
        """Send the desk notice to every number; return how many went out."""
        sent = 0
        for target in targets:
            try:
                result = await messaging.async_send_whatsapp(
                    self.hass, target, message, waha=self.waha
                )
                sent += bool(result.get("sent"))
            except Exception as err:  # noqa: BLE001
                _LOGGER.warning("Avviso richiesta web a %s fallito: %s", target, err)
        return sent

    async def async_test_web_notice(self) -> dict[str, Any]:
        """«Prova avviso»: the notice of a web request, to every number."""
        targets = notify_numbers(self._web_settings.get("web_notify_whatsapp"))
        if not targets:
            raise ValidationError("Scrivi almeno un numero per l'avviso")
        sent = await self._send_web_notice(
            targets,
            "Prova: avviso di una nuova richiesta dal sito\n"
            "ABCDE · Mario Rossi · +39 333 1234567\n"
            "sabato 14 novembre · 10:00 Massaggio Relax",
        )
        return {"sent": sent, "numbers": len(targets)}

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

    async def async_propose_request_date(
        self,
        request_id: str,
        day: str,
        clock: str = "",
        text: str | None = None,
        *,
        alternatives: list[dict[str, Any]] | None = None,
        dry_run: bool = False,
        by_name: str = "",
    ) -> dict[str, Any]:
        """Offer the guest the first free date when the one she asked is full.

        ``dry_run`` only writes the message, for the preview in the card. The
        desk may change the text before sending (``text``). The request stays
        open: when the guest says yes, the desk moves it to the new date and
        confirms it as usual.
        """
        if not day:
            raise ValidationError("Indica la prima data disponibile")
        if day < dt_util.now().date().isoformat():
            raise ValidationError("La data proposta è già passata")
        payload = self.request_payload(self._find(self.requests, request_id, "Richiesta"))
        if payload.get("is_confirmed"):
            raise ValidationError("La richiesta è già confermata")
        offers = self._propose_alternatives(payload, day, alternatives or [])
        message = (text or "").strip() or self.format_propose_message(payload, day, clock, offers)
        if dry_run:
            return {"request_id": request_id, "text": message, "alternatives": offers}
        phone = (payload.get("client") or {}).get("phone") or ""
        chat_id = messaging.whatsapp_chat_id(phone)
        if not chat_id:
            raise ValidationError("Il richiedente non ha un telefono per WhatsApp")
        result = await messaging.async_send_whatsapp(self.hass, chat_id, message, waha=self.waha)
        sent = bool(result.get("sent"))
        if not sent:
            raise ValidationError(
                f"Messaggio non inviato: {result.get('error') or 'WhatsApp non risponde'}"
            )
        async with self._lock:
            request = self._find(self.requests, request_id, "Richiesta")
            request["proposed_date"] = day
            request["proposed_time"] = (clock or "")[:5]
            request["proposed_at"] = dt_util.utcnow().isoformat()
            request["proposed_by"] = by_name
            request["proposed_alternatives"] = offers
            await self._async_save()
            payload = self.request_payload(request)
        return {"request": payload, "sent": True, "text": message}

    def _propose_alternatives(
        self, payload: dict[str, Any], day: str, items: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """The treatments offered instead, checked and with their names.

        ``day`` of an item is "asked" (the date the guest asked for, the
        default), "proposed" (the date offered) or a date. The price is the one
        typed in the card, else the list price of the treatment.
        """
        offers: list[dict[str, Any]] = []
        asked = str(payload.get("date") or "")
        for item in items:
            treatment = self._find(self.treatments, str(item.get("treatment_id") or ""), "Trattamento")
            when = str(item.get("day") or item.get("date") or "asked")
            if when == "asked":
                when = asked or day
            elif when == "proposed":
                when = day
            price = item.get("price")
            if price in (None, ""):
                price = treatment.get("price")
            try:
                price = round(float(price), 2) if price not in (None, "") else None
            except (TypeError, ValueError):
                raise ValidationError(f"Prezzo non valido per {treatment['name']}") from None
            offers.append(
                {
                    "treatment_id": treatment["id"],
                    "treatment_name": treatment["name"],
                    "price": price,
                    "date": when[:10],
                    "time": str(item.get("time") or "")[:5],
                }
            )
        return offers

    def format_propose_message(
        self,
        payload: dict[str, Any],
        day: str,
        clock: str = "",
        offers: list[dict[str, Any]] | None = None,
    ) -> str:
        """The text that offers another date, from the notifications tab."""
        template = str(self._data[KEY_SETTINGS].get("request_propose_message") or "").strip()
        if not template:
            template = DEFAULT_PROPOSE_MESSAGE
        client = payload.get("client") or {}
        names: list[str] = []
        for entry in payload.get("entries") or []:
            name = str(entry.get("treatment_name") or "").strip()
            if name and name not in names:
                names.append(name)
        if len(names) > 1:
            treatments = ", ".join(names[:-1]) + " e " + names[-1]
        else:
            treatments = names[0] if names else "il trattamento richiesto"
        asked = str(payload.get("date") or "")
        text = (
            template.replace("{nome}", str(client.get("first_name") or "").strip() or "ospite")
            .replace("{cognome}", str(client.get("last_name") or "").strip())
            .replace("{codice}", str(payload.get("code") or "—"))
            .replace("{data_richiesta}", _day_words(asked) if asked else "nella data richiesta")
            .replace("{trattamenti}", treatments)
            .replace("{data_proposta}", _day_words(day))
            .replace("{orario_proposto}", f" alle {clock[:5]}" if clock else "")
        )
        return self._with_alternatives(text, offers or [])

    def _with_alternatives(self, text: str, offers: list[dict[str, Any]]) -> str:
        """Put the alternatives where {alternativa} is, or before the goodbye."""
        settings = self._data[KEY_SETTINGS]
        block = ""
        if offers:
            intro = str(settings.get("request_propose_alt_intro") or DEFAULT_PROPOSE_ALT_INTRO).strip()
            line = str(settings.get("request_propose_alt_line") or DEFAULT_PROPOSE_ALT_LINE)
            lines = [
                line.replace("{trattamento_alternativo}", offer["treatment_name"])
                .replace("{prezzo_alternativo}", _euro(offer["price"]))
                .replace("{data_alternativa}", _day_words(offer["date"]))
                .replace("{orario_alternativo}", f" alle {offer['time']}" if offer["time"] else "")
                for offer in offers
            ]
            block = "\n".join([intro, *lines] if intro else lines)
        if "{alternativa}" in text:
            if block:
                return text.replace("{alternativa}", f"\n{block}\n")
            # No alternative: the placeholder leaves no empty lines behind.
            return re.sub(r"\n*\{alternativa\}\n*", "\n\n", text).strip()
        if not block:
            return text
        # A text written before 2.2.2: the alternatives go before the goodbye.
        marker = text.find("\nCi risponda")
        if marker >= 0:
            return f"{text[:marker].rstrip()}\n\n{block}\n\n{text[marker:].lstrip()}"
        return f"{text.rstrip()}\n\n{block}"

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
        persons = {entry.get("person") for entry in entries if entry.get("person") is not None}
        for entry in sorted(entries, key=lambda e: (e.get("person") or 0, str(e.get("time") or ""))):
            name = str(entry.get("treatment_name") or "Trattamento")
            clock = str(entry.get("time") or "")
            if clock and not first_time:
                first_time = clock
            line = f"• {clock} {name}" if clock else f"• {name}"
            if len(persons) > 1:
                line += f" · Persona {(entry.get('person') or 0) + 1}"
            lines.append(line)
        return (
            template.replace("{nome}", str(client.get("first_name") or "").strip() or "ospite")
            .replace("{cognome}", str(client.get("last_name") or "").strip())
            .replace("{data}", _day_words(str(payload.get("date") or "")) if payload.get("date") else (str(payload.get("date_it") or "") or "—"))
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
        self, appointment_id: str, reason: str = "", whole_group: bool = False
    ) -> dict[str, Any]:
        """Cancel an appointment, keeping it in the history.

        ``whole_group`` (2.8.7) cancels with it every appointment of the same
        booking (same batch) still standing: the couple or the group at once.
        The payload of the one asked for carries ``cancelled_ids``.
        """
        async with self._lock:
            appointment = self._find(self.appointments, appointment_id, "Appuntamento")
            if appointment["status"] == STATUS_CANCELLED:
                raise ValidationError("L'appuntamento e' gia' annullato")
            targets = [appointment]
            batch = appointment.get("batch_id")
            if whole_group and batch:
                targets += [
                    a for a in self.appointments
                    if a is not appointment and a.get("batch_id") == batch and a["status"] != STATUS_CANCELLED
                ]
            now = dt_util.utcnow().isoformat()
            for item in targets:
                item["status"] = STATUS_CANCELLED
                item["cancel_reason"] = reason
                item["cancelled_at"] = now
                self._voucher_release(item)
            await self._async_save()

        payloads = [self.appointment_payload(item) for item in targets]
        for payload in payloads:
            self.hass.bus.async_fire(EVENT_APPOINTMENT_CANCELLED, payload)
            await self._async_notify_operator(
                payload, "Appuntamento annullato", show_operator=False
            )
        result = dict(payloads[0])
        result["cancelled_ids"] = [p["id"] for p in payloads]
        return result

    def _group_members(self, appointment: dict[str, Any]) -> list[dict[str, Any]]:
        batch = appointment.get("batch_id")
        if not batch:
            return [appointment]
        return [a for a in self.appointments if a.get("batch_id") == batch]

    async def async_split_from_group(self, appointment_id: str) -> dict[str, Any]:
        """Take one person, with all her treatments, out of a group (2.8.8).

        She becomes a booking of her own: new code, same client card, her
        payments and voucher takings with her. The people left are numbered
        again from Persona 1.
        """
        async with self._lock:
            appointment = self._find(self.appointments, appointment_id, "Appuntamento")
            members = self._group_members(appointment)
            active = [a for a in members if a.get("status") != STATUS_CANCELLED]
            person = appointment.get("person") or 0
            people = {a.get("person") or 0 for a in active}
            if len(people) < 2:
                raise ValidationError("Nel gruppo c'è una sola persona: non c'è niente da scollegare")
            moving = [a for a in members if (a.get("person") or 0) == person]
            codes = {a["code"] for a in self.appointments if a.get("code")}
            batch_id = _new_id("batch")
            code = _new_code(codes)
            for item in moving:
                item["batch_id"] = batch_id
                item["code"] = code
                item["person"] = 0
            staying = [a for a in members if a not in moving]
            order = sorted({a.get("person") or 0 for a in staying})
            renumber = {old: new for new, old in enumerate(order)}
            for item in staying:
                item["person"] = renumber[item.get("person") or 0]
            await self._async_save()
        return {
            "code": code,
            "batch_id": batch_id,
            "appointments": [self.appointment_payload(a) for a in moving],
        }

    async def async_join_group(self, appointment_id: str, code: str) -> dict[str, Any]:
        """Add another booking, found by its code, to this group (2.8.8).

        Its people come after the ones already in the group, keep their own
        client card and take the group's code.
        """
        wanted = str(code or "").strip().upper()
        if not wanted:
            raise ValidationError("Scrivi il codice della prenotazione da aggiungere")
        async with self._lock:
            appointment = self._find(self.appointments, appointment_id, "Appuntamento")
            if appointment.get("status") == STATUS_CANCELLED:
                raise ValidationError("La prenotazione è annullata")
            if not appointment.get("batch_id"):
                appointment["batch_id"] = _new_id("batch")
            target = appointment["batch_id"]
            group = self._group_members(appointment)
            group_code = appointment.get("code") or ""
            if wanted == group_code.upper():
                raise ValidationError("È il codice di questa stessa prenotazione")
            joining = [
                a for a in self.appointments
                if str(a.get("code") or "").upper() == wanted and a.get("batch_id") != target
            ]
            if not joining:
                raise ValidationError(f"Nessuna prenotazione con il codice {wanted}")
            if all(a.get("status") == STATUS_CANCELLED for a in joining):
                raise ValidationError(f"La prenotazione {wanted} è annullata")
            # Every appointment of the other booking(s), not only those with
            # the code typed: an old group may still have a code per person.
            batches = {a.get("batch_id") for a in joining if a.get("batch_id")}
            joining += [a for a in self.appointments if a.get("batch_id") in batches and a not in joining]
            offset = max((a.get("person") or 0) for a in group) + 1
            for items in _group_by(joining, lambda a: a.get("batch_id") or a["id"]).values():
                for item in items:
                    item["person"] = offset + (item.get("person") or 0)
                offset = max(item["person"] for item in items) + 1
            for item in joining:
                item["batch_id"] = target
                item["code"] = group_code or item.get("code")
            await self._async_save()
        return {
            "code": group_code,
            "batch_id": target,
            "appointments": [self.appointment_payload(a) for a in self._group_members(appointment)],
        }

    def format_cancel_message(self, payloads: list[dict[str, Any]], reason: str = "") -> str:
        """The guest's cancellation message for one or more appointments (2.8.7)."""
        ordered = sorted(payloads, key=lambda p: str(p.get("start_local") or ""))
        first = ordered[0]
        client = first.get("client") or {}
        settings = self._data[KEY_SETTINGS]
        days = sorted({str(p.get("start_local") or "")[:10] for p in ordered if p.get("start_local")})
        values = {
            "{nome}": str(client.get("first_name") or "").strip() or "ospite",
            "{cognome}": str(client.get("last_name") or "").strip(),
            "{hotel}": str(settings.get("guest_header") or "").strip() or DEFAULT_GUEST_HEADER,
            "{data}": " e ".join(_day_words(day) for day in days) if days else "—",
            "{appuntamenti}": "\n".join(self._appointment_lines(ordered)),
            "{trattamenti}": "\n".join(self._appointment_lines(ordered)),
            "{codice}": ", ".join(dict.fromkeys(str(p.get("code") or "") for p in ordered if p.get("code"))) or "—",
            "{motivo}": reason,
        }
        text = str(settings.get("cancel_message") or "").strip() or DEFAULT_CANCEL_MESSAGE
        if not reason:
            text = "\n".join(line for line in text.split("\n") if "{motivo}" not in line)
        for key, value in values.items():
            text = text.replace(key, value)
        return text

    async def async_send_cancel_message(self, appointment_ids: list[str]) -> dict[str, Any]:
        """Tell the guests their booking is cancelled: one message per number (2.8.7).

        A party booked on one card gets one message with every appointment;
        people with their own number each get theirs.
        """
        by_chat: dict[str, list[dict[str, Any]]] = {}
        reason = ""
        for item in self.appointments:
            if item["id"] not in appointment_ids:
                continue
            reason = reason or str(item.get("cancel_reason") or "")
            payload = self.appointment_payload(item)
            chat_id = messaging.whatsapp_chat_id(str((payload.get("client") or {}).get("phone") or ""))
            if chat_id:
                by_chat.setdefault(chat_id, []).append(payload)
        if not by_chat:
            return {"sent": 0, "failed": 0, "error": "Nessun numero WhatsApp nella scheda del cliente"}
        sent = failed = 0
        error = ""
        for chat_id, payloads in by_chat.items():
            try:
                result = await messaging.async_send_whatsapp(
                    self.hass, chat_id, self.format_cancel_message(payloads, reason), waha=self.waha)
            except Exception as err:  # noqa: BLE001
                result = {"sent": False, "error": str(err)}
            if result.get("sent"):
                sent += 1
            else:
                failed += 1
                error = str(result.get("error") or error)
        return {"sent": sent, "failed": failed, "error": error}

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
                arrived = True
            else:
                if not appointment["checked_in"]:
                    raise ValidationError("L'ingresso non e' registrato")
                appointment["checked_in"] = False
                appointment["checked_in_at"] = ""
                arrived = False
            await self._async_save()
        # The guest arrived with a voucher bought online: redeem it on the
        # shop too (2.7.0). Best effort; a failure is retried by the sync.
        if arrived:
            voucher = next((v for v in self.vouchers if v.get("source") == "wordpress"
                            and appointment["id"] in v.get("appointment_ids", []) and not v.get("wp_redeemed")), None)
            if voucher is not None:
                await self.async_wp_redeem(voucher["id"])
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
        if handled and answer == ANSWER_DECLINE and payload.get("offer_state") == OFFER_UNASSIGNED:
            await self._async_alert_unassigned(payload)
        return {
            "handled": handled,
            "answer": answer,
            "reason": reason,
            "appointment": payload,
        }

    async def _async_alert_unassigned(self, payload: dict[str, Any]) -> None:
        """Tell the desk that no masseuse took a booking (2.3.5).

        Before, the booking only turned «Da assegnare» in the card. Now the
        reception numbers (the ones of the website notices) get a WhatsApp
        and Home Assistant shows a notification.
        """
        text = (
            "⚠️ Nessuna massaggiatrice ha accettato "
            f"{self._summary(payload)}.\nAssegnalo a mano da Spa Booking."
        )
        for target in notify_numbers(self._data[KEY_SETTINGS].get("web_notify_whatsapp")):
            try:
                await messaging.async_send_whatsapp(self.hass, target, text, waha=self.waha)
            except Exception as err:  # noqa: BLE001
                _LOGGER.warning("Avviso «da assegnare» a %s fallito: %s", target, err)
        try:
            await self.hass.services.async_call(
                "persistent_notification",
                "create",
                {
                    "title": "Spa Booking: massaggio da assegnare",
                    "message": text,
                    "notification_id": f"spa_booking_unassigned_{payload.get('id')}",
                },
                blocking=False,
            )
        except Exception:  # noqa: BLE001
            _LOGGER.debug("Notifica persistente non disponibile")

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
        for extra_id in [] if appointment.get("extras_included") else appointment.get("extras") or []:
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
        except (TypeError, ValueError) as err:
            raise ValidationError("Importo incasso non valido") from err
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
        # The reply is noted in the conversation by the send itself (2.8.4).
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
        # A party is confirmed as a whole (2.8.2): from one appointment the
        # message reaches every person booked with it (same batch), so a couple
        # reads both treatments, the total of both and the balance of both.
        ids = list(dict.fromkeys(ids))
        for item in list(ids):
            anchor = next((a for a in self.appointments if a["id"] == item), None)
            batch = (anchor or {}).get("batch_id")
            if not batch:
                continue
            for other in self.appointments:
                if (
                    other.get("batch_id") == batch
                    and other["id"] not in ids
                    and other.get("status") != STATUS_CANCELLED
                    and other.get("client_id") == anchor.get("client_id")
                ):
                    ids.append(other["id"])
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
        # One message for the whole party (2.3.5): before, the text was
        # repeated once per person.
        message = self.format_summary_group(payloads)
        result = await messaging.async_send_whatsapp(
            self.hass, chat_id, message, waha=self.waha
        )
        if result.get("sent"):
            # The card shows "Reinvia conferma" and when it went out.
            async with self._lock:
                now = dt_util.utcnow().isoformat()
                for item in ids:
                    appointment = next((a for a in self.appointments if a["id"] == item), None)
                    if appointment is not None:
                        appointment["confirmation_sent_at"] = now
                await self._async_save()
        return {
            "appointment_id": ids[0],
            "appointment_ids": ids,
            "sent": bool(result.get("sent")),
            "result": result,
        }

    async def async_send_deposit_request(
        self, appointment_id: str, *, resend: bool = False
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
            if appointment.get("deposit_request_sent") and not resend:
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
            appointment["deposit_request_sent_at"] = dt_util.utcnow().isoformat()
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

    def format_promo(
        self,
        client: dict[str, Any],
        code: str = "",
        promo: dict[str, Any] | None = None,
    ) -> str:
        """Return the promotional message personalised for one guest.

        ``{nome}`` / ``{cognome}`` / ``{codice}`` are filled from the client
        card and her latest booking; ``{codice_promo}`` / ``{scadenza_promo}``
        from the promo. Without ``promo`` the old single promo of the settings
        is used.
        """
        settings = self._data.get(KEY_SETTINGS, {})
        if promo is None:
            promo = {
                "message": settings.get("promo_message"),
                "code": settings.get("promo_code"),
                "expiry": settings.get("promo_expiry"),
            }
        template = str(promo.get("message") or "").strip() or DEFAULT_PROMO_MESSAGE
        first_name = str(client.get("first_name") or "").strip()
        last_name = str(client.get("last_name") or "").strip()
        package = self.promo_package(promo)
        for key in ("{pacchetto}", "{prezzo_pacchetto}", "{prezzo_listino}", "{link_pacchetto}"):
            template = template.replace(key, package.get(key, ""))
        return (
            template.replace("{nome}", first_name or "ospite")
            .replace("{cognome}", last_name)
            .replace("{codice}", str(code or ""))
            .replace("{codice_promo}", str(promo.get("code") or ""))
            .replace("{scadenza_promo}", _date_it(str(promo.get("expiry") or "")))
        )

    def promo_package(self, promo: dict[str, Any]) -> dict[str, str]:
        """Name, price and link of the shop package a promo offers (2.8.5).

        Read from the shop's current product list, so a renamed product or a
        new price is used at once; the snapshot saved with the promo is the
        fallback when the product is no longer on the site. The link is the
        product page: the plugin sends it (1.1.0), else the WordPress
        «?post_type=product&p=ID» address, which leads to the same page.
        """
        key = str(promo.get("product_key") or "")
        if not key:
            return {}
        settings = self._data.get(KEY_SETTINGS, {})
        product = next((p for p in settings.get("wp_products") or [] if p.get("key") == key), None) or {}
        name = str(product.get("name") or promo.get("product_name") or "").strip()
        listed = product.get("price") if product.get("price") is not None else promo.get("product_price")
        offer = promo.get("product_promo_price")
        url = str(product.get("url") or promo.get("product_url") or "").strip()
        base = str(settings.get("wp_url") or "").rstrip("/")
        if not url and base and key.split(":")[0].isdigit():
            if not base.startswith(("http://", "https://")):
                base = "https://" + base
            url = f"{base}/?post_type=product&p={key.split(':')[0]}"
        price = offer if offer is not None else listed
        return {
            "{pacchetto}": name,
            "{prezzo_pacchetto}": _money_text(price) if price is not None else "",
            "{prezzo_listino}": _money_text(listed) if listed is not None else "",
            "{link_pacchetto}": url,
        }

    def _promo_expiry(self, promo: dict[str, Any] | None = None) -> date | None:
        """The last day the promo may go out, or None when it has no expiry."""
        source = promo.get("expiry") if promo is not None else (
            self._data.get(KEY_SETTINGS, {}).get("promo_expiry")
        )
        raw = str(source or "")
        return datetime.strptime(raw, "%Y-%m-%d").date() if raw else None

    def _promo_by_id(self, promo_id: str) -> dict[str, Any]:
        """One saved promo campaign (2.3.9)."""
        for promo in self._data.get(KEY_SETTINGS, {}).get("promos") or []:
            if promo.get("id") == promo_id:
                return promo
        raise ValidationError("Promo non trovata: forse è stata eliminata")

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
        promo_id: str | None = None,
    ) -> dict[str, Any]:
        """Broadcast the promotional message to the chosen clients.

        Each send is spaced out by ``promo_interval_sec`` so the WAHA add-on is
        never flooded. Without ``client_ids`` every client with a phone gets it.
        ``promo_id`` picks a saved campaign (its text, code and expiry);
        ``message`` replaces the text.
        """
        promo: dict[str, Any] | None = (
            self._promo_by_id(promo_id) if promo_id else None
        )
        if message is not None and message.strip():
            base = promo or {
                "code": self._data.get(KEY_SETTINGS, {}).get("promo_code"),
                "expiry": self._data.get(KEY_SETTINGS, {}).get("promo_expiry"),
            }
            text_promo: dict[str, Any] | None = {**base, "message": message.strip()}
        else:
            text_promo = promo
        template = (
            str((text_promo or {}).get("message") or "").strip()
            if text_promo is not None
            else str(self._data.get(KEY_SETTINGS, {}).get("promo_message") or "").strip()
        ) or DEFAULT_PROMO_MESSAGE
        expiry = self._promo_expiry(text_promo)
        if expiry and dt_util.as_local(dt_util.utcnow()).date() > expiry:
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
                client, self._last_client_code(client["id"]), text_promo
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
                    # Counted on the client card (2.3.2).
                    client["promo_sent_count"] = int(client.get("promo_sent_count") or 0) + 1
                    client["promo_last_sent_at"] = dt_util.utcnow().isoformat()
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
        if promo is not None:
            # Counted on the campaign too, for the list in the Promo tab.
            promo["sent_count"] = int(promo.get("sent_count") or 0) + sent
            promo["sent_at"] = dt_util.utcnow().isoformat()
        if sent or promo is not None:
            async with self._lock:
                await self._async_save()
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
        """Automatic sends of the saved promo campaigns.

        Called every few minutes by the scheduler. A campaign is due from its
        ``time`` for one hour (a tick that lands late still sends, a restart in
        the afternoon does not fire a morning promo), on its ``date`` when it
        goes once, or every day from its ``date`` until its expiry. Each one is
        stamped before sending, so it never goes out twice in a day.
        """
        settings = self._data.get(KEY_SETTINGS, {})
        now_local = dt_util.as_local(dt_util.utcnow())
        today = now_local.date().isoformat()
        minutes_now = now_local.hour * 60 + now_local.minute
        results: dict[str, Any] = {}
        for promo in list(settings.get("promos") or []):
            mode = promo.get("mode")
            if mode not in ("giorno", "ogni") or not promo.get("time"):
                continue
            target = self._minutes_of(str(promo["time"]))
            if target < 0 or not 0 <= minutes_now - target < 60:
                continue
            start = str(promo.get("date") or "")
            if mode == "giorno" and start != today:
                continue
            if mode == "ogni" and start and today < start:
                continue
            if mode == "giorno" and promo.get("last_sent_on"):
                continue
            if promo.get("last_sent_on") == today:
                continue
            expiry = self._promo_expiry(promo)
            if expiry and now_local.date() > expiry:
                continue
            async with self._lock:
                promo["last_sent_on"] = today
                await self._async_save()
            try:
                results[promo["id"]] = await self.async_send_promo(
                    promo_id=promo["id"]
                )
            except ValidationError as err:
                results[promo["id"]] = {"sent": 0, "reason": str(err)}
        if not results:
            return {"sent": 0, "total": 0, "reason": "nessuna promo da inviare ora"}
        return {
            "sent": sum(int(r.get("sent") or 0) for r in results.values()),
            "promos": results,
        }

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

        # The history names the masseuse who answered on WhatsApp.
        if ACTOR.get() is None:
            name = (self._operator(operator_id) or {}).get("name") or "Operatrice"
            ACTOR.set(("", f"{name} (WhatsApp)"))
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
                await self._async_alert_unassigned(self.appointment_payload(appointment))
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
        skip_weekdays: list[int] | None = None,
    ) -> dict[str, Any]:
        """Close a range of days for the facility, a category or an operator.

        ``skip_weekdays`` (Monday = 0) are left open inside the range.
        """
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
                    "skip_weekdays": (skip_weekdays or []) if last > first else [],
                }
            )
            if not self._closure_days(closure):
                raise ValidationError(
                    "Con i giorni esclusi la chiusura non coprirebbe nessun giorno"
                )
            self.closures.append(closure)
            await self._async_save()
        return closure

    async def async_delete_closure(self, closure_id: str) -> dict[str, Any]:
        """Reopen the days a closure was holding."""
        async with self._lock:
            self._find(self.closures, closure_id, "Chiusura")
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
        # Tokens of the needle, so "mario rossi" matches even when the
        # haystack joins names and phone in a different order.
        needle_tokens = needle.split()
        matches: list[dict[str, Any]] = []
        # Build haystacks once, lowering each field a single time.
        for client in self.clients:
            first = (client.get("first_name") or "")
            last = (client.get("last_name") or "")
            phone = (client.get("phone") or "")
            email = (client.get("email") or "")
            haystack = f"{first} {last} {phone} {email}".lower()
            if needle and not all(tok in haystack for tok in needle_tokens):
                continue
            matches.append(self.client_payload(client))
            if len(matches) >= limit:
                break
        matches.sort(
            key=lambda c: ((c.get("last_name") or "").lower(), (c.get("first_name") or "").lower())
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
            self._find(self.clients, client_id, "Cliente")
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
            self._find(self.categories, category_id, "Categoria")
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
        vat_rate: float | None = None,
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
                    "vat_rate": vat_rate,
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
        vat_rate: float | None = None,
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
            if vat_rate is not None:
                # A negative rate from the card means «use the default».
                treatment["vat_rate"] = _norm_vat(vat_rate)
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
            self._find(self.treatments, treatment_id, "Trattamento")
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
        gender: str = "",
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
                    "gender": gender,
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
        gender: str | None = None,
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
            if gender is not None:
                operator["gender"] = gender if gender in ("F", "M") else ""
            await self._async_save()
        return operator

    async def async_delete_operator(
        self, operator_id: str, force: bool = False
    ) -> dict[str, Any]:
        """Delete an operator, refusing to orphan future appointments."""
        async with self._lock:
            self._find(self.operators, operator_id, "Operatore")
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

        for (_client_id, _day), items in groups.items():
            # Clustering per contiguita' temporale
            clusters: list[list[dict[str, Any]]] = []
            for item in sorted(items, key=lambda a: str(a.get("start") or "")):
                if not clusters:
                    clusters.append([item])
                    continue
                last = clusters[-1]
                # contiguita' se l'ultimo intervallo e' sovrapposto o gap <= 15 min
                contiguous = True
                try:
                    last_end_dt = dt_util.parse_datetime(str(last[-1].get("end") or ""))
                    cur_start_dt = dt_util.parse_datetime(str(item.get("start") or ""))
                    if last_end_dt is not None and cur_start_dt is not None:
                        gap_min = (cur_start_dt - last_end_dt).total_seconds() / 60.0
                        if gap_min > 15:
                            contiguous = False
                except (ValueError, TypeError, AttributeError):
                    contiguous = False

                if contiguous:
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
            # A restored backup is not a list of changes made now.
            self._history_snap = None
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
            KEY_SETTINGS: {
                **self._data[KEY_SETTINGS],
                KEY_PROFILES: access.public_profiles(
                    self._data[KEY_SETTINGS].get(KEY_PROFILES) or {}
                ),
            },
            KEY_PERMISSIONS: self.permissions_payload(),
        }

    def permissions_payload(self) -> dict[str, str]:
        """Return the access level chosen for each user."""
        return dict(self._data[KEY_SETTINGS].get(KEY_PERMISSIONS) or {})

    def user_level(self, user_id: str | None) -> str:
        """Return the level stored for a user in the Accessi tab, or "none".

        Home Assistant administrators and calls without a user are handled by
        ``services.caller_level``, which needs the auth store.
        """
        if not user_id:
            return "none"
        level = self.permissions_payload().get(user_id)
        return level if level in PERMISSION_LEVELS else "none"

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
        self.pin_sessions.end_user(user_id)
        return dict(permissions)

    # ------------------------------------------------- logins and the PIN

    def profiles(self) -> dict[str, dict[str, Any]]:
        """The stored user profiles, PIN hashes included."""
        return dict(self._data[KEY_SETTINGS].get(KEY_PROFILES) or {})

    def profile(self, user_id: str | None) -> dict[str, Any]:
        """One user's profile (empty when she has none)."""
        return dict(self.profiles().get(user_id or "") or {})

    @property
    def pin_idle_minutes(self) -> int:
        """Minutes of inactivity before the shared tablet signs out."""
        return int(self._data[KEY_SETTINGS].get("pin_idle_minutes") or 10)

    async def async_set_user_profile(
        self,
        user_id: str,
        *,
        operator_id: str | None = None,
        shared: bool | None = None,
        pin: str | None = None,
        clear_pin: bool = False,
    ) -> dict[str, Any]:
        """Link a user to an operator, mark the shared tablet, set her PIN."""
        if pin is not None and pin != "" and not access.valid_pin(pin):
            raise SpaBookingError("Il PIN deve essere di 4 cifre")
        async with self._lock:
            profiles = self.profiles()
            profile = dict(profiles.get(user_id) or {
                "operator_id": "", "shared": False, "pin_salt": "", "pin_hash": "",
            })
            if operator_id is not None:
                if operator_id and not any(
                    op["id"] == operator_id for op in self.operators
                ):
                    raise SpaBookingError("Operatrice non trovata")
                if operator_id:
                    for other_id, other in profiles.items():
                        if other_id != user_id and other.get("operator_id") == operator_id:
                            raise SpaBookingError(
                                "Questa operatrice è già collegata a un altro utente"
                            )
                profile["operator_id"] = operator_id
            if shared is not None:
                profile["shared"] = bool(shared)
            if clear_pin:
                profile["pin_salt"] = profile["pin_hash"] = ""
            elif pin:
                # Each PIN belongs to one person: it is also her signature
                # on a voucher, so two people may not share it.
                for other_id, other in profiles.items():
                    if other_id != user_id and other.get("pin_hash") and await self.hass.async_add_executor_job(
                        access.check_pin, pin, other.get("pin_salt", ""), other.get("pin_hash", "")
                    ):
                        raise SpaBookingError("Questo PIN è già usato da un'altra persona: scegline un altro")
                profile["pin_salt"], profile["pin_hash"] = await self.hass.async_add_executor_job(
                    access.hash_pin, pin
                )
            profiles[user_id] = profile
            self._data[KEY_SETTINGS][KEY_PROFILES] = profiles
            await self._async_save()
        # A new PIN, operator or role takes effect at the next sign-in.
        self.pin_sessions.end_user(user_id)
        return access.public_profiles({user_id: profile})[user_id]

    async def async_users_payload(self) -> list[dict[str, Any]]:
        """Return the Home Assistant users for the Accessi tab.

        System users (Supervisor, Cast, Content, integration tokens...) are
        excluded: they are not people and cannot be granted access.
        """
        try:
            users = await self.hass.auth.async_get_users()
            profiles = access.public_profiles(self.profiles())
            return [
                {
                    "id": user.id,
                    "name": user.name or user.id,
                    "is_admin": user.is_admin,
                    "is_owner": user.is_owner,
                    "is_active": user.is_active,
                    "username": next(
                        (
                            str(cred.data.get("username") or "")
                            for cred in getattr(user, "credentials", None) or []
                            if cred.auth_provider_type == "homeassistant"
                        ),
                        "",
                    ),
                    **profiles.get(user.id, {"operator_id": "", "shared": False, "has_pin": False}),
                }
                for user in users
                # A disabled user stays listed, so she can be enabled again.
                if not user.system_generated
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
            if isinstance(changes.get("promos"), list):
                # What the sends wrote stays: the card only edits the campaign.
                done = {
                    p.get("id"): p for p in settings.get("promos") or []
                }
                kept = []
                for item in changes["promos"]:
                    if not isinstance(item, dict):
                        continue
                    item = dict(item)
                    before = done.get(item.get("id"))
                    if before is None:
                        item.update(
                            last_sent_on="", sent_at="", sent_count=0,
                            created_at=dt_util.utcnow().isoformat(),
                        )
                    else:
                        for key in ("last_sent_on", "sent_at", "sent_count", "created_at"):
                            item[key] = before.get(key)
                        if (item.get("mode"), item.get("date")) != (
                            before.get("mode"), before.get("date")
                        ):
                            # A new day (or way) of sending: it may go again.
                            item["last_sent_on"] = ""
                    kept.append(item)
                changes["promos"] = kept
            if isinstance(changes.get("partner_campaigns"), list):
                # What the sends wrote stays: the card edits only the text and the day.
                done_c = {c.get("id"): c for c in settings.get("partner_campaigns") or []}
                merged = []
                for item in changes["partner_campaigns"]:
                    if not isinstance(item, dict):
                        continue
                    before = done_c.get(item.get("id"))
                    item = dict(item)
                    for key in ("sent_at", "sent_count", "last_error"):
                        item[key] = (before or {}).get(key, "" if key != "sent_count" else 0)
                    if before and (item.get("date"), item.get("time"), item.get("mode")) != (
                        before.get("date"), before.get("time"), before.get("mode")
                    ):
                        item["sent_at"] = ""  # a new day: it may go again
                    merged.append(item)
                changes["partner_campaigns"] = merged
            # The card never sees the mailbox password: empty means «keep it».
            for secret in ("smtp_password", "google_client_secret"):
                if changes.get(secret) == "":
                    changes.pop(secret)
            for key, value in changes.items():
                if key in settings and value is not None:
                    settings[key] = value
            settings = _norm_settings(settings)
            pairing_changed = "wp_product_map" in changes
            # Switching the website on issues its token straight away, so the
            # card can show the value to copy before the first guest arrives;
            # switching it off keeps the token, ready for the next season.
            if settings.get("web_enabled") and not str(
                settings.get("web_token") or ""
            ).strip():
                settings["web_token"] = secrets.token_urlsafe(32)
            self._data[KEY_SETTINGS] = settings
            if pairing_changed:
                self._wp_apply_pairing()
            await self._async_save()
        if "whatsapp_engine" in changes:
            await self.async_apply_whatsapp_engine()
        if "telegram_bot_token" in changes:
            await self.async_apply_telegram()
        return dict(self._data[KEY_SETTINGS])

    # --------------------------------------------------------------- Telegram

    async def async_apply_telegram(self) -> None:
        """Start, restart or stop the bot built into Spa Booking (2.9.0)."""
        from .telegram_native import TelegramBot

        token = str(self._data[KEY_SETTINGS].get("telegram_bot_token") or "").strip()
        current = getattr(self, "telegram", None)
        if current is not None and current.token == token:
            return
        await self.async_stop_telegram()
        if not token:
            return

        def on_update(data: dict[str, Any]) -> None:
            self.hass.bus.async_fire(EVENT_ANSWER_REQUEST, data)

        bot = TelegramBot(self.hass, token, on_update)
        self.telegram = bot
        messaging.set_telegram_bot(bot)
        await bot.async_start()

    async def async_stop_telegram(self) -> None:
        bot = getattr(self, "telegram", None)
        self.telegram = None
        messaging.set_telegram_bot(None)
        if bot is not None:
            await bot.async_stop()

    async def async_telegram_status(self) -> dict[str, Any]:
        bot = getattr(self, "telegram", None)
        if bot is None:
            return {"configured": False, "ok": False, "error": "", "recent": []}
        if not bot.me:
            from .telegram_native import TelegramError

            try:
                await bot.async_get_me()
            except TelegramError as err:
                bot.error = str(err)
        return bot.status()

    # ------------------------------------------------------------------- WAHA

    @property
    def whatsapp_engine(self) -> str:
        """Always "integrated": the WAHA add-on is gone (2.9.0)."""
        return "integrated"

    async def async_apply_whatsapp_engine(self) -> None:
        """Start or stop the built-in WhatsApp connection to match the settings."""
        if self.whatsapp_engine == "integrated":
            if self.wa_bridge is None:
                inbound = WahaInbound(
                    self.hass, self, webhook_id="", secret="", session="spa"
                )
                self.wa_bridge = WaBridge(self.hass, inbound)
                self.wa_bridge.listeners.append(self.async_update_listeners)
                await self.wa_bridge.async_start()
        elif self.wa_bridge is not None:
            bridge, self.wa_bridge = self.wa_bridge, None
            await bridge.async_stop()

    async def async_stop_whatsapp(self) -> None:
        """Stop the built-in connection (entry unloaded, Home Assistant closing)."""
        if self.wa_bridge is not None:
            bridge, self.wa_bridge = self.wa_bridge, None
            await bridge.async_stop()

    @property
    def waha(self) -> WaBridge | None:
        """The WhatsApp connection built into Spa Booking, or None while it is off.

        The name stays for the many senders that pass ``waha=self.waha``.
        """
        return self.wa_bridge

    async def async_check_waha(self) -> dict[str, Any]:
        """Ask WAHA who it is, so the card can prove the configuration works.

        The answer carries nothing secret: the version and the engine, plus a
        readable error when the add-on is unreachable or the key is refused.
        """
        client = self.waha
        if client is None:
            return {"configured": True, "ok": False, "error": "WhatsApp integrato non avviato"}
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

    def _card_file_version(self) -> str:
        """Return the short content hash of the card, computed at load time."""
        return self._card_version or CARD_JS_VERSION

    async def async_refresh_card_version(self) -> str:
        """Re-hash the card file in the executor and remember the result."""
        from .card_view import card_version, read_card

        read = await self.hass.async_add_executor_job(read_card)
        self._card_version = card_version(read[0]) if read else ""
        return self._card_file_version()

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
        await self.async_refresh_card_version()
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
            # The history goes to the administrator through export_data only.
            **{key: value for key, value in appointment.items() if key != "history"},
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
            "{appuntamenti}": "\n".join(self._appointment_lines([payload])),
        }
        if "{appuntamenti}" in template:
            values["{data}"] = _day_words(start[:10]) if start else "—"
            values["{appuntamenti}"] = "\n".join(self._appointment_lines([payload], with_price=True))
        text = self._with_discount(template, self._discount_line([payload]))
        for key, value in values.items():
            text = text.replace(key, value)
        return text

    def _discount_of(self, payload: dict[str, Any]) -> tuple[float, float, float]:
        """(list price, price paid, percent) of a discounted treatment (2.8.7).

        (0, 0, 0) when the guest pays the list price. The percent is the
        partner's when the discount is hers, else worked out from the prices.
        """
        price = payload.get("price")
        if price is None:
            return (0.0, 0.0, 0.0)
        listed = payload.get("list_price")
        if listed is None:
            treatment = next((t for t in self.treatments if t["id"] == payload.get("treatment_id")), None)
            listed = (treatment or {}).get("price")
        try:
            listed, price = float(listed), float(price)
        except (TypeError, ValueError):
            return (0.0, 0.0, 0.0)
        if listed <= 0 or price >= listed - 0.004:
            return (0.0, 0.0, 0.0)
        pct = float(payload.get("partner_discount_pct") or 0) or round((1 - price / listed) * 100, 1)
        return (round(listed, 2), round(price, 2), pct)

    def _discount_line(self, payloads: list[dict[str, Any]]) -> str:
        """«🎁 Sconto 10%: −16,00 €», or "" when nobody had a discount (2.8.7)."""
        saved = 0.0
        pcts = set()
        partner = False
        for payload in payloads:
            listed, price, pct = self._discount_of(payload)
            if listed:
                saved += listed - price
                pcts.add(pct)
                partner = partner or bool(payload.get("partner_discount_pct"))
        if saved <= 0:
            return ""
        label = "Sconto partner" if partner else "Sconto"
        if len(pcts) == 1:
            label += f" {_pct_text(next(iter(pcts)))}%"
        return f"🎁 {label}: −{_money_text(saved)}"

    @staticmethod
    def _with_discount(template: str, line: str) -> str:
        """Put the discount line in the text: at {sconto}, else above the total."""
        if "{sconto}" in template:
            if line:
                return template.replace("{sconto}", line)
            return "\n".join(row for row in template.split("\n") if row.strip() != "{sconto}").replace("{sconto}", "")
        if not line:
            return template
        rows = template.split("\n")
        for index, row in enumerate(rows):
            if "{totale}" in row or "{residuo}" in row:
                rows.insert(index, line)
                return "\n".join(rows)
        return template + "\n" + line

    def _appointment_lines(
        self,
        payloads: list[dict[str, Any]],
        *,
        with_day: bool | None = None,
        with_price: bool = False,
    ) -> list[str]:
        """"• 10:00–11:30 Massaggio Relax 90 min · Persona 2", one per booking.

        The person is named only for a party; the day only when the bookings
        are on different days.
        """
        ordered = sorted(payloads, key=lambda p: str(p.get("start_local") or ""))
        persons = {p.get("person") or 0 for p in ordered}
        days = {str(p.get("start_local") or "")[:10] for p in ordered}
        if with_day is None:
            with_day = len(days) > 1
        lines = []
        for payload in ordered:
            start = str(payload.get("start_local") or "")
            end = str(payload.get("end_local") or "")
            name = str((payload.get("treatment") or {}).get("name") or "Trattamento")
            when = start[11:16]
            if end[11:16]:
                when = f"{when}–{end[11:16]}"
            if with_day and start[:10]:
                when = f"{_day_words(start[:10])} {when}"
            line = f"• {when} {name}".rstrip()
            if len(persons) > 1:
                line += f" · Persona {(payload.get('person') or 0) + 1}"
            if with_price:
                # The price of this person's treatment (with her accessories),
                # so a party reads what each one costs before the total.
                price = float(self._payment_totals(payload).get("total") or 0)
                listed, paid, _pct = self._discount_of(payload)
                if price > 0 and listed:
                    # The list price struck through, then what she pays.
                    line += f" · ~{_money_text(price + listed - paid)}~ {_money_text(price)}"
                elif price > 0:
                    line += f" · {_money_text(price)}"
            lines.append(line)
        return lines

    def format_summary_group(self, payloads: list[dict[str, Any]]) -> str:
        """The confirmation of a whole booking, one message for the party.

        ``{appuntamenti}`` lists every appointment; ``{data}`` is the day (or
        the days); the money is the sum of the party. The single-appointment
        placeholders of the old text keep working: ``{trattamento}`` lists all
        the treatments, ``{ora}`` is the first start and ``{fine}`` the last end.
        """
        if len(payloads) == 1 and "{appuntamenti}" not in self._summary_template():
            return self.format_summary(payloads[0])
        ordered = sorted(payloads, key=lambda p: str(p.get("start_local") or ""))
        first, last = ordered[0], ordered[-1]
        client = first.get("client") or {}
        settings = self._data[KEY_SETTINGS]
        totals = {"total": 0.0, "collected": 0.0, "due": 0.0}
        deposit = 0.0
        payments: list[str] = []
        for payload in ordered:
            part = self._payment_totals(payload)
            for key in totals:
                totals[key] += float(part.get(key) or 0)
            deposit += float(payload.get("deposit_amount") or 0)
            if payload.get("payments"):
                payments.append(self._payment_lines(payload))
        days = sorted({str(p.get("start_local") or "")[:10] for p in ordered if p.get("start_local")})
        day_text = " e ".join(_day_words(day) for day in days) if days else "—"
        codes = list(dict.fromkeys(str(p.get("code") or "") for p in ordered if p.get("code")))
        start = str(first.get("start_local") or "")
        end = str(last.get("end_local") or "")
        values = {
            "{nome}": str(client.get("first_name") or "").strip() or "ospite",
            "{cognome}": str(client.get("last_name") or "").strip(),
            "{cliente}": str(client.get("full_name") or "").strip() or "ospite",
            "{hotel}": str(settings.get("guest_header") or "").strip() or DEFAULT_GUEST_HEADER,
            "{codice}": ", ".join(codes) or "—",
            "{appuntamenti}": "\n".join(self._appointment_lines(ordered, with_price=True)),
            # An old text without {appuntamenti}: each treatment with its own
            # price, so a party still reads what every person pays.
            "{trattamento}": " + ".join(
                str((p.get("treatment") or {}).get("name") or "n/d")
                + (
                    f" {_money_text(self._payment_totals(p).get('total'))}"
                    if len(ordered) > 1 and float(self._payment_totals(p).get("total") or 0) > 0
                    else ""
                )
                for p in ordered
            ),
            "{durata}": str(first.get("duration_min") or ""),
            "{data}": day_text,
            "{ora}": start[11:16] or "—",
            "{fine}": end[11:16] or "—",
            "{totale}": _money_text(totals["total"]),
            "{acconto}": _money_text(deposit),
            "{versato}": _money_text(totals["collected"]),
            "{residuo}": _money_text(totals["due"]),
            "{pagamenti}": "\n".join(payments) or "Nessun versamento registrato.",
        }
        text = self._with_discount(self._summary_template(), self._discount_line(ordered))
        if not totals["total"] and not totals["collected"]:
            # No price on the booking: the money line would read "0,00 €".
            text = "\n".join(
                line for line in text.split("\n")
                if not any(key in line for key in ("{totale}", "{versato}", "{residuo}"))
            )
        for key, value in values.items():
            text = text.replace(key, value)
        return text

    def _summary_template(self) -> str:
        return str(self._data[KEY_SETTINGS].get("summary_message") or "").strip() or DEFAULT_SUMMARY_MESSAGE

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

    def format_appointment_reminder(
        self, payload: dict[str, Any] | list[dict[str, Any]]
    ) -> str:
        """Return the customizable appointment reminder message.

        The wording comes from the notifications tab, so the reception changes
        it without touching code; an empty setting falls back to the built-in
        text. Given the appointments of one guest's day (a party, or two
        treatments) it is one message listing them all (2.3.5).
        """
        template = str(
            self._data[KEY_SETTINGS].get("appointment_reminder_message") or ""
        ).strip()
        if not template:
            template = DEFAULT_APPOINTMENT_REMINDER_MESSAGE
        payloads = payload if isinstance(payload, list) else [payload]
        payloads = sorted(payloads, key=lambda p: str(p.get("start_local") or ""))
        payload = payloads[0]

        start = payload.get("start_local") or ""
        client = payload.get("client") or {}

        # "Trattamenti: {trattamenti}" (the old text) wants them on one line;
        # {trattamenti} on its own line gets one line per appointment.
        inline = re.search(r"[^\n\s][^\n]*\{trattamenti\}", template) is not None
        if inline:
            treatment_names = ", ".join(
                self._treatment_names_for_payload(p) for p in payloads
            )
        else:
            treatment_names = "\n".join(self._appointment_lines(payloads, with_day=False))
        start_date = (_day_words(start[:10]) if not inline else self.format_day(start)) if start else "—"
        start_time = start[11:16] if len(start) >= 16 else "—"
        codes = list(dict.fromkeys(str(p.get("code") or "") for p in payloads if p.get("code")))

        return (
            template.replace("{nome}", str(client.get("first_name") or "").strip() or "ospite")
            .replace("{cognome}", str(client.get("last_name") or "").strip())
            .replace("{codice}", ", ".join(codes) or "—")
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
        self, appointment_id: str | None = None, *, manual: bool = False
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

        # In manual mode the timer sends nothing: only the desk does, for one
        # appointment or with «Invia promemoria ora» for the ones due.
        if not auto and not appointment_id and not manual:
            return {"sent": 0, "failed": 0, "reason": "invio manuale disabilitato"}

        now = dt_util.utcnow()
        advance_window: timedelta = timedelta(hours=hours)
        outbox: list[tuple[str, str]] = []
        # A manual send for one appointment reminds the guest of her whole
        # day: the party or her other treatments come in the same message.
        wanted: set[str] | None = None
        if appointment_id:
            target = self._find(self.appointments, appointment_id, "Appuntamento")
            day = (dt_util.as_local(dt_util.parse_datetime(target["start"])).date()
                   if dt_util.parse_datetime(target["start"]) else None)
            wanted = {
                a["id"] for a in self.appointments
                if a["id"] == appointment_id
                or (
                    a.get("client_id") and a.get("client_id") == target.get("client_id")
                    and a["status"] == STATUS_CONFIRMED
                    and dt_util.parse_datetime(a["start"])
                    and dt_util.as_local(dt_util.parse_datetime(a["start"])).date() == day
                )
            }
        groups: dict[tuple[str, str], list[dict[str, Any]]] = {}
        async with self._send_lock:
            async with self._lock:
                for appointment in self.appointments:
                    if wanted is not None and appointment["id"] not in wanted:
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
                    # Marked before sending, as before: a reminder is sent
                    # once, a failed one is not retried an hour later.
                    appointment["reminder_sent"] = True
                    appointment["reminder_sent_at"] = now.isoformat()
                    local_day = str(payload.get("start_local") or "")[:10]
                    groups.setdefault((chat_id, local_day), []).append(payload)
                for (chat_id, _day), payloads in groups.items():
                    message = self.format_appointment_reminder(payloads)
                    if not message:
                        message = self.format_reminder(payloads[0])
                    outbox.append((chat_id, message))
                if outbox:
                    await self._async_save()
            # Sent outside the data lock: the desk keeps booking meanwhile.
            sent = failed = 0
            for chat_id, message in outbox:
                result = await messaging.async_send_whatsapp(
                    self.hass, chat_id, message, waha=self.waha
                )
                if result.get("sent"):
                    sent += 1
                else:
                    failed += 1
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
        asked: set[tuple[str, str]] = set()
        outbox: list[tuple[str, str, str]] = []
        # 2.9.0: the button asks the whole booking, one message per number.
        wanted: set[str] = set()
        if appointment_id:
            anchor = next((a for a in self.appointments if a["id"] == appointment_id), None)
            wanted = {a["id"] for a in self._group_members(anchor)} if anchor else {appointment_id}
        chats_asked: set[str] = set()
        async with self._send_lock:
            async with self._lock:
                for appointment in self.appointments:
                    if appointment_id:
                        if appointment["id"] not in wanted:
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
                    if appointment_id and chat_id in chats_asked:
                        appointment["review_request_sent"] = True
                        continue
                    chats_asked.add(chat_id)
                    if not appointment_id:
                        end = dt_util.parse_datetime(appointment["end"])
                        day = dt_util.as_local(end).date().isoformat() if end else ""
                        guest_day = (appointment["client_id"], day)
                        if guest_day in asked:
                            # Same guest, same day, already asked: the review
                            # request is per person, not per treatment.
                            appointment["review_request_sent"] = True
                            continue
                        asked.add(guest_day)
                    # Claimed now so a parallel run cannot ask twice; a failed
                    # send is released below and tried again next time.
                    appointment["review_request_sent"] = True
                    outbox.append(
                        (appointment["id"], chat_id, self.format_review_request(payload))
                    )
                if outbox or asked:
                    await self._async_save()

            sent = 0
            failed_ids: set[str] = set()
            for record_id, chat_id, message in outbox:
                result = await messaging.async_send_whatsapp(
                    self.hass, chat_id, message, waha=self.waha
                )
                if result.get("sent"):
                    sent += 1
                else:
                    failed_ids.add(record_id)

            if failed_ids:
                async with self._lock:
                    for appointment in self.appointments:
                        if appointment["id"] in failed_ids:
                            appointment["review_request_sent"] = False
                    await self._async_save()
        return {"sent": sent, "failed": len(failed_ids)}

    async def async_send_voucher_expiry_reminders(self) -> dict[str, Any]:
        """Remind each voucher recipient once that her voucher is expiring.

        A voucher is due when it expires within ``voucher_expiry_reminder_days``
        and has not expired yet: a window rather than one exact day, so a day
        the system was off is caught up instead of skipped. The recipient gets
        one message per voucher, listing every person and treatment on it. The
        messages are sent outside the lock, so the desk can keep booking.
        """
        settings = self._data.get(KEY_SETTINGS, {})
        reminder_days = int(
            settings.get("voucher_expiry_reminder_days")
            or DEFAULT_VOUCHER_EXPIRY_REMINDER_DAYS
        )
        template = str(
            settings.get("voucher_expiry_reminder_message")
            or DEFAULT_VOUCHER_EXPIRY_REMINDER_MESSAGE
        )
        today = dt_util.now().date()
        horizon = today + timedelta(days=reminder_days)
        async with self._send_lock:
            return await self._async_send_voucher_expiry(
                template, today, horizon
            )

    async def _async_send_voucher_expiry(
        self, template: str, today: date, horizon: date
    ) -> dict[str, Any]:
        """The body of ``async_send_voucher_expiry_reminders``."""
        names = {t["id"]: t["name"] for t in self.treatments}

        due: list[tuple[str, str, str]] = []
        for voucher in self.vouchers:
            if voucher.get("status") != VOUCHER_ACTIVE:
                continue
            if voucher.get("expiry_reminder_sent"):
                continue
            expires_on = _norm_date(voucher.get("expires_on"))
            if not expires_on:
                continue
            expiry = date.fromisoformat(expires_on)
            if not today <= expiry <= horizon:
                continue
            chat_id = messaging.whatsapp_chat_id(
                str(voucher.get("recipient_phone") or "")
            )
            if not chat_id:
                continue
            people = voucher.get("people") or []
            treatments = ", ".join(
                names.get(str(t), str(t))
                for person in people
                for t in (person.get("treatment_ids") or [])
            ) or "nessun trattamento"
            total = sum(
                float(person.get("gift_card_amount") or 0) for person in people
            )
            recipient = str(voucher.get("recipient_name") or "").strip()
            first, _, last = recipient.partition(" ")
            message = (
                template.replace("{nome}", first or "ospite")
                .replace("{cognome}", last)
                .replace("{data_scadenza}", _date_it(expires_on))
                .replace("{codice}", str(voucher.get("code") or ""))
                .replace("{valore}", f"€ {total:.2f}" if total else "")
                .replace("{trattamenti}", treatments)
            )
            due.append((voucher["id"], chat_id, message))

        sent_ids: list[str] = []
        failed = 0
        for voucher_id, chat_id, message in due:
            result = await messaging.async_send_whatsapp(
                self.hass, chat_id, message, waha=self.waha
            )
            if result.get("sent"):
                sent_ids.append(voucher_id)
            else:
                # Left unflagged: the next tick tries again.
                failed += 1

        if sent_ids:
            async with self._lock:
                for voucher in self.vouchers:
                    if voucher["id"] in sent_ids:
                        voucher["expiry_reminder_sent"] = True
                await self._async_save()
        return {"sent": len(sent_ids), "failed": failed}

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
            # Last month: from its first day up to the first of this month.
            # (Up to 2.0.15 the end was the last day itself, so the automatic
            # report silently left out the last day of every month.)
            this_month = today.replace(day=1)
            last = this_month - timedelta(days=1)
            return last.replace(day=1), this_month

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

    async def _async_stamp_setting(self, key: str, value: Any) -> None:
        """Persist one bookkeeping value of the settings (a last-run stamp)."""
        async with self._lock:
            self._data[KEY_SETTINGS][key] = value
            await self._async_save()

    async def async_monthly_report_tick(self) -> dict[str, Any]:
        """Send last month's report once, on the 1st at ``report_time``.

        Called every few minutes by the scheduler. The month is stamped before
        sending, so a restart, a second timer or an old automation never send
        the same report twice; a missed exact minute is caught up later the
        same day.
        """
        settings = self._data[KEY_SETTINGS]
        if not settings.get("report_enabled", True):
            return {"sent": False, "reason": "report disattivato"}
        now_local = dt_util.now()
        if now_local.day != 1:
            return {"sent": False, "reason": "non è il primo del mese"}
        report_time = _norm_clock(settings.get("report_time")) or DEFAULT_REPORT_TIME
        if now_local.strftime("%H:%M") < report_time:
            return {"sent": False, "reason": f"in attesa delle {report_time}"}
        month = (now_local.date().replace(day=1) - timedelta(days=1)).strftime("%Y-%m")
        if settings.get("report_last_month") == month:
            return {"sent": False, "reason": f"report {month} già inviato"}
        await self._async_stamp_setting("report_last_month", month)
        result = await self.async_send_monthly_report(month)
        return {"sent": True, "month": month, **result}

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


_WEEKDAYS_IT = ("lunedì", "martedì", "mercoledì", "giovedì", "venerdì", "sabato", "domenica")
_MONTHS_IT = (
    "gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno",
    "luglio", "agosto", "settembre", "ottobre", "novembre", "dicembre",
)


def _day_words(value: str) -> str:
    """"domenica 15 novembre" from 2026-11-15 (the year only when not this one)."""
    try:
        day = date.fromisoformat(value[:10])
    except ValueError:
        return value
    text = f"{_WEEKDAYS_IT[day.weekday()]} {day.day} {_MONTHS_IT[day.month - 1]}"
    if day.year != dt_util.now().year:
        text += f" {day.year}"
    return text


def _euro(value: float | None) -> str:
    """"€ 160" or "€ 160,50"; "prezzo da definire" when unknown."""
    if value is None:
        return "prezzo da definire"
    if float(value).is_integer():
        return f"€ {int(value)}"
    return f"€ {value:.2f}".replace(".", ",")


_WEEKDAY_PLURALS = (
    "i lunedì", "i martedì", "i mercoledì", "i giovedì", "i venerdì", "i sabati", "le domeniche",
)


def skipped_days_words(days: list[int]) -> str:
    """"esclusi i sabati", "esclusi i sabati e le domeniche"."""
    words = [_WEEKDAY_PLURALS[day] for day in sorted(set(days)) if 0 <= day <= 6]
    if not words:
        return ""
    joined = words[0] if len(words) == 1 else f"{', '.join(words[:-1])} e {words[-1]}"
    return f"esclusi {joined}"


def notify_numbers(value: Any) -> list[str]:
    """The numbers of a notice field: one per line, or split by , and ;."""
    return [
        part.strip()
        for part in re.split(r"[\n,;]+", str(value or ""))
        if part.strip()
    ]

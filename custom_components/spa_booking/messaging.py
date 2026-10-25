"""Outbound messaging helpers for the SPA Booking integration.

WhatsApp goes to the WAHA add-on: directly through its HTTP API when the
gateway is configured in the settings (``waha_url``), or through the
``rest_command.spa_booking_whatsapp_send`` fallback declared in
``packages/spa_booking.yaml``. Telegram goes through
``telegram_bot.send_message``. Both helpers are best effort: a missing service
or a refused call is logged and reported back to the caller, never raised,
because a booking must not fail because a phone is asleep.
"""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.util import slugify

from .const import (
    ANSWER_AVAILABLE,
    ANSWER_CONFIRM,
    ANSWER_DECLINE,
    ANSWER_EMOJI_AVAILABLE,
    ANSWER_EMOJI_CONFIRM,
    ANSWER_EMOJI_DECLINE,
    ANSWER_MAX_WORDS,
    ANSWER_PHRASES_CONFIRM,
    ANSWER_WORDS_AVAILABLE,
    ANSWER_WORDS_CONFIRM,
    ANSWER_WORDS_DECLINE,
)

from .waha import WahaError

_LOGGER = logging.getLogger(__name__)

#: Fallback, used until the gateway is configured in the settings: a
#: rest_command declared in packages/spa_booking.yaml that calls the WAHA
#: add-on's POST /api/sendText with the message escaped through |to_json,
#: because a multi-line report cannot be interpolated raw into a JSON string.
WHATSAPP_SERVICE = "rest_command"
WHATSAPP_SERVICE_NAME = "spa_booking_whatsapp_send"

TELEGRAM_DOMAIN = "telegram_bot"
TELEGRAM_SERVICE_NAME = "send_message"

#: Telegram rejects messages longer than 4096 characters.
TELEGRAM_CHUNK = 3800
#: WhatsApp renders long messages poorly; keep each send readable.
WHATSAPP_CHUNK = 1200


def national_number(phone: str) -> str:
    """Return an Italian phone number without its country code or trunk zero.

    Only the country code is normalised away: dropping a fixed number of
    trailing digits would merge two different subscribers.
    """
    digits = "".join(char for char in (phone or "") if char.isdigit())
    for prefix in ("0039", "39"):
        if digits.startswith(prefix) and len(digits) > len(prefix):
            digits = digits[len(prefix) :]
            break
    return digits.lstrip("0")


def whatsapp_chat_id(phone: str, explicit: str = "") -> str:
    """Return the WhatsApp chat id of a phone number.

    An explicit ``whatsapp_chat_id`` always wins, because a masseuse may want a
    group or a number that does not match the one on her card.
    """
    if explicit.strip():
        return explicit.strip()
    national = national_number(phone)
    return f"39{national}@c.us" if national else ""


def to_whatsapp_chat_id(chat_id: str) -> str:
    """Return the chat id the Whatsapp add-on expects.

    A group (``…@g.us``) or an already-formatted id passes through; a bare
    phone number becomes ``39…@c.us``.
    """
    value = (chat_id or "").strip()
    if not value:
        return ""
    if "@" in value:
        return value
    digits = "".join(char for char in value if char.isdigit())
    if not digits:
        return ""
    # Italian default: add the country code when only the national part is given.
    if not digits.startswith("39"):
        digits = f"39{digits}"
    return f"{digits}@c.us"


def chunk_text(text: str, limit: int) -> list[str]:
    """Split a message into chunks that fit a channel's message limit.

    Lines are kept intact where possible so a report stays readable, and a
    chunk is only broken mid-line when a single line is longer than the limit.
    """
    if limit <= 0:
        return [text]
    chunks: list[str] = []
    current = ""
    for line in text.split("\n"):
        while len(line) > limit:
            if current:
                chunks.append(current)
                current = ""
            chunks.append(line[:limit])
            line = line[limit:]
        candidate = f"{current}\n{line}" if current else line
        if len(candidate) > limit:
            chunks.append(current)
            current = line
        else:
            current = candidate
    if current:
        chunks.append(current)
    return chunks


async def async_send_whatsapp(
    hass: HomeAssistant,
    chat_id: str,
    message: str,
    blocking: bool = True,
    waha: WahaClient | None = None,
) -> dict[str, Any]:
    """Send a WhatsApp message, preferring the WAHA add-on over rest_command.

    ``waha`` is the client of a configured gateway: when it is given, the call
    goes straight to the add-on. When it is None the send goes through
    ``rest_command.spa_booking_whatsapp_send`` as before, so an installation
    that never configured the gateway keeps working untouched.
    """
    target = to_whatsapp_chat_id(chat_id)
    if not target:
        return {"channel": "whatsapp", "chat_id": chat_id, "sent": False, "error": "nessun destinatario"}

    parts = chunk_text(message, WHATSAPP_CHUNK)
    sent = 0
    last_error = ""
    for part in parts:
        result = None
        if waha is not None:
            try:
                result = await waha.async_send_text(target, part)
            except WahaError as err:
                # A gateway that answers an error is a failure like any other:
                # the rest_command fallback is not retried, because the same
                # refusal would come back from it too.
                _LOGGER.warning("WhatsApp a %s fallito: %s", target, err)
                return {
                    "channel": "whatsapp",
                    "chat_id": chat_id,
                    "sent": False,
                    "parts": sent,
                    "error": str(err),
                }
            if not result.get("sent"):
                last_error = str(result.get("error") or "invio non riuscito")
                _LOGGER.warning(
                    "WhatsApp a %s rifiutato da WAHA: %s", target, last_error
                )
                break
        else:
            if not hass.services.has_service(WHATSAPP_SERVICE, WHATSAPP_SERVICE_NAME):
                return {
                    "channel": "whatsapp",
                    "chat_id": chat_id,
                    "sent": False,
                    "error": f"servizio {WHATSAPP_SERVICE}.{WHATSAPP_SERVICE_NAME} assente",
                }
            try:
                await hass.services.async_call(
                    WHATSAPP_SERVICE,
                    WHATSAPP_SERVICE_NAME,
                    {"chat_id": target, "message": part},
                    blocking=blocking,
                )
            except HomeAssistantError as err:
                last_error = str(err)
                _LOGGER.warning("WhatsApp a %s fallito: %s", target, err)
                break
        sent += 1

    return {
        "channel": "whatsapp",
        "chat_id": chat_id,
        "sent": sent == len(parts) and sent > 0,
        "parts": sent,
        "error": "" if sent == len(parts) else (last_error or "invio non riuscito"),
    }


async def async_send_telegram(
    hass: HomeAssistant,
    config_entry_id: str,
    chat_id: str,
    message: str,
    blocking: bool = True,
    inline_keyboard: list[list[dict[str, str]]] | None = None,
) -> dict[str, Any]:
    """Send a Telegram message through a configured bot.

    ``inline_keyboard`` is a list of rows of ``{"text": …, "callback_data": …}``
    buttons. Telegram is the only channel here that can show real buttons;
    WhatsApp has to make do with typed replies.
    """
    if not chat_id:
        return {
            "channel": "telegram",
            "chat_id": "",
            "sent": False,
            "error": "nessun chat id",
        }
    if not config_entry_id:
        return {
            "channel": "telegram",
            "chat_id": chat_id,
            "sent": False,
            "error": "nessun bot Telegram configurato",
        }
    if not hass.services.has_service(TELEGRAM_DOMAIN, TELEGRAM_SERVICE_NAME):
        return {
            "channel": "telegram",
            "chat_id": chat_id,
            "sent": False,
            "error": "integrazione telegram_bot non caricata",
        }

    parts = chunk_text(message, TELEGRAM_CHUNK)
    sent = 0
    last_error = ""
    for index, part in enumerate(parts):
        payload: dict[str, Any] = {
            "config_entry_id": config_entry_id,
            "chat_id": [str(chat_id)],
            "message": part,
        }
        # Buttons only make sense on the message that carries the offer text,
        # never on the continuation of a long report.
        if inline_keyboard and index == 0:
            payload["inline_keyboard"] = inline_keyboard
        try:
            await hass.services.async_call(
                TELEGRAM_DOMAIN,
                TELEGRAM_SERVICE_NAME,
                payload,
                blocking=blocking,
            )
            sent += 1
        except HomeAssistantError as err:
            last_error = str(err)
            _LOGGER.warning("Telegram a %s fallito: %s", chat_id, err)
            break

    return {
        "channel": "telegram",
        "chat_id": str(chat_id),
        "sent": sent == len(parts) and sent > 0,
        "parts": sent,
        "error": "" if sent == len(parts) else (last_error or "invio non riuscito"),
    }


def report_channels_for_operator(
    hass: HomeAssistant, operator: dict[str, Any], settings: dict[str, Any]
) -> list[tuple[str, str]]:
    """Return the (channel, chat_id) pairs enabled for one operator."""
    pairs: list[tuple[str, str]] = []
    if operator.get("notify_whatsapp", True):
        chat_id = whatsapp_chat_id(operator.get("phone", ""), operator.get("whatsapp_chat_id", ""))
        if chat_id:
            pairs.append(("whatsapp", chat_id))
    if operator.get("notify_telegram", True):
        chat_id = str(operator.get("telegram_chat_id") or "").strip()
        if chat_id:
            pairs.append(("telegram", chat_id))
    return pairs


# ------------------------------------------------------------------
# reading an answer back
# ------------------------------------------------------------------
def _words(text: str) -> list[str]:
    """Return a message reduced to lowercase words."""
    cleaned = "".join(
        char.lower() if char.isalnum() or char.isspace() else " "
        for char in (text or "")
    )
    return cleaned.split()


def parse_answer(text: str) -> str | None:
    """Return the answer a typed WhatsApp reply means, or None.

    A refusal or a confirmation word only counts when the whole reply is short
    enough to be an answer, otherwise ordinary chat ("Arrivo tra 5 minuti,
    no?") would close an offer by accident. A real confirmation word such as
    "confermo" is accepted whatever the length, because it cannot be part of
    an unrelated sentence.
    """
    if not text:
        return None
    lowered = text.lower()
    if any(phrase in lowered for phrase in ANSWER_PHRASES_CONFIRM):
        return ANSWER_CONFIRM

    tokens = _words(text)
    if len(tokens) > ANSWER_MAX_WORDS:
        return None
    if any(word in tokens for word in ANSWER_WORDS_DECLINE):
        return ANSWER_DECLINE
    if any(word in tokens for word in ANSWER_WORDS_AVAILABLE):
        return ANSWER_AVAILABLE
    if any(word in tokens for word in ANSWER_WORDS_CONFIRM):
        return ANSWER_CONFIRM
    return None


def parse_reaction(emoji: str) -> str | None:
    """Return the answer a WhatsApp reaction means, or None."""
    value = (emoji or "").strip()
    if not value:
        return None
    if value in ANSWER_EMOJI_CONFIRM:
        return ANSWER_CONFIRM
    if value in ANSWER_EMOJI_DECLINE:
        return ANSWER_DECLINE
    if value in ANSWER_EMOJI_AVAILABLE:
        return ANSWER_AVAILABLE
    return None


def find_operator_by_chat(
    operators: list[dict[str, Any]], channel: str, chat_id: str
) -> dict[str, Any] | None:
    """Return the operator owning an inbound chat id, or None.

    The WhatsApp id is compared as stored, as derived from the phone number,
    and as the WAHA integration's notify entity (``notify.waha_<name>``),
    because the add-on may report any spelling of the same sender.
    """
    wanted = (chat_id or "").strip()
    if not wanted:
        return None
    wanted_digits = "".join(char for char in wanted if char.isdigit())
    for operator in operators:
        if channel == "telegram":
            if str(operator.get("telegram_chat_id") or "").strip() == wanted:
                return operator
            continue
        # A WAHA inbound event carries no phone number: the sender is the
        # integration's notify entity (notify.waha_<name>), so match on that.
        waha_entity = f"notify.waha_{slugify(str(operator.get('name') or ''))}"
        if wanted == waha_entity and waha_entity != "notify.waha_":
            return operator
        explicit = str(operator.get("whatsapp_chat_id") or "").strip()
        derived = whatsapp_chat_id(operator.get("phone", ""), "")
        if wanted in {explicit, derived} and wanted:
            return operator
        # The add-on may report the same number as @s.whatsapp.net, @c.us or a
        # bare number, so the digits are compared as a fallback.
        phone_digits = "".join(
            char for char in (operator.get("phone") or "") if char.isdigit()
        )
        if phone_digits and wanted_digits.endswith(phone_digits):
            return operator
    return None

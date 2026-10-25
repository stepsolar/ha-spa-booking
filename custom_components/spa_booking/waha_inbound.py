"""Inbound WhatsApp events from the WAHA add-on, straight into this integration.

WAHA posts every message and every reaction to the webhook configured on its
session. This module owns that webhook:

* the call is authenticated with the SHA-512 HMAC WAHA signs the body with,
  before the body is parsed at all;
* only the two events an SPA answer arrives in are understood (a text message
  and an emoji reaction). A poll vote, a group notification, an ACK or a state
  change is acknowledged and ignored, so nothing else can reach a booking;
* the sender is matched to an operator here, so the answer carries her id;
* the result is fired as the internal ``spa_booking_answer_request`` event, the
  same one the Telegram buttons and the old YAML automations produced.

A replayed event is dropped: WAHA retries a webhook that did not answer 2xx,
and a retried "confermo" must not confirm a second offer.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import re
import time
from collections import deque
from typing import TYPE_CHECKING, Any

from aiohttp import web
from homeassistant.components import webhook
from homeassistant.core import HomeAssistant

from .const import DOMAIN, EVENT_ANSWER_REQUEST
from . import messaging

if TYPE_CHECKING:
    from .coordinator import SpaBookingCoordinator

_LOGGER = logging.getLogger(__name__)

#: A body larger than this is refused before being parsed: WAHA sends a small
#: JSON envelope, so a big body is either a wrong client or an attack.
MAX_BODY_BYTES = 256 * 1024

#: The two events this integration understands. Everything else is ignored.
SUPPORTED_EVENTS = ("message", "message.reaction")

#: Only these reactions answer an offer. A heart on a message is a thank you,
#: not a confirmation, and must not move a booking.
ANSWER_REACTIONS = frozenset({"✅", "✔️", "👍", "❌", "🚫", "👎", "🔄", "🔁", "♻️"})

#: A message longer than this is not an operator answer: it is a conversation
#: forward, a receipt or a pasted report.
MAX_TEXT_LENGTH = 8192

#: How long a delivered event id is remembered, and how many of them. The
#: window only has to cover WAHA's retries, which happen seconds apart.
DEDUP_WINDOW_SECONDS = 3600
DEDUP_MAX_IDS = 512

#: A chat that is not a direct conversation (group, broadcast, newsletter)
#: is never an operator answering a shift offer. WAHA may report the same
#: sender as @c.us, @s.whatsapp.net or @lid depending on version, so all
#: three direct-chat spellings are accepted; groups (@g.us) stay excluded.
_DIRECT_CHAT = re.compile(r"^[0-9]{7,20}@(c\.us|s\.whatsapp\.net|lid)$", re.IGNORECASE)


def verify_hmac_sha512(secret: str, raw_body: bytes, signature: str | None) -> bool:
    """Verify WAHA's SHA-512 signature over the unmodified request body."""
    if not secret or not signature:
        return False
    expected = hmac.new(secret.encode(), raw_body, hashlib.sha512).hexdigest()
    return hmac.compare_digest(expected, signature.strip().lower())


class WahaInbound:
    """The WAHA webhook of one installation: verify, filter, translate."""

    def __init__(
        self,
        hass: HomeAssistant,
        coordinator: SpaBookingCoordinator,
        *,
        webhook_id: str,
        secret: str,
        session: str,
    ) -> None:
        """Keep what the handler needs: the coordinator, the id and the secret."""
        self._hass = hass
        self._coordinator = coordinator
        self._webhook_id = webhook_id
        self._secret = secret
        self._session = session
        self._seen: deque[tuple[str, float]] = deque()
        self.accepted_count = 0

    # ------------------------------------------------------------ registration

    def async_register(self) -> None:
        """Claim the webhook path for this installation.

        Registering again with the same id replaces the previous handler, so
        pressing the card's button twice is harmless.
        """
        webhook.async_register(
            self._hass,
            DOMAIN,
            f"WAHA risposte ({self._webhook_id})",
            self._webhook_id,
            self._async_handle,
            local_only=True,
        )

    def async_unregister(self) -> None:
        """Free the webhook path, usually because the entry unloaded."""
        webhook.async_unregister(self._hass, self._webhook_id)

    # ----------------------------------------------------------------- handler

    async def _async_handle(
        self, hass: HomeAssistant, webhook_id: str, request: web.Request
    ) -> web.Response:
        """Authenticate one WAHA call, then translate it into an answer."""
        try:
            raw = await request.content.read(MAX_BODY_BYTES + 1)
        except Exception:  # noqa: BLE001 - aiohttp has many read failures
            return web.Response(status=400)
        if len(raw) > MAX_BODY_BYTES:
            return web.Response(status=413)
        if not verify_hmac_sha512(self._secret, raw, request.headers.get("X-Webhook-Hmac")):
            return web.Response(status=401)
        try:
            data = json.loads(raw)
        except ValueError:
            return web.Response(status=400)
        if not isinstance(data, dict):
            return web.Response(status=400)
        try:
            await self._handle_payload(data)
        except Exception:  # noqa: BLE001
            _LOGGER.exception("Evento WAHA non gestito")
        # 2xx no matter what: WAHA retries anything else, and a retry of an
        # answer already applied must not apply it twice.
        return web.Response(status=200)

    # ----------------------------------------------------------------- parsing

    async def _handle_payload(self, data: dict[str, Any]) -> None:
        """Fire an answer for one inbound message or reaction, if it is one."""
        event = data.get("event")
        if event not in SUPPORTED_EVENTS:
            return
        if data.get("session") != self._session:
            return
        payload = data.get("payload")
        if not isinstance(payload, dict):
            return
        # A message the SPA number itself sent (a confirmation we just gave
        # an operator) must never come back as her answer.
        if payload.get("fromMe") is not False:
            return
        chat_id = payload.get("from")
        if not isinstance(chat_id, str) or not _DIRECT_CHAT.fullmatch(chat_id):
            return
        chat_id = await self._async_resolve_sender(chat_id)
        if not self._claim_event(data, payload):
            return

        if event == "message":
            self._handle_text(payload, chat_id)
        else:
            self._handle_reaction(payload, chat_id)

    async def _async_resolve_sender(self, chat_id: str) -> str:
        """Map a LID sender to her phone chat id through the WAHA server.

        Anything that is not a LID, or a LID the server cannot map, passes
        through untouched, so answering never depends on this one lookup.
        """
        if not chat_id.lower().endswith("@lid"):
            return chat_id
        try:
            client = self._coordinator.waha
            resolved = await client.async_resolve_lid(chat_id) if client else None
        except Exception:  # noqa: BLE001 - inbound must survive a WAHA hiccup
            return chat_id
        return resolved or chat_id

    def _handle_text(self, payload: dict[str, Any], chat_id: str) -> None:
        """Turn an inbound text message into an answer request."""
        if payload.get("hasMedia"):
            # A photo or a voice note is not an answer: the operator has to
            # type it, like the answer words she already knows.
            return
        text = payload.get("body")
        if not isinstance(text, str) or not text.strip():
            return
        if len(text) > MAX_TEXT_LENGTH:
            return
        self.accepted_count += 1
        self._fire_answer(text=text, chat_id=chat_id, source="whatsapp")

    def _handle_reaction(self, payload: dict[str, Any], chat_id: str) -> None:
        """Turn an inbound emoji reaction into an answer request."""
        reaction = payload.get("reaction")
        emoji = reaction.get("text") if isinstance(reaction, dict) else None
        if not isinstance(emoji, str) or emoji.strip() not in ANSWER_REACTIONS:
            return
        self.accepted_count += 1
        self._fire_answer(emoji=emoji.strip(), chat_id=chat_id, source="whatsapp")

    def _fire_answer(
        self,
        *,
        chat_id: str,
        source: str,
        text: str = "",
        emoji: str = "",
    ) -> None:
        """Publish the answer on the event the coordinator already listens to.

        The operator is resolved here rather than in the coordinator, so the
        answer carries her id directly: the sender is the number WAHA reports,
        which is the one fact that cannot be spelled differently.
        """
        operator = messaging.find_operator_by_chat(
            self._coordinator.operators, "whatsapp", chat_id
        )
        event: dict[str, Any] = {
            "text": text,
            "emoji": emoji,
            "chat_id": chat_id,
            "channel": "whatsapp",
            "source": source,
        }
        if operator is not None:
            event["operator_id"] = operator["id"]
        self._hass.bus.async_fire(EVENT_ANSWER_REQUEST, event)

    def _claim_event(self, data: dict[str, Any], payload: dict[str, Any]) -> bool:
        """Drop an event already delivered, so a WAHA retry is a no-op."""
        raw_id = data.get("id") or payload.get("id")
        if not isinstance(raw_id, str) or not raw_id:
            # No id means no way to recognise a replay: let it through, because
            # an operator's confirmation matters more than a rare duplicate.
            return True
        now = time.time()
        while self._seen and now - self._seen[0][1] > DEDUP_WINDOW_SECONDS:
            self._seen.popleft()
        if any(event_id == raw_id for event_id, _ in self._seen):
            return False
        self._seen.append((raw_id, now))
        while len(self._seen) > DEDUP_MAX_IDS:
            self._seen.popleft()
        return True

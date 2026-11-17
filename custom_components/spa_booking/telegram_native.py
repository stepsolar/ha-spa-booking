"""Telegram built into Spa Booking (2.9.0).

The bot is talked to directly through the Telegram Bot API, with the token
saved in the card (Configurazione › Notifiche › Collegamenti): no
``telegram_bot`` integration and no automation in Home Assistant.

* Sending: ``sendMessage``, with the inline buttons of the offers.
* Receiving: long polling of ``getUpdates`` in a background task, so no
  public address is needed. A text message or a button press is turned into
  the same ``spa_booking_answer_request`` event the WhatsApp answers use.
* ``/start`` (or any message) answers with the chat's id, so each operator
  can read hers and the desk copies it into her card; the last people who
  wrote to the bot are listed in the card too.
"""

from __future__ import annotations

import asyncio
from collections import deque
from collections.abc import Callable
import contextlib
import logging
from typing import Any

import aiohttp

from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

_LOGGER = logging.getLogger(__name__)

API = "https://api.telegram.org/bot{token}/{method}"
#: Seconds Telegram keeps a getUpdates call open when nothing arrives.
POLL_TIMEOUT = 25


#: Failed polls in a row before the card shows the bot as not working
#: (3.15.1): one slow answer or a network hiccup is retried, not an error.
FAILURES_BEFORE_ERROR = 3


class TelegramError(Exception):
    """Telegram answered an error, or could not be reached."""


def explain(error: str) -> str:
    """What a Telegram error means for the desk (3.15.1)."""
    text = str(error or "")
    if "Conflict" in text or "409" in text:
        return ("Un altro programma sta leggendo lo stesso bot: di solito l'integrazione Telegram di "
                "Home Assistant (Impostazioni › Dispositivi e servizi) o una seconda copia di Spa Booking "
                "(es. Spa Booking Web). Toglila, oppure usa un bot diverso.")
    if "Unauthorized" in text or "401" in text or "Not Found" in text or "404" in text:
        return "Token non valido o bot eliminato: copia di nuovo il token da @BotFather."
    if "Too Many Requests" in text or "429" in text:
        return "Telegram chiede di rallentare: riprova tra qualche minuto."
    return text


class TelegramBot:
    """One bot: send, and poll for what the operators write or press."""

    def __init__(
        self,
        hass: HomeAssistant,
        token: str,
        on_update: Callable[[dict[str, Any]], Any],
    ) -> None:
        self.hass = hass
        self.token = token.strip()
        self._on_update = on_update
        self._task: asyncio.Task | None = None
        self._offset = 0
        self.me: dict[str, Any] = {}
        self.error = ""
        self.failures = 0
        self.running = False
        #: The last chats that wrote to the bot: id, name, username.
        self.recent: deque[dict[str, Any]] = deque(maxlen=20)

    # ------------------------------------------------------------- the API
    async def _api(self, method: str, payload: dict[str, Any] | None = None, wait: int = 20) -> Any:
        session = async_get_clientsession(self.hass)
        try:
            async with session.post(
                API.format(token=self.token, method=method),
                json=payload or {},
                timeout=aiohttp.ClientTimeout(total=wait + 10),
            ) as response:
                body = await response.json(content_type=None)
        except (aiohttp.ClientError, asyncio.TimeoutError) as err:
            raise TelegramError(f"Telegram non raggiungibile: {err}") from err
        if not isinstance(body, dict) or not body.get("ok"):
            description = (body or {}).get("description") if isinstance(body, dict) else ""
            raise TelegramError(str(description or "risposta non valida"))
        return body.get("result")

    async def async_get_me(self) -> dict[str, Any]:
        self.me = await self._api("getMe") or {}
        return self.me

    async def async_send(
        self,
        chat_id: str,
        text: str,
        inline_keyboard: list[list[dict[str, str]]] | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {"chat_id": str(chat_id), "text": text, "disable_web_page_preview": True}
        if inline_keyboard:
            payload["reply_markup"] = {"inline_keyboard": inline_keyboard}
        return await self._api("sendMessage", payload)

    # ----------------------------------------------------------- receiving
    async def async_start(self) -> None:
        if self._task is not None:
            return
        try:
            await self.async_get_me()
            # A webhook set by another program would stop getUpdates.
            await self._api("deleteWebhook", {"drop_pending_updates": False})
            self.error = ""
        except TelegramError as err:
            self.error = str(err)
            _LOGGER.warning("Bot Telegram non avviato: %s", err)
        self.running = True
        self._task = self.hass.async_create_background_task(self._poll(), "spa_booking_telegram")

    async def async_stop(self) -> None:
        self.running = False
        task, self._task = self._task, None
        if task is not None:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await task

    async def _poll(self) -> None:
        backoff = 5
        while self.running:
            try:
                updates = await self._api(
                    "getUpdates",
                    {"offset": self._offset, "timeout": POLL_TIMEOUT,
                     "allowed_updates": ["message", "callback_query"]},
                    wait=POLL_TIMEOUT,
                ) or []
                self.error = ""
                self.failures = 0
                backoff = 5
            except asyncio.CancelledError:
                raise
            except TelegramError as err:
                # 409: another program reads the same bot (Home Assistant's
                # Telegram integration): say so, and keep trying. A network
                # hiccup only counts after a few in a row (3.15.1).
                self.failures += 1
                text = str(err)
                if self.failures >= FAILURES_BEFORE_ERROR or "Conflict" in text or "Unauthorized" in text:
                    self.error = text
                _LOGGER.debug("Telegram getUpdates: %s", err)
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 120)
                continue
            for update in updates:
                self._offset = max(self._offset, int(update.get("update_id", 0)) + 1)
                try:
                    await self._handle(update)
                except Exception:  # noqa: BLE001 - one bad update must not stop the bot
                    _LOGGER.exception("Aggiornamento Telegram non gestito")

    async def _handle(self, update: dict[str, Any]) -> None:
        callback = update.get("callback_query")
        if callback:
            message = callback.get("message") or {}
            chat = message.get("chat") or {}
            self._remember(chat, callback.get("from") or {})
            with contextlib.suppress(TelegramError):
                await self._api("answerCallbackQuery", {"callback_query_id": callback.get("id"), "text": "Ricevuto ✅"})
            # «spa:<appointment id>:<answer>», as the offer buttons are built.
            parts = str(callback.get("data") or "").split(":")
            if len(parts) == 3 and parts[0] == "spa":
                await self._dispatch({
                    "channel": "telegram", "chat_id": str(chat.get("id") or ""),
                    "appointment_id": parts[1], "answer": parts[2], "source": "telegram",
                })
            return
        message = update.get("message") or {}
        chat = message.get("chat") or {}
        text = str(message.get("text") or "").strip()
        if not chat or not text:
            return
        self._remember(chat, message.get("from") or {})
        if text.split()[0].split("@")[0].lower() in ("/start", "/id"):
            with contextlib.suppress(TelegramError):
                await self.async_send(
                    str(chat.get("id")),
                    f"Ciao! Il codice di questa chat è {chat.get('id')}.\n"
                    "Comunicalo alla reception: lo inserisce nella tua scheda operatore "
                    "e da lì ricevi qui gli appuntamenti.",
                )
            return
        await self._dispatch({
            "channel": "telegram", "chat_id": str(chat.get("id") or ""),
            "text": text, "source": "telegram",
        })

    async def _dispatch(self, data: dict[str, Any]) -> None:
        result = self._on_update(data)
        if asyncio.iscoroutine(result):
            await result

    def _remember(self, chat: dict[str, Any], sender: dict[str, Any]) -> None:
        chat_id = str(chat.get("id") or "")
        if not chat_id:
            return
        name = " ".join(x for x in (chat.get("first_name") or sender.get("first_name"),
                                    chat.get("last_name") or sender.get("last_name")) if x) \
            or str(chat.get("title") or "")
        entry = {"chat_id": chat_id, "name": name, "username": str(chat.get("username") or sender.get("username") or "")}
        for old in list(self.recent):
            if old["chat_id"] == chat_id:
                self.recent.remove(old)
        self.recent.appendleft(entry)

    def status(self) -> dict[str, Any]:
        return {
            "configured": True,
            "ok": bool(self.me) and not self.error,
            "username": str(self.me.get("username") or ""),
            "name": str(self.me.get("first_name") or ""),
            "error": explain(self.error),
            "recent": list(self.recent),
        }

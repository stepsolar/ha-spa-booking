"""2.9.0: Telegram built into Spa Booking."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

from custom_components.spa_booking import messaging
from custom_components.spa_booking.telegram_native import TelegramBot

from .conftest import run


def _bot():
    events: list[dict[str, Any]] = []
    bot = TelegramBot(MagicMock(), " 123:abc ", events.append)
    calls: list[tuple[str, dict]] = []

    async def api(method, payload=None, wait=20):
        calls.append((method, payload or {}))
        return {"message_id": 1}

    bot._api = api
    return bot, events, calls


def test_button_press_and_text_become_answers() -> None:
    bot, events, calls = _bot()
    assert bot.token == "123:abc"
    run(bot._handle({"update_id": 5, "callback_query": {
        "id": "q1", "data": "spa:apt_9:confirm", "from": {"first_name": "Giulia"},
        "message": {"chat": {"id": 777, "first_name": "Giulia"}}}}))
    assert events[-1] == {"channel": "telegram", "chat_id": "777", "appointment_id": "apt_9",
                          "answer": "confirm", "source": "telegram"}
    assert calls[0][0] == "answerCallbackQuery"
    run(bot._handle({"update_id": 6, "message": {"chat": {"id": 777}, "text": "SI"}}))
    assert events[-1]["text"] == "SI" and events[-1]["channel"] == "telegram"
    assert bot.status()["recent"][0]["chat_id"] == "777"


def test_start_answers_with_the_chat_id() -> None:
    bot, events, calls = _bot()
    run(bot._handle({"update_id": 7, "message": {"chat": {"id": 4242, "first_name": "Maria"}, "text": "/start"}}))
    assert not events
    assert calls[-1][0] == "sendMessage" and "4242" in calls[-1][1]["text"]


def test_messaging_uses_the_built_in_bot() -> None:
    bot, _events, calls = _bot()
    messaging.set_telegram_bot(bot)
    try:
        result = run(messaging.async_send_telegram(MagicMock(), "", "777", "Ciao",
                                                   inline_keyboard=[[{"text": "Ok", "callback_data": "spa:x:confirm"}]]))
    finally:
        messaging.set_telegram_bot(None)
    assert result["sent"]
    method, payload = calls[-1]
    assert method == "sendMessage" and payload["chat_id"] == "777"
    assert payload["reply_markup"]["inline_keyboard"][0][0]["callback_data"] == "spa:x:confirm"

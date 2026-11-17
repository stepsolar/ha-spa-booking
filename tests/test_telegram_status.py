"""3.15.1: the Telegram bot's state — hiccups are retried, errors explained."""

from __future__ import annotations

import asyncio

from custom_components.spa_booking import telegram_native
from custom_components.spa_booking.telegram_native import TelegramBot, TelegramError

from .conftest import run


class Hass:
    pass


def test_hiccups_are_not_an_error(monkeypatch) -> None:
    bot = TelegramBot(Hass(), "123:abc", lambda data: None)
    bot.me = {"username": "spa_bot"}
    answers = [TelegramError("Telegram non raggiungibile: timeout")] * 2 + [[]]
    calls = []

    async def api(method, payload=None, wait=20):
        calls.append(method)
        answer = answers.pop(0)
        if not answers:
            bot.running = False
        if isinstance(answer, Exception):
            raise answer
        return answer

    async def no_sleep(seconds):
        return None

    monkeypatch.setattr(bot, "_api", api)
    monkeypatch.setattr(asyncio, "sleep", no_sleep)
    bot.running = True
    run(bot._poll())
    assert calls == ["getUpdates"] * 3
    assert bot.error == "" and bot.failures == 0 and bot.status()["ok"]


def test_conflict_is_explained_at_once(monkeypatch) -> None:
    bot = TelegramBot(Hass(), "123:abc", lambda data: None)
    bot.me = {"username": "spa_bot"}

    async def api(method, payload=None, wait=20):
        bot.running = False
        raise TelegramError("Conflict: terminated by other getUpdates request")

    async def no_sleep(seconds):
        return None

    monkeypatch.setattr(bot, "_api", api)
    monkeypatch.setattr(asyncio, "sleep", no_sleep)
    bot.running = True
    run(bot._poll())
    status = bot.status()
    assert not status["ok"] and "Un altro programma" in status["error"]
    assert "Token non valido" in telegram_native.explain("Unauthorized")

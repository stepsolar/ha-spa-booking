"""Shared fixtures for the Spa Booking tests.

The coordinator is built without starting Home Assistant: its business rules
are plain Python over the stored dataset, so the tests set up the dataset,
call the coordinator and look at the result. Outbound messages are captured
instead of sent.
"""

from __future__ import annotations

import asyncio
from collections import deque
from collections.abc import Callable
from datetime import datetime
from typing import Any
from unittest.mock import MagicMock

import pytest

from custom_components.spa_booking import coordinator as coordinator_module
from custom_components.spa_booking import access, messaging
from custom_components.spa_booking.coordinator import SpaBookingCoordinator
from custom_components.spa_booking.normalize import _normalise, default_data

TZ_NAME = "Europe/Rome"


class _FakeStore:
    """Keeps the last saved dataset in memory."""

    def __init__(self) -> None:
        self.saved: dict[str, Any] | None = None
        self.saves = 0

    async def async_load(self) -> dict[str, Any] | None:
        return self.saved

    async def async_save(self, data: dict[str, Any]) -> None:
        self.saved = data
        self.saves += 1

    def async_delay_save(self, func: Any, delay: float = 0) -> None:
        self.saved = func()
        self.saves += 1


async def _executor(func: Callable[..., Any], *args: Any) -> Any:
    return func(*args)


def build_coordinator(data: dict[str, Any] | None = None) -> SpaBookingCoordinator:
    """Return a coordinator over ``data`` (default: the seed with 2 operators)."""
    coordinator = object.__new__(SpaBookingCoordinator)
    hass = MagicMock()
    hass.async_add_executor_job = _executor
    hass.services.has_service.return_value = False
    coordinator.hass = hass
    coordinator.entry = MagicMock(entry_id="test_entry", data={}, title="Spa")
    coordinator._store = _FakeStore()
    coordinator._lock = asyncio.Lock()
    coordinator._send_lock = asyncio.Lock()
    coordinator._external_messages = deque(maxlen=20)
    coordinator._chats_store = _FakeStore()
    coordinator._chats = {}
    coordinator._waha_inbound = None
    coordinator._card_version = ""
    coordinator.scheduler = None
    coordinator.wa_bridge = None
    coordinator.pin_sessions = access.PinSessions()
    coordinator._current_user_id = None
    coordinator.data = None
    coordinator.async_set_updated_data = lambda new: setattr(coordinator, "data", new)
    coordinator.async_update_listeners = lambda: None
    coordinator._data = _normalise(data or default_data(["Maria", "Giulia"]))
    coordinator.data = coordinator._data
    return coordinator


@pytest.fixture
def coordinator() -> SpaBookingCoordinator:
    """A coordinator over the seed dataset, operators Maria and Giulia."""
    return build_coordinator()


@pytest.fixture
def sent(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    """Capture every WhatsApp/Telegram message instead of sending it."""
    outbox: list[dict[str, Any]] = []

    async def fake_whatsapp(hass, chat_id, message, blocking=True, waha=None):
        outbox.append({"channel": "whatsapp", "chat_id": chat_id, "message": message})
        return {"channel": "whatsapp", "chat_id": chat_id, "sent": True, "parts": 1, "error": ""}

    async def fake_telegram(hass, entry_id, chat_id, message, blocking=True, inline_keyboard=None):
        outbox.append({"channel": "telegram", "chat_id": chat_id, "message": message})
        return {"channel": "telegram", "chat_id": chat_id, "sent": True, "parts": 1, "error": ""}

    monkeypatch.setattr(messaging, "async_send_whatsapp", fake_whatsapp)
    monkeypatch.setattr(messaging, "async_send_telegram", fake_telegram)
    return outbox


@pytest.fixture
def freeze(monkeypatch: pytest.MonkeyPatch) -> Callable[[str], datetime]:
    """Freeze the coordinator's clock at a local "YYYY-MM-DD HH:MM" time."""
    from zoneinfo import ZoneInfo

    dt_util = coordinator_module.dt_util

    def _freeze(value: str) -> datetime:
        local = datetime.fromisoformat(value).replace(tzinfo=ZoneInfo(TZ_NAME))
        monkeypatch.setattr(dt_util, "now", lambda time_zone=None: local)
        monkeypatch.setattr(dt_util, "utcnow", lambda: local.astimezone(ZoneInfo("UTC")))
        monkeypatch.setattr(dt_util, "DEFAULT_TIME_ZONE", ZoneInfo(TZ_NAME))
        return local

    return _freeze


def run(coro: Any) -> Any:
    """Run a coroutine to completion (the tests stay synchronous)."""
    return asyncio.run(coro)

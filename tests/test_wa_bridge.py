"""The built-in WhatsApp connection, run against the real program in bin/."""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from custom_components.spa_booking import wa_bridge
from custom_components.spa_booking.waha import WahaError

from .conftest import build_coordinator, run

BINARY = wa_bridge.binary_path()
needs_binary = pytest.mark.skipif(BINARY is None, reason="no bridge program for this machine")


class _Inbound:
    def __init__(self) -> None:
        self.events: list[dict[str, Any]] = []

    async def async_handle_event(self, data: dict[str, Any]) -> None:
        self.events.append(data)


def _hass(tmp_path: Path) -> Any:
    loop = asyncio.get_running_loop()

    async def executor(func, *args):
        return func(*args)

    return SimpleNamespace(
        config=SimpleNamespace(path=lambda *parts: str(tmp_path.joinpath(*parts))),
        async_add_executor_job=executor,
        async_create_background_task=lambda coro, name: loop.create_task(coro),
    )


async def _wait_for(predicate, limit: float = 15) -> None:
    deadline = asyncio.get_running_loop().time() + limit
    while not predicate():
        if asyncio.get_running_loop().time() > deadline:
            raise AssertionError("timeout")
        await asyncio.sleep(0.05)


@needs_binary
def test_bridge_lifecycle(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(wa_bridge, "RESTART_DELAYS", (0.2,))

    async def scenario() -> None:
        inbound = _Inbound()
        bridge = wa_bridge.WaBridge(_hass(tmp_path), inbound)
        changes: list[str] = []
        bridge.listeners.append(lambda: changes.append(bridge.state))
        await bridge.async_start()
        await _wait_for(lambda: bridge.state == "not_linked")
        assert bridge.running

        status = await bridge.async_status()
        assert status["state"] == "not_linked" and status["label"] == "Non collegato"
        assert status["engine"] == "whatsmeow"

        # Not linked: a send is refused, never raised.
        result = await bridge.async_send_text("393331234567@c.us", "ciao")
        assert result == {"sent": False, "message_id": None, "error": "WhatsApp non collegato"}
        assert await bridge.async_resolve_lid("123@lid") is None
        with pytest.raises(WahaError):
            await bridge.async_get_server()

        # The session folder is private.
        folder = tmp_path / ".storage" / "spa_booking_whatsapp"
        assert (folder / "whatsapp.db").exists()
        assert oct(os.stat(folder).st_mode & 0o777) == "0o700"

        # Messages and reactions go to the same handler as the WAHA webhook.
        line = {"event": "message", "session": "spa", "id": "X1",
                "payload": {"from": "393331234567@c.us", "fromMe": False, "body": "confermo"}}
        await bridge._async_handle_line(json.dumps(line).encode())
        assert inbound.events == [line]

        # Killed from outside: started again by itself.
        first = bridge._proc
        first.kill()
        await _wait_for(lambda: bridge._proc is not None and bridge._proc is not first and bridge.running)
        await _wait_for(lambda: bridge.state == "not_linked")
        assert (await bridge.async_status())["state"] == "not_linked"

        proc = bridge._proc
        await bridge.async_stop()
        assert proc.returncode is not None
        assert bridge.state == "stopped" and not bridge.running
        with pytest.raises(WahaError):
            await bridge.async_send_text("393331234567@c.us", "ciao")
        assert "starting" in changes

    asyncio.run(scenario())


def test_missing_program_is_reported(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(wa_bridge, "binary_path", lambda: None)

    async def scenario() -> None:
        bridge = wa_bridge.WaBridge(_hass(tmp_path), _Inbound())
        await bridge.async_start()
        await _wait_for(lambda: bridge.state == "missing")
        status = await bridge.async_status()
        assert status["label"].startswith("Programma non disponibile")
        await bridge.async_stop()

    asyncio.run(scenario())


def test_engine_choice_picks_the_gateway(monkeypatch: pytest.MonkeyPatch) -> None:
    coordinator = build_coordinator()
    settings = coordinator._data["settings"]
    assert coordinator.whatsapp_engine == "integrated"  # 2.9.0: no more WAHA add-on
    assert coordinator.waha is None  # not started yet
    assert "waha_url" not in settings

    started: list[str] = []

    class FakeBridge:
        def __init__(self, hass, inbound) -> None:
            self.listeners: list[Any] = []

        async def async_start(self) -> None:
            started.append("start")

        async def async_stop(self) -> None:
            started.append("stop")

    monkeypatch.setattr("custom_components.spa_booking.coordinator.WaBridge", FakeBridge)
    run(coordinator.async_update_settings(whatsapp_engine="integrated"))
    assert isinstance(coordinator.waha, FakeBridge)  # never WAHA while integrated
    run(coordinator.async_stop_whatsapp())
    assert started == ["start", "stop"]
    assert coordinator.wa_bridge is None and coordinator.waha is None

"""3.20.0: the AI assistant — its key, its permissions, its tools and MCP."""

from __future__ import annotations

import pytest

from custom_components.spa_booking import ai
from custom_components.spa_booking.const import KEY_SETTINGS
from custom_components.spa_booking.exceptions import ValidationError
from custom_components.spa_booking.normalize import default_data

from .conftest import build_coordinator, run

SPA = "trt_ingresso_90"
MASSAGE = "trt_massaggio_relax_90"


@pytest.fixture
def bot(freeze, sent):
    freeze("2026-11-10 08:00")
    coordinator = build_coordinator(default_data(["Maria"]))
    coordinator._data[KEY_SETTINGS].update(ai_enabled=True, ai_permissions=["read", "clients", "requests"])
    return coordinator


def test_key_is_kept_as_hash(bot) -> None:
    key = run(bot.async_ai_key())["key"]
    settings = bot._data[KEY_SETTINGS]
    assert key.startswith("sbai_") and key not in str(settings)
    assert ai.key_ok(settings, key) and not ai.key_ok(settings, key + "x") and not ai.key_ok(settings, "")
    run(bot.async_ai_key(revoke=True))
    assert not ai.key_ok(bot._data[KEY_SETTINGS], key)


def test_read_tools(bot) -> None:
    info = run(ai.run_tool(bot, "info_spa", {}))
    assert info["oggi"] == "2026-11-10"
    listino = run(ai.run_tool(bot, "listino", {}))
    assert any(t["id"] == SPA and t["durata_min"] for t in listino["trattamenti"])
    free = run(ai.run_tool(bot, "disponibilita", {"data": "2026-11-12", "trattamento_id": MASSAGE}))
    assert free["orari_liberi"]
    # One masseuse: never two people together.
    two = run(ai.run_tool(bot, "disponibilita", {"data": "2026-11-12", "trattamento_id": MASSAGE, "persone": 2}))
    assert two["orari_liberi"] == []


def test_permissions(bot) -> None:
    names = {t["name"] for t in ai.tools_for(bot._data[KEY_SETTINGS])}
    assert "crea_richiesta" in names and "crea_prenotazione" not in names and "annulla_prenotazione" not in names
    with pytest.raises(ValidationError, match="Permesso non concesso"):
        run(ai.run_tool(bot, "crea_prenotazione", {}))


def test_request_and_booking(bot) -> None:
    guest = {"nome": "Anna", "cognome": "Rossi", "telefono": "347 1234567"}
    request = run(ai.run_tool(bot, "crea_richiesta", {**guest, "data": "2026-11-12",
                                                      "voci": [{"trattamento_id": SPA, "ora": "15:00"}]}))
    assert request["codice"]
    bot._data[KEY_SETTINGS]["ai_permissions"] = ["read", "clients", "bookings", "manage"]
    booked = run(ai.run_tool(bot, "crea_prenotazione", {"cliente": guest, "voci": [
        {"trattamento_id": SPA, "data": "2026-11-12", "ora": "15:00", "persona": 0},
        {"trattamento_id": SPA, "data": "2026-11-12", "ora": "15:00", "persona": 1}]}))
    assert len(booked["prenotati"]) == 2
    appointment = next(a for a in bot.appointments if a["id"] == booked["prenotati"][0]["id"])
    assert appointment["created_by_name"] == "Assistente IA"
    found = run(ai.run_tool(bot, "cerca_cliente", {"testo": "3471234567"}))
    assert found["clienti"][0]["prossimi_appuntamenti"]
    moved = run(ai.run_tool(bot, "sposta_prenotazione", {"appuntamento_id": appointment["id"], "data": "2026-11-13", "ora": "10:00"}))
    assert moved["appuntamento"]["data"] == "2026-11-13" and moved["appuntamento"]["ora"] == "10:00"
    run(ai.run_tool(bot, "annulla_prenotazione", {"appuntamento_id": appointment["id"]}))
    assert next(a for a in bot.appointments if a["id"] == appointment["id"])["status"] == "cancelled"
    assert ai.AI_LOG[0]["tool"] == "annulla_prenotazione"


def test_mcp(bot) -> None:
    view = ai.SpaBookingAiMcpView()
    init = run(view._one(bot, {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}))
    assert init["result"]["serverInfo"]["name"] == "spa-booking" and "tools" in init["result"]["capabilities"]
    assert run(view._one(bot, {"jsonrpc": "2.0", "method": "notifications/initialized"})) is None
    tools = run(view._one(bot, {"jsonrpc": "2.0", "id": 2, "method": "tools/list"}))["result"]["tools"]
    assert {"info_spa", "disponibilita"} <= {t["name"] for t in tools}
    call = run(view._one(bot, {"jsonrpc": "2.0", "id": 3, "method": "tools/call",
                               "params": {"name": "disponibilita", "arguments": {"data": "2026-11-12", "trattamento_id": SPA}}}))
    assert call["result"]["isError"] is False and call["result"]["structuredContent"]["orari_liberi"]
    bad = run(view._one(bot, {"jsonrpc": "2.0", "id": 4, "method": "tools/call", "params": {"name": "crea_prenotazione"}}))
    assert bad["result"]["isError"] is True
    assert run(view._one(bot, {"jsonrpc": "2.0", "id": 5, "method": "nope"}))["error"]["code"] == -32601

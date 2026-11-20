"""3.20.0: the AI views over HTTP: switch, key, MCP and JSON (needs the real aiohttp)."""

import json

import pytest

test_utils = pytest.importorskip("aiohttp.test_utils")

from homeassistant.components.http import KEY_HASS
from custom_components.spa_booking import ai
from custom_components.spa_booking.const import DOMAIN, KEY_SETTINGS
from custom_components.spa_booking.normalize import default_data
from .conftest import build_coordinator, run

def _req(c, method, path, key, body=None):
    app = {KEY_HASS: type("H", (), {"data": {DOMAIN: c}})()}
    headers = {"Authorization": f"Bearer {key}"} if key else {}
    r = test_utils.make_mocked_request(method, path, headers=headers, app=app)
    async def text(): return json.dumps(body) if body is not None else ""
    r.text = text
    return r

def test_http(freeze, sent):
    freeze("2026-11-10 08:00")
    c = build_coordinator(default_data(["Maria"]))
    view = ai.SpaBookingAiMcpView()
    assert run(view.post(_req(c, "POST", ai.MCP_URL, "x", {}))).status == 404
    c._data[KEY_SETTINGS]["ai_enabled"] = True
    key = run(c.async_ai_key())["key"]
    assert run(view.post(_req(c, "POST", ai.MCP_URL, "bad", {}))).status == 401
    resp = run(view.post(_req(c, "POST", ai.MCP_URL, key, {"jsonrpc": "2.0", "id": 1, "method": "tools/list"})))
    assert resp.status == 200 and "listino" in resp.text
    resp = run(ai.SpaBookingAiCallView().post(_req(c, "POST", ai.CALL_URL, key, {"tool": "info_spa", "arguments": {}})))
    assert resp.status == 200 and '"ok": true' in resp.text
    resp = run(view.post(_req(c, "POST", ai.MCP_URL, key, {"jsonrpc": "2.0", "method": "notifications/initialized"})))
    assert resp.status == 202

"""3.5.0: photos and files in the WhatsApp chats."""

from __future__ import annotations

import base64

import pytest

from custom_components.spa_booking.exceptions import ValidationError

from .conftest import run


class FakeClient:
    def __init__(self) -> None:
        self.sent = []

    async def async_send_file(self, chat_id, data, *, mimetype, filename, caption=""):
        self.sent.append((chat_id, len(data), mimetype, filename, caption))
        return {"sent": True}

    async def async_fetch_media(self, media):
        return (b"\x89PNG fake", "image/png") if media.get("id") == "W1" else None


def test_send_and_receive_files(coordinator, monkeypatch, tmp_path, freeze) -> None:
    freeze("2026-11-15 10:00")
    monkeypatch.setattr(coordinator, "_media_dir", lambda: str(tmp_path))
    with pytest.raises(ValidationError, match="WhatsApp integrato o WAHA"):
        run(coordinator.async_send_chat_file("393471234567@c.us", "aGVsbG8=", "application/pdf", "listino.pdf"))
    client = FakeClient()
    monkeypatch.setattr(type(coordinator), "waha", property(lambda self: client))
    result = run(coordinator.async_send_chat_file("+39 347 1234567", base64.b64encode(b"%PDF-1").decode(),
                                                  "application/pdf", "listino.pdf", "Ecco il listino"))
    assert result["sent"] and client.sent[0][0] == "393471234567@c.us"
    run(coordinator.async_record_incoming_media("393471234567@c.us", {"body": "", "media": {"id": "W1", "mimetype": "image/png"}}))
    run(coordinator.async_record_incoming_media("393471234567@c.us", {"body": "vocale", "media": {"id": "X", "error": "file troppo grande"}}))
    chat = next(c for c in coordinator.whatsapp_chats() if c["chat_id"] == "393471234567@c.us")
    out, photo, missing = chat["messages"]
    assert out["dir"] == "out" and out["media"]["filename"] == "listino.pdf" and out["text"] == "Ecco il listino"
    assert photo["dir"] == "in" and photo["media"]["mimetype"] == "image/png"
    assert missing["media"].get("missing") and missing["text"] == "vocale"
    got = run(coordinator.async_chat_media(photo["media"]["id"]))
    assert base64.b64decode(got["data"]) == b"\x89PNG fake"
    assert coordinator.external_messages[0]["text"] == "vocale"
    run(coordinator.async_mark_chat_read("393471234567@s.whatsapp.net"))
    assert next(c for c in coordinator.whatsapp_chats() if c["chat_id"] == "393471234567@c.us")["read_at"]

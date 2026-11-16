"""3.11.0: messages written on the hotel's phone appear in the chat."""

from __future__ import annotations

from custom_components.spa_booking.waha_inbound import WahaInbound

from .conftest import run


class Bus:
    def __init__(self) -> None:
        self.fired = []

    def async_fire(self, event, data) -> None:
        self.fired.append((event, data))


class Hass:
    def __init__(self) -> None:
        self.bus = Bus()

    def async_create_task(self, coro):
        return run(coro)


def _event(event, payload, eid):
    return {"event": event, "session": "default", "id": eid, "payload": payload}


def test_phone_reply_in_chat(coordinator, freeze) -> None:
    freeze("2026-11-16 10:00")
    hass = Hass()
    inbound = WahaInbound(hass, coordinator, webhook_id="w", secret="s", session="default")
    chat = "393471234567@c.us"
    coordinator.record_incoming_whatsapp(chat, "Posso venire domani alle 15?")
    # The reply typed on the phone (built-in bridge: «to» is the guest).
    run(inbound.async_handle_event(_event("message", {"id": "A1", "fromMe": True, "from": chat, "to": chat, "body": "Certo, la aspettiamo!"}, "A1")))
    # A WAHA retry of the same event is not noted twice.
    run(inbound.async_handle_event(_event("message", {"id": "A1", "fromMe": True, "from": chat, "to": chat, "body": "Certo, la aspettiamo!"}, "A1")))
    messages = next(c for c in coordinator.whatsapp_chats() if c["chat_id"] == chat)["messages"]
    assert [m["dir"] for m in messages] == ["in", "out"]
    assert messages[1]["text"] == "Certo, la aspettiamo!" and messages[1]["by"] == "Dal telefono" and messages[1]["phone"]
    # Answered from the phone: the chat is read.
    assert next(c for c in coordinator.whatsapp_chats() if c["chat_id"] == chat)["read_at"] >= messages[1]["at"]
    # Never an answer to an offer, and never an external message.
    assert not hass.bus.fired

    # What the desk just sent, echoed back by WAHA (message.any), is not doubled.
    coordinator.record_outgoing_whatsapp(chat, "Le confermo le 15:00")
    run(inbound.async_handle_event(_event("message.any", {"id": "B1", "fromMe": True, "from": "393330000000@c.us", "to": chat, "body": "Le confermo le 15:00"}, "B1")))
    messages = next(c for c in coordinator.whatsapp_chats() if c["chat_id"] == chat)["messages"]
    assert [m["text"] for m in messages].count("Le confermo le 15:00") == 1
    # A received message in «message.any» is ignored (it comes in «message»).
    run(inbound.async_handle_event(_event("message.any", {"id": "C1", "fromMe": False, "from": chat, "body": "doppio"}, "C1")))
    assert not any(m["text"] == "doppio" for m in next(c for c in coordinator.whatsapp_chats() if c["chat_id"] == chat)["messages"])
    # Groups and broadcasts stay out.
    run(inbound.async_handle_event(_event("message", {"id": "D1", "fromMe": True, "to": "1203630@g.us", "body": "gruppo"}, "D1")))
    assert all(c["chat_id"] != "1203630@g.us" for c in coordinator.whatsapp_chats())

"""2.8.4: every WhatsApp sent or received is kept in the card's chat."""

from __future__ import annotations

from custom_components.spa_booking import messaging

from .conftest import run


def test_sent_and_received_are_one_conversation(coordinator, monkeypatch, freeze) -> None:
    freeze("2026-11-13 10:00")

    async def deliver(hass, chat_id, message, blocking=True, waha=None):
        return {"channel": "whatsapp", "chat_id": chat_id, "sent": True, "parts": 1, "error": ""}

    monkeypatch.setattr(messaging, "async_deliver_whatsapp", deliver)
    remove = messaging.add_sent_listener(coordinator.record_outgoing_whatsapp)
    try:
        maria = coordinator.operators[0]
        maria.update(phone="333 1112222", whatsapp_chat_id="", notify_on_create=True)
        booked = run(coordinator.async_create_appointment(
            treatment_id="trt_massaggio_relax_90", start="2026-11-14T10:00:00+01:00",
            first_name="Anna", phone="347 1234567", operator_ids=[maria["id"]]))
        coordinator.appointments[-1]["status"] = "confirmed"
        run(coordinator.async_send_guest_summary(booked["id"]))
        # The guest answers from WhatsApp (spelled @s.whatsapp.net) and Maria accepts.
        coordinator.record_incoming_whatsapp("393471234567@s.whatsapp.net", "Grazie!")
        coordinator.record_incoming_whatsapp("393331112222@c.us", "SI")
    finally:
        remove()
    chats = {c["chat_id"]: c["messages"] for c in coordinator.whatsapp_chats()}
    guest = chats["393471234567@c.us"]
    assert [m["dir"] for m in guest] == ["out", "in"] and "confermata" in guest[0]["text"]
    assert guest[0]["by"] == ""  # no one logged in: «Automatico»
    operator = chats["393331112222@c.us"]
    assert operator[0]["dir"] == "out" and operator[-1] == {**operator[-1], "dir": "in", "operator_id": maria["id"]}
    assert coordinator.chat_stamp

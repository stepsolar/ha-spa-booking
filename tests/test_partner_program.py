"""2.8.6: partner discount for the guests, prize voucher, partner detail."""

from __future__ import annotations

from custom_components.spa_booking import messaging

from .conftest import run

MASSAGE = "trt_massaggio_relax_90"


OPS: list = []


def _setup(coordinator):
    OPS[:] = [o["id"] for o in coordinator.operators]
    settings = coordinator._data["settings"]
    settings.update(partner_discount_pct=10.0, partner_points_per_euro=1.0,
                    partner_reward_points=300, partner_reward_value=30)
    treatment = next(t for t in coordinator.treatments if t["id"] == MASSAGE)
    treatment["price"] = 80.0
    partner = run(coordinator.async_save_partner({"company": "B&B Sole", "first_name": "Rosa",
                                                   "phone": "333 4445556", "code": "PRT-SOLE"}))["partner"]
    return partner


def test_guest_of_a_partner_gets_the_discount_and_partner_the_points(coordinator, freeze) -> None:
    freeze("2026-11-13 10:00")
    partner = _setup(coordinator)
    booked = run(coordinator.async_create_bookings([{
        "treatment_id": MASSAGE, "partner_id": "prt-sole",
        "entries": [{"start": "2026-11-14T10:00:00", "first_name": "Anna", "phone": "347 1234567", "person": 0, "operator_ids": OPS}]}]))
    appointment = next(a for a in coordinator.appointments if a["id"] == booked["appointments"][0]["id"])
    assert appointment["price"] == 72.0 and appointment["partner_discount_pct"] == 10.0
    from custom_components.spa_booking.normalize import _norm_appointment
    assert _norm_appointment(dict(appointment))["partner_discount_pct"] == 10.0  # survives a restart
    detail = coordinator.partner_detail(partner["id"])
    assert detail["points"]["balance"] == 72
    assert detail["bookings"][0]["value"] == 72.0 and detail["bookings"][0]["points"] == 72
    # Partner removed from the booking: list price again, no points.
    run(coordinator.async_set_appointment_partner(appointment["id"], ""))
    assert appointment["price"] is None and "partner_discount_pct" not in appointment
    assert coordinator.partner_detail(partner["id"])["points"]["balance"] == 0


def test_partner_own_discount_and_desk_price_wins(coordinator, freeze) -> None:
    freeze("2026-11-13 10:00")
    partner = _setup(coordinator)
    run(coordinator.async_save_partner({"id": partner["id"], "discount_pct": 15}))
    booked = run(coordinator.async_create_bookings([{
        "treatment_id": MASSAGE, "partner_id": partner["id"],
        "entries": [{"start": "2026-11-14T10:00:00", "first_name": "Anna", "phone": "347 1234567", "person": 0, "operator_ids": OPS},
                    {"start": "2026-11-14T12:00:00", "first_name": "Anna", "phone": "347 1234567", "person": 0,
                     "price": 50, "operator_ids": OPS}]}]))["appointments"]
    prices = sorted(next(a for a in coordinator.appointments if a["id"] == b["id"])["price"] for b in booked)
    assert prices == [50.0, 68.0]


def test_partner_reward_voucher_is_sent(coordinator, freeze, monkeypatch) -> None:
    freeze("2026-11-13 10:00")
    partner = _setup(coordinator)
    sent = []

    async def fake(hass, chat_id, message, blocking=True, waha=None):
        sent.append((chat_id, message))
        return {"sent": True}

    monkeypatch.setattr(messaging, "async_send_whatsapp", fake)
    run(coordinator.async_partner_points_adjust(partner["id"], 300, "Benvenuto"))
    result = run(coordinator.async_partner_reward(partner["id"], "Stefano"))
    assert result["sent"] == "whatsapp" and result["points"]["balance"] == 0
    voucher = next(v for v in coordinator.vouchers if v["id"] == result["voucher"]["id"])
    assert voucher["people"][0]["gift_card_amount"] == 30 and voucher["source"] == "partner"
    assert sent and voucher["code"] in sent[0][1] and "30,00 €" in sent[0][1]
    detail = coordinator.partner_detail(partner["id"])
    assert detail["rewards"][0]["code"] == voucher["code"] and detail["rewards"][0]["sent"] == "whatsapp"
    # No more points: no second voucher.
    import pytest
    from custom_components.spa_booking.exceptions import ValidationError
    with pytest.raises(ValidationError):
        run(coordinator.async_partner_reward(partner["id"]))


def test_confirmation_shows_the_discount(coordinator, freeze, monkeypatch) -> None:
    freeze("2026-11-13 10:00")
    partner = _setup(coordinator)
    sent = []

    async def fake(hass, chat_id, message, blocking=True, waha=None):
        sent.append(message)
        return {"sent": True}

    monkeypatch.setattr(messaging, "async_send_whatsapp", fake)
    booked = run(coordinator.async_create_bookings([{
        "treatment_id": MASSAGE, "partner_id": partner["id"],
        "entries": [{"start": "2026-11-14T10:00:00", "first_name": "Anna", "phone": "347 1234567", "person": i,
                     "operator_ids": OPS} for i in range(2)]}]))["appointments"]
    run(coordinator.async_send_guest_summary(booked[0]["id"]))
    text = sent[-1]
    assert "~80,00 €~ 72,00 €" in text
    assert "🎁 Sconto partner 10%: −16,00 €" in text
    assert "Totale 144,00 €" in text
    # A booking without discount has no discount line, and no empty line for it.
    plain = coordinator.format_summary_group([coordinator.appointment_payload(a) for a in coordinator.appointments[:0]] or [
        {**coordinator.appointment_payload(next(a for a in coordinator.appointments if a["id"] == booked[0]["id"])),
         "price": None, "partner_discount_pct": 0}])
    assert "Sconto" not in plain and "{sconto}" not in plain and "\n\n\n" not in plain


def test_cancel_whole_group_and_tell_the_guest(coordinator, freeze, monkeypatch) -> None:
    freeze("2026-11-13 10:00")
    _setup(coordinator)
    sent = []

    async def fake(hass, chat_id, message, blocking=True, waha=None):
        sent.append((chat_id, message))
        return {"sent": True}

    monkeypatch.setattr(messaging, "async_send_whatsapp", fake)
    booked = run(coordinator.async_create_bookings([{
        "treatment_id": MASSAGE,
        "entries": [{"start": "2026-11-14T10:00:00", "first_name": "Anna", "phone": "347 1234567", "person": i,
                     "operator_ids": OPS} for i in range(2)]}]))["appointments"]
    sent.clear()
    result = run(coordinator.async_cancel_appointment(booked[0]["id"], "Maltempo", whole_group=True))
    assert len(result["cancelled_ids"]) == 2
    assert all(a["status"] == "cancelled" for a in coordinator.appointments if a["id"] in result["cancelled_ids"])
    operator_msgs = len(sent)
    guest = run(coordinator.async_send_cancel_message(result["cancelled_ids"]))
    assert guest == {"sent": 1, "failed": 0, "error": ""}
    chat, text = sent[operator_msgs]
    assert chat == "393471234567@c.us" and "annullamento" in text and "Persona 2" in text


def test_cancel_one_person_only(coordinator, freeze) -> None:
    freeze("2026-11-13 10:00")
    _setup(coordinator)
    booked = run(coordinator.async_create_bookings([{
        "treatment_id": MASSAGE,
        "entries": [{"start": "2026-11-14T10:00:00", "first_name": "Anna", "phone": "347 1234567", "person": i,
                     "operator_ids": OPS} for i in range(2)]}]))["appointments"]
    result = run(coordinator.async_cancel_appointment(booked[0]["id"]))
    assert result["cancelled_ids"] == [booked[0]["id"]]
    other = next(a for a in coordinator.appointments if a["id"] == booked[1]["id"])
    assert other["status"] != "cancelled"

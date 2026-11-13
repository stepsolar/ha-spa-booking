"""Vouchers and gift cards as payments (2.8.1)."""

from __future__ import annotations

import pytest

from custom_components.spa_booking.exceptions import ValidationError

from .conftest import run


def _price(coordinator, treatment_id):
    treatment = next(t for t in coordinator.treatments if t["id"] == treatment_id)
    if not treatment.get("price"):
        treatment["price"] = 60.0
    return float(treatment["price"])


def _book(coordinator, code, treatment="trt_ingresso_90", people=1, when="2026-11-14 10:00"):
    return run(coordinator.async_create_bookings([{
        "treatment_id": treatment,
        "entries": [{"start": when, "first_name": f"Ospite{i}", "phone": "333 7654321", "person": i,
                     "payment": {"voucher": True, "voucher_code": code}} for i in range(people)],
    }]))["appointments"]


def _voucher(coordinator, people):
    return run(coordinator.async_create_voucher("Anna", "333 1111111", "Bea", "333 2222222", people,
                                                created_by_name="Desk"))


def test_gift_card_pays_part_and_keeps_the_rest(coordinator, freeze) -> None:
    freeze("2026-11-13 10:00")
    price = _price(coordinator, "trt_ingresso_90")
    voucher = _voucher(coordinator, [{"name": "", "treatment_ids": [], "gift_card_amount": price / 2}])
    booked = _book(coordinator, voucher["code"])
    appointment = next(a for a in coordinator.appointments if a["id"] == booked[0]["id"])
    totals = coordinator._payment_totals(appointment)
    assert [p["method"] for p in appointment["payments"]] == ["gift_card"]
    assert totals["collected"] == round(price / 2, 2) and totals["due"] == round(price - price / 2, 2)
    stored = next(v for v in coordinator.vouchers if v["id"] == voucher["id"])
    assert stored["status"] == "redeemed"  # the credit is spent

    # A bigger gift card: the booking is paid and the rest stays for next time.
    big = _voucher(coordinator, [{"name": "", "treatment_ids": [], "gift_card_amount": price + 30}])
    _book(coordinator, big["code"], when="2026-11-15 10:00")
    stored = next(v for v in coordinator.vouchers if v["id"] == big["id"])
    assert stored["status"] == "active" and coordinator._voucher_credit(stored) == 30.0
    assert coordinator.voucher_payload(stored)["credit_left"] == 30.0
    # Spent on a second visit.
    _book(coordinator, big["code"], when="2026-11-16 10:00")
    assert stored["status"] == "redeemed"


def test_treatment_voucher_pays_and_extra_is_balance(coordinator, freeze) -> None:
    freeze("2026-11-13 10:00")
    _price(coordinator, "trt_ingresso_90")
    voucher = _voucher(coordinator, [{"name": "Bea", "treatment_ids": ["trt_ingresso_90"]}])
    # Two people booked with a voucher for one: allowed, the second pays.
    booked = _book(coordinator, voucher["code"], people=2)
    paid = [coordinator._payment_totals(next(a for a in coordinator.appointments if a["id"] == b["id"])) for b in booked]
    assert sorted(t["due"] for t in paid) == [0.0, _price(coordinator, "trt_ingresso_90")]
    # Cancelling the voucher's appointment gives the voucher back.
    holder = next(a for a in coordinator.appointments if a["id"] in [b["id"] for b in booked] and a.get("payments"))
    run(coordinator.async_cancel_appointment(holder["id"]))
    stored = next(v for v in coordinator.vouchers if v["id"] == voucher["id"])
    assert stored["status"] == "active" and not stored["treatments_redeemed"] and holder["payments"] == []


def test_wrong_treatment_is_refused(coordinator, freeze) -> None:
    freeze("2026-11-13 10:00")
    voucher = _voucher(coordinator, [{"name": "Bea", "treatment_ids": ["trt_ingresso_90"]}])
    other = next(t["id"] for t in coordinator.treatments if t["id"] != "trt_ingresso_90" and t.get("active", True))
    with pytest.raises(ValidationError, match="manca"):
        _book(coordinator, voucher["code"], treatment=other)


def test_couple_confirmation_lists_both_prices(coordinator, freeze, monkeypatch) -> None:
    """2.8.2: «Invia conferma» on one of a couple sends both, each with its price."""
    from custom_components.spa_booking import messaging

    freeze("2026-11-13 10:00")
    treatment = next(t for t in coordinator.treatments if t["id"] == "trt_ingresso_90")
    treatment["price"] = 80.0
    sent = []

    async def fake(hass, chat_id, message, blocking=True, waha=None):
        sent.append(message)
        return {"sent": True}

    monkeypatch.setattr(messaging, "async_send_whatsapp", fake)
    booked = run(coordinator.async_create_bookings([{
        "treatment_id": "trt_ingresso_90",
        "entries": [{"start": "2026-11-14 10:00", "first_name": "Puleo", "phone": "333 7654321", "person": i}
                    for i in range(2)],
    }]))["appointments"]
    result = run(coordinator.async_send_guest_summary(booked[0]["id"]))
    assert len(result["appointment_ids"]) == 2 and len(sent) == 1
    text = sent[0]
    assert "Persona 1" in text and "Persona 2" in text
    assert text.count("80,00 €") >= 2
    assert "Totale 160,00 €" in text and "Da saldare 160,00 €" in text
    assert all(a["confirmation_sent_at"] for a in coordinator.appointments if a["id"] in result["appointment_ids"])

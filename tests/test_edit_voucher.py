"""3.20.2: a gift voucher chosen while editing a booking pays it, once."""

from __future__ import annotations

from .conftest import run
from .test_operator_notify import MASSAGE


def test_voucher_added_on_edit(coordinator, freeze) -> None:
    freeze("2026-11-10 08:00")
    booked = run(coordinator.async_create_bookings([{
        "treatment_id": MASSAGE,
        "entries": [{"start": "2026-11-12T10:00:00", "first_name": "Anna", "phone": "333 1234567", "person": 0,
                     "price": 80, "operator_ids": [coordinator.operators[0]["id"]]}]}]))["appointments"]
    gift = run(coordinator.async_create_voucher("Bea", "333 2", "Anna", "333 1234567",
                                                [{"name": "Anna", "gift_card_amount": 50}], created_by_name="Laura"))
    row = {"appointment_id": booked[0]["id"], "treatment_id": MASSAGE, "start": "2026-11-12T10:00:00",
           "client_id": booked[0]["client_id"], "person": 0, "price": 80, "operator_id": coordinator.operators[0]["id"]}
    run(coordinator.async_update_booking_batch(booked[0]["id"], [dict(row)], voucher_code=gift["code"]))
    appointment = next(a for a in coordinator.appointments if a["id"] == booked[0]["id"])
    taken = [p for p in appointment["payments"] if p.get("voucher_code") == gift["code"]]
    assert sum(p["amount"] for p in taken) == 50
    assert coordinator._payment_totals(appointment)["due"] == 30
    # Saved again with the same voucher: not used twice.
    run(coordinator.async_update_booking_batch(booked[0]["id"], [dict(row)], voucher_code=gift["code"]))
    appointment = next(a for a in coordinator.appointments if a["id"] == booked[0]["id"])
    assert sum(p["amount"] for p in appointment["payments"] if p.get("voucher_code")) == 50

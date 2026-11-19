"""3.16.0: a changed booking sends «prenotazione modificata», not a new confirmation."""

from __future__ import annotations

from .conftest import run
from .test_operator_notify import MASSAGE, _settle


def _book(coordinator):
    return run(coordinator.async_create_bookings([{
        "treatment_id": MASSAGE,
        "entries": [{"start": "2026-11-12T10:00:00", "first_name": "Anna", "phone": "333 1234567", "person": 0, "operator_ids": [coordinator.operators[0]["id"]]}]}]))["appointments"]


def test_change_after_move(coordinator, sent, freeze) -> None:
    freeze("2026-11-10 08:00")
    booked = _book(coordinator)
    _settle()
    sent.clear()
    run(coordinator.async_send_guest_summary(booked[0]["id"]))
    assert "la Sua prenotazione è confermata" in sent[-1]["message"]

    freeze("2026-11-10 09:00")
    result = run(coordinator.async_update_booking_batch(booked[0]["id"], [{
        "appointment_id": booked[0]["id"], "treatment_id": MASSAGE, "start": "2026-11-14T15:00:00",
        "client_id": booked[0]["client_id"], "person": 0, "operator_id": coordinator.operators[0]["id"]}]))
    moved = result["appointments"][0]
    assert moved["changed_at"] > moved["confirmation_sent_at"]
    _settle()
    sent.clear()
    run(coordinator.async_send_guest_summary(moved["id"]))
    text = sent[-1]["message"]
    assert "è stata modificata ed è confermata" in text and "14" in text
    # Once told, the next one is a plain confirmation again.
    run(coordinator.async_send_guest_summary(moved["id"]))
    assert "la Sua prenotazione è confermata" in sent[-1]["message"]
    # Asked explicitly.
    run(coordinator.async_send_guest_summary(moved["id"], kind="change"))
    assert "modificata" in sent[-1]["message"]


def test_notes_only_is_not_a_change(coordinator, sent, freeze) -> None:
    freeze("2026-11-10 08:00")
    booked = _book(coordinator)
    result = run(coordinator.async_update_booking_batch(booked[0]["id"], [{
        "appointment_id": booked[0]["id"], "treatment_id": MASSAGE, "start": "2026-11-12T10:00:00",
        "client_id": booked[0]["client_id"], "person": 0, "notes": "allergia", "operator_id": coordinator.operators[0]["id"]}]))
    assert not result["appointments"][0]["changed_at"]


def test_single_edit_marks_the_change(coordinator, sent, freeze) -> None:
    freeze("2026-11-10 08:00")
    booked = run(coordinator.async_create_appointment(
        treatment_id=MASSAGE, start="2026-11-12T10:00:00+01:00", first_name="Bea", phone="333 7654321", operator_ids=[coordinator.operators[0]["id"]]))
    run(coordinator.async_send_guest_summary(booked["id"]))
    freeze("2026-11-10 09:00")
    moved = run(coordinator.async_update_appointment(booked["id"], start="2026-11-12T16:00:00+01:00"))
    assert moved["changed_at"] and moved["confirmation_sent_at"]
    _settle()
    run(coordinator.async_send_guest_summary(moved["id"]))
    assert "modificata" in sent[-1]["message"]

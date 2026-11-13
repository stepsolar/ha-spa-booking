"""2.8.3: requests confirmed with an automatic masseuse, and the new masseuse
is asked when an edit changes who does the treatment."""

from __future__ import annotations

from .conftest import run

MASSAGE = "trt_massaggio_relax_90"


def _reachable(coordinator):
    maria, giulia = coordinator.operators[0], coordinator.operators[1]
    for index, operator in enumerate((maria, giulia)):
        operator["notify_on_create"] = True
        operator["whatsapp_chat_id"] = f"39333000000{index}@c.us"
    return maria["id"], giulia["id"]


def _to(sent, operator, coordinator):
    chat = next(o for o in coordinator.operators if o["id"] == operator)["whatsapp_chat_id"]
    return [m["message"] for m in sent if m["chat_id"] == chat]


def test_confirmed_request_asks_a_masseuse(coordinator, sent, freeze) -> None:
    freeze("2026-11-10 08:00")
    maria, giulia = _reachable(coordinator)
    request = run(coordinator.async_create_request(
        first_name="Puleo", phone="+39 347 1111111", date="2026-11-14", people=2,
        entries=[{"treatment_id": MASSAGE, "time": "10:00"}]))
    request = request.get("request", request)
    sent.clear()
    result = run(coordinator.async_confirm_request(request["id"]))
    booked = [a for a in coordinator.appointments if a["id"] in [p["id"] for p in result["appointments"]]]
    assert len(booked) == 2
    assert all(a["operator_id"] for a in booked), "Automatica must pick somebody"
    assert {a["operator_id"] for a in booked} == {maria, giulia}
    assert all(a["offer_state"] == "offered" for a in booked)
    assert _to(sent, maria, coordinator) and _to(sent, giulia, coordinator)


def test_request_confirmed_from_the_form(coordinator, sent, freeze) -> None:
    freeze("2026-11-10 08:00")
    maria, giulia = _reachable(coordinator)
    request = run(coordinator.async_create_request(
        first_name="Rita", phone="+39 347 3333333", date="2026-11-14", people=1,
        entries=[{"treatment_id": MASSAGE, "time": "10:00"}]))
    request = request.get("request", request)
    # The desk moved it to 11:00 and picked Giulia in the form.
    rows = [{"treatment_id": MASSAGE, "entries": [{
        "start": "2026-11-14T11:00:00", "client_id": request["client_id"], "operator_id": giulia, "person": 0}]}]
    result = run(coordinator.async_confirm_request_with(request["id"], rows))
    stored = next(r for r in coordinator.requests if r["id"] == request["id"])
    assert stored["status"] == "confirmed" and stored["appointment_ids"] == [result["appointments"][0]["id"]]
    appointment = next(a for a in coordinator.appointments if a["id"] == stored["appointment_ids"][0])
    assert appointment["operator_id"] == giulia and appointment["start_local" if "start_local" in appointment else "start"]
    assert _to(sent, giulia, coordinator)


def test_new_operator_is_asked_after_an_edit(coordinator, sent, freeze) -> None:
    freeze("2026-11-10 08:00")
    maria, giulia = _reachable(coordinator)
    booked = run(coordinator.async_create_appointment(
        treatment_id=MASSAGE, start="2026-11-12T10:00:00+01:00", first_name="Anna",
        phone="333 1234567", operator_ids=[maria]))
    sent.clear()
    run(coordinator.async_update_appointment(booked["id"], operator_id=giulia))
    appointment = next(a for a in coordinator.appointments if a["id"] == booked["id"])
    assert appointment["operator_id"] == giulia and appointment["offer_state"] == "offered"
    assert _to(sent, giulia, coordinator), "the new masseuse gets the request"
    assert any("non più assegnato" in m for m in _to(sent, maria, coordinator))


def test_new_operator_is_asked_after_a_group_edit(coordinator, sent, freeze) -> None:
    freeze("2026-11-10 08:00")
    maria, giulia = _reachable(coordinator)
    booked = run(coordinator.async_create_bookings([{
        "treatment_id": MASSAGE,
        "entries": [{"start": "2026-11-12T10:00:00", "first_name": "Anna", "phone": "333 1234567",
                     "operator_ids": [maria], "person": 0}]}]))["appointments"]
    sent.clear()
    run(coordinator.async_update_booking_batch(booked[0]["id"], [{
        "id": booked[0]["id"], "treatment_id": MASSAGE, "start": "2026-11-12T10:00:00",
        "client_id": booked[0]["client_id"],
        "operator_id": giulia, "person": 0}]))
    assert _to(sent, giulia, coordinator)

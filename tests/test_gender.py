"""2.3.3: the guest's wish for a woman or a man, and the priority order."""

from __future__ import annotations

import pytest

from custom_components.spa_booking.exceptions import ValidationError

from .conftest import run

MASSAGE = "trt_massaggio_relax_90"


def _team(coordinator):
    maria, giulia = coordinator.operators[0]["id"], coordinator.operators[1]["id"]
    marco = run(coordinator.async_add_operator(
        "Marco", treatment_ids=[MASSAGE], gender="M", priority=5))["id"]
    run(coordinator.async_update_operator(maria, gender="F", priority=2))
    run(coordinator.async_update_operator(giulia, gender="F", priority=1))
    return maria, giulia, marco


def _book(coordinator, start, pool, preference=""):
    return run(coordinator.async_create_appointment(
        treatment_id=MASSAGE, start=start, first_name="Ospite", phone=f"333 {start[11:13]}{len(pool)}0000",
        operator_ids=pool, therapist_preference=preference))


def test_priority_order_without_preference(coordinator, sent, freeze) -> None:
    freeze("2026-11-10 08:00")
    maria, giulia, marco = _team(coordinator)
    booked = _book(coordinator, "2026-11-12T10:00:00+01:00", [maria, giulia, marco])
    appointment = next(a for a in coordinator.appointments if a["id"] == booked["id"])
    # Lowest priority number first: Giulia (1), then Maria (2), then Marco (5).
    assert appointment["offer_candidates"] == [giulia, maria, marco]
    assert appointment["operator_id"] == giulia


def test_preference_for_a_man(coordinator, sent, freeze) -> None:
    freeze("2026-11-10 08:00")
    maria, giulia, marco = _team(coordinator)
    booked = _book(coordinator, "2026-11-12T11:00:00+01:00", [maria, giulia, marco], "M")
    appointment = next(a for a in coordinator.appointments if a["id"] == booked["id"])
    assert appointment["operator_id"] == marco and appointment["offer_candidates"] == [marco]
    assert appointment["therapist_preference"] == "M"


def test_preference_for_a_woman_skips_the_man(coordinator, sent, freeze) -> None:
    freeze("2026-11-10 08:00")
    maria, giulia, marco = _team(coordinator)
    booked = _book(coordinator, "2026-11-12T12:00:00+01:00", [marco, maria, giulia], "F")
    appointment = next(a for a in coordinator.appointments if a["id"] == booked["id"])
    assert appointment["offer_candidates"] == [giulia, maria]


def test_nobody_of_that_gender_free_warns_the_desk(coordinator, sent, freeze) -> None:
    freeze("2026-11-10 08:00")
    maria, giulia, marco = _team(coordinator)
    _book(coordinator, "2026-11-12T15:00:00+01:00", [marco])
    with pytest.raises(ValidationError, match="massaggiatore"):
        _book(coordinator, "2026-11-12T15:00:00+01:00", [maria, giulia, marco], "M")


def test_desk_pick_is_never_second_guessed(coordinator, sent, freeze) -> None:
    freeze("2026-11-10 08:00")
    maria, _giulia, _marco = _team(coordinator)
    booked = _book(coordinator, "2026-11-12T16:00:00+01:00", [maria], "M")
    appointment = next(a for a in coordinator.appointments if a["id"] == booked["id"])
    assert appointment["operator_id"] == maria


def test_request_carries_the_preference(coordinator, sent, freeze) -> None:
    freeze("2026-11-10 08:00")
    _team(coordinator)
    request = run(coordinator.async_create_request(
        first_name="Ugo", phone="+39 347 1111111", date="2026-11-14", people=1,
        entries=[{"treatment_id": MASSAGE, "time": "10:00"}], therapist_preference="M"))
    request = request.get("request", request)
    assert request["therapist_preference"] == "M"
    run(coordinator.async_confirm_request(request["id"]))
    booked = [a for a in coordinator.appointments if a.get("therapist_preference") == "M"]
    assert booked, "the confirmed appointment remembers the wish"


def test_each_person_has_her_own_wish(coordinator, sent, freeze) -> None:
    freeze("2026-11-10 08:00")
    _team(coordinator)
    request = run(coordinator.async_create_request(
        first_name="Coppia", phone="+39 347 2222222", date="2026-11-14", people=2,
        entries=[
            {"treatment_id": MASSAGE, "time": "10:00", "person": 0, "therapist_preference": "F"},
            {"treatment_id": MASSAGE, "time": "10:00", "person": 1, "therapist_preference": "M"},
        ]))
    request = request.get("request", request)
    assert [e.get("therapist_preference") for e in request["entries"]] == ["F", "M"]
    run(coordinator.async_confirm_request(request["id"]))
    wishes = sorted(
        (a["person"], a["therapist_preference"]) for a in coordinator.appointments
        if a.get("client_id") == request["client_id"])
    assert wishes == [(0, "F"), (1, "M")]

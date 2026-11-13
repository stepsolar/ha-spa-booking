"""2.8.8: one code per group, split a person off, join another booking."""

from __future__ import annotations

import pytest

from custom_components.spa_booking.exceptions import ValidationError

from .conftest import run

MASSAGE = "trt_massaggio_relax_90"


def _group(coordinator, people=3, day="2026-11-14", name="Anna", phone="347 1234567"):
    ops = [o["id"] for o in coordinator.operators]
    return run(coordinator.async_create_bookings([{
        "treatment_id": MASSAGE,
        "entries": [{"start": f"{day}T{10 + 2 * i:02d}:00:00", "first_name": name, "phone": phone,
                     "person": i, "operator_ids": ops} for i in range(people)]}]))["appointments"]


def _live(coordinator, payloads):
    return [next(a for a in coordinator.appointments if a["id"] == p["id"]) for p in payloads]


def test_a_group_has_one_code(coordinator, freeze) -> None:
    freeze("2026-11-13 10:00")
    booked = _live(coordinator, _group(coordinator))
    assert len({a["code"] for a in booked}) == 1


def test_split_a_person_and_join_her_back(coordinator, freeze) -> None:
    freeze("2026-11-13 10:00")
    booked = _live(coordinator, _group(coordinator))
    code = booked[0]["code"]
    result = run(coordinator.async_split_from_group(booked[1]["id"]))
    moved = booked[1]
    assert moved["code"] == result["code"] != code and moved["person"] == 0
    assert moved["client_id"] == booked[0]["client_id"] and moved["batch_id"] != booked[0]["batch_id"]
    assert [booked[0]["person"], booked[2]["person"]] == [0, 1]  # numbered again
    assert any(h.get("changes") and any(c["field"] == "code" for c in h["changes"]) for h in moved["history"])
    # Joining her back by her code.
    run(coordinator.async_join_group(booked[0]["id"], result["code"]))
    assert moved["code"] == code and moved["batch_id"] == booked[0]["batch_id"] and moved["person"] == 2


def test_join_a_different_client(coordinator, freeze) -> None:
    freeze("2026-11-13 10:00")
    first = _live(coordinator, _group(coordinator, people=1))
    other = _live(coordinator, _group(coordinator, people=2, day="2026-11-15", name="Marco", phone="333 9876543"))
    run(coordinator.async_join_group(first[0]["id"], other[0]["code"].lower()))
    assert {a["code"] for a in first + other} == {first[0]["code"]}
    assert [a["person"] for a in other] == [1, 2] and other[0]["client_id"] != first[0]["client_id"]


def test_refusals(coordinator, freeze) -> None:
    freeze("2026-11-13 10:00")
    single = _live(coordinator, _group(coordinator, people=1))
    with pytest.raises(ValidationError):
        run(coordinator.async_split_from_group(single[0]["id"]))
    with pytest.raises(ValidationError):
        run(coordinator.async_join_group(single[0]["id"], "ZZZZZ"))
    with pytest.raises(ValidationError):
        run(coordinator.async_join_group(single[0]["id"], single[0]["code"]))

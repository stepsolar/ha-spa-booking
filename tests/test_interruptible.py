"""3.20.5: a shared spa entry may be interrupted by a massage and lengthened."""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from custom_components.spa_booking.exceptions import OverlapError

from .conftest import run

SPA = "trt_ingresso_120"
MASSAGE = "trt_massaggio_relax_90"


def _rows(coordinator, spa_extra=0, second_massage=False):
    ops = [o["id"] for o in coordinator.operators]
    guest = {"first_name": "Anna", "last_name": "Rossi", "phone": "347 1234567", "person": 0}
    rows = [
        {"treatment_id": SPA, "entries": [{"start": "2026-11-14T16:00:00", **guest, "extra_min": spa_extra}]},
        {"treatment_id": MASSAGE, "entries": [{"start": "2026-11-14T17:00:00", **guest, "operator_ids": ops[:1]}]},
    ]
    if second_massage:
        rows.append({"treatment_id": "trt_massaggio_relax_120", "entries": [{"start": "2026-11-14T17:30:00", **guest, "operator_ids": ops}]})
    return rows


def _flag(coordinator, value=True):
    run(coordinator.async_update_category("cat_ingresso_spa", capacity={"interruptible": value}))


def test_refused_without_the_flag(coordinator, freeze) -> None:
    freeze("2026-11-14 09:00")
    with pytest.raises(OverlapError):
        run(coordinator.async_create_bookings(_rows(coordinator)))


def test_allowed_and_lengthened_with_the_flag(coordinator, freeze) -> None:
    freeze("2026-11-14 09:00")
    _flag(coordinator)
    assert coordinator._category("cat_ingresso_spa")["interruptible"] is True
    run(coordinator.async_create_bookings(_rows(coordinator, spa_extra=90)))
    spa = next(a for a in coordinator.appointments if a["treatment_id"] == SPA)
    assert spa["extra_min"] == 90
    start, end = (datetime.fromisoformat(spa[key]) for key in ("start", "end"))
    assert end - start == timedelta(minutes=210)  # 16:00 + 120 + 90 = 19:30


def test_two_massages_still_refused(coordinator, freeze) -> None:
    freeze("2026-11-14 09:00")
    _flag(coordinator)
    with pytest.raises(OverlapError):
        run(coordinator.async_create_bookings(_rows(coordinator, second_massage=True)))


def test_extra_min_ignored_on_other_categories(coordinator, freeze) -> None:
    freeze("2026-11-14 09:00")
    run(coordinator.async_create_bookings([{"treatment_id": MASSAGE, "entries": [
        {"start": "2026-11-14T10:00:00", "first_name": "Bea", "phone": "347 7654321", "extra_min": 60, "operator_ids": [coordinator.operators[0]["id"]]}]}]))
    assert coordinator.appointments[-1]["extra_min"] == 0


def test_single_edit_keeps_the_extension(coordinator, freeze) -> None:
    freeze("2026-11-14 09:00")
    _flag(coordinator)
    run(coordinator.async_create_bookings(_rows(coordinator, spa_extra=60)))
    spa = next(a for a in coordinator.appointments if a["treatment_id"] == SPA)
    end = spa["end"]
    run(coordinator.async_update_appointment(spa["id"], notes="ciao"))
    spa = next(a for a in coordinator.appointments if a["treatment_id"] == SPA)
    assert spa["extra_min"] == 60 and spa["end"] == end

"""Agenda rules: operator pause, free-operator choice, edits, monthly report."""

from __future__ import annotations

import pytest

from custom_components.spa_booking.const import KEY_CATEGORIES
from custom_components.spa_booking.exceptions import OverlapError, SpaBookingError

from .conftest import run

MASSAGE_90 = "trt_massaggio_relax_90"


def _ops(coordinator):
    maria, giulia = coordinator.operators
    return maria["id"], giulia["id"]


def _book(coordinator, start, operator_ids, phone="333 1111111", **extra):
    return run(
        coordinator.async_create_appointment(
            treatment_id=extra.pop("treatment_id", MASSAGE_90),
            start=start,
            first_name=extra.pop("first_name", "Cliente"),
            last_name=phone[-3:],
            phone=phone,
            operator_ids=operator_ids,
            **extra,
        )
    )


@pytest.fixture
def massages(coordinator, freeze, sent):
    freeze("2026-11-10 08:00")
    for category in coordinator._data[KEY_CATEGORIES]:
        if category["id"] == "cat_massaggi":
            category["pause_min"] = 15
    return coordinator


def test_pause_after_existing_appointment(massages) -> None:
    maria, _ = _ops(massages)
    _book(massages, "2026-11-12 10:00", [maria])  # 10:00-11:30, busy till 11:45
    with pytest.raises(OverlapError):
        _book(massages, "2026-11-12 11:30", [maria], phone="333 2222222")
    _book(massages, "2026-11-12 11:45", [maria], phone="333 3333333")


def test_pause_before_existing_appointment(massages) -> None:
    """New: the new massage also needs its own pause before the next one."""
    maria, _ = _ops(massages)
    _book(massages, "2026-11-12 12:00", [maria])
    with pytest.raises(OverlapError):
        _book(massages, "2026-11-12 10:30", [maria], phone="333 2222222")  # ends 12:00
    _book(massages, "2026-11-12 10:15", [maria], phone="333 3333333")  # 11:45 + 15


def test_busy_first_choice_falls_to_free_colleague(massages) -> None:
    maria, giulia = _ops(massages)
    _book(massages, "2026-11-12 10:00", [maria])
    second = _book(massages, "2026-11-12 10:00", [maria, giulia], phone="333 2222222")
    assert second["operator_id"] == giulia


def test_everybody_busy_still_refused(massages) -> None:
    maria, giulia = _ops(massages)
    _book(massages, "2026-11-12 10:00", [maria])
    _book(massages, "2026-11-12 10:00", [giulia], phone="333 2222222")
    with pytest.raises(OverlapError):
        _book(massages, "2026-11-12 10:00", [maria, giulia], phone="333 3333333")


def test_editing_old_back_to_back_pair_keeps_working(massages) -> None:
    """Appointments booked back to back before the rule can still be edited."""
    maria, _ = _ops(massages)
    for category in massages._data[KEY_CATEGORIES]:
        category["pause_min"] = 0
    first = _book(massages, "2026-11-12 10:00", [maria])
    _book(massages, "2026-11-12 11:30", [maria], phone="333 2222222")
    for category in massages._data[KEY_CATEGORIES]:
        category["pause_min"] = 15
    updated = run(massages.async_update_appointment(first["id"], notes="nota nuova"))
    assert updated["notes"] == "nota nuova"


def test_deleted_treatment_does_not_break_bookings(massages) -> None:
    maria, _ = _ops(massages)
    booked = _book(massages, "2026-11-12 10:00", [maria])
    for appointment in massages.appointments:
        if appointment["id"] == booked["id"]:
            appointment["treatment_id"] = "trt_gone"
    _book(massages, "2026-11-12 13:00", [maria], phone="333 2222222")


def test_monthly_report_includes_last_day(coordinator, freeze, sent) -> None:
    freeze("2026-10-30 08:00")
    maria, _ = _ops(coordinator)
    _book(coordinator, "2026-10-31 18:00", [maria])
    for appointment in coordinator.appointments:
        appointment["status"] = "confirmed"
    freeze("2026-11-01 09:00")
    first, following = coordinator._month_bounds(None)
    assert (first.isoformat(), following.isoformat()) == ("2026-10-01", "2026-11-01")
    report = coordinator.monthly_report()
    text = repr(report)
    assert "2026-10-31" in text


def test_failed_batch_edit_leaves_everything_as_it_was(massages) -> None:
    import copy

    maria, giulia = _ops(massages)
    first = _book(massages, "2026-11-12 10:00", [maria])
    stored = next(a for a in massages.appointments if a["id"] == first["id"])
    assert stored["batch_id"]
    before = copy.deepcopy(massages._data)
    rows = [
        {"appointment_id": first["id"], "treatment_id": MASSAGE_90,
         "start": "2026-11-12 14:00", "operator_ids": [giulia]},
        {"treatment_id": "trt_does_not_exist", "start": "2026-11-12 16:00"},
    ]
    with pytest.raises(SpaBookingError):
        run(massages.async_update_booking_batch(first["id"], rows))
    assert massages._data == before


def test_category_rule_can_be_forced(massages) -> None:
    """'Privata' takes morning bookings Mon-Fri only: the desk may book anyway."""
    from custom_components.spa_booking.coordinator import FORCE_RULES
    from custom_components.spa_booking.exceptions import CategoryRuleError

    for category in massages._data[KEY_CATEGORIES]:
        if category["id"] == "cat_massaggi":
            category.update(
                name="Privata", morning_start="09:00", morning_end="13:00",
                morning_days=[0, 1, 2, 3, 4],
            )
    maria, _ = _ops(massages)
    with pytest.raises(CategoryRuleError, match="Privata' accetta prenotazioni di mattina solo"):
        _book(massages, "2026-11-14 10:00", [maria])  # a Saturday
    token = FORCE_RULES.set(True)
    try:
        booked = _book(massages, "2026-11-14 10:00", [maria])
    finally:
        FORCE_RULES.reset(token)
    assert booked["id"]
    # The flag lasted for that call only.
    with pytest.raises(CategoryRuleError):
        _book(massages, "2026-11-14 11:45", [maria], phone="333 4444444")

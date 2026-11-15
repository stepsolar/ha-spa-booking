"""3.4.0: how many people a category holds at once, and staggered entries."""

from __future__ import annotations

from datetime import date

import pytest

from custom_components.spa_booking.coordinator import FORCE_RULES
from custom_components.spa_booking.exceptions import CategoryRuleError, ValidationError

from .conftest import run

SPA = "trt_ingresso_90"
SPA_LONG = "trt_ingresso_120"
MASSAGE = "trt_massaggio_relax_90"


def _book(coordinator, treatment_id, start, people=1, name="Anna", ops=None):
    entries = [{"start": start, "first_name": f"{name}{i}", "phone": f"347 {sum(map(ord, name)) % 1000:03d}45{i:02d}", "person": i,
                **({"operator_ids": ops} if ops else {})} for i in range(people)]
    return run(coordinator.async_create_bookings([{"treatment_id": treatment_id, "entries": entries}]))


def _cap(coordinator, category_id, **fields):
    return run(coordinator.async_update_category(category_id, capacity=fields))


def test_massages_at_once_rigid(coordinator, freeze) -> None:
    freeze("2026-11-14 09:00")
    _cap(coordinator, "cat_massaggi", capacity_max=1)
    ops = [o["id"] for o in coordinator.operators]
    _book(coordinator, MASSAGE, "2026-11-16T17:00:00", ops=[ops[0]], name="A")
    with pytest.raises(ValidationError, match="è al completo alle 17:30") as err:
        _book(coordinator, MASSAGE, "2026-11-16T17:30:00", ops=[ops[1]], name="B")
    assert not isinstance(err.value, CategoryRuleError)  # never forceable here
    with pytest.raises(ValidationError, match="è al completo alle 17:00"):
        _book(coordinator, MASSAGE, "2026-11-16T16:00:00", ops=[ops[1]], name="C")
    token = FORCE_RULES.set(True)
    try:
        with pytest.raises(ValidationError, match="al completo"):
            _book(coordinator, MASSAGE, "2026-11-16T17:15:00", ops=[ops[1]], name="D")
    finally:
        FORCE_RULES.reset(token)
    # When the first one has finished the slot is free again.
    _book(coordinator, MASSAGE, "2026-11-16T18:30:00", ops=[ops[1]], name="E")


def test_spa_entries_six_every_fifteen_minutes(coordinator, freeze) -> None:
    freeze("2026-11-14 09:00")
    _cap(coordinator, "cat_ingresso_spa", capacity_max=16, entry_max=6, entry_minutes=15, capacity_force=True)
    _book(coordinator, SPA, "2026-11-16T16:00:00", people=6, name="A")
    with pytest.raises(CategoryRuleError, match="ha già 6 ingressi in 15 minuti dalle 16:00, il prossimo ingresso è alle 16:15"):
        _book(coordinator, SPA_LONG, "2026-11-16T16:05:00", name="B")
    _book(coordinator, SPA_LONG, "2026-11-16T16:15:00", people=6, name="C")
    _book(coordinator, SPA, "2026-11-16T16:30:00", people=4, name="D")
    with pytest.raises(CategoryRuleError, match="al completo alle 16:45, massimo 16"):
        _book(coordinator, SPA, "2026-11-16T16:45:00", name="E")
    # The website never offers what is full.
    coordinator._data["settings"]["web_enabled"] = True
    times = run(coordinator.async_public_availability(date(2026, 11, 16), SPA))
    offered = {s["time"] if isinstance(s, dict) else s for s in (times.get("slots") or times.get("times") or [])}
    assert "16:45" not in offered and "16:05" not in offered
    assert "10:00" in offered, times


def test_group_forced_and_window(coordinator, freeze) -> None:
    freeze("2026-11-14 09:00")
    _cap(coordinator, "cat_ingresso_spa", capacity_max=16, entry_max=6, entry_minutes=15, capacity_force=True,
         capacity_from="15:00", capacity_to="20:00")
    with pytest.raises(CategoryRuleError):
        _book(coordinator, SPA, "2026-11-16T16:00:00", people=18)
    token = FORCE_RULES.set(True)
    try:
        booked = _book(coordinator, SPA, "2026-11-16T16:00:00", people=18)
    finally:
        FORCE_RULES.reset(token)
    assert booked["count"] == 18
    # Editing one of the group without moving it is not refused.
    first = booked["appointments"][0]
    run(coordinator.async_update_appointment(first["id"], notes="arriva col gruppo"))
    # Outside the window the rules do not apply.
    _book(coordinator, SPA, "2026-11-16T10:00:00", people=8)

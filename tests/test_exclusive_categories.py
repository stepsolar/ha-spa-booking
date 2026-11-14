"""2.9.1: mutually exclusive categories never overlap, not even forced."""

from __future__ import annotations

import pytest

from custom_components.spa_booking.coordinator import FORCE_RULES

from .conftest import run

SPA = "trt_ingresso_90"


def _private(coordinator):
    shared = next(t for t in coordinator.treatments if t["id"] == SPA)
    category = run(coordinator.async_add_category("Spa privata", exclusive_with=[shared["category_id"]]))
    return run(coordinator.async_add_treatment("Spa privata 2 ore", category_id=category["id"], duration_min=120, price=150))


def _book(coordinator, treatment_id, start, name):
    return run(coordinator.async_create_bookings([{
        "treatment_id": treatment_id,
        "entries": [{"start": start, "first_name": name, "phone": "347 1234567"}]}]))


def test_private_spa_refused_over_shared_spa(coordinator, freeze) -> None:
    freeze("2026-11-14 09:00")
    private = _private(coordinator)
    _book(coordinator, SPA, "2026-11-14T10:00:00", "Anna")
    with pytest.raises(Exception, match="non può sovrapporsi"):
        _book(coordinator, private["id"], "2026-11-14T11:00:00", "Bruno")
    # «Prenota comunque» must not lift this rule.
    token = FORCE_RULES.set(True)
    try:
        with pytest.raises(Exception, match="non può sovrapporsi"):
            _book(coordinator, private["id"], "2026-11-14T09:00:00", "Bruno")
    finally:
        FORCE_RULES.reset(token)
    # Back to back is fine.
    _book(coordinator, private["id"], "2026-11-14T12:00:00", "Bruno")


def test_private_spa_package_refused(coordinator, freeze) -> None:
    freeze("2026-11-14 09:00")
    private = _private(coordinator)
    _book(coordinator, SPA, "2026-11-14T15:00:00", "Anna")
    with pytest.raises(Exception, match="non può sovrapporsi"):
        run(coordinator.async_create_bookings([{"treatment_id": private["id"], "entries": [
            {"start": "2026-11-14T14:00:00", "first_name": "Bruno", "phone": "347 7654321", "person": i,
             "package_key": "41:0", "package_group": "g1"} for i in range(2)]}]))

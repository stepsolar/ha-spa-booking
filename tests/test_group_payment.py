"""3.18.1: a taking for a whole group, split by what each person owes."""

from __future__ import annotations

from .conftest import run

SPA = "trt_ingresso_90"


def _group(coordinator, people=2):
    entries = [{"start": "2026-11-16T15:00:00", "first_name": "Anna", "phone": "347 1234567", "person": i,
                "price": 40} for i in range(people)]
    return run(coordinator.async_create_bookings([{"treatment_id": SPA, "entries": entries}]))["appointments"]


def _due(coordinator, aid):
    return coordinator._payment_totals(next(a for a in coordinator.appointments if a["id"] == aid))["due"]


def test_split_over_the_group(coordinator, freeze) -> None:
    freeze("2026-11-14 09:00")
    group = _group(coordinator)
    ids = [a["id"] for a in group]
    result = run(coordinator.async_add_payment(ids[0], "cash", 80, appointment_ids=ids))
    assert [p["amount"] for p in result["parts"]] == [40.0, 40.0]
    assert _due(coordinator, ids[0]) == 0 and _due(coordinator, ids[1]) == 0
    # One taking: removed from everybody.
    pay = next(a for a in coordinator.appointments if a["id"] == ids[1])["payments"][0]
    run(coordinator.async_delete_payment(ids[1], pay["id"]))
    assert all(not a.get("payments") for a in coordinator.appointments if a["id"] in ids)


def test_partial_and_extra(coordinator, freeze) -> None:
    freeze("2026-11-14 09:00")
    ids = [a["id"] for a in _group(coordinator)]
    run(coordinator.async_add_payment(ids[0], "card", 50, appointment_ids=ids))
    assert _due(coordinator, ids[0]) == 0 and _due(coordinator, ids[1]) == 30
    run(coordinator.async_add_payment(ids[0], "card", 40, appointment_ids=ids))
    # 30 on the second, the 10 more on the first.
    assert _due(coordinator, ids[1]) == 0
    first = next(a for a in coordinator.appointments if a["id"] == ids[0])
    assert sum(p["amount"] for p in first["payments"]) == 50


def test_summary_counts_the_party(coordinator, sent, freeze) -> None:
    """80 € on one of two 40 € people: nothing left to pay."""
    freeze("2026-11-14 09:00")
    ids = [a["id"] for a in _group(coordinator)]
    run(coordinator.async_add_payment(ids[0], "cash", 80))
    assert _due(coordinator, ids[1]) == 40  # per person it still reads so
    payloads = [coordinator.appointment_payload(a) for a in coordinator.appointments if a["id"] in ids]
    text = coordinator.format_summary_group(payloads)
    assert "80,00" in text and "40,00 €" not in text.split("80,00")[-1].split("\n")[0]

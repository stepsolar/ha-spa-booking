"""Loyalty points and partners (2.4.0)."""

from __future__ import annotations

import pytest

from custom_components.spa_booking.exceptions import ValidationError

from .conftest import run
from .test_scheduler import _confirmed_booking


def _pay(coordinator, appointment_id, amount, method="card"):
    for appointment in coordinator.appointments:
        if appointment["id"] == appointment_id:
            appointment.setdefault("payments", []).append(
                {"id": f"p{amount}", "method": method, "date": "2026-11-10", "amount": amount}
            )


def test_points_from_takings_and_vouchers(coordinator, sent, freeze) -> None:
    freeze("2026-11-10 08:00")
    coordinator._data["settings"].update(
        {"loyalty_enabled": True, "loyalty_points_per_euro": 2, "loyalty_threshold": 300, "loyalty_reward": 20}
    )
    booked = _confirmed_booking(coordinator, "2026-11-11 09:00")
    client = coordinator.clients[0]
    _pay(coordinator, booked["id"], 60)
    _pay(coordinator, booked["id"], 40, "voucher")  # paid with a voucher: no points
    info = coordinator.loyalty_of(client)
    assert info["earned"] == 120 and info["balance"] == 120 and not info["ready"]
    # A voucher she bought counts too (matched by phone).
    run(coordinator.async_create_voucher(
        "Anna", "+39 333 1234567", "Amica", "", [{"name": "Amica", "treatment_ids": [], "gift_card_amount": 50}],
        None, "Laura"))
    assert coordinator.loyalty_of(client)["earned"] == 220
    # A correction by the desk.
    run(coordinator.async_loyalty_adjust(client["id"], 100, "Benvenuto", "Laura"))
    info = coordinator.loyalty_of(client)
    assert info["balance"] == 320 and info["ready"]
    # The reward: a voucher worth 20 €, points taken, WhatsApp sent.
    result = run(coordinator.async_loyalty_reward(client["id"], "Laura"))
    assert result["sent"] and result["loyalty"]["balance"] == 20
    reward = next(v for v in coordinator.vouchers if v.get("source") == "punti")
    assert reward["people"][0]["gift_card_amount"] == 20 and reward["client_id"] == client["id"]
    assert reward["code"] in str(sent[-1]) and "20,00 €" in str(sent[-1])
    # The reward voucher itself earns nothing; not enough points for another.
    assert coordinator.loyalty_of(client)["earned"] == 220
    with pytest.raises(ValidationError):
        run(coordinator.async_loyalty_reward(client["id"]))
    # A cancelled appointment loses its points.
    for appointment in coordinator.appointments:
        appointment["status"] = "cancelled"
    assert coordinator.loyalty_of(client)["earned"] == 100
    assert [e["kind"] for e in client["loyalty_log"]] == ["rettifica", "premio"]


def test_automatic_rewards(coordinator, sent, freeze) -> None:
    freeze("2026-11-10 08:00")
    booked = _confirmed_booking(coordinator, "2026-11-11 09:00")
    _pay(coordinator, booked["id"], 120)
    coordinator._data["settings"].update({"loyalty_threshold": 100, "loyalty_reward": 10})
    assert run(coordinator.async_loyalty_tick())["rewards"] == 0  # off by default
    coordinator._data["settings"]["loyalty_enabled"] = True
    assert run(coordinator.async_loyalty_tick())["rewards"] == 1
    assert run(coordinator.async_loyalty_tick())["rewards"] == 0  # 20 points left
    assert "loyalty" not in coordinator.export_data()  # worked out, never stored


def test_partners(coordinator) -> None:
    first = run(coordinator.async_save_partner({"first_name": "Giulia", "company": "B&B Mare", "phone": "333 1"}))["partner"]
    assert first["code"].startswith("PRT-") and first["source"] == "manuale"
    changed = run(coordinator.async_save_partner({"id": first["id"], "notes": "Porta clienti in estate"}))["partner"]
    assert changed["code"] == first["code"] and changed["company"] == "B&B Mare"
    with pytest.raises(ValidationError):
        run(coordinator.async_save_partner({"company": "Altro", "code": first["code"]}))
    with pytest.raises(ValidationError):
        run(coordinator.async_save_partner({"notes": "senza nome"}))
    run(coordinator.async_delete_partner(first["id"]))
    assert coordinator.partners == []

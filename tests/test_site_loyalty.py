"""3.23.1: the shop buyers of the site get a client card and their points, past orders too."""

from __future__ import annotations

from .conftest import run
from .test_site_contacts import site  # noqa: F401


def test_shop_buyer_gets_a_card_and_points(coordinator, site) -> None:  # noqa: F811
    coordinator._data["settings"].update({"loyalty_enabled": True, "loyalty_points_per_euro": 1})
    run(coordinator.async_site_sync())
    luca = next(c for c in coordinator.site_contacts if c["email"] == "luca@x.it")
    client = next(c for c in coordinator.clients if c["id"] == luca["client_id"])
    assert client["email"] == "luca@x.it" and client["first_name"] == "Luca"
    assert client["shop_total"] == 80 and coordinator.loyalty_of(client)["balance"] == 80
    # A newsletter subscriber gets no card by herself...
    giulia = next(c for c in coordinator.site_contacts if c["email"] == "giulia@x.it")
    assert not giulia["client_id"]
    # ...until «Apri la scheda cliente».
    card = run(coordinator.async_site_client(giulia["id"]))
    assert card["first_name"] == "Giulia" and card["last_name"] == "Martino"
    assert next(c for c in coordinator.site_contacts if c["id"] == giulia["id"])["client_id"] == card["id"]
    # Syncing again: no double cards, same points.
    before = len(coordinator.clients)
    run(coordinator.async_site_sync())
    assert len(coordinator.clients) == before and coordinator.loyalty_of(client)["balance"] == 80


def test_online_voucher_not_counted_twice(coordinator, site) -> None:  # noqa: F811
    """The shop total holds the vouchers bought there: the larger counts, once."""
    coordinator._data["settings"].update({"loyalty_enabled": True, "loyalty_points_per_euro": 1})
    run(coordinator.async_site_sync())
    luca = next(c for c in coordinator.clients if c["email"] == "luca@x.it")
    run(coordinator.async_save_client(client_id=luca["id"], phone="+39 347 9990001"))
    voucher = run(coordinator.async_create_voucher(
        "Luca", "+39 347 9990001", "Amica", "", [{"name": "Amica", "treatment_ids": [], "gift_card_amount": 80}],
        None, "Shop"))
    stored = next(v for v in coordinator.vouchers if v["id"] == voucher["id"])
    stored["source"] = "wordpress"
    run(coordinator.async_voucher_clients(voucher["id"], send_message=False))
    assert coordinator.loyalty_of(luca)["balance"] == 80


def test_editing_a_voucher_registers_its_people(coordinator, freeze, monkeypatch) -> None:
    from types import SimpleNamespace
    from unittest.mock import AsyncMock, MagicMock

    from custom_components.spa_booking import services
    from custom_components.spa_booking.const import DOMAIN

    freeze("2026-11-26 18:00")
    voucher = run(coordinator.async_create_voucher(
        "Marta Neri", "+39 347 5550001", "Elisa Gialli", "+39 347 5550002",
        [{"name": "Elisa", "treatment_ids": [], "gift_card_amount": 50}], None, "Laura"))
    hass = MagicMock()
    hass.data = {DOMAIN: coordinator}
    monkeypatch.setattr(services, "_pin_signer", AsyncMock(return_value=("u", "Stefano")))
    call = SimpleNamespace(hass=hass, context=SimpleNamespace(user_id=None), data={
        "voucher_id": voucher["id"], "buyer_name": "Marta Neri", "buyer_phone": "+39 347 5550001",
        "recipient_name": "Elisa Gialli", "recipient_phone": "+39 347 5550002",
        "people": [{"name": "Elisa", "treatment_ids": [], "gift_card_amount": 50}], "pin": "1234"})
    run(services._async_update_voucher(call))
    names = {(c["first_name"], c["last_name"]) for c in coordinator.clients}
    assert ("Marta", "Neri") in names and ("Elisa", "Gialli") in names
    stored = next(v for v in coordinator.vouchers if v["id"] == voucher["id"])
    assert stored["points_state"] == "pending"  # points still to give

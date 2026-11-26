"""3.23.0: a voucher's buyer and recipient become clients; only the buyer gets points."""

from __future__ import annotations

from .conftest import run
from .test_wp_shop import shop  # noqa: F401


def _setup(coordinator):
    coordinator._data["settings"].update(
        {"loyalty_enabled": True, "loyalty_points_per_euro": 1, "loyalty_threshold": 300, "loyalty_reward": 20})


def _sell(coordinator, buyer_phone="+39 347 1112223", recipient_phone="+39 333 4445556"):
    return run(coordinator.async_create_voucher(
        "Anna Rossi", buyer_phone, "Sara Bianchi", recipient_phone,
        [{"name": "Sara", "treatment_ids": [], "gift_card_amount": 100}], None, "Laura"))


def test_confirm_registers_both_and_awards_the_buyer(coordinator, sent, freeze) -> None:
    freeze("2026-11-26 18:00")
    _setup(coordinator)
    voucher = _sell(coordinator)
    assert voucher["points_state"] == "pending"
    result = run(coordinator.async_voucher_clients(voucher["id"], by="Laura"))
    buyer = next(c for c in coordinator.clients if c["id"] == result["buyer"]["id"])
    recipient = next(c for c in coordinator.clients if c["id"] == result["recipient"]["id"])
    assert (buyer["first_name"], buyer["last_name"]) == ("Anna", "Rossi")
    assert (recipient["first_name"], recipient["last_name"]) == ("Sara", "Bianchi")
    assert result["points"] == 100 and coordinator.loyalty_of(buyer)["balance"] == 100
    assert coordinator.loyalty_of(recipient)["balance"] == 0
    # The WhatsApp: the points, the balance, what is missing; never the code.
    text = str(sent[-1])
    assert result["sent"] and "100 punti" in text and "200 punti" in text
    assert voucher["code"] not in text
    # A second confirm gives nothing more.
    again = run(coordinator.async_voucher_clients(voucher["id"], by="Laura"))
    assert again["points"] == 0 and coordinator.loyalty_of(buyer)["balance"] == 100
    assert len(coordinator.clients) == len({c["id"] for c in coordinator.clients})


def test_not_now_keeps_the_points_for_later(coordinator, sent, freeze) -> None:
    freeze("2026-11-26 18:00")
    _setup(coordinator)
    voucher = _sell(coordinator)
    run(coordinator.async_voucher_clients(voucher["id"], award_points=False, send_message=False))
    buyer = next(c for c in coordinator.clients if c["first_name"] == "Anna")
    assert coordinator.loyalty_of(buyer)["balance"] == 0
    stored = next(v for v in coordinator.vouchers if v["id"] == voucher["id"])
    assert stored["points_state"] == "pending"
    # «Assegna punti» later.
    run(coordinator.async_voucher_clients(voucher["id"], send_message=False, register_recipient=False))
    assert coordinator.loyalty_of(buyer)["balance"] == 100


def test_existing_client_and_same_person(coordinator, sent, freeze) -> None:
    freeze("2026-11-26 18:00")
    _setup(coordinator)
    before = len(coordinator.clients)
    voucher = _sell(coordinator, recipient_phone="+39 347 1112223")
    result = run(coordinator.async_voucher_clients(voucher["id"], send_message=False))
    assert result["buyer"]["id"] == result["recipient"]["id"]
    assert len(coordinator.clients) == before + 1


def test_recipient_paying_herself_earns_points(coordinator, sent, freeze) -> None:
    """Paid with the voucher: nothing; paid by card later: points, as everyone."""
    from .test_loyalty import _pay
    from .test_scheduler import _confirmed_booking

    freeze("2026-11-10 08:00")
    _setup(coordinator)
    booked = _confirmed_booking(coordinator, "2026-11-11 09:00")
    client = coordinator.clients[0]
    _pay(coordinator, booked["id"], 50, "voucher")
    assert coordinator.loyalty_of(client)["earned"] == 0
    _pay(coordinator, booked["id"], 30)
    assert coordinator.loyalty_of(client)["earned"] == 30


def test_old_vouchers_keep_their_points(coordinator, freeze) -> None:
    """Sold before 3.23 (no state): still counted by the buyer's phone."""
    freeze("2026-11-26 18:00")
    _setup(coordinator)
    client = run(coordinator.async_save_client(first_name="Anna", last_name="Rossi", phone="+39 347 1112223"))
    voucher = _sell(coordinator)
    client = next(c for c in coordinator.clients if c["id"] == client["id"])
    assert coordinator.loyalty_of(client)["bought"] == 0  # new: waits for the desk
    next(v for v in coordinator.vouchers if v["id"] == voucher["id"])["points_state"] = ""
    assert coordinator.loyalty_of(client)["bought"] == 100


def test_bought_online_gets_points_at_once(coordinator, shop, sent) -> None:  # noqa: F811
    """Shop online: nobody confirms, the buyer gets her points at the sync."""
    _setup(coordinator)
    run(coordinator.async_wp_sync())
    voucher = next(v for v in coordinator.vouchers if v["source"] == "wordpress")
    assert voucher["points_state"] == "awarded"
    buyer = next(c for c in coordinator.clients if c["id"] == voucher["buyer_client_id"])
    assert (buyer["first_name"], buyer["last_name"]) == ("Filippo", "Rossi")
    assert coordinator.loyalty_of(buyer)["balance"] == 80
    assert voucher["code"] not in str(sent[-1]) and "80 punti" in str(sent[-1])
    recipient = next(c for c in coordinator.clients if c["id"] == voucher["recipient_client_id"])
    assert recipient["first_name"] == "Nicoletta" and coordinator.loyalty_of(recipient)["balance"] == 0
    # The next sync gives nothing more.
    run(coordinator.async_wp_sync())
    assert coordinator.loyalty_of(buyer)["balance"] == 80

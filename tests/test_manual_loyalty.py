"""2.8.11: loyalty voucher sent by hand; packages hidden from web or desk."""

from __future__ import annotations

from custom_components.spa_booking import messaging
from custom_components.spa_booking.normalize import _norm_settings

from .conftest import run


def test_manual_loyalty_voucher_to_client_and_partner(coordinator, freeze, monkeypatch) -> None:
    freeze("2026-11-14 10:00")
    sent = []

    async def fake(hass, chat_id, message, blocking=True, waha=None):
        sent.append((chat_id, message))
        return {"sent": True}

    monkeypatch.setattr(messaging, "async_send_whatsapp", fake)
    client = run(coordinator.async_save_client(first_name="Anna", last_name="Rossi", phone="347 1234567"))
    client = client.get("client", client)
    result = run(coordinator.async_send_loyalty_voucher(client_id=client["id"], discount_percent=15, days=30, by="Stefano"))
    voucher = result["voucher"]
    assert result["sent"] == "whatsapp" and voucher["status"] == "sent" and voucher["manual"]
    assert voucher["discount_percent"] == 15 and voucher["expires_on"] == "2026-12-14"
    assert voucher["code"] in sent[-1][1] and voucher["appointment_id"] == ""
    partner = run(coordinator.async_save_partner({"company": "B&B Sole", "phone": "333 4445556"}))["partner"]
    other = run(coordinator.async_send_loyalty_voucher(partner_id=partner["id"]))
    assert other["voucher"]["partner_id"] == partner["id"] and other["sent"] == "whatsapp"
    assert other["voucher"]["first_name"] == "B&B Sole"


def test_hidden_packages(coordinator) -> None:
    settings = coordinator._data["settings"]
    tid = coordinator.treatments[0]["id"]
    settings.update(_norm_settings({**settings,
        "wp_products": [{"product_id": 1, "variation_id": 0, "name": "A", "price": 100},
                        {"product_id": 2, "variation_id": 0, "name": "B", "price": 120}],
        "wp_product_map": {"1:0": {"people": 2, "treatment_ids": [tid]}, "2:0": {"people": 2, "treatment_ids": [tid]}},
        "package_hidden_web": ["1:0"], "package_hidden_desk": ["2:0"]}))
    packages = {p["key"]: p for p in coordinator.shop_packages()}
    assert packages["1:0"]["hidden_web"] and not packages["1:0"]["hidden_desk"]
    assert packages["2:0"]["hidden_desk"] and not packages["2:0"]["hidden_web"]

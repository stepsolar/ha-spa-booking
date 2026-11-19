"""3.18.0: the gift cards sold in Spa Booking are coupons on the shop, for one purchase."""

from __future__ import annotations

import pytest

from custom_components.spa_booking import wp_shop

from .conftest import run


@pytest.fixture
def site(coordinator, monkeypatch, freeze):
    freeze("2026-11-13 10:00")
    state = {"sent": [], "used": []}

    async def vouchers(session, base, secret, days=200):
        return []

    async def gift_cards(session, base, secret, cards):
        state["sent"].append(cards)
        return {"ok": True, "used": state["used"], "conflicts": []}

    monkeypatch.setattr(wp_shop, "vouchers", vouchers)
    monkeypatch.setattr(wp_shop, "gift_cards", gift_cards)
    monkeypatch.setattr(coordinator, "_http_session", lambda: None)
    run(coordinator.async_update_settings(wp_enabled=True, wp_url="benessere.hotelilmarchese.it"))
    run(coordinator.async_wp_new_secret())
    return state


def _sell(coordinator, people):
    return run(coordinator.async_create_voucher("Anna", "333 1", "Bea", "333 2", people, created_by_name="Laura"))


def test_only_gift_cards_go_to_the_shop(coordinator, site) -> None:
    gift = _sell(coordinator, [{"name": "Bea", "gift_card_amount": 100}])
    _sell(coordinator, [{"name": "Bea", "treatment_ids": ["trt_ingresso_90"]}])
    run(coordinator.async_wp_sync())
    cards = site["sent"][-1]
    assert [c["code"] for c in cards] == [gift["code"]]
    assert cards[0]["amount"] == 100.0 and cards[0]["expires"] == gift["expires_on"]


def test_spent_on_the_shop_then_cancelled(coordinator, site) -> None:
    gift = _sell(coordinator, [{"name": "Bea", "gift_card_amount": 100}])
    site["used"] = [{"code": gift["code"], "order_id": 10300, "amount": 64.5, "at": "2026-11-13T11:00:00+01:00"}]
    result = run(coordinator.async_wp_gift_sync())
    assert result["closed"] == [gift["code"]]
    voucher = next(v for v in coordinator.vouchers if v["id"] == gift["id"])
    # One purchase: the credit the order did not use is gone too.
    assert voucher["status"] == "redeemed" and coordinator._voucher_credit(voucher) == 0
    assert voucher["shop_order_id"] == "10300" and "ordine #10300" in voucher["wp_note"]
    assert coordinator.wp_gift_cards_list() == []
    # The order is cancelled on the shop: the credit is back.
    site["used"] = []
    result = run(coordinator.async_wp_gift_sync())
    assert result["reopened"] == [gift["code"]]
    assert voucher["status"] == "active" and coordinator._voucher_credit(voucher) == 100.0
    assert [c["code"] for c in coordinator.wp_gift_cards_list()] == [gift["code"]]


def test_switched_off(coordinator, site) -> None:
    _sell(coordinator, [{"name": "Bea", "gift_card_amount": 50}])
    run(coordinator.async_update_settings(wp_gift_cards=False))
    # Once with no cards (the shop drops them), then nothing.
    assert run(coordinator.async_wp_gift_sync())["published"] == 0 and site["sent"][-1] == []
    assert run(coordinator.async_wp_gift_sync()) == {"skipped": "spento"}

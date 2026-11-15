"""3.6.0: the products of the online shop, with categories, changed from Spa Booking."""

from __future__ import annotations

import pytest

from custom_components.spa_booking import wp_shop
from custom_components.spa_booking.exceptions import ValidationError

from .conftest import run


def test_change_a_product_and_read_the_list_again(coordinator, monkeypatch) -> None:
    sent = []
    catalogue = {"name": "Percorso Spa", "price": 50.0}

    async def update(session, base, secret, changes):
        sent.append(changes)
        catalogue.update({"name": changes.get("name", catalogue["name"]), "price": float(changes.get("regular_price") or catalogue["price"])})
        return {"ok": True, "id": changes["id"]}

    async def listing(session, base, secret):
        return ([{"product_id": 12, "variation_id": 0, "name": catalogue["name"], "price": catalogue["price"],
                  "categories": [{"id": 3, "name": "Percorsi"}], "status": "publish"}],
                [{"id": 3, "name": "Percorsi", "parent": 0, "count": 1}, {"id": 4, "name": "Coppia", "parent": 0, "count": 0}])

    monkeypatch.setattr(wp_shop, "product_update", update)
    monkeypatch.setattr(wp_shop, "products_and_categories", listing)
    monkeypatch.setattr(coordinator, "_http_session", lambda: None)
    run(coordinator.async_update_settings(wp_enabled=True, wp_url="benessere.example.it"))
    run(coordinator.async_wp_new_secret())
    with pytest.raises(ValidationError, match="nome"):
        run(coordinator.async_wp_product_update(12, {"name": "  "}))
    with pytest.raises(ValidationError, match="Prezzo"):
        run(coordinator.async_wp_product_update(12, {"regular_price": "-3"}))
    run(coordinator.async_wp_product_update(12, {"name": "Percorso Spa 2 ore", "regular_price": "55", "category_ids": [3, 4],
                                                 "secret": "never sent"}))
    assert sent == [{"id": 12, "name": "Percorso Spa 2 ore", "regular_price": "55", "category_ids": [3, 4]}]
    settings = coordinator._data["settings"]
    product = settings["wp_products"][0]
    assert product["name"] == "Percorso Spa 2 ore" and product["price"] == 55.0
    assert product["categories"] == [{"id": 3, "name": "Percorsi"}]
    assert [c["name"] for c in settings["wp_categories"]] == ["Percorsi", "Coppia"]


def test_orders_status_and_vouchers(coordinator, monkeypatch) -> None:
    """3.7.0: orders of the shop, their codes, and what may be changed from here."""
    sent = []

    async def order(session, base, secret, order_id):
        return {"id": order_id, "status": "processing", "items": [{"name": "Massaggio Relax", "codes": "ABC123, XYZ999"}]}

    async def order_update(session, base, secret, changes):
        sent.append(changes)
        return {"id": changes["id"], "status": changes["status"] or "processing"}

    async def nothing():
        return {}

    monkeypatch.setattr(wp_shop, "order", order)
    monkeypatch.setattr(wp_shop, "order_update", order_update)
    monkeypatch.setattr(coordinator, "_http_session", lambda: None)
    monkeypatch.setattr(coordinator, "async_wp_sync", nothing)
    coordinator.hass.async_create_task = lambda coro: coro.close()
    run(coordinator.async_update_settings(wp_enabled=True, wp_url="benessere.example.it"))
    run(coordinator.async_wp_new_secret())
    coordinator.vouchers.append({"id": "v1", "code": "ABC123", "source": "wordpress", "status": "active"})
    got = run(coordinator.async_wp_order(10208))
    assert got["items"][0]["vouchers"] == [{"code": "ABC123", "status": "active", "voucher_id": "v1"},
                                           {"code": "XYZ999", "status": "", "voucher_id": ""}]
    # Plugin 1.4.0 sent the items as plain names (3.7.1).
    async def old_order(session, base, secret, order_id):
        return {"id": order_id, "status": "processing", "items": ["Massaggio Relax ×2"]}

    monkeypatch.setattr(wp_shop, "order", old_order)
    assert run(coordinator.async_wp_order(10208))["items"][0]["name"] == "Massaggio Relax ×2"
    with pytest.raises(ValidationError, match="rimborsi"):
        run(coordinator.async_wp_order_update(10208, status="refunded"))
    with pytest.raises(ValidationError, match="Niente"):
        run(coordinator.async_wp_order_update(10208))
    run(coordinator.async_wp_order_update(10208, status="completed", note="Verificato in reception"))
    assert sent[0]["status"] == "completed" and sent[0]["note"] == "Verificato in reception"


def test_variation_enabled_is_kept() -> None:
    """3.9.0: a disabled variation (plugin 1.6.0) stays disabled; old plugins mean enabled."""
    from custom_components.spa_booking.normalize import _norm_settings

    settings = _norm_settings({"wp_products": [
        {"product_id": 4097, "variation_id": 5118, "name": "senza kit", "enabled": False, "variation_stock_status": "outofstock"},
        {"product_id": 4097, "variation_id": 5117, "name": "con kit"},
    ]})
    off, on = settings["wp_products"]
    assert off["enabled"] is False and off["variation_stock_status"] == "outofstock"
    assert on["enabled"] is True and on["variation_stock_status"] == ""

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

"""3.20.3: a voucher sold as a package keeps its name and price."""

from __future__ import annotations

import pytest

from custom_components.spa_booking.exceptions import ValidationError

from .conftest import run

SPA = "trt_ingresso_90"


def test_voucher_as_package(coordinator) -> None:
    settings = coordinator._data["settings"]
    settings["wp_products"] = [{"key": "p_coppia", "name": "Spa di coppia", "price": 120}]
    settings["wp_product_map"] = {"p_coppia": {"treatment_ids": [SPA], "people": 2, "extras": []}}
    people = [{"name": "Anna", "treatment_ids": [SPA]}, {"name": "Luca", "treatment_ids": [SPA]}]
    voucher = run(coordinator.async_create_voucher("Bea", "333 1", "Anna", "333 2", people,
                                                   created_by_name="Laura", package_key="p_coppia"))
    stored = next(v for v in coordinator.vouchers if v["id"] == voucher["id"])
    assert stored["wp_product_name"] == "Spa di coppia" and stored["value"] == 120
    assert stored["source"] == "" and len(stored["people"]) == 2
    with pytest.raises(ValidationError, match="Pacchetto non trovato"):
        run(coordinator.async_create_voucher("Bea", "", "", "", people, created_by_name="Laura", package_key="nope"))


def test_admin_edits_voucher_same_code(coordinator) -> None:
    settings = coordinator._data["settings"]
    settings["wp_products"] = [{"key": "p_coppia", "name": "Spa di coppia", "price": 120}]
    settings["wp_product_map"] = {"p_coppia": {"treatment_ids": [SPA], "people": 2, "extras": []}}
    voucher = run(coordinator.async_create_voucher("Bea", "333 1", "Anna", "333 2", [{"name": "Anna", "treatment_ids": [SPA]}],
                                                   created_by_name="Laura"))
    people = [{"name": "Anna", "treatment_ids": [SPA]}, {"name": "Luca", "treatment_ids": [SPA]}]
    changed = run(coordinator.async_update_voucher(voucher["id"], "Bea Neri", "333 1", "Anna Rossi", "333 2", people,
                                                   "Stefano", package_key="p_coppia"))
    assert changed["code"] == voucher["code"]
    stored = next(v for v in coordinator.vouchers if v["id"] == voucher["id"])
    assert stored["buyer_name"] == "Bea Neri" and len(stored["people"]) == 2 and stored["wp_product_name"] == "Spa di coppia"
    assert stored["edits"][-1]["by"] == "Stefano" and "people" in stored["edits"][-1]["what"]
    # Used: names only.
    stored["treatments_redeemed"] = True
    with pytest.raises(ValidationError, match="solo nomi e telefoni"):
        run(coordinator.async_update_voucher(voucher["id"], "Bea", "", "Anna", "", people[:1], "Stefano"))
    run(coordinator.async_update_voucher(voucher["id"], "Beatrice Neri", "", "Anna", "", people, "Stefano"))
    assert stored["buyer_name"] == "Beatrice Neri"

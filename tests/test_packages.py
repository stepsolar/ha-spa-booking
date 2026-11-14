"""2.8.9: shop packages for two or more people in bookings and requests."""

from __future__ import annotations

from custom_components.spa_booking.normalize import _norm_appointment, _norm_settings

from .conftest import run

MASSAGE = "trt_massaggio_relax_90"
SPA = "trt_ingresso_90"


def _shop(coordinator):
    for tid, price in ((MASSAGE, 80.0), (SPA, 40.0)):
        next(t for t in coordinator.treatments if t["id"] == tid)["price"] = price
    accessory = coordinator.accessories[0] if coordinator.accessories else None
    extras = [accessory["id"]] if accessory else []
    settings = coordinator._data["settings"]
    settings.update(_norm_settings({**settings,
        "wp_products": [{"product_id": 41, "variation_id": 0, "name": "You&Me", "price": 200},
                        {"product_id": 42, "variation_id": 0, "name": "Relax di coppia", "price": 150}],
        "wp_product_map": {"41:0": {"people": 2, "treatment_ids": [MASSAGE, SPA], "extras": extras},
                           "42:0": {"people": 2, "treatment_ids": [MASSAGE]}}}))
    return extras


def test_two_couples_two_packages(coordinator, freeze) -> None:
    freeze("2026-11-13 10:00")
    extras = _shop(coordinator)
    assert {p["key"] for p in coordinator.shop_packages(min_people=2)} == {"41:0", "42:0"}
    ops = [o["id"] for o in coordinator.operators]

    def entry(person, hour, key, group):
        return {"start": f"2026-11-14T{hour}:00:00", "first_name": "Anna", "phone": "347 1234567", "person": person,
                **({"operator_ids": ops} if hour in ("10", "12") else {}), "extras": extras if key == "41:0" else [], "package_key": key, "package_group": group}
    rows = [
        {"treatment_id": MASSAGE, "entries": [entry(0, "10", "41:0", "g1"), entry(1, "10", "41:0", "g1"),
                                              entry(2, "12", "42:0", "g2"), entry(3, "12", "42:0", "g2")]},
        {"treatment_id": SPA, "entries": [entry(0, "14", "41:0", "g1"), entry(1, "14", "41:0", "g1")]},
    ]
    booked = run(coordinator.async_create_bookings(rows))["appointments"]
    live = [next(a for a in coordinator.appointments if a["id"] == b["id"]) for b in booked]
    first = [a for a in live if a["package_group"] == "g1"]
    second = [a for a in live if a["package_group"] == "g2"]
    assert round(sum(coordinator._payment_totals(a)["total"] for a in first), 2) == 200.0  # extras included
    assert round(sum(coordinator._payment_totals(a)["total"] for a in second), 2) == 150.0
    assert all(a["package_name"] == "You&Me" and a["extras_included"] for a in first)
    massage = next(a for a in first if a["treatment_id"] == MASSAGE)
    assert massage["price"] == round(200 * 80 / 240, 2)
    assert _norm_appointment(dict(massage))["package_group"] == "g1"  # survives a restart


def test_request_with_package_books_the_package_price(coordinator, freeze) -> None:
    freeze("2026-11-13 10:00")
    extras = _shop(coordinator)
    request = run(coordinator.async_create_request(
        first_name="Puleo", phone="+39 347 1111111", date="2026-11-14", people=2,
        entries=[{"treatment_id": MASSAGE, "time": "10:00", "person": p, "package_key": "41:0", "package_group": "x"}
                 for p in range(2)] + [{"treatment_id": SPA, "time": "12:00", "person": p, "package_key": "41:0",
                                         "package_group": "x"} for p in range(2)]))
    request = request.get("request", request)
    assert request["entries"][0]["package_key"] == "41:0"
    result = run(coordinator.async_confirm_request(request["id"]))
    live = [next(a for a in coordinator.appointments if a["id"] == p["id"]) for p in result["appointments"]]
    assert round(sum(coordinator._payment_totals(a)["total"] for a in live), 2) == 200.0
    assert all(a.get("extras") == extras for a in live)

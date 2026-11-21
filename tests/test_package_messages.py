"""3.20.6: a package's accessories are included; the guest reads one price per package."""

from __future__ import annotations

from .conftest import run
from .test_packages import MASSAGE, SPA, _shop


def _book(coordinator, extra_on_top=None):
    extras = _shop(coordinator)
    assert extras, "the default data has an accessory"
    accessory = coordinator.accessories[0]
    accessory["price"] = 5.0
    if extra_on_top:
        coordinator._data["settings"]["accessories"].append({**accessory, "id": "acc_top", "label": "Calice", "price": 8.0})
    ops = [o["id"] for o in coordinator.operators]

    def entry(person, hour, key, group, extra):
        return {"start": f"2026-11-14T{hour}:00:00", "first_name": "Anna", "phone": "347 1234567", "person": person,
                **({"operator_ids": ops} if hour in ("10", "12") else {}), "extras": extra, "package_key": key,
                "package_group": group}
    mine = extras + (["acc_top"] if extra_on_top else [])
    rows = [
        {"treatment_id": MASSAGE, "entries": [entry(0, "10", "41:0", "g1", mine), entry(1, "10", "41:0", "g1", extras),
                                              entry(2, "12", "42:0", "g2", []), entry(3, "12", "42:0", "g2", [])]},
        {"treatment_id": SPA, "entries": [entry(0, "14", "41:0", "g1", extras), entry(1, "14", "41:0", "g1", extras)]},
    ]
    booked = run(coordinator.async_create_bookings(rows))["appointments"]
    return [coordinator.appointment_payload(next(a for a in coordinator.appointments if a["id"] == b["id"])) for b in booked]


def test_message_shows_packages_not_discounts(coordinator, freeze) -> None:
    freeze("2026-11-13 10:00")
    payloads = _book(coordinator)
    label = coordinator.accessories[0]["label"]
    text = "\n".join(coordinator._appointment_lines(payloads, with_price=True))
    assert "📦 *You&Me* · 200,00 €" in text
    assert "📦 *Relax di coppia* · 150,00 €" in text
    assert "📦 Totale pacchetti: 350,00 €" in text
    assert f"Persona 1: 10:00–11:30 Massaggio Relax 90 min, 14:00–15:30 Ingresso Spa 90 min · inclusi: {label}" in text
    assert "~" not in text  # no struck-through list price per treatment
    assert coordinator._discount_line(payloads) == ""


def test_accessory_on_top_of_the_package_is_paid(coordinator, freeze) -> None:
    freeze("2026-11-13 10:00")
    payloads = _book(coordinator, extra_on_top=True)
    total = round(sum(coordinator._payment_totals(p)["total"] for p in payloads), 2)
    # 200 + 150 for the packages, the included accessory free, the glass paid.
    assert total == 350 + 8
    text = "\n".join(coordinator._appointment_lines(payloads, with_price=True))
    assert "in più: Calice 8,00 €" in text


def test_request_message_shows_the_package(coordinator, freeze) -> None:
    freeze("2026-11-13 10:00")
    extras = _shop(coordinator)
    request = run(coordinator.async_create_request(
        first_name="Puleo", phone="+39 347 1111111", date="2026-11-14", people=2,
        entries=[{"treatment_id": MASSAGE, "time": "10:00", "person": p, "package_key": "41:0", "package_group": "x",
                  "extras": extras} for p in range(2)]
        + [{"treatment_id": SPA, "time": "12:00", "person": p, "package_key": "41:0", "package_group": "x",
            "extras": extras} for p in range(2)]))
    request = request.get("request", request)
    payload = coordinator.request_payload(request)
    text = coordinator.format_request_message(payload)
    assert "📦 *You&Me* · 200,00 €" in text
    assert "Persona 2: 10:00 Massaggio Relax 90 min, 12:00 Ingresso Spa 90 min · inclusi:" in text

"""3.16.0: «pochi ingressi» — the desk is told the day before when too few come."""

from __future__ import annotations

from .conftest import run
from .test_capacity import SPA, _book


def _alerts(coordinator, sent):
    return [m for m in sent if m["message"].startswith("⚠️ Pochi ingressi")]


def test_two_people_alert_four_do_not(coordinator, sent, freeze) -> None:
    coordinator._data["settings"]["web_notify_whatsapp"] = "+39 333 0000000"
    freeze("2026-11-10 08:00")
    _book(coordinator, SPA, "2026-11-12T15:00:00", people=2, name="Anna")
    _book(coordinator, SPA, "2026-11-13T10:00:00", people=4, name="Bea")
    sent.clear()
    # Too early: 2 days before.
    run(coordinator.async_low_spa_tick())
    assert not _alerts(coordinator, sent)
    # 24 hours before the first arrival of the 12th: two people, alert.
    freeze("2026-11-11 15:00")
    result = run(coordinator.async_low_spa_tick())
    alerts = _alerts(coordinator, sent)
    assert result["alerted"] == ["2026-11-12"] and len(alerts) == 1
    assert "solo 2 persone (minimo 3)" in alerts[0]["message"] and "15:00" in alerts[0]["message"]
    # Once per day.
    run(coordinator.async_low_spa_tick())
    assert len(_alerts(coordinator, sent)) == 1
    # The 13th has four: no alert.
    freeze("2026-11-12 10:30")
    run(coordinator.async_low_spa_tick())
    assert len(_alerts(coordinator, sent)) == 1


def test_switched_off(coordinator, sent, freeze) -> None:
    coordinator._data["settings"]["low_spa_alert"] = False
    freeze("2026-11-10 08:00")
    _book(coordinator, SPA, "2026-11-11T09:00:00", people=1, name="Anna")
    assert run(coordinator.async_low_spa_tick()) == {"skipped": "spento"}

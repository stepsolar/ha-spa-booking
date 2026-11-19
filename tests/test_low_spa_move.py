"""3.17.0: «pochi ingressi» — another day proposed to the guests, or moved."""

from __future__ import annotations

from .conftest import run
from .test_capacity import SPA, _book


def _days(coordinator, name):
    return sorted(
        a["start"][:10] for a in coordinator.appointments
        if a.get("status") != "cancelled"
        and str(coordinator.appointment_payload(a)["client"].get("first_name", "")).startswith(name)
    )


def _setup(coordinator, freeze):
    coordinator._data["settings"]["web_notify_whatsapp"] = "+39 333 0000000"
    freeze("2026-11-10 08:00")
    _book(coordinator, SPA, "2026-11-12T15:00:00", people=1, name="Anna")
    _book(coordinator, SPA, "2026-11-13T15:00:00", people=2, name="Bea")
    freeze("2026-11-11 15:00")


def test_alert_names_the_best_day(coordinator, sent, freeze) -> None:
    _setup(coordinator, freeze)
    sent.clear()
    run(coordinator.async_low_spa_tick())
    alert = next(m["message"] for m in sent if m["message"].startswith("⚠️ Pochi ingressi"))
    assert "Giorno consigliato: venerdì 13 novembre (2 persone)" in alert
    info = coordinator.low_spa_info("2026-11-12")
    assert info["people"] == 1 and info["suggestions"][0]["day"] == "2026-11-13"
    assert info["suggestions"][0]["enough"] and len(info["bookings"]) == 1


def test_proposal_then_yes_moves(coordinator, sent, freeze) -> None:
    _setup(coordinator, freeze)
    sent.clear()
    result = run(coordinator.async_low_spa_propose("2026-11-12", "2026-11-13"))
    assert len(result["sent"]) == 1
    proposal = sent[-1]
    assert "venerdì 13 novembre alle 15:00" in proposal["message"] and "SÌ" in proposal["message"]
    assert coordinator.low_spa_info("2026-11-12")["bookings"][0]["proposal"]["to"] == "2026-11-13"
    # Not an answer: an ordinary message.
    assert not run(coordinator.async_low_spa_reply(proposal["chat_id"], "A che ora apre la piscina?"))
    sent.clear()
    assert run(coordinator.async_low_spa_reply(proposal["chat_id"], "Sì grazie!"))
    assert _days(coordinator, "Anna") == ["2026-11-13"]
    assert any("modificata" in m["message"] for m in sent if m["chat_id"] == proposal["chat_id"])
    assert any("ha accettato" in m["message"] for m in sent)
    assert not coordinator._data["settings"]["low_spa_proposals"]


def test_proposal_no_keeps_the_day(coordinator, sent, freeze) -> None:
    _setup(coordinator, freeze)
    run(coordinator.async_low_spa_propose("2026-11-12", "2026-11-13"))
    chat = sent[-1]["chat_id"]
    assert run(coordinator.async_low_spa_reply(chat, "No"))
    assert _days(coordinator, "Anna") == ["2026-11-12"]
    assert not coordinator._data["settings"]["low_spa_proposals"]
    assert any("preferisce mantenere" in m["message"] for m in sent)


def test_auto_moves_and_tells(coordinator, sent, freeze) -> None:
    _setup(coordinator, freeze)
    coordinator._data["settings"]["low_spa_move"] = "auto"
    sent.clear()
    run(coordinator.async_low_spa_tick())
    assert _days(coordinator, "Anna") == ["2026-11-13"]
    alert = next(m["message"] for m in sent if m["message"].startswith("⚠️ Pochi ingressi"))
    assert "Spostati a venerdì 13 novembre" in alert
    assert any("modificata" in m["message"] for m in sent)


def test_off_only_alerts(coordinator, sent, freeze) -> None:
    _setup(coordinator, freeze)
    coordinator._data["settings"]["low_spa_move"] = "off"
    run(coordinator.async_low_spa_tick())
    assert _days(coordinator, "Anna") == ["2026-11-12"]
    assert not any("Giorno consigliato" in m["message"] for m in sent)

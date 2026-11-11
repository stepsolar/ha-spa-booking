"""2.3.5: the offer to the masseuses, end to end."""

from __future__ import annotations



from .conftest import run

MASSAGE = "trt_massaggio_relax_90"


def _setup(coordinator, timeout=2, reminder=1):
    maria, giulia = coordinator.operators[0], coordinator.operators[1]
    for operator, phone in ((maria, "+39 333 0000001"), (giulia, "+39 333 0000002")):
        operator["phone"] = phone
        operator["notify_on_create"] = True
        operator["notify_whatsapp"] = True
    maria["priority"], giulia["priority"] = 1, 2
    coordinator._data["settings"].update({"offer_timeout_hours": timeout, "offer_reminder_hours": reminder})
    return maria["id"], giulia["id"]


def _book(coordinator, pool):
    booked = run(coordinator.async_create_appointment(
        treatment_id=MASSAGE, start="2026-11-12T10:00:00+01:00",
        first_name="Ospite", phone="+39 347 5550000", operator_ids=pool))
    return next(a for a in coordinator.appointments if a["id"] == booked["id"])


def _to(sent, operator):
    digits = "".join(ch for ch in operator["phone"] if ch.isdigit())
    return [item["message"] for item in sent if digits in str(item.get("chat_id"))]


def test_offer_goes_to_the_first_and_waits(coordinator, sent, freeze) -> None:
    freeze("2026-11-10 08:00")
    maria, giulia = _setup(coordinator)
    appointment = _book(coordinator, [giulia, maria])
    assert appointment["operator_id"] == maria and appointment["offer_state"] == "offered"
    assert appointment["offer_expires_at"]
    assert _to(sent, coordinator.operators[0]), "Maria is asked on WhatsApp"
    assert not _to(sent, coordinator.operators[1])


def test_refusal_passes_to_the_next(coordinator, sent, freeze) -> None:
    freeze("2026-11-10 08:00")
    maria, giulia = _setup(coordinator)
    appointment = _book(coordinator, [maria, giulia])
    sent.clear()
    result = run(coordinator.async_answer_offer(appointment["id"], "decline", operator_id=maria))
    assert result["handled"]
    assert appointment["operator_id"] == giulia and appointment["offer_state"] == "offered"
    assert _to(sent, coordinator.operators[1]), "Giulia gets the offer"
    run(coordinator.async_answer_offer(appointment["id"], "confirm", operator_id=giulia))
    assert appointment["offer_state"] == "" and appointment["operator_id"] == giulia


def test_no_answer_reminds_then_moves_on(coordinator, sent, freeze) -> None:
    freeze("2026-11-10 08:00")
    maria, giulia = _setup(coordinator, timeout=2, reminder=1)
    appointment = _book(coordinator, [maria, giulia])
    sent.clear()
    freeze("2026-11-10 09:10")  # one hour left: reminder
    assert run(coordinator.async_expire_offers())["reminded"] == 1
    assert any("Promemoria" in text for text in _to(sent, coordinator.operators[0]))
    freeze("2026-11-10 10:05")  # deadline passed: next one
    assert run(coordinator.async_expire_offers())["expired"] == 1
    assert appointment["operator_id"] == giulia


def test_everybody_refuses_and_the_desk_is_told(coordinator, sent, freeze) -> None:
    freeze("2026-11-10 08:00")
    maria, giulia = _setup(coordinator)
    coordinator._data["settings"]["web_notify_whatsapp"] = "+39 0925 992446"
    appointment = _book(coordinator, [maria, giulia])
    run(coordinator.async_answer_offer(appointment["id"], "decline", operator_id=maria))
    run(coordinator.async_answer_offer(appointment["id"], "decline", operator_id=giulia))
    assert appointment["offer_state"] == "unassigned" and appointment["operator_id"] is None
    assert any("Nessuna massaggiatrice ha accettato" in item["message"] and "0925992446" in item["chat_id"].replace(" ", "") for item in sent), sent[-1]

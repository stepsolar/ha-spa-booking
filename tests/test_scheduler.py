"""The internal timers: what runs when, and that nothing is sent twice."""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from custom_components.spa_booking.const import KEY_SETTINGS, KEY_VOUCHERS
from custom_components.spa_booking.normalize import _norm_voucher
from custom_components.spa_booking.scheduler import SpaBookingScheduler, in_quiet_hours

from .conftest import run

ROME = ZoneInfo("Europe/Rome")


def _at(value: str) -> datetime:
    return datetime.fromisoformat(value).replace(tzinfo=ROME)


def test_quiet_hours_span_midnight() -> None:
    assert in_quiet_hours(_at("2026-11-10 22:00"), "21:00", "08:00")
    assert in_quiet_hours(_at("2026-11-10 03:00"), "21:00", "08:00")
    assert not in_quiet_hours(_at("2026-11-10 08:00"), "21:00", "08:00")
    assert not in_quiet_hours(_at("2026-11-10 12:00"), "21:00", "08:00")


def test_quiet_hours_same_day_and_disabled() -> None:
    assert in_quiet_hours(_at("2026-11-10 13:30"), "13:00", "15:00")
    assert not in_quiet_hours(_at("2026-11-10 16:00"), "13:00", "15:00")
    assert not in_quiet_hours(_at("2026-11-10 03:00"), "00:00", "00:00")


def test_guest_jobs_skipped_in_quiet_hours(coordinator, sent, freeze) -> None:
    freeze("2026-11-10 23:00")
    scheduler = SpaBookingScheduler(coordinator.hass, coordinator)
    result = run(scheduler.async_run(_at("2026-11-10 23:00")))
    assert "offers" in result
    assert result["guest_messages"] == "orario di silenzio"
    assert "reminders" not in result


def test_periodic_jobs_only_every_interval(coordinator, sent, freeze) -> None:
    freeze("2026-11-10 10:03")
    scheduler = SpaBookingScheduler(coordinator.hass, coordinator)
    result = run(scheduler.async_run(_at("2026-11-10 10:03")))
    assert set(result) == {"promo"}
    result = run(scheduler.async_run(_at("2026-11-10 10:05")))
    assert {"offers", "reminders", "reviews", "promo_vouchers", "voucher_expiry"} <= set(result)


def test_failing_job_does_not_stop_others(coordinator, sent, freeze, monkeypatch) -> None:
    freeze("2026-11-10 10:05")

    async def boom():
        raise RuntimeError("rotto")

    monkeypatch.setattr(coordinator, "async_expire_offers", boom)
    scheduler = SpaBookingScheduler(coordinator.hass, coordinator)
    result = run(scheduler.async_run(_at("2026-11-10 10:05")))
    assert result["offers"] == {"error": True}
    assert "reminders" in result


def test_monthly_report_once_on_the_first(coordinator, sent, freeze, monkeypatch) -> None:
    calls: list[str | None] = []

    async def fake_report(month=None):
        calls.append(month)
        return {"results": []}

    monkeypatch.setattr(coordinator, "async_send_monthly_report", fake_report)
    coordinator._data[KEY_SETTINGS]["report_time"] = "08:00"

    freeze("2026-12-01 07:55")
    assert run(coordinator.async_monthly_report_tick())["sent"] is False
    freeze("2026-12-01 08:10")
    assert run(coordinator.async_monthly_report_tick())["sent"] is True
    freeze("2026-12-01 08:15")
    assert run(coordinator.async_monthly_report_tick())["sent"] is False
    freeze("2026-12-02 08:10")
    assert run(coordinator.async_monthly_report_tick())["sent"] is False
    assert calls == ["2026-11"]


def test_daily_promo_once_and_only_near_its_time(coordinator, sent, freeze, monkeypatch) -> None:
    sends: list[int] = []

    async def fake_send(*args, **kwargs):
        sends.append(1)
        return {"sent": 1, "total": 1}

    monkeypatch.setattr(coordinator, "async_send_promo", fake_send)
    coordinator._data[KEY_SETTINGS]["promos"] = [
        {"id": "p1", "name": "Ogni giorno", "mode": "ogni", "time": "10:00", "message": "Ciao"}
    ]

    freeze("2026-11-10 09:59")
    run(coordinator.async_scheduled_promo())
    freeze("2026-11-10 10:01")
    run(coordinator.async_scheduled_promo())
    freeze("2026-11-10 10:02")
    run(coordinator.async_scheduled_promo())
    assert len(sends) == 1
    freeze("2026-11-11 15:00")  # hours late: no surprise afternoon promo
    run(coordinator.async_scheduled_promo())
    assert len(sends) == 1


def _voucher(expires_on: str, **extra) -> dict:
    return _norm_voucher(
        {
            "id": "v1",
            "code": "VCH-AAAA2222",
            "recipient_name": "Anna Rossi",
            "recipient_phone": "392 1234567",
            "people": [
                {"name": "Anna", "treatment_ids": ["trt_massaggio_relax_90"]},
                {"name": "Luca", "treatment_ids": ["trt_ingresso_90"]},
            ],
            "expires_on": expires_on,
            "status": "active",
            **extra,
        }
    )


def test_voucher_expiry_reminder_sent_once(coordinator, sent, freeze) -> None:
    freeze("2026-11-10 10:00")
    coordinator._data[KEY_VOUCHERS] = [_voucher("2026-12-20")]
    result = run(coordinator.async_send_voucher_expiry_reminders())
    assert result == {"sent": 1, "failed": 0}
    assert len(sent) == 1  # one message per voucher, not per person
    assert sent[0]["chat_id"] == "393921234567@c.us"
    assert "VCH-AAAA2222" in sent[0]["message"]
    assert "Anna" in sent[0]["message"]
    run(coordinator.async_send_voucher_expiry_reminders())
    assert len(sent) == 1


def test_voucher_expiry_lists_treatment_names(coordinator, sent, freeze) -> None:
    freeze("2026-11-10 10:00")
    coordinator._data[KEY_SETTINGS]["voucher_expiry_reminder_message"] = "{trattamenti}"
    coordinator._data[KEY_VOUCHERS] = [_voucher("2026-12-20")]
    run(coordinator.async_send_voucher_expiry_reminders())
    assert sent[0]["message"] == "Massaggio Relax 90 min, Ingresso Spa 90 min"


def test_voucher_expiry_flag_survives_reload(coordinator) -> None:
    voucher = _voucher("2026-12-20", expiry_reminder_sent=True)
    assert voucher["expiry_reminder_sent"] is True


def test_voucher_expiry_skips_expired_and_far(coordinator, sent, freeze) -> None:
    freeze("2026-11-10 10:00")
    coordinator._data[KEY_VOUCHERS] = [_voucher("2026-11-01"), {**_voucher("2027-06-01"), "id": "v2"}]
    assert run(coordinator.async_send_voucher_expiry_reminders())["sent"] == 0
    assert not sent


def _confirmed_booking(coordinator, start, phone="333 1234567"):
    maria = coordinator.operators[0]["id"]
    booked = run(
        coordinator.async_create_appointment(
            treatment_id="trt_massaggio_relax_90",
            start=start,
            first_name="Anna",
            phone=phone,
            operator_ids=[maria],
        )
    )
    for appointment in coordinator.appointments:
        if appointment["id"] == booked["id"]:
            appointment["status"] = "confirmed"
    return booked


def test_reminder_sent_once(coordinator, sent, freeze) -> None:
    freeze("2026-11-10 10:00")
    _confirmed_booking(coordinator, "2026-11-11 09:00")
    assert run(coordinator.async_send_reminders())["sent"] == 1
    assert run(coordinator.async_send_reminders())["sent"] == 0
    assert len(sent) == 1


def test_review_request_retried_after_failure(coordinator, sent, freeze, monkeypatch) -> None:
    from custom_components.spa_booking import messaging

    freeze("2026-11-10 08:00")
    _confirmed_booking(coordinator, "2026-11-10 09:00")
    freeze("2026-11-10 17:00")  # ended 10:30, asked after 6 hours

    async def failing(hass, chat_id, message, blocking=True, waha=None):
        return {"sent": False, "error": "telefono spento"}

    monkeypatch.setattr(messaging, "async_send_whatsapp", failing)
    assert run(coordinator.async_send_review_requests())["failed"] == 1
    assert not coordinator.appointments[0]["review_request_sent"]

    async def working(hass, chat_id, message, blocking=True, waha=None):
        sent.append(chat_id)
        return {"sent": True}

    monkeypatch.setattr(messaging, "async_send_whatsapp", working)
    assert run(coordinator.async_send_review_requests())["sent"] == 1
    assert coordinator.appointments[0]["review_request_sent"]


def test_fresh_install_has_every_collection() -> None:
    from custom_components.spa_booking.const import KEY_PROMO_VOUCHERS
    from custom_components.spa_booking.normalize import default_data

    data = default_data(["Maria"])
    assert data[KEY_VOUCHERS] == []
    assert data[KEY_PROMO_VOUCHERS] == []


def test_reminder_manual_mode_and_sent_time(coordinator, sent, freeze) -> None:
    freeze("2026-11-10 10:00")
    coordinator._data["settings"]["appointment_reminder_auto"] = False
    _confirmed_booking(coordinator, "2026-11-11 09:00")
    # The timer sends nothing in manual mode; the desk's button does.
    assert run(coordinator.async_send_reminders())["sent"] == 0
    assert run(coordinator.async_send_reminders(manual=True))["sent"] == 1
    assert coordinator.appointments[0]["reminder_sent_at"].startswith("2026-11-10")
    # Resent for one appointment on purpose.
    assert run(coordinator.async_send_reminders(coordinator.appointments[0]["id"]))["sent"] == 1


def test_confirmation_remembers_when_it_went_out(coordinator, sent, freeze) -> None:
    freeze("2026-11-10 10:00")
    _confirmed_booking(coordinator, "2026-11-11 09:00")
    appointment = coordinator.appointments[0]
    assert appointment["confirmation_sent_at"] == ""
    assert run(coordinator.async_send_guest_summary(appointment["id"]))["sent"]
    assert appointment["confirmation_sent_at"].startswith("2026-11-10")


def test_web_notice_to_several_numbers(coordinator, sent) -> None:
    from custom_components.spa_booking.coordinator import notify_numbers

    assert notify_numbers("+39 333 1\n+39 347 2; +41 79 3") == ["+39 333 1", "+39 347 2", "+41 79 3"]
    coordinator._data["settings"]["web_notify_whatsapp"] = "+39 333 1111111\n+39 347 2222222"
    result = run(coordinator.async_test_web_notice())
    assert result == {"sent": 2, "numbers": 2} and len(sent) == 2


def test_promo_counted_on_the_client(coordinator, sent, freeze) -> None:
    freeze("2026-11-10 10:00")
    _confirmed_booking(coordinator, "2026-11-11 09:00")
    client = coordinator.clients[-1]
    coordinator._data["settings"].update({"promo_interval_sec": 0, "promo_max_sends": 0, "promo_message": "Ciao {nome}"})
    assert run(coordinator.async_send_promo([client["id"]]))["sent"] == 1
    run(coordinator.async_send_promo([client["id"]]))
    assert client["promo_sent_count"] == 2
    assert client["promo_last_sent_at"].startswith("2026-11-10")


def _party(coordinator):
    """Anna and her friend, two massages at the same time (2.3.5)."""
    maria, giulia = coordinator.operators[0]["id"], coordinator.operators[1]["id"]
    first = _confirmed_booking(coordinator, "2026-11-11 09:00")
    second = run(coordinator.async_create_appointment(
        treatment_id="trt_massaggio_relax_90", start="2026-11-11 09:00",
        client_id=first["client_id"], operator_ids=[giulia], force_client_overlap=True,
    ))
    for appointment in coordinator.appointments:
        if appointment["id"] == second["id"]:
            appointment["status"] = "confirmed"
            appointment["person"] = 1
    assert maria != giulia
    return first, second


def test_party_summary_is_one_message(coordinator, sent, freeze) -> None:
    freeze("2026-11-10 10:00")
    first, second = _party(coordinator)
    run(coordinator.async_send_guest_summary(appointment_ids=[first["id"], second["id"]]))
    assert len(sent) == 1
    text = sent[0][1] if isinstance(sent[0], tuple) else str(sent[0])
    assert text.count("Gentile Anna") == 1
    assert "Persona 1" in text and "Persona 2" in text
    assert "mercoledì 11 novembre" in text


def test_party_reminder_is_one_message(coordinator, sent, freeze) -> None:
    freeze("2026-11-10 10:00")
    first, _second = _party(coordinator)
    assert run(coordinator.async_send_reminders())["sent"] == 1
    text = sent[0][1] if isinstance(sent[0], tuple) else str(sent[0])
    assert text.count("Le ricordiamo") == 1 and "Persona 2" in text
    # The desk's button for one of them also reminds the whole party at once.
    sent.clear()
    assert run(coordinator.async_send_reminders(first["id"]))["sent"] == 1


def test_old_default_texts_are_upgraded() -> None:
    from custom_components.spa_booking.const import (
        DEFAULT_SUMMARY_MESSAGE, LEGACY_SUMMARY_MESSAGE, LEGACY_DEPOSIT_MESSAGE, DEFAULT_DEPOSIT_MESSAGE,
    )
    from custom_components.spa_booking.normalize import _norm_settings

    settings = _norm_settings({"summary_message": LEGACY_SUMMARY_MESSAGE, "deposit_message": LEGACY_DEPOSIT_MESSAGE})
    assert settings["summary_message"] == DEFAULT_SUMMARY_MESSAGE
    assert settings["deposit_message"] == DEFAULT_DEPOSIT_MESSAGE
    assert _norm_settings({"summary_message": "Ciao {nome}"})["summary_message"] == "Ciao {nome}"


def test_old_single_promo_becomes_the_first_saved_one() -> None:
    from custom_components.spa_booking.normalize import _norm_settings

    settings = _norm_settings(
        {"promo_message": "Ciao {nome}", "promo_code": "ESTATE20", "promo_time": "9.30",
         "promo_date": "2026-12-01", "promo_expiry": "2026-12-31"}
    )
    (promo,) = settings["promos"]
    assert promo["mode"] == "giorno" and promo["date"] == "2026-12-01" and promo["time"] == "09:30"
    assert promo["code"] == "ESTATE20" and promo["message"] == "Ciao {nome}"
    assert _norm_settings({})["promos"] == []
    # Once saved as a list, the list is the truth (even an empty one).
    assert _norm_settings({"promos": [], "promo_time": "10:00"})["promos"] == []


def test_saved_promos_each_on_their_day(coordinator, sent, freeze) -> None:
    freeze("2026-11-10 08:00")
    _confirmed_booking(coordinator, "2026-11-11 09:00")
    coordinator._data["settings"].update({"promo_interval_sec": 0, "promo_max_sends": 0})
    run(coordinator.async_update_settings(promos=[
        {"id": "natale", "name": "Natale", "mode": "giorno", "date": "2026-12-01",
         "time": "10:00", "code": "NATALE26", "expiry": "2027-01-06",
         "message": "Buon Natale {nome}: {codice_promo} entro {scadenza_promo}"},
        {"id": "bf", "name": "Black Friday", "mode": "giorno", "date": "2026-11-27",
         "time": "09:00", "message": "Black Friday {nome}", "sent_count": 99},
        {"id": "mano", "name": "A mano", "message": "x"},
    ]))
    promos = coordinator._data["settings"]["promos"]
    assert promos[1]["sent_count"] == 0  # the card cannot write the counters
    freeze("2026-11-27 09:10")
    result = run(coordinator.async_scheduled_promo())
    assert set(result["promos"]) == {"bf"} and len(sent) == 1
    run(coordinator.async_scheduled_promo())
    assert len(sent) == 1  # once only
    freeze("2026-12-01 10:05")
    run(coordinator.async_scheduled_promo())
    assert len(sent) == 2
    assert "NATALE26 entro 06/01/2027" in str(sent[-1])
    bf = coordinator._promo_by_id("bf")
    assert bf["sent_count"] == 1 and bf["last_sent_on"] == "2026-11-27"
    # Moving a sent one-off promo to another day lets it go again.
    run(coordinator.async_update_settings(promos=[dict(p, date="2026-12-05") if p["id"] == "bf" else p for p in promos]))
    assert coordinator._promo_by_id("bf")["last_sent_on"] == ""
    assert coordinator._promo_by_id("bf")["sent_count"] == 1


def test_send_one_saved_promo_by_hand(coordinator, sent, freeze) -> None:
    freeze("2026-11-10 08:00")
    _confirmed_booking(coordinator, "2026-11-11 09:00")
    coordinator._data["settings"].update({"promo_interval_sec": 0, "promo_max_sends": 0})
    run(coordinator.async_update_settings(promos=[
        {"id": "w", "name": "Weekend", "code": "RELAX", "expiry": "2026-11-09", "message": "{codice_promo}"},
        {"id": "v", "name": "Valida", "code": "RELAX", "message": "Codice {codice_promo}"},
    ]))
    import pytest
    from custom_components.spa_booking.exceptions import ValidationError

    with pytest.raises(ValidationError):
        run(coordinator.async_send_promo(promo_id="w"))  # expired yesterday
    assert run(coordinator.async_send_promo(promo_id="v"))["sent"] == 1
    assert "Codice RELAX" in str(sent[-1])

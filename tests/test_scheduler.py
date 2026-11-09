"""The internal timers: what runs when, and that nothing is sent twice."""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from custom_components.spa_booking.const import KEY_SETTINGS, KEY_VOUCHERS
from custom_components.spa_booking.coordinator import _norm_voucher
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
    coordinator._data[KEY_SETTINGS]["promo_time"] = "10:00"

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

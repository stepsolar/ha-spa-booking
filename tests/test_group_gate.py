"""2.9.0: a group leaves with one loyalty voucher and is asked one review."""

from __future__ import annotations

from custom_components.spa_booking import messaging

from .conftest import run

SPA = "trt_ingresso_90"


def _group(coordinator):
    booked = run(coordinator.async_create_bookings([{
        "treatment_id": SPA,
        "entries": [{"start": "2026-11-14T10:00:00", "first_name": "Anna", "phone": "347 1234567", "person": i}
                    for i in range(3)]}]))["appointments"]
    for b in booked:
        next(a for a in coordinator.appointments if a["id"] == b["id"])["status"] = "confirmed"
    return [b["id"] for b in booked]


def test_group_check_out_one_voucher(coordinator, freeze) -> None:
    freeze("2026-11-14 09:00")
    coordinator._data["settings"]["promo_voucher_auto"] = True
    ids = _group(coordinator)
    for item in ids:
        run(coordinator.async_check_in_appointment(item))
        run(coordinator.async_check_out_appointment(item))
    assert len([v for v in coordinator.promo_vouchers if v.get("appointment_id") in ids]) == 1


def test_review_button_asks_the_group_once(coordinator, freeze, monkeypatch) -> None:
    freeze("2026-11-14 09:00")
    sent = []

    async def fake(hass, chat_id, message, blocking=True, waha=None):
        sent.append(chat_id)
        return {"sent": True}

    monkeypatch.setattr(messaging, "async_send_whatsapp", fake)
    ids = _group(coordinator)
    result = run(coordinator.async_send_review_requests(ids[1]))
    assert result["sent"] == 1 and len(sent) == 1
    assert all(a["review_request_sent"] for a in coordinator.appointments if a["id"] in ids)

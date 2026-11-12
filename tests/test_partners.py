"""Partner bookings, points and email campaigns (2.5.0)."""

from __future__ import annotations

import pytest

from custom_components.spa_booking.exceptions import ValidationError

from .conftest import run


def _partner(coordinator, **extra):
    return run(coordinator.async_save_partner({"first_name": "Giulia", "company": "B&B Il Faro",
                                               "email": "faro@example.com", **extra}))["partner"]


def test_points_from_bookings_and_cancellation(coordinator, sent, freeze) -> None:
    freeze("2026-11-10 08:00")
    partner = _partner(coordinator)
    coordinator._data["settings"]["partner_points_per_euro"] = 0.5
    maria = coordinator.operators[0]["id"]
    booked = run(coordinator.async_create_appointment(
        treatment_id="trt_massaggio_relax_90", start="2026-11-11 09:00", first_name="Anna",
        phone="333 1234567", operator_ids=[maria], partner_id=partner["code"].lower(), price=80))
    stored = next(a for a in coordinator.appointments if a["id"] == booked["id"])
    assert stored["partner_id"] == partner["id"]
    assert coordinator.partner_points_of(partner) == {
        "earned": 40, "adjust": 0, "spent": 0, "balance": 40, "booked": 80.0, "bookings": 1}
    # A party through create_bookings, then the request path.
    run(coordinator.async_create_bookings([{
        "treatment_id": "trt_ingresso_90", "partner_id": partner["id"],
        "entries": [{"start": "2026-11-12 10:00", "first_name": "Luca", "phone": "333 7654321", "person": 0}],
    }]))
    assert coordinator.partner_points_of(partner)["bookings"] == 2
    # Cancelled: the points go with it.
    run(coordinator.async_cancel_appointment(booked["id"], "cambio programma"))
    info = coordinator.partner_points_of(partner)
    assert info["bookings"] == 1 and info["earned"] < 40
    run(coordinator.async_partner_points_adjust(partner["id"], 100, "Premio estate"))
    assert coordinator.partner_points_of(partner)["adjust"] == 100


def test_request_from_the_link_carries_the_partner(coordinator, sent, freeze) -> None:
    freeze("2026-11-10 08:00")
    partner = _partner(coordinator)
    request = run(coordinator.async_create_request(
        first_name="Sara", phone="333 1112223", date="2026-11-12",
        entries=[{"treatment_id": "trt_ingresso_90", "time": "10:00"}], partner=partner["code"]))
    stored = next(r for r in coordinator.requests if r["id"] == request["id"])
    assert stored["partner_id"] == partner["id"]
    assert coordinator._request_rows(stored)[0]["partner_id"] == partner["id"]
    # An unknown code is simply ignored.
    other = run(coordinator.async_create_request(
        first_name="Ugo", phone="333 9998887", date="2026-11-12",
        entries=[{"treatment_id": "trt_ingresso_90", "time": "11:00"}], partner="PRT-NONE"))
    assert next(r for r in coordinator.requests if r["id"] == other["id"])["partner_id"] == ""


def test_campaign_email(coordinator, monkeypatch, freeze) -> None:
    freeze("2026-11-10 08:00")
    partner = _partner(coordinator)
    _partner(coordinator, first_name="Marco", company="Palestra", email="")  # no email: skipped
    mails = []

    async def deliver(to, subject, body, html=None):
        mails.append((to, subject, body, html))
        return {"sent": True, "to": [to]}

    monkeypatch.setattr(coordinator, "_async_deliver_email", deliver)
    campaign = {"id": "c1", "name": "Natale", "subject": "Natale in spa per i tuoi ospiti, {nome}",
                "message": "Ciao {nome}, condividi {link_prenotazione}: {punti_per_euro} punti per euro.",
                "mode": "giorno", "date": "2026-11-12", "time": "10:00"}
    run(coordinator.async_update_settings(partner_campaigns=[campaign], partner_points_per_euro=1.5))
    with pytest.raises(ValidationError):  # email off
        run(coordinator.async_send_partner_campaign("c1"))
    coordinator._data["settings"]["email_enabled"] = True
    with pytest.raises(ValidationError):  # no booking page for the link
        run(coordinator.async_send_partner_campaign("c1"))
    coordinator._data["settings"]["partner_booking_url"] = "https://www.ilmarchese.it/spa/prenota"
    test = run(coordinator.async_send_partner_campaign("c1", "io@ilmarchese.it"))
    assert test["test"] and mails[-1][1].startswith("[PROVA]")
    # The start day: nothing before 10:00, once at 10:05.
    freeze("2026-11-12 09:50")
    run(coordinator.async_partner_campaign_tick())
    assert len(mails) == 1
    freeze("2026-11-12 10:05")
    result = run(coordinator.async_partner_campaign_tick())
    assert result["c1"]["sent"] == 1 and mails[-1][0] == "faro@example.com"
    to, subject, body, html = mails[-1]
    link = f"https://www.ilmarchese.it/spa/prenota?partner={partner['code']}"
    assert subject == "Natale in spa per i tuoi ospiti, Giulia" and link in body and "1,5 punti" in body
    assert f'<a href="{link}">' in html
    run(coordinator.async_partner_campaign_tick())
    assert len(mails) == 2  # once only
    stored = coordinator._data["settings"]["partner_campaigns"][0]
    assert stored["sent_count"] == 1 and stored["sent_at"]


def test_vat_rates(coordinator, sent, freeze) -> None:
    """VAT (2.5.1): default 22%, own rate per treatment, frozen on the booking."""
    freeze("2026-11-10 08:00")
    assert coordinator._data["settings"]["vat_default"] == 22.0
    massage = next(t for t in coordinator.treatments if t["id"] == "trt_massaggio_relax_90")
    assert coordinator.vat_rate_of(massage) == 22.0
    run(coordinator.async_update_treatment(massage["id"], vat_rate=10))
    assert coordinator.vat_rate_of(massage) == 10.0
    maria = coordinator.operators[0]["id"]
    booked = run(coordinator.async_create_appointment(
        treatment_id=massage["id"], start="2026-11-11 09:00", first_name="Anna",
        phone="333 1234567", operator_ids=[maria]))
    stored = next(a for a in coordinator.appointments if a["id"] == booked["id"])
    assert stored["vat_rate"] == 10.0
    # Back to the default: the booking keeps its rate.
    run(coordinator.async_update_treatment(massage["id"], vat_rate=-1))
    assert massage["vat_rate"] is None and coordinator.vat_rate_of(massage) == 22.0
    assert next(a for a in coordinator.appointments if a["id"] == booked["id"])["vat_rate"] == 10.0
    assert coordinator.vat_split(61.0, 22) == (50.0, 11.0)
    run(coordinator.async_update_settings(vat_default=10))
    assert coordinator.vat_rate_of(massage) == 10.0


def test_billing_data(coordinator) -> None:
    """Dati fatturazione (2.5.2): stored trimmed, empty by default."""
    assert coordinator._data["settings"]["billing_company"] == ""
    run(coordinator.async_update_settings(billing_company="  Il Marchese S.r.l. ", billing_vat_number="01234567890",
                                          billing_province="AG"))
    settings = coordinator._data["settings"]
    assert settings["billing_company"] == "Il Marchese S.r.l."
    assert settings["billing_vat_number"] == "01234567890" and settings["billing_province"] == "AG"

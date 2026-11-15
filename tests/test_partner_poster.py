"""The A5 poster of a partner (3.2.0): QR code, page and email."""

from __future__ import annotations

import pytest

from custom_components.spa_booking import poster as poster_mod, qr
from custom_components.spa_booking.exceptions import ValidationError

from .conftest import run


def _partner(coordinator, **extra):
    return run(coordinator.async_save_partner({"first_name": "Maria", "company": "B&B Villa Rosa",
                                               "email": "maria@villarosa.it", **extra}))["partner"]


def test_qr_code_round_trip() -> None:
    """The matrix has the size of its version and the finder patterns."""
    text = "https://benessere.example.it/percorso/?partner=PRT101"
    matrix = qr.qr_matrix(text)
    assert len(matrix) in (29, 33, 37)
    assert all(matrix[0][i] for i in range(7)) and all(matrix[i][0] for i in range(7))
    png = qr.qr_png(text, scale=4)
    assert png.startswith(b"\x89PNG") and b"IEND" in png
    try:
        import cv2  # noqa: PLC0415
        import numpy as np  # noqa: PLC0415
    except ImportError:
        return
    image = cv2.imdecode(np.frombuffer(png, dtype=np.uint8), cv2.IMREAD_COLOR)
    assert cv2.QRCodeDetector().detectAndDecode(image)[0] == text


def test_poster_page_and_email(coordinator, monkeypatch, freeze) -> None:
    freeze("2026-11-15 08:00")
    partner = _partner(coordinator, discount_pct=10)
    mails = []

    async def deliver(to, subject, body, html=None):
        mails.append((to, subject, body, html))
        return {"sent": True, "to": [to]}

    monkeypatch.setattr(coordinator, "_async_deliver_email", deliver)
    with pytest.raises(ValidationError):  # email off
        run(coordinator.async_send_partner_poster(partner["id"]))
    coordinator._data["settings"]["email_enabled"] = True
    with pytest.raises(ValidationError):  # no booking page for the QR code
        run(coordinator.async_send_partner_poster(partner["id"]))
    coordinator._data["settings"]["partner_booking_url"] = "https://benessere.example.it/percorso/"
    coordinator._data["settings"]["web_public_url"] = "https://ha.example.it"
    result = run(coordinator.async_send_partner_poster(partner["id"]))
    assert result["sent"] == 1
    to, subject, body, html = mails[-1]
    assert to == "maria@villarosa.it" and "Spa Sciacca" in subject
    token = poster_mod.poster_token(coordinator.partners[0])
    assert f"https://ha.example.it/api/spa_booking/partner/poster?k={token}" in html
    assert f"https://ha.example.it/api/spa_booking/partner/qr?k={token}" in html
    assert "sconto del <b" in html and "CODICE " + partner["code"] in html
    assert "partner=" + partner["code"] in body
    assert coordinator.partner_by_poster_token(token)["id"] == partner["id"]
    assert coordinator.partner_by_poster_token("x" * 24) is None
    page = coordinator.partner_poster_page(coordinator.partners[0])
    assert "Spa <b>Sciacca</b>" in page and "window.print()" in page and "<svg" in page
    assert "Marchese" not in page and "Marchese" not in html
    assert coordinator.partners[0]["campaigns_sent"] == 1
    # Unsubscribed: no poster.
    run(coordinator.async_save_partner({"id": partner["id"], "subscribed": False}))
    with pytest.raises(ValidationError):
        run(coordinator.async_send_partner_poster(partner["id"]))


def test_poster_texts_are_editable(coordinator) -> None:
    run(coordinator.async_update_settings(partner_poster={
        "title": "Spa del Borgo", "items": [{"icon": "pool", "title": "Piscina", "text": "calda"}, {"title": ""}],
        "prices": [{"label": "Ingresso", "price": "40 €"}, {"label": "senza prezzo"}]}))
    poster = coordinator.poster_settings()
    assert poster["title"] == "Spa del Borgo"
    assert [i["title"] for i in poster["items"]] == ["Piscina"]
    assert poster["prices"] == [{"label": "Ingresso", "price": "40 €"}]
    assert poster["footer"] == poster_mod.DEFAULT_POSTER["footer"]


def test_campaign_to_one_partner(coordinator, monkeypatch, freeze) -> None:
    freeze("2026-11-15 08:00")
    first = _partner(coordinator)
    _partner(coordinator, company="Hotel Aurora", email="aurora@example.it")
    mails = []

    async def deliver(to, subject, body, html=None):
        mails.append(to)
        return {"sent": True, "to": [to]}

    monkeypatch.setattr(coordinator, "_async_deliver_email", deliver)
    coordinator._data["settings"]["email_enabled"] = True
    run(coordinator.async_update_settings(partner_campaigns=[{"id": "c1", "name": "Natale", "subject": "Ciao", "message": "Buon Natale"}]))
    result = run(coordinator.async_send_partner_campaign("c1", partner_id=first["id"]))
    assert result["sent"] == 1 and mails == ["maria@villarosa.it"]
    assert not coordinator._data["settings"]["partner_campaigns"][0].get("sent_at")

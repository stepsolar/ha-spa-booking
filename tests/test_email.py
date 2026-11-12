"""Email sending through an SMTP mailbox (2.4.1)."""

from __future__ import annotations

import smtplib

import pytest

from custom_components.spa_booking import email_sender
from custom_components.spa_booking.exceptions import ValidationError

from .conftest import run


class _FakeSMTP:
    sent: list = []
    fail: Exception | None = None

    def __init__(self, host, port, timeout=None, context=None):
        self.host, self.port = host, port
        self.calls = []

    def ehlo(self):
        return None

    def starttls(self, context=None):
        self.calls.append("starttls")

    def login(self, user, password):
        if _FakeSMTP.fail:
            raise _FakeSMTP.fail
        self.calls.append(("login", user, password))

    def send_message(self, message):
        _FakeSMTP.sent.append((self.host, self.port, self.calls, message))

    def quit(self):
        return None


@pytest.fixture
def smtp(monkeypatch):
    _FakeSMTP.sent = []
    _FakeSMTP.fail = None
    monkeypatch.setattr(smtplib, "SMTP", _FakeSMTP)
    monkeypatch.setattr(smtplib, "SMTP_SSL", _FakeSMTP)
    return _FakeSMTP


def test_gmail_test_email(coordinator, smtp) -> None:
    run(coordinator.async_update_settings(
        email_enabled=True, smtp_provider="gmail", smtp_username="spa@gmail.com",
        smtp_password="abcd efgh ijkl mnop", email_from_name="Il Marchese Spa"))
    result = run(coordinator.async_test_email())
    assert result["sent"] and result["to"] == ["spa@gmail.com"]
    host, port, calls, message = smtp.sent[-1]
    assert (host, port) == ("smtp.gmail.com", 587) and calls[0] == "starttls"
    assert calls[1] == ("login", "spa@gmail.com", "abcdefghijklmnop")  # spaces dropped
    assert message["From"] == "Il Marchese Spa <spa@gmail.com>"
    # An empty password from the card keeps the saved one.
    run(coordinator.async_update_settings(smtp_password="", email_from_name="Spa"))
    assert coordinator._data["settings"]["smtp_password"] == "abcd efgh ijkl mnop"


def test_errors_in_words(coordinator, smtp) -> None:
    run(coordinator.async_update_settings(
        email_enabled=True, smtp_provider="gmail", smtp_username="spa@gmail.com", smtp_password="x"))
    smtp.fail = smtplib.SMTPAuthenticationError(535, b"bad")
    result = run(coordinator.async_test_email())
    assert not result["sent"] and "password per le app" in result["error"]
    # Aruba: SSL on 465.
    smtp.fail = None
    run(coordinator.async_update_settings(smtp_provider="aruba", smtp_username="info@hotel.it"))
    assert run(coordinator.async_send_email(["cliente@example.com"], "Ciao", "Testo"))["sent"]
    assert smtp.sent[-1][:2] == ("smtps.aruba.it", 465)
    assert email_sender.email_config(coordinator._data["settings"])["security"] == "ssl"


def test_off_by_default(coordinator, smtp) -> None:
    with pytest.raises(ValidationError):
        run(coordinator.async_send_email("a@b.it", "x", "y"))


def test_google_login_and_send(coordinator, monkeypatch) -> None:
    import base64
    import json
    from urllib.parse import parse_qs, urlparse

    from custom_components.spa_booking import google_auth

    calls = {}
    id_token = "x." + base64.urlsafe_b64encode(json.dumps({"email": "spa.marchese@gmail.com"}).encode()).decode().rstrip("=") + ".y"

    async def fake_exchange(session, cid, secret, code, redirect):
        calls["exchange"] = (cid, secret, code, redirect)
        return {"refresh_token": "R1", "access_token": "A1", "expires_in": 3600, "id_token": id_token,
                "scope": "openid email https://www.googleapis.com/auth/gmail.send"}

    async def fake_send(session, token, raw):
        calls.setdefault("sent", []).append((token, raw))
        return {"id": "m1"}

    async def fake_refresh(session, cid, secret, refresh):
        calls["refresh"] = refresh
        return "A2", 9e12

    async def fake_revoke(session, token):
        calls["revoked"] = token

    monkeypatch.setattr(google_auth, "exchange_code", fake_exchange)
    monkeypatch.setattr(google_auth, "gmail_send", fake_send)
    monkeypatch.setattr(google_auth, "refresh_access", fake_refresh)
    monkeypatch.setattr(google_auth, "revoke", fake_revoke)
    coordinator._http_session = lambda: None

    with pytest.raises(ValidationError):  # no client yet
        run(coordinator.async_google_auth_url("https://casa.example/api/spa_booking/google/callback"))
    run(coordinator.async_update_settings(email_enabled=True, google_client_id="CID.apps.googleusercontent.com",
                                          google_client_secret="SEC", email_aliases=["prenotazioni@ilmarchese.it"]))
    with pytest.raises(ValidationError):  # Google wants https
        run(coordinator.async_google_auth_url("http://192.168.1.5:8123/api/spa_booking/google/callback"))
    started = run(coordinator.async_google_auth_url("https://casa.example/api/spa_booking/google/callback"))
    query = parse_qs(urlparse(started["url"]).query)
    assert "gmail.send" in query["scope"][0] and query["access_type"] == ["offline"]
    # A forged state is refused; the real one links the account.
    with pytest.raises(google_auth.GoogleAuthError):
        run(coordinator.async_google_callback("forged", "C"))
    assert run(coordinator.async_google_callback(query["state"][0], "CODE")) == "spa.marchese@gmail.com"
    assert calls["exchange"][2:] == ("CODE", "https://casa.example/api/spa_booking/google/callback")
    settings = coordinator._data["settings"]
    assert settings["email_method"] == "google" and settings["google_refresh_token"] == "R1"
    # The state works once only.
    with pytest.raises(google_auth.GoogleAuthError):
        run(coordinator.async_google_callback(query["state"][0], "CODE"))
    # Sending from an «Invia messaggi come» address.
    run(coordinator.async_update_settings(email_from="prenotazioni@ilmarchese.it", email_from_name="Il Marchese Spa", google_client_secret=""))
    assert coordinator._data["settings"]["google_client_secret"] == "SEC"  # empty keeps it
    assert run(coordinator.async_send_email(["cliente@example.com"], "Conferma", "Ciao"))["sent"]
    token, raw = calls["sent"][-1]
    assert token == "A1" and b"From: Il Marchese Spa <prenotazioni@ilmarchese.it>" in raw
    assert run(coordinator.async_test_email())["to"] == ["prenotazioni@ilmarchese.it"]
    # An expired access token is refreshed.
    coordinator._google_access = ("old", 0)
    run(coordinator.async_send_email("cliente@example.com", "x", "y"))
    assert calls["refresh"] == "R1" and calls["sent"][-1][0] == "A2"
    run(coordinator.async_google_disconnect())
    assert calls["revoked"] == "R1" and coordinator._data["settings"]["google_refresh_token"] == ""
    assert not run(coordinator.async_send_email("cliente@example.com", "x", "y"))["sent"]

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

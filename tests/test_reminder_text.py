"""3.20.1: the reminder says what to bring; a stored older default gets it too."""

from __future__ import annotations

from custom_components.spa_booking.const import (
    APPOINTMENT_REMINDER_MESSAGE_2_3_5,
    DEFAULT_APPOINTMENT_REMINDER_MESSAGE,
    LEGACY_APPOINTMENT_REMINDER_MESSAGE,
)
from custom_components.spa_booking.normalize import _norm_settings


def test_what_to_bring() -> None:
    assert "Cosa portare: costume da bagno, cuffia e ciabattine antiscivolo (obbligatorie)" in DEFAULT_APPOINTMENT_REMINDER_MESSAGE
    assert "€ 3,00 ciascuna" in DEFAULT_APPOINTMENT_REMINDER_MESSAGE


def test_old_defaults_upgraded_own_text_kept() -> None:
    for old in ("", APPOINTMENT_REMINDER_MESSAGE_2_3_5, LEGACY_APPOINTMENT_REMINDER_MESSAGE):
        assert _norm_settings({"appointment_reminder_message": old})["appointment_reminder_message"] == DEFAULT_APPOINTMENT_REMINDER_MESSAGE
    assert _norm_settings({"appointment_reminder_message": "Mio testo"})["appointment_reminder_message"] == "Mio testo"

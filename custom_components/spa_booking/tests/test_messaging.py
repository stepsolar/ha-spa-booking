"""Tests for the messaging helpers that need no Home Assistant beyond
``HomeAssistant`` itself: answer parsing and text chunking."""

from __future__ import annotations

from unittest.mock import MagicMock


def import_messaging():
    from custom_components.spa_booking import messaging

    return messaging


def test_parse_reaction_confirm():
    m = import_messaging()
    assert m.parse_reaction("✅") == "confirm"
    assert m.parse_reaction("👍") == "confirm"


def test_parse_reaction_unknown():
    m = import_messaging()
    assert m.parse_reaction("😀") is None
    assert m.parse_reaction("") is None


def test_parse_answer_confermo():
    m = import_messaging()
    assert m.parse_answer("confermo") == "confirm"


def test_parse_answer_decline():
    m = import_messaging()
    assert m.parse_answer("no") == "decline"


def test_parse_answer_available():
    m = import_messaging()
    assert m.parse_answer("disponibile") == "available"


def test_chunk_text_short():
    m = import_messaging()
    assert m.chunk_text("short", 100) == ["short"]


def test_chunk_text_splits():
    m = import_messaging()
    chunks = m.chunk_text("a" * 100 + "\nb" * 100, 50)
    assert all(len(c) <= 50 or "\n" not in c for c in chunks)
    assert len(chunks) > 1


def test_whatsapp_chat_id_italian():
    m = import_messaging()
    assert m.whatsapp_chat_id("3331234567", "") == "393331234567@c.us"
    assert m.whatsapp_chat_id("3331234567", "399999@c.us") == "399999@c.us"
PY
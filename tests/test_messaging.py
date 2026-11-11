"""Tests for the messaging helpers that need no Home Assistant beyond
``HomeAssistant`` itself: answer parsing and text chunking."""

from __future__ import annotations



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
    assert m.parse_answer("disponibile") == "available_again"


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


def test_international_digits_tim_landline_foreign():
    m = import_messaging()
    assert m.international_digits("392 1234567") == "393921234567"
    assert m.international_digits("+39 392 1234567") == "393921234567"
    assert m.international_digits("0039 333 1234567") == "393331234567"
    assert m.international_digits("0925 992446") == "390925992446"
    assert m.international_digits("+49 151 23456789") == "4915123456789"


def test_negated_confirmation_is_a_refusal():
    m = import_messaging()
    assert m.parse_answer("non confermo") == "decline"
    assert m.parse_answer("Non va bene") == "decline"
    assert m.parse_answer("non accetto!") == "decline"
    assert m.parse_answer("va bene, grazie mille a te") == "confirm"


def test_lid_is_never_matched_by_digits():
    m = import_messaging()
    operators = [{"id": "o1", "name": "Maria", "phone": "333 1234567"}]
    assert m.find_operator_by_chat(operators, "whatsapp", "393331234567@lid") is None
    assert m.find_operator_by_chat(operators, "whatsapp", "393331234567@c.us")["id"] == "o1"


def test_operator_chat_id_migration():
    from custom_components.spa_booking.normalize import default_data

    from .conftest import build_coordinator

    coordinator = build_coordinator(default_data(["Maria", "Giulia"]))
    maria, giulia = coordinator.operators
    maria.update(phone="392 1234567", whatsapp_chat_id="3921234567@c.us")  # old wrong rule
    giulia.update(phone="392 7654321", whatsapp_chat_id="120363@g.us")  # typed: a group
    assert coordinator._migrate_operator_chat_ids() is True
    assert maria["whatsapp_chat_id"] == "393921234567@c.us"
    assert giulia["whatsapp_chat_id"] == "120363@g.us"
    assert coordinator._migrate_operator_chat_ids() is False


def test_whatsapp_chats_survive_and_are_deleted_by_hand() -> None:
    """2.3.5: conversations are stored on disk and deleted only on purpose."""

    from tests.conftest import build_coordinator

    coordinator = build_coordinator()
    from tests.conftest import run as go

    go(coordinator.async_add_external_message("39333@c.us", "Buongiorno, avete posto sabato?"))
    go(coordinator.async_add_external_message("39444@c.us", "Info prezzi"))
    saved = coordinator._chats_store.saved
    assert set(saved["chats"]) == {"39333@c.us", "39444@c.us"}

    # A restart: a new coordinator reads the same file back.
    again = build_coordinator()
    async def load():
        return saved
    again._chats_store.async_load = load
    go(again._async_load_chats())
    assert [c["chat_id"] for c in again.whatsapp_chats()] == ["39444@c.us", "39333@c.us"]
    assert again.external_messages[0]["text"] == "Info prezzi"

    assert go(again.async_delete_chats("39444@c.us")) == 1
    assert [c["chat_id"] for c in again.whatsapp_chats()] == ["39333@c.us"]
    assert go(again.async_delete_chats()) == 1 and again.whatsapp_chats() == []

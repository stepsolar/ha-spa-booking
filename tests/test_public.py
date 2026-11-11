"""The website API: rate limiting and what a voucher lookup reveals."""

from __future__ import annotations

from datetime import date

import pytest

from custom_components.spa_booking.const import KEY_CATEGORIES, KEY_SETTINGS
from custom_components.spa_booking.normalize import default_data
from custom_components.spa_booking.public import RateLimiter

from .conftest import build_coordinator, run

MASSAGE = "trt_massaggio_relax_90"


def test_rate_limiter_blocks_then_recovers() -> None:
    limiter = RateLimiter({"voucher": 3}, window=60)
    assert all(limiter.allow("voucher", "1.2.3.4", now=t) for t in (0, 1, 2))
    assert not limiter.allow("voucher", "1.2.3.4", now=3)
    assert limiter.allow("voucher", "5.6.7.8", now=3)  # another address
    assert limiter.allow("voucher", "1.2.3.4", now=61)  # window moved on


def test_rate_limiter_kinds_are_separate() -> None:
    limiter = RateLimiter({"voucher": 1, "read": 1}, window=60)
    assert limiter.allow("voucher", "a", now=0)
    assert limiter.allow("read", "a", now=0)
    assert not limiter.allow("voucher", "a", now=1)


@pytest.fixture
def web(freeze, sent):
    freeze("2026-11-10 08:00")
    coordinator = build_coordinator(default_data(["Maria"]))  # one masseuse
    coordinator._data[KEY_SETTINGS].update(web_enabled=True, web_token="t")
    return coordinator, date(2026, 11, 12)


def _times(result):
    return [slot["time"] for slot in result["slots"]]


def test_one_operator_cannot_be_promised_twice(web) -> None:
    coordinator, day = web
    first = run(coordinator.async_public_availability(day, MASSAGE))
    assert "10:00" in _times(first)
    planned = [coordinator.plan_public_entry(day, MASSAGE, "10:00", [])]
    second = run(coordinator.async_public_availability(day, MASSAGE, planned))
    assert "10:00" not in _times(second)


def test_site_respects_category_windows(web) -> None:
    coordinator, day = web
    for category in coordinator._data[KEY_CATEGORIES]:
        if category["id"] == "cat_massaggi":
            category.update(morning_start="09:00", morning_end="13:00")
    times = _times(run(coordinator.async_public_availability(day, MASSAGE)))
    assert "10:00" in times
    assert "15:00" not in times  # the desk would refuse it


def test_web_request_books_each_person_once(web) -> None:
    coordinator, day = web
    coordinator._data[KEY_SETTINGS]["web_enabled"] = True
    result = run(
        coordinator.async_create_request(
            first_name="Anna",
            phone="392 1234567",
            date=day.isoformat(),
            people=2,
            entries=[
                {"treatment_id": MASSAGE, "time": "10:00", "person": 0},
                {"treatment_id": "trt_ingresso_90", "time": "10:00", "person": 1},
                {"treatment_id": "trt_ingresso_90", "time": "12:00", "person": 0},
            ],
            source="web",
        )
    )
    request_id = next(r["id"] for r in coordinator.requests if r["code"] == result["code"])
    confirmed = run(coordinator.async_confirm_request(request_id))
    assert confirmed["count"] == 3  # not 3 entries x 2 people


def test_desk_request_still_books_every_person(web) -> None:
    coordinator, day = web
    result = run(
        coordinator.async_create_request(
            first_name="Luca",
            phone="333 7654321",
            date=day.isoformat(),
            people=2,
            entries=[{"treatment_id": "trt_ingresso_90", "time": "15:00"}],
        )
    )
    request_id = next(r["id"] for r in coordinator.requests if r["code"] == result["code"])
    assert run(coordinator.async_confirm_request(request_id))["count"] == 2


def test_editing_a_request_rewrites_it(web, sent) -> None:
    coordinator, day = web
    first = run(
        coordinator.async_create_request(
            first_name="Anna", phone="392 1234567", date=day.isoformat(),
            entries=[{"treatment_id": MASSAGE, "time": "10:00"}],
        )
    )
    acknowledgements = len(sent)
    original = next(r for r in coordinator.requests if r["code"] == first["code"])
    edited = run(
        coordinator.async_create_request(
            first_name="Anna", phone="392 1234567", date=day.isoformat(), people=2,
            entries=[
                {"treatment_id": MASSAGE, "time": "10:00", "person": 0},
                {"treatment_id": "trt_ingresso_90", "time": "11:00", "person": 1},
            ],
            request_id=original["id"],
        )
    )
    assert len(coordinator.requests) == 1  # no duplicate left behind
    assert edited["code"] == first["code"]
    assert coordinator.requests[0]["people"] == 2
    assert len(sent) == acknowledgements  # the guest is not messaged again


def test_confirmed_request_cannot_be_rewritten(web) -> None:
    from custom_components.spa_booking.exceptions import ValidationError

    coordinator, day = web
    first = run(
        coordinator.async_create_request(
            first_name="Anna", phone="392 1234567", date=day.isoformat(),
            entries=[{"treatment_id": MASSAGE, "time": "10:00"}],
        )
    )
    request_id = coordinator.requests[0]["id"]
    run(coordinator.async_confirm_request(request_id))
    with pytest.raises(ValidationError):
        run(
            coordinator.async_create_request(
                first_name="Anna", phone="392 1234567", date=day.isoformat(),
                entries=[{"treatment_id": MASSAGE, "time": "12:00"}],
                request_id=request_id,
            )
        )
    assert first["code"]


def test_two_line_code_loads_the_form_from_home_assistant(web) -> None:
    coordinator, _ = web
    result = run(coordinator.async_web_snippet("http://192.168.1.10:8123"))
    short = result["snippet"]
    # No public address set: the one already written in the full form wins
    # over the local address the desk happens to use.
    assert short.count("\n") == 1
    assert 'src="https://hailmarchese.it/api/spa_booking/public/form.js"' in short
    assert 'data-token="t"' in short
    assert "INCOLLA_QUI_IL_TOKEN" not in result["snippet_full"]
    coordinator._data[KEY_SETTINGS]["web_public_url"] = "https://spa.example.org"
    short = run(coordinator.async_web_snippet())["snippet"]
    assert 'src="https://spa.example.org/api/spa_booking/public/form.js"' in short


def test_form_file_is_served_with_an_etag() -> None:
    from custom_components.spa_booking.public import FORM_JS_FILE, SpaBookingPublicFormView

    body, etag = SpaBookingPublicFormView._read()
    assert FORM_JS_FILE.name == "spa-booking-form.js"
    assert "spa_booking/public/form.js" in body and etag.startswith('"')
    assert SpaBookingPublicFormView._read()[1] == etag


def test_update_fingerprint_separates_card_from_code(tmp_path) -> None:
    from types import SimpleNamespace

    from custom_components.spa_booking import updates

    (tmp_path / "frontend").mkdir()
    (tmp_path / "coordinator.py").write_text("A = 1\n")
    (tmp_path / "manifest.json").write_text('{"version": "2.2.0b4"}')
    (tmp_path / "frontend" / "spa-booking-card.js").write_text("// v1")
    first = updates.code_fingerprint(tmp_path)
    (tmp_path / "frontend" / "spa-booking-card.js").write_text("// v2")
    assert updates.code_fingerprint(tmp_path) == first  # card only: reload
    (tmp_path / "coordinator.py").write_text("A = 2\n")
    assert updates.code_fingerprint(tmp_path) != first  # code: restart
    assert updates.disk_version(tmp_path) == "2.2.0b4"
    states = [
        SimpleNamespace(entity_id="update.other", state="on", attributes={"title": "Altro"}),
        SimpleNamespace(entity_id="update.spa_booking_update", state="on", attributes={
            "release_url": "https://github.com/stepsolar/ha-spa-booking/releases/v2.2.0",
            "installed_version": "v2.2.0b4", "latest_version": "v2.2.0", "in_progress": False}),
    ]
    found = updates.find_update_entity(states)
    assert found["entity_id"] == "update.spa_booking_update" and found["available"]
    assert updates.find_update_entity(states[:1]) is None


def test_propose_another_date(web, monkeypatch) -> None:
    from custom_components.spa_booking import messaging

    coordinator, _ = web
    sent = []

    async def fake_send(hass, chat_id, text, waha=None):
        sent.append((chat_id, text))
        return {"sent": True}

    monkeypatch.setattr(messaging, "async_send_whatsapp", fake_send)
    treatment = coordinator.treatments[0]
    request = run(coordinator.async_create_request(
        first_name="Elena", last_name="Conti", phone="+39 347 222 3344",
        date="2026-11-14", people=1,
        entries=[{"treatment_id": treatment["id"], "time": "10:00"}],
    ))
    request = request.get("request", request)
    sent.clear()  # the acknowledgement of the new request
    preview = run(coordinator.async_propose_request_date(request["id"], "2026-11-15", "10:30", dry_run=True))
    text = preview["text"]
    assert text.startswith("Gentile Elena")
    assert "sabato 14 novembre" in text and "domenica 15 novembre alle 10:30" in text
    assert treatment["name"] in text
    assert not sent  # a preview sends nothing
    no_time = run(coordinator.async_propose_request_date(request["id"], "2026-11-15", "", dry_run=True))["text"]
    assert "domenica 15 novembre." in no_time
    result = run(coordinator.async_propose_request_date(
        request["id"], "2026-11-15", "10:30", "Testo cambiato", by_name="Laura"))
    assert sent == [("393472223344@c.us", "Testo cambiato")]
    assert result["request"]["proposed_date"] == "2026-11-15"
    assert result["request"]["proposed_time"] == "10:30"
    assert result["request"]["proposed_by"] == "Laura"


def test_propose_alternative_treatments(web, monkeypatch) -> None:
    from custom_components.spa_booking import messaging
    from custom_components.spa_booking.const import LEGACY_PROPOSE_MESSAGE
    from custom_components.spa_booking.normalize import _norm_settings as normalize_settings

    coordinator, _ = web
    sent = []

    async def fake_send(hass, chat_id, text, waha=None):
        sent.append((chat_id, text))
        return {"sent": True}

    monkeypatch.setattr(messaging, "async_send_whatsapp", fake_send)
    asked, other = coordinator.treatments[0], coordinator.treatments[1]
    request = run(coordinator.async_create_request(
        first_name="Elena", last_name="Conti", phone="+39 347 222 3344",
        date="2026-11-14", people=1,
        entries=[{"treatment_id": asked["id"], "time": "10:00"}],
    ))
    request = request.get("request", request)
    sent.clear()

    # Without alternatives the placeholder leaves no empty lines behind.
    plain = run(coordinator.async_propose_request_date(request["id"], "2026-11-15", "", dry_run=True))["text"]
    assert "{alternativa}" not in plain and "\n\n\n" not in plain
    assert "In alternativa" not in plain

    alts = [
        {"treatment_id": other["id"], "price": 160, "day": "asked"},
        {"treatment_id": asked["id"], "price": 89.5, "day": "proposed", "time": "11:00"},
    ]
    text = run(coordinator.async_propose_request_date(
        request["id"], "2026-11-15", "", alternatives=alts, dry_run=True))["text"]
    assert "In alternativa Le proponiamo:" in text
    assert f"• {other['name']}, sabato 14 novembre, al prezzo di € 160" in text
    assert f"• {asked['name']}, domenica 15 novembre alle 11:00, al prezzo di € 89,50" in text
    assert text.index("In alternativa") < text.index("Ci risponda")
    assert "\n\n\n" not in text

    # The list price when none is typed.
    listed = run(coordinator.async_propose_request_date(
        request["id"], "2026-11-15", "", alternatives=[{"treatment_id": other["id"]}], dry_run=True))
    assert listed["alternatives"][0]["price"] == other.get("price")

    result = run(coordinator.async_propose_request_date(
        request["id"], "2026-11-15", "", alternatives=alts))
    saved = result["request"]["proposed_alternatives"]
    assert [a["treatment_name"] for a in saved] == [other["name"], asked["name"]]
    assert saved[0]["date"] == "2026-11-14" and saved[0]["price"] == 160
    assert "€ 160" in sent[-1][1]

    # A text saved before 2.2.2 becomes the new default; a custom one keeps
    # its words and gets the alternatives before the goodbye.
    assert "{alternativa}" in normalize_settings({"request_propose_message": LEGACY_PROPOSE_MESSAGE})["request_propose_message"]
    coordinator._data["settings"]["request_propose_message"] = "Ciao {nome}, c'è posto {data_proposta}.\nCi risponda pure."
    custom = run(coordinator.async_propose_request_date(
        request["id"], "2026-11-15", "", alternatives=alts[:1], dry_run=True))["text"]
    assert custom.startswith("Ciao Elena, c'è posto domenica 15 novembre.\n\nIn alternativa")
    assert custom.endswith("Ci risponda pure.")


def test_closure_skips_weekdays(web) -> None:
    from custom_components.spa_booking.coordinator import SpaBookingCoordinator, skipped_days_words

    coordinator, _ = web
    closure = run(coordinator.async_add_closure(
        date_from="2026-11-01", date_to="2026-11-30", skip_weekdays=[5], label="Ferie"))
    assert closure["skip_weekdays"] == [5]
    days = SpaBookingCoordinator._closure_days(closure)
    assert "2026-11-07" not in days and "2026-11-14" not in days  # Saturdays stay open
    assert "2026-11-09" in days and "2026-11-15" in days
    assert len(days) == 30 - 4
    assert "esclusi i sabati" in SpaBookingCoordinator._closure_message(closure, "Chiuso")
    assert skipped_days_words([6, 5]) == "esclusi i sabati e le domeniche"
    # A single day ignores the excluded weekdays; a range with nothing left is refused.
    single = run(coordinator.async_add_closure(date_from="2026-12-05", skip_weekdays=[5]))
    assert single["skip_weekdays"] == [] and SpaBookingCoordinator._closure_days(single) == ["2026-12-05"]
    try:
        run(coordinator.async_add_closure(date_from="2026-12-12", date_to="2026-12-13", skip_weekdays=[5, 6]))
    except Exception as error:  # noqa: BLE001
        assert "nessun giorno" in str(error)
    else:
        raise AssertionError("an empty closure must be refused")

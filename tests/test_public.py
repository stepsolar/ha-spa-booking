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

"""Personal logins: roles, the masseuse's own appointments, the tablet PIN."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from custom_components.spa_booking import access, services
from custom_components.spa_booking.const import KEY_PROFILES, KEY_SETTINGS
from custom_components.spa_booking.exceptions import ValidationError

from .conftest import run
from .test_permissions import _call, setup  # noqa: F401 - fixture


def _giulia_id(coordinator) -> str:
    return next(op["id"] for op in coordinator.operators if op["name"] == "Giulia")


def _maria_id(coordinator) -> str:
    return next(op["id"] for op in coordinator.operators if op["name"] == "Maria")


def test_pin_hash_roundtrip() -> None:
    salt, digest = access.hash_pin("4821")
    assert access.check_pin("4821", salt, digest)
    assert not access.check_pin("4822", salt, digest)
    assert not access.check_pin("48a1", salt, digest)
    assert not access.check_pin("4821", "", "")


def test_profiles_never_expose_the_pin(setup) -> None:  # noqa: F811
    _, coordinator = setup
    run(coordinator.async_set_user_profile("u_giulia", pin="4821"))
    stored = coordinator._data[KEY_SETTINGS][KEY_PROFILES]["u_giulia"]
    assert stored["pin_hash"] and stored["pin_salt"]
    public = coordinator.config_payload()["settings"][KEY_PROFILES]["u_giulia"]
    assert public == {"operator_id": "", "shared": False, "has_pin": True}
    assert "pin_hash" not in str(services._without_secrets(coordinator._data[KEY_SETTINGS]))


def test_operator_linked_once(setup) -> None:  # noqa: F811
    _, coordinator = setup
    giulia = _giulia_id(coordinator)
    run(coordinator.async_set_user_profile("u_giulia", operator_id=giulia))
    with pytest.raises(Exception, match="già collegata"):
        run(coordinator.async_set_user_profile("u_operator", operator_id=giulia))


def test_therapist_books_only_herself(setup) -> None:  # noqa: F811
    hass, coordinator = setup
    giulia, maria = _giulia_id(coordinator), _maria_id(coordinator)
    inner = AsyncMock(return_value={"ok": True})
    create = services._guarded(services.SERVICE_CREATE_APPOINTMENT, inner)
    # Not linked to an operator yet: refused with a clear reason.
    with pytest.raises(ValidationError, match="collegato"):
        run(create(_call(hass, "u_giulia", {"operator_id": giulia})))
    run(coordinator.async_set_user_profile("u_giulia", operator_id=giulia))
    assert run(create(_call(hass, "u_giulia", {"operator_id": giulia}))) == {"ok": True}
    with pytest.raises(ValidationError, match="solo i tuoi"):
        run(create(_call(hass, "u_giulia", {"operator_id": maria})))
    with pytest.raises(ValidationError, match="te stessa"):
        run(create(_call(hass, "u_giulia", {})))
    with pytest.raises(ValidationError, match="incassi"):
        run(create(_call(hass, "u_giulia", {
            "operator_id": giulia, "payment": {"paid": True, "paid_amount": 80}})))
    # A voucher redeemed is not money taken.
    assert run(create(_call(hass, "u_giulia", {
        "operator_id": giulia, "payment": {"voucher": True, "voucher_code": "VCH-X"}})))
    # Rows of a multi-person booking are checked too.
    bookings = services._guarded(services.SERVICE_CREATE_BOOKINGS, inner)
    with pytest.raises(ValidationError):
        run(bookings(_call(hass, "u_giulia", {"rows": [
            {"entries": [{"operator_id": giulia}, {"operator_id": maria}]}]})))
    # Payments and new vouchers are the reception's.
    with pytest.raises(ValidationError):
        run(services._guarded(services.SERVICE_ADD_PAYMENT, inner)(_call(hass, "u_giulia")))
    with pytest.raises(ValidationError):
        run(services._guarded(services.SERVICE_CREATE_VOUCHER, inner)(_call(hass, "u_giulia")))


def test_therapist_cannot_touch_someone_elses_appointment(setup) -> None:  # noqa: F811
    hass, coordinator = setup
    giulia, maria = _giulia_id(coordinator), _maria_id(coordinator)
    run(coordinator.async_set_user_profile("u_giulia", operator_id=giulia))
    coordinator._data["appointments"] = [
        {"id": "a1", "operator_id": maria}, {"id": "a2", "operator_id": giulia},
    ]
    inner = AsyncMock(return_value={"ok": True})
    check_in = services._guarded(services.SERVICE_CHECK_IN_APPOINTMENT, inner)
    with pytest.raises(ValidationError):
        run(check_in(_call(hass, "u_giulia", {"appointment_id": "a1"})))
    assert run(check_in(_call(hass, "u_giulia", {"appointment_id": "a2"})))
    # The reception may do it for everybody.
    assert run(check_in(_call(hass, "u_operator", {"appointment_id": "a1"})))


def test_shared_tablet_acts_as_the_person_with_the_pin(setup) -> None:  # noqa: F811
    hass, coordinator = setup
    run(coordinator.async_set_user_profile("u_tablet", shared=True))
    run(coordinator.async_set_user_profile("u_operator", pin="1234"))
    inner = AsyncMock(return_value={"ok": True})
    book = services._guarded(services.SERVICE_CREATE_APPOINTMENT, inner)
    # Before a PIN the tablet can do nothing.
    with pytest.raises(ValidationError, match="PIN"):
        run(book(_call(hass, "u_tablet")))
    who = run(services._async_whoami(_call(hass, "u_tablet")))
    assert who["shared"] and who["level"] == "none"
    assert [p["name"] for p in who["people"]] == ["Laura"]
    with pytest.raises(ValidationError, match="sbagliato"):
        run(services._async_pin_login(_call(hass, "u_tablet", {"user_id": "u_operator", "pin": "9999"})))
    who = run(services._async_pin_login(_call(hass, "u_tablet", {"user_id": "u_operator", "pin": "1234"})))
    assert who["name"] == "Laura" and who["level"] == "operator"
    assert run(book(_call(hass, "u_tablet"))) == {"ok": True}
    # Configuration stays closed: Laura is the reception, not an admin.
    with pytest.raises(ValidationError):
        run(services._guarded(services.SERVICE_ADD_TREATMENT, inner)(_call(hass, "u_tablet")))
    run(services._async_pin_logout(_call(hass, "u_tablet")))
    with pytest.raises(ValidationError, match="PIN"):
        run(book(_call(hass, "u_tablet")))


def test_pin_locks_after_five_wrong(setup) -> None:  # noqa: F811
    hass, coordinator = setup
    run(coordinator.async_set_user_profile("u_tablet", shared=True))
    run(coordinator.async_set_user_profile("u_operator", pin="1234"))
    login = services._async_pin_login
    for _ in range(5):
        with pytest.raises(ValidationError):
            run(login(_call(hass, "u_tablet", {"user_id": "u_operator", "pin": "0000"})))
    # Even the right PIN is refused while locked.
    with pytest.raises(ValidationError, match="Troppi"):
        run(login(_call(hass, "u_tablet", {"user_id": "u_operator", "pin": "1234"})))


def test_tablet_session_expires(setup, monkeypatch) -> None:  # noqa: F811
    hass, coordinator = setup
    run(coordinator.async_set_user_profile("u_tablet", shared=True))
    run(coordinator.async_set_user_profile("u_operator", pin="1234"))
    clock = [1000.0]
    monkeypatch.setattr(services.time, "monotonic", lambda: clock[0])
    run(services._async_pin_login(_call(hass, "u_tablet", {"user_id": "u_operator", "pin": "1234"})))
    clock[0] += 11 * 60
    assert run(services.caller_level(_call(hass, "u_tablet"), coordinator)) == "none"


def test_pin_only_on_the_shared_tablet(setup) -> None:  # noqa: F811
    hass, coordinator = setup
    run(coordinator.async_set_user_profile("u_operator", pin="1234"))
    with pytest.raises(ValidationError, match="tablet"):
        run(services._async_pin_login(_call(hass, "u_reader", {"user_id": "u_operator", "pin": "1234"})))


def test_voucher_signed_by_who_is_signed_in(setup) -> None:  # noqa: F811
    hass, coordinator = setup
    treatment = coordinator.treatments[0]["id"]
    data = {
        "buyer_name": "Anna", "buyer_phone": "+39 333 1234567",
        "recipient_name": "Sara", "recipient_phone": "",
        "people": [{"name": "Sara", "treatment_ids": [treatment]}],
        "created_by": "Qualcun altro",
    }
    create = services._guarded(services.SERVICE_CREATE_VOUCHER, services._async_create_voucher)
    # From 2.3.0 a person signs with her PIN.
    with pytest.raises(ValidationError, match="PIN"):
        run(create(_call(hass, "u_operator", data)))
    run(coordinator.async_set_user_profile("u_operator", pin="1234"))
    run(coordinator.async_set_user_profile("u_giulia", pin="5678"))
    voucher = run(create(_call(hass, "u_operator", {**data, "pin": "1234"})))["voucher"]
    # The owner of the PIN, not what the form says.
    assert voucher["created_by_name"] == "Laura"
    assert voucher["created_by"] == "u_operator"
    with pytest.raises(ValidationError, match="PIN sbagliato"):
        run(create(_call(hass, "u_operator", {**data, "pin": "0000"})))
    # A masseuse cannot sell vouchers even with her right PIN.
    with pytest.raises(ValidationError, match="Reception"):
        run(create(_call(hass, "u_operator", {**data, "pin": "5678"})))
    # Two people may not share a PIN.
    with pytest.raises(Exception, match="già usato"):
        run(coordinator.async_set_user_profile("u_giulia", pin="1234"))
    # An automation has to say who made it.
    voucher = run(create(_call(hass, None, data)))["voucher"]
    assert voucher["created_by_name"] == "Qualcun altro"
    with pytest.raises(ValidationError, match="chi ha creato"):
        run(create(_call(hass, None, {**data, "created_by": ""})))


def test_hidden_admin_cannot_be_the_tablet(setup) -> None:  # noqa: F811
    hass, _ = setup
    call = _call(hass, None, {"user_id": "u_admin_ha", "shared": True})
    hass.auth.async_get_user = AsyncMock(side_effect=lambda uid: {
        "u_admin_ha": SimpleNamespace(id="u_admin_ha", name="Stefano", is_admin=True,
                                      is_owner=False, is_active=True, system_generated=False),
    }.get(uid))
    with pytest.raises(ValidationError):
        run(services._async_set_user_profile(call))


def test_only_reception_may_force_category_rules(setup) -> None:  # noqa: F811
    hass, coordinator = setup
    from custom_components.spa_booking.coordinator import FORCE_RULES

    giulia = _giulia_id(coordinator)
    run(coordinator.async_set_user_profile("u_giulia", operator_id=giulia))
    seen = []

    async def inner(call):
        seen.append(FORCE_RULES.get())
        return {"ok": True}

    create = services._guarded(services.SERVICE_CREATE_APPOINTMENT, inner)
    with pytest.raises(ValidationError, match="reception"):
        run(create(_call(hass, "u_giulia", {"operator_id": giulia, "force_rules": True})))
    run(create(_call(hass, "u_operator", {"force_rules": True})))
    run(create(_call(hass, "u_operator", {})))
    assert seen == [True, False]
    assert FORCE_RULES.get() is False


def test_booking_history_and_author(setup) -> None:  # noqa: F811
    hass, coordinator = setup
    from custom_components.spa_booking.coordinator import ACTOR

    treatment = next(t for t in coordinator.treatments if not t.get("operator_ids"))
    # What async_load does at start-up.
    coordinator._history_snap = {a["id"]: coordinator._history_values(a) for a in coordinator.appointments}
    token = ACTOR.set(("u_operator", "Laura"))
    try:
        booked = run(coordinator.async_create_appointment(
            first_name="Anna", last_name="Neri", phone="+39 333 0000001",
            treatment_id=treatment["id"], start="2026-12-10T10:00:00+01:00",
        ))
    finally:
        ACTOR.reset(token)
    appt = next(a for a in coordinator.appointments if a["id"] == booked["id"])
    assert appt["created_by_name"] == "Laura"
    assert appt["history"][0]["action"] == "Creata" and appt["history"][0]["by"] == "Laura"

    token = ACTOR.set(("u_admin_ha", "Stefano"))
    try:
        appt["notes"] = "Allergia agli oli"
        run(coordinator._async_save())
    finally:
        ACTOR.reset(token)
    last = appt["history"][-1]
    assert last["by"] == "Stefano" and last["action"] == "Modificata"
    assert last["changes"] == [{"field": "notes", "label": "Note", "old": "—", "new": "Allergia agli oli"}]
    # Nothing changed: no entry.
    run(coordinator._async_save())
    assert len(appt["history"]) == 2

    # Only the administrator sees it.
    export = services._guarded(services.SERVICE_EXPORT_DATA, services._async_export_data)
    seen = run(export(_call(hass, "u_operator")))["data"]["appointments"]
    assert all("history" not in item for item in seen)
    seen = run(export(_call(hass, "u_admin_ha")))["data"]["appointments"]
    assert any(item.get("history") for item in seen)

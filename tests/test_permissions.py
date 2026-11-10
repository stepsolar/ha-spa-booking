"""Server-side access levels: the card's Accessi tab is enforced by services."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.spa_booking import services
from custom_components.spa_booking.const import DOMAIN, KEY_PERMISSIONS, KEY_SETTINGS
from custom_components.spa_booking.exceptions import ValidationError

from .conftest import run

def _user(uid, name, admin=False):
    return SimpleNamespace(
        id=uid, name=name, is_admin=admin, is_owner=False, is_active=True,
        system_generated=False, credentials=[],
    )


USERS = {
    "u_admin_ha": _user("u_admin_ha", "Stefano", admin=True),
    "u_operator": _user("u_operator", "Laura"),
    "u_reader": _user("u_reader", "Ospite"),
    "u_stranger": _user("u_stranger", "Estraneo"),
    "u_giulia": _user("u_giulia", "Giulia"),
    "u_tablet": _user("u_tablet", "Tablet reception"),
}


@pytest.fixture
def setup(coordinator):
    coordinator._data[KEY_SETTINGS][KEY_PERMISSIONS] = {
        "u_operator": "operator",
        "u_reader": "read",
        "u_giulia": "therapist",
    }
    coordinator._data[KEY_SETTINGS]["waha_api_key"] = "segreto"
    coordinator._data[KEY_SETTINGS]["web_token"] = "token-sito"
    hass = MagicMock()
    hass.data = {DOMAIN: coordinator}
    hass.async_add_executor_job = coordinator.hass.async_add_executor_job
    hass.auth.async_get_user = AsyncMock(side_effect=lambda uid: USERS.get(uid))
    return hass, coordinator


def _call(hass, user_id, data=None):
    return SimpleNamespace(
        hass=hass,
        data=data or {},
        context=SimpleNamespace(user_id=user_id),
    )


@pytest.mark.parametrize(
    ("user_id", "expected"),
    [
        (None, "admin"),  # automations and scripts act as the system
        ("u_admin_ha", "admin"),
        ("u_operator", "operator"),
        ("u_reader", "read"),
        ("u_stranger", "none"),  # same rule as the card: not listed = no access
    ],
)
def test_caller_level(setup, user_id, expected) -> None:
    hass, coordinator = setup
    assert run(services.caller_level(_call(hass, user_id), coordinator)) == expected


def test_reader_cannot_book(setup) -> None:
    hass, _ = setup
    handler = services._guarded(services.SERVICE_CREATE_APPOINTMENT, AsyncMock())
    with pytest.raises(ValidationError):
        run(handler(_call(hass, "u_reader")))


def test_operator_can_book_but_not_configure(setup) -> None:
    hass, _ = setup
    inner = AsyncMock(return_value={"ok": True})
    assert run(services._guarded(services.SERVICE_CREATE_APPOINTMENT, inner)(_call(hass, "u_operator"))) == {"ok": True}
    with pytest.raises(ValidationError):
        run(services._guarded(services.SERVICE_ADD_TREATMENT, inner)(_call(hass, "u_operator")))
    with pytest.raises(ValidationError):
        run(services._guarded(services.SERVICE_SEND_PROMO, inner)(_call(hass, "u_operator")))


def test_unlisted_services_default_to_admin(setup) -> None:
    hass, _ = setup
    handler = services._guarded("some_future_service", AsyncMock())
    with pytest.raises(ValidationError):
        run(handler(_call(hass, "u_operator")))
    run(handler(_call(hass, "u_admin_ha")))


def test_secrets_hidden_from_non_admin(setup) -> None:
    hass, _ = setup
    data = run(services._async_export_data(_call(hass, "u_operator")))["data"]
    assert data["settings"]["waha_api_key"] == ""
    assert data["settings"]["web_token"] == ""
    config = run(services._async_get_config(_call(hass, "u_reader")))["config"]
    assert config["settings"]["waha_api_key"] == ""
    admin = run(services._async_export_data(_call(hass, "u_admin_ha")))["data"]
    assert admin["settings"]["waha_api_key"] == "segreto"


def test_operator_may_only_change_layout(setup) -> None:
    hass, coordinator = setup
    run(services._async_update_settings(_call(hass, "u_operator", {"appearance": "dark"})))
    assert coordinator._data[KEY_SETTINGS]["appearance"] == "dark"
    with pytest.raises(ValidationError):
        run(services._async_update_settings(_call(hass, "u_operator", {"waha_url": "http://evil"})))
    assert coordinator._data[KEY_SETTINGS]["waha_url"] == ""


def test_every_service_has_a_level() -> None:
    for service in services.ALL_SERVICES:
        level = services.SERVICE_LEVELS.get(service, "admin")
        assert level in services._LEVEL_RANK

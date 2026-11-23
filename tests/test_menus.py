"""3.21.0: the administrator turns each menu on or off per user (Accessi)."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from custom_components.spa_booking import menus, services
from custom_components.spa_booking.exceptions import ValidationError

from .conftest import run
from .test_permissions import _call, setup  # noqa: F401


def test_role_then_eyes() -> None:
    base = menus.visible_menus("operator")
    assert "whatsapp" in base and "config" not in base and "spa.telecamere" in base
    mine = menus.visible_menus("operator", {"whatsapp": False, "config.trattamenti": True, "config": True,
                                            "spa.telecamere": False, "config.accessi": True, "bogus": True})
    assert "whatsapp" not in mine and "spa.telecamere" not in mine
    assert {"config", "config.trattamenti"} <= mine
    assert "config.accessi" not in mine and "bogus" not in mine
    # A sub-menu without its parent, a parent without sub-menus: hidden.
    assert "config.trattamenti" not in menus.visible_menus("operator", {"config.trattamenti": True})
    assert "nuovo" not in menus.visible_menus("operator", {"nuovo.appuntamento": False, "nuovo.nuova": False,
                                                            "nuovo.lista": False})
    assert menus.visible_menus("none", {"agenda": True}) == set()
    assert "config.accessi" in menus.visible_menus("admin", {"config": False})


def test_settings_by_tab() -> None:
    assert menus.setting_tab("treatments_order") == "trattamenti"
    assert menus.setting_tab("accessories") == "accessori"
    assert menus.setting_tab("smtp_host") == "email"
    assert menus.setting_tab("appointment_reminder_message") == "notifiche"
    assert menus.setting_tab("ai_enabled") == "accessi"
    assert menus.setting_tab("web_open_time") == "impostazioni"


def test_eye_opens_only_its_own_services_and_settings(setup) -> None:  # noqa: F811
    hass, coordinator = setup
    inner = AsyncMock(return_value={"ok": True})
    add_treatment = services._guarded(services.SERVICE_ADD_TREATMENT, inner)
    add_category = services._guarded(services.SERVICE_ADD_CATEGORY, inner)
    with pytest.raises(ValidationError):
        run(add_treatment(_call(hass, "u_operator")))
    run(coordinator.async_set_user_menus("u_operator", {"config": True, "config.trattamenti": True}))
    assert run(add_treatment(_call(hass, "u_operator"))) == {"ok": True}
    with pytest.raises(ValidationError):
        run(add_category(_call(hass, "u_operator")))
    # Users and restore stay with the administrators.
    with pytest.raises(ValidationError):
        run(services._guarded(services.SERVICE_SET_USER_MENUS, inner)(_call(hass, "u_operator")))
    # Settings: the treatments tab's own, not the others.
    update = services._guarded(services.SERVICE_UPDATE_SETTINGS, services._async_update_settings)
    run(update(_call(hass, "u_operator", {"vat_default": 10})))
    with pytest.raises(ValidationError):
        run(update(_call(hass, "u_operator", {"web_public_url": "http://evil"})))
    # Whoami tells the card.
    me = run(services._guarded(services.SERVICE_WHOAMI, services._async_whoami)(_call(hass, "u_operator")))
    assert "config.trattamenti" in me["menus"] and "config.categorie" not in me["menus"]


def test_blank_secret_does_not_wipe(setup) -> None:  # noqa: F811
    hass, coordinator = setup
    coordinator._data["settings"]["smtp_password"] = "segreta"
    run(coordinator.async_set_user_menus("u_operator", {"config": True, "config.email": True}))
    update = services._guarded(services.SERVICE_UPDATE_SETTINGS, services._async_update_settings)
    run(update(_call(hass, "u_operator", {"smtp_host": "smtp.example.it", "smtp_password": ""})))
    assert coordinator._data["settings"]["smtp_password"] == "segreta"
    assert coordinator._data["settings"]["smtp_host"] == "smtp.example.it"


def test_back_to_the_role(setup) -> None:  # noqa: F811
    _hass, coordinator = setup
    run(coordinator.async_set_user_menus("u_operator", {"whatsapp": False}))
    assert coordinator.menu_overrides("u_operator") == {"whatsapp": False}
    run(coordinator.async_set_user_menus("u_operator", None))
    assert coordinator.menu_overrides("u_operator") == {}


def test_card_role_table_matches_the_server() -> None:
    """The card draws the eyes from its own copy of the role table."""
    import re
    from pathlib import Path

    card = Path(__file__).parents[1] / "custom_components/spa_booking/frontend/spa-booking-card.js"
    block = re.search(r"const MENU_ROLE_DEFAULTS = \{(.*?)\n\};", card.read_text(encoding="utf-8"), re.S).group(1)
    for level in ("none", "read", "therapist", "operator", "manager"):
        found = re.search(rf"{level}: \[(.*?)\]", block, re.S).group(1)
        assert set(re.findall(r'"([a-z.]+)"', found)) == menus.role_menus(level), level


def test_whole_page_saved_back_is_fine(setup) -> None:  # noqa: F811
    """Impostazioni saves every key of the page: unchanged AI keys are not refused."""
    hass, coordinator = setup
    coordinator._data["settings"]["ai_enabled"] = False
    run(coordinator.async_set_user_menus("u_operator", {"config": True, "config.impostazioni": True}))
    update = services._guarded(services.SERVICE_UPDATE_SETTINGS, services._async_update_settings)
    run(update(_call(hass, "u_operator", {"card_title": "Spa", "ai_enabled": False})))
    assert coordinator._data["settings"]["card_title"] == "Spa"
    with pytest.raises(ValidationError):
        run(update(_call(hass, "u_operator", {"ai_enabled": True})))

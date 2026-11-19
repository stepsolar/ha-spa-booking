"""3.17.2: an accessory can be hidden from the website form."""

from __future__ import annotations

from custom_components.spa_booking.normalize import _norm_settings


def test_web_visible_is_kept() -> None:
    settings = _norm_settings({"accessories": [
        {"id": "acc_camera", "label": "Camera", "icon": "mdi:bed-king-outline", "web_visible": False},
        {"id": "kit", "label": "Kit"},
    ]})
    by_id = {a["id"]: a for a in settings["accessories"]}
    assert by_id["acc_camera"]["web_visible"] is False
    assert by_id["kit"]["web_visible"] is True

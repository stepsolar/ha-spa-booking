"""Dedicated, isolated scaffold for the SPA dashboard builder.

This package is intentionally read-only and additive: it reports the existing
Spa/Camera entity lists from the coordinator settings without replacing the
work done by the front-end card. Future steps (feature editors, views,
actions) can extend it without breaking the current card runtime.
"""


def dashboard_config(settings: dict) -> dict:
    """Return a compact dashboard-oriented view of the settings."""
    if not isinstance(settings, dict):
        return {}
    return {
        "appearance": settings.get("appearance"),
        "card_title": settings.get("card_title"),
        "spa_entities": settings.get("spa_entities", []),
        "camera_entities": settings.get("camera_entities", []),
        "accessories": settings.get("accessories", []),
    }

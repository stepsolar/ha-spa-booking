"""Spa Booking Web draws the icons from mdi_paths: every icon of the card must be there."""

from __future__ import annotations

import re
from pathlib import Path

from custom_components.spa_booking.mdi_paths import MDI_PATHS

ROOT = Path(__file__).parents[1] / "custom_components/spa_booking"


def test_every_icon_of_the_card_has_its_drawing() -> None:
    """3.23.2: new icons showed as an empty button in Spa Booking Web."""
    sources = [ROOT / "frontend/spa-booking-card.js", ROOT / "const.py", ROOT / "menus.py"]
    used = set()
    for source in sources:
        used |= set(re.findall(r"mdi:([a-z0-9][a-z0-9-]*[a-z0-9])", source.read_text(encoding="utf-8")))
    missing = sorted(used - set(MDI_PATHS))
    assert not missing, f"Aggiungi a mdi_paths.py (da @mdi/svg): {missing}"
    assert all(paths and all(p.startswith("M") for p in paths) for paths in MDI_PATHS.values())

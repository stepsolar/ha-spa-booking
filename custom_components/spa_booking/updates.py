"""Updates of Spa Booking: what is installed, what runs, what is waiting.

HACS installs a new version by replacing the files of the integration and
then asks for a restart, because Home Assistant imports the Python code once
and cannot swap it while running. Spa Booking can tell the two kinds of
update apart:

* only the card or the website form changed (``frontend/``): those files are
  read from disk at every request, so reloading the page is enough;
* any Python file, ``services.yaml`` or the manifest changed: the running
  code is the old one until Home Assistant restarts.

The fingerprint of the code that runs is taken when the integration starts;
comparing it with the files on disk says which case applies.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

PACKAGE_DIR = Path(__file__).parent
#: The part of the integration that only a restart brings in.
_CODE_SUFFIXES = (".py", ".yaml", ".json")
REPO_MARKER = "ha-spa-booking"


def code_fingerprint(base: Path = PACKAGE_DIR) -> str:
    """A hash of every file a restart would load (Python, YAML, JSON)."""
    digest = hashlib.sha256()
    for path in sorted(base.rglob("*")):
        if (
            path.is_file()
            and path.suffix in _CODE_SUFFIXES
            and "__pycache__" not in path.parts
            and "frontend" not in path.relative_to(base).parts
            and "bin" not in path.relative_to(base).parts
        ):
            digest.update(str(path.relative_to(base)).encode())
            digest.update(path.read_bytes())
    return digest.hexdigest()[:16]


def disk_version(base: Path = PACKAGE_DIR) -> str:
    """The version written in the manifest on disk right now."""
    try:
        return str(json.loads((base / "manifest.json").read_text(encoding="utf-8")).get("version") or "")
    except (OSError, ValueError):
        return ""


def find_update_entity(states: Any) -> dict[str, Any] | None:
    """The update entity HACS created for Spa Booking, if any.

    HACS names it after the repository (``update.spa_booking_update`` in a
    default install), but the user may rename it: it is recognised by the
    release link or the title instead.
    """
    for state in states:
        if not state.entity_id.startswith("update."):
            continue
        attrs = state.attributes or {}
        url = str(attrs.get("release_url") or "")
        title = str(attrs.get("title") or attrs.get("friendly_name") or "")
        if REPO_MARKER in url or title.strip().lower().startswith("spa booking"):
            return {
                "entity_id": state.entity_id,
                "available": state.state == "on",
                "installed_version": attrs.get("installed_version") or "",
                "latest_version": attrs.get("latest_version") or "",
                "in_progress": bool(attrs.get("in_progress")),
                "release_url": url,
                "title": title,
            }
    return None

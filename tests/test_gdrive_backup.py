"""Daily backups on Google Drive (2.8.0)."""

from __future__ import annotations

import json

import pytest

from custom_components.spa_booking import gdrive_backup
from custom_components.spa_booking.exceptions import ValidationError

from .conftest import run


@pytest.fixture
def drive(coordinator, monkeypatch):
    state = {"files": {}, "next": 0, "folder": ""}

    async def token():
        return "tok"

    async def ensure_folder(session, tok, folder_id=""):
        state["folder"] = folder_id or "fold1"
        return state["folder"]

    async def list_backups(session, tok, folder):
        return sorted(state["files"].values(), key=lambda f: f["createdTime"], reverse=True)

    async def upload(session, tok, folder, name, payload, existing_id=""):
        if existing_id:
            state["files"][existing_id]["data"] = payload
            return state["files"][existing_id]
        state["next"] += 1
        fid = f"f{state['next']}"
        state["files"][fid] = {"id": fid, "name": name, "createdTime": f"2026-11-{state['next']:02d}T03:30:00Z", "data": payload}
        return state["files"][fid]

    async def delete(session, tok, file_id):
        state["files"].pop(file_id, None)

    async def download(session, tok, file_id):
        return state["files"][file_id]["data"]

    for name, fn in (("ensure_folder", ensure_folder), ("list_backups", list_backups), ("upload", upload),
                     ("delete", delete), ("download", download)):
        monkeypatch.setattr(gdrive_backup, name, fn)
    monkeypatch.setattr(coordinator, "_async_google_token", token)
    monkeypatch.setattr(coordinator, "_http_session", lambda: None)
    settings = coordinator._data["settings"]
    settings.update(google_refresh_token="r", google_scopes="openid email https://www.googleapis.com/auth/drive.file")
    return state


def test_keeps_three_one_per_day(coordinator, drive, freeze) -> None:
    for day in ("2026-11-10", "2026-11-11", "2026-11-12", "2026-11-13"):
        freeze(f"{day} 03:35")
        run(coordinator.async_gdrive_backup())
    names = sorted(f["name"] for f in drive["files"].values())
    assert names == ["spa-booking-backup-2026-11-11.json", "spa-booking-backup-2026-11-12.json", "spa-booking-backup-2026-11-13.json"]
    # The same day again replaces that day's file.
    result = run(coordinator.async_gdrive_backup())
    assert result["replaced"] and len(drive["files"]) == 3
    # The file is the whole dataset, readable by «Ripristina backup».
    payload = json.loads(next(iter(drive["files"].values()))["data"])
    assert "appointments" in payload and "settings" in payload


def test_daily_tick_and_restore(coordinator, drive, freeze) -> None:
    run(coordinator.async_update_settings(gdrive_enabled=True, gdrive_time="03:30", card_title="Prima"))
    freeze("2026-11-13 02:00")
    assert run(coordinator.async_gdrive_tick()) == {"skipped": "non ancora"}
    freeze("2026-11-13 03:31")
    assert run(coordinator.async_gdrive_tick())["ok"]
    freeze("2026-11-13 09:00")
    assert run(coordinator.async_gdrive_tick()) == {"skipped": "già fatto oggi"}
    # Restore: the list, then the data back.
    files = run(coordinator.async_gdrive_list())["files"]
    assert len(files) == 1
    run(coordinator.async_update_settings(card_title="Dopo"))
    run(coordinator.async_gdrive_restore(files[0]["id"]))
    assert coordinator._data["settings"]["card_title"] == "Prima"


def test_needs_drive_permission(coordinator, drive) -> None:
    coordinator._data["settings"]["google_scopes"] = "openid email https://www.googleapis.com/auth/gmail.send"
    with pytest.raises(ValidationError):
        run(coordinator.async_gdrive_backup())


def test_to_delete_by_day() -> None:
    files = [{"name": f"spa-booking-backup-2026-11-{d:02d}.json", "createdTime": ""} for d in (3, 1, 4, 2)]
    assert [f["name"][-7:-5] for f in gdrive_backup.to_delete(files)] == ["01"]

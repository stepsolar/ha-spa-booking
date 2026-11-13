"""Automatic backups on Google Drive (2.8.0).

Once a day Spa Booking writes its whole dataset (the same JSON as «Scarica
backup», so «Ripristina backup» reads it) into a «Spa Booking backup» folder
on the connected Google account, and keeps the newest three: the oldest is
deleted each time a new day's backup arrives. A second backup on the same
day replaces that day's file.

It uses the ``drive.file`` permission: Spa Booking sees and touches only the
files it created itself, nothing else on the Drive.
"""

from __future__ import annotations

import json
from typing import Any
import uuid

from aiohttp import ClientError

from .google_auth import GoogleAuthError, _google_error

API = "https://www.googleapis.com/drive/v3/files"
UPLOAD = "https://www.googleapis.com/upload/drive/v3/files"
FOLDER_NAME = "Spa Booking backup"
FOLDER_MIME = "application/vnd.google-apps.folder"
PREFIX = "spa-booking-backup-"
KEEP = 3


async def _call(session: Any, method: str, url: str, token: str, *, expect_json: bool = True, **kwargs: Any) -> Any:
    headers = {"Authorization": f"Bearer {token}", **kwargs.pop("headers", {})}
    try:
        async with session.request(method, url, headers=headers, timeout=60, **kwargs) as response:
            if response.status >= 400:
                try:
                    body = await response.json(content_type=None)
                except ValueError:
                    body = {}
                if response.status == 403 and "insufficient" in json.dumps(body).lower():
                    raise GoogleAuthError("Manca il permesso Google Drive: premi «Collega Google Drive» e spunta il permesso.")
                if response.status == 404:
                    raise GoogleAuthError("not_found")
                raise GoogleAuthError(_google_error(response.status, body if isinstance(body, dict) else {}))
            if not expect_json:
                return await response.read()
            if response.status == 204:
                return {}
            return await response.json(content_type=None)
    except (ClientError, TimeoutError) as err:
        raise GoogleAuthError(f"Google Drive non raggiungibile: {err}") from err


async def ensure_folder(session: Any, token: str, folder_id: str = "") -> str:
    """The backup folder: the known one if it still exists, else a new one."""
    if folder_id:
        try:
            info = await _call(session, "GET", f"{API}/{folder_id}", token, params={"fields": "id,trashed"})
            if info.get("id") and not info.get("trashed"):
                return folder_id
        except GoogleAuthError as err:
            if str(err) != "not_found":
                raise
    created = await _call(session, "POST", API, token, json={"name": FOLDER_NAME, "mimeType": FOLDER_MIME},
                          params={"fields": "id"})
    return str(created.get("id") or "")


async def list_backups(session: Any, token: str, folder_id: str) -> list[dict[str, Any]]:
    """The backups in the folder, newest first."""
    body = await _call(session, "GET", API, token, params={
        "q": f"'{folder_id}' in parents and trashed = false and name contains '{PREFIX}'",
        "orderBy": "createdTime desc",
        "fields": "files(id,name,createdTime,modifiedTime,size)",
        "pageSize": "50",
    })
    return [f for f in body.get("files") or [] if str(f.get("name") or "").startswith(PREFIX)]


async def upload(session: Any, token: str, folder_id: str, name: str, payload: bytes, existing_id: str = "") -> dict[str, Any]:
    """Write one backup file (a new one, or that day's again)."""
    if existing_id:
        return await _call(session, "PATCH", f"{UPLOAD}/{existing_id}", token, data=payload,
                           params={"uploadType": "media", "fields": "id,name,createdTime,modifiedTime,size"},
                           headers={"Content-Type": "application/json"})
    boundary = uuid.uuid4().hex
    meta = json.dumps({"name": name, "parents": [folder_id], "mimeType": "application/json"}).encode()
    body = (f"--{boundary}\r\nContent-Type: application/json; charset=UTF-8\r\n\r\n".encode() + meta
            + f"\r\n--{boundary}\r\nContent-Type: application/json\r\n\r\n".encode() + payload
            + f"\r\n--{boundary}--".encode())
    return await _call(session, "POST", UPLOAD, token, data=body,
                       params={"uploadType": "multipart", "fields": "id,name,createdTime,modifiedTime,size"},
                       headers={"Content-Type": f"multipart/related; boundary={boundary}"})


async def delete(session: Any, token: str, file_id: str) -> None:
    try:
        await _call(session, "DELETE", f"{API}/{file_id}", token, expect_json=False)
    except GoogleAuthError as err:
        if str(err) != "not_found":
            raise


async def download(session: Any, token: str, file_id: str) -> bytes:
    return await _call(session, "GET", f"{API}/{file_id}", token, expect_json=False, params={"alt": "media"})


def to_delete(files: list[dict[str, Any]], keep: int = KEEP) -> list[dict[str, Any]]:
    """What goes beyond the newest `keep` backups (by name: one per day)."""
    ordered = sorted(files, key=lambda f: (str(f.get("name") or ""), str(f.get("createdTime") or "")), reverse=True)
    return ordered[keep:]

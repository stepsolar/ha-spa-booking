"""WhatsApp built into Spa Booking (beta).

Instead of the WAHA add-on, the integration starts its own small program,
``bin/spa-wa-bridge-linux-<arch>`` (sources in ``bridge/`` of the repository,
built on the whatsmeow library). It links to the hotel's number as a linked
device, like WhatsApp Web, and talks to Home Assistant over 127.0.0.1 only,
with a token generated at every start.

This module:

* starts the program, restarts it when it stops, stops it with the entry;
* offers the same methods as ``WahaClient`` (``async_send_text``,
  ``async_send_image``, ``async_resolve_lid``, ``async_get_server``), so the
  rest of the integration sends through it without knowing which one is used;
* reads the program's event stream and hands messages and reactions to the
  same handler the WAHA webhook uses (the program reports them in WAHA's
  shape), so offers, answers and external messages work exactly as before;
* exposes the linking flow (QR code, code to type on the phone, unlink) to
  the card.

The session (the keys of the linked device) lives in
``.storage/spa_booking_whatsapp/`` and is part of Home Assistant's backups.
"""

from __future__ import annotations

import asyncio
import base64
import contextlib
import json
import logging
import os
from pathlib import Path
import platform
import secrets
import stat
from typing import TYPE_CHECKING, Any

from aiohttp import ClientError, ClientSession, ClientTimeout

from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .waha import WahaConnectionError, WahaError, WahaServer

if TYPE_CHECKING:
    from .waha_inbound import WahaInbound

_LOGGER = logging.getLogger(__name__)

BIN_DIR = Path(__file__).parent / "bin"
#: Session name the program uses in its events (WAHA-compatible).
SESSION = "spa"
#: Restart delays after an unexpected stop, in seconds (then stays at the last).
RESTART_DELAYS = (2, 5, 15, 30, 60, 300)
#: A program that ran this long before stopping starts again from the first delay.
STABLE_AFTER = 600
#: How long a single API call may take (a send waits for "typing" and pacing).
CALL_TIMEOUT = ClientTimeout(total=75)
#: States the card shows, in Italian.
STATE_LABELS = {
    "missing": "Programma non disponibile per questo sistema",
    "stopped": "Fermo",
    "starting": "Avvio in corso",
    "not_linked": "Non collegato",
    "pairing": "In attesa del collegamento",
    "connecting": "Connessione in corso",
    "connected": "Connesso",
    "disconnected": "Disconnesso, nuovo tentativo in corso",
    "logged_out": "Scollegato dal telefono",
    "banned": "Numero bloccato temporaneamente da WhatsApp",
}


def binary_path() -> Path | None:
    """The program for this machine, or None when none is shipped for it."""
    machine = platform.machine().lower()
    arch = {"x86_64": "amd64", "amd64": "amd64", "aarch64": "arm64", "arm64": "arm64"}.get(machine)
    if arch is None:
        return None
    path = BIN_DIR / f"spa-wa-bridge-linux-{arch}"
    return path if path.is_file() else None


def _ensure_executable(path: Path) -> None:
    """HACS does not keep the executable bit of downloaded files."""
    mode = path.stat().st_mode
    if not mode & stat.S_IXUSR:
        path.chmod(mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


class WaBridge:
    """The built-in WhatsApp connection of one installation."""

    session_name = SESSION

    def __init__(self, hass: HomeAssistant, inbound: WahaInbound) -> None:
        """Keep Home Assistant and the handler of inbound messages."""
        self._hass = hass
        self._inbound = inbound
        self._data_dir = Path(hass.config.path(".storage", "spa_booking_whatsapp"))
        self._token = ""
        self._base = ""
        self._proc: asyncio.subprocess.Process | None = None
        self._session: ClientSession | None = None
        self._supervisor: asyncio.Task | None = None
        self._events: asyncio.Task | None = None
        self._stopping = False
        self._ready = asyncio.Event()
        self.state = "stopped"
        self.detail = ""
        self.listeners: list[Any] = []

    # ---------------------------------------------------------- lifecycle

    @property
    def running(self) -> bool:
        """Whether the program is up and answering."""
        return self._ready.is_set() and self._proc is not None and self._proc.returncode is None

    async def async_start(self) -> None:
        """Start the program (and keep it running) in the background."""
        if self._supervisor is not None:
            return
        self._stopping = False
        self._session = ClientSession()
        self._supervisor = self._hass.async_create_background_task(
            self._async_supervise(), "spa_booking_whatsapp_bridge"
        )

    async def async_stop(self) -> None:
        """Stop the program and every task around it."""
        self._stopping = True
        self._ready.clear()
        for task in (self._events, self._supervisor):
            if task is not None:
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError, Exception):
                    await task
        self._events = self._supervisor = None
        await self._async_kill()
        if self._session is not None:
            await self._session.close()
            self._session = None
        self._set_state("stopped", "")

    async def _async_kill(self) -> None:
        proc, self._proc = self._proc, None
        if proc is None or proc.returncode is not None:
            return
        with contextlib.suppress(ProcessLookupError):
            proc.terminate()
        try:
            await asyncio.wait_for(proc.wait(), 8)
        except TimeoutError:
            with contextlib.suppress(ProcessLookupError):
                proc.kill()
            await proc.wait()

    async def _async_supervise(self) -> None:
        """Run the program; restart it with growing pauses when it stops."""
        failures = 0
        while not self._stopping:
            path = await self._hass.async_add_executor_job(binary_path)
            if path is None:
                self._set_state(
                    "missing",
                    f"Nessun programma per il processore '{platform.machine()}': usa WAHA.",
                )
                return
            started = asyncio.get_running_loop().time()
            try:
                await self._async_run_once(path)
            except asyncio.CancelledError:
                raise
            except Exception as err:  # noqa: BLE001 - keep supervising
                _LOGGER.warning("WhatsApp integrato: %s", err)
                self._set_state("stopped", str(err))
            if self._stopping:
                return
            if asyncio.get_running_loop().time() - started > STABLE_AFTER:
                failures = 0
            delay = RESTART_DELAYS[min(failures, len(RESTART_DELAYS) - 1)]
            failures += 1
            _LOGGER.warning("WhatsApp integrato fermo: riavvio tra %s secondi", delay)
            await asyncio.sleep(delay)

    async def _async_run_once(self, path: Path) -> None:
        """Start the program once and wait for it to stop."""
        await self._hass.async_add_executor_job(_ensure_executable, path)
        await self._hass.async_add_executor_job(
            lambda: self._data_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
        )
        self._token = secrets.token_urlsafe(32)
        self._ready.clear()
        self._set_state("starting", "")
        env = {
            "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
            "SPA_WA_TOKEN": self._token,
            "TZ": os.environ.get("TZ", "UTC"),
        }
        self._proc = await asyncio.create_subprocess_exec(
            str(path),
            "--listen", "127.0.0.1:0",
            "--data", str(self._data_dir),
            "--name", "Spa Booking",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            env=env,
        )
        assert self._proc.stdout is not None
        # The first line says where the API listens.
        line = await asyncio.wait_for(self._proc.stdout.readline(), 30)
        text = line.decode(errors="replace").strip()
        if not text.startswith("SPA_WA_LISTEN "):
            raise WahaConnectionError(f"avvio non riuscito: {text or 'nessuna risposta'}")
        self._base = "http://" + text.split(" ", 1)[1]
        self._ready.set()
        self._events = self._hass.async_create_background_task(
            self._async_read_events(), "spa_booking_whatsapp_events"
        )
        try:
            await self._async_pump_logs()
            await self._proc.wait()
        finally:
            self._ready.clear()
            if self._events is not None:
                self._events.cancel()
                self._events = None
        code = self._proc.returncode if self._proc else None
        self._proc = None
        if not self._stopping:
            raise WahaConnectionError(f"il programma si è fermato (codice {code})")

    async def _async_pump_logs(self) -> None:
        """Copy the program's log lines into Home Assistant's log."""
        assert self._proc is not None and self._proc.stdout is not None
        async for raw in self._proc.stdout:
            line = raw.decode(errors="replace").rstrip()
            if not line:
                continue
            if "[ERROR]" in line:
                _LOGGER.error("WhatsApp: %s", line)
            elif "[WARN]" in line:
                _LOGGER.warning("WhatsApp: %s", line)
            else:
                _LOGGER.debug("WhatsApp: %s", line)

    # ------------------------------------------------------------- events

    async def _async_read_events(self) -> None:
        """Follow the program's event stream, reconnecting when it drops."""
        while not self._stopping and self._ready.is_set():
            try:
                assert self._session is not None
                async with self._session.get(
                    f"{self._base}/events",
                    headers=self._headers,
                    timeout=ClientTimeout(total=None, sock_read=90),
                ) as response:
                    response.raise_for_status()
                    async for raw in response.content:
                        await self._async_handle_line(raw)
            except asyncio.CancelledError:
                raise
            except (ClientError, TimeoutError, ValueError) as err:
                _LOGGER.debug("Flusso eventi WhatsApp interrotto: %s", err)
            await asyncio.sleep(2)

    async def _async_handle_line(self, raw: bytes) -> None:
        try:
            event = json.loads(raw)
        except ValueError:
            return
        if not isinstance(event, dict):
            return
        kind = event.get("event")
        if kind == "state":
            self._set_state(str(event.get("state") or ""), str(event.get("detail") or ""))
        elif kind == "qr":
            self._notify()
        elif kind in ("message", "message.reaction"):
            try:
                await self._inbound.async_handle_event(event)
            except Exception:  # noqa: BLE001 - one bad message must not stop the stream
                _LOGGER.exception("Messaggio WhatsApp non gestito")

    def _set_state(self, state: str, detail: str) -> None:
        if (state, detail) == (self.state, self.detail):
            return
        previous = self.state
        self.state, self.detail = state, detail
        if state in ("logged_out", "banned") or (previous == "connected" and state == "disconnected"):
            _LOGGER.warning("WhatsApp integrato: %s %s", STATE_LABELS.get(state, state), detail)
        self._notify()

    def _notify(self) -> None:
        for listener in list(self.listeners):
            listener()

    # ----------------------------------------------------------------- API

    @property
    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._token}"}

    async def _call(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        if not self.running or self._session is None:
            raise WahaConnectionError(
                f"WhatsApp integrato non attivo ({STATE_LABELS.get(self.state, self.state)})"
            )
        try:
            async with self._session.request(
                method, f"{self._base}{path}", headers=self._headers, timeout=CALL_TIMEOUT, **kwargs
            ) as response:
                data = await response.json(content_type=None)
        except (ClientError, TimeoutError, ValueError) as err:
            raise WahaConnectionError(f"WhatsApp integrato non risponde: {err}") from err
        return data if isinstance(data, dict) else {}

    async def async_status(self) -> dict[str, Any]:
        """State, linked number and QR code, for the card."""
        status: dict[str, Any] = {"state": self.state, "detail": self.detail}
        if self.running:
            with contextlib.suppress(WahaError):
                status = await self._call("GET", "/status")
        state = str(status.get("state") or self.state)
        status["state"] = state
        status["label"] = STATE_LABELS.get(state, state)
        return status

    async def async_pair_start(self) -> dict[str, Any]:
        """Start linking: QR codes appear in ``async_status``."""
        result = await self._call("POST", "/pair/start")
        if result.get("error"):
            raise WahaError(str(result["error"]))
        return result

    async def async_pair_code(self, phone: str) -> str:
        """An 8-character code to type on the phone instead of the QR code."""
        result = await self._call("POST", "/pair/code", json={"phone": phone})
        if not result.get("code"):
            raise WahaError(str(result.get("error") or "codice non disponibile"))
        return str(result["code"])

    async def async_logout(self) -> None:
        """Unlink this device from the number."""
        await self._call("POST", "/logout")

    # ----------------------------------------- the WahaClient interface

    async def async_send_text(
        self, chat_id: str, text: str, *, link_preview: bool = True
    ) -> dict[str, Any]:
        """Send one text message; a refused destination is reported, not raised."""
        if not chat_id:
            return {"sent": False, "error": "nessun destinatario"}
        result = await self._call("POST", "/send/text", json={"chat_id": chat_id, "text": text})
        return {
            "sent": bool(result.get("sent")),
            "message_id": result.get("message_id"),
            "error": str(result.get("error") or ""),
        }

    async def async_send_image(
        self,
        chat_id: str,
        image: str | bytes,
        *,
        caption: str = "",
        filename: str = "immagine.jpg",
        mimetype: str = "image/jpeg",
    ) -> dict[str, Any]:
        """Send one picture, from bytes or from a URL fetched here."""
        if not chat_id:
            return {"sent": False, "error": "nessun destinatario"}
        if not isinstance(image, bytes):
            session = async_get_clientsession(self._hass)
            try:
                async with session.get(str(image), timeout=ClientTimeout(total=30)) as response:
                    response.raise_for_status()
                    image = await response.read()
                    mimetype = response.content_type or mimetype
            except (ClientError, TimeoutError) as err:
                return {"sent": False, "error": f"immagine non scaricabile: {err}"}
        return await self._call(
            "POST",
            "/send/image",
            json={
                "chat_id": chat_id,
                "image": base64.b64encode(image).decode("ascii"),
                "mimetype": mimetype,
                "caption": caption,
            },
        )

    async def async_resolve_lid(self, lid: str) -> str | None:
        """The phone chat id behind a LID, when the session knows it."""
        result = await self._call("GET", "/lid", params={"lid": lid})
        value = result.get("chat_id")
        return str(value) if value else None

    async def async_get_server(self) -> WahaServer:
        """Version and engine, for the card's connection test."""
        status = await self._call("GET", "/status")
        if status.get("state") != "connected":
            raise WahaConnectionError(
                f"WhatsApp integrato: {STATE_LABELS.get(str(status.get('state')), status.get('state'))}"
            )
        return WahaServer(version=str(status.get("version") or ""), engine="integrato")

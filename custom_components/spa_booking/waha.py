"""A small async client for the WAHA WhatsApp HTTP API.

WhatsApp has no public protocol an integration may speak: every Home Assistant
setup talks to it through a gateway, and here that gateway is the local WAHA
add-on. This client therefore stays deliberately small:

* ``async_send_text`` – plain text to one chat id (``39…@c.us`` or a group).
* ``async_send_image`` – a picture, for when a document or a photo has to
  travel with the message.
* ``async_get_server`` – the version and the engine, used by the card's
  connection test.

Everything else the WAHA add-on can do (groups, polls, commands, …) is
deliberately left out: a capability nobody calls is code nobody maintains.

The client never raises for a refused send: WAHA answers a JSON body with
``sent: false`` for a number that is not on WhatsApp, and the caller decides
whether that is an error. Only transport and authentication problems raise.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from aiohttp import ClientResponseError, ClientSession

_LOGGER = logging.getLogger(__name__)

#: How long a single HTTP call to WAHA may take before the client gives up.
REQUEST_TIMEOUT_SECONDS = 20

#: WAHA requires a chat id to address a destination: a bare phone number is
#: not accepted by /api/sendText.
_JID_DIRECT = "@c.us"
_JID_GROUP = "@g.us"


class WahaError(Exception):
    """Base error for every WAHA call that failed."""


class WahaConnectionError(WahaError):
    """WAHA could not be reached at all (wrong URL, add-on down)."""


class WahaAuthenticationError(WahaError):
    """WAHA rejected the configured API key."""


@dataclass(frozen=True, slots=True)
class WahaServer:
    """The little WAHA says about itself, used to confirm a configuration."""

    version: str
    engine: str | None


def _message_id(data: Any) -> str | None:
    """Return the id WAHA assigned to a sent message, when it reports one.

    WAHA answers ``{"id": {"fromMe": true, "remote": "…", "id": "…",
    "_serialized": "…"}}`` for a text message, while other endpoints answer a
    plain string. Only the string form is used for the ACK-like return value.
    """
    if isinstance(data, dict):
        if "id" not in data:
            return None
        raw = data.get("id")
        return raw if isinstance(raw, str) else _message_id(raw)
    return data if isinstance(data, str) else None


def _flag_sent(data: Any) -> bool:
    """Whether WAHA reported the message as accepted for delivery.

    An accepted send answers ``{"sent": true, "ack": …, …}``; a number that is
    not on WhatsApp answers ``{"sent": false, "error": …}``. A missing "sent"
    is treated as accepted, because older builds only answered the id.
    """
    if isinstance(data, dict) and data.get("sent") is False:
        return False
    return True


class WahaClient:
    """Send WhatsApp messages through one local WAHA add-on."""

    def __init__(
        self,
        session: ClientSession,
        api_key: str,
        session_name: str,
        *,
        base_url: str,
    ) -> None:
        """Keep the session, the key and the add-on's base URL."""
        self._session = session
        self._api_key = api_key
        self.session_name = session_name
        self.base_url = base_url.rstrip("/")

    # -------------------------------------------------------------- sending

    async def async_send_text(
        self, chat_id: str, text: str, *, link_preview: bool = True
    ) -> dict[str, Any]:
        """Send one WhatsApp text message and report how WAHA received it.

        Returns ``{"sent": …, "message_id": …, "error": …}``: a destination WAHA
        refused (not a WhatsApp number, group left, …) is reported as not sent
        rather than raised, because a booking must not fail over it.
        """
        if not chat_id:
            return {"sent": False, "error": "nessun destinatario"}
        data = await self._post(
            "/api/sendText",
            {
                "session": self.session_name,
                "chatId": chat_id,
                "text": text,
                "linkPreview": link_preview,
            },
        )
        sent = _flag_sent(data)
        return {
            "sent": sent,
            "message_id": _message_id(data),
            "error": "" if sent else str(data.get("error") or "destinatario rifiutato"),
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
        """Send one picture, by public URL or by already-loaded bytes.

        A URL travels as WAHA expects it; raw bytes are base64-encoded here, so
        a caller can send a report just rendered in memory instead of writing
        it somewhere WAHA could reach.
        """
        if not chat_id:
            return {"sent": False, "error": "nessun destinatario"}
        payload = {"session": self.session_name, "chatId": chat_id}
        if isinstance(image, bytes):
            import base64

            payload["file"] = {
                "mimetype": mimetype,
                "filename": filename,
                "data": base64.b64encode(image).decode("ascii"),
            }
        else:
            payload["file"] = {"url": str(image)}
        if caption:
            payload["caption"] = caption
        return await self._request("POST", "/api/sendImage", json=payload)

    # ------------------------------------------------------------ diagnostic

    async def async_resolve_lid(self, lid: str) -> str | None:
        """Map a WhatsApp LID to its phone-number direct-chat id.

        Returns ``39…@c.us`` for a mapped LID, or None when the server knows
        no phone number for it. Only transport and authentication problems
        raise: an unknown LID is a normal answer from an unknown sender.
        """
        from urllib.parse import quote

        value = (lid or "").strip()
        if not value:
            return None
        data = await self._request(
            "GET",
            f"/api/{quote(self.session_name, safe='')}/lids/{quote(value, safe='')}",
        )
        if not isinstance(data, dict):
            return None
        phone = data.get("pn")
        if not isinstance(phone, str) or not phone.strip():
            return None
        phone = phone.strip()
        if "@" in phone:
            return phone
        digits = "".join(char for char in phone if char.isdigit())
        if not digits:
            return None
        if not digits.startswith("39"):
            digits = f"39{digits}"
        return f"{digits}@c.us"

    async def async_get_server(self) -> WahaServer:
        """Validate the credentials and report WAHA's version and engine.

        The version call is also the cheapest way to prove a configuration
        works: it is the one request that answers quickly, with nothing but
        the key, whether the add-on is reachable and accepts the key.
        """
        data = await self._request("GET", "/api/version")
        if not isinstance(data, dict):
            raise WahaError("Risposta non valida da WAHA")
        version = data.get("version")
        if not isinstance(version, str) or not version:
            raise WahaError("WAHA non ha riportato la sua versione")
        engine = data.get("engine")
        return WahaServer(
            version=version, engine=engine if isinstance(engine, str) else None
        )

    # --------------------------------------------------------------- plumbing

    async def _post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        """POST a JSON body and return the body as a dictionary."""
        data = await self._request("POST", path, json=payload)
        return data if isinstance(data, dict) else {}

    async def async_ensure_webhook(self, url: str, hmac_key: str) -> bool:
        """Point this session at ``url`` for messages and reactions.

        The other webhooks already configured on the session are left alone:
        this installation owns its own entry and nothing else, so an add-on or
        another integration that also listens keeps working.

        Returns whether the session configuration had to change.
        """
        from urllib.parse import quote

        session_path = f"/api/sessions/{quote(self.session_name, safe='')}"
        data = await self._request("GET", session_path)
        if not isinstance(data, dict):
            raise WahaError("Configurazione della sessione WAHA non valida")

        raw_config = data.get("config")
        config: dict[str, Any] = {**raw_config} if isinstance(raw_config, dict) else {}
        raw_webhooks = config.get("webhooks", [])
        if not isinstance(raw_webhooks, list) or not all(
            isinstance(item, dict) for item in raw_webhooks
        ):
            raise WahaError("Configurazione dei webhook WAHA non valida")

        # Only the two events an answer can arrive in. WAHA lets a session
        # notify many more; asking for fewer keeps the payloads small and means
        # nothing unrelated ever reaches this integration.
        desired = {
            "url": url,
            "events": ["message", "message.reaction"],
            "hmac": {"key": hmac_key},
            "retries": {"policy": "constant", "delaySeconds": 1, "attempts": 3},
        }
        matching = [item for item in raw_webhooks if item.get("url") == url]
        if len(matching) == 1 and _webhook_matches(matching[0], desired):
            return False

        if matching:
            # A previous version of this same webhook: keep whatever else it
            # declared and only update what this integration needs.
            desired = {**matching[-1], **desired}
        webhooks = [item for item in raw_webhooks if item.get("url") != url]
        webhooks.append(desired)

        config["webhooks"] = webhooks
        await self._request(
            "PUT", session_path, json={"name": self.session_name, "config": config}
        )
        return True

    async def _request(
        self,
        method: str,
        path: str,
        *,
        json: dict[str, Any] | None = None,
    ) -> Any:
        """Call WAHA with the configured key, translating its errors."""
        headers = {"Content-Type": "application/json"}
        if self._api_key:
            headers["X-Api-Key"] = self._api_key
        url = f"{self.base_url}{path}"
        try:
            async with self._session.request(
                method,
                url,
                json=json,
                headers=headers,
                timeout=REQUEST_TIMEOUT_SECONDS,
            ) as response:
                status = response.status
                body = await response.json(content_type=None)
        except ClientResponseError as err:
            raise WahaConnectionError(f"WAHA ha rifiutato la connessione: {err}") from err
        except Exception as err:  # noqa: BLE001 - aiohttp raises many shapes
            raise WahaConnectionError(
                f"WAHA non raggiungibile su {self.base_url}: {err}"
            ) from err

        if status in (401, 403):
            raise WahaAuthenticationError(
                "WAHA ha rifiutato la chiave API configurata"
            )
        if status == 404:
            raise WahaError(
                f"Endpoint WAHA non trovato su {self.base_url} "
                "(l'add-on è in esecuzione?)"
            )
        if status >= 400:
            raise WahaError(_error_text(body) or f"WAHA ha risposto {status}")
        return body


def _error_text(body: Any) -> str:
    """Return the message of a WAHA error body, whatever shape it came in."""
    if isinstance(body, dict):
        for key in ("error", "message", "detail"):
            value = body.get(key)
            if isinstance(value, str) and value:
                return value
        return str(body)
    return str(body or "")


def _webhook_matches(current: dict[str, Any], desired: dict[str, Any]) -> bool:
    """Whether a session webhook already is the one this integration wants.

    Comparing the events as a set matters: WAHA may answer them in any order,
    and a reordered list is the same subscription, not a change.
    """
    if current.get("url") != desired["url"]:
        return False
    if not isinstance(current.get("hmac"), dict) or not current["hmac"].get("key"):
        return False
    events = current.get("events")
    if not isinstance(events, list):
        return False
    return {str(item) for item in events} == set(desired["events"])

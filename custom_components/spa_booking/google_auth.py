"""«Accedi con Google» for sending email through Gmail (2.4.2).

Spa Booking signs in to Google on its own (no Home Assistant Google
integration): the desk presses the button, accepts on Google's page, and the
integration keeps a refresh token with the only permission it asks for,
``gmail.send`` (send mail, nothing else: it cannot read the mailbox). The
mail then goes out through the Gmail API, from the account or from one of its
«Invia messaggi come» addresses.

Google requires an OAuth client (Client ID and Client secret) made once in a
Google Cloud project; the card walks through it and shows the redirect
address to paste there.
"""

from __future__ import annotations

import base64
from dataclasses import dataclass
import json
import secrets
import time
from typing import Any
from urllib.parse import urlencode

from aiohttp import ClientError, web

from homeassistant.components.http import KEY_HASS, HomeAssistantView

from .const import DOMAIN

AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
REVOKE_URL = "https://oauth2.googleapis.com/revoke"
SEND_URL = "https://gmail.googleapis.com/gmail/v1/users/me/messages/send"
#: Send only (sensitive, not restricted), plus who the account is.
SCOPES = "openid email https://www.googleapis.com/auth/gmail.send"
#: Drive backups (2.8.0): only the files Spa Booking creates (non-sensitive).
DRIVE_SCOPE = "https://www.googleapis.com/auth/drive.file"
SCOPES_DRIVE = f"openid email {DRIVE_SCOPE}"
CALLBACK_PATH = "/api/spa_booking/google/callback"
STATE_TTL_SEC = 15 * 60


class GoogleAuthError(Exception):
    """A Google failure, already in words for the desk."""


@dataclass
class PendingLogin:
    """A login started from the card, waiting for Google to come back."""

    redirect_uri: str
    expires: float
    purpose: str = "email"


def new_state(pending: dict[str, PendingLogin], redirect_uri: str, purpose: str = "email") -> str:
    """A one-time state for one login; old ones are dropped."""
    now = time.time()
    for key in [k for k, v in pending.items() if v.expires < now]:
        pending.pop(key, None)
    state = secrets.token_urlsafe(24)
    pending[state] = PendingLogin(redirect_uri, now + STATE_TTL_SEC, purpose)
    return state


def auth_url(client_id: str, redirect_uri: str, state: str, login_hint: str = "", scopes: str = SCOPES) -> str:
    """Google's consent page for this login."""
    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": scopes,
        "access_type": "offline",
        # Always ask, so Google always hands back a refresh token.
        "prompt": "consent",
        "include_granted_scopes": "true",
        "state": state,
    }
    if login_hint:
        params["login_hint"] = login_hint
    return f"{AUTH_URL}?{urlencode(params)}"


def email_of_id_token(id_token: str) -> str:
    """The account's address, read from the ID token Google just sent us over TLS."""
    try:
        payload = id_token.split(".")[1]
        payload += "=" * (-len(payload) % 4)
        return str(json.loads(base64.urlsafe_b64decode(payload)).get("email") or "")
    except (IndexError, ValueError):
        return ""


def _google_error(status: int, body: dict[str, Any]) -> str:
    """Google's answer in Italian."""
    error = body.get("error")
    if isinstance(error, dict):
        message = str(error.get("message") or "")
        reason = str(((error.get("errors") or [{}])[0] or {}).get("reason") or "")
    else:
        message = str(body.get("error_description") or error or "")
        reason = str(error or "")
    if reason == "invalid_grant" or "invalid_grant" in message:
        return "L'accesso Google è scaduto o è stato revocato: premi di nuovo «Accedi con Google»."
    if reason in ("invalid_client", "unauthorized_client"):
        return "Client ID o Client secret non validi: ricontrollali in Configurazione › Email."
    if reason == "redirect_uri_mismatch" or "redirect_uri" in message:
        return "L'indirizzo di ritorno non è tra quelli autorizzati nel progetto Google: copialo da Configurazione › Email."
    if status == 403 and "Gmail API has not been used" in message:
        return "La Gmail API non è attiva nel progetto Google: attivala (Google Cloud › API e servizi › Libreria › Gmail API)."
    if status == 403 or "Delegation denied" in message:
        return "Google ha rifiutato il mittente: l'indirizzo deve essere tra «Invia messaggi come» del tuo Gmail."
    if status == 400 and "Invalid To header" in message:
        return "L'indirizzo del destinatario non è valido."
    return f"Google ha risposto {status}: {message or reason or 'errore sconosciuto'}"


async def _post(session: Any, url: str, **kwargs: Any) -> dict[str, Any]:
    try:
        async with session.post(url, timeout=20, **kwargs) as response:
            try:
                body = await response.json(content_type=None)
            except ValueError:
                body = {}
            if response.status >= 400:
                raise GoogleAuthError(_google_error(response.status, body if isinstance(body, dict) else {}))
            return body if isinstance(body, dict) else {}
    except (ClientError, TimeoutError) as err:
        raise GoogleAuthError(f"Google non raggiungibile: {err}") from err


async def exchange_code(session: Any, client_id: str, client_secret: str, code: str, redirect_uri: str) -> dict[str, Any]:
    """The tokens for the code Google sent back to the callback."""
    return await _post(session, TOKEN_URL, data={
        "code": code, "client_id": client_id, "client_secret": client_secret,
        "redirect_uri": redirect_uri, "grant_type": "authorization_code",
    })


async def refresh_access(session: Any, client_id: str, client_secret: str, refresh_token: str) -> tuple[str, float]:
    """A fresh access token (valid about an hour) and when it expires."""
    body = await _post(session, TOKEN_URL, data={
        "client_id": client_id, "client_secret": client_secret,
        "refresh_token": refresh_token, "grant_type": "refresh_token",
    })
    token = str(body.get("access_token") or "")
    if not token:
        raise GoogleAuthError("Google non ha dato l'accesso: premi di nuovo «Accedi con Google».")
    return token, time.time() + float(body.get("expires_in") or 3600) - 60


async def revoke(session: Any, token: str) -> None:
    """Withdraw the permission on Google's side (best effort)."""
    try:
        await _post(session, REVOKE_URL, data={"token": token})
    except GoogleAuthError:
        pass


async def gmail_send(session: Any, access_token: str, message_bytes: bytes) -> dict[str, Any]:
    """Send one ready MIME message through the Gmail API."""
    raw = base64.urlsafe_b64encode(message_bytes).decode().rstrip("=")
    return await _post(session, SEND_URL, json={"raw": raw},
                       headers={"Authorization": f"Bearer {access_token}"})


_PAGE = """<!doctype html><html lang="it"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Spa Booking · Google</title>
<style>body{{font-family:system-ui,sans-serif;background:#f3f5f7;margin:0;display:grid;place-items:center;min-height:100vh}}
.c{{background:#fff;border-radius:16px;padding:28px 32px;max-width:420px;box-shadow:0 8px 30px rgba(0,0,0,.08);text-align:center}}
h1{{font-size:20px;margin:8px 0}}p{{color:#4b5563;line-height:1.5}}.i{{font-size:40px}}</style></head>
<body><div class="c"><div class="i">{icon}</div><h1>{title}</h1><p>{text}</p><p><small>Puoi chiudere questa finestra.</small></p></div>
<script>try{{window.opener&&window.opener.postMessage({{spaBookingGoogle:{ok}}},"*")}}catch(e){{}}setTimeout(function(){{window.close()}},{close});</script>
</body></html>"""


def _page(ok: bool, title: str, text: str) -> web.Response:
    import html as _html

    return web.Response(
        content_type="text/html",
        text=_PAGE.format(icon="✅" if ok else "⚠️", title=_html.escape(title), text=_html.escape(text),
                          ok="true" if ok else "false", close=2500 if ok else 60000),
    )


class GoogleCallbackView(HomeAssistantView):
    """Where Google sends the browser back after «Accedi con Google».

    Not authenticated by Home Assistant (Google's redirect carries no
    session): the one-time ``state`` made by the card is the proof.
    """

    url = CALLBACK_PATH
    name = "api:spa_booking:google_callback"
    requires_auth = False

    async def get(self, request: web.Request) -> web.Response:
        hass = request.app[KEY_HASS]
        coordinator = hass.data.get(DOMAIN)
        if coordinator is None:
            return web.Response(status=404, text="Not found")
        query = request.query
        if query.get("error"):
            return _page(False, "Accesso annullato", "Non hai dato il permesso su Google: riprova da Spa Booking.")
        try:
            account = await coordinator.async_google_callback(str(query.get("state") or ""), str(query.get("code") or ""))
        except GoogleAuthError as err:
            return _page(False, "Accesso non riuscito", str(err))
        if account.startswith("drive:"):
            return _page(True, "Google Drive collegato", f"Spa Booking salverà i backup sul Drive di {account[6:]}.")
        return _page(True, "Account Google collegato", f"Spa Booking invierà le email da {account}.")

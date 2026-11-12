"""Sending email through an SMTP mailbox (2.4.1): Gmail, Outlook, Aruba or any other.

Home Assistant gives no generic way to send mail with a mailbox chosen from a
card, so the integration talks SMTP itself. The connection runs in the
executor (smtplib blocks) with a short timeout, and every failure comes back
as an Italian sentence that says what to fix, never as a stack trace.
"""

from __future__ import annotations

from email.message import EmailMessage
from email.utils import formataddr, make_msgid
import smtplib
import socket
import ssl
from typing import Any

from homeassistant.core import HomeAssistant

#: Ready-made settings per provider: host, port, security.
EMAIL_PROVIDERS: dict[str, dict[str, Any]] = {
    "gmail": {"host": "smtp.gmail.com", "port": 587, "security": "starttls"},
    "outlook": {"host": "smtp.office365.com", "port": 587, "security": "starttls"},
    "aruba": {"host": "smtps.aruba.it", "port": 465, "security": "ssl"},
    "libero": {"host": "smtp.libero.it", "port": 465, "security": "ssl"},
    "altro": {"host": "", "port": 587, "security": "starttls"},
}
EMAIL_SECURITY = ("starttls", "ssl", "none")
TIMEOUT_SEC = 20


def email_config(settings: dict[str, Any]) -> dict[str, Any]:
    """The mailbox to use, with the provider's host and port filled in."""
    provider = str(settings.get("smtp_provider") or "gmail")
    preset = EMAIL_PROVIDERS.get(provider, EMAIL_PROVIDERS["altro"])
    username = str(settings.get("smtp_username") or "").strip()
    return {
        "provider": provider,
        "host": str(settings.get("smtp_host") or "").strip() or preset["host"],
        "port": int(settings.get("smtp_port") or 0) or preset["port"],
        "security": str(settings.get("smtp_security") or "") or preset["security"],
        "username": username,
        # Google shows the app password in four groups: the spaces are not part of it.
        "password": str(settings.get("smtp_password") or "").replace(" ", "") if provider == "gmail"
        else str(settings.get("smtp_password") or ""),
        "from_name": str(settings.get("email_from_name") or "").strip(),
        "from_address": str(settings.get("email_from") or "").strip() or username,
        "reply_to": str(settings.get("email_reply_to") or "").strip(),
    }


def _explain(err: Exception, config: dict[str, Any]) -> str:
    """A failure in words the desk can act on."""
    if isinstance(err, smtplib.SMTPAuthenticationError):
        if config["provider"] == "gmail":
            return ("Accesso rifiutato da Gmail: serve una «password per le app" "»"
                    " (Account Google › Sicurezza › Verifica in due passaggi › Password per le app),"
                    " non la password normale.")
        if config["provider"] == "outlook":
            return ("Accesso rifiutato da Outlook: controlla utente e password; con la verifica in due"
                    " passaggi serve una password per le app, e l'invio SMTP deve essere consentito"
                    " sull'account.")
        return "Accesso rifiutato: controlla utente e password della casella."
    if isinstance(err, smtplib.SMTPRecipientsRefused):
        return "L'indirizzo del destinatario è stato rifiutato: controllalo."
    if isinstance(err, smtplib.SMTPSenderRefused):
        return "Il mittente è stato rifiutato: l'indirizzo «Da» deve essere quello della casella (o un suo alias)."
    if isinstance(err, (socket.gaierror,)):
        return f"Server {config['host']} non trovato: controlla l'indirizzo del server."
    if isinstance(err, (TimeoutError, socket.timeout)):
        return f"Il server {config['host']}:{config['port']} non risponde: controlla porta e sicurezza."
    if isinstance(err, ConnectionRefusedError):
        return f"Connessione rifiutata da {config['host']}:{config['port']}: controlla porta e sicurezza."
    if isinstance(err, ssl.SSLError):
        return "Errore di cifratura: prova a cambiare «Sicurezza» (SSL con la porta 465, STARTTLS con la 587)."
    return f"Invio non riuscito: {err}"


def _send(config: dict[str, Any], message: EmailMessage) -> None:
    """Blocking SMTP send (runs in the executor)."""
    context = ssl.create_default_context()
    if config["security"] == "ssl":
        server: smtplib.SMTP = smtplib.SMTP_SSL(config["host"], config["port"], timeout=TIMEOUT_SEC, context=context)
    else:
        server = smtplib.SMTP(config["host"], config["port"], timeout=TIMEOUT_SEC)
    try:
        server.ehlo()
        if config["security"] == "starttls":
            server.starttls(context=context)
            server.ehlo()
        if config["username"]:
            server.login(config["username"], config["password"])
        server.send_message(message)
    finally:
        try:
            server.quit()
        except Exception:  # noqa: BLE001 - closing a broken connection
            pass


def build_message(config: dict[str, Any], to: list[str], subject: str, body: str, html: str | None = None) -> EmailMessage:
    """The message, with the sender name and a reply-to when set."""
    message = EmailMessage()
    message["From"] = formataddr((config["from_name"], config["from_address"])) if config["from_name"] else config["from_address"]
    message["To"] = ", ".join(to)
    message["Subject"] = subject
    message["Message-ID"] = make_msgid(domain=(config["from_address"].split("@")[-1] or None))
    if config["reply_to"]:
        message["Reply-To"] = config["reply_to"]
    message.set_content(body)
    if html:
        message.add_alternative(html, subtype="html")
    return message


async def async_send_email(
    hass: HomeAssistant, settings: dict[str, Any], to: list[str] | str, subject: str, body: str, html: str | None = None
) -> dict[str, Any]:
    """Send one email; ``{"sent": True}`` or ``{"sent": False, "error": ...}``."""
    config = email_config(settings)
    recipients = [to] if isinstance(to, str) else list(to)
    recipients = [r.strip() for r in recipients if r and "@" in r]
    if not recipients:
        return {"sent": False, "error": "Nessun indirizzo email valido a cui inviare."}
    if not config["host"]:
        return {"sent": False, "error": "Manca il server SMTP: scegli il provider o scrivi il server."}
    if not config["from_address"]:
        return {"sent": False, "error": "Manca l'indirizzo email del mittente."}
    if config["username"] and not config["password"]:
        return {"sent": False, "error": "Manca la password della casella."}
    message = build_message(config, recipients, subject, body, html)
    try:
        await hass.async_add_executor_job(_send, config, message)
    except Exception as err:  # noqa: BLE001 - every failure becomes a sentence
        return {"sent": False, "error": _explain(err, config)}
    return {"sent": True, "to": recipients}

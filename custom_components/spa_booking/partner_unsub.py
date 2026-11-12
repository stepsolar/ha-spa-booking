"""The page where a partner stops the campaign emails (2.6.0).

Reached from the link at the bottom of every partner campaign. A GET only
shows the question, the button POSTs it: mail scanners that open every link
must not unsubscribe anybody by themselves.
"""

from __future__ import annotations

import html

from aiohttp import web

from homeassistant.components.http import KEY_HASS, HomeAssistantView

from .const import DOMAIN

UNSUB_PATH = "/api/spa_booking/partner/unsubscribe"

_PAGE = """<!doctype html><html lang="it"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><meta name="robots" content="noindex">
<title>{title}</title>
<style>body{{font-family:system-ui,sans-serif;background:#f3f5f7;margin:0;display:grid;place-items:center;min-height:100vh;padding:16px;box-sizing:border-box}}
.c{{background:#fff;border-radius:16px;padding:28px 32px;max-width:440px;box-shadow:0 8px 30px rgba(0,0,0,.08);text-align:center}}
h1{{font-size:20px;margin:8px 0}}p{{color:#4b5563;line-height:1.5}}.i{{font-size:40px}}
button{{font:inherit;font-weight:600;border:0;border-radius:10px;padding:12px 20px;background:#0a84a8;color:#fff;cursor:pointer}}</style></head>
<body><div class="c"><div class="i">{icon}</div><h1>{title}</h1><p>{text}</p>{form}</div></body></html>"""


def _page(icon: str, title: str, text: str, form: str = "", status: int = 200) -> web.Response:
    return web.Response(status=status, content_type="text/html",
                        text=_PAGE.format(icon=icon, title=html.escape(title), text=html.escape(text), form=form))


class PartnerUnsubscribeView(HomeAssistantView):
    """Unsubscribe a partner from campaigns, by the token in the link."""

    url = UNSUB_PATH
    name = "api:spa_booking:partner_unsubscribe"
    requires_auth = False

    async def get(self, request: web.Request) -> web.Response:
        coordinator = request.app[KEY_HASS].data.get(DOMAIN)
        token = str(request.query.get("t") or "")
        partner = coordinator.partner_by_unsub_token(token) if coordinator else None
        if partner is None:
            return _page("⚠️", "Link non valido", "Questo link di cancellazione non è più valido.", status=404)
        name = partner.get("company") or partner.get("first_name") or ""
        if not partner.get("subscribed", True):
            return _page("✅", "Iscrizione già cancellata", f"{name}: non riceverai più le nostre email e promozioni.")
        form = (f'<form method="post" action="{UNSUB_PATH}?t={html.escape(token)}">'
                '<button type="submit">Non voglio più ricevere email</button></form>')
        return _page("✉️", "Cancella l'iscrizione", f"{name}: confermi di non voler più ricevere le nostre email e promozioni?", form)

    async def post(self, request: web.Request) -> web.Response:
        coordinator = request.app[KEY_HASS].data.get(DOMAIN)
        if coordinator is None:
            return web.Response(status=404, text="Not found")
        partner = await coordinator.async_partner_unsubscribe(str(request.query.get("t") or ""))
        if partner is None:
            return _page("⚠️", "Link non valido", "Questo link di cancellazione non è più valido.", status=404)
        return _page("✅", "Iscrizione cancellata", "Fatto: non riceverai più le nostre email e promozioni. Ci scusiamo per il disturbo.")

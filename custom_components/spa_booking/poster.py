"""The A5 poster of a partner (3.2.0): «Spa Sciacca», what the spa offers,
the prices, the partner's discount and a QR code to the booking page with the
partner's code already in.

Three forms of the same poster:

* ``poster_page``  — the printable A5 page (``/api/spa_booking/partner/poster``),
  with «Stampa» (the browser's print, also to PDF);
* ``poster_email`` — the email to the partner: a short text and the poster
  built with tables and inline styles (what email clients show), as a picture
  that opens the printable page;
* the QR code as PNG (``/api/spa_booking/partner/qr``), for the email.

Nothing on it names the hotel: the texts come from Configurazione › Promo ›
Programma partner › La locandina, with the defaults below.
"""

from __future__ import annotations

import hashlib
import html
from typing import Any

from .mdi_paths import MDI_PATHS
from .qr import qr_svg

POSTER_PATH = "/api/spa_booking/partner/poster"
QR_PATH = "/api/spa_booking/partner/qr"

POSTER_ICONS = [
    "pool", "fire", "weather-fog", "snowflake", "shower-head", "tea", "hand-heart", "face-woman-shimmer",
    "heart-outline", "spa", "leaf", "flower-outline", "candle", "water", "white-balance-sunny", "cup-outline",
]

DEFAULT_POSTER: dict[str, Any] = {
    "title": "Spa Sciacca",
    "kicker": "Day Spa · Massaggi · Benessere",
    "tagline": "Concediti qualche ora di puro relax, a due passi da qui.",
    "items": [
        {"icon": "pool", "title": "Piscina interna a 34°", "text": "acqua salata, idromassaggio e cascate cervicali"},
        {"icon": "fire", "title": "Sauna finlandese e bio sauna", "text": "calore che depura e rilassa"},
        {"icon": "weather-fog", "title": "Bagno turco", "text": "vapore con oli essenziali"},
        {"icon": "snowflake", "title": "Cascata di ghiaccio", "text": "il rituale caldo-freddo nordico"},
        {"icon": "shower-head", "title": "Docce emozionali", "text": "cromoterapia e aromaterapia"},
        {"icon": "tea", "title": "Area relax e tisaneria", "text": "il tempo per te"},
        {"icon": "hand-heart", "title": "Massaggi", "text": "relax, decontratturanti, rituali di coppia"},
        {"icon": "face-woman-shimmer", "title": "Trattamenti viso e corpo", "text": "bellezza e cura della pelle"},
    ],
    "prices": [
        {"label": "Percorso Spa · 2 ore", "price": "50 €"},
        {"label": "Spa in coppia · 2 ore", "price": "80 €"},
        {"label": "Spa + massaggio di coppia", "price": "220 €"},
    ],
    "cta": "Inquadra e prenota",
    "how": "Scegli giorno, ora e trattamento in un minuto: il codice del tuo alloggio è già inserito{sconto}.",
    "footer": "Sciacca (AG) · Accesso su prenotazione · Spa dai 16 anni · Piscina esterna nei mesi estivi",
    "email_subject": "La tua locandina {titolo} per gli ospiti 🌿",
    "email_body": (
        "Ciao {nome},\n\n"
        "ecco la locandina da mettere alla reception o nelle camere di {attivita}. "
        "I tuoi ospiti inquadrano il codice QR e prenotano con il tuo codice già inserito{sconto_ospiti}, "
        "e tu accumuli punti per ogni prenotazione."
    ),
    "email_signature": "Grazie per la collaborazione,\n{titolo}",
}


def norm_poster(raw: Any) -> dict[str, Any]:
    """The poster settings, every field present (defaults where empty)."""
    raw = raw if isinstance(raw, dict) else {}
    out: dict[str, Any] = {}
    for key, default in DEFAULT_POSTER.items():
        if key in ("items", "prices"):
            continue
        value = str(raw.get(key) or "").strip()
        out[key] = value[:600] if value else default
    items = []
    for item in raw.get("items") if isinstance(raw.get("items"), list) else DEFAULT_POSTER["items"]:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or "").strip()[:60]
        if not title:
            continue
        icon = str(item.get("icon") or "spa").strip()
        items.append({"icon": icon if icon in MDI_PATHS else "spa", "title": title,
                      "text": str(item.get("text") or "").strip()[:90]})
    out["items"] = items[:10]
    prices = []
    for price in raw.get("prices") if isinstance(raw.get("prices"), list) else DEFAULT_POSTER["prices"]:
        if not isinstance(price, dict):
            continue
        label = str(price.get("label") or "").strip()[:40]
        amount = str(price.get("price") or "").strip()[:14]
        if label and amount:
            prices.append({"label": label, "price": amount})
    out["prices"] = prices[:4]
    return out


def poster_token(partner: dict[str, Any]) -> str:
    """The partner's poster key: derived from her private token, not guessable,
    and not the unsubscribe token itself (a poster link is passed around)."""
    secret = str(partner.get("unsub_token") or partner.get("id") or "")
    return hashlib.sha256(f"poster:{secret}".encode()).hexdigest()[:24]


def _esc(text: Any) -> str:
    return html.escape(str(text or ""))


def _icon(name: str, color: str, size: int) -> str:
    paths = MDI_PATHS.get(name) or MDI_PATHS.get("spa") or ()
    inner = "".join(f'<path d="{d}"/>' for d in paths)
    return f'<svg viewBox="0 0 24 24" width="{size}" height="{size}" fill="{color}" aria-hidden="true">{inner}</svg>'


def _fill(text: str, values: dict[str, str]) -> str:
    for key, value in values.items():
        text = text.replace("{" + key + "}", value)
    return text


def poster_values(poster: dict[str, Any], partner: dict[str, Any], discount: float) -> dict[str, str]:
    pct = f"{discount:g}".replace(".", ",")
    return {
        "titolo": poster["title"],
        "nome": str(partner.get("first_name") or partner.get("company") or "partner"),
        "attivita": str(partner.get("company") or "la tua struttura"),
        "codice": str(partner.get("code") or ""),
        "sconto": f" e lo sconto del {pct}% è applicato" if discount else "",
        "sconto_ospiti": f" (con lo sconto del {pct}%)" if discount else "",
        "percentuale": pct,
    }


# --------------------------------------------------------------- the page
_PAGE_CSS = """
*{box-sizing:border-box}
@page{size:A5;margin:0}
body{margin:0;background:#8a959a;font-family:'Helvetica Neue',Arial,sans-serif}
.bar{position:sticky;top:0;z-index:2;background:#12343b;color:#fff;padding:10px 16px;display:flex;gap:10px;align-items:center;font-size:14px}
.bar b{flex:1;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.bar button{font:inherit;font-weight:700;background:#1f9e98;color:#fff;border:0;border-radius:9px;padding:9px 14px;cursor:pointer}
.stage{display:flex;justify-content:center;padding:22px 12px}
.sheet{box-shadow:0 10px 30px rgba(0,0,0,.35);transform-origin:top center}
@media (max-width:620px){.stage{padding:12px 0}.sheet{zoom:.62}}
@media print{.bar{display:none}body{background:none}.stage{padding:0}.sheet{box-shadow:none;zoom:1}}
.a5{width:148mm;height:210mm;background:#fbf8f2;color:#12343b;display:flex;flex-direction:column;overflow:hidden;position:relative;-webkit-print-color-adjust:exact;print-color-adjust:exact}
.top{background:linear-gradient(150deg,#1f9e98 0%,#0b4f63 100%);color:#fffaf2;padding:9mm 10mm 12mm;position:relative}
.top:after{content:"";position:absolute;left:0;right:0;bottom:-1px;height:6mm;background:#fbf8f2;clip-path:ellipse(70% 100% at 50% 100%)}
.kick{font-size:8.5pt;letter-spacing:4px;text-transform:uppercase;opacity:.85}
h1{font-family:Georgia,'Times New Roman',serif;font-weight:400;font-size:34pt;line-height:1;margin:2mm 0 1.5mm}
h1 b{color:#f0c977;font-weight:400}
.tag{font-size:10.5pt;opacity:.95;position:relative;z-index:1}
.waves{position:absolute;right:8mm;top:8mm;opacity:.25}
.grid{display:grid;grid-template-columns:1fr 1fr;gap:3.2mm 5mm;padding:6mm 10mm 2mm}
.it{display:flex;gap:2.5mm;align-items:flex-start}
.ic{width:8.5mm;height:8.5mm;border-radius:50%;background:#e2f2ef;display:flex;align-items:center;justify-content:center;flex:none}
.it b{display:block;font-size:9.6pt;line-height:1.15}
.it span{font-size:7.8pt;color:#5b6d72;line-height:1.2}
.prices{display:flex;gap:2.5mm;padding:3mm 10mm 0}
.pr{flex:1;background:#fff;border:1px solid #e7e1d6;border-radius:3mm;padding:2.2mm 2.5mm;text-align:center}
.pr b{display:block;font-family:Georgia,serif;font-size:15pt;color:#0b4f63;font-weight:400}
.pr span{font-size:7.6pt;color:#5b6d72;line-height:1.2;display:block}
.deal{margin:3.5mm 10mm 0;border:1.2px dashed #c9a24d;border-radius:4mm;padding:2.5mm 4mm;text-align:center;font-size:10pt;background:#fff7e3}
.deal b{color:#a7801f;font-size:13pt}
.bottom{margin-top:auto;display:flex;align-items:center;gap:5mm;padding:4mm 10mm 5mm;background:#fff;border-top:1px solid #e7e1d6}
.qr{width:38mm;height:38mm;flex:none;border:1px solid #e7e1d6;border-radius:3mm;padding:1.5mm;background:#fff}
.qr svg{width:100%;height:100%;display:block}
.cta{font-family:Georgia,serif;font-size:17pt;line-height:1.1}
.how{font-size:8.6pt;color:#5b6d72;margin-top:1.5mm;line-height:1.35}
.code{display:inline-block;margin-top:2mm;font-family:Consolas,monospace;font-weight:700;background:#12343b;color:#fff;padding:.8mm 2.5mm;border-radius:1.5mm;font-size:9pt;letter-spacing:1px}
.foot{font-size:7.4pt;color:#7b8b90;text-align:center;padding:0 10mm 3.5mm;background:#fff}
"""


def _title_html(title: str) -> str:
    """The last word of the title in gold: «Spa <b>Sciacca</b>»."""
    words = title.split()
    if len(words) < 2:
        return _esc(title)
    return f"{_esc(' '.join(words[:-1]))} <b>{_esc(words[-1])}</b>"


def poster_sheet(poster: dict[str, Any], partner: dict[str, Any], link: str, discount: float) -> str:
    """The A5 sheet itself (HTML with its CSS classes)."""
    values = poster_values(poster, partner, discount)
    items = "".join(
        f'<div class="it"><div class="ic">{_icon(i["icon"], "#1f7f7a", 18)}</div>'
        f'<div><b>{_esc(i["title"])}</b><span>{_esc(i["text"])}</span></div></div>'
        for i in poster["items"]
    )
    prices = "".join(f'<div class="pr"><span>{_esc(p["label"])}</span><b>{_esc(p["price"])}</b></div>' for p in poster["prices"])
    name = _esc(partner.get("company") or " ".join(x for x in (partner.get("first_name"), partner.get("last_name")) if x))
    deal = (f'<div class="deal">Per gli ospiti di <b>{name}</b><br>sconto del <b>{values["percentuale"]}%</b> '
            f'prenotando con il codice qui sotto</div>') if discount else ""
    waves = ('<svg class="waves" width="120" height="60" viewBox="0 0 120 60"><path d="M0 20 q15 -10 30 0 t30 0 t30 0 t30 0 '
             'M0 38 q15 -10 30 0 t30 0 t30 0 t30 0" stroke="#fff" stroke-width="3" fill="none"/></svg>')
    qr = qr_svg(link, size=150, dark="#0b3d48") if link else ""
    return (
        f'<div class="a5"><div class="top">{waves}<div class="kick">{_esc(poster["kicker"])}</div>'
        f'<h1>{_title_html(poster["title"])}</h1><div class="tag">{_esc(poster["tagline"])}</div></div>'
        f'<div class="grid">{items}</div>'
        + (f'<div class="prices">{prices}</div>' if prices else "")
        + deal
        + f'<div class="bottom"><div class="qr">{qr}</div><div><div class="cta">{_esc(poster["cta"])}</div>'
        f'<div class="how">{_esc(_fill(poster["how"], values))}</div>'
        f'<div class="code">CODICE {_esc(partner.get("code"))}</div></div></div>'
        f'<div class="foot">{_esc(poster["footer"])}</div></div>'
    )


def poster_page(poster: dict[str, Any], partner: dict[str, Any], link: str, discount: float) -> str:
    """The printable page: the sheet and a bar with «Stampa»."""
    name = _esc(partner.get("company") or partner.get("first_name") or "")
    return (
        '<!doctype html><html lang="it"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1"><meta name="robots" content="noindex">'
        f'<title>{_esc(poster["title"])} · {name}</title><style>{_PAGE_CSS}</style></head><body>'
        f'<div class="bar"><b>Locandina A5 · {name}</b>'
        '<button type="button" onclick="window.print()">🖨 Stampa o salva PDF</button></div>'
        f'<div class="stage"><div class="sheet">{poster_sheet(poster, partner, link, discount)}</div></div>'
        "</body></html>"
    )


# --------------------------------------------------------------- the email
def poster_email(
    poster: dict[str, Any], partner: dict[str, Any], link: str, discount: float,
    page_url: str, qr_url: str, unsubscribe_url: str,
) -> tuple[str, str, str]:
    """Subject, plain text and HTML of the poster email.

    Email clients ignore most CSS: the poster is redrawn with tables and
    inline styles, plain colours for the gradient, and the QR code as an
    image from the public address (SVG and data: images are blocked).
    """
    values = poster_values(poster, partner, discount)
    subject = _fill(poster["email_subject"], values)
    intro = _fill(poster["email_body"], values)
    signature = _fill(poster["email_signature"], values)
    footer = ("Non vuoi più ricevere queste email? Cancella l'iscrizione: " + unsubscribe_url) if unsubscribe_url else \
        "Non vuoi più ricevere queste email? Rispondi «CANCELLAMI» e ti togliamo dall'elenco."
    text = (f"{intro}\n\nLa locandina da stampare (A5): {page_url}\n\n"
            f"Il tuo link personale, da condividere anche su WhatsApp o sul tuo sito: {link}\n\n{signature}\n\n—\n{footer}")

    font = "font-family:Arial,Helvetica,sans-serif;"
    rows = []
    items = poster["items"]
    for index in range(0, len(items), 2):
        cells = []
        for item in items[index:index + 2]:
            cells.append(
                f'<td width="50%" valign="top" style="padding:6px 8px;{font}">'
                f'<div style="font-size:13px;font-weight:bold;color:#12343b">• {_esc(item["title"])}</div>'
                f'<div style="font-size:11px;color:#5b6d72;line-height:1.3">{_esc(item["text"])}</div></td>'
            )
        if len(cells) == 1:
            cells.append('<td width="50%"></td>')
        rows.append(f"<tr>{''.join(cells)}</tr>")
    prices = "".join(
        f'<td align="center" style="padding:4px"><div style="background:#ffffff;border:1px solid #e7e1d6;border-radius:8px;padding:6px 4px;{font}">'
        f'<div style="font-size:10px;color:#5b6d72">{_esc(p["label"])}</div>'
        f'<div style="font-family:Georgia,serif;font-size:20px;color:#0b4f63">{_esc(p["price"])}</div></div></td>'
        for p in poster["prices"]
    )
    name = _esc(partner.get("company") or partner.get("first_name") or "")
    deal = (
        f'<tr><td style="padding:8px 18px 0"><div style="border:1px dashed #c9a24d;background:#fff7e3;border-radius:10px;padding:8px;text-align:center;{font}font-size:13px;color:#12343b">'
        f'Per gli ospiti di <b style="color:#a7801f">{name}</b><br>sconto del <b style="color:#a7801f;font-size:16px">{values["percentuale"]}%</b> prenotando con il codice qui sotto</div></td></tr>'
    ) if discount else ""
    words = poster["title"].split()
    title = (f'{_esc(" ".join(words[:-1]))} <span style="color:#f0c977">{_esc(words[-1])}</span>' if len(words) > 1 else _esc(poster["title"]))
    sheet = (
        f'<a href="{_esc(page_url)}" style="text-decoration:none;color:inherit;display:block">'
        '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="max-width:440px;margin:0 auto;background:#fbf8f2;border-radius:12px;overflow:hidden;border:1px solid #e3ddd2">'
        f'<tr><td style="background:#137a7e;background-image:linear-gradient(150deg,#1f9e98,#0b4f63);padding:22px 22px 18px;color:#fffaf2;{font}">'
        f'<div style="font-size:10px;letter-spacing:3px;text-transform:uppercase;opacity:.85">{_esc(poster["kicker"])}</div>'
        f'<div style="font-family:Georgia,serif;font-size:36px;line-height:1.1;margin:6px 0 4px">{title}</div>'
        f'<div style="font-size:13px">{_esc(poster["tagline"])}</div></td></tr>'
        f'<tr><td style="padding:10px 10px 0"><table role="presentation" width="100%" cellpadding="0" cellspacing="0">{"".join(rows)}</table></td></tr>'
        + (f'<tr><td style="padding:8px 14px 0"><table role="presentation" width="100%" cellpadding="0" cellspacing="0"><tr>{prices}</tr></table></td></tr>' if prices else "")
        + deal
        + '<tr><td style="padding:14px 18px 6px;background:#ffffff;border-top:1px solid #e7e1d6">'
        '<table role="presentation" width="100%" cellpadding="0" cellspacing="0"><tr>'
        f'<td width="130" valign="middle"><img src="{_esc(qr_url)}" width="120" height="120" alt="Codice QR" style="display:block;border:1px solid #e7e1d6;border-radius:8px"></td>'
        f'<td valign="middle" style="padding-left:12px;{font}"><div style="font-family:Georgia,serif;font-size:21px;color:#12343b">{_esc(poster["cta"])}</div>'
        f'<div style="font-size:12px;color:#5b6d72;margin-top:4px">{_esc(_fill(poster["how"], values))}</div>'
        f'<div style="display:inline-block;margin-top:6px;background:#12343b;color:#ffffff;font-family:Consolas,monospace;font-weight:bold;font-size:12px;letter-spacing:1px;padding:3px 8px;border-radius:5px">CODICE {_esc(partner.get("code"))}</div></td>'
        f'</tr></table></td></tr><tr><td style="background:#ffffff;padding:0 14px 10px;text-align:center;{font}font-size:10px;color:#7b8b90">{_esc(poster["footer"])}</td></tr>'
        "</table></a>"
    )

    def paragraphs(value: str) -> str:
        return "<br>".join(_esc(line) for line in value.split("\n"))

    html_body = (
        f'<div style="{font}font-size:15px;line-height:1.55;color:#1f2328;max-width:600px">'
        f"<p>{paragraphs(intro)}</p>"
        f'<div style="margin:20px 0">{sheet}</div>'
        f'<p style="text-align:center"><a href="{_esc(page_url)}" style="display:inline-block;background:#1f9e98;color:#ffffff;'
        'text-decoration:none;font-weight:bold;padding:12px 18px;border-radius:10px">🖨 Apri la locandina da stampare (A5)</a></p>'
        f'<p>Il tuo link personale, da condividere anche su WhatsApp o sul tuo sito:<br><a href="{_esc(link)}" style="color:#1f9e98">{_esc(link)}</a></p>'
        f"<p>{paragraphs(signature)}</p>"
        f'<p style="font-size:12px;color:#7b8b90">'
        + (f'Non vuoi più ricevere queste email? <a href="{_esc(unsubscribe_url)}" style="color:#7b8b90">Cancella l\'iscrizione</a>'
           if unsubscribe_url else "Non vuoi più ricevere queste email? Rispondi «CANCELLAMI».")
        + "</p></div>"
    )
    return subject, text, html_body

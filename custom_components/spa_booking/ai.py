"""Spa Booking for an artificial intelligence (3.20.0).

An assistant (a voice switchboard, a chat bot on its own computer) works the
spa like the reception does: it reads the price list and the free hours,
finds a guest, takes a request or a booking, moves or cancels one. It talks
to Home Assistant over HTTP with a key made in Impostazioni › Intelligenza
artificiale, never with a user's login, and only does what the switches next
to the key allow.

Two ways in, the same tools behind both:

``POST /api/spa_booking/ai/mcp``
    the Model Context Protocol (JSON-RPC, «streamable HTTP» answered with
    plain JSON): what Claude, ChatGPT connectors, n8n, LangChain and most
    agent frameworks plug into as a «remote MCP server».
``GET /api/spa_booking/ai/tools`` and ``POST /api/spa_booking/ai/call``
    the same tools as plain JSON — ``{"tool": …, "arguments": {…}}`` — for a
    switchboard or a script that does not speak MCP.

Every call is checked against the key (compared as a hash, in constant time)
and the switch, written in the AI log the card shows, and done as «the
assistant»: what it books says so in «created by».
"""

from __future__ import annotations

from collections import deque
from datetime import date, timedelta
import hashlib
import hmac
import json
import logging
import secrets
from typing import Any

from aiohttp import web

from homeassistant.components.http import KEY_HASS, HomeAssistantView
from homeassistant.util import dt as dt_util

from .const import DOMAIN, KEY_SETTINGS, VOUCHER_ACTIVE
from .coordinator import ACTOR, SpaBookingCoordinator
from .exceptions import SpaBookingError, ValidationError
from .normalize import _norm_clock

_LOGGER = logging.getLogger(__name__)

AI_BASE = "/api/spa_booking/ai"
MCP_URL = f"{AI_BASE}/mcp"
TOOLS_URL = f"{AI_BASE}/tools"
CALL_URL = f"{AI_BASE}/call"

#: What the switches in the card allow, in the order shown there.
AI_PERMISSIONS = ("read", "clients", "requests", "bookings", "manage")
AI_DEFAULT_PERMISSIONS = ["read", "clients", "requests"]
MCP_PROTOCOL = "2025-03-26"
#: The calls kept for the card (memory only: gone at restart).
AI_LOG: deque[dict[str, Any]] = deque(maxlen=200)


def new_key() -> tuple[str, str]:
    """A fresh key and the hash that is stored (the key itself never is)."""
    key = "sbai_" + secrets.token_urlsafe(32)
    return key, hashlib.sha256(key.encode()).hexdigest()


def key_ok(settings: dict[str, Any], provided: str) -> bool:
    stored = str(settings.get("ai_key_hash") or "")
    if not stored or not provided:
        return False
    return hmac.compare_digest(stored, hashlib.sha256(provided.encode()).hexdigest())


# ------------------------------------------------------------------ helpers


def _day(value: Any) -> date:
    try:
        return date.fromisoformat(str(value or "").strip()[:10])
    except ValueError as err:
        raise ValidationError("Data non valida: usa AAAA-MM-GG") from err


def _clock(value: Any) -> str:
    clock = _norm_clock(value)
    if not clock:
        raise ValidationError("Ora non valida: usa HH:MM")
    return clock


def _digits(phone: Any) -> str:
    return "".join(ch for ch in str(phone or "") if ch.isdigit())


def _treatment(coordinator: SpaBookingCoordinator, treatment_id: Any) -> dict[str, Any]:
    wanted = str(treatment_id or "").strip()
    found = next((t for t in coordinator.treatments if t["id"] == wanted), None)
    if found is None:  # the assistant may say the name
        found = next((t for t in coordinator.treatments if t.get("name", "").lower() == wanted.lower()), None)
    if found is None or not found.get("active", True):
        raise ValidationError(f"Trattamento non trovato: {wanted}. Usa un id di «listino».")
    return found


def _appointment_view(coordinator: SpaBookingCoordinator, appointment: dict[str, Any]) -> dict[str, Any]:
    payload = coordinator.appointment_payload(appointment)
    start = dt_util.parse_datetime(str(appointment.get("start") or ""))
    local = dt_util.as_local(start) if start else None
    operator = payload.get("operator") or {}
    return {
        "id": appointment["id"],
        "codice": appointment.get("code") or "",
        "data": local.date().isoformat() if local else "",
        "ora": local.strftime("%H:%M") if local else "",
        "trattamento": (payload.get("treatment") or {}).get("name") or "",
        "trattamento_id": appointment.get("treatment_id"),
        "cliente": (payload.get("client") or {}).get("full_name") or "",
        "telefono": (payload.get("client") or {}).get("phone") or "",
        "stato": appointment.get("status"),
        "operatrice": operator.get("name") or "",
        "prezzo": payload.get("price"),
        "gruppo": appointment.get("batch_id") or "",
    }


def _client_find(coordinator: SpaBookingCoordinator, text: str) -> list[dict[str, Any]]:
    text = str(text or "").strip().lower()
    digits = _digits(text)
    if len(text) < 2:
        raise ValidationError("Scrivi almeno 2 caratteri, o il telefono")
    out = []
    for client in coordinator.clients:
        name = f"{client.get('first_name', '')} {client.get('last_name', '')}".strip().lower()
        phone = _digits(client.get("phone"))
        if (len(digits) >= 6 and phone.endswith(digits[-9:])) or (not digits and text in name):
            out.append(client)
    return out[:10]


# -------------------------------------------------------------------- tools


async def _info(c: SpaBookingCoordinator, args: dict[str, Any]) -> dict[str, Any]:
    settings = c._data[KEY_SETTINGS]
    now = dt_util.now()
    return {
        "nome": settings.get("guest_header") or "Spa",
        "adesso": now.isoformat(timespec="minutes"),
        "oggi": now.date().isoformat(),
        "giorno_settimana": ["lunedì", "martedì", "mercoledì", "giovedì", "venerdì", "sabato", "domenica"][now.weekday()],
        "orario_proposte": {"apertura": settings.get("web_open_time") or "09:00", "chiusura": settings.get("web_close_time") or "20:00",
                            "pausa": [settings.get("web_break_start") or "", settings.get("web_break_end") or ""]},
        "chi_sei": settings.get("ai_name") or "Assistente IA",
        "permessi": settings.get("ai_permissions") or [],
        "istruzioni": str(settings.get("ai_instructions") or ""),
        "regole": [
            "Prezzi in euro, IVA inclusa.",
            "Prima di prenotare controlla sempre «disponibilita» per quel giorno e trattamento.",
            "Chiedi sempre nome, cognome e telefono dell'ospite.",
            "Una prenotazione con in_attesa=true resta da confermare dalla reception.",
        ],
    }


async def _listino(c: SpaBookingCoordinator, args: dict[str, Any]) -> dict[str, Any]:
    categories = {cat["id"]: cat.get("name") or "" for cat in c.categories}
    treatments = []
    for t in c.treatments:
        if not t.get("active", True):
            continue
        treatments.append({
            "id": t["id"], "nome": t.get("name") or "", "categoria": categories.get(t.get("category_id"), ""),
            "durata_min": t.get("duration_min"), "prezzo": t.get("price"),
            "persone_insieme_max": t.get("max_parallel") or None,
            "con_operatrice": c._treatment_requires_operator(t),
            "descrizione": t.get("description") or "",
            "sul_sito": t.get("web_visible", True),
        })
    names = {t["id"]: t.get("name") or "" for t in c.treatments}
    packages = [{
        "chiave": p["key"], "nome": p.get("name") or "", "prezzo": p.get("price"), "persone": p.get("people"),
        "trattamenti": [{"id": tid, "nome": names.get(tid, "")} for tid in p.get("treatment_ids") or []],
        "inclusi": p.get("extras") or [], "nota": p.get("note") or "",
    } for p in c.shop_packages() if not p.get("hidden_desk")]
    accessories = [{"id": a.get("id"), "nome": a.get("label"), "prezzo": a.get("price")} for a in c.accessories]
    return {"trattamenti": treatments, "pacchetti": packages, "accessori": accessories}


async def _disponibilita(c: SpaBookingCoordinator, args: dict[str, Any]) -> dict[str, Any]:
    day = _day(args.get("data"))
    treatment = _treatment(c, args.get("trattamento_id"))
    people = max(1, min(20, int(args.get("persone") or 1)))
    first = await c.async_public_availability(day, treatment["id"], strict=False)
    times = [slot["time"] for slot in first["slots"]]
    if people > 1:
        # Every person of the party needs her own place (operator or seat).
        fit = []
        for clock in times:
            planned: list[dict[str, Any]] = []
            ok = True
            for _ in range(people):
                check = await c.async_public_availability(day, treatment["id"], planned, strict=False)
                if clock not in {s["time"] for s in check["slots"]}:
                    ok = False
                    break
                planned.append(c.plan_public_entry(day, treatment["id"], clock, planned))
            if ok:
                fit.append(clock)
        times = fit
    return {"data": day.isoformat(), "trattamento": treatment.get("name"), "trattamento_id": treatment["id"],
            "durata_min": first["duration_min"], "persone": people, "orari_liberi": times,
            "nota": "Nessun orario libero quel giorno." if not times else ""}


async def _voucher(c: SpaBookingCoordinator, args: dict[str, Any]) -> dict[str, Any]:
    code = str(args.get("codice") or "").strip().upper()
    voucher = next((v for v in c.vouchers if v.get("code", "").upper() == code), None)
    if voucher is None:
        return {"trovato": False}
    names = {t["id"]: t.get("name") or "" for t in c.treatments}
    return {
        "trovato": True, "codice": voucher["code"], "valido": voucher.get("status") == VOUCHER_ACTIVE
        and not (voucher.get("expires_on") and voucher["expires_on"] < dt_util.now().date().isoformat()),
        "stato": voucher.get("status"), "scadenza": voucher.get("expires_on") or "",
        "credito_residuo": c._voucher_credit(voucher),
        "trattamenti": [names.get(tid, tid) for p in voucher.get("people") or [] for tid in p.get("treatment_ids") or []],
        "intestato_a": voucher.get("recipient_name") or voucher.get("buyer_name") or "",
    }


async def _cerca_cliente(c: SpaBookingCoordinator, args: dict[str, Any]) -> dict[str, Any]:
    today = dt_util.now().date().isoformat()
    out = []
    for client in _client_find(c, args.get("testo") or args.get("telefono") or ""):
        upcoming = [_appointment_view(c, a) for a in c.appointments
                    if a.get("client_id") == client["id"] and a.get("status") != "cancelled" and str(a.get("start") or "")[:10] >= today]
        out.append({"id": client["id"], "nome": client.get("first_name") or "", "cognome": client.get("last_name") or "",
                    "telefono": client.get("phone") or "", "email": client.get("email") or "",
                    "prossimi_appuntamenti": sorted(upcoming, key=lambda a: (a["data"], a["ora"]))[:10]})
    return {"clienti": out}


async def _agenda(c: SpaBookingCoordinator, args: dict[str, Any]) -> dict[str, Any]:
    day = _day(args.get("data")).isoformat()
    rows = []
    for appointment in c.appointments:
        start = dt_util.parse_datetime(str(appointment.get("start") or ""))
        if start and dt_util.as_local(start).date().isoformat() == day and appointment.get("status") != "cancelled":
            rows.append(_appointment_view(c, appointment))
    return {"data": day, "appuntamenti": sorted(rows, key=lambda a: a["ora"])}


def _guest(args: dict[str, Any]) -> dict[str, str]:
    guest = args.get("cliente") if isinstance(args.get("cliente"), dict) else args
    out = {
        "first_name": str(guest.get("nome") or "").strip()[:60],
        "last_name": str(guest.get("cognome") or "").strip()[:60],
        "phone": str(guest.get("telefono") or "").strip()[:30],
        "email": str(guest.get("email") or "").strip()[:120],
    }
    if not (out["first_name"] or out["last_name"]):
        raise ValidationError("Manca il nome dell'ospite")
    if not out["phone"]:
        raise ValidationError("Manca il telefono dell'ospite")
    return out


def _voci(args: dict[str, Any]) -> list[dict[str, Any]]:
    voci = args.get("voci")
    if not isinstance(voci, list) or not voci:
        raise ValidationError("Indica almeno una voce: trattamento_id, data, ora (e persona)")
    return [v for v in voci if isinstance(v, dict)]


async def _crea_richiesta(c: SpaBookingCoordinator, args: dict[str, Any]) -> dict[str, Any]:
    guest = _guest(args)
    day = _day(args.get("data"))
    entries = []
    for index, voce in enumerate(_voci(args)):
        item = {"treatment_id": _treatment(c, voce.get("trattamento_id"))["id"], "time": _clock(voce.get("ora"))}
        item["person"] = int(voce.get("persona", index if args.get("persone") else 0) or 0)
        if voce.get("pacchetto"):
            item["package_key"] = item["package_group"] = str(voce["pacchetto"])[:40]
        entries.append(item)
    name = c._data[KEY_SETTINGS].get("ai_name") or "Assistente IA"
    result = await c.async_create_request(
        **guest, date=day.isoformat(), people=int(args.get("persone") or 1), entries=entries,
        notes=f"[{name}] {str(args.get('note') or '').strip()}".strip(),
    )
    return {"codice": result.get("code"), "data": result.get("date"), "stato": result.get("status"),
            "nota": "Richiesta registrata: la reception la conferma."}


async def _crea_prenotazione(c: SpaBookingCoordinator, args: dict[str, Any]) -> dict[str, Any]:
    guest = _guest(args)
    pending = bool(args.get("in_attesa"))
    rows: dict[str, dict[str, Any]] = {}
    for index, voce in enumerate(_voci(args)):
        treatment = _treatment(c, voce.get("trattamento_id"))
        day = _day(voce.get("data") or args.get("data"))
        clock = _clock(voce.get("ora"))
        entry: dict[str, Any] = {**guest, "start": f"{day.isoformat()}T{clock}:00",
                                 "person": int(voce.get("persona", index) or 0)}
        if voce.get("pacchetto"):
            entry["package_key"] = str(voce["pacchetto"])[:40]
            entry["package_group"] = str(voce.get("gruppo_pacchetto") or voce["pacchetto"])[:40]
        if args.get("note"):
            entry["notes"] = str(args["note"])[:500]
        row = rows.setdefault(treatment["id"], {"treatment_id": treatment["id"], "pending": pending, "entries": []})
        row["entries"].append(entry)
    result = await c.async_create_bookings(list(rows.values()))
    booked = [_appointment_view(c, a) for a in result.get("appointments") or []]
    return {"prenotati": booked, "in_attesa": pending,
            "nota": "Prenotazione inserita." + (" Resta da confermare dalla reception." if pending else "")}


async def _annulla(c: SpaBookingCoordinator, args: dict[str, Any]) -> dict[str, Any]:
    appointment_id = str(args.get("appuntamento_id") or "")
    result = await c.async_cancel_appointment(appointment_id, reason=str(args.get("motivo") or "Annullato dall'assistente IA"),
                                              whole_group=bool(args.get("tutto_il_gruppo")))
    if args.get("avvisa_ospite", True):
        try:
            await c.async_send_cancel_message(result.get("cancelled_ids") or [appointment_id])
        except SpaBookingError as err:
            _LOGGER.info("Annullamento senza messaggio: %s", err)
    return {"annullati": result.get("cancelled_ids") or [appointment_id]}


async def _sposta(c: SpaBookingCoordinator, args: dict[str, Any]) -> dict[str, Any]:
    appointment_id = str(args.get("appuntamento_id") or "")
    day = _day(args.get("data"))
    clock = _clock(args.get("ora"))
    hour, minute = (int(part) for part in clock.split(":"))
    start = dt_util.start_of_local_day(day) + timedelta(hours=hour, minutes=minute)
    await c.async_update_appointment(appointment_id, start=start)
    appointment = next(a for a in c.appointments if a["id"] == appointment_id)
    if args.get("avvisa_ospite", True):
        try:
            await c.async_send_guest_summary(appointment_ids=[appointment_id], kind="change")
        except SpaBookingError as err:
            _LOGGER.info("Spostamento senza messaggio: %s", err)
    return {"appuntamento": _appointment_view(c, appointment)}


_S = {"type": "string"}
_D = {"type": "string", "description": "Data AAAA-MM-GG"}
_T = {"type": "string", "description": "Ora HH:MM"}
_GUEST = {"nome": _S, "cognome": _S, "telefono": _S, "email": _S}
_VOCI = {"type": "array", "items": {"type": "object", "properties": {
    "trattamento_id": _S, "data": _D, "ora": _T,
    "persona": {"type": "integer", "description": "0 per la prima persona del gruppo, 1 per la seconda…"},
    "pacchetto": {"type": "string", "description": "Chiave del pacchetto (da «listino»), se la voce ne fa parte"},
}, "required": ["trattamento_id", "ora"]}}

#: name: (permission, handler, description, input schema)
TOOLS: dict[str, tuple[str, Any, str, dict[str, Any]]] = {
    "info_spa": ("read", _info, "Data e ora di adesso, nome della spa, orari, regole e istruzioni della reception. Chiamalo per primo.",
                 {"type": "object", "properties": {}}),
    "listino": ("read", _listino, "Trattamenti attivi con id, categoria, durata e prezzo; pacchetti con prezzo e persone; accessori.",
                {"type": "object", "properties": {}}),
    "disponibilita": ("read", _disponibilita, "Orari liberi di un giorno per un trattamento, per una o più persone insieme.",
                      {"type": "object", "properties": {"data": _D, "trattamento_id": _S, "persone": {"type": "integer", "default": 1}},
                       "required": ["data", "trattamento_id"]}),
    "verifica_voucher": ("read", _voucher, "Stato, scadenza, credito e trattamenti di un voucher o gift card dal codice.",
                         {"type": "object", "properties": {"codice": _S}, "required": ["codice"]}),
    "cerca_cliente": ("clients", _cerca_cliente, "Cerca un ospite per telefono o nome; con i suoi prossimi appuntamenti.",
                      {"type": "object", "properties": {"testo": {"type": "string", "description": "Telefono o nome"}}, "required": ["testo"]}),
    "agenda_giorno": ("clients", _agenda, "Gli appuntamenti di un giorno (ora, trattamento, ospite, stato).",
                      {"type": "object", "properties": {"data": _D}, "required": ["data"]}),
    "crea_richiesta": ("requests", _crea_richiesta,
                       "Registra una richiesta di appuntamento: arriva alla reception, che la conferma. Non occupa l'orario.",
                       {"type": "object", "properties": {**_GUEST, "data": _D, "persone": {"type": "integer"}, "voci": _VOCI, "note": _S},
                        "required": ["nome", "telefono", "data", "voci"]}),
    "crea_prenotazione": ("bookings", _crea_prenotazione,
                          "Inserisce una prenotazione in agenda (una voce per persona e trattamento). Controlla prima «disponibilita». "
                          "Per un pacchetto metti la sua chiave in ogni voce. in_attesa=true la lascia da confermare.",
                          {"type": "object", "properties": {"cliente": {"type": "object", "properties": _GUEST, "required": ["nome", "telefono"]},
                                                            "voci": _VOCI, "in_attesa": {"type": "boolean"}, "note": _S},
                           "required": ["cliente", "voci"]}),
    "annulla_prenotazione": ("manage", _annulla, "Annulla un appuntamento (id da «cerca_cliente» o «agenda_giorno»), di base avvisando l'ospite.",
                             {"type": "object", "properties": {"appuntamento_id": _S, "motivo": _S, "tutto_il_gruppo": {"type": "boolean"},
                                                               "avvisa_ospite": {"type": "boolean", "default": True}},
                              "required": ["appuntamento_id"]}),
    "sposta_prenotazione": ("manage", _sposta, "Sposta un appuntamento a un altro giorno/ora (stessi controlli della reception) e avvisa l'ospite.",
                            {"type": "object", "properties": {"appuntamento_id": _S, "data": _D, "ora": _T,
                                                              "avvisa_ospite": {"type": "boolean", "default": True}},
                             "required": ["appuntamento_id", "data", "ora"]}),
}


def tools_for(settings: dict[str, Any]) -> list[dict[str, Any]]:
    allowed = set(settings.get("ai_permissions") or [])
    return [{"name": name, "description": desc, "inputSchema": schema}
            for name, (perm, _h, desc, schema) in TOOLS.items() if perm in allowed]


async def run_tool(coordinator: SpaBookingCoordinator, name: str, args: dict[str, Any]) -> dict[str, Any]:
    """Run one tool as the assistant; log it. Errors come back as ValidationError."""
    settings = coordinator._data[KEY_SETTINGS]
    if name not in TOOLS:
        raise ValidationError(f"Strumento sconosciuto: {name}")
    permission, handler, _desc, _schema = TOOLS[name]
    if permission not in set(settings.get("ai_permissions") or []):
        raise ValidationError(f"Permesso non concesso all'assistente: {name}. Si attiva in Impostazioni › Intelligenza artificiale.")
    token = ACTOR.set(("", str(settings.get("ai_name") or "Assistente IA")))
    entry = {"at": dt_util.utcnow().isoformat(timespec="seconds"), "tool": name,
             "args": json.dumps(args, ensure_ascii=False)[:300], "ok": True, "result": ""}
    try:
        result = await handler(coordinator, args if isinstance(args, dict) else {})
        entry["result"] = json.dumps(result, ensure_ascii=False, default=str)[:300]
        return result
    except SpaBookingError as err:
        entry.update(ok=False, result=str(err))
        raise
    except (TypeError, ValueError) as err:
        entry.update(ok=False, result=str(err))
        raise ValidationError(f"Argomenti non validi: {err}") from err
    finally:
        ACTOR.reset(token)
        AI_LOG.appendleft(entry)
        coordinator.async_set_updated_data(coordinator._data)


# -------------------------------------------------------------------- views


class _AiView(HomeAssistantView):
    requires_auth = False
    cors_allowed = True

    def _gate(self, request: web.Request) -> SpaBookingCoordinator | web.Response:
        from .public import RATE_LIMITER, _bearer

        coordinator = request.app[KEY_HASS].data.get(DOMAIN)
        if not isinstance(coordinator, SpaBookingCoordinator):
            return web.Response(status=404, text="Not found")
        settings = coordinator._data[KEY_SETTINGS]
        if not settings.get("ai_enabled"):
            return web.Response(status=404, text="Not found")
        if not RATE_LIMITER.allow("ai", str(request.remote or "")):
            return self.json({"message": "Troppe richieste"}, status_code=429)
        if not key_ok(settings, _bearer(request)):
            return self.json({"message": "Chiave non valida"}, status_code=401)
        return coordinator


class SpaBookingAiToolsView(_AiView):
    url = TOOLS_URL
    name = "api:spa_booking:ai_tools"

    async def get(self, request: web.Request) -> web.Response:
        coordinator = self._gate(request)
        if isinstance(coordinator, web.Response):
            return coordinator
        return self.json({"tools": tools_for(coordinator._data[KEY_SETTINGS])})


class SpaBookingAiCallView(_AiView):
    url = CALL_URL
    name = "api:spa_booking:ai_call"

    async def post(self, request: web.Request) -> web.Response:
        coordinator = self._gate(request)
        if isinstance(coordinator, web.Response):
            return coordinator
        try:
            body = json.loads(await request.text() or "{}")
            result = await run_tool(coordinator, str(body.get("tool") or ""), body.get("arguments") or {})
            return self.json({"ok": True, "result": result})
        except (ValueError, AttributeError):
            return self.json({"ok": False, "error": "Corpo non valido: {\"tool\": …, \"arguments\": {…}}"}, status_code=400)
        except SpaBookingError as err:
            return self.json({"ok": False, "error": str(err)}, status_code=400)
        except Exception:  # noqa: BLE001
            _LOGGER.exception("Chiamata dell'assistente IA fallita")
            return self.json({"ok": False, "error": "Errore interno"}, status_code=500)


class SpaBookingAiMcpView(_AiView):
    """MCP over HTTP: one JSON-RPC message (or a batch) per POST, a JSON answer."""

    url = MCP_URL
    name = "api:spa_booking:ai_mcp"

    async def get(self, request: web.Request) -> web.Response:
        # No server-to-client stream: the client uses POST only.
        return web.Response(status=405, headers={"Allow": "POST"})

    async def post(self, request: web.Request) -> web.Response:
        coordinator = self._gate(request)
        if isinstance(coordinator, web.Response):
            return coordinator
        try:
            body = json.loads(await request.text() or "null")
        except ValueError:
            return self.json({"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "Parse error"}})
        messages = body if isinstance(body, list) else [body]
        answers = [a for a in [await self._one(coordinator, m) for m in messages] if a is not None]
        if not answers:
            return web.Response(status=202)
        return self.json(answers if isinstance(body, list) else answers[0])

    async def _one(self, coordinator: SpaBookingCoordinator, message: Any) -> dict[str, Any] | None:
        if not isinstance(message, dict) or message.get("jsonrpc") != "2.0":
            return {"jsonrpc": "2.0", "id": None, "error": {"code": -32600, "message": "Invalid Request"}}
        method = message.get("method")
        msg_id = message.get("id")
        if msg_id is None:  # a notification (initialized, cancelled…): nothing to answer
            return None
        settings = coordinator._data[KEY_SETTINGS]

        def ok(result: dict[str, Any]) -> dict[str, Any]:
            return {"jsonrpc": "2.0", "id": msg_id, "result": result}

        if method == "initialize":
            return ok({
                "protocolVersion": MCP_PROTOCOL,
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": {"name": "spa-booking", "version": coordinator_version()},
                "instructions": "Sei l'assistente della reception della spa. Chiama prima «info_spa» e «listino». "
                + str(settings.get("ai_instructions") or ""),
            })
        if method == "ping":
            return ok({})
        if method == "tools/list":
            return ok({"tools": tools_for(settings)})
        if method == "tools/call":
            params = message.get("params") or {}
            try:
                result = await run_tool(coordinator, str(params.get("name") or ""), params.get("arguments") or {})
                text = json.dumps(result, ensure_ascii=False, default=str)
                return ok({"content": [{"type": "text", "text": text}], "structuredContent": result, "isError": False})
            except SpaBookingError as err:
                return ok({"content": [{"type": "text", "text": str(err)}], "isError": True})
            except Exception:  # noqa: BLE001
                _LOGGER.exception("Strumento MCP fallito")
                return ok({"content": [{"type": "text", "text": "Errore interno"}], "isError": True})
        if method in ("resources/list", "prompts/list"):
            return ok({method.split("/")[0]: []})
        return {"jsonrpc": "2.0", "id": msg_id, "error": {"code": -32601, "message": f"Method not found: {method}"}}


def coordinator_version() -> str:
    from .coordinator import INTEGRATION_VERSION

    return str(INTEGRATION_VERSION)


__all__ = ["AI_LOG", "AI_PERMISSIONS", "SpaBookingAiCallView", "SpaBookingAiMcpView", "SpaBookingAiToolsView", "new_key", "run_tool"]

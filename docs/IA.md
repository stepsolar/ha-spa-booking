# Spa Booking per un'intelligenza artificiale

Dalla 3.20 un assistente IA (per esempio sul computer del centralino
telefonico) può lavorare in Spa Booking come la reception. Si configura in
**Configurazione › Impostazioni › Intelligenza artificiale**.

## 1. In Spa Booking

1. Accendi **Collegamento attivo** e scegli il **nome** dell'assistente.
2. **Crea la chiave** e copiala subito: non viene più mostrata (se si perde,
   se ne crea un'altra e la vecchia smette di funzionare).
3. Scegli **cosa può fare** e scrivi le **istruzioni** (tono, cosa proporre).
4. **Salva**.

## 2. Sul computer dell'IA

Ogni chiamata porta l'intestazione:

```
Authorization: Bearer sbai_…la-chiave…
```

L'indirizzo è quello di Home Assistant (in rete locale per esempio
`http://homeassistant.local:8123`, da fuori l'indirizzo https esterno).

### MCP (consigliato)

Server MCP remoto, trasporto «streamable HTTP» (solo POST, risposte JSON):

```
https://<home-assistant>/api/spa_booking/ai/mcp
```

Esempio di configurazione di un client MCP:

```json
{
  "mcpServers": {
    "spa-booking": {
      "type": "http",
      "url": "https://<home-assistant>/api/spa_booking/ai/mcp",
      "headers": { "Authorization": "Bearer sbai_…" }
    }
  }
}
```

### JSON semplice

```
GET  https://<home-assistant>/api/spa_booking/ai/tools      → {"tools": [...]}
POST https://<home-assistant>/api/spa_booking/ai/call
     {"tool": "disponibilita", "arguments": {"data": "2026-12-05", "trattamento_id": "trt_ingresso_90", "persone": 2}}
     → {"ok": true, "result": {...}}   oppure   {"ok": false, "error": "…"} (HTTP 400)
```

```bash
curl -s https://<home-assistant>/api/spa_booking/ai/call \
  -H "Authorization: Bearer sbai_…" -H "Content-Type: application/json" \
  -d '{"tool":"listino","arguments":{}}'
```

## 3. Gli strumenti

| Strumento | Permesso | Cosa fa |
|---|---|---|
| `info_spa` | Consultare | data e ora di adesso, nome, orari, regole e istruzioni: da chiamare per primo |
| `listino` | Consultare | trattamenti (id, categoria, durata, prezzo), pacchetti (chiave, prezzo, persone, trattamenti), accessori |
| `disponibilita` | Consultare | `data`, `trattamento_id`, `persone` → orari liberi |
| `verifica_voucher` | Consultare | `codice` → valido, scadenza, credito, trattamenti |
| `cerca_cliente` | Ospiti e agenda | `testo` (telefono o nome) → ospiti e prossimi appuntamenti |
| `agenda_giorno` | Ospiti e agenda | `data` → appuntamenti del giorno |
| `crea_richiesta` | Richieste | `nome`, `cognome`, `telefono`, `email`, `data`, `persone`, `voci` [{`trattamento_id`, `ora`, `persona`, `pacchetto`}], `note` → codice della richiesta (la conferma la reception) |
| `crea_prenotazione` | Prenotazioni | `cliente` {`nome`, `cognome`, `telefono`, `email`}, `voci` [{`trattamento_id`, `data`, `ora`, `persona`, `pacchetto`}], `in_attesa`, `note` → appuntamenti inseriti |
| `sposta_prenotazione` | Spostare e annullare | `appuntamento_id`, `data`, `ora`, `avvisa_ospite` |
| `annulla_prenotazione` | Spostare e annullare | `appuntamento_id`, `motivo`, `tutto_il_gruppo`, `avvisa_ospite` |

- Date `AAAA-MM-GG`, ore `HH:MM`, prezzi in euro IVA inclusa.
- Un gruppo: una voce per persona (`persona` 0, 1, 2…); un pacchetto: la sua
  `chiave` (da `listino`) in ogni voce.
- Una prenotazione passa gli stessi controlli della reception (orari,
  chiusure, operatrici, capienza): se non va, l'errore dice perché.
- Quello che l'IA inserisce ha in «inserito da» il nome dell'assistente; le
  ultime chiamate si vedono nella scheda.

## 4. Sicurezza

- Con il collegamento spento gli indirizzi rispondono 404.
- La chiave è salvata solo come hash; una chiave sbagliata riceve 401, troppe
  chiamate 429 (1200 ogni 10 minuti per indirizzo).
- Dai all'IA solo i permessi che servono; *Spostare e annullare* avvisa
  l'ospite.

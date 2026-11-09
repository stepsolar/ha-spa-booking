# Spa Booking — integrazione Home Assistant

Gestione degli appuntamenti della SPA dentro Home Assistant: categorie,
trattamenti con durata propria, operatrici, schede cliente, agenda del giorno
per operatrice e per categoria, pagamenti, voucher, richieste dal sito web,
promemoria e report automatici su WhatsApp e Telegram.

Versione corrente: **2.1.2** — documentazione completa in
[`custom_components/spa_booking/README.md`](custom_components/spa_booking/README.md).

## Funzionalità principali

- **Agenda del giorno** per operatrici e categorie, vista singola o raggruppata
  per cliente.
- **Prenotazioni multipersona e multitrattamento** in un'unica operazione, con
  controllo di sovrapposizioni, pause delle operatrici, fasce orarie e
  esclusioni tra categorie.
- **Offerte alle operatrici** su WhatsApp/Telegram con conferma, rifiuto e
  passaggio automatico alla successiva libera.
- **Pagamenti** multi-metodo, acconti e saldo.
- **Clienti** con deduplicazione per telefono (anche numeri esteri).
- **Voucher regalo e voucher fedeltà**, con avviso di scadenza.
- **Richieste dal sito WordPress** tramite API pubblica protetta da token e
  limite di richieste.
- **Attività automatiche** (promemoria, recensioni, promo, report mensile)
  eseguite dall'integrazione stessa, con orario di silenzio.
- **Permessi per utente** (lettura, operatore, manager, admin) applicati anche
  lato server.
- **Backup e ripristino** in JSON e CSV clienti.

## Installazione

### HACS (consigliato)
1. HACS → Integrazioni → tre puntini → *Repository personalizzati* →
   `https://github.com/stepsolar/ha-spa-booking`, categoria *Integration*.
2. Installa **Spa Booking** e riavvia Home Assistant.
3. Impostazioni → Dispositivi e servizi → Aggiungi integrazione → *Spa Booking*.

### Manuale
Copia `custom_components/spa_booking/` in `/config/custom_components/` e
riavvia. La card e il modulo del sito sono inclusi nella cartella
`frontend/`: non serve copiare altro.

La card di gestione viene caricata automaticamente in ogni dashboard; è
disponibile anche come pagina a sé su `/spa_booking`.

## Modulo per il sito web

Nella card: Configurazione → Sito web → attiva il sito, poi **Copia** e
incolla il codice in un blocco "HTML personalizzato" di WordPress. Il token è
già inserito.

## Aggiornare dalla 2.0.x

- La cartella `/config/www/spa_booking/` non viene più letta e si può
  cancellare.
- Le automazioni del vecchio `packages/spa_booking.yaml` che chiamavano
  promemoria, offerte, promo e report non servono più: l'integrazione le
  esegue da sola e non invia mai due volte, quindi si possono togliere con
  calma.
- Gli utenti non amministratori di Home Assistant devono avere un livello
  nella scheda **Accessi**, altrimenti i servizi rifiutano le loro chiamate
  (la card già non mostrava nulla a chi non aveva accesso).

## Sviluppo

```bash
pip install homeassistant pytest ruff
ruff check --select F,E9,B,ASYNC custom_components tests
python -m pytest tests
node tests/frontend/form_test.js custom_components/spa_booking/frontend/spa-booking-form.txt
node tests/frontend/card_request_test.js custom_components/spa_booking/frontend/spa-booking-card.js
node tests/frontend/card_spa_test.js custom_components/spa_booking/frontend/spa-booking-card.js
```

La CI (`.github/workflows/ci.yml`) esegue lint, test, controllo della card,
hassfest e validazione HACS a ogni push e pull request. Lavora su un branch e
apri una pull request: `main` resta sempre installabile.

## Changelog

- **v2.1.2**: nuovo stile della scheda Spa. Riquadri divisi in sezioni (Luci,
  Clima, Servizi e sensori) con riepilogo, colore secondo il tipo (luci ambra,
  servizi verde acqua, clima arancio/azzurro), termostato con temperatura
  grande e solo − e +, sensori con il valore in evidenza, una sola barra di
  luminosità per luce, entità mancanti mostrate come "Non disponibile" invece
  di bloccare la scheda. Le sezioni si spengono dal pulsante "Sezioni" in
  modalità modifica.
- **v2.1.1**: nella scheda Richiesta, con 2 o più persone compare un box per
  persona (trattamenti, orari e accessori di ciascuna, "Copia dalla 1ª"); alla
  conferma ogni trattamento viene prenotato solo per la sua persona. "Modifica"
  su una richiesta ora la aggiorna invece di crearne una nuova. "Crea
  richiesta" e "Salva cliente" dai messaggi WhatsApp non aggiungono più "39"
  ai numeri stranieri.
- **v2.1.0**: pianificatore interno (niente più package YAML), card e modulo
  dentro l'integrazione (compatibile HACS), permessi applicati lato server e
  segreti nascosti ai non amministratori, limite di richieste sull'API del
  sito, pausa dell'operatrice in entrambi i sensi, offerta alla prima
  operatrice libera, disponibilità del sito allineata alle regole della
  reception, report mensile completo fino all'ultimo giorno, rollback corretto
  della modifica di gruppo, invii WhatsApp fuori dal lock dei dati, avvisi di
  scadenza voucher funzionanti, test e CI.
- **v2.0.16**: ripristinata la card di gestione (sovrascritta per errore dal
  modulo del sito) e riscritto il modulo WordPress; verifica voucher dal sito
  di nuovo funzionante; "non confermo"/"non va bene" letti come rifiuto;
  numeri TIM 390-393/397, fissi e stranieri convertiti correttamente.
- **v2.0.15**: voucher precompilato dal sito tramite `/public/treatments`.
- **v2.0.14**: ampia zona di tocco in agenda per aprire il dettaglio.
- **v2.0.13**: avviso di sovrapposizione in modifica, storico cliente
  cliccabile, modifica gruppo senza errore di tupla.
- **v2.0.12**: annulla modifica gruppo torna all'agenda; icone MDI autonome.
- **v2.0.10**: servizio `get_dashboard_config`, aggiornamento in tempo reale.
- **v2.0.8–2.0.9**: tipo di riquadro nella scheda Spa, salvato correttamente.
- **v2.0.5–2.0.7**: raggruppamento per cliente e giornata, stato delle offerte
  conservato in modifica, check-in dall'agenda.
- **v2.0.0–2.0.4**: backup JSON completo, editor di gruppo multi-riga.

## Licenza e autore

Autore: stepsolar. Segnalazioni e proposte:
`https://github.com/stepsolar/ha-spa-booking/issues`.

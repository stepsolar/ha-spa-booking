# Spa Booking — integrazione Home Assistant

Gestione degli appuntamenti della SPA dentro Home Assistant: categorie,
trattamenti con durata propria, operatrici, schede cliente, agenda del giorno
per operatrice e per categoria, pagamenti, voucher, richieste dal sito web,
promemoria e report automatici su WhatsApp e Telegram.

Versione corrente: **2.2.0** — documentazione completa in
[`custom_components/spa_booking/README.md`](custom_components/spa_booking/README.md).

**[Guida alle schede con le anteprime](docs/GUIDA.md)**: ogni scheda della
dashboard con la spiegazione di ogni funzione.

![Agenda](docs/anteprime/01-agenda.png)

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
- **Login personale e ruoli** (Massaggiatrice, Reception, Manager,
  Amministratore) applicati anche lato server, utenti creati dalla card e
  **PIN** per il tablet condiviso della reception.
- **Prefisso internazionale** accanto a ogni campo telefono, anche nel modulo
  del sito.
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

## WhatsApp integrato (beta, dalla 2.2.0b1)

Spa Booking può collegarsi da solo al numero WhatsApp dell'hotel, come
WhatsApp Web, senza l'add-on WAHA:

1. Configurazione › WhatsApp › **Collegamento WhatsApp** › scegli
   «WhatsApp integrato (beta)».
2. Premi **Collega WhatsApp** e, dal telefono dell'hotel, WhatsApp ›
   Dispositivi collegati › Collega un dispositivo: inquadra il codice QR.
   Se la card è aperta sullo stesso telefono, scrivi il numero e premi
   **Ottieni codice**, poi «Collega con il numero di telefono».
3. Prova un invio con «Prova WhatsApp». Offerte, risposte, reazioni e
   messaggi in arrivo funzionano come con WAHA.

Per tornare a WAHA basta scegliere «Add-on WAHA». Come WAHA, non è un canale
ufficiale di WhatsApp: il rischio sul numero è lo stesso. Il telefono deve
restare con WhatsApp installato e connettersi almeno ogni 14 giorni. Per ora
funziona su processori Intel/AMD a 64 bit (mini PC, NUC, macchine virtuali).

## Modulo per il sito web

Nella card: Configurazione › Impostazioni › Sito web. Attiva il sito, poi
premi **Copia codice per il sito** e incolla il codice in un blocco «HTML
personalizzato» di WordPress. Il codice ha già il token ed è di due righe:

```html
<div id="spa-booking"></div>
<script src="https://IL-TUO-HOME-ASSISTANT/api/spa_booking/public/form.js" data-token="..." async></script>
```

Il modulo arriva da Home Assistant: quando aggiorni Spa Booking il sito
mostra subito la nuova versione e WordPress non si tocca più. Il modulo è a
4 passi:
1. data, persone e voucher;
2. trattamenti e orari per persona;
3. dati dell'ospite;
4. riepilogo.

È in italiano, inglese e tedesco: la lingua si sceglie da sola dal browser
dell'ospite, oppure con i pulsanti IT, EN e DE. Facoltativi sul tag
`<script>`:
- `data-lang` fissa la lingua;
- `data-accent` imposta il colore;
- `data-target` indica il riquadro dove mettere il modulo.

Prezzi, colore e indirizzo pubblico si impostano nella stessa sezione. Il
«Codice completo (vecchio)» resta disponibile per i siti che non possono
caricare uno script da un altro indirizzo.

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
node tests/frontend/card_whatsapp_test.js custom_components/spa_booking/frontend/spa-booking-card.js
node tests/frontend/card_login_test.js custom_components/spa_booking/frontend/spa-booking-card.js
cd bridge && go test ./...   # programma WhatsApp integrato (Go 1.26+)
```

La CI (`.github/workflows/ci.yml`) esegue lint, test, controllo della card,
hassfest e validazione HACS a ogni push e pull request. Lavora su un branch e
apri una pull request: `main` resta sempre installabile.

## Changelog

- **v2.2.0**: versione stabile che raccoglie le beta 2.2.0b1–b4.
  - WhatsApp integrato in Spa Booking, senza add-on (beta).
  - Login personale con ruoli Massaggiatrice, Reception, Manager e
    Amministratore, e PIN per il tablet della reception.
  - Prefisso internazionale su ogni telefono.
  - Voucher con «Creato da», biglietti e invio su WhatsApp.
  - Modulo del sito a passi in tre lingue, caricato da Home Assistant.
  - Avviso con «Prenota comunque» per le regole delle categorie.
  - Aggiornamenti installabili dalla card.
  - Nuovo stile di tutte le schede.
  - [Guida con le anteprime](docs/GUIDA.md).

- **v2.2.0b4** (beta):
  - **Aggiornamenti dalla card.** Quando HACS ha una nuova versione,
    l'Amministratore la vede in alto e la installa con un tocco. Dopo
    l'installazione la card dice cosa serve:
    - se è cambiata solo la card o il modulo del sito, basta ricaricare la
      pagina;
    - se è cambiato il programma, c'è il pulsante «Riavvia ora».

    Nuovi servizi: `update_status`, `install_update` e
    `restart_home_assistant`.
  - **Nuovo stile di altre schede:**
    - Lista richieste a riquadri, con i numeri in alto;
    - scheda del cliente con profilo e numeri;
    - nuova scheda cliente;
    - categorie a riquadri colorati;
    - modifica e creazione di categorie, trattamenti e operatrici in un unico
      riquadro, con i giorni come pulsanti e le fasce orarie su una riga;
    - titolo e spiegazione in ogni sotto-scheda di Configurazione.
  - Il pulsante dice «Salva categoria» e «Salva trattamento», non più
    «category» e «treatment».

- **v2.2.0b3** (beta):
  - **Modulo del sito.**
    - Su WordPress bastano due righe: il modulo arriva da Home Assistant e si
      aggiorna da solo.
    - È diviso in 4 passi, con i trattamenti a schede e gli orari come
      pulsanti.
    - È in italiano, inglese e tedesco.
    - Si possono mostrare prezzi e totale indicativo, e scegliere il colore.
  - **Regole delle categorie.** Quando una prenotazione è fuori dai giorni o
    dalle fasce di una categoria, oppure si sovrappone a una categoria
    esclusa, la card mostra un avviso con «Prenota comunque» oppure «Annulla
    e modifica». Vale anche in modifica. Forzare è permesso alla reception in
    su; chiusure e operatrice già occupata restano bloccanti.

- **v2.2.0b2** (beta):
  - **Login e ruoli.** Ognuno entra con il proprio utente, nei ruoli
    Massaggiatrice, Reception, Manager e Amministratore. Una massaggiatrice
    prenota e modifica solo i suoi appuntamenti e non vede incassi né totali.
    I permessi sono controllati anche dal server.
  - **Utenti dalla card.** In Configurazione › Accessi si creano gli utenti,
    si cambia la password e si disattiva chi non lavora più qui.
  - **Tablet della reception.** Con un utente condiviso, ognuno entra con il
    suo PIN di 4 cifre. Il tablet esce da solo dopo qualche minuto e si
    blocca dopo 5 PIN sbagliati.
  - **Prefisso internazionale.** Accanto a ogni telefono (anche nel modulo
    WordPress) c'è il prefisso, +39 di serie. I numeri salvati prima si
    aprono come +39.
  - **Voucher.**
    - Nuovo campo obbligatorio «Creato da»: è il nome di chi è collegato e
      si può anche cercare.
    - Nuova scheda con il riepilogo, i filtri e i voucher a forma di
      biglietto.
    - Creazione guidata in 3 passi.
    - Pulsante «Invia» su WhatsApp.
    - La creazione è permessa da Reception in su.
  - **Nuovo stile di tutte le schede.**
    - Agenda con il riepilogo del giorno e le fasce Mattina, Pomeriggio e
      Sera.
    - Calendario colorato in base a quanto è pieno ogni giorno.
    - WhatsApp diviso in conversazioni.
    - Configurazione con il menu a lato.
    - Clienti con le iniziali.
  - Corretta una regola di stile non chiusa che annullava lo stile della
    lista WhatsApp.

- **v2.2.0b1** (beta): WhatsApp integrato in Spa Booking, alternativa
  all'add-on WAHA: collegamento con QR code o codice dalla card, invio di
  testi e immagini con ritmo umano (pausa tra i messaggi, "sta scrivendo"),
  controllo che il numero sia su WhatsApp, ricezione di messaggi e reazioni,
  riavvio automatico, sessione nei backup di Home Assistant.
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

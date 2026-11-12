# Spa Booking — integrazione Home Assistant

Gestione degli appuntamenti della SPA dentro Home Assistant: categorie,
trattamenti con durata propria, operatrici, schede cliente, agenda del giorno
per operatrice e per categoria, pagamenti, voucher, richieste dal sito web,
promemoria e report automatici su WhatsApp e Telegram.

Versione corrente: **2.3.7** — documentazione completa in
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

- **v2.4.0** — Dettaglio a lato, punti fedeltà e partner (serve il riavvio di
  Home Assistant):
  - **Dettaglio appuntamento**: su computer non è più un popup, si apre a
    destra dell'Agenda (Timeline ed Elenco, anche per i gruppi con «Singolo /
    Gruppo»). Nuova grafica: testata colorata per stato, orario grande, riquadri
    con operatrice, ospite, codice, accessori, totale e da incassare, un grande
    pulsante per l'azione del momento (Conferma, Entrata, Uscita) e pulsanti
    tondi (Modifica, Chiama, WhatsApp, Recensione). Sul telefono sale dal basso.
  - **Punti fedeltà** (Configurazione › Promo › Punti fedeltà): punti per euro
    impostabili, calcolati sugli incassi delle prenotazioni (non su quelli
    pagati con voucher o gift card) e sui voucher acquistati; un appuntamento
    annullato perde i suoi punti. Alla soglia il cliente riceve un buono in euro
    su WhatsApp (automatico o dalla scheda cliente), i punti si scalano.
    Saldo, barra verso il premio, rettifiche e storico nella scheda cliente;
    classifica in Promo. Servizi `loyalty_reward` e `loyalty_adjust`.
  - **Partner** (Clienti › Partner): elenco con codice PRT-XXXX, aggiunta,
    modifica ed eliminazione a mano. Servizi `save_partner` e `delete_partner`.
    La registrazione dal sito arriverà più avanti.

- **v2.3.12** — Agenda rinnovata (cambia solo la card):
  - In alto il giorno per esteso («Sabato 14 novembre, fra 3 giorni») con le
    frecce, «Oggi» e le viste **Timeline**, **Elenco** e **Mese**.
  - **Striscia della settimana**: ogni giorno con il numero di appuntamenti e
    una barretta di quanto è pieno; un tocco lo apre.
  - I numeri del giorno sono pillole che filtrano: in sala ora, da confermare,
    da incassare.
  - **Timeline**: una riga per operatrice (le libere si vedono subito) e una per
    i trattamenti senza operatrice; i blocchi sono colorati per stato
    (confermato, in attesa, in sala, concluso), con la pausa tratteggiata e la
    linea rossa dell'ora attuale. Tocchi un blocco e si apre la scheda con
    tutte le azioni. A lato: uscite, prossimi arrivi con «Entrata», da
    confermare.
  - **Sul telefono** un elenco per fasce (mattina, pomeriggio, sera): una
    scheda per appuntamento con un solo pulsante (Conferma, Entrata o Uscita) e
    «⋯» per il resto.
  - **Elenco** è la vista di prima, per operatrice.

- **v2.3.11** — Nuova richiesta come Nuovo appuntamento (cambia solo la card):
  - Quattro passi: **Quando e quante persone** (con il codice voucher a
    richiesta), **Trattamenti**, **Cliente** (con ospite e preferenza
    massaggiatrice o massaggiatore), **Note**.
  - Riepilogo sempre visibile con «Salva richiesta» (sul telefono, barra in
    basso).
  - «Una scheda cliente per ogni persona» ora è spenta di default: si spunta
    solo quando serve (due persone con lo stesso nome).

- **v2.3.10** — Nuovo appuntamento riorganizzato (cambia solo la card):
  - Cinque passi numerati: **Quando e quante persone** (Oggi, Domani o Altro
    giorno, persone, voucher a richiesta), **Trattamenti**, **Cliente**,
    **Prezzo e pagamento**, **Stato e note**.
  - **Chi lo fa** a pulsanti: Automatica, Massaggiatrice, Massaggiatore e i
    nomi, con il pallino verde (libera a quell'ora) o arancione (già
    impegnata).
  - **Riepilogo** sempre visibile a destra: cliente, giorno, ogni trattamento
    con orario, operatrice, accessori e prezzo, totale, incassato, da
    incassare, stato e il pulsante «Crea». Sul telefono diventa una barra in
    basso con totale e «Crea».
  - L'ordine dei blocchi è fisso: la matita per spostarli non c'è più.

- **v2.3.9** — Promo salvate e modelli a tema:
  - **Le tue promo**: ogni campagna resta in un elenco, con stato
    (Programmata, Ogni giorno, Inviata, Scaduta, Bozza), data e ora di inizio
    dell'invio automatico, codice e scadenza. Si apre, si modifica e si elimina.
  - **Crea da un modello**: 17 temi sul benessere in spa (Natale, Nuovo anno,
    Inverno, San Valentino, Carnevale, Festa della donna, Festa del papà,
    Primavera, Pasqua, Festa della mamma, Estate, Rientro d'autunno, Black
    Friday, Weekend relax, Compleanno, Buono regalo, Ci manchi). Ognuno porta
    testo, codice con l'anno, giorno di invio e scadenza per la prossima
    ricorrenza (Pasqua, Carnevale e Black Friday calcolati sul calendario).
    Cambiando tema nella promo il testo si aggiorna.
  - Ogni promo ha il suo invio automatico: **un giorno preciso** o **ogni
    giorno** da un giorno, con l'ora di inizio; più promo possono essere
    programmate insieme e ognuna parte una volta sola al giorno.
  - La promo singola delle versioni precedenti diventa la prima dell'elenco.
  - Servizio `send_promo`: nuovo campo `promo_id`.

- **v2.3.8** — Promo e Impostazioni riorganizzate (cambia solo la card, le
  impostazioni salvate restano le stesse):
  - **Promo** con due sotto-schede, **Campagna promo** e **Voucher fedeltà**,
    e i numeri in alto (iscritti, promo inviate, voucher inviati, riscattati).
  - La campagna è in tre passi: **il messaggio** (con anteprima WhatsApp e
    segnaposto da toccare), **a chi** e **quando** (Adesso, Un giorno preciso,
    Ogni giorno), con una frase che dice quanto dura l'invio. Pausa e invii
    massimi sono in «Opzioni avanzate».
  - Il voucher fedeltà mostra la regola riassunta in una frase e l'editor del
    messaggio con anteprima.
  - **Impostazioni** con tre sotto-schede: **Generale** (aspetto, titolo,
    versione), **Sito web** (in quattro passi: attivo, orari con frase
    riassuntiva, avvisi alla reception con «Prova avviso», modulo con codice
    da copiare) e **Dati e backup** (CSV clienti, backup JSON).
  - Una sola barra «Salva» per pagina, che compare solo se cambi qualcosa.

- **v2.3.7**:
  - **Correzione salvataggio Notifiche.** «Salva» dava l'errore «not a valid
    option at 'appointment_reminder_message'». Il servizio `update_settings`
    non accettava le impostazioni del promemoria appuntamento (testo, invio
    automatico, ore), quindi neanche prima si potevano salvare. Ora le accetta,
    e un test controlla che ogni impostazione salvata dalla scheda Notifiche
    sia accettata.

- **v2.3.6** — Notifiche riorganizzate:
  - Quattro sotto-schede: **Messaggi agli ospiti**, **Operatrici**, **Report**
    e **Collegamenti**.
  - I messaggi agli ospiti sono in ordine di percorso (richiesta, proposta di
    un'altra data, acconto, conferma, promemoria, recensione), ognuno con
    «Automatico» o «Manuale» e quando parte.
  - Editor con anteprima in stile WhatsApp che si aggiorna mentre scrivi,
    segnaposto da toccare per inserirli, «Ripristina testo base».
  - Un solo numero di prova per tutti i messaggi.
  - Un'unica barra «Salva», che compare solo quando ci sono modifiche.
  - Su telefono elenco e messaggio sono due schermate.

- **v2.3.5**:
  - **Correzioni voucher.** Dopo la firma con il PIN compariva per un attimo
    la pagina d'errore della card, ed eliminando un voucher appena creato
    usciva «Failed to execute 'appendChild'». La causa era la stessa: il
    riquadro «Voucher creato» per un voucher non (ancora) presente.
  - **Chat WhatsApp conservate.** Le conversazioni della scheda WhatsApp
    (messaggi ricevuti e risposte, con chi ha risposto) restano salvate dopo
    un riavvio. Si eliminano solo a mano: la chat aperta (cestino) o «Elimina
    tutte» (Manager e Amministratore).
  - **Messaggi più curati.** Nuovi testi per conferma (riepilogo), richiesta
    ricevuta, promemoria e richiesta d'acconto. I testi base si aggiornano da
    soli, quelli personalizzati restano come sono.
  - **Un solo messaggio per più persone.** Conferma e promemoria di una
    prenotazione per due o più persone ora partono come un unico messaggio con
    un appuntamento per riga («Persona 1», «Persona 2»).
  - **Acconto.** Nel dettaglio di un appuntamento in attesa compaiono la data
    della richiesta e il pulsante «Reinvia richiesta».
  - **Offerte alle massaggiatrici verificate** con test sull'intero giro:
    proposta in ordine di priorità, rifiuto che passa alla successiva,
    promemoria e scadenza. Novità: se nessuna accetta, la reception riceve un
    WhatsApp (sui numeri degli avvisi) e una notifica in Home Assistant.
  - **Nuova grafica** per Trattamenti (schede per categoria con durata, prezzo
    e operatrici), Accessori (schede e popup con icone pronte da scegliere,
    icone predefinite più adatte) e Operatori (avatar, interruttore Attiva,
    trattamenti, contatti e azioni).

- **v2.3.4**:
  - **Preferenza per ogni persona nel modulo del sito.** «Per il massaggio
    preferisci…» compare nel riquadro di ciascuna persona che ha scelto un
    massaggio, quindi in una coppia una può chiedere la massaggiatrice e
    l'altra il massaggiatore. Il riepilogo lo mostra persona per persona. La
    richiesta lo riporta accanto a «Persona 1/2» e ogni appuntamento confermato
    lo eredita.

- **v2.3.3** — Massaggi:
  - **Correzione «Automatica».** Nel modulo Nuovo, con la massaggiatrice su
    «Automatica», un massaggio veniva rifiutato con «Seleziona un operatore»:
    la card non inviava nessuna candidata. Ora invia tutte quelle abili e il
    server le propone in ordine di priorità (numero più basso prima, saltando
    chi è disattivata, chiusa o ha rifiutato quella fascia).
  - **Genere dell'operatore** (Donna / Uomo) nella sua scheda.
  - **Preferenza dell'ospite** «Massaggiatrice / Massaggiatore /
    Indifferente»: nel modulo del sito (IT/EN/DE, solo se il massaggio scelto
    lo fanno sia donne sia uomini), nella Nuova richiesta e in Nuovo
    («Automatica: massaggiatrice / massaggiatore»). Passa dalla richiesta
    all'appuntamento confermato e compare come «Preferisce …».
  - **Assegnazione automatica con preferenza**: si propone solo a chi è del
    genere chiesto, in ordine di priorità. Se nessuno è libero, la reception
    riceve un avviso invece di un'assegnazione forzata. Un'operatrice scelta a
    mano dalla reception non viene mai cambiata.

- **v2.3.2** — Clienti:
  - **Promo e fedeltà nella scheda cliente**: promo inviate (con l'ultima),
    codici fedeltà inviati, codici riscattati (con la percentuale) e richieste
    del cliente. Da questa versione ogni promo inviata viene contata sul
    cliente.
  - **Clienti dalle richieste**: ogni richiesta, dal sito o dal banco, salva
    già la scheda del cliente (per telefono, senza doppioni); ora la scheda si
    apre dalla richiesta con «Scheda cliente».

- **v2.3.1** — WhatsApp:
  - **Conferma e promemoria dall'appuntamento.** Nel dettaglio
    dell'appuntamento le righe «Conferma WhatsApp» e «Promemoria» mostrano se
    e quando sono stati inviati, con i pulsanti «Invia conferma» / «Reinvia
    conferma» e «Invia promemoria» / «Reinvia promemoria». Prima il pulsante
    del riepilogo non compariva mai (cercava il telefono nel posto sbagliato);
    lo stesso valeva per la richiesta d'acconto e per la domanda «Inviare il
    riepilogo?» dopo la conferma.
  - **Promemoria manuali.** Con i promemoria in modalità manuale, «Invia
    promemoria ora» in Notifiche non inviava nulla: ora invia quelli in
    scadenza.
  - **Avviso richieste dal sito a più numeri** (reception, manager…), con
    «Aggiungi numero» e «Prova avviso».
  - Lo storico modifiche registra anche gli invii di conferma e promemoria.

- **v2.3.0** — Firme e storico:
  - **Voucher firmati con il PIN.** «Crea voucher» chiede il PIN di 4 cifre:
    il voucher resta firmato con il nome di chi l'ha inserito, da qualunque
    dispositivo. Il campo libero «Creato da» non c'è più. Ogni PIN deve essere
    diverso: due persone non possono usare lo stesso.
  - **Chi ha inserito.** Ogni prenotazione e ogni richiesta registra chi l'ha
    inserita (persona collegata, PIN del tablet, oppure «Sito web»). È visibile
    nel dettaglio dell'appuntamento e sulla scheda della richiesta.
  - **Storico modifiche, solo per l'amministratore.** Ogni appuntamento tiene
    l'elenco delle modifiche: quando, chi, cosa è cambiato (orario,
    operatrice, trattamento, stato, prezzo, incassi, entrata e uscita, note…).
    Comprende anche le risposte delle operatrici su WhatsApp. Gli altri ruoli
    non lo ricevono nemmeno dal server.

- **v2.2.4**:
  - **Chiusure con giorni esclusi.** In Fasce bloccate, per una chiusura di
    più giorni si possono escludere alcuni giorni della settimana, che restano
    aperti: ad esempio «chiuso tutto novembre esclusi i sabati». Vale per la
    spa intera, una categoria o un'operatrice, a giornata intera o con orario.
    Agenda, calendario, prenotazioni e modulo del sito ne tengono conto, e
    l'elenco mostra «esclusi i sabati».
  - Servizio `add_closure`: nuovo campo `skip_weekdays` (0 = lunedì … 6 =
    domenica). Le chiusure esistenti non cambiano.

- **v2.2.3**:
  - **Campo Telefono sul telefono.** Nelle schede strette, ad esempio Nuovo
    appuntamento, Nuovo cliente o Voucher, il numero restava schiacciato in un
    quadratino tra il prefisso e il campo Email, e si finiva per scriverlo
    nel campo sbagliato. Ora Telefono occupa tutta la riga, con il prefisso e
    il numero affiancati. Se lo spazio non basta, il numero va a capo sotto il
    prefisso, a larghezza piena. Stessa protezione nel modulo del sito.

- **v2.2.2**:
  - **Trattamenti alternativi in «Proponi data».** Oltre alla prima data
    disponibile si possono proporre uno o più trattamenti alternativi, ognuno
    con prezzo (preso dal listino, modificabile), giorno (di base quello
    chiesto dall'ospite) e orario facoltativo. Compaiono nel messaggio
    WhatsApp, ad esempio «Spa privata 2 ore, sabato 14 novembre, al prezzo di
    € 160», e sulla richiesta come «Alternativa: …».
  - In Notifiche › Proposta di un'altra data: nuovo segnaposto
    `{alternativa}`, più l'introduzione e la riga di ogni alternativa. Il testo
    di base della 2.2.1 si aggiorna da solo; uno personalizzato riceve le
    alternative prima di «Ci risponda…».
  - Servizio `propose_request_date`: nuovo campo `alternatives`.

- **v2.2.1**:
  - **«Proponi data» nella Lista richieste.** Quando la data chiesta è piena,
    si sceglie la prima data disponibile (e, se vuoi, l'orario). Il messaggio
    WhatsApp è già pronto, si può modificare e poi si invia; la richiesta
    mostra «Proposta: …».
  - Il testo si cambia in Notifiche › Proposta di un'altra data. Nuovo
    servizio `propose_request_date`.
  - **Utenti e ruoli sul telefono.** Corretto l'impaginazione che metteva
    tutto in colonne strette. Ogni utente è un riquadro con il ruolo sotto, e
    «Cosa può fare ogni ruolo» diventa un elenco per ruolo.

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

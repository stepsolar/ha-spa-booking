# Spa Booking

Gestione degli appuntamenti della SPA dentro Home Assistant: categorie,
trattamenti con durata propria, operatori, schede clienti e agenda del giorno
raggruppata per operatore e per categoria.

## Novità versione 1.106.0

### Nuove funzionalità voucher
- **Copia codice voucher** su ogni voucher emesso: un clic copia il codice negli appunti.
- **Crea appuntamento con codice voucher**: apre la scheda "Nuovo appuntamento" con il codice voucher pre-compilato. Supporta voucher multi-persona: tutte le persone e i loro trattamenti vengono pre-compilati automaticamente.
- **Ordinamento bottoni** su ogni voucher: 1) Copia codice, 2) Crea appuntamento, 3) Nuova scadenza, 4) Elimina.

### Messaggio di benvenuto per richieste web
- Nuovo setting `web_welcome_message` nella tab **Notifiche**: configura il numero WhatsApp su cui inviare un messaggio di benvenuto al cliente che fa una richiesta dal sito.
- Placeholder disponibili: `{nome}`, `{cognome}`, `{codice}`, `{data}`, `{ora}`, `{persone}`, `{trattamento}`.
- Messaggio predefinito personalizzabile dalla tab **Notifiche**.

### Correzioni
- Fix: import mancante `DEFAULT_WELCOME_MESSAGE` in `coordinator.py` (causava NameError all'avvio).
- Fix: tasto "Crea appuntamento" sui voucher ora compila correttamente i trattamenti (anche per voucher multi-persona).
- Fix: import internazionale numeri di telefono già in v1.105.0 (numeri con `+` o `00` usati come sono, altri letti come italiani con prefisso 39).

## Come funziona

**La durata decide la fine.** Ogni trattamento ha la sua durata (90 o 120
minuti, o quella che serve). Quando crei un appuntamento indichi solo l'ora di
inizio: l'ora di fine la calcola l'integrazione.

**L'operatore dipende dalla categoria.** Una categoria con
`requires_operator` attivo (per esempio *Massaggi*) richiede un operatore; le
altre (per esempio *Ingresso Spa*) no.

**Ogni operatrice sa quali massaggi fa.** L'elenco dei trattamenti che ciascuna
esegue sta sulla sua scheda, non sui trattamenti: una sola lista, che il modulo
*Nuovo* usa per proporre il massaggio giusto e il report mensile usa per
contare ciò che ha fatto. Un trattamento che nessuno ha spuntato accetta
qualsiasi operatrice della sua categoria.

**Niente doppi booking.** Sono controllati due casi: due appuntamenti dello
stesso operatore che si sovrappongono, e due appuntamenti dello stesso cliente
che si sovrappongono. Appuntamenti consecutivi che si toccano sono ammessi.

**Le schede cliente si riusano.** Il numero di telefono è la chiave: se
`+39 333 1234567`, `00393331234567` e `333 1234567` vengono riconosciuti come
lo stesso numero, l'appuntamento viene agganciato alla scheda esistente invece
di crearne una nuova. È possibile prenotare anche senza creare una scheda
(nome e telefono sono sufficienti).

**Le notifiche passano da WhatsApp e Telegram.** A ogni operatrice configurata
l'appuntamento arriva su entrambi i canali, se sono entrambi disponibili: il
numero di WhatsApp si deriva dal telefono come `39…@c.us` (oppure da un chat id
esplicito), quello di Telegram è la sua chat. Un canale che non è configurato
viene saltato, e un invio che fallisce non blocca la prenotazione.

## Installazione

Il codice è già in `/homeassistant/custom_components/spa_booking/` e la card in
`/homeassistant/www/spa_booking/spa-booking-card.js`. Serve un **riavvio
completo** di Home Assistant: per il codice delle integrazioni non esiste un
reload.

Poi: **Impostazioni → Dispositivi e servizi → Aggiungi integrazione → Spa
Booking**. Nella prima schermata indica il nome e gli operatori iniziali
separati da virgola.

## La dashboard di gestione

C'è già una dashboard **Spa Gestione** in modalità storage, con una vista
`panel`: la card `custom:spa-booking-card` occupa tutto lo schermo, senza la
griglia delle sezioni. In cima c'è una barra fissa con titolo e schede, sotto
il contenuto centrato su larghezza massima, così la vista legge come una pagina
e non come una card. Le schede sono solo cinque:

| Scheda | A cosa serve |
|---|---|
| **Agenda** | Gli appuntamenti del giorno, raggruppati per operatore, con annullati in una sezione a parte. Ogni riga ha i pulsanti telefono e WhatsApp e quello di annullamento. |
| **Nuovo** | Il form a cascata: **massaggiatrice** → trattamento (solo quelli che lei esegue) → data e ora → cliente. Va anche al contrario: scelto il trattamento, la card dice chi può eseguirlo. Mostra in anticipo l'orario di fine e avvisa se l'operatore o il cliente sono già occupati in quella fascia. |
| **Calendario** | Mese con il numero di appuntamenti per giorno; cliccando un giorno si apre la sua agenda. Sotto, i prossimi giorni. |
| **Clienti** | Ricerca, modifica della scheda, storico e creazione di un appuntamento per quel cliente. |
| **Configurazione** | Categorie, trattamenti, operatrici e notifiche: creazione, modifica, disattivazione, eliminazione. Visibile solo agli amministratori. |

La tab **Configurazione → Operatrici** è la scheda di ciascuna massaggiatrice:
nome, telefono, chat WhatsApp (precompilata dal telefono), chat Telegram, **la
lista dei tipi di massaggio che sa fare**, e i canali su cui riceve le
notifiche. La tab **Notifiche** gestisce invece i destinatari del report mensile
e permette di vederlo e inviarlo subito.

Per aggiungerla anche altrove: **Impostazioni → Dashboard → Risorse** non
serve, la card è già registrata. Basta scrivere in YAML

```yaml
type: custom:spa-booking-card
title: Gestione SPA
```

La card carica l'intero archivio con `spa_booking.export_data` e filtra in
locale, quindi passare da una scheda all'altra è immediato; ogni scrittura
passa comunque dai servizi dell'integrazione, che restano proprietari delle
regole di business.

Se la card resta bianca dopo il riavvio, prova un ricaricamento forzato del
browser.

### Aggiornare la card

La card è servita dalla vista HTTP dell'integrazione
(`/api/spa_booking/card.js`, in `card_view.py`) con `Cache-Control: no-cache` e
un `ETag`: il browser e l'app rivalidano a ogni caricamento, quindi una modifica
a `spa-booking-card.js` si vede **al ricaricamento successivo, senza bump di
versione e senza riavvio**. Aggiorna `CARD_VERSION` nel JS solo se vuoi il
numero che compare in console.

## Entità

| Entità | Ruolo |
|---|---|
| `sensor.spa_booking_appuntamenti_oggi` | Numero, con attributi `appointments`, `by_operator`, `by_category` |
| `sensor.spa_booking_appuntamenti_domani` | Idem per il giorno dopo |
| `sensor.spa_booking_clienti_registrati` | Numero di schede, con attributo `clients` |
| `sensor.spa_booking_prossimo_appuntamento` | Minuti dal prossimo appuntamento, con attributo `appointment` |
| `calendar.spa_booking_appuntamenti_<operatore>` | Un calendario per operatore, con lo stato *on* durante il trattamento |

Il calendario per operatore è la parte utile per le automazioni: ad esempio
accendere le luci della stanza massaggi 10 minuti prima dell'inizio, usando lo
stato del calendario o l'attributo `start_time`.

## Servizi

### Appuntamenti

`spa_booking.create_appointment` crea l'appuntamento. I campi principali:

```yaml
service: spa_booking.create_appointment
data:
  treatment_id: trt_massaggio_relax_90
  start: "2026-10-06 14:00:00"
  operator_id: op_1a2b3c4d5e6f    # obbligatorio per le categorie che lo richiedono
  last_name: Rossi
  first_name: Luigi
  phone: "+39 333 1234567"
  email: luigi@example.com
  client_notes: Allergie: no
  notes: "Portare asciugamane riscaldati"
```

Per riusare una scheda esistente basta `client_id` al posto dei dati anagrafici.
Con `operator_ids` (lista) al posto di `operator_id` l'appuntamento parte come
**offerta**: la prima massaggiatrice abile della lista riceve la proposta sulla
sua chat e la cascata continua finché qualcuna conferma.

`spa_booking.create_bookings` crea più appuntamenti in un colpo solo, tutti o
nessuno. Ogni riga ha un trattamento e una o più persone (`entries`), con
`start` (data+ora), note e cliente per persona:

```yaml
service: spa_booking.create_bookings
data:
  rows:
    - treatment_id: trt_massaggio_relax_90
      entries:
        - start: "2026-10-09T10:00:00"
          operator_ids: [op_1a2b3c4d5e6f]
          last_name: Rossi
          phone: "+39 333 1234567"
          notes: "Coppia: stessa fascia o fasce diverse, una massaggiatrice per persona"
        - start: "2026-10-09T10:00:00"
          operator_ids: [op_9f8e7d6c5b4a]
          last_name: Bianchi
          phone: "+39 333 7654321"
```

Se una sola riga non supera i controlli (sovrapposizione, massaggiatrice non
abile, fascia rifiutata) non viene creato nessun appuntamento e nessuna scheda
cliente.

`spa_booking.cancel_appointment` con `appointment_id` e `reason` opzionale:
l'appuntamento resta nello storico e libera la fascia.

### Offerte alle massaggiatrici

Quando un appuntamento richiede l'operatrice, la prima abile riceve la proposta
su WhatsApp e Telegram con i pulsanti *Confermo* / *Non disponibile*. La
risposta arriva con `spa_booking.respond_to_offer` (o con l'evento
`spa_booking_answer_request`, che gestisce anche i messaggi WhatsApp e le
reazioni):

- **Confermo** → l'appuntamento è confermato con lei.
- **Non disponibile** → la stessa fascia viene offerta alla successiva
  massaggiatrice abile della lista; chi rifiuta non viene ricontattata per
  quella fascia finché non si segnala di nuovo disponibile (`available_again`).
- Scadenza o promemoria gestiti dall'automazione **SPA: offerte** in
  `packages/spa_booking.yaml` con `spa_booking.expire_offers` ogni 5 minuti: a
  scadenza l'offerta passa alla successiva senza creare blocchi.

Le finestre rifiutate si riaprono dal dashboard (tab **Fasce bloccate**) con
`spa_booking.clear_slot_block` `{operator_id, appointment_id}`.

### Configurazione

`add_category`, `update_category`, `delete_category`
`add_treatment`, `update_treatment`, `delete_treatment`
`add_operator`, `update_operator`, `delete_operator`

Esempio di trattamento:

```yaml
service: spa_booking.add_treatment
data:
  name: Massaggio relax 90
  category_id: cat_massaggi
  duration_min: 90
```

Ogni trattamento ha `active` (lo usa la reception) e `web_visible` (lo usa il
sito web): spento quest'ultimo, non compare nell'elenco pubblico e non può
essere richiesto dagli ospiti, ma resta prenotabile in reception. Entrambi
valgono `true` se non specificati, così i trattamenti già creati restano
visibili sul sito.

Esempio di operatrice, con i massaggi che esegue e i suoi canali:

```yaml
service: spa_booking.add_operator
data:
  name: Maria
  phone: "333 1112223"
  # La chat WhatsApp si deriva dal telefono (393331112223@c.us).
  # Indicarla solo per un gruppo o un numero diverso:
  whatsapp_chat_id: ""
  telegram_chat_id: "933728087"
  treatment_ids:
    - trt_massaggio_relax_90
    - trt_massaggio_relax_120
  notify_whatsapp: true
  notify_telegram: true
```

`treatment_ids` vuoto significa che non le verranno proposti massaggi nel modulo
*Nuovo* e non comparirà nel report mensile.

### Notifiche e report mensile

`spa_booking.get_monthly_report` costruisce il riepilogo dei massaggi di un mese
(`month` in formato `AAAA-MM`, di default il mese precedente). Con
`notify: false` non invia nulla e serve per l'anteprima; con `notify: true`
invia il report completo ai destinatari configurati e, se attivo, a ciascuna
massaggiatrice il proprio riepilogo sui suoi canali.

```yaml
service: spa_booking.get_monthly_report
data:
  month: "2026-09"
  notify: true
```

Per ogni massaggiatrice il report elenca data, ora di inizio e fine, tipo di
massaggio, durata e cliente, con il totale dei massaggi e dei minuti lavorati.
Un testo più lungo del limite del canale viene spezzato su righe intere, non
troncato.

I destinatari si cambiano con `spa_booking.update_settings` (o dalla tab
**Notifiche** della card):

```yaml
service: spa_booking.update_settings
data:
  telegram_config_entry_id: 01JZ6G7TT8APQ8WCXEPRCDNQFN
  report_telegram_chats: "933728087, 5400097873, 8144958044"
  report_whatsapp_chat: ""
  report_per_operator: true
  offer_timeout_hours: 24
  offer_reminder_hours: 2
```

`offer_timeout_hours` è la scadenza di un'offerta (0 = mai); `offer_reminder_hours`
quanto prima della scadenza viene mandato un promemoria (0 = mai). Si cambiano
anche dalla tab **Notifiche** della card.

`packages/spa_booking.yaml` contiene l'automazione **SPA: report mensile
massaggi**: il 1° di ogni mese alle 08:00 chiama il servizio con `notify: true`.
Per una prova isolata, cambiare l'orario dell'automazione e riavviare Home
Assistant.

WhatsApp usa il `rest_command.spa_booking_whatsapp_send` dichiarato nello stesso
pacchetto: è lo stesso endpoint di `packages/whatsapp.yaml`, ma con il testo
passato attraverso `|to_json`, perché un report multi-riga non può essere
interpolato grezzo dentro una stringa JSON. Se l'indirizzo dell'add-on cambia,
va aggiornato anche quel comando.

### Messaggio di benvenuto per le richieste web

Puoi configurare un messaggio di benvenuto che viene inviato su WhatsApp al
cliente che fa una richiesta dal sito. Imposta il numero WhatsApp della reception
nel campo **Notifiche** → `web_welcome_message`. Lascialo vuoto per disabilitare
il messaggio di benvenuto.

Il messaggio usa i seguenti placeholder:
- `{nome}` - Nome del cliente
- `{cognome}` - Cognome del cliente
- `{codice}` - Codice riferimento della richiesta
- `{data}` - Data della richiesta
- `{ora}` - Ora del primo trattamento
- `{persone}` - Numero di persone
- `{trattamento}` - Elenco dei trattamenti richiesti

Puoi personalizzare il testo del messaggio nella tab **Notifiche** della card,
oppure usare il messaggio predefinito.

### Lettura

- `spa_booking.get_daily_agenda` con `date` (ed opzionali `operator_id`,
  `category_id`) → l'agenda del giorno con `by_operator` e `by_category`: è la
  base per il riepilogo giornaliero
- `spa_booking.get_config` → categorie, trattamenti, operatrici e impostazioni
- `spa_booking.search_clients` con `query`
- `spa_booking.get_client_history` con `client_id` → lo storico del cliente
- `spa_booking.export_data` / `import_data` → backup e ripristino dell'archivio
- `spa_booking.promo_voucher_tick` → invia i voucher fedeltà in attesa di invio
  (basato sull'impostazione `promo_voucher_after_hours`) e ne elimina i scaduti.
- `spa_booking.redeem_promo_voucher` → segna un voucher come riscattato (resta
  nell'elenco come record di vendita).
- `spa_booking.delete_promo_voucher` → rimuove un voucher dall'elenco.

## Eventi

L'integrazione emette `spa_booking_appointment_created` e
`spa_booking_appointment_cancelled` con l'appuntamento completo come payload.
Sono gli agganci per le conferme WhatsApp al cliente e per i promemoria: le
notifiche interne agli operatori sono già gestite dall'integrazione.

## Dove finiscono i dati

Tutto in `homeassistant/.storage/spa_booking.json`, con backup automatico
insieme al resto della configurazione. È una delle directory interne che
Home Assistant gestisce da sé: non va modificata a mano.

## Numeri di telefono esteri

Un numero scritto con il prefisso internazionale viene usato come è: il
codice del paese fa parte del numero e non viene toccato. Tutti gli altri
numeri si leggono come italiani, con il `39` aggiunto, come è sempre stato.

- `333 1234567` → `393331234567@c.us`
- `+39 333 1234567` → `393331234567@c.us`
- `0039 333 1234567` → `393331234567@c.us`
- `+41 79 123 45 67` → `41791234567@c.us`
- `0041 79 123 45 67` → `41791234567@c.us`

La regola vale per tutti i canali: il pulsante WhatsApp della card, le
conferme di richiesta, l'acconto, il riepilogo, la richiesta di revisione, i
voucher, le offerte alle massaggiatrici e le risposte che arrivano dal gateway.

**Un numero straniero scritto senza prefisso internazionale** ("079 123 45 67"
per la Svizzera) non è distinguibile da uno italiano: va scritto con il `+` o
con il `00`, altrimenti il messaggio finisce a un numero italiano.

Le schede clienti deduplicano con la stessa regola: `+41 79 123 45 67`,
`0041 79 123 45 67` e `41791234567` sono lo stesso ospite, quindi una sola
scheda. Il numero memorizzato resta quello scritto, con il `+` o il `00`:
niente dati da migrare.

Per le massaggiatrici c'è anche il campo "chat WhatsApp" esplicito, che ha la
precedenza su tutto: `41791234567@c.us` per un numero estero, `120363@g.us` per
un gruppo.

## Test

Tre file di verifica stanno nello scratch, non nella cartella dell'integrazione.

- `test_spa_booking.py` (130 controlli): logica con stub isolati di Home
  Assistant — durate, sovrapposizioni, deduplica clienti, raggruppamento
  dell'agenda, persistenza, schede operatrice con i tipi di massaggio,
  derivazione dei chat id WhatsApp, invio su entrambi i canali, report mensile
  e invio del report ai destinatari e a ciascuna massaggiatrice, la
  rimozione effettiva di categorie/trattamenti/operatrici non impegnate,
  l'aggiornamento di un archivio salvato prima di queste funzioni, la cascata
  delle offerte (rifiuto → successiva, disponibile di nuovo → riapertura,
  scadenza senza blocchi), il blocco della sola fascia rifiutata, il carico
  multiplo tutto-o-niente e la risposta senza id dell'appuntamento.
- `test_imports.py` (20 controlli): forma delle API di Home Assistant usate dal
  codice.
- `test_spa_card.js` (151 controlli): logica della card con un DOM finto —
  caricamento dati, agenda, calendario, cascata massaggiatrice/massaggio, form
  di creazione singola e multi-persona/multi-trattamento, ricerca clienti,
  configurazione (l'editor operatrice elenca tutti i massaggi assegnabili,
  anche quelli non ancora spuntati), tab notifiche con offerte e ore di
  scadenza/promemoria, tab fasce bloccate con la riapertura, badge delle
  offerte in agenda, controllo accessi. Verifica anche che ogni servizio sia
  chiamato chiedendo la risposta attraverso il comando websocket e che
  `callService` non compaia più.

Si eseguono con `python3` e `node` senza alcun ambiente Home Assistant.

## Visuale delle schede

Ogni scheda (Agenda, Nuovo, Spa, Clienti, Configurazione, Voucher) dispone di un
selettore visivo a una o due colonne accessibile quando si clicca il pulsante
matita (modalità modifica): due bottoni affiancati a sinistra del titolo della
scheda permettono di passare dalla visuale a due colonne a quella a una colonna
e viceversa. La scelta viene salvata nell'impostazione `tab_cols` per ogni
ambito (`form`, `notifiche`, `settings`, `richiesta`, `promo`) e persiste tra
una sessione e l'altra.

- **1 colonna** (`mdi:view-list-outline`): gli elementi si dispongono in una
  colonna verticale, ideale su tablet o finestre strette.
- **2 colonne** (`mdi:view-dashboard-outline`): gli elementi sono disposti in
  due colonne affiancate, sfruttando lo spazio orizzontale disponibile.

La selezione è globale per ciascuna scheda: se si cambia visuale nella tab
Impostazioni, essa viene applicata solo a quella scheda. Le icone mostrano il
numero corrente accanto al nome.

## Voucher emessi

Ogni voucher nella lista "Voucher emessi" dispone ora di due azioni rapide
accessibili da qualsiasi vista (non serve essere in modalità modifica):

- **Copia codice voucher** — un clic copia il codice al portapapunti del
  browser e mostra un messaggio di conferma. Il codice può poi essere incollato
  in qualsiasi campo che lo accetti (es. la tab "Nuovo appuntamento").
- **Crea appuntamento con codice** — un clic apre la scheda "Nuovo appuntamento"
  (o "Nuova richiesta") già compilata con il campo "Codice voucher" popolato.
  L'operatrice può poi completare i dati della prenotazione (nome ospite,
  telefono, trattamenti, orario) e confermare.

Sul voucher scaduto o riscattato il pulsante "Crea appuntamento" rimane visibile
ma il codice è solo a scopo di riferimento.

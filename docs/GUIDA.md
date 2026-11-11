# Spa Booking — guida alle schede (2.2)

Aggiornata alla 2.2.1: [Proponi data](#proponi-data) nelle richieste; [aggiornamenti dalla card](#aggiornamenti), nuove schede di richieste, cliente e configurazione; [modulo del sito](#modulo-del-sito) a passi e in tre lingue, [avviso delle regole di categoria](#avviso-regole-della-categoria).

Questa guida mostra ogni scheda della dashboard **Spa Booking** e spiega a
cosa serve ogni funzione. Le immagini sono state fatte con dati di prova.
Dalla 2.2 tutte le schede hanno lo stesso stile:
- riquadri chiari con gli angoli arrotondati;
- una riga di numeri in alto per vedere la situazione a colpo d'occhio;
- pulsanti colorati per lo stato di ogni elemento;
- l'azione principale sempre in alto a destra.

Il tema chiaro e quello scuro seguono Home Assistant (oppure la scelta fatta
in Impostazioni › Aspetto).

- [Accesso e ruoli](#accesso-e-ruoli)
- [Agenda](#agenda)
- [Nuovo: appuntamento, richiesta, lista richieste](#nuovo)
- [Spa](#spa)
- [Clienti](#clienti)
- [Voucher](#voucher)
- [WhatsApp](#whatsapp)
- [Configurazione](#configurazione)
- [Modulo del sito](#modulo-del-sito)
- [Aggiornamenti](#aggiornamenti)
- [Telefono e tablet](#telefono-e-tablet)

---

## Accesso e ruoli

In alto a destra c'è sempre **chi è collegato** e il suo ruolo.

Ognuno entra in Home Assistant con **il proprio nome utente e la propria
password**. Il ruolo decide cosa vede e cosa può fare, e lo stesso controllo
è fatto anche dal server: un pulsante nascosto non basta per fare
un'operazione non permessa.

| | Massaggiatrice | Reception | Manager | Amministratore |
|---|---|---|---|---|
| Agenda e calendario | ✓ | ✓ | ✓ | ✓ |
| Prenotare e modificare | solo i suoi | ✓ | ✓ | ✓ |
| Incassi | — | ✓ | ✓ | ✓ |
| Creare voucher | — | ✓ | ✓ | ✓ |
| Estendere o eliminare voucher | — | — | ✓ | ✓ |
| Scheda Spa | ✓ | ✓ | ✓ | ✓ |
| Report e totali | — | — | ✓ | ✓ |
| Configurazione e utenti | — | — | — | ✓ |

### Tablet della reception con PIN

![Tablet della reception](anteprime/22-tablet-pin.png)

Il tablet al banco resta collegato con un utente **condiviso**. Chi lo usa:
1. tocca il proprio nome;
2. inserisce il suo **PIN di 4 cifre**.

Da quel momento ogni prenotazione, incasso e voucher porta il suo nome.

**Cambia utente** (in alto a destra) lascia il tablet al collega. Dopo
qualche minuto senza tocchi il tablet torna da solo alla scelta della
persona: i minuti si impostano in Configurazione › Accessi.

Cinque PIN sbagliati di fila bloccano il tablet per un minuto.

### Cosa vede una massaggiatrice

![Vista massaggiatrice](anteprime/23-massaggiatrice.png)

Una massaggiatrice vede tutta l'agenda della giornata, ma modifica solo gli
appuntamenti dell'operatrice a cui è collegata (le altre righe hanno solo
telefono e WhatsApp). Non vede incassi e totali. Quando prenota, l'operatrice
è già impostata su di lei.

---

## Agenda

![Agenda del giorno](anteprime/01-agenda.png)

- **Barra della giornata**:
  - *Calendario* passa alla vista del mese;
  - *Oggi* e le frecce cambiano giorno;
  - *Stampa PDF* apre il foglio della giornata da stampare (prezzi e
    pagamenti solo per Manager e Amministratore);
  - *Nuovo* apre il modulo di prenotazione su quel giorno.
- **Filtri**: per categoria (Ingresso Spa, Massaggi, …) e per tipo di ospite
  (hotel o esterno). Compaiono solo le categorie presenti quel giorno.
- **Riepilogo del giorno**:
  - quanti appuntamenti ci sono;
  - quanti clienti sono **in sala ora** (entrati e non ancora usciti);
  - quanti sono **da confermare** (in attesa, oppure proposti a
    un'operatrice che non ha ancora risposto);
  - per chi registra gli incassi, quanto resta **da incassare**.
- **Uscite**: i clienti che escono adesso (da 15′ prima a 30′ dopo la fine),
  con *Conferma uscita*.
- **Appuntamenti per operatrice**, divisi in *Mattina*, *Pomeriggio* e
  *Sera*. Ogni riga riporta:
  - orario, cliente, trattamento e codice;
  - lo stato dell'offerta all'operatrice.

  I pulsanti della riga:
  - *Entrata* fa il check-in;
  - la matita apre la modifica;
  - il calendario rosso annulla;
  - telefono e WhatsApp contattano il cliente.

  Toccando la riga si apre il dettaglio con incassi, gruppo e messaggi.
- **Mostra check-in** fa vedere anche chi è già entrato. *Usciti* e
  *Annullati* restano in fondo, chiusi.

### Calendario

![Calendario del mese](anteprime/02-calendario.png)

Ogni giorno è colorato in base a quanto è pieno, rispetto al giorno più
pieno del mese: si trovano subito i giorni liberi. Oggi ha il bordo. Il
numero in alto è il totale degli appuntamenti. Le chiusure hanno il
lucchetto.

A destra c'è l'elenco del mese, giorno per giorno. Toccando un giorno si
torna all'agenda su quella data.

---

## Nuovo

### Appuntamento

![Nuovo appuntamento](anteprime/03-nuovo-appuntamento.png)

Prenotazione di una o più persone, ognuna con i suoi trattamenti, orari,
operatrice e accessori. Il modulo controlla:
- sovrapposizioni e pause delle operatrici;
- fasce bloccate e chiusure.

Sotto ci sono i totali (listino e prezzo applicato) e gli **incassi**, per
chi li registra.

Il **telefono ha il prefisso internazionale accanto** (+39 già scelto, i
Paesi più frequenti in cima). Se si scrive un numero che inizia con +41 o
0049, il prefisso si sistema da solo.

### Avviso: regole della categoria

![Avviso regola](anteprime/28-avviso-regola.png)

Se una prenotazione è fuori dalle regole di una categoria, compare un avviso
invece di un errore. Le regole sono:
- i giorni (per esempio: «La categoria 'Privata' accetta prenotazioni di
  mattina solo Lun, Mar, Mer, Gio, Ven»);
- le fasce di mattina e pomeriggio;
- le categorie che non possono sovrapporsi.

**Prenota comunque** inserisce l'appuntamento lo stesso.
**Annulla e modifica** torna al modulo così com'era, per scegliere un altro
giorno o orario.

L'avviso compare anche quando si modifica un appuntamento o un gruppo.
Forzare è permesso alla Reception, al Manager e all'Amministratore: una
massaggiatrice vede l'avviso senza il pulsante. Restano sempre bloccanti:
- le chiusure (Fasce bloccate);
- un'operatrice già occupata.

### Nuova richiesta

![Nuova richiesta](anteprime/04-nuova-richiesta.png)

Una richiesta non occupa ancora l'agenda: si usa quando l'ospite chiede ma
l'orario va confermato. Con 2 o più persone c'è un riquadro per persona
(*Copia dalla 1ª* ripete i trattamenti). Al salvataggio l'ospite riceve
il messaggio di conferma ricezione su WhatsApp.

### Lista richieste

![Lista richieste](anteprime/05-lista-richieste.png)

In alto ci sono i numeri: richieste da confermare, arrivate dal sito,
confermate. Ogni richiesta è un riquadro con:
- iniziali e nome dell'ospite;
- provenienza (Sito o Reception) ed etichetta «Nuova» se non è ancora stata
  aperta;
- telefono, voucher e codice;
- data e numero di persone;
- per ogni persona, i trattamenti con l'orario;
- le note in evidenza.

I pulsanti:
- **Conferma** crea gli appuntamenti;
- **Modifica** apre la richiesta nel modulo;
- **Invia messaggio** rimanda all'ospite il messaggio WhatsApp;
- il cestino la elimina.

### Proponi data

![Proponi data](anteprime/05b-proponi-data.png)

Se la data chiesta è piena, **Proponi data** (accanto a Conferma) apre un
riquadro dove si scelgono:
- la **prima data disponibile**;
- l'orario, se vuoi.

Il messaggio WhatsApp all'ospite è già scritto con i suoi dati e la data
proposta; lo puoi cambiare prima di premere **Invia su WhatsApp**. La
richiesta mostra poi l'etichetta «Proposta: …» e resta da confermare: quando
l'ospite accetta, «Modifica» la sposta sulla nuova data e «Conferma» la
prenota.

Il testo di base si cambia in Configurazione › Notifiche › **Proposta di
un'altra data**, con i segnaposti:
- `{nome}` e `{cognome}`;
- `{codice}`;
- `{data_richiesta}`;
- `{trattamenti}`;
- `{data_proposta}`;
- `{orario_proposto}`.

Le richieste già confermate restano in fondo, chiuse. La campanella in alto
conta le richieste dal sito non ancora aperte.

---

## Spa

![Scheda Spa](anteprime/06-spa.png)

I comandi della spa, divisi in sezioni:
- **Luci**: accensione e luminosità;
- **Clima**: termostato con − e +;
- **Servizi e sensori**: idromassaggio, ventilazione, temperatura
  dell'acqua, umidità.

Ogni sezione mostra un riepilogo, per esempio "2 luci accese su 4". La
sotto-scheda *Telecamere* (non per le massaggiatrici) mostra le immagini dal
vivo. In modalità modifica si aggiungono, spostano e nascondono i riquadri.

---

## Clienti

![Clienti](anteprime/07-clienti.png)

L'elenco dei clienti. Per ognuno si vedono:
- le iniziali;
- telefono ed email;
- l'ultima visita e il numero di visite.

I pulsanti chiamano, scrivono su WhatsApp o aprono una nuova prenotazione.
Toccando un cliente si apre la sua scheda con lo storico, le note, le promo
e la modifica dei dati, con il telefono con prefisso. Manager e
Amministratore possono creare e unire i clienti.

### Scheda del cliente

![Scheda cliente](anteprime/07b-scheda-cliente.png)

A sinistra il profilo:
- iniziali, nome e contatti;
- «Cliente abituale» (da 3 visite);
- se riceve le promo;
- quante visite ha fatto e il prossimo appuntamento;
- per Manager e Amministratore, quanto ha speso;
- note e voucher fedeltà.

A destra lo storico degli appuntamenti: toccandone uno si apre il dettaglio.
In alto ci sono Indietro, Modifica, Elimina, telefono e WhatsApp.

### Nuova scheda cliente

![Nuovo cliente](anteprime/07c-nuovo-cliente.png)

Nome, cognome, telefono con prefisso, email, note e iscrizione alle promo,
in un unico riquadro.

---

## Voucher

![Voucher](anteprime/08-voucher.png)

- **Riepilogo**:
  - voucher attivi;
  - voucher **in scadenza** nei prossimi 30 giorni;
  - voucher riscattati nel mese;
  - per il Manager, il valore delle gift card attive.

  Toccando un numero si filtra l'elenco.
- **Filtri**: Tutti, Attivi, In scadenza, Riscattati, Scaduti, Fedeltà. La
  ricerca trova anche **chi ha creato** il voucher.
- **Ogni voucher è un biglietto**, colorato secondo lo stato (verde attivo,
  ambra in scadenza, azzurro riscattato, grigio scaduto). Riporta:
  - codice, destinatario e chi lo ha regalato;
  - trattamenti per persona;
  - scadenza;
  - **Creato da** (i voucher fatti prima della 2.2 mostrano "—").

  Le azioni:
  - *Copia* copia il codice;
  - *Prenota* apre la prenotazione già compilata;
  - *Invia* lo manda su WhatsApp;
  - *Scadenza* ed *Elimina* sono solo per il Manager.

### Nuovo voucher in tre passi

![Nuovo voucher](anteprime/09-voucher-nuovo.png)

1. **Acquirente e destinatario**: nomi e telefoni con prefisso, più
   **Creato da**, obbligatorio. Il nome è già quello di chi è collegato e
   non si può cambiare: resta scritto sul voucher.
2. **Persone e trattamenti**: per ogni persona si toccano i trattamenti
   (con il prezzo), gli accessori e l'eventuale gift card in euro.
3. **Riepilogo**: si controlla tutto e si preme *Crea voucher*.

Il codice appare subito in grande, con *Copia* e *Invia*.

### Invia su WhatsApp

![Invia voucher](anteprime/10-voucher-invia.png)

Si sceglie a chi mandarlo (destinatario o acquirente). Il testo è già
pronto, con codice, trattamenti e scadenza, e si può modificare prima di
inviarlo.

---

## WhatsApp

![WhatsApp](anteprime/11-whatsapp.png)

I messaggi arrivati al numero dell'hotel da chi non è un'operatrice, divisi
per **conversazione**: a sinistra l'elenco, a destra la chat.

Se il numero è già un cliente si vedono il nome, le visite e il prossimo
appuntamento. Si risponde dal campo in basso (Invio per mandare).
*Crea richiesta* apre una richiesta con il numero già scritto. *Salva
cliente* compare solo se il numero non è ancora un cliente.

---

## Configurazione

Solo per l'Amministratore. Su schermo largo il menu è una colonna a
sinistra, sul telefono una striscia di icone.

| | |
|---|---|
| ![Categorie](anteprime/12-config-categorie.png) | **Categorie**: ogni categoria è un riquadro con il suo colore a lato e le etichette (numero di trattamenti, con o senza operatrice, pausa, regole di giorni e fasce). |
| ![Modifica categoria](anteprime/12b-config-categoria-modifica.png) | **Nuova / modifica categoria**: nome, operatrice sì o no, colore, pausa, giorni di mattina e di pomeriggio come pulsanti, fasce orarie da–a sulla stessa riga, categorie da non sovrapporre. |
| ![Trattamenti](anteprime/13-config-trattamenti.png) | **Trattamenti**: divisi per categoria, con durata, prezzo e operatrici. La matita cambia l'ordine. |
| ![Modifica trattamento](anteprime/13b-config-trattamento-modifica.png) | **Nuovo / modifica trattamento**: nome, categoria, durata, prezzo, persone insieme, attivo, visibile sul sito, operatrici abilitate. |
| ![Accessori](anteprime/14-config-accessori.png) | **Accessori**: kit, accappatoio, cuffia… con il loro simbolo. |
| ![Operatori](anteprime/15-config-operatori.png) | **Operatori**: telefono con prefisso, WhatsApp/Telegram, ruolo, trattamenti, priorità per le offerte. |
| ![Fasce bloccate](anteprime/16-config-fasce-bloccate.png) | **Fasce bloccate**: chiusure della spa, di una categoria o di un'operatrice, a giornata o con orario. |
| ![Notifiche](anteprime/17-config-notifiche.png) | **Notifiche**: collegamento WhatsApp (integrato o WAHA), report, offerte alle operatrici, acconto, riepilogo, promemoria, recensioni. Ogni messaggio ha la prova su un numero. |
| ![Promo](anteprime/18-config-promo.png) | **Promo**: invio promozionale e voucher fedeltà automatici. |
| ![Impostazioni](anteprime/21-config-impostazioni.png) | **Impostazioni**: titolo, aspetto, sito web (con il numero degli avvisi), ordine dei campi, backup e ripristino. |

### Accessi: utenti, ruoli e PIN

![Accessi](anteprime/19-config-accessi.png)

- **Cosa può fare ogni ruolo**: la tabella qui sopra, sempre a portata di
  mano.
- **Ogni utente** ha:
  - un ruolo, che si cambia dal menu a tendina;
  - la matita, che apre la scheda dell'utente.

  Nella scheda dell'utente:
  - **È in agenda come**: collega l'utente alla sua operatrice. Serve alle
    massaggiatrici per prenotare solo per sé.
  - **PIN per il tablet**: 4 cifre, salvate solo come impronta cifrata. Si cambia o si
    toglie.
  - **Tablet condiviso**: segna l'utente usato dal tablet della reception.
  - **Nuova password** e **Disattiva utente** (chi non lavora più qui);
    *Riattiva* lo rimette.
- **Esci da solo dopo (minuti)**: inattività prima che il tablet torni alla
  scelta della persona.

Sul telefono ogni utente è un riquadro con il ruolo sotto il nome, e la
tabella dei ruoli diventa un elenco per ruolo:

![Accessi sul telefono](anteprime/19b-telefono-accessi.png)

![Nuovo utente](anteprime/20-config-nuovo-utente.png)

**Nuovo utente** crea l'accesso di Home Assistant direttamente da qui. Si
indicano:
- nome;
- nome utente;
- password (almeno 6 caratteri);
- ruolo;
- operatrice collegata;
- PIN, facoltativo.

L'utente creato non è amministratore di Home Assistant e vede solo questa
dashboard.

---

## Modulo del sito

Il modulo che gli ospiti compilano sul sito dell'hotel. Su WordPress ci sono
solo due righe (Configurazione › Impostazioni › Sito web › *Copia codice per
il sito*): il modulo vero arriva da Home Assistant, quindi ogni aggiornamento
compare sul sito da solo. Il modulo è isolato dal tema del sito: il tema non
lo rovina e il modulo non cambia il sito.

| | |
|---|---|
| ![Passo 1](anteprime/30-sito-f1-quando.png) | **1. Quando**: data, numero di persone e voucher. Un voucher valido sceglie già i suoi trattamenti e il nome del destinatario. |
| ![Passo 2](anteprime/30-sito-f2-cosa.png) | **2. Cosa scegliete**: un riquadro per persona con i trattamenti divisi per categoria (durata e, se attivo, prezzo). Per ogni trattamento scelto si vedono solo gli orari ancora liberi. «Come la persona 1» copia le scelte. |
| ![Passo 3](anteprime/30-sito-f3-dati-de.png) | **3. I tuoi dati**: nome, cognome, telefono con prefisso, email e note. Senza nome e telefono non si va avanti. Qui in tedesco. |
| ![Passo 4](anteprime/30-sito-f4-riepilogo.png) | **4. Controlla e invia**: riepilogo con data, trattamenti per persona, contatto e, se attivo, il totale indicativo. |
| ![Inviata](anteprime/30-sito-f5-inviata-en.png) | **Inviata**: il codice della richiesta in grande. La richiesta arriva in Nuovo › Lista richieste con la campanella. Qui in inglese. |

**Lingue.** Italiano, inglese e tedesco. La lingua si sceglie da sola dal
browser dell'ospite e si cambia con IT, EN e DE in alto. I nomi dei
trattamenti restano quelli scritti in Configurazione.

**Impostazioni** (Sito web):
- indirizzo pubblico di Home Assistant;
- «Mostra prezzi e totale indicativo»;
- colore principale.

Sul telefono le schede dei trattamenti si mettono su due colonne:

![Telefono](anteprime/30-sito-f6-telefono.png)

---

## Aggiornamenti

![Nuova versione](anteprime/29-aggiornamento.png)

Se Spa Booking è installato da HACS, l'Amministratore vede in alto il
riquadro **Nuova versione di Spa Booking**:
- *Novità* apre le note della versione;
- *Installa* la scarica e la installa;
- *Più tardi* nasconde l'avviso.

Mentre si installa si può continuare a lavorare.

![Riavvio](anteprime/29b-aggiornamento-riavvio.png)

Finita l'installazione, la card controlla cosa è cambiato:
- **solo la card o il modulo del sito**: basta *Ricarica la pagina*, senza
  riavviare Home Assistant;
- **il programma dell'integrazione**: serve riavviare Home Assistant. *Riavvia
  ora* lo fa subito (circa un minuto, le prenotazioni non si perdono),
  *Più tardi* rimanda.

Home Assistant carica il programma delle integrazioni una sola volta
all'avvio e non può sostituirlo mentre funziona: per questo un aggiornamento
del programma richiede sempre un riavvio.

Le beta compaiono solo se in HACS, nella pagina di Spa Booking, è attivo
«Mostra le versioni beta».

---

## Telefono e tablet

| | | |
|---|---|---|
| ![Agenda](anteprime/24-telefono-agenda.png) | ![Voucher](anteprime/25-telefono-voucher.png) | ![WhatsApp](anteprime/26-telefono-whatsapp.png) |

Sul telefono le schede diventano icone e i numeri si dispongono su due
colonne. WhatsApp mostra prima l'elenco delle conversazioni e poi la chat,
con la freccia per tornare indietro.

![Tema scuro](anteprime/27-tema-scuro.png)

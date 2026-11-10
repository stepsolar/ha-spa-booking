# Spa Booking — guida alle schede (2.2)

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

### Nuova richiesta

![Nuova richiesta](anteprime/04-nuova-richiesta.png)

Una richiesta non occupa ancora l'agenda: si usa quando l'ospite chiede ma
l'orario va confermato. Con 2 o più persone c'è un riquadro per persona
(*Copia dalla 1ª* ripete i trattamenti). Al salvataggio l'ospite riceve
il messaggio di conferma ricezione su WhatsApp.

### Lista richieste

![Lista richieste](anteprime/05-lista-richieste.png)

Le richieste arrivate da reception, dal sito WordPress o da WhatsApp. Ogni
richiesta ha i pulsanti *Modifica*, *Conferma* (crea gli appuntamenti) ed
*Elimina*. La campanella in alto conta le richieste dal sito non ancora
aperte.

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
| ![Categorie](anteprime/12-config-categorie.png) | **Categorie**: colore, giorni e fasce, pausa tra un trattamento e l'altro, se serve un'operatrice. |
| ![Trattamenti](anteprime/13-config-trattamenti.png) | **Trattamenti**: durata, prezzo, persone insieme, visibilità sul sito, operatrici abilitate. |
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

## Telefono e tablet

| | | |
|---|---|---|
| ![Agenda](anteprime/24-telefono-agenda.png) | ![Voucher](anteprime/25-telefono-voucher.png) | ![WhatsApp](anteprime/26-telefono-whatsapp.png) |

Sul telefono le schede diventano icone e i numeri si dispongono su due
colonne. WhatsApp mostra prima l'elenco delle conversazioni e poi la chat,
con la freccia per tornare indietro.

![Tema scuro](anteprime/27-tema-scuro.png)

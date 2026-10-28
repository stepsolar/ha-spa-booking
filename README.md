# Spa Booking — integrazione Home Assistant

Gestione degli appuntamenti della SPA all'interno di Home Assistant: categorie,
trattamenti con durata propria, operatori, schede cliente, agenda del giorno
raggruppata per operatore e per categoria, pagamenti, voucher/promozioni,
promemoria e report automatici.

Versione corrente: **2.0.5**

## Funzionalita' principali

- **Agenda giorno** per operatori e categorie, con colori per gruppo-partito.
- **Nuovo appuntamento multipersona / multitreatment** ("Nuovo appuntamento"), gestito con `create_bookings` in un unico batch.
- **Visualizzazione flessibile** del singolo appuntamento oppure **raggruppata** (tutti gli appuntamenti della stessa persona/giornata), con totali aggregati e schede pagamento.
- **Modifica gruppo**: editor multi-riga (2 colonne, blocchi draggable) che aggiorna/aggiunge/cancella sotto-appuntamenti preservando id, codici, check-in/out e registrazioni incassi.
- **Pagamenti e totali**: importi per persona/trattamento, takings multi-metodo, saldo da incassare.
- **Clienti**: schede con deduplicazione per telefono.
- **Operatori**: orari, pause, ruoli, recapiti, offerte (`offer_state`), conferma manuale.
- **Voucher & promozioni**: creazione/vendita, estensione, promo automatica.
- **Richieste dal sito**: endpoint pubblici per prenotazioni web con token sicuro.
- **Notifiche**: WhatsApp via WAHA o webhook, Telegram, comandi di test.
- **Report mensile**, promemoria appuntamenti, richieste recensioni.
- **Backup/ripristino**: JSON completo (`export_all` / `import_all`) e CSV clienti.
- **Card Lovelace** `spa-booking-card.js` servita automaticamente dal backend.

## Installazione manuale (senza HACS)

1. Copia il contenuto della cartella `custom_components/spa_booking/` in:
   `/config/custom_components/spa_booking/`
2. Copia il contenuto della cartella `www/spa_booking/` in:
   `/config/www/spa_booking/`
3. Riavvia Home Assistant (Supervisor -> Riavvia) oppure ricarica l'integrazione:
   Impostazioni -> Integrazioni -> SPA Booking -> menu (tre punti) -> Ricarica.
4. Aggiungi l'integrazione: Impostazioni -> Integrazioni -> Aggiungi -> "Spa Booking".
5. Dopo il primo avvio, il frontend carica automaticamente la card dal backend (`card_js_url`).

## Installazione tramite HACS (repository personalizzato)
1. In HACS -> Integrations -> tre puntini -> Custom repositories -> inserisci:
   `https://github.com/stepsolar/ha-spa-booking`
2. Clicca "Add" e seleziona categoria "Integration".
3. Cerca "Spa Booking", installa e riavvia HA.

## File importanti della repo
- `custom_components/spa_booking/` — integrazione completa (Python).
- `www/spa_booking/spa-booking-card.js` — card Lovelace.
- `manifest.json` — metadati (`version`, `documentation`, `issue_tracker`).
- `services.yaml` — definizioni dei servizi `spa_booking.*`.
- `README.md` — questo file.

## Configurazione minima
Dopo l'installazione l'integrazione crea un'entry configurabile dall'UI:
- `telegram_config_entry_id`, `report_telegram_chats`, `report_whatsapp_chat`
- orari web (`web_open_time`, `web_close_time`, `web_step_min`)
- trattamenti/operatori configurabili da card e servizi dedicati.

## Servizi principali
- `spa_booking.create_bookings`, `create_appointment`, `update_appointment`, `cancel_appointment`
- `spa_booking.update_booking_batch` (modifica completa multi-riga)
- `spa_booking.export_data`, `spa_booking.export_all`
- `spa_booking.import_data`, `spa_booking.import_all`
- `spa_booking.export_clienti_csv`, `spa_booking.import_clienti_csv`
- `spa_booking.reload_card` (bust-cache frontend)
- `spa_booking.get_config`, `spa_booking.get_daily_agenda`
- `spa_booking.add_payment`, `spa_booking.send_guest_summary`, `spa_booking.send_deposit_request`
- `spa_booking.manual_confirm_offer`, `spa_booking.set_offer_state`

## Backup e restore
- **Esporta JSON completo**: Impostazioni -> scheda "Backup / Ripristino" -> "Esporta JSON".
- **Ripristina JSON**: Impostazioni -> scheda "Backup / Ripristino" -> "Ripristina JSON" (file picker).
- Il file si chiama `spa_booking_backup_YYYY-MM-DD.json` e puo' essere importato via file picker.

## Note operative
- Il card si versiona automaticamente tramite hash del file; ricarica con `spa_booking.reload_card`.
- Tutti i pagamenti/incassi restano associati anche durante l'editing (`update_batch` preserva id storici).
- Le schede clienti sono deduplicate per telefono; operatori e trattamenti si gestiscono da card.

## Changelog recente
- **v2.0.7**: conserva lo stato dell’offerta agli operatori (pending/unassigned) durante la modifica di un appuntamento o del gruppo; invalidazione solo se cambiano trattamento, operatore o orario; pulsante check-in agenda.\n- **v2.0.6**: toggle "Mostra/Nascondi appuntamenti check-in" in agenda, permessi admin, rollback transazionale, migrazione batch_id, icone standalone.\n- **v2.0.5**: raggruppa tutti gli appuntamenti dello stesso cliente nella stessa giornata (incluse categorie diverse), Vista Singolo/Raggruppato, batch_id propagation, bug "Massaggi non raggruppati" risolto.
- **v2.0.2–v2.0.4**: editor batch multi-riga, correzioni migrazione/premessa.
- **v2.0.0–v2.0.1**: backup JSON/import_all, scheda "Backup", link docs GitHub.

## Licenza e autore
Autore: stepsolar.

## Contributi
Apri issue/PR su `https://github.com/stepsolar/ha-spa-booking`.

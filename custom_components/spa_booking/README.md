# Spa Booking

Home Assistant integration for SPA Booking management: managing appointments, treatments with their duration, operators, client cards and a day agenda grouped by operator and category.

## Version 2.0.0

### Novità

- **Backup/Ripristino JSON nella scheda Impostazioni**
  - "Esporta JSON" → genera e scarica `spa_booking_backup_YYYY-MM-DD.json` con tutti i dati (impostazioni, trattamenti, operatori, clienti, appuntamenti, richieste, voucher, ecc.)
  - "Ripristina JSON" → file picker per selezionare un file `.json` e ripristinare tutto tramite `import_all`

- **Servizi `export_all` / `import_all`** registrati per l'accesso diretto ai servizi di backup/ripristino

- **Fix clipboard** robusto per "Copia codice per il sito": usa prima `navigator.clipboard.writeText()`, poi fallback `<textarea>` + `document.execCommand("copy")`

- **Documentazione GitHub** linkata nel manifest e nei file di configurazione

### Novità della versione 2.0.0

- Nuova gestione backup completo in formato JSON con download file dedicato
- Separazione totale tra box "Backup / Ripristino" e box "Clienti" (esportazione/importazione CSV)
- Servizi `spa_booking.export_all` e `spa_booking.import_all` disponibili anche senza passare dalla card
- Interfaccia utente rinnovata nella scheda Impostazioni

### Installazione

1. Copiare `custom_components/spa_booking` in `config/custom_components/`
2. Copiare `www/spa_booking/` in `config/www/`
3. Oppure installare l'add-on dallo store
4. Riavviare Home Assistant
5. Aggiungere l'integrazione "SPA Booking"

### Documentazione

- Repository: https://github.com/stepsolar/ha-spa-booking/
- Issues e Discuss: https://github.com/stepsolar/ha-spa-booking/issues

# Programma WhatsApp integrato

`spa-wa-bridge-linux-amd64` è il collegamento WhatsApp integrato in Spa Booking
(beta). È compilato dai sorgenti in [`bridge/`](../../../bridge) del repository,
basati sulla libreria open source [whatsmeow](https://github.com/tulir/whatsmeow)
(MPL-2.0), con:

```bash
cd bridge
CGO_ENABLED=0 GOOS=linux GOARCH=amd64 go build -trimpath -ldflags "-s -w -X main.version=2.2.0b1" \
  -o ../custom_components/spa_booking/bin/spa-wa-bridge-linux-amd64 .
```

L'impronta del file è in `SHA256SUMS`. L'integrazione lo avvia da sola quando in
Configurazione › WhatsApp scegli «WhatsApp integrato»; ascolta solo su
127.0.0.1 e accetta richieste solo con una chiave generata a ogni avvio.

Per ora è incluso solo il programma per processori Intel/AMD a 64 bit.

// spa-wa-bridge: the WhatsApp connection built into Spa Booking.
//
// It links to the hotel's WhatsApp number as a "linked device" (like
// WhatsApp Web) through the whatsmeow library, and offers Home Assistant a
// tiny HTTP API on 127.0.0.1 only, protected by a token the integration
// generates at every start:
//
//	GET  /status        state, linked number, current QR code (PNG data URI)
//	POST /pair/start    start linking: QR codes appear in /status
//	POST /pair/code     {"phone": "39..."} -> 8-character code for "link with phone number"
//	POST /logout        unlink this device
//	POST /send/text     {"chat_id", "text"} -> {"sent", "message_id", "error"}
//	POST /send/image    {"chat_id", "image" (base64), "mimetype", "caption"}
//	GET  /lid?lid=...   phone chat id behind a LID, when known
//	GET  /events        newline-delimited JSON: messages, reactions, state changes
//
// Messages and reactions are reported in the same shape the WAHA add-on
// posts to its webhook, so the integration handles both the same way.
package main

import (
	"context"
	"crypto/subtle"
	"encoding/base64"
	"encoding/json"
	"errors"
	"flag"
	"fmt"
	"log"
	"net"
	"net/http"
	"os"
	"os/signal"
	"path/filepath"
	"strings"
	"sync"
	"syscall"
	"time"

	_ "github.com/ncruces/go-sqlite3/driver"
	qrcode "github.com/skip2/go-qrcode"
	"go.mau.fi/whatsmeow"
	"go.mau.fi/whatsmeow/proto/waE2E"
	"go.mau.fi/whatsmeow/store"
	"go.mau.fi/whatsmeow/store/sqlstore"
	"go.mau.fi/whatsmeow/types"
	"go.mau.fi/whatsmeow/types/events"
	waLog "go.mau.fi/whatsmeow/util/log"
	"google.golang.org/protobuf/proto"
)

// Set at build time with -ldflags "-X main.version=...".
var version = "dev"

const (
	// Events are reported as WAHA does, with this session name.
	sessionName = "spa"
	// Minimum pause between two outgoing messages: a burst of promotions
	// sent in a few milliseconds is exactly what gets a number flagged.
	minSendGap = 1500 * time.Millisecond
	// How long "is typing…" is shown before a message, at most.
	maxTyping = 3 * time.Second
	// Answers about who is on WhatsApp are kept this long.
	onWhatsAppTTL = 24 * time.Hour
)

// Connection states reported in /status and as "state" events.
const (
	stateStarting     = "starting"
	stateNotLinked    = "not_linked"
	statePairing      = "pairing"
	stateConnecting   = "connecting"
	stateConnected    = "connected"
	stateDisconnected = "disconnected"
	stateLoggedOut    = "logged_out"
	stateBanned       = "banned"
)

type bridge struct {
	client *whatsmeow.Client
	token  string

	mu         sync.Mutex
	state      string
	detail     string
	qrCode     string
	qrExpires  time.Time
	pairCancel context.CancelFunc

	sendMu   sync.Mutex
	lastSend time.Time

	waMu    sync.Mutex
	onWA    map[string]onWAEntry
	subsMu  sync.Mutex
	subs    map[chan []byte]struct{}
	started time.Time
}

type onWAEntry struct {
	on  bool
	at  time.Time
	jid types.JID
}

func main() {
	listen := flag.String("listen", "127.0.0.1:0", "address of the local HTTP API")
	dataDir := flag.String("data", ".", "folder for the session database")
	name := flag.String("name", "Spa Booking", "device name shown on the phone")
	logLevel := flag.String("log", "WARN", "log level: DEBUG, INFO, WARN, ERROR")
	flag.Parse()

	token := os.Getenv("SPA_WA_TOKEN")
	if token == "" {
		log.Fatal("SPA_WA_TOKEN is required")
	}
	if !strings.HasPrefix(*listen, "127.0.0.1:") && !strings.HasPrefix(*listen, "localhost:") {
		log.Fatal("the API only listens on 127.0.0.1")
	}
	// The session database holds the keys of the linked device: readable by
	// this process only.
	syscall.Umask(0o077)
	if err := os.MkdirAll(*dataDir, 0o700); err != nil {
		log.Fatalf("data folder: %v", err)
	}

	ctx, stop := signal.NotifyContext(context.Background(), os.Interrupt, syscall.SIGTERM)
	defer stop()

	store.SetOSInfo(*name, [3]uint32{2, 2, 0})
	dbLog := waLog.Stdout("Database", *logLevel, false)
	dsn := "file:" + filepath.Join(*dataDir, "whatsapp.db") +
		"?_pragma=foreign_keys(1)&_pragma=busy_timeout(10000)&_pragma=journal_mode(wal)"
	container, err := sqlstore.New(ctx, "sqlite3", dsn, dbLog)
	if err != nil {
		log.Fatalf("session database: %v", err)
	}
	device, err := container.GetFirstDevice(ctx)
	if err != nil {
		log.Fatalf("session: %v", err)
	}

	b := &bridge{
		client:  whatsmeow.NewClient(device, waLog.Stdout("Client", *logLevel, false)),
		token:   token,
		state:   stateStarting,
		onWA:    map[string]onWAEntry{},
		subs:    map[chan []byte]struct{}{},
		started: time.Now(),
	}
	b.client.AddEventHandler(b.handleEvent)

	listener, err := net.Listen("tcp", *listen)
	if err != nil {
		log.Fatalf("listen: %v", err)
	}
	// The integration reads this line to learn the port.
	fmt.Printf("SPA_WA_LISTEN %s\n", listener.Addr().String())

	server := &http.Server{Handler: b.routes(), ReadHeaderTimeout: 10 * time.Second}
	go func() {
		if err := server.Serve(listener); err != nil && !errors.Is(err, http.ErrServerClosed) {
			log.Fatalf("http: %v", err)
		}
	}()

	if b.client.Store.ID == nil {
		b.setState(stateNotLinked, "")
	} else {
		b.setState(stateConnecting, "")
		go b.connect()
	}

	<-ctx.Done()
	shutdown, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()
	_ = server.Shutdown(shutdown)
	b.client.Disconnect()
}

// connect opens the connection of an already linked device.
func (b *bridge) connect() {
	if err := b.client.Connect(); err != nil {
		b.setState(stateDisconnected, err.Error())
	}
}

// ------------------------------------------------------------------ state

func (b *bridge) setState(state, detail string) {
	b.mu.Lock()
	changed := b.state != state || b.detail != detail
	b.state, b.detail = state, detail
	if state != statePairing {
		b.qrCode = ""
	}
	b.mu.Unlock()
	if changed {
		b.publish(map[string]any{"event": "state", "session": sessionName, "state": state, "detail": detail})
	}
}

func (b *bridge) handleEvent(evt any) {
	switch e := evt.(type) {
	case *events.Connected:
		b.setState(stateConnected, "")
	case *events.PairSuccess:
		b.setState(stateConnecting, "")
	case *events.Disconnected:
		b.setState(stateDisconnected, "connessione persa, nuovo tentativo in corso")
	case *events.KeepAliveTimeout:
		b.setState(stateDisconnected, "connessione lenta")
	case *events.StreamReplaced:
		b.setState(stateDisconnected, "un altro programma ha aperto la stessa sessione")
	case *events.LoggedOut:
		b.setState(stateLoggedOut, "dispositivo scollegato dal telefono")
	case *events.TemporaryBan:
		b.setState(stateBanned, e.String())
	case *events.ClientOutdated:
		b.setState(stateDisconnected, "versione di WhatsApp non più accettata: aggiorna Spa Booking")
	case *events.ConnectFailure:
		b.setState(stateDisconnected, fmt.Sprintf("connessione rifiutata (%v)", e.Reason))
	case *events.Message:
		b.handleMessage(e)
	}
}

// chatID spells a JID the way WAHA does: phone numbers as "@c.us".
func chatID(jid types.JID) string {
	jid = jid.ToNonAD()
	if jid.Server == types.DefaultUserServer {
		return jid.User + "@c.us"
	}
	return jid.String()
}

// senderOf returns the direct chat to answer: the phone number when known.
func (b *bridge) senderOf(info types.MessageInfo) types.JID {
	sender := info.Chat
	if sender.Server == types.HiddenUserServer {
		if !info.SenderAlt.IsEmpty() && info.SenderAlt.Server == types.DefaultUserServer {
			return info.SenderAlt
		}
		if b.client.Store.LIDs == nil {
			return sender
		}
		if pn, err := b.client.Store.LIDs.GetPNForLID(context.Background(), sender.ToNonAD()); err == nil && !pn.IsEmpty() {
			return pn
		}
	}
	return sender
}

func (b *bridge) handleMessage(e *events.Message) {
	info := e.Info
	if info.IsGroup || info.Chat.Server == types.BroadcastServer || info.Chat.Server == types.NewsletterServer {
		return
	}
	msg := e.Message
	if msg == nil {
		return
	}
	from := chatID(b.senderOf(info))
	if reaction := msg.GetReactionMessage(); reaction != nil {
		b.publish(map[string]any{
			"event":   "message.reaction",
			"session": sessionName,
			"id":      "reaction_" + info.ID,
			"payload": map[string]any{
				"id":     info.ID,
				"from":   from,
				"fromMe": info.IsFromMe,
				"reaction": map[string]any{
					"text":      reaction.GetText(),
					"messageId": reaction.GetKey().GetID(),
				},
				"timestamp": info.Timestamp.Unix(),
			},
		})
		return
	}
	body := msg.GetConversation()
	if body == "" {
		body = msg.GetExtendedTextMessage().GetText()
	}
	hasMedia := msg.GetImageMessage() != nil || msg.GetAudioMessage() != nil ||
		msg.GetVideoMessage() != nil || msg.GetDocumentMessage() != nil || msg.GetStickerMessage() != nil
	if body == "" {
		body = msg.GetImageMessage().GetCaption()
	}
	if body == "" && !hasMedia {
		return
	}
	b.publish(map[string]any{
		"event":   "message",
		"session": sessionName,
		"id":      info.ID,
		"payload": map[string]any{
			"id":         info.ID,
			"from":       from,
			"fromMe":     info.IsFromMe,
			"body":       body,
			"hasMedia":   hasMedia,
			"notifyName": info.PushName,
			"timestamp":  info.Timestamp.Unix(),
		},
	})
}

// ----------------------------------------------------------------- events

func (b *bridge) publish(event map[string]any) {
	line, err := json.Marshal(event)
	if err != nil {
		return
	}
	line = append(line, '\n')
	b.subsMu.Lock()
	defer b.subsMu.Unlock()
	for ch := range b.subs {
		select {
		case ch <- line:
		default: // a reader that is not keeping up loses events, never blocks WhatsApp
		}
	}
}

func (b *bridge) serveEvents(w http.ResponseWriter, r *http.Request) {
	flusher, ok := w.(http.Flusher)
	if !ok {
		http.Error(w, "streaming unsupported", http.StatusInternalServerError)
		return
	}
	ch := make(chan []byte, 256)
	b.subsMu.Lock()
	b.subs[ch] = struct{}{}
	b.subsMu.Unlock()
	defer func() {
		b.subsMu.Lock()
		delete(b.subs, ch)
		b.subsMu.Unlock()
	}()
	w.Header().Set("Content-Type", "application/x-ndjson")
	w.WriteHeader(http.StatusOK)
	b.mu.Lock()
	first, _ := json.Marshal(map[string]any{"event": "state", "session": sessionName, "state": b.state, "detail": b.detail})
	b.mu.Unlock()
	_, _ = w.Write(append(first, '\n'))
	flusher.Flush()
	keepalive := time.NewTicker(20 * time.Second)
	defer keepalive.Stop()
	for {
		select {
		case <-r.Context().Done():
			return
		case line := <-ch:
			if _, err := w.Write(line); err != nil {
				return
			}
			flusher.Flush()
		case <-keepalive.C:
			if _, err := w.Write([]byte("{\"event\":\"ping\"}\n")); err != nil {
				return
			}
			flusher.Flush()
		}
	}
}

// ------------------------------------------------------------------- HTTP

func (b *bridge) routes() http.Handler {
	mux := http.NewServeMux()
	mux.HandleFunc("GET /status", b.serveStatus)
	mux.HandleFunc("POST /pair/start", b.servePairStart)
	mux.HandleFunc("POST /pair/code", b.servePairCode)
	mux.HandleFunc("POST /logout", b.serveLogout)
	mux.HandleFunc("POST /send/text", b.serveSendText)
	mux.HandleFunc("POST /send/image", b.serveSendImage)
	mux.HandleFunc("GET /lid", b.serveLID)
	mux.HandleFunc("GET /events", b.serveEvents)
	return b.auth(mux)
}

func (b *bridge) auth(next http.Handler) http.Handler {
	want := []byte("Bearer " + b.token)
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if subtle.ConstantTimeCompare([]byte(r.Header.Get("Authorization")), want) != 1 {
			http.Error(w, "unauthorized", http.StatusUnauthorized)
			return
		}
		next.ServeHTTP(w, r)
	})
}

func writeJSON(w http.ResponseWriter, status int, body any) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	_ = json.NewEncoder(w).Encode(body)
}

func readJSON(r *http.Request, into any) error {
	return json.NewDecoder(http.MaxBytesReader(nil, r.Body, 16<<20)).Decode(into)
}

func (b *bridge) serveStatus(w http.ResponseWriter, _ *http.Request) {
	b.mu.Lock()
	state, detail, code, expires := b.state, b.detail, b.qrCode, b.qrExpires
	b.mu.Unlock()
	body := map[string]any{
		"state":   state,
		"detail":  detail,
		"version": version,
		"engine":  "whatsmeow",
		"uptime":  int(time.Since(b.started).Seconds()),
	}
	if id := b.client.Store.ID; id != nil {
		body["phone"] = id.User
		body["push_name"] = b.client.Store.PushName
	}
	if code != "" {
		if png, err := qrcode.Encode(code, qrcode.Medium, 320); err == nil {
			body["qr"] = "data:image/png;base64," + base64.StdEncoding.EncodeToString(png)
			body["qr_expires_in"] = int(time.Until(expires).Seconds())
		}
	}
	writeJSON(w, http.StatusOK, body)
}

// servePairStart starts the QR flow of a device that is not linked yet.
func (b *bridge) servePairStart(w http.ResponseWriter, _ *http.Request) {
	if b.client.Store.ID != nil {
		writeJSON(w, http.StatusConflict, map[string]any{"error": "già collegato"})
		return
	}
	b.mu.Lock()
	if b.pairCancel != nil {
		b.pairCancel()
	}
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Minute)
	b.pairCancel = cancel
	b.mu.Unlock()

	b.client.Disconnect()
	qrChan, err := b.client.GetQRChannel(ctx)
	if err != nil {
		cancel()
		writeJSON(w, http.StatusInternalServerError, map[string]any{"error": err.Error()})
		return
	}
	if err := b.client.Connect(); err != nil {
		cancel()
		b.setState(stateNotLinked, err.Error())
		writeJSON(w, http.StatusBadGateway, map[string]any{"error": "WhatsApp non raggiungibile: " + err.Error()})
		return
	}
	b.setState(statePairing, "")
	go func() {
		defer cancel()
		for item := range qrChan {
			switch item.Event {
			case whatsmeow.QRChannelEventCode:
				b.mu.Lock()
				b.qrCode = item.Code
				b.qrExpires = time.Now().Add(item.Timeout)
				b.mu.Unlock()
				b.publish(map[string]any{"event": "qr", "session": sessionName})
			case "success":
				b.setState(stateConnecting, "")
				return
			case whatsmeow.QRChannelEventError:
				b.setState(stateNotLinked, fmt.Sprint(item.Error))
				return
			default:
				if b.client.Store.ID == nil {
					b.setState(stateNotLinked, "tempo scaduto: riprova")
					b.client.Disconnect()
				}
				return
			}
		}
	}()
	writeJSON(w, http.StatusOK, map[string]any{"state": statePairing})
}

// servePairCode links with an 8-character code typed on the phone, for when
// the card is open on the very phone that has to scan the QR code.
func (b *bridge) servePairCode(w http.ResponseWriter, r *http.Request) {
	var req struct {
		Phone string `json:"phone"`
	}
	if err := readJSON(r, &req); err != nil {
		writeJSON(w, http.StatusBadRequest, map[string]any{"error": "richiesta non valida"})
		return
	}
	phone := strings.Map(func(c rune) rune {
		if c >= '0' && c <= '9' {
			return c
		}
		return -1
	}, req.Phone)
	if len(phone) < 8 {
		writeJSON(w, http.StatusBadRequest, map[string]any{"error": "numero non valido"})
		return
	}
	b.mu.Lock()
	pairing := b.state == statePairing
	b.mu.Unlock()
	if !pairing {
		writeJSON(w, http.StatusConflict, map[string]any{"error": "avvia prima il collegamento"})
		return
	}
	ctx, cancel := context.WithTimeout(r.Context(), 30*time.Second)
	defer cancel()
	code, err := b.client.PairPhone(ctx, phone, true, whatsmeow.PairClientChrome, "Chrome (Linux)")
	if err != nil {
		writeJSON(w, http.StatusBadGateway, map[string]any{"error": err.Error()})
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"code": code})
}

func (b *bridge) serveLogout(w http.ResponseWriter, r *http.Request) {
	b.mu.Lock()
	if b.pairCancel != nil {
		b.pairCancel()
		b.pairCancel = nil
	}
	b.mu.Unlock()
	if b.client.Store.ID != nil {
		ctx, cancel := context.WithTimeout(r.Context(), 20*time.Second)
		defer cancel()
		if err := b.client.Logout(ctx); err != nil {
			// Unlinked anyway on our side: the phone shows the device until
			// the next time it connects.
			_ = b.client.Store.Delete(ctx)
		}
	}
	b.client.Disconnect()
	b.setState(stateNotLinked, "")
	writeJSON(w, http.StatusOK, map[string]any{"state": stateNotLinked})
}

// parseChat turns "39…@c.us", "…@g.us", "…@lid" or a bare number into a JID.
func parseChat(raw string) (types.JID, error) {
	raw = strings.TrimSpace(raw)
	user, server, found := strings.Cut(raw, "@")
	if !found {
		server = "c.us"
	}
	user = strings.TrimPrefix(user, "+")
	if user == "" {
		return types.JID{}, errors.New("nessun destinatario")
	}
	switch server {
	case "c.us", types.DefaultUserServer:
		for _, c := range user {
			if c < '0' || c > '9' {
				return types.JID{}, errors.New("numero non valido")
			}
		}
		return types.NewJID(user, types.DefaultUserServer), nil
	case types.GroupServer:
		return types.NewJID(user, types.GroupServer), nil
	case types.HiddenUserServer:
		return types.NewJID(user, types.HiddenUserServer), nil
	}
	return types.JID{}, fmt.Errorf("destinatario non supportato: %s", raw)
}

// resolveRecipient checks once a day that a phone number is on WhatsApp.
func (b *bridge) resolveRecipient(ctx context.Context, jid types.JID) (types.JID, error) {
	if jid.Server != types.DefaultUserServer {
		return jid, nil
	}
	b.waMu.Lock()
	cached, ok := b.onWA[jid.User]
	b.waMu.Unlock()
	if ok && time.Since(cached.at) < onWhatsAppTTL {
		if !cached.on {
			return jid, errors.New("numero non presente su WhatsApp")
		}
		return cached.jid, nil
	}
	answers, err := b.client.IsOnWhatsApp(ctx, []string{"+" + jid.User})
	if err != nil || len(answers) == 0 {
		// Not knowing is not a reason to refuse: try the send anyway.
		return jid, nil
	}
	entry := onWAEntry{on: answers[0].IsIn, at: time.Now(), jid: jid}
	if answers[0].IsIn && !answers[0].JID.IsEmpty() {
		entry.jid = answers[0].JID
	}
	b.waMu.Lock()
	b.onWA[jid.User] = entry
	b.waMu.Unlock()
	if !entry.on {
		return jid, errors.New("numero non presente su WhatsApp")
	}
	return entry.jid, nil
}

// pace keeps a human rhythm: a pause between sends and "is typing…".
func (b *bridge) pace(ctx context.Context, to types.JID, length int) {
	b.sendMu.Lock()
	wait := minSendGap - time.Since(b.lastSend)
	b.lastSend = time.Now().Add(max(wait, 0))
	b.sendMu.Unlock()
	if wait > 0 {
		select {
		case <-time.After(wait):
		case <-ctx.Done():
		}
	}
	typing := time.Duration(length) * 25 * time.Millisecond
	typing = min(max(typing, 600*time.Millisecond), maxTyping)
	_ = b.client.SendChatPresence(ctx, to, types.ChatPresenceComposing, types.ChatPresenceMediaText)
	select {
	case <-time.After(typing):
	case <-ctx.Done():
	}
	_ = b.client.SendChatPresence(ctx, to, types.ChatPresencePaused, types.ChatPresenceMediaText)
}

func (b *bridge) ready(w http.ResponseWriter) bool {
	if b.client.Store.ID == nil {
		writeJSON(w, http.StatusOK, map[string]any{"sent": false, "error": "WhatsApp non collegato"})
		return false
	}
	if !b.client.IsConnected() {
		writeJSON(w, http.StatusOK, map[string]any{"sent": false, "error": "WhatsApp non connesso"})
		return false
	}
	return true
}

func (b *bridge) send(w http.ResponseWriter, r *http.Request, rawChat string, length int, build func(ctx context.Context) (*waE2E.Message, error)) {
	ctx, cancel := context.WithTimeout(r.Context(), 60*time.Second)
	defer cancel()
	to, err := parseChat(rawChat)
	if err != nil {
		writeJSON(w, http.StatusOK, map[string]any{"sent": false, "error": err.Error()})
		return
	}
	if !b.ready(w) {
		return
	}
	to, err = b.resolveRecipient(ctx, to)
	if err != nil {
		writeJSON(w, http.StatusOK, map[string]any{"sent": false, "error": err.Error()})
		return
	}
	msg, err := build(ctx)
	if err != nil {
		writeJSON(w, http.StatusOK, map[string]any{"sent": false, "error": err.Error()})
		return
	}
	b.pace(ctx, to, length)
	resp, err := b.client.SendMessage(ctx, to, msg)
	if err != nil {
		writeJSON(w, http.StatusOK, map[string]any{"sent": false, "error": err.Error()})
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"sent": true, "message_id": resp.ID})
}

func (b *bridge) serveSendText(w http.ResponseWriter, r *http.Request) {
	var req struct {
		ChatID string `json:"chat_id"`
		Text   string `json:"text"`
	}
	if err := readJSON(r, &req); err != nil || strings.TrimSpace(req.Text) == "" {
		writeJSON(w, http.StatusBadRequest, map[string]any{"sent": false, "error": "richiesta non valida"})
		return
	}
	b.send(w, r, req.ChatID, len(req.Text), func(context.Context) (*waE2E.Message, error) {
		return &waE2E.Message{Conversation: proto.String(req.Text)}, nil
	})
}

func (b *bridge) serveSendImage(w http.ResponseWriter, r *http.Request) {
	var req struct {
		ChatID   string `json:"chat_id"`
		Image    string `json:"image"`
		Mimetype string `json:"mimetype"`
		Caption  string `json:"caption"`
	}
	if err := readJSON(r, &req); err != nil {
		writeJSON(w, http.StatusBadRequest, map[string]any{"sent": false, "error": "richiesta non valida"})
		return
	}
	data, err := base64.StdEncoding.DecodeString(req.Image)
	if err != nil || len(data) == 0 {
		writeJSON(w, http.StatusBadRequest, map[string]any{"sent": false, "error": "immagine non valida"})
		return
	}
	if req.Mimetype == "" {
		req.Mimetype = http.DetectContentType(data)
	}
	b.send(w, r, req.ChatID, len(req.Caption), func(ctx context.Context) (*waE2E.Message, error) {
		up, err := b.client.Upload(ctx, data, whatsmeow.MediaImage)
		if err != nil {
			return nil, fmt.Errorf("caricamento immagine: %w", err)
		}
		return &waE2E.Message{ImageMessage: &waE2E.ImageMessage{
			Caption:       proto.String(req.Caption),
			Mimetype:      proto.String(req.Mimetype),
			URL:           proto.String(up.URL),
			DirectPath:    proto.String(up.DirectPath),
			MediaKey:      up.MediaKey,
			FileEncSHA256: up.FileEncSHA256,
			FileSHA256:    up.FileSHA256,
			FileLength:    proto.Uint64(up.FileLength),
		}}, nil
	})
}

func (b *bridge) serveLID(w http.ResponseWriter, r *http.Request) {
	jid, err := parseChat(r.URL.Query().Get("lid"))
	if err != nil || jid.Server != types.HiddenUserServer {
		writeJSON(w, http.StatusBadRequest, map[string]any{"error": "LID non valido"})
		return
	}
	if b.client.Store.ID == nil || b.client.Store.LIDs == nil {
		// Nothing is known before the number is linked.
		writeJSON(w, http.StatusOK, map[string]any{"chat_id": nil})
		return
	}
	pn, err := b.client.Store.LIDs.GetPNForLID(r.Context(), jid)
	if err != nil || pn.IsEmpty() {
		writeJSON(w, http.StatusOK, map[string]any{"chat_id": nil})
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"chat_id": chatID(pn)})
}

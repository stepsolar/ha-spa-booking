"""Constants for the SPA Booking integration."""

from __future__ import annotations

from typing import Final

DOMAIN: Final = "spa_booking"
INTEGRATION_NAME: Final = "Spa Booking"

#: Management card. It is served by the integration's own HTTP view
#: (card_view.py) rather than from /local, so it is never stuck behind Home
#: Assistant's ~31 day cache of /local/*: the view answers no-cache + ETag, so
#: every load revalidates and a changed card is picked up at once. No version
#: query is needed for that; CARD_JS_VERSION is only the settings fallback.
CARD_JS_VERSION: Final = "1.108.0"
CARD_JS_URL: Final = "/api/spa_booking/card.js"
#: The old /local URL, still dropped from the frontend when re-registering.
CARD_JS_URL_LEGACY: Final = "/local/spa_booking/spa-booking-card.js"

#: Minutes of pause required after an appointment of a category before the
#: masseuse can take the next one. Per-category and editable from the card.
DEFAULT_CATEGORY_PAUSE_MIN: Final = 10

#: How the management card paints itself. "auto" follows whatever Home
#: Assistant theme is active, so the card never fights the dashboard; "light"
#: and "dark" force the card on its own, independently of the global theme.
#: Stored in the settings, therefore shared by every device of the spa.
APPEARANCE_MODES: Final = ("auto", "light", "dark")
DEFAULT_APPEARANCE: Final = "auto"

STORAGE_KEY: Final = "spa_booking.json"
STORAGE_VERSION: Final = 1

KEY_CATEGORIES: Final = "categories"
KEY_TREATMENTS: Final = "treatments"
KEY_OPERATORS: Final = "operators"
KEY_CLIENTS: Final = "clients"
KEY_APPOINTMENTS: Final = "appointments"
KEY_SETTINGS: Final = "settings"
#: Time windows in which an operator refused to work. A new booking skips
#: every operator holding an overlapping block, until she taps "available
#: again" and the block is removed.
KEY_SLOT_BLOCKS: Final = "slot_blocks"

#: Closures decided by the business, as opposed to the refused windows above:
#: a range of days, optionally a time slice, where either the whole facility,
#: one category or one operator is unavailable. A booking landing inside is
#: refused outright, except an operator closure, which only removes her from
#: the offers so a colleague can still take the slot.
KEY_CLOSURES: Final = "closures"

#: Gift vouchers sold at the desk: who bought them, who receives them, which
#: treatments each person can take, and when they expire.
KEY_VOUCHERS: Final = "vouchers"
VOUCHER_ACTIVE: Final = "active"
VOUCHER_REDEEMED: Final = "redeemed"
#: Validity of a new voucher, counted in months from the day it is sold.
VOUCHER_VALID_MONTHS: Final = 6

#: Loyalty vouchers ("Voucher fedelta"): personal codes the thank-you message
#: hands to a client after she used the services. Kept in their own list, apart
#: from the sold gift vouchers, because they carry a percentage discount on a
#: spend range instead of named treatments.
KEY_PROMO_VOUCHERS: Final = "promo_vouchers"
#: Created at check-out, waiting for its message to be sent.
PROMO_VOUCHER_PENDING: Final = "pending"
#: The thank-you message has gone out; the code is usable until it expires.
PROMO_VOUCHER_SENT: Final = "sent"
#: The code was used (on a booking or by hand); it stays in the list.
PROMO_VOUCHER_REDEEMED: Final = "redeemed"

#: Appointment requests taken by the desk: a guest asking for a slot, by phone
#: or on WhatsApp. They are their own record, not appointments: a request holds
#: no slot and never shows up in the agenda. Confirming it in the Richieste tab
#: is what turns it into real appointments.
KEY_REQUESTS: Final = "requests"
#: Waiting for the desk to confirm it, then confirmed (its appointments exist).
REQUEST_PENDING: Final = "pending"
REQUEST_CONFIRMED: Final = "confirmed"

#: Where a request came from. ``REQUEST_SOURCE_DESK`` is the reception writing
#: it down (or the WhatsApp/Telegram flows); ``REQUEST_SOURCE_WEB`` is the
#: guest herself, on the hotel website. Only a web request lights the bell in
#: the card header: it is the one the desk did not see being taken.
REQUEST_SOURCE_DESK: Final = "desk"
REQUEST_SOURCE_WEB: Final = "web"
REQUEST_SOURCES: Final = (REQUEST_SOURCE_DESK, REQUEST_SOURCE_WEB)

#: Access level chosen per user in the card's Accessi tab. "none" hides the
#: dashboard, "read" is view only, "operator" handles the day, "manager" also
#: touches clients and messages, "admin" is the full configuration.
PERMISSION_LEVELS: Final = ("none", "read", "operator", "manager", "admin")

KEY_PERMISSIONS: Final = "permissions"

ATTR_USER_ID: Final = "user_id"
ATTR_LEVEL: Final = "level"

#: What a closure applies to.
CLOSURE_SCOPES: Final = ("facility", "operator", "category")

#: Upper bound on how many days one closure may span, so a mistyped end date
#: cannot turn a booking check into an unbounded loop.
MAX_CLOSURE_DAYS: Final = 366

#: Default address of the WAHA add-on inside Home Assistant OS, and the session
#: it serves. Both stay editable from the card, so an add-on installed on
#: another host needs no code change.
DEFAULT_WAHA_URL: Final = "http://homeassistant:3000"
DEFAULT_WAHA_SESSION: Final = "default"

#: Public booking API, used by the hotel website. The site is a separate
#: origin, so it cannot reach the authenticated Lovelace websocket: it calls
#: the three HTTP views of ``public.py`` instead, each guarded by the token
#: below. The window is the day as the website offers it — it says nothing
#: about when the spa really opens, which is the reception's business.
WEB_API_BASE: Final = "/api/spa_booking/public"
#: Token the website must send in ``Authorization: Bearer …``. Generated on
#: first use and rotatable from the card; an empty setting means "generate one
#: when the site is switched on".
DEFAULT_WEB_TOKEN: Final = ""
#: The website is off until the reception turns it on: nobody can call the
#: public views while this is false.
DEFAULT_WEB_ENABLED: Final = False
#: Hours the website offers, and the step between one proposed start and the
#: next. All editable from the card, because the spa's season and the desk's
#: habits change.
DEFAULT_WEB_OPEN_TIME: Final = "09:00"
DEFAULT_WEB_CLOSE_TIME: Final = "20:00"
#: The break that splits the offered day in two (lunch): the morning runs
#: from the opening to this clock and the afternoon from ``..._END`` to the
#: closing one. Both empty — the default — mean one single window, exactly
#: the day the site offered before the break existed.
DEFAULT_WEB_BREAK_START: Final = ""
DEFAULT_WEB_BREAK_END: Final = ""
DEFAULT_WEB_STEP_MIN: Final = 30
#: How many days ahead the website may offer, and how many start times one
#: day+request may return — the second is a guard, not a setting: a busy day
#: must never turn into an unbounded answer.
DEFAULT_WEB_MAX_DAYS_AHEAD: Final = 60
WEB_MAX_SLOTS: Final = 96
#: Numero WhatsApp della reception che riceve l'avviso quando un ospite invia
#: una richiesta dal sito. Vuoto — il default — significa nessun avviso: la
#: richiesta arriva comunque in Nuovo › Lista richieste.
DEFAULT_WEB_NOTIFY_WHATSAPP: Final = ""
#: Segnaposto del token nello snippet da incollare nella pagina del sito: la
#: card lo sostituisce al volo col token corrente, senza mai scriverlo su disco.
WEB_SNIPPET_TOKEN_PLACEHOLDER: Final = "INCOLLA_QUI_IL_TOKEN"
#: Titolo che la card mostra in testata. Vuoto — il default — significa usare
#: il valore della configurazione della card, e se quello manca "Gestione SPA".
DEFAULT_CARD_TITLE: Final = ""

#: Chat Telegram già autorizzate per il bot "Hotel Il Marchese": il report
#: mensile parte verso tutte e tre finché non vengono cambiate dalla card.
DEFAULT_TELEGRAM_ENTRY_ID: Final = "01JZ6G7TT8APQ8WCXEPRCDNQFN"
DEFAULT_REPORT_TELEGRAM_CHATS: Final = "933728087, 5400097873, 8144958044"
DEFAULT_REPORT_TIME: Final = "08:00"

#: Durations offered when seeding the first dataset.
DEFAULT_DURATIONS: Final = (90, 120)

STATUS_CONFIRMED: Final = "confirmed"
STATUS_CANCELLED: Final = "cancelled"
#: A booking taken at the desk and not yet confirmed. It occupies its slot like
#: a confirmed one — the room and the operator are held — but it says so, and
#: the payment or one press turns it into STATUS_CONFIRMED.
STATUS_PENDING: Final = "pending"

#: The statuses that hold a slot. Everything that asks "is this place taken?"
#: counts a pending booking, or two clients would be let into the same hour.
#: What is merely reporting — the agenda, the calendar — lists them and marks
#: them instead of hiding them.
BOOKING_STATUSES: Final = (STATUS_CONFIRMED, STATUS_PENDING)

#: Offer lifecycle of an appointment that needs an operator. ``OFFER_NONE``
#: is stored as an empty string: treatments that need nobody (spa entry) and
#: already confirmed bookings have nothing outstanding.
OFFER_NONE: Final = ""
OFFER_PENDING: Final = "offered"
OFFER_UNASSIGNED: Final = "unassigned"

#: The three answers an operator can give, whatever the channel is.
ANSWER_CONFIRM: Final = "confirm"
ANSWER_DECLINE: Final = "decline"
ANSWER_AVAILABLE: Final = "available_again"

#: How long an offer waits for an answer before the next candidate is asked,
#: and how long before that a reminder is sent (0 disables the reminder).
#: Both live in settings, so the reception can change them from the card.
DEFAULT_OFFER_TIMEOUT_HOURS: Final = 24
DEFAULT_OFFER_REMINDER_HOURS: Final = 2

#: Hours after an appointment ends before the guest is asked for a review, and
#: how long that request stays eligible. The window is the safety net: it
#: covers a restart or a long outage, but an old visit is never asked all of a
#: sudden just because the integration came back up days later.
REVIEW_REQUEST_AFTER_HOURS: Final = 6
REVIEW_REQUEST_WINDOW_HOURS: Final = 24

#: Whether the automatic review request is on by default, and how many hours
#: after a treatment ends it goes out. Both are settings the reception can
#: change from the notifications tab; the constants are only the starting point.
DEFAULT_REVIEW_REQUEST_AUTO: Final = True
DEFAULT_REVIEW_REQUEST_AFTER_HOURS: Final = REVIEW_REQUEST_AFTER_HOURS

#: Bank details the deposit request reads out to the guest. Editable from the
#: notifications tab. Empty values fall back to the hotel's defaults.
DEFAULT_DEPOSIT_INTESTATARIO: Final = "IL MARCHESE SOC COOP ARL"
DEFAULT_DEPOSIT_IBAN: Final = "IT92Q0326882970052705511040"

#: The default deposit request message. Placeholders: {nome}, {importo},
#: {intestatario}, {iban}, {codice}. Editable from the notifications tab.
DEFAULT_DEPOSIT_MESSAGE: Final = "\n".join(
    [
        "Gentile {nome}, la Sua prenotazione è stata registrata 📋",
        "È in attesa di conferma: per bloccare il Suo posto Le chiediamo un "
        "acconto di € {importo} tramite bonifico bancario istantaneo.",
        "",
        "Intestatario: {intestatario}",
        "IBAN: {iban}",
        "CAUSALE: NOME E COGNOME {codice}",
        "",
        "Non appena riceveremo il bonifico Le confermeremo l'appuntamento. "
        "Grazie!",
    ]
)

#: The headline shown after the title of the guest-facing appointment summary
#: (the "RIEPILOGO APPUNTAMENTO" the guest receives on WhatsApp). Editable from
#: the notifications tab.
DEFAULT_GUEST_HEADER: Final = "Il Marchese Hotel & Spa"

#: The default promotional message. Placeholders: {nome}, {cognome}, {codice}.
#: Editable from the Promo tab.
DEFAULT_PROMO_MESSAGE: Final = "\n".join(
    [
        "Gentile {nome}, dal Il Marchese Hotel & Spa 🧖‍♀️✨",
        "",
        "Le dedichiamo un'offerta speciale per il Suo prossimo trattamento "
        "benessere: contattarci per scoprire i dettagli.",
        "",
        "Il Suo codice prenotazione: {codice}",
        "",
        "Ti aspettiamo!",
        "Lo Staff - Il Marchese Hotel & Spa",
        "📞 +39 0925 992446",
    ]
)

#: Default pause (seconds) between one WhatsApp send and the next, so the WAHA
#: add-on is never flooded when broadcasting to many clients.
DEFAULT_PROMO_INTERVAL_SEC: Final = 3

#: Default daily time the automatic promo broadcast fires (empty = disabled).
DEFAULT_PROMO_TIME: Final = ""

#: The message asking a guest for a review. ``{nome}`` is replaced with her first
#: name, or with "ospite" when the client card has none. It lives here because
#: it is also the starting point the card shows in the notifications tab: the
#: reception edits a copy of it there and the setting takes over from this.
DEFAULT_REVIEW_MESSAGE: Final = "\n".join(
    [
        "Gentile {nome}, è stato un piacere averla con noi a Il Marchese "
        "Hotel & Spa! 🧖‍♀️✨",
        "",
        "Speriamo che i trattamenti Le abbiano regalato il relax che cercava.",
        "Se le fa piacere, un minuto per raccontare la sua esperienza?",
        "",
        "📍 Google : https://g.page/r/CYio3KzgDS_9EAE/review",
        "📍 TripAdvisor : https://www.tripadvisor.it/UserReviewEdit-"
        "g580230-d7066961-Hotel_Il_Marchese_Spa-Sciacca_Province_of_Agrigento_Sicily.html",
        "",
        "Un caro saluto,",
        "Lo Staff - Il Marchese Hotel & Spa",
        "📞 +39 0925 992446",
    ]
)

#: Bank details the deposit request message reads out to the guest. Both live
#: in settings, so the reception can change them from the card without touching
#: code. The defaults match the hotel's current transfer coordinates.
DEFAULT_DEPOSIT_INTESTATARIO: Final = "IL MARCHESE SOC COOP ARL"
DEFAULT_DEPOSIT_IBAN: Final = "IT92Q0326882970052705511040"

#: The headline shown after the title of the guest-facing appointment summary
#: (the "RIEPILOGO APPUNTAMENTO" the guest receives on WhatsApp). Editable from
#: the notifications tab.
DEFAULT_GUEST_HEADER: Final = "Il Marchese Hotel & Spa"

#: The message a guest receives when the desk takes her appointment request:
#: it says the request was received and is waiting for confirmation. It is the
#: starting point the card shows in the notifications tab, where the reception
#: edits a copy and the setting takes over from this. Placeholders: {nome},
#: {cognome}, {data}, {ora}, {persone}, {trattamenti}, {codice}.
DEFAULT_REQUEST_MESSAGE: Final = "\n".join(
    [
        "Gentile {nome}, abbiamo ricevuto la Sua richiesta 🧖‍♀️✨",
        "Data: {data}",
        "Persone: {persone}",
        "Trattamenti: {trattamenti}",
        "",
        "La richiesta è in attesa di conferma: La contatteremo al più presto.",
        "Riferimento: {codice}",
    ]
)

#: The default appointment reminder message sent to the guest before her appointment.
#: ``{nome}`` first name, ``{cognome}`` last name, ``{codice}`` booking reference,
#: ``{data}`` date (dd/mm/yyyy), ``{ora}`` start time, ``{trattamenti}`` treatment list.
DEFAULT_APPOINTMENT_REMINDER_MESSAGE: Final = "\n".join(
    [
        "Gentile {nome}, le ricordiamo il Suo appuntamento 🧖‍♀️✨",
        "",
        "Data: {data}",
        "Ora: {ora}",
        "Trattamenti: {trattamenti}",
        "Codice: {codice}",
        "",
        "Ti aspettiamo!",
        "Lo Staff - Il Marchese Hotel & Spa",
        "📞 +39 0925 992446",
    ]
)

DEFAULT_APPOINTMENT_REMINDER_AUTO: Final = True
DEFAULT_APPOINTMENT_REMINDER_HOURS: Final = 24

DEFAULT_REQUEST_MESSAGE: Final = "\n".join(
    [
        "Gentile {nome}, abbiamo ricevuto la Sua richiesta 🧖‍♀️✨",
        "Data: {data}",
        "Persone: {persone}",
        "Trattamenti: {trattamenti}",
        "",
        "La richiesta è in attesa di conferma: La contatteremo al più presto.",
        "Riferimento: {codice}",
    ]
)

#: The message sent to a voucher recipient 60 days before the voucher expires.
#: Placeholders: {nome} recipient first name, {cognome} last name,
#: {data_scadenza} expiry date (dd/mm/yyyy), {codice} voucher code,
#: {valore} gift card amount if any, {trattamenti} treatments list.
#: Editable from the Notifiche tab.
DEFAULT_VOUCHER_EXPIRY_REMINDER_MESSAGE: Final = "\n".join(
    [
        "Gentile {nome}, il Suo voucher sta per scadere 🎁",
        "",
        "Il voucher {codice} scadrà il {data_scadenza}.",
        "Non perdere l'occasione di usarlo per i Suoi trattamenti benessere!",
        "",
        "Lo Staff - Il Marchese Hotel & Spa",
        "📞 +39 0925 992446",
    ]
)

#: How many days before expiry to send the reminder (default 60).
DEFAULT_VOUCHER_EXPIRY_REMINDER_DAYS: Final = 60

#: The thank-you message a client receives after using the services, carrying a
#: personal loyalty voucher code (the "Voucher fedelta" list). It is a template
#: the reception edits from the Promo tab. Placeholders: {nome}, {cognome},
#: {codice}, {sconto} (percent), {spesa_minima}, {scadenza} (dd/mm/yyyy).
DEFAULT_PROMO_VOUCHER_MESSAGE: Final = "\n".join(
    [
        "Grazie {nome} {cognome} per essere stata nostra ospite! 🧖‍♀️✨",
        "",
        "Per ringraziarLa, Le abbiamo riservato un voucher fedeltà:",
        "🎟️ Codice: {codice}",
        "🎁 Sconto: {sconto}% sul Suo prossimo trattamento",
        "💶 Spesa minima: {spesa_minima}",
        "📅 Da usare entro il: {scadenza}",
        "",
        "Ti aspettiamo per nuovi momenti di relax!",
        "Lo Staff - Il Marchese Hotel & Spa",
        "📞 +39 0925 992446",
    ]
)

#: How long a loyalty voucher stays valid, in days, before it is auto-deleted
#: when it was never used (default 30).
DEFAULT_PROMO_VOUCHER_DAYS: Final = 30

#: The percentage discount the loyalty voucher grants (default 10).
DEFAULT_PROMO_VOUCHER_DISCOUNT: Final = 10

#: The minimum and maximum spend the loyalty voucher applies to, in euros.
DEFAULT_PROMO_VOUCHER_MIN_SPEND: Final = 100
DEFAULT_PROMO_VOUCHER_MAX_SPEND: Final = 500

#: How many hours after the check-out the thank-you message is sent (default 24).
DEFAULT_PROMO_VOUCHER_AFTER_HOURS: Final = 24

#: Whether the loyalty voucher is created and sent automatically on check-out.
DEFAULT_PROMO_VOUCHER_AUTO: Final = False

#: The number of days an unused loyalty voucher is kept in storage after its
#: code was generated, computed from the "created_at" date, before auto-deletion.
PROMO_VOUCHER_CODE_PREFIX: Final = "FID-"

#: The message asking a guest to pay her deposit by bank transfer. ``{nome}``
#: becomes the client's first name, ``{importo}`` the amount, ``{intestatario}``
#: and ``{iban}`` the bank details, ``{codice}`` the booking reference. It lives
#: here as the starting point the card shows in the notifications tab.
DEFAULT_DEPOSIT_MESSAGE: Final = "\n".join(
    [
        "Gentile {nome}, la Sua prenotazione è stata registrata 📋",
        "È in attesa di conferma: per bloccare il Suo posto Le chiediamo un "
        "acconto di € {importo} tramite bonifico bancario istantaneo.",
        "",
        "Intestatario: {intestatario}",
        "IBAN: {iban}",
        "CAUSALE: NOME E COGNOME {codice}",
        "",
        "Non appena riceveremo il bonifico Le confermeremo l'appuntamento. "
        "Grazie!",
    ]
)

DEFAULT_PROMO_MESSAGE: Final = "\n".join(
    [
        "Gentile {nome}, dal Il Marchese Hotel & Spa ",
        "",
        "Le dedichiamo un'offerta speciale per il Suo prossimo trattamento "
        "benessere: contattarci per scoprire i dettagli.",
        "",
        "Il Suo codice prenotazione: {codice}",
        "",
        "Ti aspettiamo!",
        "Lo Staff - Il Marchese Hotel & Spa",
        " +39 0925 992446",
    ]
)

DEFAULT_PROMO_INTERVAL_SEC: Final = 3

DEFAULT_PROMO_TIME: Final = ""

#: The guest-facing appointment summary, the message sent when a booking is
#: confirmed. A template the reception edits from the notifications tab, so it
#: is also the starting point the card shows there. Placeholders: {nome},
#: {cognome}, {cliente}, {hotel} (the headline), {codice}, {trattamento},
#: {durata}, {data}, {ora}, {fine}, {totale}, {acconto}, {versato}, {residuo}
#: and {pagamenti} (one line per registered taking).
DEFAULT_SUMMARY_MESSAGE: Final = "\n".join(
    [
        "RIEPILOGO APPUNTAMENTO",
        "",
        "{hotel}",
        "",
        "Codice: {codice}",
        "Cliente: {cliente}",
        "Trattamento: {trattamento} ({durata} min)",
        "Quando: {data} dalle {ora} alle {fine}",
        "",
        "Acconto: {acconto}",
        "Versato: {versato}",
        "Da saldare: {residuo}",
        "",
        "Versamenti:",
        "{pagamenti}",
    ]
)

#: Accepted WhatsApp spellings. A confirm phrase is unambiguous and accepted
#: at any length; everything else only counts when the reply is short enough
#: to actually be an answer, so "Arrivo tra 5 minuti, no?" is not a refusal.
#: Reactions are matched on the emoji alone, because they carry no text.
ANSWER_PHRASES_CONFIRM: Final = ("confermo", "va bene", "accetto")
ANSWER_MAX_WORDS: Final = 5
ANSWER_WORDS_CONFIRM: Final = ("si", "sì", "ok", "oky", "okay", "certo")
ANSWER_WORDS_DECLINE: Final = ("non", "no")
ANSWER_WORDS_AVAILABLE: Final = ("disponibile", "libera", "libero", "torno", "rientro")
ANSWER_EMOJI_CONFIRM: Final = ("✅", "✔️", "👍")
ANSWER_EMOJI_DECLINE: Final = ("❌", "🚫", "👎")
ANSWER_EMOJI_AVAILABLE: Final = ("🔄", "🔁", "♻️")

ATTR_APPOINTMENT_ID: Final = "appointment_id"
ATTR_CLIENT_ID: Final = "client_id"
ATTR_OPERATOR_ID: Final = "operator_id"
ATTR_TREATMENT_ID: Final = "treatment_id"
ATTR_CATEGORY_ID: Final = "category_id"
ATTR_REASON: Final = "reason"
ATTR_DATE: Final = "date"
ATTR_QUERY: Final = "query"
ATTR_LIMIT: Final = "limit"
ATTR_PAYLOAD: Final = "payload"
ATTR_MONTH: Final = "month"
ATTR_NOTIFY: Final = "notify"
ATTR_RESPONSE: Final = "response"
ATTR_ROWS: Final = "rows"
ATTR_OPERATOR_IDS: Final = "operator_ids"
ATTR_BLOCK_ID: Final = "block_id"
ATTR_ANSWER: Final = "answer"
ATTR_CHAT_ID: Final = "chat_id"
ATTR_CHANNEL: Final = "channel"
ATTR_CONFIG_ENTRY_ID: Final = "config_entry_id"
ATTR_SOURCE: Final = "source"
ATTR_PAYMENT: Final = "payment"
ATTR_GUEST_TYPE: Final = "guest_type"
ATTR_EXTRAS: Final = "extras"
ATTR_STATE: Final = "state"
ATTR_KIND: Final = "kind"
ATTR_CHECKED_IN: Final = "checked_in"
ATTR_FORCE_NEW: Final = "force_new"
ATTR_APPOINTMENT_IDS: Final = "appointment_ids"
ATTR_REQUEST_ID: Final = "request_id"
ATTR_PEOPLE: Final = "people"
ATTR_ENTRIES: Final = "entries"
ATTR_METHOD: Final = "method"
ATTR_AMOUNT: Final = "amount"
ATTR_PAYMENT_ID: Final = "payment_id"
ATTR_TIME: Final = "time"

#: The ways an appointment can be paid, with the label and the icon the card
#: shows for each. Declared here so the service schema and the coordinator read
#: the same list: they have to agree, and this is the one place they can.
PAYMENT_METHODS: Final = (
    ("card", "Carta di credito", "mdi:credit-card-outline"),
    ("cash", "Contante", "mdi:cash"),
    ("bank_transfer", "Bonifico", "mdi:bank-transfer-in"),
    ("gift_card", "Gift card", "mdi:gift-outline"),
    ("voucher", "Voucher", "mdi:ticket-confirmation-outline"),
)

#: The two kinds of staff the spa desk works with, as (id, label, icon).
#:
#: This classifies, it does not restrict: an operator of either kind stays
#: assignable to every treatment and stays notified exactly as before, so the
#: role can never make an appointment impossible to book. Declared here so the
#: service schema, the coordinator and the card read one list and cannot drift.
OPERATOR_ROLES: Final = (
    ("massaggiatore", "Massaggiatore", "mdi:hand-heart"),
    ("spa_manager", "Spa Manager", "mdi:account-tie-outline"),
)

#: The default when an operator has no role: they give massages, which is what
#: every operator was before the role existed.
OPERATOR_ROLE_DEFAULT: Final = OPERATOR_ROLES[0][0]

#: Whether the guest stays at the hotel or came from outside, as (id, label,
#: icon). Declared here so the service schema, the coordinator and the card
#: read one list and cannot drift.
GUEST_TYPES: Final = (
    ("hotel", "Ospite dell'hotel", "mdi:hotel"),
    ("external", "Esterno", "mdi:account-outline"),
)

#: The default for an appointment that was never flagged: a booking without a
#: flag is from outside, which is what every appointment was before the field
#: existed.
GUEST_TYPE_DEFAULT: Final = "external"

#: The accessories a guest can have with the booking, as (id, label, icon).
#: Declared here so the service schema, the coordinator and the card read one
#: list and cannot drift. Chosen per person, so each entry of a booking row
#: carries its own ``extras``.
EXTRAS: Final = (
    ("wellness_kit", "Wellness Kit", "mdi:gift-outline"),
    ("accappatoio", "Accappatoio", "mdi:tshirt-crew-outline"),
    ("cuffia", "Cuffia", "mdi:shower-head"),
    ("ciabattine", "Ciabattine", "mdi:shoe-formal"),
)

#: Valid accessory ids, for ``vol.In``.
EXTRAS_NAMES: Final = tuple(name for name, _, _ in EXTRAS)

#: The accessories the Accessori tab starts from, before the reception edits
#: them: the same id, label and icon as ``EXTRAS``, plus the price and the
#: description that tab adds. Built from ``EXTRAS`` so the two cannot drift.
ACCESSORY_DEFAULTS: Final = tuple(
    {
        "id": item_id,
        "label": label,
        "icon": icon,
        "price": None,
        "description": "",
    }
    for item_id, label, icon in EXTRAS
)

#: A booking with no accessory chosen: an empty set, the same meaning as
#: every appointment that predates the field.
EXTRAS_DEFAULT: Final = ()

EVENT_APPOINTMENT_CREATED: Final = f"{DOMAIN}_appointment_created"
EVENT_APPOINTMENT_CANCELLED: Final = f"{DOMAIN}_appointment_cancelled"
EVENT_OFFER_ANSWERED: Final = f"{DOMAIN}_offer_answered"
#: Fired by the automations in packages/spa_booking.yaml so the coordinator
#: can read an inbound WhatsApp message or a Telegram button press.
EVENT_ANSWER_REQUEST: Final = f"{DOMAIN}_answer_request"
#: Fired when a WhatsApp message arrives from a number that is not a client
#: or an operator, so the desk can read and answer the request.
EVENT_EXTERNAL_MESSAGE: Final = f"{DOMAIN}_external_message"
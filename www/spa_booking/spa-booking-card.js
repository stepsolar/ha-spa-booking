/**
 * SPA Booking - Lovelace card.
 *
 * Single tabbed card for managing SPA appointments:
 *   Agenda       day agenda grouped by operator, with cancel actions
 *   Nuovo        cascading booking form (treatment -> operator -> date/time -> client)
 *   Calendario   month view with per-day counts
 *   Clienti      client search, card editing and history
 *   Telecamere   live feeds of the configured cameras
 *   Configurazione  categories, treatments and operators (admin only)
 *
 * The whole dataset is fetched once with `spa_booking.export_data` and then
 * filtered client side, so navigation between tabs is instant. Every mutation
 * goes through the integration services, which own all business rules.
 *
 * Registered as a Lovelace module by the spa_booking integration itself
 * (add_extra_js_url), so there is no manual resource to add.
 */

const DOMAIN = "spa_booking";
const CARD_VERSION = "2.0.10";

// Window of the "Uscite" panel at the top of the agenda: it opens this many
// minutes before an appointment ends and lingers this many minutes after,
// so the reception can confirm the exit while it happens or a little late.
const EXIT_LEAD_MIN = 15;
const EXIT_GRACE_MIN = 30;

// Accepted values of the `appearance` setting. "auto" keeps the card on the
// Home Assistant theme; the other two force it, whatever the global theme is.
const APPEARANCE_MODES = ["auto", "light", "dark"];
const APPEARANCE_LABELS = {
  auto: "Segui Home Assistant",
  light: "Chiaro",
  dark: "Scuro",
};

const GIORNI = ["Lun", "Mar", "Mer", "Gio", "Ven", "Sab", "Dom"];
const GIORNI_LONGHI = [
  "Lunedì",
  "Martedì",
  "Mercoledì",
  "Giovedì",
  "Venerdì",
  "Sabato",
  "Domenica",
];
/**
 * The ways of paying, in the order they are offered.
 *
 * Declared here, once: the checkbox in the form and the chip in the agenda read
 * the same name and the same icon from this list, so the two can never spell
 * one thing and draw another.
 */
const PAYMENT_METHODS = [
  { id: "card", label: "Carta di credito", icon: "mdi:credit-card-outline" },
  { id: "cash", label: "Contante", icon: "mdi:cash" },
  { id: "bank_transfer", label: "Bonifico", icon: "mdi:bank-transfer-in" },
  { id: "gift_card", label: "Gift card", icon: "mdi:gift-outline" },
  { id: "voucher", label: "Voucher", icon: "mdi:ticket-confirmation-outline" },
];

// The two kinds of staff, mirroring OPERATOR_ROLES in the integration's
// const.py. It labels, it does not gate: an operator of either kind stays
// assignable to every treatment and stays notified as before. The first entry
// is the fallback for an operator saved before roles existed.
const OPERATOR_ROLES = [
  { id: "massaggiatore", label: "Massaggiatore", icon: "mdi:hand-heart" },
  { id: "spa_manager", label: "Spa Manager", icon: "mdi:account-tie-outline" },
];

const roleOf = (operator) =>
  OPERATOR_ROLES.find((role) => role.id === (operator && operator.role)) ||
  OPERATOR_ROLES[0];

// Whether the guest stays at the hotel or came from outside, mirroring
// GUEST_TYPES in the integration's const.py. It labels the booking for the
// agenda and its filters; no business rule uses it. The second entry is the
// fallback for an appointment flagged before the field existed.
const GUEST_TYPES = [
  { id: "hotel", label: "Ospite dell'hotel", icon: "mdi:alpha-h-box" },
  { id: "external", label: "Esterno", icon: "mdi:account-outline" },
];
const GUEST_DEFAULT = "external";

// The accessories a booking can carry are configured in the Accessori tab of
// Configurazione and read from settings.accessories. This is only what the
// card falls back to before the settings have loaded (and while the key has
// never been saved), so the booking form is never left without accessories.
const ACC_FALLBACK = [
  { id: "wellness_kit", label: "Wellness Kit", icon: "mdi:gift-outline", price: null, description: "" },
  { id: "accappatoio", label: "Accappatoio", icon: "mdi:tshirt-crew-outline", price: null, description: "" },
  { id: "cuffia", label: "Cuffia", icon: "mdi:shower-head", price: null, description: "" },
  { id: "ciabattine", label: "Ciabattine", icon: "mdi:shoe-formal", price: null, description: "" },
];

// Drawn when an accessory has no icon of its own, and for one that has since
// been deleted from the configuration.
const ACC_DEFAULT_ICON = "mdi:gift-outline";

// Distinct colours handed to the day's groups in order of appearance, so two
// groups of the same day never share a vertical bar. The last one wraps
// around when a day has more groups than colours.
const GROUP_COLORS = [
  "#5c6bc0",
  "#26a69a",
  "#ef5350",
  "#ffa726",
  "#ab47bc",
  "#66bb6a",
  "#ec407a",
];

const MESI = [
  "Gennaio",
  "Febbraio",
  "Marzo",
  "Aprile",
  "Maggio",
  "Giugno",
  "Luglio",
  "Agosto",
  "Settembre",
  "Ottobre",
  "Novembre",
  "Dicembre",
];

// The report page for a single day, opened in its own tab where it is the
// only content: the styles are self-contained so that the page prints (or is
// saved) as PDF exactly as it reads.
const REPORT_CSS = `
* { box-sizing: border-box; }
body { margin: 0; font-family: var(--mdc-typography-font-family, Roboto, Arial, sans-serif);
       color: #1d1d1d; }
.report-page { max-width: 210mm; margin: 0 auto; padding: 14px 18px; }
.report-page h1 { font-size: 20px; margin: 0 0 2px; }
.report-date { font-size: 14px; color: #444; margin-bottom: 8px; }
.report-summary { font-size: 12px; color: #444; margin-bottom: 10px; }
.report-section { font-size: 13px; margin: 14px 0 4px; border-top: 1px solid #999; padding-top: 8px; }
.report-row { display: flex; gap: 10px; padding: 5px 0; border-bottom: 1px solid #e0e0e0;
              page-break-inside: avoid; align-items: baseline; font-size: 12.5px; }
.report-row.report-head { font-weight: 700; font-size: 10.5px; text-transform: uppercase;
                          color: #666; border-bottom: 2px solid #999; }
.report-row.exited { opacity: .55; }
.r-time { width: 52px; flex: 0 0 auto; font-variant-numeric: tabular-nums; font-weight: 600; }
.r-client { flex: 1.2 1 130px; min-width: 0; }
.r-guest { display: block; font-size: 10.5px; color: #666; }
.r-treat { flex: 1.4 1 150px; min-width: 0; }
.r-persons { flex: 0 0 auto; width: 56px; text-align: center; font-variant-numeric: tabular-nums; }
.r-extras { font-size: 10.5px; color: #555; }
.r-op { flex: 1 1 100px; min-width: 0; }
.r-pay { flex: 1.2 1 120px; min-width: 0; }
.r-status { flex: 0 0 auto; width: 108px; }
.r-status.pending { color: #b26a00; }
.r-status.warn { color: #b00020; }
.r-cat { flex: 0 0 auto; width: 92px; color: #555; }
.r-code { flex: 0 0 auto; width: 72px; font-weight: 600; font-variant-numeric: tabular-nums;
          letter-spacing: 0.5px; color: #333; }
.r-dur { flex: 0 0 auto; width: 64px; text-align: right; font-variant-numeric: tabular-nums; }
.r-note { font-size: 12px; color: #666; margin-top: 6px; }
@media print {
  body { margin: 0; }
  .report-page { padding: 0; }
}
`;

const TABS = [
  { id: "agenda", label: "Agenda", icon: "mdi:clipboard-text-clock-outline" },
  { id: "nuovo", label: "Nuovo", icon: "mdi:calendar-plus" },
  { id: "spa", label: "Spa", icon: "mdi:spa" },
  { id: "clienti", label: "Clienti", icon: "mdi:account-group" },
  { id: "voucher", label: "Voucher", icon: "mdi:ticket-percent-outline" },
  { id: "whatsapp", label: "WhatsApp", icon: "mdi:whatsapp" },
  { id: "config", label: "Configurazione", icon: "mdi:cog" },
];

// Sub-tabs of the Nuovo tab: the appointment form and the requests (form and
// list), which used to live in their own top-level tab.
const NUOVO_TABS = [
  { id: "appuntamento", label: "Appuntamento", icon: "mdi:calendar-plus" },
  { id: "nuova", label: "Nuova richiesta", icon: "mdi:plus-circle-outline" },
  { id: "lista", label: "Lista richieste", icon: "mdi:clipboard-check-outline" },
];

// Block IDs for the Richiesta form sections (for drag-and-drop reordering).
const RICHIESTA_BLOCKS = [
  { id: "persone", label: "Persone", icon: "mdi:account-group" },
  { id: "trattamenti", label: "Trattamenti", icon: "mdi:spa-outline" },
  { id: "accessori", label: "Accessori", icon: "mdi:gift-outline" },
  { id: "ospite", label: "Ospite", icon: "mdi:account-badge" },
  { id: "cliente", label: "Cliente", icon: "mdi:account" },
  { id: "note", label: "Note", icon: "mdi:note-text-outline" },
];

// Sub-tabs of the Agenda tab. The month calendar moved to the agenda bar
// as a toggle button (left of "Oggi"). This array is now empty — the bar
// handles the view switch directly.
const AGENDA_TABS = [];

// Sub-tabs of the Spa tab. The cameras used to be a top-level tab; they now
// live inside Spa, with the very same sub-tab bar the configuration uses
// (a vertical icon strip on a phone).
const SPA_TABS = [
  { id: "controlli", label: "Spa", icon: "mdi:spa" },
  { id: "telecamere", label: "Telecamere", icon: "mdi:cctv" },
];

const CFG_TABS = [
  { id: "categorie", label: "Categorie", icon: "mdi:tag-outline" },
  { id: "trattamenti", label: "Trattamenti", icon: "mdi:spa-outline" },
  { id: "accessori", label: "Accessori", icon: "mdi:gift-outline" },
  { id: "operatori", label: "Operatori", icon: "mdi:account-group-outline" },
  { id: "blocchi", label: "Fasce bloccate", icon: "mdi:lock-outline" },
  { id: "notifiche", label: "Notifiche", icon: "mdi:bell-outline" },
  { id: "promo", label: "Promo", icon: "mdi:bullhorn-outline" },
  { id: "accessi", label: "Accessi", icon: "mdi:shield-account-outline" },
  { id: "impostazioni", label: "Impostazioni", icon: "mdi:cog" },
];


// -----------------------------------------------------------------------------
// small helpers
// -----------------------------------------------------------------------------

const pad = (n) => String(n).padStart(2, "0");

const ymd = (date) => `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`;

const todayStr = () => ymd(new Date());

const parseDate = (value) => {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? null : date;
};

const hhmm = (date) => `${pad(date.getHours())}:${pad(date.getMinutes())}`;

const timeOf = (date) => hhmm(date);

// Black or white ink for a coloured background, by its perceived brightness.
const readableInk = (color) => {
  const hex = String(color || "").replace("#", "");
  if (hex.length !== 6) return "";
  const r = parseInt(hex.slice(0, 2), 16);
  const g = parseInt(hex.slice(2, 4), 16);
  const b = parseInt(hex.slice(4, 6), 16);
  if ([r, g, b].some((value) => Number.isNaN(value))) return "";
  const luminance = (0.299 * r + 0.587 * g + 0.114 * b) / 255;
  return luminance > 0.6 ? "#1b1f24" : "#f4f6f8";
};

const addDays = (date, days) => {
  const next = new Date(date.getFullYear(), date.getMonth(), date.getDate());
  next.setDate(next.getDate() + days);
  return next;
};

const addMonths = (date, months) => new Date(date.getFullYear(), date.getMonth() + months, 1);

const startOfDay = (date) => new Date(date.getFullYear(), date.getMonth(), date.getDate());

/** Build a local Date from a "YYYY-MM-DD" and a "HH:MM" pair, with a safe fallback. */
const parseLocal = (day, time) => {
  const [year, month, date] = String(day || "").split("-").map((value) => parseInt(value, 10));
  const [hour, minute] = String(time || "10:00").split(":").map((value) => parseInt(value, 10));
  return new Date(
    year || 1970,
    (month || 1) - 1,
    date || 1,
    hour || 0,
    minute || 0,
    0,
    0
  );
};

const isSameDay = (a, b) =>
  a.getFullYear() === b.getFullYear() &&
  a.getMonth() === b.getMonth() &&
  a.getDate() === b.getDate();

const longDay = (date) => {
  // getDay(): 0 = Sunday. Shift so Monday is the first column.
  const index = (date.getDay() + 6) % 7;
  return `${GIORNI_LONGHI[index]} ${date.getDate()} ${MESI[date.getMonth()]} ${date.getFullYear()}`;
};

const shortDay = (date) => {
  const index = (date.getDay() + 6) % 7;
  return `${GIORNI[index]} ${date.getDate()}/${pad(date.getMonth() + 1)}`;
};

/** dd/mm/yyyy, or an empty string when the date cannot be parsed. */
const shortDate = (value) => {
  const date = value instanceof Date ? value : parseDate(value);
  return date ? `${pad(date.getDate())}/${pad(date.getMonth() + 1)}/${date.getFullYear()}` : "";
};

const minutesLabel = (minutes) => {
  if (minutes === null || minutes === undefined) return "";
  if (minutes < 60) return `${minutes} min`;
  const hours = Math.floor(minutes / 60);
  const rest = minutes % 60;
  return rest ? `${hours}h ${rest}min` : `${hours}h`;
};

/** "1 annullato", "3 annullati": the count and its noun always agree. */
const counted = (count, one, many) => `${count} ${count === 1 ? one : many}`;

const euro = (value) => {
  if (value === null || value === undefined || value === "") return "";
  const number = Number(value);
  if (Number.isNaN(number)) return "";
  return `${number.toFixed(2).replace(".", ",")} €`;
};

const normalizePhone = (phone) => (phone || "").replace(/[^\d]/g, "");

/**
 * Whether a number carries an explicit international prefix.
 *
 * A leading "+" or "00" says which country the number belongs to, so it is
 * used exactly as it is written. Every other number is read as Italian.
 */
const isInternationalPhone = (phone) => {
  const value = String(phone || "").trim();
  return value.startsWith("+") || value.startsWith("00");
};

/** The digits of an international number, country code included. */
const internationalDigits = (phone) => {
  const digits = normalizePhone(phone);
  return digits.startsWith("00") ? digits.slice(2) : digits;
};

/** Build a WhatsApp Web link, defaulting the Italian country code. */
const waLink = (phone) => {
  const value = String(phone || "").trim();
  if (!value) return null;
  if (isInternationalPhone(value)) {
    const full = internationalDigits(value);
    return full ? `https://web.whatsapp.com/send/?phone=${full}` : null;
  }
  let digits = normalizePhone(value);
  if (!digits) return null;
  if (digits.startsWith("0039")) digits = digits.slice(4);
  if (digits.startsWith("39")) digits = digits.slice(2);
  return `https://web.whatsapp.com/send/?phone=39${digits}`;
};

const telHref = (phone) => `tel:+${normalizePhone(phone)}`;

/**
 * Tiny DOM builder. Accepts `el("div", {class: "x"}, child, ...)`.
 * `on` holds event listeners, `html` sets innerHTML.
 */
/**
 * Append children, skipping the ones a builder declined to produce.
 *
 * A builder returns null when there is nothing to show: a treatment with no
 * parallel capacity has no stepper, a day with no closures has no list.
 * `el()` drops those out of its own children, but a direct appendChild does
 * not — and appending null throws in the browser while looking perfectly fine
 * to a test that uses stub nodes.
 */
function add(node, ...children) {
  children
    .flat()
    .filter((child) => child !== null && child !== undefined && child !== false && child === child)
    .forEach((child) => {
      node.appendChild(child instanceof Node ? child : document.createTextNode(String(child)));
    });
  return node;
}

function el(tag, props, ...children) {
  const node = document.createElement(tag);
  if (props) {
    Object.entries(props).forEach(([key, value]) => {
      if (value === null || value === undefined || value === false) return;
      if (key === "on") {
        Object.entries(value).forEach(([event, handler]) => node.addEventListener(event, handler));
        return;
      }
      if (key === "html") {
        node.innerHTML = value;
        return;
      }
      if (key === "value") {
        node.value = value;
        return;
      }
      if (key === "checked" || key === "disabled" || key === "selected") {
        node[key] = Boolean(value);
        return;
      }
      node.setAttribute(key, value);
    });
  }
  children
    .flat()
    .filter((child) => child !== null && child !== undefined && child !== false)
    .forEach((child) => {
      node.appendChild(child instanceof Node ? child : document.createTextNode(String(child)));
    });
  return node;
}

// -----------------------------------------------------------------------------
// card
// -----------------------------------------------------------------------------

class SpaBookingCard extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });

    this._config = {};
    this._hass = null;
    this._loading = false;
    this._ready = false;
    // False until the first load answers: only then are the permissions known,
    // so the card shows a plain loading line and never a flash of "denied".
    this._loadedOnce = false;

    this._data = {
      categories: [],
      treatments: [],
      operators: [],
      clients: [],
      appointments: [],
      vouchers: [],
      promo_vouchers: [],
      requests: [],
      slot_blocks: [],
      closures: [],
      settings: {},
    };
    // `appointment` is what the detail popup looks the row up by, so an id
    // survives a re-render instead of pointing at a stale object.
    this._lookup = {
      category: new Map(),
      treatment: new Map(),
      operator: new Map(),
      client: new Map(),
      appointment: new Map(),
    };
    this._byDay = new Map();
    // One distinct colour per group of the day, handed out in the order the
    // group is first rendered. Reset on every data refresh so a busy day
    // always starts from the first colour.
    this._groupColorMap = new Map();
    this._notifyDraft = null;
    this._closureDraft = null;
    this._report = null;
    // The filters of the report preview: what to include (all bookings or only
    // massages), narrowed by category and treatment, over a day, month or year.
    this._reportFilter = {
      scope: "massages",
      period: "month",
      periodKey: "",
      category_id: "",
      treatment_id: "",
    };

    this._tab = "agenda";
    this._cfgTab = "trattamenti";
    // Agenda tab: the sub-tab bar switches between the day list and the month.
    // Kept apart from _tab, which is the top-level bar.
    this._agendaTab = "agenda";
    // Spa tab: the sub-tab bar switches between the control tiles and the
    // cameras. Kept apart from _tab, which is the top-level bar.
    this._spaTab = "controlli";
    // Nuovo tab: the sub-tab bar switches between the appointment form and the
    // requests (form and list), which used to live in their own top-level tab.
    this._nuovoTab = "appuntamento";
    this._richiestaEditMode = false;
    // Accessi tab: the Home Assistant user list is fetched once and cached,
    // so a re-render never blocks on the network.
    this._users = null;
    this._usersLoading = false;
    this._usersError = "";
    this._day = todayStr();
    this._month = startOfDay(new Date());
    this._message = null;
    // Success messages clear themselves; the timer and the key of the message
    // it belongs to live here so a new message restarts the countdown.
    this._messageTimer = null;
    this._messageTimerKey = null;
    this._busy = false;
    this._busySpa = false;
    // Spa tab: _spaEditMode puts the tab itself into edit mode (⋮ on every
    // tile, drag to reorder — the pencil toggles it straight away, there is no
    // separate Modifica menu). _spaTileDlg is the entity popup currently open,
    // _spaAddDlg the add-entity picker and _spaDrag the tile being dragged.
    // Every edit saves immediately, so there is no working copy.
    this._spaEditMode = false;
    this._spaTileDlg = null;
    this._spaAddDlg = false;
    this._spaBrightnessDlg = null;
    this._spaDrag = null;
    // Telecamere tab: the very same in-place editor, on the camera tiles.
    // Kept apart from the Spa state so the two tabs never share an open popup.
    this._camEditMode = false;
    this._camTileDlg = null;
    this._camAddDlg = false;
    this._camDrag = null;
    // Nuovo appuntamento tab: the edit mode here only reorders the form blocks
    // (drag on the handle, immediate save; blocks can move between columns).
    // No per-block popup, nothing can be added or removed.
    this._formEditMode = false;
    this._formDrag = null;
    // Notifiche (Configurazione → Impostazioni): the same edit mode, its own
    // blocks and its own saved order.
    this._notifyEditMode = false;
    this._notifyDrag = null;
    // Impostazioni tab (Configurazione → Impostazioni): the four boxes move
    // between the two columns and save their own order.
    this._settingsEditMode = false;
    this._settingsDrag = null;
    // Promo broadcast: edit mode reorders the blocks and saves promo_order.
    this._promoEditMode = false;
    this._promoDrag = null;
    this._blockDrag = null;
    // Trattamenti tab: edit mode reorders categories (between columns) and
    // treatments (within each category).
    this._trtEditMode = false;
    // Accessori tab: the same in-place editor as the Spa tiles, on the
    // accessories. _accEditMode reorders them, _accDlg is the popup currently
    // open (an accessory id, or "__new__" for the add form). Every edit saves
    // immediately, so there is no working copy.
    this._accEditMode = false;
    this._accDlg = null;
    this._accDrag = null;
    // Operatori tab: edit mode reorders operators inside each column (sets priority).
    this._opEditMode = false;
    this._opDrag = null;
    // The operator card itself is editable too: the pencil on the card's own
    // header turns the boxes (identity, contacts, priority, notifications,
    // messages, treatments) into draggable blocks, exactly like the booking
    // forms. Only their order can change.
    this._operatorFormMode = false;
    this._operatorDrag = null;

    // booking form state
    this._form = {
      treatment_id: "",
      operator_id: "",
      date: todayStr(),
      time: "10:00",
      client_mode: "new",
      client_id: "",
      client_query: "",
      client_results: null,
      first_name: "",
      last_name: "",
      phone: "",
      email: "",
      client_notes: "",
      notes: "",
      // The treatment rows of the booking: one person can book several
      // treatments the same day, each in its own time slot.
      treatments: [],
      // One payment for the whole booking, so it is written onto every person
      // of the group when the rows go out.
      payment: {
        paid: false, paid_amount: "",
        deposit: false, deposit_amount: "",
        voucher: false, voucher_code: "",
        balance_due: false, balance_due_amount: "",
        methods: [],
      },
      // Taken and left waiting for someone to confirm, instead of confirmed on
      // the spot. Any payment settles it anyway.
      pending: false,
      // Hotel guest or from outside: one of the two is always picked, so a
      // booking is never silently left without a flag.
      guest_type: GUEST_DEFAULT,
      // The accessories this person gets with the booking, a subset of the
      // ones configured in the Accessori tab. The quick single booking keeps
      // them flat; every multi person carries its own set.
      extras: [],
      // Persons first: the booking starts with date and count, then one block
      // per person. people is the requested count; persons is null for the
      // quick single booking (the flat fields above back it) and an array of
      // per-person blocks once the count exceeds one, sent all-or-nothing
      // through create_bookings.
      people: 1,
      persons: null,
    };

    // client tab state
    this._clientQuery = "";
    this._clientSelected = null;
    this._clientEditing = null;
    this._clientCreating = false;
    this._clientDraft = null;

    // agenda view state
    this._categoryFilter = "";
    this._guestFilter = "";
    // Show appointments that already checked in (hidden by default to keep the working day readable).
    this._showCheckedIn = false;

    // config tab state
    this._editing = null;

    // Which appointment the detail popup is showing, if any.
    this._detailId = null;
    // Which detail view the popup is in: 'single' or 'grouped'
    this._detailView = 'single';
    this._batchEditing = false;
    this._batchAnchorId = null;
    this._batchAnchorBatchId = null;
    this._batchRows = [];
    this._batchBusy = false;
    this._batchEditMode = false;
    this._batchFormMode = false;
    // The Escape handler, once connectedCallback has bound it. Declared here so
    // it is null before binding and null again after unbinding, rather than
    // undefined in one case and null in the other.
    this._escapeBound = null;
  }

  static getStubConfig() {
    return { title: "Gestione SPA" };
  }

  setConfig(config) {
    this._config = config || {};
    if (this._ready) this._render();
    // Turning the option on or off in the card editor has to take effect at
    // once, not at the next page load. Called before the card is connected the
    // walk upwards finds nothing and this is simply a no-op.
    this._applyFullscreen();
  }

  connectedCallback() {
    // Live clock in the header: update only the two text nodes on each tick,
    // never a full re-render.
    if (!this._clockTimer) {
      this._clockTimer = setInterval(() => this._tick(), 10000);
      this._tick();
    }
    // Escape closes the detail popup. Listening on the document rather than
    // on the sheet itself, because the key lands wherever the focus is: on a
    // phone there may be no focused element inside the sheet at all.
    if (!this._escapeBound) {
      this._escapeBound = (event) => {
        if (event.key !== "Escape") return;
        if (this._overlapPopup) { this._overlapPopup = null; this._render(); }
        else if (this._payPopup) this._closePayPopup();
        else if (this._detailId) this._closeDetail();
      };
      document.addEventListener("keydown", this._escapeBound);
    }
    // The header lives outside this shadow root, so it can only be touched once
    // the card is in the document and its ancestors are known.
    this._applyFullscreen();
  }

  disconnectedCallback() {
    if (this._clockTimer) {
      clearInterval(this._clockTimer);
      this._clockTimer = null;
    }
    // A listener left behind would close a popup of a card that is no longer
    // on screen, and would keep the whole card alive.
    if (this._escapeBound) {
      document.removeEventListener("keydown", this._escapeBound);
      this._escapeBound = null;
    }
    // Leaving the dashboard must leave its header behind.
    this._setFullscreen(false);
  }

  _tick() {
    const root = this.shadowRoot;
    if (!root) return;
    const time = root.querySelector(".clock-time");
    const date = root.querySelector(".clock-date");
    if (time) time.textContent = this._fmtTime();
    if (date) date.textContent = this._fmtDate();
  }

  _fmtTime() {
    return new Date().toLocaleTimeString("it-IT", {
      hour: "2-digit",
      minute: "2-digit",
    });
  }

  _fmtDate() {
    return new Date().toLocaleDateString("it-IT", {
      weekday: "short",
      day: "numeric",
      month: "short",
    });
  }

  set hass(hass) {
    this._hass = hass;
    if (hass && !this._ready) {
      this._ready = true;
      this._loadData().then(() => {
        // Fire ready event for standalone page loading spinner
        this.dispatchEvent(new CustomEvent("spa-booking-ready", { bubbles: true, composed: true }));
      }).catch(err => {
        console.error('Error loading data:', err);
        // Still fire ready event to hide spinner, but log error
        this.dispatchEvent(new CustomEvent("spa-booking-ready", { bubbles: true, composed: true }));
      });
    }
    // Real-time updates for the Spa tab entities: subscribe through the hass shim so
    // the cards update promptly after a state change (without changing tab).
    if (this._ready && hass && !this._spaStateWatcher) {
      this._spaStateWatcher = true;
      try {
        const ids = this._spaTiles().map((t) => t.entity_id);
        const schedule = () => {
          if (this._tab !== "spa") return;
          if (this._spaTileDlg || this._detailId || this._spaAddDlg) return;
          if (!this._spaRenderTimer) {
            this._spaRenderTimer = setTimeout(() => {
              this._spaRenderTimer = null;
              this._render();
            }, 250);
          }
        };
        if (hass.connection && typeof hass.connection.subscribeEntities === "function") {
          hass.connection.subscribeEntities(ids, () => schedule());
        } else if (typeof hass.subscribeEntities === "function") {
          hass.subscribeEntities(ids, () => schedule());
        }
      } catch (err) {
        console.warn("subscribeEntities failed", err);
      }
    }
  }

  getCardSize() {
    return 12;
  }

  // ---------------------------------------------------------------- loading

  async _loadData() {
    if (!this._hass) return;
    this._loading = true;
    this._render();
    try {
      const response = await this._service("export_data");
      const data = (response && response.data) || {};
      this._integrationVersion = (response && response.integration_version) || "—";
      this._data = {
        categories: data.categories || [],
        treatments: data.treatments || [],
        operators: data.operators || [],
        clients: data.clients || [],
        appointments: data.appointments || [],
        vouchers: data.vouchers || [],
        promo_vouchers: data.promo_vouchers || [],
        requests: data.requests || [],
        slot_blocks: data.slot_blocks || [],
        closures: data.closures || [],
        settings: data.settings || {},
      };
      // The notification and promo forms keep their unsaved edits across a
      // reload, so the placeholder of the saved values must not overwrite them.
      if (!this._notifyDraft) this._notifyDraft = { ...this._data.settings };
      if (!this._promoDraft) this._promoDraft = {
        promo_message: (this._data.settings.promo_message || ""),
        promo_time: (this._data.settings.promo_time || ""),
        promo_interval_sec: this._data.settings.promo_interval_sec != null
          ? this._data.settings.promo_interval_sec : 3,
        promo_max_sends: this._data.settings.promo_max_sends || 0,
        promo_window_min: this._data.settings.promo_window_min || 10,
        promo_date: this._data.settings.promo_date || "",
        promo_code: this._data.settings.promo_code || "",
        promo_expiry: this._data.settings.promo_expiry || "",
        promo_voucher_message: this._data.settings.promo_voucher_message || "",
        promo_voucher_days: this._data.settings.promo_voucher_days != null
          ? this._data.settings.promo_voucher_days : 30,
        promo_voucher_discount: this._data.settings.promo_voucher_discount != null
          ? this._data.settings.promo_voucher_discount : 10,
        promo_voucher_min_spend: this._data.settings.promo_voucher_min_spend != null
          ? this._data.settings.promo_voucher_min_spend : 100,
        promo_voucher_max_spend: this._data.settings.promo_voucher_max_spend != null
          ? this._data.settings.promo_voucher_max_spend : 500,
        promo_voucher_after_hours: this._data.settings.promo_voucher_after_hours != null
          ? this._data.settings.promo_voucher_after_hours : 24,
        promo_voucher_auto: this._data.settings.promo_voucher_auto === true,
      };
      // The website window (its hours, the step between offers and how far
      // ahead it may look), edited with its own Salva so a reload does not
      // overwrite a half-typed change.
      if (!this._webDraft) this._webDraft = {
        open_time: this._data.settings.web_open_time || "09:00",
        close_time: this._data.settings.web_close_time || "20:00",
        break_start: this._data.settings.web_break_start || "",
        break_end: this._data.settings.web_break_end || "",
        step_min: this._data.settings.web_step_min != null
          ? this._data.settings.web_step_min : 30,
        max_days_ahead: this._data.settings.web_max_days_ahead != null
          ? this._data.settings.web_max_days_ahead : 60,
        notify_whatsapp: this._data.settings.web_notify_whatsapp || "",
      };
      this._reindex();
    } catch (error) {
      this._data = {
        categories: [],
        treatments: [],
        operators: [],
        clients: [],
        appointments: [],
        slot_blocks: [],
        closures: [],
        settings: {},
      };
      this._reindex();
      this._message = {
        kind: "error",
        text: this._friendlyError(
          error,
          "Integrazione Spa Booking non disponibile. Aggiungila da Impostazioni → Dispositivi e servizi e ricarica la pagina."
        ),
      };
    } finally {
      this._loading = false;
      this._loadedOnce = true;
      this._render();
    }
  }

  _reindex() {
    const index = (list) => {
      const map = new Map();
      (list || []).forEach((item) => map.set(item.id, item));
      return map;
    };
    this._lookup = {
      category: index(this._data.categories),
      treatment: index(this._data.treatments),
      operator: index(this._data.operators),
      client: index(this._data.clients),
      appointment: index(this._data.appointments),
    };

    this._byDay = new Map();
    // A data refresh reshuffles the day's rows, so the group colours are
    // re-handed starting from the first one.
    this._groupColorMap = new Map();
    this._data.appointments.forEach((appointment) => {
      const start = parseDate(appointment.start);
      if (!start) return;
      const key = ymd(start);
      if (!this._byDay.has(key)) this._byDay.set(key, []);
      this._byDay.get(key).push(appointment);
    });
    this._byDay.forEach((list) =>
      list.sort((a, b) => String(a.start).localeCompare(String(b.start)))
    );

    this._applyAppearance();
  }

  /**
   * Reflect the stored appearance on the host element. The stylesheet keys off
   * this attribute, so switching it repaints the card without a re-render and
   * without touching the Home Assistant theme that governs the whole dashboard.
   */
  _applyAppearance() {
    const raw = String((this._data.settings || {}).appearance || "").trim().toLowerCase();
    const mode = APPEARANCE_MODES.includes(raw) ? raw : "auto";
    if (mode === "auto") {
      this.removeAttribute("data-spa-theme");
    } else {
      this.setAttribute("data-spa-theme", mode);
    }
  }

  // ------------------------------------------------------------- accessors

  _treatmentName(appointment) {
    const treatment = this._lookup.treatment.get(appointment.treatment_id);
    return treatment ? treatment.name : "Trattamento eliminato";
  }

  _categoryOf(treatment) {
    return treatment ? this._lookup.category.get(treatment.category_id) : null;
  }

  _operatorName(appointment) {
    const operator = this._lookup.operator.get(appointment.operator_id);
    return operator ? operator.name : null;
  }

  _clientName(appointment) {
    const client = this._lookup.client.get(appointment.client_id);
    if (!client) return "Cliente eliminato";
    return [client.first_name, client.last_name].filter(Boolean).join(" ") || client.phone;
  }

  _clientPhone(appointment) {
    const client = this._lookup.client.get(appointment.client_id);
    return client ? client.phone : "";
  }

  _clientNotes(appointment) {
    const client = this._lookup.client.get(appointment.client_id);
    return client ? client.notes : "";
  }

  _durationOf(appointment) {
    const start = parseDate(appointment.start);
    const end = parseDate(appointment.end);
    if (!start || !end) return null;
    return Math.round((end.getTime() - start.getTime()) / 60000);
  }

  _treatmentRequiresOperator(treatment) {
    if (!treatment) return false;
    if (this._operatorsForTreatment(treatment.id).length) return true;
    const category = this._categoryOf(treatment);
    return Boolean(category && category.requires_operator);
  }

  /**
   * Everything one operator has in the book, newest first.
   *
   * A cancelled appointment stays in the history instead of vanishing: it is
   * part of what she worked around, and the reason it was cancelled is what
   * the receptionist will be asked about. Splitting on "now" only changes the
   * label, never what is listed.
   */
  _operatorHistory(operator) {
    const now = new Date();
    return this._data.appointments
      .filter((appointment) => appointment.operator_id === operator.id)
      .map((appointment) => {
        const start = parseDate(appointment.start);
        const end = parseDate(appointment.end);
        const cancelled = appointment.status === "cancelled";
        return {
          appointment,
          when: start,
          end,
          // A booking nobody confirmed yet is not "in programma": the client
          // may never come, and counting it as done would overstate the work.
          state: cancelled
            ? "annullato"
            : appointment.status === "pending"
              ? "in attesa"
              : start && start > now
                ? "in programma"
                : "effettuato",
        };
      })
      .filter((entry) => entry.when)
      .sort((a, b) => String(b.appointment.start).localeCompare(String(a.appointment.start)));
  }

  /** Operators able to perform a treatment, read from their own card. */
  _operatorsForTreatment(treatmentId) {
    return this._data.operators.filter((operator) =>
      (operator.treatment_ids || []).includes(treatmentId)
    );
  }

  /** Treatments an operator performs, used by her configuration card. */
  _treatmentsOfOperator(operator) {
    const ids = operator.treatment_ids || [];
    return this._data.treatments.filter((treatment) => ids.includes(treatment.id));
  }

  /** An Italian phone number reduced to its national significant digits. */
  _nationalNumber(phone) {
    let digits = String(phone || "").replace(/\D/g, "");
    for (const prefix of ["0039", "39"]) {
      if (digits.startsWith(prefix) && digits.length > prefix.length) {
        digits = digits.slice(prefix.length);
        break;
      }
    }
    return digits.replace(/^0+/, "");
  }

  /** The WhatsApp chat id of an operator: an explicit one always wins. */
  _whatsappIdOf(operator) {
    if (operator.whatsapp_chat_id) return operator.whatsapp_chat_id;
    const phone = String(operator.phone || "").trim();
    if (!phone) return "";
    // A number that says which country it belongs to is used as it is: the
    // Italian country code would send the message to somebody else.
    if (isInternationalPhone(phone)) {
      const full = internationalDigits(phone);
      return full ? `${full}@c.us` : "";
    }
    const national = this._nationalNumber(phone);
    return national ? `39${national}@c.us` : "";
  }

  _operatorNamesFor(treatment) {
    return this._operatorsForTreatment(treatment.id)
      .map((operator) => operator.name)
      .sort((a, b) => a.localeCompare(b));
  }

  _selectedTreatment(treatmentId) {
    if (treatmentId) return this._lookup.treatment.get(treatmentId) || null;
    // No explicit id: the first treatment of the booking that has one.
    for (const treat of this._treatmentsOf(this._form)) {
      if (treat.treatment_id) {
        const found = this._lookup.treatment.get(treat.treatment_id);
        if (found) return found;
      }
    }
    return null;
  }

  _activeTreatments() {
    return this._data.treatments.filter((treatment) => treatment.active);
  }

  // ---------------------------------------------------- multi-booking state

  /** Monotonic id, so every row and entry can be found in the DOM again. */
  _uid() {
    this._uidSeq = (this._uidSeq || 0) + 1;
    return this._uidSeq;
  }

  /** A blank per-person block: her treatments and her accessories. */
  _personFrom(partial) {
    return {
      uid: this._uid(),
      treatments: [this._blankTreatment()],
      extras: [],
      ...(partial || {}),
    };
  }

  /** A blank treatment row of a person: picker, slot and masseuse. */
  _blankTreatment() {
    return { uid: this._uid(), treatment_id: "", operator_id: "", time: "10:00", list_price: null, price: null };
  }

  /** The treatment rows of a booking state (one person, or the flat form).
   *  Always a live array with at least one blank row, so adding one is a push. */
  _treatmentsOf(state) {
    if (!state) return [];
    if (!Array.isArray(state.treatments)) {
      // Legacy shape (scalar fields, no treatments list): promote them.
      state.treatments = [{
        uid: this._uid(),
        treatment_id: state.treatment_id || "",
        operator_id: state.operator_id || "",
        time: state.time || "10:00",
      }];
    }
    if (!state.treatments.length) state.treatments.push(this._blankTreatment());
    return state.treatments;
  }

  _peopleCount() {
    return Array.isArray(this._form.persons) ? this._form.persons.length : 1;
  }

  /** Hard ceiling for the people stepper: the treatment's max_parallel. */
  _peopleMax() {
    const treatment = this._selectedTreatment();
    if (treatment && !this._treatmentRequiresOperator(treatment)) {
      const max = Number(treatment.max_parallel) || 0;
      if (max > 0) return Math.min(10, max);
    }
    if (Array.isArray(this._form.persons)) {
      const ids = [];
      this._form.persons.forEach((person) => {
        this._treatmentsOf(person).forEach((treat) => {
          if (treat.treatment_id && !ids.includes(treat.treatment_id)) ids.push(treat.treatment_id);
        });
      });
      if (ids.length === 1) {
        const shared = this._lookup.treatment.get(ids[0]);
        if (shared && !this._treatmentRequiresOperator(shared)) {
          const max = Number(shared.max_parallel) || 0;
          if (max > 0) return Math.min(10, max);
        }
      }
    }
    return 10;
  }

  /** People that must be booked together for the selected treatment. */
  _peopleMin() {
    const treatment = this._selectedTreatment();
    if (treatment && !this._treatmentRequiresOperator(treatment)) {
      return Math.max(1, Number(treatment.min_parallel) || 0);
    }
    return 1;
  }

  /**
   * Change the requested number of people. One person keeps the quick single
   * form (flat fields); more than one switches to the per-person array,
   * preserving everything already typed as the first person.
   */
  _setPeople(n) {
    const count = Math.max(1, Math.min(this._peopleMax(), Math.floor(n)));
    if (count === 1) {
      const first = Array.isArray(this._form.persons) ? this._form.persons[0] : null;
      if (first) {
        this._form.treatments = this._treatmentsOf(first).map((t) => ({ ...t, uid: this._uid() }));
        this._form.extras = [...(first.extras || [])];
      }
      this._form.persons = null;
      this._form.people = 1;
    } else {
      const persons = Array.isArray(this._form.persons) ? this._form.persons.slice() : [];
      if (!persons.length) {
        persons.push(this._personFrom({
          treatments: this._treatmentsOf(this._form).map((t) => ({ ...t, uid: this._uid() })),
          extras: [...(this._form.extras || [])],
        }));
      }
      while (persons.length < count) persons.push(this._personFrom());
      this._form.persons = persons.slice(0, count);
      this._form.people = count;
    }
    this._render();
  }

  _removePersonAt(index) {
    const persons = (this._form.persons || []).filter((_, i) => i !== index);
    if (persons.length > 1) {
      this._form.persons = persons;
      this._form.people = persons.length;
    } else if (persons.length === 1) {
      // Back to a single person: her treatments become the flat form's ones.
      this._form.treatments = this._treatmentsOf(persons[0]).map((t) => ({ ...t, uid: this._uid() }));
      this._form.extras = [...(persons[0].extras || [])];
      this._form.persons = null;
      this._form.people = 1;
    }
    this._render();
  }

  /**
   * Copy the first person's treatment and slot onto one other person.
   * The masseuse is left alone on purpose: she may not be able to perform the
   * treatment that person is now getting, so the picker falls back to
   * "Automatica" whenever the copied treatment is out of her reach.
   */
  _copyFromFirst(index) {
    const persons = this._form.persons;
    if (!Array.isArray(persons) || index < 1 || !persons[0]) return;
    this._copyInto(persons[index], persons[0]);
    this._render();
  }

  /** The same copy, applied to every other person in one go. */
  _copyFirstToAll() {
    const persons = this._form.persons;
    if (!Array.isArray(persons) || persons.length < 2) return;
    const first = persons[0];
    persons.slice(1).forEach((person) => this._copyInto(person, first));
    this._render();
  }

  /** Copy the treatments (and their slots) from `source` onto `target`.
   * The masseuse is left alone on purpose: she may not be able to perform the
   * treatment that person is now getting, so the picker falls back to
   * "Automatica" whenever the copied treatment is out of her reach. */
  _copyInto(target, source) {
    const copy = this._treatmentsOf(source).map((t) => {
      const next = { ...t, uid: this._uid() };
      const treatment = this._lookup.treatment.get(next.treatment_id);
      if (
        next.operator_id &&
        treatment &&
        !this._operatorsForTreatment(treatment.id).some((op) => op.id === next.operator_id)
      ) {
        // The new treatment is not one she does, and offering her anyway would
        // be refused when saving.
        next.operator_id = "";
      }
      return next;
    });
    target.treatments = copy.length ? copy : [this._blankTreatment()];
    // The accessories are hers too: copying a person copies her whole booking.
    target.extras = [...(source.extras || [])];
    if (target.client_results) target.client_results = null;
  }

  /**
   * The payment to store, or null when the desk said nothing.
   *
   * Nothing ticked is not the same as "paid": the field is left out entirely
   * so the appointment keeps "not specified" instead of claiming it was
   * settled. Every amount travels only while its own flag is ticked, so a
   * stale number cannot linger after the flag is cleared.
   *
   * The requested deposit is the one exception: it is what the deposit request
   * asks for, not money received, so it must reach the booking with no flag
   * ticked. Only the flags settle a booking, so sending it keeps a pending
   * booking pending and still askable.
   */
  _paymentData(state = this._form) {
    const payment = state.payment || {};
    // Each amount is read only while its own flag is ticked, so a number left
    // behind by a flag that was unticked can never travel with the booking.
    const amountOf = (key) => {
      const value = parseFloat(String(payment[key] || "").replace(",", "."));
      return Number.isFinite(value) ? value : 0;
    };
    // The deposit the desk wants to ask the guest for, kept apart from the
    // "ha fatto acconto" flag on purpose.
    const depositRequested = amountOf("deposit_amount");
    const said = [payment.paid, payment.deposit, payment.voucher, payment.balance_due]
      .some(Boolean)
      || depositRequested > 0;
    // A booking that says nothing leaves the field out, so the appointment is
    // "not specified". An edit always sends it, or clearing the last flag
    // would silently keep the old payment instead of removing it.
    if (!said && !this._editing) return null;
    return {
      // A deposit and the balance still owed can both be true at once, so the
      // flags are sent as they are instead of being resolved into one state.
      paid: Boolean(payment.paid),
      paid_amount: payment.paid ? amountOf("paid_amount") : 0,
      deposit: Boolean(payment.deposit),
      deposit_amount: depositRequested,
      voucher: Boolean(payment.voucher),
      voucher_code: payment.voucher ? String(payment.voucher_code || "") : "",
      balance_due: Boolean(payment.balance_due),
      balance_due_amount: payment.balance_due ? amountOf("balance_due_amount") : 0,
      methods: PAYMENT_METHODS
        .filter(({ id }) => (payment.methods || []).includes(id))
        .map(({ id }) => id),
    };
  }

  /** Parse a money input the Italian way: comma or dot both work. */
  _priceInput(value) {
    const text = String(value == null ? "" : value).trim().replace(",", ".");
    if (!text) return null;
    const number = parseFloat(text);
    if (!Number.isFinite(number) || number < 0) return null;
    return Math.round(number * 100) / 100;
  }

  /** Effective prices of one booking row: discounted, list, catalogue. */
  _treatPrices(treat) {
    const treatment = (treat && treat.treatment_id && this._lookup.treatment.get(treat.treatment_id)) || null;
    const catalogue = treatment && treatment.price != null ? Number(treatment.price) || 0 : 0;
    const list = treat && treat.list_price != null ? treat.list_price : catalogue;
    const price = treat && treat.price != null ? treat.price : list;
    return { name: treatment ? treatment.name : "—", list, price };
  }

  /** Per-person breakdown and grand total of the new-booking form. */
  _bookingTotals() {
    const states = this._form.persons || [this._form];
    const people = states.map((person, personIndex) => {
      const lines = [];
      this._treatmentsOf(person).forEach((treat) => {
        if (!treat.treatment_id) return;
        lines.push({ treat, ...this._treatPrices(treat) });
      });
      const extras = (person.extras || []).map((id) => {
        const entry = this._accessory(id) || {};
        return { label: entry.label || id, price: Number(entry.price) || 0 };
      });
      const subtotal =
        Math.round((lines.reduce((sum, line) => sum + line.price, 0) +
          extras.reduce((sum, extra) => sum + extra.price, 0)) * 100) / 100;
      return { name: person.first_name || person.last_name || `Persona ${personIndex + 1}`, lines, extras, subtotal };
    });
    const total = Math.round(people.reduce((sum, person) => sum + person.subtotal, 0) * 100) / 100;
    return { people, total };
  }

  /** Sum of the staged takings of the new-booking form. */
  _stagedCollected() {
    const sum = (this._form.stagedPayments || []).reduce(
      (total, item) => total + (Number(item.amount) || 0), 0);
    return Math.round(sum * 100) / 100;
  }

  /** Box Totali: per person, treatments with list and discounted price. */
  /**
   * The deposit to ask the guest for, on a booking form or an edit draft.
   *
   * Plain money the desk types while the totals are in front of her, on the
   * same two-column rhythm as the prices above: the label on the left, the
   * amount where the price column sits. It is stored as the requested deposit
   * and never as a taking: no payment flag is ticked by it, so it does not
   * confirm a pending booking and does not count as collected money.
   */
  _depositField(state) {
    return el("div", { class: "stack tight" },
      el("div", { class: "deposit-row" },
        el("div", { class: "deposit-label" }, "Acconto richiesto (€)"),
        el("input", {
          class: "input", type: "text", inputmode: "decimal",
          "aria-label": "Acconto richiesto (€)",
          value: (state.payment && state.payment.deposit_amount) || "",
          placeholder: "0,00",
          on: {
            input: (event) => {
              state.payment = state.payment || {};
              state.payment.deposit_amount = event.target.value;
            },
            change: () => { this._render(); },
            keydown: (event) => { event.stopPropagation(); },
          },
        })),
      el("div", { class: "hint" },
        "Importo da chiedere all'ospite: è quello che usano la richiesta d'acconto e il riepilogo."));
  }

  /**
   * One price cell of the Totali grid.
   *
   * The column heading is the label, so the input only carries its own
   * accessible name. `apply` gets the parsed number because the booking form
   * writes on the treatment row while the edit sheet writes on the draft.
   * Nothing redraws while typing, or the focus would jump away: the totals
   * refresh when the field is left.
   */
  _totaliPriceCell(value, apply, label) {
    return el("input", {
      class: "input", type: "text", inputmode: "decimal",
      "aria-label": label,
      value: value != null ? String(value).replace(".", ",") : "",
      placeholder: "0,00",
      on: {
        input: (event) => { apply(this._priceInput(event.target.value)); },
        change: () => { this._render(); },
        keydown: (event) => { event.stopPropagation(); },
      },
    });
  }

  _totaliBlock() {
    const box = el("div", { class: "stack tight" },
      el("h3", {}, "Totali"));
    const { people, total } = this._bookingTotals();
    if (!people.some((person) => person.lines.length)) {
      box.appendChild(el("div", { class: "hint" }, "Scegli i trattamenti per vedere i totali."));
      return box;
    }
    people.forEach((person) => {
      if (!person.lines.length && !person.extras.length) return;
      const card = el("div", { class: "cfg-box" },
        el("div", {}, el("strong", {}, person.name)));
      // One line per treatment: its name and its two prices side by side, so a
      // figure is never read against the wrong treatment. Three columns at
      // every width, a phone included.
      if (person.lines.length) {
        const grid = el("div", { class: "totali-grid" },
          el("div", { class: "totali-head" }, "Trattamento"),
          el("div", { class: "totali-head" }, "Listino (€)"),
          el("div", { class: "totali-head" }, "Scontato (€)"));
        person.lines.forEach((line) => {
          grid.appendChild(el("div", { class: "totali-name" }, line.name));
          grid.appendChild(this._totaliPriceCell(line.list, (value) => {
            line.treat.list_price = value;
          }, `Listino di ${line.name}`));
          grid.appendChild(this._totaliPriceCell(line.price, (value) => {
            line.treat.price = value;
          }, `Scontato di ${line.name}`));
        });
        card.appendChild(grid);
      }
      person.extras.forEach((extra) => {
        card.appendChild(el("div", { class: "dim small" },
          `${extra.label} · ${euro(extra.price)}`));
      });
      card.appendChild(el("div", {}, el("strong", {}, `Subtotale: ${euro(person.subtotal)}`)));
      box.appendChild(card);
    });
    box.appendChild(el("div", {}, el("strong", {}, `Totale appuntamento: ${euro(total)}`)));
    box.appendChild(this._depositField(this._form));
    return box;
  }

  /** Box Incassi: staged takings, collected total and amount still owed. */
  _incassiBlock() {
    const { total } = this._bookingTotals();
    const collected = this._stagedCollected();
    const box = el("div", { class: "stack tight" },
      el("h3", {}, "Incassi"));
    box.appendChild(el("button", {
      class: "btn primary small",
      disabled: this._busy,
      on: { click: () => this._openPayPopup() },
    }, el("ha-icon", { icon: "mdi:cash-plus" }), "Registra un incasso"));
    const staged = this._form.stagedPayments || [];
    if (!staged.length) {
      box.appendChild(el("div", { class: "hint" }, "Nessun incasso registrato."));
    }
    staged.forEach((item) => {
      const method = PAYMENT_METHODS.find(({ id }) => id === item.method) || {};
      box.appendChild(el("div", { class: "row tight" },
        el("span", { class: "grow" },
          `${method.label || item.method} · ${item.date || "—"} · ${euro(item.amount)}`),
        el("button", {
          class: "icon-btn danger",
          title: "Rimuovi incasso",
          disabled: this._busy,
          on: { click: () => {
            this._form.stagedPayments = staged.filter((other) => other.uid !== item.uid);
            this._render();
          } },
        }, el("ha-icon", { icon: "mdi:close" }))));
    });
    box.appendChild(el("div", {}, `Totale incassato: ${euro(collected)}`));
    const due = Math.max(0, Math.round((total - collected) * 100) / 100);
    box.appendChild(el("div", {}, el("strong", {}, `Totale da incassare: ${euro(due)}`)));
    return box;
  }

  /** Effective line total of the appointment being edited (draft prices). */
  _editLineTotal(draft) {
    const treatment = (draft.treatment_id && this._lookup.treatment.get(draft.treatment_id)) || null;
    const catalogue = treatment && treatment.price != null ? Number(treatment.price) || 0 : 0;
    const list = draft.list_price != null ? draft.list_price : catalogue;
    const price = draft.price != null ? draft.price : list;
    const extras = (draft.extras || []).reduce((sum, id) => {
      const entry = this._accessory(id) || {};
      return sum + (Number(entry.price) || 0);
    }, 0);
    return {
      name: treatment ? treatment.name : "—",
      list, price,
      extras: (draft.extras || []).map((id) => {
        const entry = this._accessory(id) || {};
        return { label: entry.label || id, price: Number(entry.price) || 0 };
      }),
      total: Math.round((price + extras) * 100) / 100,
    };
  }

  /** Box Totali in the edit form: one treatment, editable prices. */
  _editTotaliBlock(draft) {
    const line = this._editLineTotal(draft);
    // The party around this appointment: her own row is the draft, the other
    // members are as they stand in the data, so the total is the whole
    // booking and not just the person being edited.
    const anchor = this._editing && this._editing.id
      ? this._lookup.appointment.get(this._editing.id)
      : null;
    const others = anchor
      ? this._groupOf(anchor).filter((member) => member.id !== anchor.id)
      : [];
    const othersTotal = others.reduce((sum, member) => {
      const parts = this._lineBreakdown(member);
      return sum + parts.price + parts.extras;
    }, 0);
    const persons = others.length + 1;
    const total = Math.round((line.total + othersTotal) * 100) / 100;
    const box = el("div", { class: "stack tight" },
      el("h3", {}, "Totali"));
    // Same three columns as the booking form. The treatment name moved into
    // the grid, so it is no longer repeated as the card title.
    const card = el("div", { class: "cfg-box" },
      el("div", { class: "totali-grid" },
        el("div", { class: "totali-head" }, "Trattamento"),
        el("div", { class: "totali-head" }, "Listino (€)"),
        el("div", { class: "totali-head" }, "Scontato (€)"),
        el("div", { class: "totali-name" }, line.name),
        this._totaliPriceCell(line.list, (value) => { draft.list_price = value; },
          `Listino di ${line.name}`),
        this._totaliPriceCell(line.price, (value) => { draft.price = value; },
          `Scontato di ${line.name}`)));
    line.extras.forEach((extra) => {
      card.appendChild(el("div", { class: "dim small" },
        `${extra.label} · ${euro(extra.price)}`));
    });
    if (others.length) {
      card.appendChild(el("div", { class: "dim small" },
        `${euro(line.price)} a persona × ${persons} persone`));
    }
    card.appendChild(el("div", {}, el("strong", {},
      others.length
        ? `Totale prenotazione: ${euro(total)}`
        : `Totale appuntamento: ${euro(total)}`)));
    box.appendChild(card);
    box.appendChild(this._depositField(draft));
    return { box, total };
  }

  /** Box Incassi in the edit form: live takings of the appointment. */
  _editIncassiBlock(appointment, total) {
    // Takings are summed over the whole party: a deposit often sits on the
    // first appointment of a group, so reading only this one would show the
    // booking unpaid while its money is already registered.
    const members = this._groupOf(appointment);
    const live = (members.length ? members : [appointment])
      .map((member) => (this._data.appointments || []).find((item) => item.id === member.id) || member);
    const rows = live.flatMap((member) => (member.payments || [])
      .map((item) => ({ member, item })));
    const collected = Math.round(rows.reduce(
      (sum, { item }) => sum + (Number(item.amount) || 0), 0) * 100) / 100;
    const box = el("div", { class: "stack tight" },
      el("h3", {}, "Incassi"));
    box.appendChild(el("button", {
      class: "btn primary small",
      disabled: this._busy,
      on: { click: () => this._openPayPopupFor(appointment.id) },
    }, el("ha-icon", { icon: "mdi:cash-plus" }), "Registra un incasso"));
    if (!rows.length) {
      box.appendChild(el("div", { class: "hint" }, "Nessun incasso registrato."));
    }
    rows.forEach(({ member, item }) => {
      const method = PAYMENT_METHODS.find(({ id }) => id === item.method) || {};
      box.appendChild(el("div", { class: "row tight" },
        el("span", { class: "grow" },
          `${method.label || item.method} · ${item.date || "—"} · ${euro(item.amount)}`),
        el("button", {
          class: "icon-btn danger",
          title: "Rimuovi incasso",
          disabled: this._busy,
          on: { click: async () => {
            try {
              // The taking is removed from the appointment that holds it: on
              // a group a deposit may sit on a member other than this one,
              // and the backend only looks inside the record named here.
              await this._call("delete_payment", {
                appointment_id: member.id,
                payment_id: item.id,
              });
            } catch (error) {
              /* message already shown */
            }
          } },
        }, el("ha-icon", { icon: "mdi:close" }))));
    });
    box.appendChild(el("div", {}, `Totale incassato: ${euro(collected)}`));
    const due = Math.max(0, Math.round((total - collected) * 100) / 100);
    box.appendChild(el("div", {}, el("strong", {}, `Totale da incassare: ${euro(due)}`)));
    return box;
  }

  /** Open the taking popup with today and the first method preselected. */
  _openPayPopup() {
    this._payPopup = {
      target: { kind: "form" },
      method: "cash",
      date: (this._form && this._form.date) || todayStr(),
      amount: "",
    };
    this._render();
  }

  /** Open the taking popup writing straight onto an existing appointment. */
  _openPayPopupFor(appointmentId) {
    this._payPopup = {
      target: { kind: "appointment", id: appointmentId },
      method: "cash",
      date: todayStr(),
      amount: "",
    };
    this._render();
  }

  _closePayPopup() {
    this._payPopup = null;
    this._render();
  }

  /** Confirm the taking popup into the staged list of the form. */
  async _confirmPayPopup() {
    const draft = this._payPopup || {};
    const amount = this._priceInput(draft.amount);
    if (!draft.method || amount == null || amount <= 0) {
      this._message = { kind: "error", text: "Indica metodo, data e un importo positivo." };
      this._render();
      return;
    }
    const target = draft.target || { kind: "form" };
    if (target.kind === "appointment" && target.id) {
      // Existing appointment: written at once, the reload brings fresh data.
      this._payPopup = null;
      try {
        await this._call("add_payment", {
          appointment_id: target.id,
          method: draft.method,
          date: String(draft.date || todayStr()),
          amount,
        });
      } catch (error) {
        /* message already shown */
      }
      return;
    }
    this._form.stagedPayments = [...(this._form.stagedPayments || []), {
      uid: this._uid(),
      method: draft.method,
      date: String(draft.date || todayStr()),
      amount,
    }];
    this._payPopup = null;
    this._render();
  }

  /** The taking popup, over a backdrop like the appointment detail. */
  _renderPayPopup() {
    const draft = this._payPopup;
    const sheet = el("div", { class: "detail-sheet" },
      el("h3", {}, "Registra un incasso"));
    const methodSelect = el("select", {
      class: "input",
      on: {
        change: (event) => { draft.method = event.target.value; this._render(); },
      },
    });
    PAYMENT_METHODS.forEach(({ id, label }) => {
      methodSelect.appendChild(el("option", { value: id, selected: draft.method === id }, label));
    });
    sheet.appendChild(el("label", { class: "field" },
      el("span", {}, "Tipo di pagamento"),
      methodSelect));
    sheet.appendChild(el("label", { class: "field" },
      el("span", {}, "Data di pagamento"),
      el("input", {
        class: "input", type: "date", value: draft.date || "",
        on: { input: (event) => { draft.date = event.target.value; } },
      })));
    sheet.appendChild(el("label", { class: "field" },
      el("span", {}, "Incasso (€)"),
      el("input", {
        class: "input", type: "text", inputmode: "decimal",
        value: draft.amount || "", placeholder: "0,00",
        on: {
          input: (event) => { draft.amount = event.target.value; },
          keydown: (event) => { event.stopPropagation(); },
        },
      })));
    sheet.appendChild(el("div", { class: "row" },
      el("button", {
        class: "btn primary", disabled: this._busy,
        on: { click: () => this._confirmPayPopup() },
      }, "Registra"),
      el("button", { class: "btn", on: { click: () => this._closePayPopup() } }, "Annulla")));
    return el("div", {
      class: "detail-backdrop",
      on: { click: (event) => {
        if (event.target === event.currentTarget) this._closePayPopup();
      } },
    }, sheet);
  }

  /** Everything that has to be booked, in the create_bookings shape.
   *  A person can book several treatments the same day, each in its own slot:
   *  one row per treatment. Only the first row of a person opens her client
   *  card, every following row lands on that very same card. */
  _bookingRows() {
    const clients =
      this._form.client_mode === "existing"
        ? this._form.client_id
          ? { client_id: this._form.client_id }
          : {}
        : {
            first_name: this._form.first_name,
            last_name: this._form.last_name,
            phone: this._form.phone,
            email: this._form.email,
            client_notes: this._form.client_notes,
          };
    const rows = [];
    (this._form.persons || [this._form]).forEach((person, personIndex) => {
      this._treatmentsOf(person).forEach((treat, index) => {
        if (!treat.treatment_id) return;
        rows.push({
          treatment_id: treat.treatment_id,
          // One flag for the whole batch: a party waits together or is confirmed
          // together, and the backend refuses a batch that asks for both.
          pending: this._form.pending,
          // Same for the hotel/external flag: the party comes from one place.
          guest_type: this._form.guest_type || GUEST_DEFAULT,
          entries: [
            {
              start: `${this._form.date}T${treat.time || "10:00"}:00`,
              notes: this._form.notes || "",
              // The accessories are the person's, not the treatment's: the same
              // set goes on every treatment she booked that day.
              extras: person.extras || [],
              // Per-row agreed prices, both editable from the Totali box.
              // Null means catalogue price: the backend falls back to it.
              ...(treat.appointment_id ? { appointment_id: treat.appointment_id } : {}),
              ...(treat.list_price != null ? { list_price: treat.list_price } : {}),
              ...(treat.price != null ? { price: treat.price } : {}),
              ...(treat.operator_id ? { operator_id: treat.operator_id } : {}),
              ...(this._batchEditing ? {} : (this._paymentData() ? { payment: this._paymentData() } : {})),
              ...clients,
              // Which person of the party this row is: 0 is the one written on
              // the card (the leader), 1.. are her guests. The backend uses this
              // to refuse only the same person twice in the same hour, not two
              // different people of one party.
              "person": personIndex,
              // A separate card per person, for two people who share a name:
              // only the first of her treatments forces the card, the rest of
              // the same person must match it.
              ...(index === 0 && this._form.new_client !== false ? { force_new: true } : {}),
            },
          ],
        });
      });
    });
    return rows;
  }

  _appointmentsOfDay(day) {
    return (this._byDay.get(day) || []).filter((appointment) => appointment.status !== "cancelled");
  }

  /** Whether an appointment matches the current search query. */
  _matchesSearch(appointment) {
    const query = (this._searchQuery || "").trim().toLowerCase();
    if (!query) return true;
    const haystack = [
      appointment.code || "",
      (appointment.client && (appointment.client.full_name || "")) || "",
      (appointment.client && (appointment.client.phone || "")) || "",
      (appointment.treatment && (appointment.treatment.name || "")) || "",
    ]
      .join(" ")
      .toLowerCase();
    return haystack.includes(query);
  }

  _appointmentsOfMonth(date) {
    const out = new Map();
    this._byDay.forEach((list, key) => {
      const day = new Date(`${key}T00:00:00`);
      if (day.getFullYear() === date.getFullYear() && day.getMonth() === date.getMonth()) {
        const open = list.filter((appointment) => appointment.status !== "cancelled");
        if (open.length) out.set(key, open);
      }
    });
    return out;
  }

  _clientAppointments(clientId) {
    return this._data.appointments
      .filter((appointment) => appointment.client_id === clientId)
      .sort((a, b) => String(b.start).localeCompare(String(a.start)));
  }

  // ------------------------------------------------------------------ calls

  // `hass.callService` cannot deliver `return_response` on this frontend: the
  // fifth argument never reaches Home Assistant, and every service of this
  // integration is registered with `SupportsResponse.ONLY`, so each call is
  // rejected with "must be called with return_response=True". The websocket
  // command carries the flag inside the message itself, which is how the other
  // cards of this installation call services that answer with data.
  async _service(service, data) {
    const result = await this._hass.callWS({
      type: "call_service",
      domain: DOMAIN,
      service,
      service_data: data || {},
      return_response: true,
    });
    return (result && result.response) || {};
  }

  async _call(service, data) {
    this._busy = true;
    this._render();
    try {
      const response = await this._service(service, data);
      this._message = { kind: "ok", text: this._successText(service) };
      await this._loadData();
      return response;
    } catch (error) {
      this._message = { kind: "error", text: this._friendlyError(error, "Operazione non riuscita.") };
      this._render();
      throw error;
    } finally {
      this._busy = false;
      this._render();
    }
  }

  /**
   * Ask the configured WAHA gateway who it is: reachable, key accepted, which
   * router. Sends nothing and changes nothing, so it is safe to press first.
   */
  async _checkWaha() {
    this._busy = true;
    this._wahaStatus = "Verifica in corso…";
    this._render();
    try {
      const result = await this._service("check_waha", {});
      if (!result || result.configured === false) {
        this._wahaStatus = "⚠ " + ((result && result.error) || "Gateway non configurato.");
      } else if (result.ok) {
        this._wahaStatus =
          "✅ WAHA raggiungibile — versione " + (result.version || "?") +
          (result.engine ? " · router " + result.engine : "") + ".";
      } else {
        this._wahaStatus = "⚠ " + (result.error || "WAHA non raggiungibile.");
      }
    } catch (error) {
      this._wahaStatus = "⚠ " + this._friendlyError(error, "Verifica non riuscita.");
    } finally {
      this._busy = false;
      this._render();
    }
  }

  /**
   * Turn on inbound answers: save the gateway, then subscribe its session to
   * this integration's webhook. The secret is created once on the backend and
   * never comes back, so nothing here can leak it.
   */
  async _enableWaha() {
    this._busy = true;
    this._wahaStatus = "Attivazione in corso…";
    this._render();
    try {
      await this._call("update_settings", {
        waha_url: (this._notifyDraft && this._notifyDraft.waha_url || "").trim(),
        waha_api_key: (this._notifyDraft && this._notifyDraft.waha_api_key) || "",
        waha_session: ((this._notifyDraft && this._notifyDraft.waha_session) || "").trim() || "default",
        waha_ha_url: ((this._notifyDraft && this._notifyDraft.waha_ha_url) || "").trim(),
      });
      const result = await this._service("waha_webhook", {});
      this._wahaStatus =
        "✅ Ricezione attiva — WAHA pubblicherà su " +
        (result && result.webhook_url ? result.webhook_url : "questo webhook") +
        ((result && result.updated) ? "." : " (iscrizione già presente).");
      await this._loadData();
    } catch (error) {
      this._wahaStatus = "⚠ " + this._friendlyError(error, "Attivazione non riuscita.");
    } finally {
      this._busy = false;
      this._render();
    }
  }

  async _toggleOffer(appointment, isPending) {
    await this._call("set_offer_state", {
      appointment_id: appointment.id,
      state: isPending ? "confirmed" : "pending",
    });
  }

  _successText(service) {
    const map = {
      create_appointment: "Appuntamento creato.",
      create_bookings: "Appuntamenti creati.",
      clear_slot_block: "Fascia riaperta.",
      set_offer_state: "Stato conferma aggiornato.",
      send_operator_message: "Messaggio inviato all'operatrice.",
      send_guest_summary: "Riepilogo inviato all'ospite.",
      send_deposit_request: "Richiesta acconto inviata all'ospite.",
      cancel_appointment: "Appuntamento annullato.",
      delete_appointment: "Appuntamento eliminato.",
      check_in_appointment: "Ingresso registrato.",
      check_out_appointment: "Uscita registrata.",
      resize_appointment_group: "Numero di persone aggiornato.",
      save_client: "Scheda cliente salvata.",
      delete_client: "Scheda cliente eliminata.",
      add_category: "Categoria creata.",
      update_category: "Categoria aggiornata.",
      delete_category: "Categoria eliminata.",
      add_treatment: "Trattamento creato.",
      update_treatment: "Trattamento aggiornato.",
      delete_treatment: "Trattamento eliminato.",
      add_operator: "Operatrice creata.",
      update_operator: "Operatrice aggiornata.",
      delete_operator: "Operatrice eliminata.",
      update_settings: "Destinatari aggiornati.",
      set_user_permissions: "Permessi aggiornati.",
      create_request: "Richiesta salvata.",
      delete_request: "Richiesta eliminata.",
      confirm_request: "Richiesta confermata.",
      send_request_message: "Messaggio richiesta inviato.",
      save_settings: "Impostazioni salvate.",
      set_accessories: "Accessori salvati.",
      regenerate_public_token: "Nuovo token del sito generato.",
    };
    return map[service] || "Fatto.";
  }

  /**
   * Turn a service call error into something a receptionist can act on.
   * A missing or unloaded integration is reported with actionable guidance,
   * because that is the one failure an operator can actually fix.
   */
  _friendlyError(error, fallback) {
    if (!error) return fallback;
    let message = String(error.message || error);
    message = message.replace(/^Error performing service call: /i, "");
    // Home Assistant appends the traceback when logging is verbose.
    message = message.split("\n\n")[0].trim();

    const unavailable = /(service not found|not found|not loaded|not found|no service)/i.test(message);
    if (unavailable) {
      return "Integrazione Spa Booking non disponibile. Aggiungila da Impostazioni → Dispositivi e servizi, poi ricarica la pagina.";
    }
    return message || fallback;
  }

  // -------------------------------------------------------------- PERMESSI

  /**
   * The signed-in user's access level for this dashboard.
   *
   * The stored map wins; a Home Assistant admin or owner who is not listed
   * stays an administrator, so the people who run Home Assistant can never be
   * shut out of the card. Everyone else has no access until granted.
   */
  _userLevel() {
    const user = this._hass && this._hass.user;
    if (!user) return "admin";
    const permissions =
      (this._data && this._data.settings && this._data.settings.permissions) || {};
    if (permissions[user.id]) return permissions[user.id];
    if (user.is_admin || user.is_owner) return "admin";
    return "none";
  }

  /** Whether the signed-in user may do <capability>. */
  _can(capability) {
    const rank = { none: 0, read: 1, operator: 2, manager: 3, admin: 4 };
    const need =
      {
        view_agenda: "read",
        view_calendar: "read",
        view_clients: "operator",
        book: "operator",
        day: "operator",
        offers: "operator",
        messages: "manager",
        manage_clients: "manager",
        config: "admin",
      }[capability] || "admin";
    return (rank[this._userLevel()] || 0) >= (rank[need] || 0);
  }

  /** The tabs the signed-in user may see, in their usual order. */
  _visibleTabs() {
    const allowed =
      {
        none: [],
        read: ["agenda"],
        operator: ["agenda", "nuovo", "spa", "clienti", "voucher", "whatsapp"],
        manager: ["agenda", "nuovo", "spa", "clienti", "voucher", "whatsapp"],
        admin: ["agenda", "nuovo", "spa", "clienti", "voucher", "whatsapp", "config"],
      }[this._userLevel()] || [];
    return TABS.filter((tab) => allowed.includes(tab.id));
  }

  /**
   * Sub-tabs of the Agenda tab. A read-only account sees both the day list and
   * the month, exactly as it used to see the two top-level tabs.
   */
  _visibleAgendaTabs() {
    const allowed =
      {
        none: [],
        read: ["agenda", "calendario"],
        operator: ["agenda", "calendario"],
        manager: ["agenda", "calendario"],
        admin: ["agenda", "calendario"],
      }[this._userLevel()] || [];
    return AGENDA_TABS.filter((tab) => allowed.includes(tab.id));
  }

  /**
   * Sub-tabs of the Spa tab. Every level that may open Spa sees the controls;
   * the cameras follow the level that used to own the Telecamere tab, so a
   * read-only account never gets them.
   */
  _visibleSpaTabs() {
    const allowed =
      {
        none: [],
        read: [],
        operator: ["controlli", "telecamere"],
        manager: ["controlli", "telecamere"],
        admin: ["controlli", "telecamere"],
      }[this._userLevel()] || [];
    return SPA_TABS.filter((tab) => allowed.includes(tab.id));
  }

  _visibleNuovoTabs() {
    const allowed =
      {
        none: [],
        read: [],
        operator: ["appuntamento", "nuova", "lista"],
        manager: ["appuntamento", "nuova", "lista"],
        admin: ["appuntamento", "nuova", "lista"],
      }[this._userLevel()] || [];
    return NUOVO_TABS.filter((tab) => allowed.includes(tab.id));
  }

  /** What an account without access to this dashboard sees. */
  _renderDenied() {
    const user = this._hass && this._hass.user;
    const name = user && user.name ? String(user.name) : "";
    return el(
      "div",
      { class: "wrap" },
      el(
        "div",
        { class: "denied" },
        el("ha-icon", { icon: "mdi:shield-lock-outline", class: "denied-icon" }),
        el("h2", {}, "Accesso non consentito"),
        el("p", {},
          name
            ? `Ciao ${name}, il tuo account non ha accesso a questa dashboard.`
            : "Il tuo account non ha accesso a questa dashboard."),
        el("p", { class: "hint" },
          "Chiedi a un amministratore di abilitarti dalla sezione Accessi della configurazione.")
      )
    );
  }

  // ----------------------------------------------------------------- render

  /**
   * Redraw the whole card.
   *
   * Lovelace swallows whatever a card throws and shows its own error card, so a
   * failure here would leave an empty card with no explanation. Drawing the
   * reason instead is the only thing that lets anybody act on it.
   */
  _render() {
    try {
      this._renderInner();
    } catch (error) {
      this._renderFailure(error);
    }
  }

  /**
   * Keep the keystrokes in a search field that redraws the card.
   *
   * Redrawing on every letter destroys the field and steals the focus: the
   * next keys land on Home Assistant and its popups open. So the redraw is
   * debounced and the field takes the focus back afterwards, with the caret at
   * the end. The keys never reach the dashboard shortcuts, capture phase too.
   */
  _searchInputRedraw(input, selector, store) {
    input.addEventListener("input", (event) => {
      store(event.target.value);
      clearTimeout(this._searchRedrawTimer);
      this._searchRedrawTimer = setTimeout(() => {
        this._searchRedrawTimer = null;
        this._render();
        const node = this.shadowRoot && this.shadowRoot.querySelector(selector);
        if (node) {
          node.focus();
          const end = (node.value || "").length;
          try { node.setSelectionRange(end, end); } catch (err) { /* noop */ }
        }
      }, 250);
    });
    ["keydown", "keyup", "keypress"].forEach((type) =>
      input.addEventListener(type, (event) => event.stopPropagation(), true));
    return input;
  }

  /** What went wrong, in the card, instead of an empty card. */
  _renderFailure(error) {
    try {
      const root = this.shadowRoot;
      root.innerHTML = "";
      add(root, this._style());
      const box = el("div", { class: "stack" });
      box.appendChild(
        el("div", { class: "hint warn" },
          "La card non è riuscita a disegnarsi: " +
          (error && error.message ? error.message : String(error)))
      );
      // The first stack frames name the function and the line, which is what
      // identifies the fault; the rest is noise for whoever has to read it.
      const frames = error && error.stack
        ? String(error.stack).split("\n").slice(1, 4).join(" · ").trim()
        : "";
      if (frames) box.appendChild(el("div", { class: "appt-note" }, frames));
      box.appendChild(
        el("button", {
          class: "btn",
          on: { click: () => { this._editing = null; this._render(); } },
        }, "Torna all'agenda")
      );
      root.appendChild(box);
    } catch (fatal) {
      // Nothing left to draw with: at least do not leave a half-written card.
    }
  }

  _renderInner() {
    if (!this._ready) return;
    const root = this.shadowRoot;
    root.innerHTML = "";
    add(root, this._style());

    // Nothing but a loading line until the first load answers: only then are
    // the permissions known, so a granted account never sees a flash of
    // "Accesso non consentito".
    if (!this._loadedOnce) {
      root.appendChild(
        el("div", { class: "wrap" }, el("div", { class: "hint" }, "Caricamento…"))
      );
      return;
    }
    // An account with no access sees the reason and nothing else: no data, no
    // tabs, no header.
    if (this._userLevel() === "none") {
      root.appendChild(this._renderDenied());
      return;
    }
    // A tab the account may not see must not stay selected after a level
    // change; fall back to the first tab it is allowed to see.
    const allowed = this._visibleTabs();
    if (!allowed.some((tab) => tab.id === this._tab)) {
      this._tab = allowed.length ? allowed[0].id : "agenda";
    }

    // The header and the tabs form one full-width bar that stays on top while
    // the content scrolls, so the card reads like a page and not like a card.
    const topbar = el("div", { class: "topbar" });
    if (!this._config.hidden_header) add(topbar, this._header());
    const searchResults = this._searchResults();
    if (searchResults) topbar.appendChild(searchResults);
    add(topbar, this._tabs());
    root.appendChild(topbar);

    const body = el("div", { class: "wrap" });
    if (this._message) add(body, this._messageBox());
    if (this._loading && !this._data.appointments.length) {
      body.appendChild(el("div", { class: "hint" }, "Caricamento…"));
    }

    if (this._tab === "agenda") add(body, this._renderAgenda());
    if (this._tab === "nuovo") add(body, this._renderNew());
    if (this._tab === "spa") add(body, this._renderSpa());
    if (this._tab === "clienti") add(body, this._renderClients());
    if (this._tab === "voucher") add(body, this._renderVouchers());
    if (this._tab === "whatsapp") add(body, this._renderWhatsapp());
    if (this._tab === "config") add(body, this._renderConfig());

    root.appendChild(body);
    // The popup lives outside the scrolling body so it covers whatever the
    // reader was looking at when they tapped the row.
    if (this._detailId) add(root, this._renderDetail());
    if (this._payPopup) add(root, this._renderPayPopup());
    if (this._overlapPopup) add(root, this._renderOverlapPopup());
    // The view container only exists once Home Assistant has rendered the
    // dashboard around us, so the header height is reclaimed here and not only
    // on connect.
    this._applyFullscreen();
  }

  /**
   * Open Home Assistant's own navigation menu.
   *
   * The listener lives on `home-assistant-main`, which sits inside the shadow
   * root of `home-assistant` — see home-assistant-main.ts. An event only ever
   * travels upwards, so it has to be fired on that element or below: firing it
   * on `home-assistant` sends it away from the listener and nothing happens.
   * `open: true` makes the button open the menu instead of toggling it, so
   * pressing it twice never leaves the desk without a way back.
   */
  _toggleHaMenu() {
    const shell = document.querySelector("home-assistant");
    const main =
      shell && shell.shadowRoot
        ? shell.shadowRoot.querySelector("home-assistant-main")
        : null;
    (main || shell || document).dispatchEvent(
      new CustomEvent("hass-toggle-menu", {
        bubbles: true,
        composed: true,
        detail: { open: true },
      })
    );
  }

  /**
   * Hide Home Assistant's own header, so the card really fills the screen.
   *
   * The dashboard used to take a `fullscreen: true`, but Home Assistant dropped
   * that option: LovelaceConfig today carries only `background` and `views`,
   * and hui-root renders its `.header` unconditionally. There is no setting
   * left to ask for this, so the card does it where the header actually lives.
   *
   * The header lives in hui-root's shadow root, so that is where the card acts,
   * and the change is undone as soon as the option is turned off. If the walk
   * upwards ever fails, nothing happens: a card must never be the reason a
   * dashboard stops rendering.
   */
  _applyFullscreen() {
    this._setFullscreen(this._config.fullscreen === true);
  }

  /** Show or remove the injected style; false always means "put it back". */
  _setFullscreen(wanted) {
    const root = this._lovelaceRoot();
    if (!root || !root.shadowRoot) return;

    // Inline styles, not a stylesheet: Home Assistant builds its component
    // styles as adopted stylesheets, which win over anything written inside a
    // shadow tree. An inline declaration outranks those, so the header height
    // really goes away instead of only looking gone.
    const header = root.shadowRoot.querySelector(".header");
    const container = root.shadowRoot.querySelector("hui-view-container");

    if (!wanted) {
      if (header && header.dataset.spaFullscreen !== undefined) {
        header.style.display = "";
        delete header.dataset.spaFullscreen;
      }
      if (container && container.dataset.spaFullscreen !== undefined) {
        container.style.paddingTop = "";
        delete container.dataset.spaFullscreen;
      }
      return;
    }
    if (header) {
      header.style.display = "none";
      header.dataset.spaFullscreen = "1";
    }
    if (container) {
      // The view padded itself by the height of the header we just hid. Only
      // the notch is kept, otherwise the card would slide under the status bar.
      container.style.paddingTop = "var(--safe-area-inset-top, 0px)";
      container.dataset.spaFullscreen = "1";
    }
  }

  /** The hui-root element above this card, or null when it cannot be found. */
  _lovelaceRoot() {
    let node = typeof this.getRootNode === "function" ? this.getRootNode() : null;
    for (let depth = 0; node && depth < 20; depth += 1) {
      const host = node.host || node;
      if (host && host.localName === "hui-root") return host;
      // Outside a shadow root getRootNode returns the document, and the
      // document returns itself: the depth limit is what stops that loop.
      node =
        host && typeof host.getRootNode === "function" ? host.getRootNode() : null;
    }
    return null;
  }

  /**
   * Results of the header search, under the search field. Every booking (past,
   * present, future) matches first; client cards are offered only when no
   * booking matches. Tapping a booking opens its day and popup; tapping a card
   * opens it in the Clienti tab.
   */
  _searchResults() {
    const query = (this._searchQuery || "").trim().toLowerCase();
    if (!query) return null;
    const panel = el("div", { class: "search-results" });
    panel.appendChild(
      el("div", { class: "search-results-head" },
        el("span", { class: "dim small" }, `Ricerca: «${this._searchQuery.trim()}»`),
        el("button", {
          class: "icon-btn",
          title: "Chiudi ricerca",
          on: { click: () => { this._searchQuery = ""; this._render(); } },
        }, el("ha-icon", { icon: "mdi:close" })))
    );

    const bookings = (this._data.appointments || [])
      .filter((appointment) => appointment.status !== "cancelled" && this._matchesSearch(appointment))
      .sort((a, b) => String(a.start).localeCompare(String(b.start)));
    if (bookings.length) {
      bookings.slice(0, 40).forEach((appointment) => {
        const start = parseDate(appointment.start);
        const when = start
          ? `${start.toLocaleDateString("it-IT", { weekday: "short", day: "numeric", month: "short", year: "numeric" })} ${timeOf(start)}`
          : "—";
        panel.appendChild(
          el("button", {
            class: "search-hit",
            on: { click: () => this._openSearchBooking(appointment) },
          },
            el("span", { class: "dim small" }, `${when}${appointment.code ? " · " + appointment.code : ""}`),
            el("span", {},
              [
                appointment.client && appointment.client.full_name,
                appointment.treatment && appointment.treatment.name,
              ].filter(Boolean).join(" · ")))
        );
      });
      if (bookings.length > 40) {
        panel.appendChild(el("div", { class: "hint small" }, `Altri ${bookings.length - 40} risultati: scrivi di più per restringere.`));
      }
      return panel;
    }

    const canOpenClients = this._visibleTabs().some((tab) => tab.id === "clienti");
    const clients = (this._data.clients || []).filter((client) =>
      [client.first_name, client.last_name, client.full_name, client.phone, client.email]
        .filter(Boolean).join(" ").toLowerCase().includes(query));
    if (clients.length && canOpenClients) {
      clients.slice(0, 40).forEach((client) => {
        panel.appendChild(
          el("button", {
            class: "search-hit",
            on: { click: () => this._openSearchClient(client) },
          },
            el("span", {}, client.full_name || [client.first_name, client.last_name].filter(Boolean).join(" ") || "—"),
            el("span", { class: "dim small" }, [client.phone, client.email].filter(Boolean).join(" · ")))
        );
      });
      return panel;
    }
    panel.appendChild(el("div", { class: "hint" }, "Nessuna prenotazione o scheda cliente trovata."));
    return panel;
  }

  _openSearchBooking(appointment) {
    const start = parseDate(appointment.start);
    if (start) this._day = ymd(start);
    this._tab = "agenda";
    this._searchQuery = "";
    this._detailId = appointment.id;
    this._render();
  }

  _openSearchClient(client) {
    this._tab = "clienti";
    this._searchQuery = "";
    this._clientSelected = client && client.id;
    this._render();
  }

  _header() {
    // The title the reception wrote in Impostazioni wins; the card's own YAML
    // configuration is the fallback, and the built-in one the last resort.
    const settings = this._data && this._data.settings;
    const title = (settings && settings.card_title)
      || this._config.title
      || "Gestione SPA";
    const head = el("div", { class: "head" });
    head.appendChild(
      el(
        "button",
        {
          class: "icon-btn menu-btn",
          title: "Menu di Home Assistant",
          on: { click: () => this._toggleHaMenu() },
        },
        el("ha-icon", { icon: "mdi:menu" })
      ));
    head.appendChild(el("ha-icon", { class: "head-icon", icon: "mdi:spa-outline" }));
    head.appendChild(
      el(
        "div",
        { class: "head-text" },
        el("div", { class: "title" }, title)
      ));
    // Search: text input on desktop, magnifier icon on mobile. It sits just
    // left of the clock, so the running time stays the rightmost element.
    // No instant redraw while typing: rebuilding the header on every letter
    // steals the focus, the next keys land on Home Assistant and its popups
    // open. The search redraws debounced, then takes the focus back.
    const searchInput = el("input", {
      class: "input search-input",
      type: "search",
      placeholder: "Cerca codice, cliente, telefono",
      value: this._searchQuery || "",
      on: {
        input: (event) => {
          this._searchQuery = event.target.value;
          clearTimeout(this._searchTimer);
          this._searchTimer = setTimeout(() => {
            this._searchTimer = null;
            this._render();
            const node = this.shadowRoot && this.shadowRoot.querySelector(".search-input");
            if (node) {
              node.focus();
              const end = (node.value || "").length;
              try { node.setSelectionRange(end, end); } catch (err) { /* noop */ }
            }
          }, 250);
        },
        keydown: (event) => { event.stopPropagation(); },
        keyup: (event) => { event.stopPropagation(); },
        keypress: (event) => { event.stopPropagation(); },
      },
    });
    // Capture phase too: dashboard-level shortcut listeners never see keys
    // typed in the dashboard search.
    ["keydown", "keyup", "keypress"].forEach((type) =>
      searchInput.addEventListener(type, (event) => event.stopPropagation(), true));
    head.appendChild(searchInput);
    head.appendChild(
      el("button", {
        class: "icon-btn search-toggle",
        title: "Cerca",
        on: { click: () => {
          const query = prompt("Cerca per codice, cliente o telefono:", this._searchQuery || "");
          if (query !== null) { this._searchQuery = query.trim(); this._render(); }
        } },
      }, el("ha-icon", { icon: "mdi:magnify" })));
    // Bell: the requests that arrived from the website and nobody has opened
    // yet. Hidden for the accounts that cannot reach the request list at all.
    if (this._visibleNuovoTabs().some((tab) => tab.id === "lista")) {
      const unread = this._webUnreadCount();
      const bell = el("button", {
        class: "icon-btn notify-btn",
        title: unread
          ? `${unread} richieste dal sito non ancora viste`
          : "Richieste dal sito",
        on: { click: () => this._openWebRequests() },
      }, el("ha-icon", { icon: "mdi:bell-outline" }));
      if (unread) {
        bell.appendChild(el("span", { class: "notify-badge" }, String(unread)));
      }
      head.appendChild(bell);
    }
    head.appendChild(
      el(
        "div",
        { class: "clock" },
        el("div", { class: "clock-time" }, this._fmtTime()),
        el("div", { class: "clock-date" }, this._fmtDate())
      ));
    return head;
  }

  _tabs() {
    return el(
      "div",
      { class: "tabs" },
      this._visibleTabs().map((tab) =>
        el(
          "button",
          {
            class: `tab${this._tab === tab.id ? " active" : ""}`,
            title: tab.label,
            on: {
              click: () => {
                // Leaving the new-booking tab without saving empties the form.
                if (this._tab === "nuovo" && tab.id !== "nuovo") this._resetForm();
                // Leaving the voucher tab clears the draft form.
                if (this._tab === "voucher" && tab.id !== "voucher") this._voucherDraft = null;
                this._tab = tab.id;
                this._render();
              },
            },
          },
          el("ha-icon", { icon: tab.icon }),
          el("span", { class: "tab-label" }, tab.label)
        )
      )
    );
  }

  _messageBox() {
    // A success message clears itself after a few seconds; an error stays
    // until it is dismissed, because the desk has to read it.
    if (this._message.kind === "ok") {
      const key = this._message.text;
      if (this._messageTimerKey !== key) {
        if (this._messageTimer) clearTimeout(this._messageTimer);
        this._messageTimerKey = key;
        this._messageTimer = setTimeout(() => {
          this._message = null;
          this._messageTimer = null;
          this._messageTimerKey = null;
          this._render();
        }, 5000);
      }
    } else if (this._messageTimer) {
      clearTimeout(this._messageTimer);
      this._messageTimer = null;
      this._messageTimerKey = null;
    }
    return el(
      "div",
      { class: `msg ${this._message.kind}` },
      el("ha-icon", {
        icon: this._message.kind === "error" ? "mdi:alert-circle" : "mdi:check-circle",
      }),
      el("span", {}, this._message.text),
      el("button", { class: "icon-btn", on: { click: () => { this._message = null; this._render(); } } },
        el("ha-icon", { icon: "mdi:close" })
      )
    );
  }

  // ------------------------------------------------------------------ AGENDA

  /**
   * Agenda tab: the day list with a toggle button in the bar to switch
   * to the month calendar. On mobile the button stays in the bar.
   */
  _renderAgenda() {
    // Editing one appointment takes over the whole tab: the editor replaces
    // the bar too, so nothing can switch the page away from it.
    if (this._batchEditing) {
      return this._renderEditBatch();
    }
    if (this._editing && this._editing.kind === "appointment") {
      return this._renderEditAppointment();
    }
    const wrap = el("div", { class: "stack agenda" });

    // The view is stored in _agendaTab: "agenda" or "calendario".
    const showCalendar = this._agendaTab === "calendario";

    if (showCalendar) {
      add(wrap, this._renderCalendar());
    } else {
      add(wrap, this._renderAgendaDay());
    }
    return wrap;
  }

  /** Agenda sub-tab: the working day, hour by hour, in user order. */
  _renderAgendaDay() {
    const wrap = el("div", { class: "stack" });
    const day = new Date(`${this._day}T00:00:00`);
    const dayList = this._appointmentsOfDay(this._day).filter(
      (appointment) =>
        this._categoryMatch(appointment) && this._guestMatch(appointment) &&
        this._matchesSearch(appointment));
    // Once the reception has recorded the exit the appointment is over: it
    // leaves the working agenda and folds into the "Usciti" section below.
    const exited = dayList.filter((appointment) => appointment.checked_out);
    const allActive = dayList.filter((appointment) => !appointment.checked_out);
    const list = this._showCheckedIn ? allActive : allActive.filter((appointment) => !appointment.checked_in);
    const totalMin = list.reduce((sum, item) => sum + (this._durationOf(item) || 0), 0);

    const categoryChips = this._categoryChips();
    const guestChips = this._guestChips();

    // One row that never wraps: Oggi, the day arrows, then the two actions
    // (print and new). The category and guest chips move to their own row
    // below, so the bar itself always fits on a phone.
    wrap.appendChild(
      el(
        "div",
        { class: "row agenda-bar" },
        // Calendario toggle button: left of Oggi. Shows opposite view name.
        el("button", {
          class: `btn primary small agenda-toggle`,
          on: { click: () => { this._agendaTab = this._agendaTab === "agenda" ? "calendario" : "agenda"; this._render(); } },
        },
          el("ha-icon", { icon: this._agendaTab === "agenda" ? "mdi:calendar-month" : "mdi:view-day" }),
          el("span", { class: "btn-label" }, this._agendaTab === "agenda" ? "Calendario" : "Agenda")
        ),
        el("button", {
          class: "btn small",
          on: { click: () => { this._day = todayStr(); this._render(); } },
        }, "Oggi"),
        el(
          "button",
          { class: "icon-btn", on: { click: () => { this._day = ymd(addDays(day, -1)); this._render(); } } },
          el("ha-icon", { icon: "mdi:chevron-left" })
        ),
        el("input", {
          class: "date-input",
          type: "date",
          value: this._day,
          on: { change: (event) => { this._day = event.target.value || todayStr(); this._render(); } },
        }),
        el(
          "button",
          { class: "icon-btn", on: { click: () => { this._day = ymd(addDays(day, 1)); this._render(); } } },
          el("ha-icon", { icon: "mdi:chevron-right" })
        ),
        el("button", {
          class: "btn small",
          title: "Stampa PDF",
          on: { click: () => this._printDay() },
        }, el("ha-icon", { icon: "mdi:printer" }),
          el("span", { class: "btn-label" }, "Stampa PDF")),
        el("button", {
          class: "btn primary small",
          title: "Nuovo",
          disabled: this._busy,
          style: this._can("book") ? null : "display: none",
          on: {
            click: () => {
              this._form.date = this._day;
              this._tab = "nuovo";
              this._nuovoTab = "appuntamento";
              this._render();
            },
          },
        }, el("ha-icon", { icon: "mdi:plus" }),
          el("span", { class: "btn-label" }, "Nuovo"))
      )
    );

    // The filters have their own row: they can wrap freely without moving
    // the bar above.
    if (categoryChips.length || guestChips.length) {
      wrap.appendChild(
        el("div", { class: "row tight agenda-filters" },
          ...categoryChips,
          ...guestChips)
      );
    }

    wrap.appendChild(el("div", { class: "day-title" }, longDay(day)));

    // Today only: the clients leaving now or shortly, so the reception can
    // confirm each exit while it happens (or shortly after).
    if (this._day === todayStr()) {
      const exits = this._exitAppointments(list);
      if (exits.length) {
        const panel = el("div", { class: "exit-panel" });
        panel.appendChild(
          el("div", { class: "exit-head" },
            el("ha-icon", { icon: "mdi:exit-run" }),
            el("span", {}, `Uscite (${EXIT_LEAD_MIN}′ prima / ${EXIT_GRACE_MIN}′ dopo)`),
            el("span", { class: "badge" }, String(exits.length)))
        );
        exits.forEach((appointment) => {
          const end = parseDate(appointment.end);
          panel.appendChild(
            el("div", { class: "exit-row" },
              el("span", { class: "exit-time" }, end ? timeOf(end) : "—"),
              el("span", { class: "grow" },
                this._clientName(appointment),
                el("span", { class: "sep" }, "·"),
                el("span", { class: "dim" }, this._treatmentName(appointment))),
              el("button", {
                class: "btn small",
                disabled: this._busy,
                style: this._can("day") ? null : "display: none",
                on: { click: () => this._confirmExit(appointment) },
              }, "Conferma uscita"))
          );
        });
        wrap.appendChild(panel);
      }
    }

    if (!dayList.length) {
      wrap.appendChild(el("div", { class: "empty" }, "Nessun appuntamento per questa data."));
    } else if (!list.length) {
      wrap.appendChild(
        el("div", { class: "row", style: "margin: 6px 0 10px 0; align-items: center; gap: 8px;" },
          el("span", { class: "dim", style: "font-size: 13px;" }, "Mostra check-in"),
          el("button", {
            class: "btn small",
            style: "background: #009ac7; color: #fff;",
            title: this._showCheckedIn ? "Nascondi check-in" : "Mostra check-in",
            on: { click: () => { this._showCheckedIn = !this._showCheckedIn; this._render(); } },
          }, el("ha-icon", { icon: this._showCheckedIn ? "mdi:close" : "mdi:check" })))
      );
      wrap.appendChild(el("div", { class: "empty" },
        "Tutti gli appuntamenti di oggi hanno registrato l'uscita."));
    } else {
      // Appointments per starting hour, so the desk reads at a glance how the
      // day is spread and where the next booking lands.
      const byHour = new Map();
      list.forEach((appointment) => {
        const start = parseDate(appointment.start);
        if (!start) return;
        const hour = start.getHours();
        byHour.set(hour, (byHour.get(hour) || 0) + 1);
      });
      const hours = [...byHour.keys()].sort((a, b) => a - b);

      wrap.appendChild(
        el(
          "div",
          { class: "meta" },
          el("span", {},
            `${list.length} ${list.length === 1 ? "appuntamento" : "appuntamenti"} · ${minutesLabel(totalMin)}`),
          hours.length
            ? el("span", { class: "meta-hours" },
                hours.map((hour) => `${pad(hour)}:00 ×${byHour.get(hour)}`).join("  ·  "))
            : null
        )
      );

      // Toggle to show/hide the appointments that already checked in.
      wrap.appendChild(
        el("div", { class: "row", style: "margin: 6px 0 0 0; align-items: center; gap: 8px;" },
          el("span", { class: "dim", style: "font-size: 13px;" },
            "Mostra check-in"),
          el("button", {
            class: "btn small",
            style: "background: #009ac7; color: #fff;",
            title: this._showCheckedIn ? "Nascondi check-in" : "Mostra check-in",
            on: { click: () => { this._showCheckedIn = !this._showCheckedIn; this._render(); } },
          },
            el("ha-icon", { icon: this._showCheckedIn ? "mdi:close" : "mdi:check" }))
        )
      );

      // One row per booking group (same treatment, client and slot): the
      // members are identical, so the row stands for the whole party and a
      // button next to the pencil opens the single rows underneath. A lone
      // booking is just its own row.
      const bookingGroups = [];
      const seen = new Map();
      list.forEach((appointment) => {
        const key = [
          appointment.treatment_id,
          appointment.client_id,
          appointment.start,
          appointment.operator_id || "",
        ].join("|");
        if (!seen.has(key)) {
          seen.set(key, []);
          bookingGroups.push(seen.get(key));
        }
        seen.get(key).push(appointment);
      });

      const groups = new Map();
      bookingGroups.forEach((members) => {
        const key = members[0].operator_id || "__none__";
        if (!groups.has(key)) groups.set(key, []);
        groups.get(key).push(members);
      });

      if (!this._expandedGroups) this._expandedGroups = new Set();

      // Two columns: massages (treatments that need an operator) on the right,
      // everything else on the left.
      const columns = el("div", { class: "agenda-columns" });
      const leftCol = el("div", { class: "agenda-column" });
      const rightCol = el("div", { class: "agenda-column" });

      [...groups.entries()].forEach(([key, partyList]) => {
        const operator = this._lookup.operator.get(key);
        const treatment = this._lookup.treatment.get(partyList[0][0].treatment_id);
        const category = this._categoryOf(treatment);
        const target = category && category.requires_operator ? rightCol : leftCol;
        const card = el("div", { class: "group" });
        card.appendChild(
          el(
            "div",
            { class: "group-head" },
            el("ha-icon", { icon: operator ? "mdi:account-voice" : "mdi:account-off-outline" }),
            el("span", {}, operator ? operator.name : "Senza operatore"),
            el("span", { class: "badge" },
              String(partyList.reduce((sum, members) => sum + members.length, 0)))
          )
        );
        partyList.forEach((members) => {
          add(card, this._appointmentRow(members[0]));
          const groupKey = [
            members[0].treatment_id,
            members[0].client_id,
            members[0].start,
            members[0].operator_id || "",
          ].join("|");
          if (members.length > 1 && this._expandedGroups.has(groupKey)) {
            members.slice(1).forEach((appointment) =>
              add(card, this._appointmentRow(appointment)));
          }
        });
        target.appendChild(card);
      });

      columns.appendChild(leftCol);
      columns.appendChild(rightCol);
      wrap.appendChild(columns);
    }

    // Clients already gone: kept out of the working list, but still one click
    // away with their time, so a late correction can still be made.
    if (exited.length) {
      wrap.appendChild(
        el("details", { class: "exited-box" },
          el("summary", {}, `Usciti (${exited.length})`),
          exited.map((appointment) => this._appointmentRow(appointment))
        )
      );
    }

    const past = (this._byDay.get(this._day) || []).filter(
      (appointment) =>
        appointment.status === "cancelled" &&
        this._categoryMatch(appointment) &&
        this._guestMatch(appointment)
    );
    if (past.length) {
      wrap.appendChild(
        el("details", { class: "cancelled-box" },
          el("summary", {}, `Annullati (${past.length})`),
          past.map((appointment) => this._appointmentRow(appointment, true))
        )
      );
    }

    return wrap;
  }

  /** Category filter chips shown next to "Oggi"; "" = no filter. */
  _categoryChips() {
    // Only the categories that actually have an appointment that day: a chip
    // that filters to nothing is noise. The day's list is unfiltered here, so
    // every category present shows even while another filter is active.
    const present = new Set();
    this._appointmentsOfDay(this._day).forEach((appointment) => {
      const treatment = this._lookup.treatment.get(appointment.treatment_id);
      const category = this._categoryOf(treatment);
      if (category) present.add(category.id);
    });
    if (!present.size) return [];
    const categories = [...this._data.categories]
      .filter((category) => present.has(category.id))
      .sort((a, b) => a.name.localeCompare(b.name));
    const build = (label, value) =>
      el("button", {
        class: `fchip${this._categoryFilter === value ? " active" : ""}`,
        on: {
          click: () => {
            this._categoryFilter = this._categoryFilter === value ? "" : value;
            this._render();
          },
        },
      }, label);
    const chips = [build("Tutte", "")];
    categories.forEach((category) => chips.push(build(category.name, category.id)));
    return chips;
  }

  /** Whether an appointment belongs to the active category filter. */
  _categoryMatch(appointment) {
    if (!this._categoryFilter) return true;
    const treatment = this._lookup.treatment.get(appointment.treatment_id);
    const category = treatment ? this._categoryOf(treatment) : null;
    return Boolean(category && category.id === this._categoryFilter);
  }

  /** The guest flag of an appointment, anything unknown reading as external. */
  _guestMeta(id) {
    return GUEST_TYPES.find((entry) => entry.id === id) || GUEST_TYPES[1];
  }

  /** Whether an appointment belongs to the active hotel/external filter. */
  _guestMatch(appointment) {
    if (!this._guestFilter) return true;
    return (appointment.guest_type || GUEST_DEFAULT) === this._guestFilter;
  }

  /** Hotel / external icon chips shown next to the category filters. */
  _guestChips() {
    // Same rule as the categories: only the guest types present that day.
    const present = new Set();
    this._appointmentsOfDay(this._day).forEach((appointment) =>
      present.add(appointment.guest_type || GUEST_DEFAULT));
    return GUEST_TYPES
      .filter((entry) => present.has(entry.id))
      .map((entry) =>
        el("button", {
          class: `fchip${this._guestFilter === entry.id ? " active" : ""}`,
          title: entry.label,
          on: {
            click: () => {
              this._guestFilter = this._guestFilter === entry.id ? "" : entry.id;
              this._render();
            },
          },
        }, el("ha-icon", { icon: entry.icon }))
      );
  }

  /** The hotel/external toggle shared by the new-booking and edit forms. */
  _guestField(target) {
    return el("div", { class: "field" },
      el("span", {}, "Ospite"),
      el("div", { class: "role-choice" },
        GUEST_TYPES.map((choice) =>
          el("button", {
            type: "button",
            class: `role-opt${(target.guest_type || GUEST_DEFAULT) === choice.id ? " on" : ""}`,
            title: choice.label,
            on: { click: () => { target.guest_type = choice.id; this._render(); } },
          },
            el("ha-icon", { icon: choice.icon }),
            choice.label))));
  }

  /**
   * A price as a number, the comma accepted the way the integration accepts
   * it, and anything unreadable as null (the price is informational only).
   */
  _accPrice(value) {
    if (value === null || value === undefined || value === "") return null;
    const num = Number(String(value).trim().replace(",", "."));
    return Number.isFinite(num) ? num : null;
  }

  /**
   * The accessories configured in the Accessori tab, normalised to objects.
   * Read from settings.accessories; until the settings have loaded (or while
   * the key has never been saved) the factory list stands in, so the booking
   * form is never left without accessories.
   */
  _accessories() {
    const settings = (this._data && this._data.settings) || {};
    const raw = Array.isArray(settings.accessories) ? settings.accessories : null;
    const seen = new Set();
    const out = [];
    (raw === null ? ACC_FALLBACK : raw).forEach((item) => {
      const entry = typeof item === "string" ? { id: item } : item;
      if (!entry || typeof entry !== "object") return;
      const id = String(entry.id || "").trim();
      if (!id || seen.has(id)) return;
      seen.add(id);
      out.push({
        id,
        label: String(entry.label || id).trim() || id,
        icon: String(entry.icon || ACC_DEFAULT_ICON).trim() || ACC_DEFAULT_ICON,
        price: this._accPrice(entry.price),
        description: String(entry.description || "").trim(),
      });
    });
    return out;
  }

  /**
   * One accessory by id. The configured list comes first; an accessory that
   * has since been deleted keeps the last known name (settings
   * accessory_labels), so an appointment that still carries it is never left
   * with a bare id.
   */
  _accessory(id) {
    const key = String(id || "");
    const found = this._accessories().find((entry) => entry.id === key);
    if (found) return found;
    const labels = ((this._data && this._data.settings) || {}).accessory_labels || {};
    return {
      id: key,
      label: String(labels[key] || key),
      icon: ACC_DEFAULT_ICON,
      price: null,
      description: "",
    };
  }

  /** The name of one accessory: configured, else its last known name. */
  _accessoryLabel(id) {
    return this._accessory(id).label;
  }

  /**
   * The accessories of one person: every configured accessory is its own
   * toggle, so the chosen ones have an icon each. Shared by the new-booking
   * and edit forms; a multi-person booking keeps a separate set per person.
   * An accessory deleted from the configuration but already on this
   * appointment is still shown, so it can be taken off.
   */
  _extrasField(target) {
    const chosen = new Set(target.extras || []);
    const entries = this._accessories();
    (target.extras || []).forEach((id) => {
      if (!entries.some((entry) => entry.id === id)) entries.push(this._accessory(id));
    });
    return el("div", { class: "field" },
      el("span", {}, "Accessori"),
      el("div", { class: "role-choice" },
        entries.map((entry) =>
          el("button", {
            type: "button",
            class: `role-opt${chosen.has(entry.id) ? " on" : ""}`,
            title: entry.price === null
              ? entry.label
              : `${entry.label} · ${euro(entry.price)}`,
            on: {
              click: () => {
                const next = new Set(target.extras || []);
                if (next.has(entry.id)) next.delete(entry.id);
                else next.add(entry.id);
                // The backend wants a plain list: send the chosen id order as
                // configured, not as clicked.
                target.extras = entries
                  .map((item) => item.id)
                  .filter((id) => next.has(id));
                this._render();
              },
            },
          },
            el("ha-icon", { icon: entry.icon }),
            entry.label))));
  }

  /** Whether an appointment starts today (local time). */
  _isToday(appointment) {
    const start = parseDate(appointment.start);
    return Boolean(start) && ymd(start) === todayStr();
  }

  /**
   * Today's confirmed appointments ending within the next 15 minutes: the
   * clients the reception is about to greet out. Already confirmed exits are
   * left out, so each row disappears once recorded.
   */
  /**
   * Confirmed appointments whose exit is being handled right now: the panel
   * opens 15 minutes before they end and stays open 30 minutes after, so a
   * receptionist can record the entry on time and still log a late exit.
   * Appointments already confirmed are left out, so a row disappears the
   * moment the exit is recorded.
   */
  _exitAppointments(list) {
    const now = Date.now();
    return list.filter((appointment) => {
      if (appointment.status !== "confirmed" || appointment.checked_out) return false;
      const end = parseDate(appointment.end);
      if (!end) return false;
      // Positive delta: it ends within the next EXIT_LEAD_MIN minutes.
      // Negative delta: it ended at most EXIT_GRACE_MIN minutes ago.
      const delta = end.getTime() - now;
      return delta >= -EXIT_GRACE_MIN * 60 * 1000 && delta <= EXIT_LEAD_MIN * 60 * 1000;
    });
  }

  /**
   * Everything about one appointment, over the agenda.
   *
   * The row is a summary for scanning; this is the record. It carries the
   * payment in words and figures because the row's icons deliberately say only
   * the shape of the payment, not the amounts. It is drawn on top rather than
   * in the flow so the reader does not lose their place in the day, and the
   * backdrop closes it the way a sheet is expected to close.
   */
  _renderDetail() {
    const appointment = this._lookup.appointment.get(this._detailId);
    if (!appointment) return null;

    const start = parseDate(appointment.start);
    const end = parseDate(appointment.end);
    const client = this._lookup.client.get(appointment.client_id);
    const treatment = this._lookup.treatment.get(appointment.treatment_id);
    const category = this._categoryOf(treatment);
    const cancelled = appointment.status === "cancelled";
    const group = this._groupOf(appointment);
    const guest = this._guestMeta(appointment.guest_type);

    const section = (title, ...rows) =>
      rows.some(Boolean)
        ? el("div", { class: "detail-section" },
            el("h4", {}, title),
            el("div", { class: "detail-rows" }, rows.filter(Boolean)))
        : null;

    // Which view the popup is rendering right now drives the totals and the
    // (optional) grouped listing below. "single" keeps the existing
    // one-appointment behaviour; "grouped" sums every related appointment.
    const grouped = this._detailView === "grouped";
    const related = this._relatedOf(appointment);
    const groupTotals = grouped ? this._relatedTotals(appointment) : null;

    // The agreed price of this person, per head: a group charges it once per
    // person, so the total below is the count times this figure.
    const own = this._lineBreakdown(appointment);
    const price =
      own.price > 0
        ? `${euro(own.price)}${group.length > 1 ? " a persona" : ""}`
        : null;

    const sheet = el("div", {
      class: "detail-sheet",
      role: "dialog",
      "aria-modal": "true",
      "aria-label": `Dettagli ${this._clientName(appointment)}`,
    });

    sheet.appendChild(
      el("div", { class: "detail-head" },
        el("div", {},
          el("div", { class: "detail-title" }, this._clientName(appointment)),
          el("div", { class: "detail-sub" },
            `${this._treatmentName(appointment)} · ${longDay(start)}`)),
        el("div", { class: "detail-toggle" },
          el("button", {
            class: `btn small ${this._detailView === "grouped" ? "active" : ""}`,
            title: this._detailView === "grouped" ? "Mostra vista singola" : "Mostra vista raggruppata",
            disabled: this._busy,
            on: { click: () => { this._detailView = this._detailView === "grouped" ? "single" : "grouped"; this._render(); } },
          },
            el("ha-icon", { style: "--mdc-icon-size: 20px; --ha-icon-size: 20px; width: 20px; height: 20px;", icon: this._detailView === "grouped" ? "mdi:view-list-outline" : "mdi:view-day" }),
            el("span", { class: "btn-label" }, this._detailView === "grouped" ? "Singola" : "Raggruppata"))),
        el("button", {
          class: "icon-btn",
          title: "Chiudi",
          on: { click: () => this._closeDetail() },
        }, el("ha-icon", { icon: "mdi:close" })))
    );

    sheet.appendChild(
      section(
        "Quando",
        this._detailLine("Inizio", start ? timeOf(start) : "—"),
        this._detailLine("Fine", end ? timeOf(end) : "—"),
        this._detailLine("Durata", minutesLabel(this._durationOf(appointment)) || "—"),
        this._detailLine(
          "Stato",
          cancelled
            ? el("span", { class: "detail-value due" }, "Annullato")
            : appointment.status === "pending"
              ? el("span", { class: "detail-value pending" }, "In attesa di conferma")
              : el("span", { class: "detail-value ok" }, "Confermato")
        ),
        this._detailLine(
          "Ospite",
          el("span", { class: `detail-guest ${guest.id}` },
            el("ha-icon", { icon: guest.icon }),
            guest.label)
        ),
        appointment.confirmed_by
          ? this._detailLine("Confermato da", appointment.confirmed_by)
          : null,
        appointment.confirmed_at
          ? this._detailLine(
              "Confermato il",
              `${shortDate(appointment.confirmed_at)} ${timeOf(parseDate(appointment.confirmed_at))}`
            )
          : null,
        this._detailLine("Entrata", appointment.checked_in ? "registrata" : "non registrata"),
        this._detailLine("Uscita", appointment.checked_out ? "registrata" : "non registrata")
      )
    );

    sheet.appendChild(
      section(
        "Trattamento",
        this._detailLine("Trattamento", this._treatmentName(appointment)),
        this._detailLine("Categoria", category ? category.name : "—"),
        this._detailLine("Prezzo", price || "—"),
        this._detailLine("Operatrice", this._operatorName(appointment) || "nessuna"),
        (() => {
          const op = this._lookup.operator.get(appointment.operator_id);
          if (!op) return null;
          const role = roleOf(op);
          return this._detailLine(
            "Ruolo",
            el("span", { class: `detail-role ${op.role === "spa_manager" ? "mgr" : "mass"}` },
              el("ha-icon", { icon: role.icon }),
              role.label)
          );
        })(),
        (category && category.requires_operator && appointment.operator_id && !cancelled
          && this._can("offers"))
          ? this._detailLine(
              "Conferma",
              el("button", {
                class: `btn small ${appointment.offer_state === "offered" ? "offer-wait" : "offer-ok"}`,
                disabled: this._busy,
                on: {
                  click: (event) => {
                    event.stopPropagation();
                    if (appointment.offer_state === "offered") {
                      // Manual confirm: the operator confirmed by phone, not
                      // via WhatsApp/Telegram. The reception confirms by hand.
                      this._call("manual_confirm_offer", {
                        appointment_id: appointment.id,
                      });
                    } else {
                      // Toggle back to pending (undo confirmation)
                      this._toggleOffer(appointment, true);
                    }
                  },
                },
              },
              el("ha-icon", { icon: "mdi:check-all" }),
              appointment.offer_state === "offered" ? "Conferma" : "Confermato")
            )
          : null,
        // Deposit request: ask the guest to pay her deposit by bank transfer.
        // Only a still-waiting booking that expects a deposit (amount set, no
        // money received yet) and has not already been asked qualifies.
        (!cancelled
          && appointment.status === "pending"
          && this._can("offers")
          && !this._paymentReceived(appointment)
          && (appointment.deposit_amount > 0)
          && !appointment.deposit_request_sent
          && appointment.client && appointment.client.phone)
          ? this._detailLine(
              "Acconto",
              el("button", {
                class: "btn small offer-wait",
                disabled: this._busy,
                on: {
                  click: (event) => {
                    event.stopPropagation();
                    this._call("send_deposit_request", {
                      appointment_id: appointment.id,
                    });
                  },
                },
              },
              el("ha-icon", { icon: "mdi:bank-transfer" }),
              "Richiedi acconto")
            )
          : null,
        // Appointment summary: send it by hand at any time, e.g. when the desk
        // confirmed by phone and the guest asks for the details in writing.
        (!cancelled
          && this._can("offers")
          && appointment.client && appointment.client.phone)
          ? this._detailLine(
              "Riepilogo",
              el("button", {
                class: "btn small",
                disabled: this._busy,
                on: {
                  click: (event) => {
                    event.stopPropagation();
                    this._call("send_guest_summary", {
                      appointment_id: appointment.id,
                    });
                  },
                },
              },
              el("ha-icon", { icon: "mdi:whatsapp" }),
              "Invia riepilogo")
            )
          : null,
        group.length > 1
          ? this._detailLine("Persone nella fascia", String(group.length))
          : null,
        appointment.offer_state === "offered"
          ? this._detailLine("Proposta", "in attesa di conferma")
          : null,
        appointment.offer_state === "unassigned"
          ? this._detailLine("Proposta", "da assegnare")
          : null,
        appointment.checked_in && appointment.checked_in_at
          ? this._detailLine("Entrata", timeOf(new Date(appointment.checked_in_at)))
          : null,
        appointment.checked_out && appointment.checked_out_at
          ? this._detailLine("Uscita", timeOf(new Date(appointment.checked_out_at)))
          : null
      )
    );

    const extras = (appointment.extras || [])
      .map((id) => this._accessory(id));

    add(
      sheet,
      section(
        "Accessori",
        extras.length
          ? this._detailLine(
              "Accessori",
              el("span", { class: "detail-extras" },
                extras.map((entry) =>
                  el("span", { class: "extra-pill" },
                    el("ha-icon", { icon: entry.icon }),
                    entry.label)))
            )
          : this._detailLine("Accessori", "nessuno")
      )
    );

    // The old Pagamento flags live on in the data, but the popup shows the
    // new register instead: totals and takings with their payment ways. The
    // figures cover the whole party, takings included wherever they were
    // registered, so a two-people booking never reads a one-person total.
    const totals = grouped
      ? this._relatedTotals(appointment)
      : (related.length > 1 ? this._appointmentTotals(appointment) : this._singleTotals(appointment));
    const { total, collected, due, persons } = totals;
    const takingRows = (grouped ? related : (related.length > 1 ? this._groupOf(appointment) : [appointment])).flatMap((member) =>
      (member.payments || []).map((item) => {
        const method = PAYMENT_METHODS.find(({ id }) => id === item.method) || {};
        return this._detailLine(
          method.label || item.method,
          `${item.date || "—"} · ${euro(item.amount)}`);
      }));
    sheet.appendChild(
      section(
        grouped ? "Totali gruppo" : "Totali e incassi",
        related.length > 1
          ? this._detailLine("Appuntamenti nel gruppo", String(related.length))
          : null,
        persons > 1
          ? this._detailLine("Persone", String(persons))
          : null,
        this._detailLine(grouped ? "Totale gruppo" : "Totale", euro(total), due <= 0 ? "ok" : "due"),
        ...(takingRows.length ? takingRows : [this._detailLine("Incassi", "nessun incasso")]),
        this._detailLine("Totale incassato", euro(collected), collected > 0 ? "ok" : null),
        this._detailLine("Totale da incassare", euro(due), due > 0 ? "due" : "ok")
      )
    );

    if (grouped && related.length > 1) {
      const listEl = el("div", { class: "detail-group-list" });
      related.forEach((member) => {
        const startM = parseDate(member.start);
        const endM = parseDate(member.end);
        const priceM = this._lineBreakdown(member).price;
        const bits = [
          `${timeOf(startM)}-${timeOf(endM)} ${this._treatmentName(member)}`,
        ];
        if (member.client_id && member.client_id !== appointment.client_id) bits.push(` (${this._clientName(member)})`);
        if (priceM > 0) bits.push(` - ${euro(priceM)}`);
        if (member.status === "pending") bits.push(" (in attesa)");
        if (member.status === "cancelled") bits.push(" (annullato)");
        const row = el("div", { class: "detail-line" }, bits.join(""));
        const editable = this._can("book") && member.status !== "cancelled";
        if (editable) {
          row.appendChild(el("button", {
            class: "btn small",
            title: "Modifica questo sotto-appuntamento",
            disabled: this._busy,
            on: { click: (event) => { event.stopPropagation(); this._closeAnd(() => this._openEditAppointment(member)); } },
          }, el("ha-icon", { icon: "mdi:pencil" }), el("span", { class: "btn-label" }, "Modifica")));
        }
        listEl.appendChild(row);
      });
      add(sheet, section("Appuntamenti del gruppo", listEl));
    }

    const clientRows = [];
    if (client && client.phone) {
      clientRows.push(this._detailLine("Telefono", client.phone));
    }
    if (client && client.email) {
      clientRows.push(this._detailLine("Email", client.email));
    }
    // add(), not appendChild: a section with nothing in it returns null, and
    // appending null throws. This is the same trap as the group stepper.
    add(sheet, section("Cliente", ...clientRows));
    add(
      sheet,
      section(
        "Note",
        appointment.notes ? el("div", { class: "detail-text" }, appointment.notes) : null,
        cancelled && appointment.cancel_reason
          ? this._detailLine("Motivo annullamento", appointment.cancel_reason)
          : null
      )
    );

    // The same actions as on the row, so the popup is a shortcut and not a
    // second, different way of working.
    const actions = el("div", { class: "detail-actions" });
    if (grouped && related.length > 1 && this._can("book")) {
      actions.appendChild(el("button", {
        class: "btn primary",
        disabled: this._busy,
        on: { click: () => this._closeAnd(() => this._openEditBatch(appointment)) },
      }, el("ha-icon", { style: "--mdc-icon-size: 20px; --ha-icon-size: 20px; width: 20px; height: 20px;", icon: "mdi:pencil" }),
      el("span", { class: "btn-label" }, "Modifica gruppo")));
    }
    const phone = client ? client.phone : "";
    const whatsapp = waLink(phone);
    // Management buttons follow the same rule as the row: operators and above.
    const canBook = this._can("book");
    if (canBook && !cancelled) {
      // Waiting: confirming comes first here too, for the same reason.
      if (appointment.status === "pending") {
        actions.appendChild(
          el("button", {
            class: "btn primary",
            disabled: this._busy,
            on: { click: () => this._closeAnd(() => this._confirmAppointment(appointment)) },
          }, "Conferma")
        );
      }
      if (
        this._isToday(appointment) &&
        appointment.status === "confirmed" &&
        !appointment.checked_in
      ) {
        actions.appendChild(
          el("button", {
            class: "btn small",
            disabled: this._busy,
            on: { click: () => this._closeAnd(() => this._confirmEntry(appointment)) },
          }, "Registra entrata")
        );
      }
      if (appointment.checked_in && !appointment.checked_out) {
        // The exit follows the entry: a client leaves after arriving, and the
        // "Uscite" panel counts what is recorded here. Offering it the other way
        // round would let the desk close an appointment that never opened.
        actions.appendChild(
          el("button", {
            class: "btn small",
            disabled: this._busy,
            on: { click: () => this._closeAnd(() => this._confirmExit(appointment)) },
          }, "Registra uscita")
        );
        // Once the entry is recorded, a wrong one can be taken back — but only
        // before the exit, because the exit closes the visit.
        actions.appendChild(
          el("button", {
            class: "btn small",
            disabled: this._busy,
            on: {
              click: () =>
                this._closeAnd(() => this._confirmEntry(appointment, false)),
            },
          }, "Cancella entrata")
        );
      }
      actions.appendChild(
        el("button", {
          class: "btn primary",
          disabled: this._busy,
          on: {
            click: () => this._closeAnd(() => this._openEditAppointment(appointment)),
          },
        }, "Modifica")
      );
      // Richiesta recensione: presente su ogni appuntamento non annullato. Se
      // la richiesta è già partita il pulsante cambia aspetto e si disattiva,
      // e la stella appare anche sulla riga dell'agenda.
      actions.appendChild(
        appointment.review_request_sent
          ? el("button", {
              class: "btn small review-sent",
              disabled: true,
              title: "Richiesta recensione già inviata",
            }, el("ha-icon", { icon: "mdi:star" }), "Recensione inviata")
          : el("button", {
              class: "btn small",
              disabled: this._busy || !whatsapp,
              title: whatsapp
                ? "Invia la richiesta di recensione a questo cliente"
                : "Il cliente non ha un numero WhatsApp valido",
              on: {
                click: () => this._closeAnd(() => this._sendReviewRequest(appointment)),
              },
            }, el("ha-icon", { icon: "mdi:star-outline" }), "Invia recensione")
      );
      actions.appendChild(
        el("button", {
          class: "btn danger",
          disabled: this._busy,
          on: { click: () => this._closeAnd(() => this._confirmCancel(appointment)) },
        }, "Annulla")
      );
    } else if (canBook) {
      actions.appendChild(
        el("button", {
          class: "btn danger",
          disabled: this._busy,
          on: {
            click: () => this._closeAnd(() => this._confirmDeleteAppointment(appointment)),
          },
        }, "Elimina definitivamente")
      );
    }
    // Contacts on the right, icon-only coloured buttons: WhatsApp keeps its
    // own green, the phone takes the card's primary colour.
    if (phone || whatsapp) {
      const contacts = el("div", { class: "detail-contacts" });
      if (phone) {
        contacts.appendChild(
          el("a", { class: "btn tel", href: telHref(phone), title: phone },
            el("ha-icon", { icon: "mdi:phone" }))
        );
      }
      if (whatsapp) {
        contacts.appendChild(
          el("a", { class: "btn wa", href: whatsapp, target: "_blank", rel: "noopener", title: "WhatsApp" },
            el("ha-icon", { icon: "mdi:whatsapp" }))
        );
      }
      actions.appendChild(contacts);
    }
    sheet.appendChild(actions);

    return el("div", {
      class: "detail-backdrop",
      on: { click: (event) => {
        // Only a tap on the backdrop itself closes it, never one inside.
        if (event.target === event.currentTarget) this._closeDetail();
      } },
    }, sheet);
  }

  /** Close the popup, then run something that redraws on its own. */
  _closeAnd(action) {
    this._detailId = null;
    action();
  }

  /**
   * Tapping the body of a row opens everything about that appointment.
   *
   * The row is a one-line summary meant for scanning; the popup is where the
   * facts live, including the payment figures the icons deliberately leave out.
   * Reachable from the keyboard too, because a desk tablet often is.
   */
  _openDetail(appointment) {
    this._detailId = appointment.id;
    this._detailView = "single";
    this._render();
  }

  _closeDetail() {
    this._detailId = null;
    this._render();
  }

  /** The body of a row, which is the tap target that opens the popup. */
  _rowTappable(appointment, ...children) {
    return el("div", {
      class: "appt-main",
      role: "button",
      tabindex: "0",
      title: "Dettagli appuntamento",
      on: {
        click: () => this._openDetail(appointment),
        keydown: (event) => {
          if (event.key === "Enter" || event.key === " ") {
            event.preventDefault();
            this._openDetail(appointment);
          }
        },
      },
    }, children);
  }

  /** Send the review request for one appointment, from the popup button. */
  async _sendReviewRequest(appointment) {
    this._busy = true;
    this._render();
    try {
      const response = await this._service("send_review_requests", {
        appointment_id: appointment.id,
      });
      const sent = (response && response.sent) || 0;
      const failed = (response && response.failed) || 0;
      this._message = {
        kind: sent ? "ok" : "error",
        text: sent
          ? "Richiesta recensione inviata via WhatsApp."
          : failed
            ? "Invio non riuscito: controlla il numero WhatsApp del cliente."
            : "Nessun invio: il cliente non ha un numero WhatsApp valido.",
      };
    } catch (error) {
      this._message = { kind: "error", text: this._friendlyError(error, "Invio non riuscito.") };
    } finally {
      this._busy = false;
      await this._loadData();
      this._render();
    }
  }

  async _confirmEntry(appointment, value = true) {
    try {
      await this._call("check_in_appointment", {
        appointment_id: appointment.id,
        checked_in: value,
      });
    } catch (error) {
      /* message already shown */
    }
  }

  async _confirmExit(appointment) {
    try {
      await this._call("check_out_appointment", { appointment_id: appointment.id });
    } catch (error) {
      /* message already shown */
    }
  }

  /**
   * Who is pressing, read from the Home Assistant session.
   *
   *
   * The confirmer is a member of staff, not one of the masseuses, so their name
   * is not in the operator list: it comes from whoever is signed in. That only
   * tells the truth if every member of staff has an account of their own — on
   * a shared tablet the name recorded will be the account's, not the person's.
   */
  _confirmerName() {
    const user = this._hass && this._hass.user;
    if (!user) return "";
    return String(user.name || "").trim();
  }

  /**
   * Turn a waiting booking into a confirmed one, and sign it.
   *
   * The name is not typed: it is who is logged in. If there is no session at
   * all the booking is still confirmed, because refusing to confirm would be
   * worse than confirming without a signature.
   */
  async _confirmAppointment(appointment, force = false) {
    const who = this._confirmerName();
    try {
      // _call reloads the data and shows its own message, so the confirmation
      // is silent here rather than overwritten by a second one.
      await this._call("update_appointment", {
        appointment_id: appointment.id,
        pending: false,
        confirmed_by: who,
        ...(force ? { force_client_overlap: true } : {}),
      });
      this._message = {
        kind: "ok",
        text: who
          ? `Appuntamento confermato da ${who}.`
          : "Appuntamento confermato.",
      };
      this._render();
      // A confirmed booking is owed the summary: ask, and let the desk decide
      // rather than sending a WhatsApp nobody asked for.
      const phone = (appointment.client || {}).phone || "";
      if (phone && window.confirm(
        "Inviare all'ospite il riepilogo dell'appuntamento su WhatsApp?")) {
        try {
          await this._call("send_guest_summary", { appointment_id: appointment.id });
        } catch (error) {
          /* message already shown */
        }
      }
    } catch (error) {
      // Same question as on create: a same-client overlap offers forcing,
      // an operator clash keeps the plain error.
      const text = String((error && error.message) || "");
      if (!force && /sovrappone/i.test(text) && /cliente/i.test(text)) {
        this._overlapPopup = { message: text, retry: { kind: "confirm", id: appointment.id } };
        this._render();
        return;
      }
      /* any other message already shown */
    }
  }

  _appointmentRow(appointment, cancelled) {
    const start = parseDate(appointment.start);
    const end = parseDate(appointment.end);
    const client = this._lookup.client.get(appointment.client_id);
    const phone = client ? client.phone : "";
    const whatsapp = waLink(phone);
    const notes = this._clientNotes(appointment);
    const treatment = this._lookup.treatment.get(appointment.treatment_id);
    const category = this._categoryOf(treatment);
    const guest = this._guestMeta(appointment.guest_type);

    // data-appt carries the id, so the detail popup and the tests can point at
    // one specific appointment instead of guessing from its text.
    const row = el("div", {
      class: `appt${cancelled ? " cancelled" : ""}`,
      "data-appt": appointment.id,
    });

    // People who came together under one client card share a slot: a bar on
    // the left and a chip with the count make that visible at a glance, so
    // three rows with the same name read as one booking and not as three.
    const group = cancelled ? [] : this._groupOf(appointment);
    if (group.length > 1) row.classList.add("grouped");
    // The vertical bar of a group is one distinct colour per group of the
    // day, so a busy day reads as one bar per party instead of a single
    // colour for all of them.
    const groupColor = this._groupColor(appointment);
    if (groupColor) row.style.setProperty("--group-color", groupColor);

    // Background colour of the appointment comes from its treatment's
    // category. Cancelled rows keep their faded look instead.
    if (!cancelled && category && category.color) {
      row.classList.add("tinted");
      row.style.setProperty("--appt-bg", category.color);
      row.style.setProperty("--appt-fg", readableInk(category.color));
    }

    // The icon row is built once and used once: the accessories this person
    // chose, the payment marks and the group chip. It gets its own line so
    // nothing overlaps on a phone.
    const extrasIcons = appointment.extras && appointment.extras.length
      ? el("span", { class: "appt-extras" },
          appointment.extras
            .map((id) => this._accessory(id))
            .map((entry) =>
              el("ha-icon", {
                class: "extra-icon",
                icon: entry.icon,
                title: entry.label,
              })))
      : null;
    const payIcons = this._paymentIcons(appointment);
    // La stella: segnala su ogni appuntamento che la richiesta di recensione
    // è già partita. Compare anche come riga dentro il popup.
    const reviewStar = appointment.review_request_sent
      ? el("ha-icon", { class: "review-star", icon: "mdi:star",
          title: "Richiesta recensione inviata" })
      : null;
    const groupChip = group.length > 1
      ? el("span", { class: "chip group", title: `${group.length} persone` },
          el("ha-icon", { class: "chip-icon", icon: "mdi:account-group" }),
          el("span", { class: "group-count" }, String(group.length)),
          el("span", { class: "group-label" }, " persone"))
      : null;
    // The masseuse's confirmation, beside the category: a clickable double
    // check, green once she confirmed, amber while the offer is still open.
    // Only a booking that really has an assigned operator can carry it.
    const offerPending = appointment.offer_state === "offered";
    const canOffer = this._can("offers");
    const confirmIcon = category && category.requires_operator && appointment.operator_id
      ? el("ha-icon", {
          class: `offer-check ${offerPending ? "wait" : "ok"}${canOffer ? "" : " static"}`,
          icon: "mdi:check-all",
          title: offerPending ? "In attesa di conferma" : "Confermato",
          on: canOffer
            ? {
                click: (event) => {
                  event.stopPropagation();
                  this._toggleOffer(appointment, offerPending);
                },
              }
            : {},
        })
      : null;

    row.appendChild(
      this._rowTappable(
        appointment,
        el("div", { class: "appt-left" },
          el("div", { class: "appt-time" }, `${timeOf(start)} – ${timeOf(end)}`),
          // The hotel/external flag sits under the time, where it reads on
          // every row, whatever else the row carries.
          el("ha-icon", {
            class: `guest-icon ${guest.id}`,
            icon: guest.icon,
            title: guest.label,
          }),
          // The booking reference, compact under the time so the reception
          // spots it at a glance on every row of the agenda.
          appointment.code
            ? el("span", { class: "appt-code", title: "Codice prenotazione" }, appointment.code)
            : null,
          // The category, the confirmation check and the group chip share the
          // line under the time.
          (category || groupChip || confirmIcon)
            ? el("div", { class: "appt-tags" },
                category ? el("span", { class: "chip" }, category.name) : null,
                confirmIcon,
                groupChip)
            : null),
        el(
          "div",
          { class: "appt-body" },
          el("div", { class: "appt-client" }, this._clientName(appointment)),
          el(
            "div",
            { class: "appt-treat" },
            this._treatmentName(appointment),
            el("span", { class: "sep" }, "·"),
            el("span", { class: "dim" }, minutesLabel(this._durationOf(appointment)))
          ),
          // The icons get their own row, so nothing overlaps on a phone: the
          // accessories and the payment marks, left to right.
          extrasIcons || payIcons || reviewStar
            ? el("div", { class: "appt-icons" }, extrasIcons, payIcons, reviewStar)
            : null,
          appointment.offer_state === "offered"
            ? el("span", { class: "chip warn" },
                `Proposta a ${this._operatorName(appointment) || "—"} · in attesa`)
            : null,
          appointment.offer_state === "unassigned"
            ? el("span", { class: "chip danger" }, "Da assegnare")
            : null,
          // Waiting for confirmation is a state of the booking, not of the
          // offer to the masseuse: the two must not be read as one thing.
          appointment.status === "pending"
            ? el("span", { class: "chip pending", title: "In attesa di conferma" },
                el("ha-icon", { class: "chip-icon", icon: "mdi:clock-outline" }),
                el("span", { class: "chip-text" }, "In attesa di conferma"))
            : null,
          appointment.status !== "pending" && appointment.confirmed_by
            ? el("span", { class: "dim small" }, `Confermato da ${appointment.confirmed_by}`)
            : null,
          appointment.checked_in
            ? el("span", { class: "chip ok" }, "Entrata ✓")
            : null,
          appointment.checked_out
            ? el("span", { class: "chip ok" }, "Uscita ✓")
            : null,
          appointment.notes ? el("div", { class: "appt-note" }, appointment.notes) : null,
          cancelled && appointment.cancel_reason
            ? el("div", { class: "appt-note" }, `Annullato: ${appointment.cancel_reason}`)
            : null
        )
      )
    );

    const actions = el("div", { class: "appt-actions" });
    // Management actions are for operators and above; a read-only account
    // still sees the row, the popup and the contact shortcuts.
    const canOperate = this._can("book");
    // A zero-height break, used on phones to push phone and WhatsApp onto
    // their own row under the management actions.
    actions.appendChild(el("div", { class: "appt-actions-break" }));
    // The whole row opens the detail popup, and the buttons on the right are
    // shortcuts: they must not be swallowed by that tap target, so each one
    // stops the click from reaching the row behind it.
    actions.addEventListener("click", (event) => event.stopPropagation());
    if (phone) {
      actions.appendChild(
        el("a", { class: "btn small tel appt-contact", href: telHref(phone), title: phone },
          el("ha-icon", { icon: "mdi:phone" }))
      );
    }
    if (whatsapp) {
      actions.appendChild(
        el("a", { class: "btn small wa appt-contact", href: whatsapp, target: "_blank", rel: "noopener", title: "WhatsApp" },
          el("ha-icon", { icon: "mdi:whatsapp" }))
      );
    }
    if (notes) {
      actions.appendChild(
        el("button", {
          class: "btn small",
          title: notes,
          on: { click: () => { this._message = { kind: "ok", text: `Note cliente: ${notes}` }; this._render(); } },
        }, el("ha-icon", { icon: "mdi:note-text-outline" }))
      );
    }
    if (!cancelled) {
      // A booking still waiting: confirming it is the first thing to offer,
      // because it is the one thing the desk cannot leave undone.
      if (canOperate && appointment.status === "pending") {
        actions.appendChild(
          el("button", {
            class: "btn small primary",
            disabled: this._busy,
            title: this._confirmerName()
              ? `Conferma e registra ${this._confirmerName()}`
              : "Conferma l'appuntamento",
            on: { click: () => this._confirmAppointment(appointment) },
          }, el("ha-icon", { icon: "mdi:check" }),
            el("span", { class: "btn-label" }, "Conferma"))
        );
      }
      // Check-in: today's confirmed appointments only, and only until the
      // reception records the entry — then the button gives way to its chip.
      if (
        canOperate &&
        this._isToday(appointment) &&
        appointment.status === "confirmed" &&
        !appointment.checked_in
      ) {
        actions.appendChild(
          el("button", {
            class: "btn small checkin",
            disabled: this._busy,
            on: { click: () => this._confirmEntry(appointment) },
          }, "Entrata")
        );
        // Invisible separator: forces a line break after Entrata on mobile,
        // so Modifica and Annulla start on a new row below it.
        actions.appendChild(el("div", { class: "checkin-break" }));
      }
      if (group.length > 1) {
        const groupKey = [
          appointment.treatment_id,
          appointment.client_id,
          appointment.start,
          appointment.operator_id || "",
        ].join("|");
        const expanded = this._expandedGroups && this._expandedGroups.has(groupKey);
        actions.appendChild(
          el("button", {
            class: "btn small",
            title: expanded
              ? "Nascondi le persone del gruppo"
              : "Mostra le persone del gruppo",
            disabled: this._busy,
            on: { click: () => this._toggleParty(appointment) },
          }, el("ha-icon", { icon: "mdi:account-group" }))
        );
      }
      if (canOperate) {
        actions.appendChild(
          el("button", {
            class: "btn small",
            title: "Modifica appuntamento",
            disabled: this._busy,
            on: { click: () => this._openEditAppointment(appointment) },
          }, el("ha-icon", { icon: "mdi:pencil" }))
        );
        actions.appendChild(
          el("button", {
            class: "btn small danger",
            title: "Annulla appuntamento",
            disabled: this._busy,
            on: { click: () => this._confirmCancel(appointment) },
          }, el("ha-icon", { icon: "mdi:calendar-remove" }))
        );
      }
    } else if (canOperate) {
      actions.appendChild(
        el("button", {
          class: "btn small danger",
          title: "Elimina definitivamente",
          disabled: this._busy,
          on: { click: () => this._confirmDeleteAppointment(appointment) },
        }, el("ha-icon", { icon: "mdi:delete" }))
      );
    }
    row.appendChild(actions);
    return row;
  }

  async _confirmCancel(appointment) {
    const label = `${this._clientName(appointment)} — ${this._treatmentName(appointment)}`;
    if (!window.confirm(`Annullare l'appuntamento di ${label}?\n\nL'annullamento resta nello storico.`)) {
      return;
    }
    const reason = window.prompt("Motivo dell'annullamento (facoltativo):", "") || "";
    try {
      await this._call("cancel_appointment", { appointment_id: appointment.id, reason });
    } catch (error) {
      /* message already shown */
    }
  }

  async _confirmDeleteAppointment(appointment) {
    const label = `${this._clientName(appointment)} — ${this._treatmentName(appointment)}`;
    if (!window.confirm(`Eliminare definitivamente l'appuntamento annullato di ${label}?\n\nNon potrà più essere recuperato.`)) {
      return;
    }
    try {
      await this._call("delete_appointment", { appointment_id: appointment.id });
    } catch (error) {
      /* message already shown */
    }
  }

  /** Open the edit form for an appointment (pre-filled with current data). */
  _openEditAppointment(appointment) {
    this._editFormMode = false;
    this._editDrag = null;
    const treatment = (appointment.treatment_id && this._lookup.treatment.get(appointment.treatment_id)) || null;
    const catalogue = treatment && treatment.price != null ? Number(treatment.price) || 0 : 0;
    const list = appointment.list_price != null ? appointment.list_price : catalogue;
    const price = appointment.price != null ? appointment.price : list;
    this._editing = {
      kind: "appointment",
      id: appointment.id,
      draft: {
        treatment_id: appointment.treatment_id,
        start: appointment.start,
        client_id: appointment.client_id,
        operator_id: appointment.operator_id || "",
        notes: appointment.notes || "",
        guest_type: appointment.guest_type || GUEST_DEFAULT,
        extras: appointment.extras || [],
        list_price: list,
        price: price,
        payment: {
          paid: Boolean(appointment.paid),
          paid_amount: appointment.paid_amount ? String(appointment.paid_amount) : "",
          deposit: Boolean(appointment.deposit),
          deposit_amount: appointment.deposit_amount ? String(appointment.deposit_amount) : "",
          voucher: Boolean(appointment.voucher),
          voucher_code: appointment.voucher_code || "",
          balance_due: Boolean(appointment.balance_due),
          balance_due_amount: appointment.balance_due_amount ? String(appointment.balance_due_amount) : "",
          methods: [...(appointment.methods || [])],
        },
      },
    };
    this._render();
  }


  _openEditBatch(appointment) {
    // Build a populated Nuovo-form starting from the existing batch so the
    // receiver can edit everything people/treatments/time/operator/price/notes
    // with the same draggable two-column UI as a fresh booking.
    const related = this._relatedOf(appointment).filter((a) => a.status !== "cancelled");
    const anchor = related[0] || appointment;
    const sharedClients = [...new Set(related.map((a) => a.client_id).filter(Boolean))];
    const leaderClient = sharedClients.length ? this._lookup.client.get(sharedClients[0]) : null;

    const defaultPerson = { uid: this._uid(), person: 0, treatments: [], extras: [], first_name: "", last_name: "", phone: "", email: "" };
    const byPerson = new Map();
    for (const appt of related) {
      const pidx = appt.person != null ? Number(appt.person) : 0;
      if (!byPerson.has(pidx)) {
        byPerson.set(pidx, {
          uid: this._uid(),
          person: pidx,
          treatments: [],
          extras: appt.extras || [],
        });
      }
      const p = byPerson.get(pidx);
      const tr = (appt.treatment_id && this._lookup.treatment.get(appt.treatment_id)) || null;
      const catalogue = tr && tr.price != null ? Number(tr.price) || 0 : 0;
      p.treatments.push({
        uid: this._uid(),
        treatment_id: appt.treatment_id,
        time: timeOf(parseDate(appt.start)),
        list_price: appt.list_price != null ? appt.list_price : catalogue,
        price: appt.price != null ? appt.price : (appt.list_price != null ? appt.list_price : catalogue),
        operator_id: appt.operator_id || "",
        extras: [],
        appointment_id: appt.id,
        force_new: false,
      });
    }
    const persons = [...byPerson.values()];
    if (!persons.length) {
      persons.push({ uid: this._uid(), person: 0, treatments: [], extras: [] });
    }

    this._form = {
      treatment_id: "",
      operator_id: "",
      date: related.length ? ymd(parseDate(related[0].start)) : todayStr(),
      time: related.length ? timeOf(parseDate(related[0].start)) : "10:00",
      client_mode: "new",
      client_id: (related[0] && related[0].client_id) || "",
      client_query: "",
      client_results: null,
      first_name: leaderClient ? (leaderClient.first_name || "") : "",
      last_name: leaderClient ? (leaderClient.last_name || "") : "",
      phone: leaderClient ? (leaderClient.phone || "") : "",
      email: leaderClient ? (leaderClient.email || "") : "",
      client_notes: leaderClient ? (leaderClient.notes || "") : "",
      notes: related.length ? (related[0].notes || "") : "",
      treatments: [],
      payment: {
        paid: false, paid_amount: "", deposit: false, deposit_amount: "",
        voucher: false, voucher_code: "", balance_due: false, balance_due_amount: "",
        methods: [],
      },
      pending: related.length ? related[0].status === "pending" : false,
      guest_type: (related.length && related[0].guest_type) || GUEST_DEFAULT,
      extras: [],
      people: persons.length,
      persons: persons,
      new_client: false,
      stagedPayments: [],
      _batchEditing: true,
    };

    this._batchEditing = true;
    this._batchEditMode = false;
    this._batchAnchorId = appointment.id;
    this._batchAnchorBatchId = appointment.batch_id || appointment.id;
    this._batchRows = related.map((m) => ({ appointment_id: m.id, _deleted: false }));
    this._formEditMode = false;
    this._tab = "nuovo";
    this._nuovoTab = "appuntamento";
    this._render();
  }

  _renderEditBatch() {
    const anchor = this._lookup.appointment.get(this._batchAnchorId) || {};
    const treatments = this._activeTreatments();
    const rows = this._batchRows;

    const treatmentOptions = () => null;

    const rowCard = (row, index) => {
      if (row._deleted) return null;
      const box = el("div", { class: "session-card-batch" });
      // Trattamento
      const treatmentSelect = el("select", {
        class: "input",
        on: { change: (event) => { row.treatment_id = event.target.value; this._render(); } },
      });
      treatmentSelect.appendChild(el("option", { value: "" }, "— Scegli il trattamento —"));
      const categories = [...this._data.categories].sort((a, b) => a.name.localeCompare(b.name));
      const grouped = new Map();
      treatments.forEach((t) => {
        if (t.category_id && this._lookup.category.has(t.category_id)) {
          if (!grouped.has(t.category_id)) grouped.set(t.category_id, []);
          grouped.get(t.category_id).push(t);
        } else {
          grouped.set("__none__", [...(grouped.get("__none__") || []), t]);
        }
      });
      [...categories, { id: "__none__", name: "Senza categoria" }].forEach((category) => {
        const list = grouped.get(category.id) || [];
        if (!list.length) return;
        const optgroup = el("optgroup", { label: category.name });
        list.forEach((treatment) =>
          optgroup.appendChild(el("option", { value: treatment.id, selected: row.treatment_id === treatment.id }, treatment.name))
        );
        treatmentSelect.appendChild(optgroup);
      });
      box.appendChild(treatmentSelect);

      // Data + orario
      const start = row.start || "";
      const day = start.split("T")[0] || todayStr();
      const time = (start.split("T")[1] || "10:00").slice(0, 5);
      const dateInput = el("input", { class: "input", type: "date", value: day,
        on: { change: (event) => {
          const d = event.target.value || todayStr();
          const t = ((row.start || "").split("T")[1] || "10:00").slice(0, 5);
          row.start = `${d}T${t}`; this._render();
        } } });
      const timeInput = el("input", { class: "input", type: "time", value: time,
        on: { change: (event) => { const d = (row.start || "").split("T")[0] || todayStr(); row.start = `${d}T${(event.target.value || "10:00")}`; this._render(); } } });
      box.appendChild(dateInput);
      box.appendChild(timeInput);

      // Operatore
      const operatorSelect = el("select", {
        class: "input",
        on: { change: (event) => { row.operator_id = event.target.value || ""; } },
      });
      operatorSelect.appendChild(el("option", { value: "" }, "— Nessun operatore —"));
      this._data.operators.forEach((operator) =>
        operatorSelect.appendChild(el("option", { value: operator.id, selected: row.operator_id === operator.id }, operator.name))
      );
      box.appendChild(operatorSelect);

      // Prezzi
      const listPriceInput = el("input", { class: "input", type: "number", step: "0.01", value: row.list_price != null ? row.list_price : "" ,
        on: { input: (event) => { const v = event.target.value; row.list_price = v === "" ? null : Number(v); } } });
      const priceInput = el("input", { class: "input", type: "number", step: "0.01", value: row.price != null ? row.price : "" ,
        on: { input: (event) => { const v = event.target.value; row.price = v === "" ? null : Number(v); } } });
      box.appendChild(listPriceInput);
      box.appendChild(priceInput);

      // Note
      box.appendChild(el("textarea", { class: "input", rows: "2", value: row.notes || "",
        on: { input: (event) => { row.notes = event.target.value; } } }));

      // Pagamenti read-only
      const oldAppointment = row.appointment_id ? this._lookup.appointment.get(row.appointment_id) : null;
      if (oldAppointment && (oldAppointment.payments || []).length) {
        const paying = (oldAppointment.payments || []).map((item) => {
          const m = PAYMENT_METHODS.find(({ id }) => id === item.method) || {};
          return `${m.label || item.method}: ${euro(item.amount)} (${item.date || "—"})`;
        }).join(", ");
        box.appendChild(el("div", { class: "hint" }, `Incassi registrati: ${paying}`));
      }

      box.appendChild(el("button", {
        class: "btn danger small",
        disabled: this._batchBusy,
        on: { click: () => { row._deleted = true; this._render(); } },
      }, el("ha-icon", { icon: "mdi:delete" }), el("span", { class: "btn-label" }, "Rimuovi")));

      return box;
    };

    const wrap = el("div", {
      class: "stack form-compact" + (this._batchFormMode ? " form-edit" : ""),
    });

    // Header with pencil toggle for drag mode
    const head = el("div", { class: "row" },
      el("h3", {}, `Modifica gruppo (${this._batchRows.filter((r) => !r._deleted).length} attive)`),
      el("div", { class: "spacer" }));
    if (this._batchFormMode) {
      head.appendChild(this._colChooser("batch"));
      head.appendChild(
        el("div", { class: "spa-head-actions" },
          el("button", {
            class: "btn primary small",
            title: "Fine modifica",
            on: { click: () => { this._batchFormMode = false; this._render(); } },
          }, el("ha-icon", { icon: "mdi:check" }))
        )
      );
    } else {
      head.appendChild(
        el("button", {
          class: "icon-btn",
          title: "Modifica ordine box",
          on: { click: () => { this._batchFormMode = true; this._render(); } },
        }, el("ha-icon", { icon: "mdi:pencil" })));
    }
    head.appendChild(el("button", {
      class: "icon-btn",
      title: "Chiudi",
      on: { click: () => { this._batchEditing = false; this._batchRows = []; this._render(); } },
    }, el("ha-icon", { icon: "mdi:close" })));
    wrap.appendChild(head);

    const columns = this._colsGrid("form");
    const left = el("div", { class: "stack tight form-col", "data-col": "left" });
    const right = el("div", { class: "stack tight form-col", "data-col": "right" });

    const rowsContent = el("div", { class: "stack tight" });
    this._batchRows.forEach((row, index) => {
      if (row._deleted) return;
      add(rowsContent, rowCard(row, index));
    });

    const totalsContent = el("div", { class: "stack tight" });
    const groupedTotals = this._relatedTotals(this._lookup.appointment.get(this._batchAnchorId) || {});
    totalsContent.appendChild(el("div", { class: "detail-line" }, "Totale gruppo", euro(groupedTotals.total), "ok"));
    totalsContent.appendChild(el("div", { class: "detail-line" }, "Persone", String(groupedTotals.persons)));
    totalsContent.appendChild(el("div", { class: "detail-line" }, "Incassato", euro(groupedTotals.collected), "ok"));
    totalsContent.appendChild(el("div", { class: "detail-line" }, "Da incassare", euro(groupedTotals.due), "due"));

    const incassiContent = el("div", { class: "stack tight" });
    const anchorAppointment = this._lookup.appointment.get(this._batchAnchorId);
    const groupMembers = this._relatedOf(anchorAppointment || {});
    const allTakingRows = groupMembers.flatMap((member) =>
      (member.payments || []).map((item) => {
        const method = PAYMENT_METHODS.find(({ id }) => id === item.method) || {};
        return el("div", { class: "detail-line" }, method.label || item.method, `${item.date || "—"} · ${euro(item.amount)}`);
      }));
    if (allTakingRows.length) {
      allTakingRows.forEach((row) => add(incassiContent, row));
    } else {
      add(incassiContent, el("div", { class: "hint" }, "Nessun incasso registrato"));
    }

    const noteContent = el("div", { class: "stack tight" });
    noteContent.appendChild(el("div", { class: "hint" }, "Le note delle righe singole si modificano in ciascuna scheda."));

    const allBlocks = [
      { id: "righe", content: rowsContent },
      { id: "note", content: noteContent },
      { id: "totali", content: totalsContent },
      { id: "incassi", content: incassiContent },
    ];

    allBlocks.forEach(({ id, content }) => {
      if (this._batchFormMode) {
        const target = this._batchFormOrder("left").includes(id) ? left : right;
        add(target, this._batchSection(id, content));
      } else {
        // Default layout: righe + note left, totali + incassi right
        if (id === "righe") add(left, content);
        if (id === "note") add(right, content);
        if (id === "totali") add(right, content);
        if (id === "incassi") add(left, content);
      }
    });

    columns.appendChild(left);
    columns.appendChild(right);
    wrap.appendChild(columns);

    return wrap;
  }


  async _saveBatchEdit() {
    try {
      this._batchBusy = true;
      this._render();
      const flattened = [];
      this._bookingRows().forEach((row) => {
        (row.entries || []).forEach((entry) => {
          flattened.push({
            ...entry,
            treatment_id: entry.treatment_id || row.treatment_id,
            pending: row.pending,
            guest_type: entry.guest_type || row.guest_type || GUEST_DEFAULT,
            batch_id: this._batchAnchorBatchId,
          });
        });
      });
      await this._call("update_booking_batch", {
        appointment_id: this._batchAnchorId,
        rows: flattened,
      });
      this._batchEditing = false;
      this._batchAnchorId = null;
      this._batchAnchorBatchId = null;
      this._batchRows = [];
      this._tab = "agenda";
      this._message = { kind: "ok", text: "Gruppo aggiornato." };
    } catch (error) {
      /* message shown by _call */
    } finally {
      this._batchBusy = false;
      this._render();
    }
  }

  async _confirmDeleteClient(client) {
    const label = [client.first_name, client.last_name].filter(Boolean).join(" ") || client.phone || "senza nome";
    const guard = this._clientAppointments(client.id).filter(
      (appointment) => appointment.status !== "cancelled" && parseDate(appointment.end) >= new Date()
    );
    if (guard.length) {
      this._message = {
        kind: "error",
        text: `Impossibile eliminare la scheda: il cliente ha ${guard.length} appuntamenti confermati futuri. Annullali prima.`,
      };
      this._render();
      return;
    }
    if (!window.confirm(`Eliminare la scheda cliente di ${label}?\n\nLa scheda e i suoi dati verranno rimossi definitivamente.`)) {
      return;
    }
    try {
      await this._call("delete_client", { client_id: client.id });
      this._clientSelected = null;
      this._clientEditing = null;
      this._render();
    } catch (error) {
      /* message already shown */
    }
  }

  // -------------------------------------------------------------------- NUOVO

  _renderNew() {
    // Sub-tab bar for Appuntamento / Nuova richiesta / Lista richieste. It sits
    // outside the "no active treatments" check of the appointment form, so the
    // request list stays reachable even when nothing is bookable.
    const allowed = this._visibleNuovoTabs();
    if (!allowed.some((tab) => tab.id === this._nuovoTab)) {
      this._nuovoTab = allowed.length ? allowed[0].id : "appuntamento";
    }
    const wrap = el("div", { class: "stack nuovo" });
    if (allowed.length > 1) {
      const subTabs = el("div", { class: "tabs tight" });
      allowed.forEach((tab) => {
        subTabs.appendChild(
          el("button", {
            class: `tab small${this._nuovoTab === tab.id ? " active" : ""}`,
            title: tab.label,
            on: {
              click: () => {
                this._nuovoTab = tab.id;
                this._render();
              },
            },
          },
            el("ha-icon", { icon: tab.icon }),
            el("span", { class: "tab-label" }, tab.label)
          )
        );
      });
      wrap.appendChild(subTabs);
    }

    if (this._nuovoTab === "appuntamento") {
      add(wrap, this._renderNuovoForm());
    }
    if (this._nuovoTab === "nuova") {
      add(wrap, this._renderRichiestaForm());
    }
    if (this._nuovoTab === "lista") {
      add(wrap, this._renderRichiesteList());
    }
    return wrap;
  }

  _renderNuovoForm() {
    const treatments = this._activeTreatments();

    if (!treatments.length) {
      return el("div", { class: "empty" },
        "Non ci sono trattamenti attivi. Creane uno nella scheda Configurazione.");
    }

    // Persons first: date and count at the top, then one compact block per
    // person (treatment, masseuse, time), then the shared client card and
    // the appointment notes. One person = the flat form fields; more = the
    // persons array, sent all or nothing through create_bookings.
    const multi = Array.isArray(this._form.persons);
    const wrap = el("div", {
      class: "stack form-compact" + (this._formEditMode ? " form-edit" : ""),
    });

    if (this._can("config")) wrap.appendChild(this._formHeader());

    add(wrap, this._peopleRow());

    if (this._peopleMin() > 1) {
      wrap.appendChild(el("div", { class: "hint" },
        `Questo trattamento richiede almeno ${this._peopleMin()} persone insieme nella stessa fascia.`));
    }

    // Two columns: the booking itself on the left, the client on the right, so
    // the reception goes from the treatment to who it belongs to without
    // scrolling. On a narrow screen the columns stack to one. In edit mode the
    // blocks inside each column can be dragged to a new order and nothing else
    // changes: no names, no icons, nothing can be added or removed.
    const columns = this._colsGrid("form");
    const left = el("div", { class: "stack tight form-col", "data-col": "left" });
    const right = el("div", { class: "stack tight form-col", "data-col": "right" });
    this._formOrder("left").forEach((id) => {
      const content = this._formBlock(id, multi);
      if (content) add(left, this._formSection(id, content));
    });
    this._formOrder("right").forEach((id) => {
      const content = this._formBlock(id, multi);
      if (content) add(right, this._formSection(id, content));
    });
    columns.appendChild(left);
    columns.appendChild(right);
    wrap.appendChild(columns);

    // Everything ready to be booked: every treatment of every person counts,
    // so one person with two treatments shows "Crea 2 appuntamenti".
    const states = multi ? this._form.persons : [this._form];
    let count = 0;
    states.forEach((person) => {
      count += this._treatmentsOf(person).filter((treat) => treat.treatment_id).length;
    });
    const isBatchEditing = !!this._batchEditing;
    wrap.appendChild(
      el("div", { class: "row" },
        el("button", {
          class: "btn primary",
          disabled: this._busy || !count,
          on: { click: () => isBatchEditing ? this._saveBatchEdit() : this._createBookings() },
        }, el("ha-icon", { icon: "mdi:check" }), isBatchEditing
            ? `Salva modifiche al gruppo (${count})`
            : (count === 1 ? "Crea appuntamento" : `Crea ${count} appuntamenti`)),
        el("button", {
          class: "btn",
          disabled: this._busy,
          on: { click: () => isBatchEditing
            ? (this._batchEditing = false, this._batchRows = [], this._batchAnchorId = null, this._batchAnchorBatchId = null, this._render())
            : this._clearForm() },
        }, "Annulla")
      )
    );

    return wrap;
  }

  /**
   * Layout of the form blocks: which section lives in which column. A block is
   * free to sit in either column, so the saved order is read column by column
   * and any block never placed is sent back to its default column. Unknown ids
   * are dropped, duplicates collapsed.
   */
  _formLayout() {
    const settings = (this._data && this._data.settings) || {};
    const raw = (settings.form_order && typeof settings.form_order === "object") ? settings.form_order : {};
    const defaults = {
      left: ["booking", "notes", "prenotazione", "totali", "incassi"],
      right: ["client", "guest"],
    };
    const all = defaults.left.concat(defaults.right);
    const seen = new Set();
    const layout = { left: [], right: [] };
    ["left", "right"].forEach((column) => {
      const given = Array.isArray(raw[column]) ? raw[column] : [];
      given.forEach((id) => {
        if (all.includes(id) && !seen.has(id)) { seen.add(id); layout[column].push(id); }
      });
    });
    ["left", "right"].forEach((column) => {
      defaults[column].forEach((id) => {
        if (!seen.has(id)) { seen.add(id); layout[column].push(id); }
      });
    });
    return layout;
  }

  /** Order of one form column, via the shared layout. */
  _formOrder(column) {
    return this._formLayout()[column];
  }

  /** Every recognized form block id. The old payment flags are no longer
   *  offered on new bookings: takings are registered as incassi instead.
   *  Saved layouts naming "payment" drop it, the backend keeps reading it. */
  _formAll() {
    return ["booking", "notes", "prenotazione", "totali", "incassi", "client", "guest"];
  }

  /** Build one form block for its column, or null when it does not apply. */
  _formBlock(id, multi) {
    if (id === "booking") {
      const box = el("div", { class: "stack tight" });
      if (!multi) add(box, this._bookingBlock(this._form, 0, false));
      else this._form.persons.forEach((person, index) =>
        add(box, this._bookingBlock(person, index, this._form.persons.length > 1)));
      return box;
    }
    if (id === "notes") {
      return el("label", { class: "field" },
        el("span", {}, "Note appuntamento"),
        el("textarea", {
          class: "input", rows: "2",
          on: { input: (event) => { this._form.notes = event.target.value; } },
        }, this._form.notes)
      );
    }
    if (id === "prenotazione") {
      const box = el("div", { class: "stack tight" });
      box.appendChild(
        el("div", { class: "field" },
          el("span", {}, "Prenotazione"),
          el("div", { class: "role-choice" },
            [
              { id: false, label: "Confermata", icon: "mdi:check-circle" },
              { id: true, label: "In attesa di conferma", icon: "mdi:clock-outline" },
            ].map((choice) =>
              el("button", {
                type: "button",
                class: `role-opt${this._form.pending === choice.id ? " on" : ""}`,
                title: choice.label,
                on: { click: () => { this._form.pending = choice.id; this._render(); } },
              },
                el("ha-icon", { icon: choice.icon }),
                choice.label)))
      ));
      box.appendChild(
        el("div", { class: "hint" },
          this._form.pending
            ? "La prenotazione resta in attesa e occupa la fascia. Appena metti " +
              "un voucher, un acconto o il pagamento intero passa da sola a confermata."
            : "La prenotazione viene confermata subito.")
      );
      return box;
    }
    if (id === "totali") return this._totaliBlock();
    if (id === "incassi") return this._incassiBlock();
    if (id === "client") {
      const box = el("div", { class: "stack tight" });
      box.appendChild(this._clientSection(this._form));
      if (multi && this._form.persons.length > 1) {
        box.appendChild(
          el("label", { class: "check" },
            el("input", { type: "checkbox", checked: this._form.new_client !== false,
              on: { change: (event) => { this._form.new_client = event.target.checked; } } }),
            el("span", {}, "Una scheda cliente per ogni persona"))
        );
        box.appendChild(el("div", { class: "hint" },
          "Serve quando due persone hanno lo stesso nome: ognuna riceve una scheda " +
          "separata, così puoi prenotare due massaggi nella stessa fascia."));
      }
      return box;
    }
    if (id === "guest") return this._guestField(this._form);
    return null;
  }

  /** Wrap a block for edit mode: only the drag handle is added. */
  _formSection(id, content) {
    if (!this._formEditMode) return content;
    const sec = el("div", { class: "form-sec", "data-section": id });
    sec.appendChild(content);
    sec.appendChild(
      el("button", {
        class: "icon-btn form-grip",
        title: "Sposta blocco",
      }, el("ha-icon", { icon: "mdi:drag-horizontal-variant" }))
    );
    this._formWireDrag(sec, id);
    return sec;
  }

  /** Wrap a notifications block for edit mode: only the drag handle is added. */
  _notifySection(id, content) {
    if (!this._notifyEditMode) return content;
    const sec = el("div", { class: "form-sec", "data-section": id });
    sec.appendChild(content);
    sec.appendChild(
      el("button", {
        class: "icon-btn form-grip",
        title: "Sposta blocco",
      }, el("ha-icon", { icon: "mdi:drag-horizontal-variant" }))
    );
    // Same drag as the booking form: it starts on the handle and works with a
    // mouse or a finger, so every block moves up/down and across columns.
    this._formWireDrag(sec, id, "notify");
    return sec;
  }

  // ------------------------------------------------------------------
  // column chooser: one column or two, per tab
  // ------------------------------------------------------------------

  /** How many columns a tab lays its blocks out in: 1 (stacked) or 2. */
  _tabCols(scope) {
    const settings = (this._data && this._data.settings) || {};
    const all = settings.tab_cols || {};
    const value = Number(all[scope]);
    return value === 1 ? 1 : 2;
  }

  /**
   * The two buttons that pick the layout, shown on the left of the tab title
   * while it is in edit mode. The choice is saved, so it survives a reload
   * and follows the reception to another device.
   */
  _colChooser(scope) {
    const current = this._tabCols(scope);
    return el("div", { class: "col-chooser" },
      el("span", { class: "col-chooser-label" }, "Colonne"),
      el("button", {
        class: "btn small" + (current === 1 ? " on" : ""),
        title: "Visualizza a una colonna",
        on: { click: () => this._setTabCols(scope, 1) },
      }, el("ha-icon", { icon: "mdi:view-list-outline" }), el("span", {}, "1")),
      el("button", {
        class: "btn small" + (current === 2 ? " on" : ""),
        title: "Visualizza a due colonne",
        on: { click: () => this._setTabCols(scope, 2) },
      }, el("ha-icon", { icon: "mdi:view-dashboard-outline" }), el("span", {}, "2"))
    );
  }

  /** Save how many columns a tab shows, then redraw it. */
  async _setTabCols(scope, cols) {
    const settings = (this._data && this._data.settings) || {};
    const all = { ...(settings.tab_cols || {}) };
    all[scope] = cols;
    try {
      await this._service("update_settings", { tab_cols: all });
      await this._loadData();
    } catch (error) {
      this._message = {
        kind: "error",
        text: this._friendlyError(error, "Salvataggio non riuscito."),
      };
    }
    this._render();
  }

  /** The block grid of a tab: two columns, or one when the reception chose it. */
  _colsGrid(scope) {
    return el("div", {
      class: "two-col" + (this._tabCols(scope) === 1 ? " one-col" : ""),
    });
  }

  /** Title row of the notifications tab: pencil toggle for edit mode. */
  _notifyHeader() {
    const head = el("div", { class: "spa-head" });
    if (this._notifyEditMode) head.appendChild(this._colChooser("notifiche"));
    head.appendChild(
      el("div", { class: "spa-head-title" },
        el("ha-icon", { icon: "mdi:bell-outline" }),
        el("span", {}, this._notifyEditMode ? "Modifica notifiche" : "Notifiche"))
    );
    if (this._notifyEditMode) {
      head.appendChild(
        el("div", { class: "spa-head-actions" },
          el("button", {
            class: "btn primary small",
            title: "Fine modifica",
            on: { click: () => { this._notifyEditMode = false; this._render(); } },
          }, el("ha-icon", { icon: "mdi:check" })))
      );
      return head;
    }
    head.appendChild(
      el("button", {
        class: "icon-btn spa-menu-btn",
        title: "Modifica ordine blocchi",
        on: { click: () => { this._notifyEditMode = true; this._render(); } },
      }, el("ha-icon", { icon: "mdi:pencil" }))
    );
    return head;
  }

  /** Title row of the Impostazioni tab: pencil toggle for edit mode. */
  _settingsHeader() {
    const head = el("div", { class: "spa-head" });
    if (this._settingsEditMode) head.appendChild(this._colChooser("settings"));
    head.appendChild(
      el("div", { class: "spa-head-title" },
        el("ha-icon", { icon: "mdi:cog-outline" }),
        el("span", {}, this._settingsEditMode ? "Modifica impostazioni" : "Impostazioni"))
    );
    if (this._settingsEditMode) {
      head.appendChild(
        el("div", { class: "spa-head-actions" },
          el("button", {
            class: "btn primary small",
            title: "Fine modifica",
            on: { click: () => { this._settingsEditMode = false; this._render(); } },
          }, el("ha-icon", { icon: "mdi:check" })))
      );
      return head;
    }
    head.appendChild(
      el("button", {
        class: "icon-btn spa-menu-btn",
        title: "Modifica ordine blocchi",
        on: { click: () => { this._settingsEditMode = true; this._render(); } },
      }, el("ha-icon", { icon: "mdi:pencil" }))
    );
    return head;
  }

  /** Wrap a Settings block for edit mode: only the drag handle is added. */
  _settingsSection(id, content) {
    if (!this._settingsEditMode) return content;
    const sec = el("div", { class: "form-sec", "data-section": id });
    sec.appendChild(content);
    sec.appendChild(
      el("button", {
        class: "icon-btn form-grip",
        title: "Sposta blocco",
      }, el("ha-icon", { icon: "mdi:drag-horizontal-variant" }))
    );
    // Same drag as the notifications tab: starts on the handle, works with a
    // mouse or a finger, and crosses from one column to the other.
    this._formWireDrag(sec, id, "settings");
    return sec;
  }

  /** Title row of the Nuovo appuntamento tab: pencil menu or edit actions. */
  _formHeader() {
    const head = el("div", { class: "spa-head" });
    if (this._formEditMode) head.appendChild(this._colChooser("form"));
    head.appendChild(
      el("div", { class: "spa-head-title" },
        el("ha-icon", { icon: "mdi:calendar-plus" }),
        el("span", {}, this._batchEditing ? "Modifica gruppo" : (this._formEditMode ? "Modifica scheda" : "Nuovo appuntamento")))
    );
    if (this._formEditMode) {
      head.appendChild(
        el("div", { class: "spa-head-actions" },
          el("button", {
            class: "btn primary small",
            title: "Fine modifica",
            on: { click: () => this._formEditExit() },
          }, el("ha-icon", { icon: "mdi:check" })))
      );
      return head;
    }
    head.appendChild(
      el("button", {
        class: "icon-btn spa-menu-btn",
        title: "Modifica scheda",
        on: { click: () => this._formEditEnter() },
      }, el("ha-icon", { icon: "mdi:pencil" }))
    );
    return head;
  }

  _richiestaFormHeader() {
    const head = el("div", { class: "spa-head" });
    if (this._richiestaEditMode) head.appendChild(this._colChooser("richiesta"));
    head.appendChild(
      el("div", { class: "spa-head-title" },
        el("ha-icon", { icon: "mdi:form-select" }),
        el("span", {}, this._richiestaEditMode ? "Modifica ordine" : "Richiesta"))
    );
    if (this._richiestaEditMode) {
      head.appendChild(
        el("div", { class: "spa-head-actions" },
          el("button", {
            class: "btn primary small",
            title: "Fine modifica",
            on: { click: () => { this._richiestaEditMode = false; this._render(); } },
          }, el("ha-icon", { icon: "mdi:check" })))
      );
      return head;
    }
    head.appendChild(
      el("button", {
        class: "icon-btn spa-menu-btn",
        title: "Modifica ordine blocchi",
        on: { click: () => { this._richiestaEditMode = true; this._render(); } },
      }, el("ha-icon", { icon: "mdi:pencil" }))
    );
    return head;
  }

  _richiestaSection(id, content) {
    if (!this._richiestaEditMode) return content;
    const sec = el("div", { class: "form-sec", "data-section": id });
    sec.appendChild(content);
    sec.appendChild(
      el("button", {
        class: "icon-btn form-grip",
        title: "Sposta blocco",
      }, el("ha-icon", { icon: "mdi:drag-horizontal-variant" }))
    );
    sec.draggable = true;
    return sec;
  }

  /** The pencil itself toggles edit mode: no intermediate Modifica menu. */
  _formEditEnter() {
    this._formEditMode = true;
    this._render();
  }

  _formEditExit() {
    this._formEditMode = false;
    this._formDrag = null;
    this._render();
  }

  /** Drag a block by its handle: mouse starts at once, touch after a hold.
   *  The same machinery serves the booking forms, the edit sheet, the
   *  notifications tab and the operator card; only the order it saves
   *  afterwards differs. */
  _formWireDrag(sec, id, scope = "form") {
    const grip = sec.querySelector(".form-grip");
    if (!grip) return;
    const state = scope === "notify" ? "_notifyDrag"
      : scope === "settings" ? "_settingsDrag"
      : scope === "edit" ? "_editDrag"
      : scope === "operator" ? "_operatorDrag"
      : "_formDrag";
    let timer = null;
    grip.addEventListener("pointerdown", (event) => {
      if (event.button && event.button !== 0) return;
      const begin = () => {
        if (!sec.isConnected) return;
        this[state] = { id, node: sec };
        sec.classList.add("dragging");
      };
      const move = (ev) => {
        if (this[state] && this[state].node === sec) {
          this._blockReorder(sec, ev.clientX, ev.clientY);
          if (ev.cancelable) ev.preventDefault();
        }
      };
      const up = () => {
        if (timer) clearTimeout(timer);
        window.removeEventListener("pointermove", move);
        window.removeEventListener("pointerup", up);
        window.removeEventListener("pointercancel", up);
        if (this[state] && this[state].node === sec) {
          sec.classList.remove("dragging");
          this[state] = null;
          if (scope === "notify") this._notifyCommitOrder();
          else if (scope === "settings") this._settingsCommitOrder();
          else if (scope === "edit") this._editCommitOrder();
          else if (scope === "operator") this._operatorCommitOrder();
          else this._formCommitOrder();
        }
      };
      window.addEventListener("pointermove", move, { passive: false });
      window.addEventListener("pointerup", up);
      window.addEventListener("pointercancel", up);
      if (event.pointerType === "mouse") begin();
      else timer = setTimeout(begin, 300);
    });
  }

  /**
   * Move the dragged block into the column nearest to the pointer (left or
   * right, they stack on narrow screens) and drop it at the vertical spot
   * closest to the pointer, so blocks cross columns freely.
   */
  _blockReorder(node, x, y) {
    const col = this._blockColumnAt(x, y);
    if (!col) return;
    let before = null;
    col.querySelectorAll(".form-sec").forEach((item) => {
      if (item === node) return;
      const rect = item.getBoundingClientRect();
      if (!before && y < rect.top + rect.height / 2) before = item;
    });
    col.insertBefore(node, before);
  }

  /** The column under (or closest to) the pointer, for cross-column drags. */
  _blockColumnAt(x, y) {
    const container = this.shadowRoot && this.shadowRoot.querySelector(".two-col");
    if (!container) return null;
    let best = null;
    let bestDist = Infinity;
    container.querySelectorAll(".form-col").forEach((col) => {
      const r = col.getBoundingClientRect();
      const dx = x < r.left ? r.left - x : x > r.right ? x - r.right : 0;
      const dy = y < r.top ? r.top - y : y > r.bottom ? y - r.bottom : 0;
      const dist = Math.hypot(dx, dy);
      if (dist < bestDist) { bestDist = dist; best = col; }
    });
    return best;
  }

  /**
   * After a drag: read the new visual order of both columns (blocks can cross
   * columns) and save it, unless it matches what is already stored.
   */
  async _formCommitOrder() {
    const container = this.shadowRoot && this.shadowRoot.querySelector(".two-col");
    if (!container) return;
    const current = this._formLayout();
    const next = this._readBlockOrder(container);
    // Every recognized block must be present exactly once, in one of the two.
    const all = this._formAll();
    const flat = next.left.concat(next.right);
    if (flat.length !== all.length || all.some((id) => !flat.includes(id))) return;
    const same = (a, b) => a.length === b.length && a.every((id, index) => id === b[index]);
    if (same(next.left, current.left) && same(next.right, current.right)) return;
    try {
      await this._service("update_settings", { form_order: next });
      await this._loadData();
    } catch (error) {
      this._message = {
        kind: "error",
        text: this._friendlyError(error, "Salvataggio non riuscito."),
      };
      this._render();
    }
  }

  /** The visual order of both columns, read from the DOM after a drag. */
  _readBlockOrder(container) {
    const next = { left: [], right: [] };
    ["left", "right"].forEach((column) => {
      const col = container.querySelector(`.form-col[data-col="${column}"]`);
      if (!col) return;
      col.querySelectorAll(".form-sec[data-section]").forEach((node) => {
        const id = node.getAttribute("data-section");
        if (!next[column].includes(id)) next[column].push(id);
      });
    });
    return next;
  }

  /** Layout of the edit-sheet blocks, from the saved order or the default. */
  _editFormLayout() {
    const settings = (this._data && this._data.settings) || {};
    const raw = (settings.edit_form_order && typeof settings.edit_form_order === "object") ? settings.edit_form_order : {};
    const defaults = {
      left: ["trattamento", "quando", "operatore", "note", "totali", "incassi"],
      right: ["cliente", "ospite", "accessori"],
    };
    const all = this._editFormAll();
    const seen = new Set();
    const layout = { left: [], right: [] };
    ["left", "right"].forEach((column) => {
      const given = Array.isArray(raw[column]) ? raw[column] : [];
      given.forEach((id) => {
        if (all.includes(id) && !seen.has(id)) { seen.add(id); layout[column].push(id); }
      });
    });
    ["left", "right"].forEach((column) => {
      defaults[column].forEach((id) => {
        if (!seen.has(id)) { seen.add(id); layout[column].push(id); }
      });
    });
    return layout;
  }

  /** Order of one edit-sheet column, via the shared layout. */
  _editFormOrder(column) {
    return this._editFormLayout()[column];
  }

  /** Every recognized edit-sheet block id. */
  _editFormAll() {
    return ["trattamento", "quando", "operatore", "note", "totali", "incassi", "cliente", "ospite", "accessori"];
  }

  /** Wrap an edit-sheet block for edit mode: drag handle included. */
  _editFormSection(id, content) {
    if (!this._editFormMode) return content;
    const sec = el("div", { class: "form-sec", "data-section": id });
    sec.appendChild(content);
    sec.appendChild(
      el("button", {
        class: "icon-btn form-grip",
        title: "Sposta blocco",
      }, el("ha-icon", { icon: "mdi:drag-horizontal-variant" }))
    );
    this._formWireDrag(sec, id, "edit");
    return sec;
  }

  /**
   * After an edit-sheet drag: read the new visual order and save it, unless
   * it matches what is already stored.
   */
  async _editCommitOrder() {
    const container = this.shadowRoot && this.shadowRoot.querySelector(".two-col");
    if (!container) return;
    const current = this._editFormLayout();
    const next = this._readBlockOrder(container);
    const flat = next.left.concat(next.right);
    // Every block drawn on this sheet must be read back exactly once, in one
    // of the two columns. The sheet can legitimately miss one (an incassi box
    // that does not apply, say), so the count follows what was drawn and not
    // the full list of known blocks.
    const drawn = [...container.querySelectorAll(".form-sec[data-section]")]
      .map((node) => node.dataset.section);
    if (flat.length !== drawn.length || drawn.some((id) => !flat.includes(id))) return;
    const same = (a, b) => a.length === b.length && a.every((id, index) => id === b[index]);
    if (same(next.left, current.left) && same(next.right, current.right)) return;
    try {
      await this._service("update_settings", { edit_form_order: next });
      await this._loadData();
    } catch (error) {
      // A refusal must be seen, not swallowed: a stale Home Assistant build
      // rejects the field and the blocks would silently jump back.
      this._message = {
        kind: "error",
        text: this._friendlyError(
          error,
          "Ordine dei box non salvato. Serve forse il riavvio di Home Assistant.",
        ),
      };
      this._render();
    }
  }

  /** Layout of the operator-card boxes, from the saved order or the default. */
  _operatorFormLayout() {
    const settings = (this._data && this._data.settings) || {};
    const raw = (settings.operator_form_order && typeof settings.operator_form_order === "object")
      ? settings.operator_form_order : {};
    const defaults = {
      left: ["nome", "contatti", "priorita", "notifiche", "messaggi"],
      right: ["trattamenti"],
    };
    const all = this._operatorFormAll();
    const seen = new Set();
    const layout = { left: [], right: [] };
    ["left", "right"].forEach((column) => {
      const given = Array.isArray(raw[column]) ? raw[column] : [];
      given.forEach((id) => {
        if (all.includes(id) && !seen.has(id)) { seen.add(id); layout[column].push(id); }
      });
    });
    ["left", "right"].forEach((column) => {
      defaults[column].forEach((id) => {
        if (!seen.has(id)) { seen.add(id); layout[column].push(id); }
      });
    });
    return layout;
  }

  /** Order of one operator-card column, via the shared layout. */
  _operatorFormOrder(column) {
    return this._operatorFormLayout()[column];
  }

  /** Every recognized operator-card box id. */
  _operatorFormAll() {
    return ["nome", "contatti", "priorita", "notifiche", "messaggi", "trattamenti"];
  }

  /** Wrap an operator-card box for edit mode: drag handle included. */
  _operatorFormSection(id, content) {
    if (!this._operatorFormMode) return content;
    const sec = el("div", { class: "form-sec", "data-section": id });
    sec.appendChild(content);
    sec.appendChild(
      el("button", {
        class: "icon-btn form-grip",
        title: "Sposta blocco",
      }, el("ha-icon", { icon: "mdi:drag-horizontal-variant" }))
    );
    this._formWireDrag(sec, id, "operator");
    return sec;
  }

  /**
   * After an operator-card drag: read the new visual order and save it,
   * unless it matches what is already stored. The messages box only exists on
   * a saved operator (a new one has no id to send to), so both the reading and
   * the comparison follow the boxes actually drawn.
   */
  async _operatorCommitOrder() {
    const container = this.shadowRoot && this.shadowRoot.querySelector(".two-col");
    if (!container) return;
    const current = this._operatorFormLayout();
    const next = this._readBlockOrder(container);
    const drawn = [...container.querySelectorAll(".form-sec[data-section]")]
      .map((node) => node.dataset.section);
    const flat = next.left.concat(next.right);
    if (!flat.length || flat.length !== drawn.length || drawn.some((id) => !flat.includes(id))) return;
    const same = (a, b) => a.length === b.length && a.every((id, index) => id === b[index]);
    const only = (list) => list.filter((id) => drawn.includes(id));
    if (same(only(next.left), only(current.left)) && same(only(next.right), only(current.right))) return;
    try {
      await this._service("update_settings", { operator_form_order: next });
      await this._loadData();
    } catch (error) {
      this._message = {
        kind: "error",
        text: this._friendlyError(
          error,
          "Ordine dei box non salvato. Serve forse il riavvio di Home Assistant.",
        ),
      };
      this._render();
    }
  }

  /** Mark a notifications or promo block with its id, so the saved order can place it. */
  _tagBlock(id, node) {
    node.dataset.block = id;
    return node;
  }

  /** Put the blocks in the saved order of one tab; blocks not stored keep their column. */
  _placeBlocks(left, right, key) {
    const settings = (this._data && this._data.settings) || {};
    const raw = settings[key];
    if (!raw || typeof raw !== "object") return;
    const origin = new Map();
    [...left.children].forEach((node) => origin.set(node, left));
    [...right.children].forEach((node) => origin.set(node, right));
    const byId = new Map();
    origin.forEach((column, node) => { if (node.dataset.block) byId.set(node.dataset.block, node); });
    const placed = new Set();
    ["left", "right"].forEach((column) => {
      const target = column === "left" ? left : right;
      (Array.isArray(raw[column]) ? raw[column] : []).forEach((id) => {
        const node = byId.get(id);
        if (node && !placed.has(node)) { placed.add(node); target.appendChild(node); }
      });
    });
    origin.forEach((column, node) => { if (!placed.has(node)) column.appendChild(node); });
  }

  /** Drag and drop of notifications or promo blocks: across columns and up/down. */
  _blockWire(container, scope) {
    container.addEventListener("dragstart", (event) => {
      const sec = event.target.closest(".form-sec[data-section]");
      if (!sec) return;
      this._blockDrag = { scope, id: sec.dataset.section };
      event.dataTransfer.effectAllowed = "move";
      event.dataTransfer.setData("text/plain", sec.dataset.section);
      sec.classList.add("dragging");
    });
    container.addEventListener("dragover", (event) => {
      const drag = this._blockDrag;
      if (!drag || drag.scope !== scope || !event.target.closest(".form-col")) return;
      event.preventDefault();
      event.dataTransfer.dropEffect = "move";
    });
    container.addEventListener("drop", (event) => this._blockDrop(event, scope));
    container.addEventListener("dragend", () => {
      this._blockDrag = null;
      container.querySelectorAll(".dragging").forEach((node) => node.classList.remove("dragging"));
    });
  }

  _blockDrop(event, scope) {
    const drag = this._blockDrag;
    this._blockDrag = null;
    if (!drag || drag.scope !== scope) return;
    const container = event.currentTarget;
    const col = event.target.closest(".form-col");
    const dragged = container.querySelector(`.form-sec[data-section="${drag.id}"]`);
    if (!col || !dragged) return;
    event.preventDefault();
    const over = event.target.closest(".form-sec[data-section]");
    if (over && over !== dragged) {
      if (this._trtBelowMiddle(event, over)) over.after(dragged);
      else over.before(dragged);
    } else {
      col.appendChild(dragged);
    }
    dragged.classList.remove("dragging");
    this._blockCommit(container, scope);
  }

  /** Save the visual order of both columns in the tab's own setting. */
  async _blockCommit(container, scope) {
    const key = scope === "promo" ? "promo_order" : "notifiche_order";
    const next = this._readBlockOrder(container);
    const flat = next.left.concat(next.right);
    const rendered = [...container.querySelectorAll(".form-sec[data-section]")].map((node) => node.dataset.section);
    if (flat.length !== rendered.length || rendered.some((id) => !flat.includes(id))) return;
    try {
      await this._service("update_settings", { [key]: next });
      await this._loadData();
    } catch (error) {
      this._message = {
        kind: "error",
        text: this._friendlyError(error, "Salvataggio non riuscito."),
      };
      this._render();
    }
  }

  /** Same as the form's, for the notifications tab: its blocks, its setting. */
  /** The stored two-column layout of the notifications tab, defaults included. */
  _notifyLayout() {
    const settings = (this._data && this._data.settings) || {};
    const raw = (settings.notifiche_order && typeof settings.notifiche_order === "object")
      ? settings.notifiche_order : {};
    const defaults = { left: ["telegram", "whatsapp", "waha", "preview"],
                       right: ["review", "report", "offers", "deposit", "guest_header", "summary",
                               "request_message", "appointment_reminder"] };
    const seen = new Set();
    const layout = { left: [], right: [] };
    ["left", "right"].forEach((column) => {
      const given = Array.isArray(raw[column]) ? raw[column] : [];
      given.forEach((id) => {
        if (seen.has(id)) return;
        seen.add(id);
        layout[column].push(id);
      });
    });
    ["left", "right"].forEach((column) => {
      defaults[column].forEach((id) => {
        if (!seen.has(id)) { seen.add(id); layout[column].push(id); }
      });
    });
    return layout;
  }

  async _notifyCommitOrder() {
    const container = this.shadowRoot && this.shadowRoot.querySelector(".two-col");
    if (!container) return;
    const current = this._notifyLayout();
    const next = this._readBlockOrder(container);
    const flat = next.left.concat(next.right);
    // Validate against the blocks really on screen, not against a fixed list:
    // an id that is no longer drawn must never block the save.
    const rendered = [...container.querySelectorAll(".form-sec[data-section]")]
      .map((node) => node.dataset.section);
    if (flat.length !== rendered.length || rendered.some((id) => !flat.includes(id))) return;
    const same = (a, b) => a.length === b.length && a.every((id, index) => id === b[index]);
    if (same(next.left, current.left) && same(next.right, current.right)) return;
    try {
      await this._service("update_settings", { notifiche_order: next });
      await this._loadData();
    } catch (error) {
      this._message = {
        kind: "error",
        text: this._friendlyError(error, "Salvataggio non riuscito."),
      };
      this._render();
    }
  }

  async _settingsCommitOrder() {
    const container = this.shadowRoot && this.shadowRoot.querySelector(".two-col");
    if (!container) return;
    const next = this._readBlockOrder(container);
    const flat = next.left.concat(next.right);
    // Validate against the blocks really on screen: an id no longer drawn
    // must never block the save.
    const rendered = [...container.querySelectorAll(".form-sec[data-section]")]
      .map((node) => node.dataset.section);
    if (flat.length !== rendered.length || rendered.some((id) => !flat.includes(id))) return;
    try {
      await this._service("update_settings", { impostazioni_order: next });
      await this._loadData();
    } catch (error) {
      this._message = {
        kind: "error",
        text: this._friendlyError(error, "Salvataggio non riuscito."),
      };
      this._render();
    }
  }

  /** Date and people count: the first thing the booking form asks for. */
  _peopleRow() {
    const count = this._peopleCount();
    const row = el("div", { class: "row tight" },
      el("label", { class: "field" },
        el("span", {}, "Data"),
        el("input", {
          class: "input", type: "date", value: this._form.date,
          on: { change: (event) => { this._form.date = event.target.value || todayStr(); this._render(); } },
        })),
      el("label", { class: "field stepper-field" },
        el("span", {}, "Persone"),
        el("div", { class: "row tight stepper" },
          el("button", {
            class: "icon-btn",
            disabled: this._busy || count <= 1,
            on: { click: () => this._setPeople(count - 1) },
          }, el("ha-icon", { icon: "mdi:minus" })),
          el("span", { class: "stepper-num" }, String(count)),
          el("button", {
            class: "icon-btn",
            disabled: this._busy || count >= this._peopleMax(),
            on: { click: () => this._setPeople(count + 1) },
          }, el("ha-icon", { icon: "mdi:plus" })),
          // Bulk shortcut: the first person's treatments and slots for
          // everybody, so a group doing the same thing is one click instead of
          // N-1. It sits right on the +, and only once there is somebody to
          // copy to.
          Array.isArray(this._form.persons) && this._form.persons.length > 1
            ? el("button", {
                class: "btn small copy-all",
                title: "Porta i trattamenti e gli orari della persona 1 su tutte le altre. " +
                  "La massaggiatrice resta quella scelta per ciascuna persona.",
                disabled: this._busy ||
                  !this._treatmentsOf(this._form.persons[0]).some((t) => t.treatment_id),
                on: { click: () => this._copyFirstToAll() },
              }, el("ha-icon", { icon: "mdi:content-copy" }))
            : null))
    );
    row.appendChild(this._voucherField());
    return row;
  }

  /**
   * The payment flags, each with the detail that belongs to it.
   *
   * Every flag that means money has its own amount, because "already handed
   * over 30" and "still owed 10" are two facts about the same booking rather
   * than two versions of it. A detail only appears while its own flag is
   * ticked: an input behind a box nobody checked is a trap, and it lets the
   * last value survive silently after the flag is cleared.
   */
  _paymentBlock(target) {
    const payment = target.payment || (target.payment = this._blankPayment());
    // One list, so a flag and its field can never drift apart: the chip that
    // opens a detail and the detail itself are declared together.
    const flags = [
      { key: "paid", label: "Pagato", icon: "mdi:check-circle-outline", chip: "mdi:check-circle" },
      { key: "deposit", label: "Ha fatto acconto", icon: "mdi:hand-coin-outline", chip: "mdi:hand-coin" },
      { key: "voucher", label: "C'è un voucher", icon: "mdi:ticket-confirmation-outline", chip: "mdi:ticket-confirmation" },
      { key: "balance_due", label: "Saldo ancora da pagare", icon: "mdi:clock-outline", chip: "mdi:clock-alert" },
    ];

    const box = el("div", { class: "field pay-box" },
      el("span", {}, "Pagamento"));

    // One row per entry, always visible: the checkbox with its label on the
    // left, the field for the value on the right. An amount typed without its
    // flag never travels: _paymentData only reads the value while its own
    // flag is ticked.
    const amountInput = (key, placeholder) =>
      el("input", {
        class: "input pay-amount", type: "number", min: "0", step: "0.01",
        placeholder,
        on: {
          input: (event) => { payment[key] = event.target.value; },
        },
      }, payment[key] === 0 ? "" : String(payment[key]));

    const line = (flag, field) =>
      el("div", { class: "pay-line" },
        el("label", { class: "check" },
          el("input", {
            type: "checkbox",
            checked: Boolean(payment[flag.key]),
            on: {
              change: (event) => {
                payment[flag.key] = event.target.checked;
                this._render();
              },
            },
          }),
          el("span", { class: "pay-check" },
            el("ha-icon", { icon: flag.icon }),
            flag.label)),
        field);

    box.appendChild(
      el("div", { class: "pay-lines" },
        line(flags[0], amountInput("paid_amount", "0,00")),
        line(flags[1], amountInput("deposit_amount", "0,00")),
        line(flags[2], el("input", {
          class: "input pay-amount", type: "text", placeholder: "es. VOUCHER-2026",
          on: { input: (event) => { payment.voucher_code = event.target.value; } },
        }, payment.voucher_code)),
        line(flags[3], amountInput("balance_due_amount", "0,00"))
      )
    );

    // The ways of paying are a second question from the amounts: which is
    // separate on purpose, so a voucher keeps its own code and its own saldo.
    box.appendChild(
      el("div", { class: "pay-methods" },
        el("span", { class: "dim small" }, "Come ha pagato"),
        el("div", { class: "checks" },
          PAYMENT_METHODS.map(({ id, label, icon }) =>
            el("label", { class: "check pay-method" },
              el("input", {
                type: "checkbox",
                checked: (payment.methods || []).includes(id),
                on: {
                  change: (event) => {
                    const current = new Set(payment.methods || []);
                    if (event.target.checked) current.add(id);
                    else current.delete(id);
                    // Kept in the declared order, so the payload does not
                    // depend on the order the desk happened to click.
                    payment.methods = PAYMENT_METHODS
                      .filter((method) => current.has(method.id))
                      .map((method) => method.id);
                    this._render();
                  },
                },
              }),
              el("span", { class: "pay-check" },
                el("ha-icon", { icon }),
                label))
          )
        ))
    );

    const expected = this._expectedTotal();
    if (expected !== null) {
      box.appendChild(
        el("div", { class: "hint" },
          `Totale trattamenti in lista: ${euro(expected)}.`)
      );
    }
    return box;
  }

  /**
   * The payment as a horizontal row of icons, with no text.
   *
   * At the desk the eye scans a column of rows, so the payment has to be
   * readable in one pass and without stealing horizontal room from the name:
   * icon only, and the amounts live in the detail popup one tap away. Colour
   * carries the meaning — green paid, amber deposit, red still owed, violet
   * voucher — and each way of paying gets its own colour too, so a card and a
   * cash payment are told apart without reading anything.
   */
  _paymentIcons(appointment) {
    if (!appointment) return null;
    const icons = [this._priceStatusIcon(appointment)];
    if (appointment.paid) icons.push(this._payIcon("mdi:currency-eur", "Pagato", "ok"));
    if (appointment.deposit) {
      icons.push(this._payIcon("mdi:hand-coin", "Acconto", "deposit"));
    }
    if (appointment.balance_due) {
      icons.push(this._payIcon("mdi:currency-eur", "Saldo da pagare", "due"));
    }
    // The voucher sits after the money icons: it is a document, not a figure,
    // and the amounts come first at the desk.
    if (appointment.voucher) {
      icons.push(this._payIcon("mdi:ticket-confirmation", "Voucher", "voucher"));
    }
    (appointment.methods || []).forEach((id) => {
      const method = PAYMENT_METHODS.find((entry) => entry.id === id);
      if (method) icons.push(this._payIcon(method.icon, method.label, method.id));
    });
    // Ways of paying used as takings: a voucher or gift card incasso shows
    // its own icon too, once per method.
    const shown = new Set(appointment.methods || []);
    (appointment.payments || []).forEach((item) => {
      if (shown.has(item.method)) return;
      shown.add(item.method);
      const method = PAYMENT_METHODS.find((entry) => entry.id === item.method);
      if (method) icons.push(this._payIcon(method.icon, method.label, method.id));
    });
    return icons.length ? el("span", { class: "pay-icons" }, icons) : null;
  }

  /** Agreed totals of an appointment: total, collected and still owed. */
  /** One appointment's own line: agreed price for her head and her extras. */
  _lineBreakdown(appointment) {
    const treatment = (appointment.treatment_id && this._lookup.treatment.get(appointment.treatment_id)) || null;
    const catalogue = treatment && treatment.price != null ? Number(treatment.price) || 0 : 0;
    const agreed = appointment.price != null ? appointment.price
      : appointment.list_price != null ? appointment.list_price : catalogue;
    const extras = (appointment.extras || []).reduce((sum, id) => {
      const entry = this._accessory(id) || {};
      return sum + (Number(entry.price) || 0);
    }, 0);
    const collected = Math.round(((appointment.payments || []).reduce(
      (sum, item) => sum + (Number(item.amount) || 0), 0)) * 100) / 100;
    return {
      price: Math.max(0, Number(agreed) || 0),
      extras,
      collected,
    };
  }

  /**
   * What the whole booking owes and has taken in.
   *
   * The price of a treatment is per person, and every person of a party is
   * an appointment of her own: the group total adds one line per head, so a
   * two-people spa entry reads twice the single price instead of once. The
   * extras belong to the single person, and the takings are summed over the
   * members because a deposit may sit on the first appointment of the group.
   */
  _appointmentTotals(appointment) {
    const group = this._groupOf(appointment);
    // A cancelled booking is only its own line: the party around it still
    // stands, and its figures are not the price of the cancelled row.
    const live = appointment.status === "confirmed" || appointment.status === "pending";
    const people = live && group.length ? group : [appointment];
    let price = 0;
    let extras = 0;
    let collected = 0;
    people.forEach((member) => {
      const line = this._lineBreakdown(member);
      price += line.price;
      extras += line.extras;
      collected += line.collected;
    });
    const total = Math.round((price + extras) * 100) / 100;
    return {
      total,
      collected: Math.round(collected * 100) / 100,
      due: Math.max(0, Math.round((total - collected) * 100) / 100),
      persons: people.length,
    };
  }

  /** The € status of an appointment: green paid up, amber a taking was
   *  registered, red everything still owed. Figures live in the tooltip. */
  _priceStatusIcon(appointment) {
    const { total, collected, due } = this._appointmentTotals(appointment);
    const tone = due <= 0 ? "ok" : collected > 0 ? "deposit" : "due";
    const label = due <= 0
      ? `Saldato · ${euro(collected)} di ${euro(total)}`
      : collected > 0
        ? `Acconto registrato · ${euro(collected)} di ${euro(total)} · restano ${euro(due)}`
        : `Da pagare · ${euro(total)}`;
    return this._payIcon("mdi:currency-eur", label, tone);
  }

  /** Whether the booking already has money on it (deposit, paid or voucher). */
  _paymentReceived(appointment) {
    return Boolean(appointment.paid || appointment.deposit || appointment.voucher);
  }

  _payIcon(icon, label, tone) {
    return el("span", { class: `pay-icon ${tone}`, title: label }, el("ha-icon", { icon }));
  }

  /**
   * What has been ticked and how much, spelled out.
   *
   * The row shows icons only, so this is where the figures live: every flag
   * with its own amount, the voucher code and the ways of paying. An amount
   * that was never typed stays a dash rather than a zero, because "0" would
   * read as a figure entered on purpose.
   */
  _paymentDetails(payment) {
    const rows = [];
    const amount = (value) => (Number(value) > 0 ? euro(value) : "—");
    if (payment.paid) {
      rows.push(this._detailLine("Pagato", amount(payment.paid_amount), "ok"));
    }
    if (payment.deposit) {
      rows.push(this._detailLine("Acconto", amount(payment.deposit_amount), "deposit"));
    }
    if (payment.voucher) {
      rows.push(
        this._detailLine("Voucher", payment.voucher_code || "senza codice", "voucher")
      );
    }
    if (payment.balance_due) {
      rows.push(this._detailLine("Saldo da pagare", amount(payment.balance_due_amount), "due"));
    }
    const methods = PAYMENT_METHODS.filter(({ id }) =>
      (payment.methods || []).includes(id)
    );
    if (methods.length) {
      rows.push(
        this._detailLine(
          "Come ha pagato",
          methods.map((method) =>
            el("span", { class: `detail-method ${method.id}` },
              el("ha-icon", { icon: method.icon }),
              method.label)
          )
        )
      );
    }
    return rows;
  }

  _detailLine(label, value, tone) {
    return el(
      "div",
      { class: "detail-line" },
      el("span", { class: "detail-label" }, label),
      el("span", { class: `detail-value${tone ? ` ${tone}` : ""}` }, value)
    );
  }

/** One line describing what is ticked, so the fold can be left closed. */
  _paymentSummary(payment) {
    if (!payment) return "";
    const parts = [];
    const amountOf = (key) => {
      const value = parseFloat(String(payment[key] || "").replace(",", "."));
      return Number.isFinite(value) && value > 0 ? euro(value) : "";
    };
    if (payment.paid) {
      const amount = amountOf("paid_amount");
      parts.push(amount ? `Pagato ${amount}` : "Pagato");
    }
    if (payment.deposit) {
      const amount = amountOf("deposit_amount");
      parts.push(amount ? `Acconto ${amount}` : "Acconto");
    }
    if (payment.voucher) {
      parts.push(payment.voucher_code ? `Voucher ${payment.voucher_code}` : "Voucher");
    }
    if (payment.balance_due) {
      const amount = amountOf("balance_due_amount");
      parts.push(amount ? `Saldo da pagare ${amount}` : "Saldo da pagare");
    }
    const methods = PAYMENT_METHODS
      .filter(({ id }) => (payment.methods || []).includes(id))
      .map(({ label }) => label);
    if (methods.length) parts.push(methods.join(" + "));
    return parts.join(" · ");
  }

  /**
   * What the people being booked should cost, or null when no treatment has a
   * price. Only a reminder for the deposit: the card never refuses a payment
   * that does not add up, because the desk has the final word.
   */
  _expectedTotal() {
    const states = this._form.persons
      ? this._form.persons
      : [this._form];
    let sum = 0;
    let priced = false;
    states.forEach((state) => {
      this._treatmentsOf(state).forEach((treat) => {
        const treatment = this._lookup.treatment.get(treat.treatment_id);
        const price = treatment ? treatment.price : null;
        if (price === null || price === undefined || price === "") return;
        sum += Number(price);
        priced = true;
      });
    });
    return priced ? sum : null;
  }

  // ------------------------------------------------------------- report print

  /**
   * Open the day's report in a new tab, where it is the only content and can
   * be printed (or saved) as PDF from the browser. A fresh window is used so
   * the print dialog never covers the dashboard and the report never depends
   * on the card's own shadow styles.
   */
  _printDay() {
    this._openHtmlPage(
      `Spa Booking — Report ${ymd(new Date(`${this._day}T00:00:00`))}`,
      this._dayReportNode()
    );
  }

  /**
   * Open a printable document in a new tab: it is the only content, so the
   * print dialog (and "Save as PDF") acts on the report and nothing else.
   */
  _openHtmlPage(title, bodyNode) {
    const html =
      "<!DOCTYPE html><html lang=\"it\"><head><meta charset=\"utf-8\">" +
      `<title>${title}</title><style>${REPORT_CSS}</style></head>` +
      `<body>${bodyNode.outerHTML}</body></html>`;
    const win = window.open("", "_blank");
    if (!win) {
      this._message = {
        kind: "error",
        text: "Il browser ha bloccato la nuova scheda: consenti i popup per questa pagina e riprova.",
      };
      this._render();
      return;
    }
    win.document.open();
    win.document.write(html);
    win.document.close();
    win.focus();
    // A fresh page whose only content is the report: once it has laid out,
    // open the print dialog, where "Save as PDF" is the destination.
    setTimeout(() => { win.focus(); win.print(); }, 250);
  }

  /** The printable day report: header, summary and the chronological list. */
  _dayReportNode() {
    const dayList = this._appointmentsOfDay(this._day).filter(
      (appointment) =>
        this._categoryMatch(appointment) && this._guestMatch(appointment));
    const exited = dayList.filter((appointment) => appointment.checked_out);
    const list = dayList.filter((appointment) => !appointment.checked_out);
    const totalMin = list.reduce((sum, item) => sum + (this._durationOf(item) || 0), 0);

    const doc = el("div", { class: "report-page" });
    doc.appendChild(el("h1", {}, "Spa Booking — Report del giorno"));
    doc.appendChild(el("div", { class: "report-date" },
      longDay(new Date(`${this._day}T00:00:00`))));

    doc.appendChild(el("div", { class: "report-summary" },
      `${counted(list.length, "appuntamento", "appuntamenti")} · ` +
      `${minutesLabel(totalMin) || "0 min"}` +
      (exited.length ? ` · ${counted(exited.length, "uscito", "usciti")}` : "")));

    const line = (appointment, persons) => {
      const start = parseDate(appointment.start);
      const guest =
        GUEST_TYPES.find((entry) => entry.id === appointment.guest_type) ||
        GUEST_TYPES[1];
      const extras = (appointment.extras || [])
        .map((id) => this._accessory(id));
      let status = "Confermata";
      let statusClass = "";
      if (appointment.offer_state === "unassigned") {
        status = "Da assegnare";
        statusClass = "warn";
      } else if (appointment.offer_state === "offered") {
        status = "Proposta in attesa";
        statusClass = "pending";
      } else if (appointment.status === "pending") {
        status = "In attesa di conferma";
        statusClass = "pending";
      }
      const payment = this._paymentSummary(appointment.payment) || "—";
      return el("div", { class: "report-row" },
        el("div", { class: "r-time" }, timeOf(start)),
        el("div", { class: "r-client" },
          this._clientName(appointment),
          el("span", { class: "r-guest" }, guest.label)),
        el("div", { class: "r-treat" },
          this._treatmentName(appointment),
          extras.length
            ? el("div", { class: "r-extras" },
                `Accessori: ${extras.map((entry) => entry.label).join(", ")}`)
            : null),
        el("div", { class: "r-persons" }, String(persons || 1)),
        el("div", { class: "r-op" },
          this._operatorName(appointment) || "—"),
        el("div", { class: "r-pay" }, payment),
        el("div", { class: `r-status ${statusClass}` }, status));
    };

    doc.appendChild(
      el("div", { class: "report-row report-head" },
        el("div", { class: "r-time" }, "Ora"),
        el("div", { class: "r-code" }, "Codice"),
        el("div", { class: "r-client" }, "Cliente"),
        el("div", { class: "r-treat" }, "Trattamento"),
        el("div", { class: "r-persons" }, "Persone"),
        el("div", { class: "r-op" }, "Operatrice"),
        el("div", { class: "r-pay" }, "Pagamento"),
        el("div", { class: "r-status" }, "Stato")));

    // One row per booking group (same treatment, client and slot), with the
    // number of people; a lone booking is one row of one person.
    const parties = (items) => {
      const grouped = [];
      const seen = new Map();
      items.forEach((appointment) => {
        const key = [
          appointment.treatment_id,
          appointment.client_id,
          appointment.start,
          appointment.operator_id || "",
        ].join("|");
        if (!seen.has(key)) {
          seen.set(key, []);
          grouped.push(seen.get(key));
        }
        seen.get(key).push(appointment);
      });
      return grouped;
    };

    if (!list.length && !exited.length) {
      doc.appendChild(el("div", { class: "r-note" },
        "Nessun appuntamento registrato per questo giorno."));
    } else {
      parties(list).forEach((members) =>
        doc.appendChild(line(members[0], members.length)));
      if (exited.length) {
        doc.appendChild(el("h2", { class: "report-section" }, "Usciti"));
        parties(exited).forEach((members) => {
          const row = line(members[0], members.length);
          row.classList.add("exited");
          doc.appendChild(row);
        });
      }
    }
    return doc;
  }

  /** One person: treatment, masseuse when needed, start time and preview. */
  _bookingBlock(state, index, removable) {
    const box = el("div", { class: "bk-person" });
    const treatments = this._treatmentsOf(state);

    box.appendChild(
      el("div", { class: "bk-person-head" },
        el("span", { class: "dim" }, `Persona ${index + 1}`),
        index === 0 && removable
          ? el("span", { class: "chip" }, "riferimento")
          : null,
        el("div", { class: "spacer" }),
        index > 0
          ? el("button", {
              class: "btn small",
              title: "Copia trattamenti e orari dalla persona 1",
              disabled: this._busy,
              on: { click: () => this._copyFromFirst(index) },
            }, "Copia dalla 1ª")
          : null,
        removable
          ? el("button", {
              class: "icon-btn danger",
              title: "Rimuovi persona",
              disabled: this._busy,
              on: { click: () => this._removePersonAt(index) },
            }, el("ha-icon", { icon: "mdi:close" }))
          : null)
    );

    // One row per treatment: picker and clock on the same line, so the time of
    // every single treatment stands right next to its name — Trattamento 1,
    // Trattamento 2, … — and each keeps its own slot, masseuse and accessories.
    treatments.forEach((treat, j) => {
      box.appendChild(this._bookingTreatRow(state, treat, j, treatments.length > 1));
    });

    // The accessories belong to the person, not to each treatment: one set per
    // person, chosen once here and repeated on every treatment of hers.
    // One more treatment for this person, in another time slot. The button sits
    // inside her own card on purpose: with a party each person adds hers and
    // nobody else's booking is touched. It comes before the accessories.
    box.appendChild(
      el("button", {
        class: "btn primary small add-treat-btn",
        title: `Aggiungi un altro trattamento alla persona ${index + 1}, con un'altra fascia oraria`,
        disabled: this._busy,
        on: { click: () => this._addTreatment(state) },
      }, el("ha-icon", { icon: "mdi:plus-circle-outline" }), "Aggiungi trattamento")
    );

    box.appendChild(this._extrasField(state));

    return box;
  }

  /** One treatment of one person: label, picker and clock on the same row. */
  _bookingTreatRow(person, treat, j, hasMany) {
    const treatment = this._lookup.treatment.get(treat.treatment_id) || null;

    const row = el("div", { class: "bk-treat" });
    row.appendChild(el("span", { class: "bk-treat-label" }, `Trattamento ${j + 1}`));
    row.appendChild(this._treatmentSelect(treat, this._activeTreatments()));
    row.appendChild(this._timeFieldCompact(treat));
    if (hasMany) {
      row.appendChild(el("button", {
        class: "icon-btn bk-treat-x",
        title: "Rimuovi questo trattamento",
        disabled: this._busy,
        on: { click: () => this._removeTreatment(person, treat) },
      }, el("ha-icon", { icon: "mdi:close" })));
    }

    const sub = el("div", { class: "bk-treat-sub" });
    if (treatment && this._treatmentRequiresOperator(treatment)) {
      sub.appendChild(
        el("label", { class: "field" },
          el("span", {}, "Massaggiatrice"),
          this._masseuseSelect(treat, treatment))
      );
    }
    // The accessories are not here: they are one choice for the whole booking
    // and sit under the person cards, so nothing is chosen twice.
    add(sub, this._slotPreview(treat));
    return el("div", { class: "bk-treat-block" }, row, sub);
  }

  _removeTreatment(person, treat) {
    if (!Array.isArray(person.treatments) || person.treatments.length <= 1) return;
    person.treatments = person.treatments.filter((t) => t.uid !== treat.uid);
    this._render();
  }

  /** Add one treatment row to this person only, in her own card. */
  _addTreatment(person) {
    this._treatmentsOf(person).push(this._blankTreatment());
    this._render();
  }

  /** Masseuse picker with "Automatica": follow the able list, in order. */
  _masseuseSelect(state, treatment) {
    const select = el("select", {
      class: "input",
      on: {
        change: (event) => {
          state.operator_id = event.target.value;
          this._render();
        },
      },
    });
    select.appendChild(el("option", { value: "", selected: !state.operator_id },
      "— Automatica —"));
    const pool =
      treatment && this._treatmentRequiresOperator(treatment)
        ? this._operatorsForTreatment(treatment.id)
        : [...this._data.operators].filter((operator) => this._treatmentsOfOperator(operator).length);
    pool
      .slice()
      // Offer order: priority first (lower = sooner), name to break ties,
      // so the desk reads the same order the backend offers in.
      .sort((a, b) => (Number(a.priority) || 0) - (Number(b.priority) || 0) || a.name.localeCompare(b.name))
      .forEach((operator) =>
        select.appendChild(el("option", {
          value: operator.id, selected: state.operator_id === operator.id },
          operator.name))
      );
    if (!pool.length) {
      select.appendChild(el("option", { value: "" }, "Nessuna operatrice abile"));
    }
    return select;
  }

  /** The <select> of treatments, grouped by category. */
  /** Position of a treatment in the saved Trattamenti order; unlisted ones go last. */
  _trtRank(treatment) {
    const order = (this._data.settings && this._data.settings.treatments_order) || [];
    const index = order.indexOf(treatment.id);
    return index < 0 ? Number.MAX_SAFE_INTEGER : index;
  }

  /** Categories as the Trattamenti tab shows them: left column, then right, then the rest. */
  _categoriesInTreatmentOrder() {
    const order = (this._data.settings && this._data.settings.categories_order) || {};
    const ids = [...(order.left || []), ...(order.right || [])];
    const rank = (category) => {
      const index = ids.indexOf(category.id);
      return index < 0 ? Number.MAX_SAFE_INTEGER : index;
    };
    return [...this._data.categories].sort((a, b) => rank(a) - rank(b) || a.name.localeCompare(b.name));
  }

  _treatmentSelect(state, offered) {
    const select = el("select", {
      class: "input",
      on: {
        change: (event) => {
          state.treatment_id = event.target.value;
          if (state.client_results) state.client_results = null;
          this._render();
        },
      },
    });
    select.appendChild(el("option", { value: "" }, "— Scegli il trattamento —"));

    const categories = this._categoriesInTreatmentOrder();
    const grouped = new Map();
    const loose = [];
    offered.forEach((treatment) => {
      if (treatment.category_id && this._lookup.category.has(treatment.category_id)) {
        if (!grouped.has(treatment.category_id)) grouped.set(treatment.category_id, []);
        grouped.get(treatment.category_id).push(treatment);
      } else {
        loose.push(treatment);
      }
    });

    const appendOption = (group, treatment) =>
      group.appendChild(
        el("option", { value: treatment.id, selected: state.treatment_id === treatment.id },
          `${treatment.name} · ${treatment.duration_min}′${treatment.price ? ` · ${euro(treatment.price)}` : ""}`)
      );

    categories.forEach((category) => {
      const items = grouped.get(category.id);
      if (!items || !items.length) return;
      const group = el("optgroup", { label: category.name });
      items
        .sort((a, b) => this._trtRank(a) - this._trtRank(b) || a.name.localeCompare(b.name))
        .forEach((treatment) => appendOption(group, treatment));
      select.appendChild(group);
    });

    if (loose.length) {
      const group = el("optgroup", { label: "Senza categoria" });
      loose
        .sort((a, b) => this._trtRank(a) - this._trtRank(b) || a.name.localeCompare(b.name))
        .forEach((treatment) => appendOption(group, treatment));
      select.appendChild(group);
    }
    return select;
  }

  /**
   * Start-time input bound to a person state object (the date is global).
   * Two selects (hours and minutes) for a direct choice, plus a clock button
   * that opens the native picker — the round clock on a phone.
   */
  _timeField(state, label = "Ora inizio") {
    return el("label", { class: "field" },
      el("span", {}, label),
      this._timeFieldCompact(state));
  }

  /**
   * Start-time controls bound to a treatment object: two selects (hours and
   * minutes) for a direct choice, plus a clock button that opens the native
   * picker — the round clock on a phone. Meant to sit on the same row as the
   * treatment picker.
   */
  _timeFieldCompact(state) {
    const [hour = "10", minute = "00"] = String(state.time || "10:00").split(":");
    const hours = Array.from({ length: 24 }, (_, i) => pad(i));
    const minutes = ["00", "10", "20", "30", "40", "50"];
    const chosenMinute = pad(minute).slice(0, 2);
    if (!minutes.includes(chosenMinute)) {
      minutes.push(chosenMinute);
      minutes.sort();
    }
    const setTime = (h, m) => {
      state.time = `${pad(h)}:${pad(m)}`;
      this._render();
    };
    const picker = (values, current, onPick) => {
      const select = el("select", {
        class: "input",
        on: { change: (event) => onPick(event.target.value) },
      });
      values.forEach((value) =>
        select.appendChild(el("option", { value, selected: value === current }, value)));
      return select;
    };
    // A hidden native input, so the clock button can open the browser's own
    // picker (the round clock on a phone) without showing a second field.
    const native = el("input", {
      class: "time-native",
      type: "time",
      step: "600",
      value: `${pad(hour)}:${chosenMinute}`,
      on: { change: (event) => { state.time = event.target.value || "10:00"; this._render(); } },
    });
    return el("div", { class: "row tight time-row" },
      picker(hours, pad(hour), (value) => setTime(value, chosenMinute)),
      el("span", { class: "dim" }, ":"),
      picker(minutes, chosenMinute, (value) => setTime(pad(hour), value)),
      el("button", {
        type: "button",
        class: "icon-btn",
        title: "Scegli l'ora dall'orologio",
        on: {
          click: () => {
            if (typeof native.showPicker === "function") {
              try { native.showPicker(); } catch (error) { native.click(); }
            } else {
              native.click();
            }
          },
        },
      }, el("ha-icon", { icon: "mdi:clock-outline" })),
      native);
  }

  /** Mode buttons plus the picker or the new-client fields, bound to a state. */
  _clientSection(state) {
    const wrap = el("div", { class: "stack tight" });
    const modeRow = el("div", { class: "row tight" });
    [
      { id: "new", label: "Nuovo cliente / non cliente" },
      { id: "existing", label: "Scheda cliente" },
    ].forEach((mode) =>
      modeRow.appendChild(
        el("button", {
          class: `tab small${state.client_mode === mode.id ? " active" : ""}`,
          on: { click: () => { state.client_mode = mode.id; this._render(); } },
        }, mode.label)
      )
    );
    wrap.appendChild(modeRow);

    if (state.client_mode === "existing") {
      add(wrap, this._clientPicker(state));
    } else {
      wrap.appendChild(
        el("div", { class: "field-grid" },
          el("label", { class: "field" },
            el("span", {}, "Nome"),
            el("input", {
              class: "input", type: "text", value: state.first_name, autocomplete: "off",
              on: { input: (event) => { state.first_name = event.target.value; } },
            })),
          el("label", { class: "field" },
            el("span", {}, "Cognome"),
            el("input", {
              class: "input", type: "text", value: state.last_name, autocomplete: "off",
              on: { input: (event) => { state.last_name = event.target.value; } },
            }))
        )
      );
      wrap.appendChild(
        el("div", { class: "field-grid" },
          el("label", { class: "field" },
            el("span", {}, "Telefono"),
            el("input", {
              class: "input", type: "tel", value: state.phone, autocomplete: "off",
              placeholder: "es. 333 1234567 · estero: +41 79 1234567",
              on: { input: (event) => { state.phone = event.target.value; } },
            })),
          el("label", { class: "field" },
            el("span", {}, "Email"),
            el("input", {
              class: "input", type: "email", value: state.email, autocomplete: "off",
              on: { input: (event) => { state.email = event.target.value; } },
            }))
        )
      );
      wrap.appendChild(
        el("label", { class: "field" },
          el("span", {}, "Note cliente (allergie, pressione, preferenze)"),
          el("textarea", {
            class: "input", rows: "2",
            on: { input: (event) => { state.client_notes = event.target.value; } },
          }, state.client_notes)
        )
      );
      wrap.appendChild(el("div", { class: "hint" },
        "Lascia vuoto il telefono se non lo conosci: l'appuntamento verrà comunque registrato."));
    }
    return wrap;
  }

  _clearForm() {
    this._resetForm();
    this._render();
  }

  /** Empty the new-booking form without redrawing (used when leaving the tab). */
  _resetForm() {
    this._form = {
      ...this._form,
      treatment_id: "",
      operator_id: "",
      client_id: "",
      client_query: "",
      client_results: null,
      first_name: "",
      last_name: "",
      phone: "",
      email: "",
      client_notes: "",
      notes: "",
      extras: [],
      treatments: [],
      people: 1,
      persons: null,
      pending: false,
      guest_type: GUEST_DEFAULT,
      voucher_query: "",
      voucher_code: "",
      stagedPayments: [],
    };
    this._payPopup = null;
    this._resetPayment();
  }


  /** Live preview of the computed slot plus a client side overlap hint. */
  _slotPreview(state = this._form, treatmentId = state.treatment_id) {
    const treatment = this._selectedTreatment(treatmentId);
    if (!treatment) return el("div", { class: "hint" }, "Scegli un trattamento per vedere l'orario di fine.");

    const start = parseLocal(state.date || this._form.date, state.time);
    const end = new Date(start.getTime() + treatment.duration_min * 60000);
    const pause = this._pauseOf(treatment);

    const box = el("div", { class: "preview" });
    box.appendChild(
      el("div", { class: "preview-time" },
        el("ha-icon", { icon: "mdi:clock-outline" }),
        el("strong", {}, `${pad(start.getHours())}:${pad(start.getMinutes())} – ${pad(end.getHours())}:${pad(end.getMinutes())}`),
        pause ? el("span", { class: "dim" }, ` · pausa ${pause}′`) : null,
        el("span", { class: "dim" }, ` · ${minutesLabel(treatment.duration_min)}`))
    );
    if (treatment.price) {
      box.appendChild(el("div", { class: "dim small" }, euro(treatment.price)));
    }

    const dayKey = ymd(start);
    const conflicts = this._appointmentsOfDay(dayKey).filter((appointment) => {
      const otherStart = parseDate(appointment.start);
      const otherEnd = parseDate(appointment.end);
      if (!otherStart || !otherEnd) return false;
      // The pause after an appointment extends the window of its masseuse:
      // a new slot right after it is refused while the category pauses.
      const guard = new Date(otherEnd.getTime() + this._pauseOfAppointment(appointment) * 60000);
      return otherStart < end && guard > start;
    });

    if (state.operator_id) {
      const mine = conflicts.filter((appointment) => appointment.operator_id === state.operator_id);
      if (mine.length) {
        box.appendChild(
          el("div", { class: "hint warn" },
            `La massaggiatrice è già impegnata: ${mine.map((appointment) => `${timeOf(parseDate(appointment.start))} ${this._clientName(appointment)}`).join(", ")}`)
        );
      }
    } else if (state.client_id || this._form.client_id) {
      const clientId = state.client_id || this._form.client_id;
      // The pause does not bind the client: her conflict window stays exact.
      const mine = conflicts.filter((appointment) =>
        appointment.client_id === clientId &&
        appointment.operator_id !== state.operator_id);
      if (mine.length) {
        box.appendChild(
          el("div", { class: "hint warn" },
            `Il cliente è già impegnato: ${mine.map((appointment) => `${timeOf(parseDate(appointment.start))} ${this._treatmentName(appointment)}`).join(", ")}`)
        );
      }
    }

    return box;
  }

  /** Pause (minutes) required after this treatment's category, 0 if none. */
  _pauseOf(treatment) {
    if (!treatment || !treatment.category_id) return 0;
    const category = this._lookup.category.get(treatment.category_id);
    return category ? Math.max(0, Number(category.pause_min) || 0) : 0;
  }

  /** Pause required after an existing appointment, read from its category. */
  _pauseOfAppointment(appointment) {
    return this._pauseOf(this._lookup.treatment.get(appointment.treatment_id));
  }

  _clientPicker(state = this._form) {
    const box = el("div", { class: "stack tight" });
    const selected = this._lookup.client.get(state.client_id);

    box.appendChild(
      el("label", { class: "field" },
        el("span", {}, "Cerca cliente (nome, cognome, telefono, email)"),
        el("input", {
          class: "input",
          type: "search",
          value: state.client_query,
          placeholder: "inizia a scrivere…",
          on: {
            input: (event) => {
              state.client_query = event.target.value;
              this._searchClients(event.target.value, state);
            },
            keydown: (event) => { event.stopPropagation(); },
          },
        })
      )
    );

    if (selected) {
      box.appendChild(
        el("div", { class: "selected-client" },
          el("ha-icon", { icon: "mdi:account-check" }),
          el("div", { class: "sc-body" },
            el("strong", {}, [selected.first_name, selected.last_name].filter(Boolean).join(" ") || selected.phone),
            el("div", { class: "dim small" }, [selected.phone, selected.email].filter(Boolean).join(" · "))
          ),
          el("button", {
            class: "icon-btn",
            title: "Deseleziona",
            on: {
              click: () => {
                state.client_id = "";
                state.client_query = "";
                state.client_results = null;
                this._render();
              },
            },
          }, el("ha-icon", { icon: "mdi:close" }))
        )
      );
    } else {
      // Kept in a dedicated node so the search box keeps focus while typing.
      // The key carries the row/entry uid so every person in the multi form
      // gets its own result list; the flat form keeps the empty key.
      const results = el("div", { "data-client-results": String(state.uid || "") });
      box.appendChild(results);
      this._fillClientResults(results, state);
    }

    return box;
  }

  /** Render the client suggestion list into a container, without a full re-render. */
  _fillClientResults(container, state = this._form) {
    container.innerHTML = "";
    const select = (client) => {
      state.client_id = client.id;
      state.client_results = null;
      state.client_query = [client.first_name, client.last_name].filter(Boolean).join(" ");
      this._render();
    };

    if (state.client_results && state.client_results.length) {
      container.className = "results";
      state.client_results.forEach((client) =>
        container.appendChild(
          el(
            "button",
            { class: "result", type: "button", on: { click: () => select(client) } },
            el("span", {},
              [client.first_name, client.last_name].filter(Boolean).join(" ") || client.phone),
            el("span", { class: "dim small" }, client.phone)
          )
        )
      );
      return;
    }

    container.className = "hint";
    container.appendChild(
      document.createTextNode(
        state.client_query
          ? "Nessun cliente trovato. Usa la scheda «Nuovo cliente»."
          : "Nessuna scheda selezionata: verrà creato un cliente nuovo."
      )
    );
  }

  async _searchClients(query, state = this._form) {
    const trimmed = (query || "").trim();
    const key = String(state.uid || "");
    // The flat single form uses the bare [data-client-results] container; the
    // multi form keys every container by its row/entry uid.
    const findContainer = () =>
      key
        ? this.shadowRoot && this.shadowRoot.querySelector(`[data-client-results="${key}"]`)
        : this.shadowRoot && this.shadowRoot.querySelector("[data-client-results]");

    if (trimmed.length < 2) {
      state.client_results = null;
      const container = findContainer();
      if (container) this._fillClientResults(container, state);
      return;
    }

    try {
      const response = await this._service("search_clients", { query: trimmed, limit: 12 });
      // A slower earlier request must not overwrite a newer one.
      if (String(state.client_query).trim() !== trimmed) return;
      state.client_results = (response && response.clients) || [];
    } catch (error) {
      state.client_results = [];
    }

    const target = findContainer();
    if (target) this._fillClientResults(target, state);
  }

  /** A payment with nothing ticked: "the desk was never told". */
  _blankPayment() {
    return {
      paid: false, paid_amount: "",
      deposit: false, deposit_amount: "",
      voucher: false, voucher_code: "",
      balance_due: false, balance_due_amount: "",
      methods: [],
    };
  }

  /** Payment back to "not specified", used after a booking is written. */
  _resetPayment(state = this._form) {
    state.payment = this._blankPayment();
  }

  /** All-or-nothing booking: create_bookings creates every row or none. The
   *  single-appointment case is just one row, so there is a single path. */
  async _createBookings(force = false) {
    const rows = this._bookingRows();
    if (!rows.length) return;
    if (force) {
      // The desk saw the overlap warning and books anyway: every entry
      // carries the flag, the backend still refuses operator clashes.
      rows.forEach((row) => (row.entries || []).forEach((entry) => {
        entry.force_client_overlap = true;
      }));
    }

    try {
      const response = await this._call("create_bookings", { rows });
      const appointments = (response && response.appointments) || [];
      const first = appointments[0];
      // Staged takings belong to the whole booking: they are written onto
      // its first appointment, where the Incassi box of Fase 3 reads them.
      const staged = this._form.stagedPayments || [];
      if (first && staged.length) {
        for (const item of staged) {
          try {
            await this._call("add_payment", {
              appointment_id: first.id,
              method: item.method,
              date: item.date,
              amount: item.amount,
            });
          } catch (error) {
            /* message already shown */
          }
        }
      }
      const start = first ? parseDate(first.start) : new Date(`${rows[0].entries[0].start}:00`);
      this._day = ymd(start);
      this._form = {
        ...this._form,
        treatment_id: "",
        operator_id: "",
        client_id: "",
        client_results: null,
        client_query: "",
        first_name: "",
        last_name: "",
        phone: "",
        email: "",
        client_notes: "",
        notes: "",
        extras: [],
        treatments: [],
        people: 1,
        persons: null,
        new_client: true,
        stagedPayments: [],
      };
      this._payPopup = null;
      this._resetPayment();
      this._tab = "agenda";
      this._render();
      // The desk decides what the guest gets, if anything: a booking still
      // waiting for confirmation is owed the deposit request, one born
      // confirmed is owed the summary. Nothing goes out on its own.
      await this._offerGuestMessage(appointments);
    } catch (error) {
      // A same-client overlap is not a dead end: offer to book anyway or to
      // go back and fix the form, which stays untouched. An operator clash
      // keeps the plain error, it can never be forced.
      const text = String((error && error.message) || "");
      if (!force && /sovrappone/i.test(text) && /cliente/i.test(text)) {
        this._overlapPopup = { message: text };
        this._render();
        return;
      }
      /* any other message already shown */
    }
  }

  /**
   * Ask the desk what the guest should receive, right after a booking is
   * written.
   *
   * A booking still waiting for confirmation is owed the deposit request, one
   * that is already confirmed is owed the summary. Nothing is ever sent on its
   * own, and a guest with no phone number is told plainly instead of failing
   * on a send that could never arrive.
   */
  async _offerGuestMessage(appointments) {
    const rows = (appointments || []).filter((item) => item && item.id);
    const first = rows[0];
    if (!first) return;
    const phone = (first.client || {}).phone || "";
    if (!phone) {
      this._message = {
        kind: "error",
        text: "L'ospite non ha un numero di telefono: nessun messaggio è stato inviato.",
      };
      this._render();
      return;
    }
    if (first.status === "pending") {
      // With no amount there is nothing to ask for: the desk sets it in the
      // payment sheet and asks from the appointment popup.
      if (!(first.deposit_amount > 0)) {
        this._message = {
          kind: "ok",
          text: "Appuntamento salvato. Imposta l'acconto richiesto nei Totali per poterlo richiedere.",
        };
        this._render();
        return;
      }
      if (!window.confirm("Inviare all'ospite la richiesta d'acconto su WhatsApp?")) return;
      try {
        await this._call("send_deposit_request", { appointment_id: first.id });
      } catch (error) {
        /* message already shown */
      }
      return;
    }
    if (!window.confirm("Inviare all'ospite il riepilogo dell'appuntamento su WhatsApp?")) return;
    try {
      await this._call("send_guest_summary", {
        appointment_ids: rows.map((item) => item.id),
      });
    } catch (error) {
      /* message already shown */
    }
  }

  /** The overlap question, over a backdrop like the other popups. */
  _renderOverlapPopup() {
    const draft = this._overlapPopup || {};
    const retry = draft.retry || { kind: "create" };
    const retryNow = () => {
      this._overlapPopup = null;
      if (retry.kind === "confirm" && retry.id) {
        const appointment = (this._data.appointments || []).find((item) => item.id === retry.id);
        if (appointment) this._confirmAppointment(appointment, true);
        else this._render();
      } else {
        this._createBookings(true);
      }
    };
    const sheet = el("div", { class: "detail-sheet overlap-sheet" },
      el("div", { class: "overlap-icon" },
        el("ha-icon", { icon: "mdi:alert-octagon-outline" })),
      el("h3", { class: "overlap-title" }, "Sovrapposizione cliente"),
      el("div", { class: "detail-text overlap-text" }, draft.message || ""),
      el("div", { class: "hint" },
        "Continuando, l'appuntamento viene inserito anche se si sovrappone. Annullando, torni al form invariato per le modifiche."));
    sheet.appendChild(el("div", { class: "row" },
      el("button", {
        class: "btn primary", disabled: this._busy,
        on: { click: () => retryNow() },
      }, "Continua comunque"),
      el("div", { class: "spacer" }),
      el("button", { class: "btn", on: { click: () => { this._overlapPopup = null; this._render(); } } }, "Annulla e modifica")));
    return el("div", {
      class: "detail-backdrop",
      on: { click: (event) => {
        if (event.target === event.currentTarget) { this._overlapPopup = null; this._render(); }
      } },
    }, sheet);
  }
  _requestRows() {
    const entry = this._form;
    if (!entry.date) return null;
    const count = this._peopleCount();
    if (count < 1) return null;
    const treatments = entry.treatments && entry.treatments.length ? entry.treatments : [this._blankTreatment()];
    const validTreats = treatments.filter((t) => t.treatment_id);
    if (!validTreats.length) return null;

    let clientPayload;
    if (entry.client_mode === "existing") {
      if (!entry.client_id) return null;
      clientPayload = { client_id: entry.client_id };
    } else {
      clientPayload = {
        first_name: entry.first_name || "",
        last_name: entry.last_name || "",
        phone: entry.phone || "",
        email: entry.email || "",
        client_notes: entry.client_notes || "",
      };
      if (!clientPayload.first_name && !clientPayload.last_name && !clientPayload.phone) {
        return null; // no client info at all
      }
    }

    const entries = validTreats.map((t) => ({
      treatment_id: t.treatment_id,
      time: t.time || "10:00",
      extras: entry.extras || [],
      // operator_id intentionally omitted for requests — reception assigns later
    }));

    return {
      date: entry.date,
      people: count,
      entries,
      ...clientPayload,
      guest_type: entry.guest_type || GUEST_DEFAULT,
      notes: entry.notes || "",
      voucher_code: (entry.voucher_code || "").trim().toUpperCase(),
    };
  }

  async _saveRequest() {
    const payload = this._requestRows();
    if (!payload) return;
    try {
      await this._call("create_request", payload);
      this._resetForm();
      this._tab = "nuovo";
      this._nuovoTab = "lista";
      this._render();
    } catch (error) {
      /* message already shown */
    }
  }

  _removeTreatmentAt(personIndex, treatIndex) {
    const entry = this._form;
    const treats = entry.treatments || [];
    if (treats.length <= 1) return;
    treats.splice(treatIndex, 1);
    this._render();
  }

  _addTreatmentAt(personIndex) {
    const entry = this._form;
    const treats = entry.treatments || [];
    treats.push(this._blankTreatment());
    this._render();
  }

  // --------------------------------------------------------------- CALENDARIO

  /**
   * The closures of the month on screen, spelled out.
   *
   * The cells can only carry a lock: the cell is about a dozen characters
   * wide, and the useful part of a closure is its scope and its clock. So the
   * grid says "this day is shut" and this says why, and for how long.
   */
  _renderMonthClosures(closuresByDay, month) {
    const wrap = el("div", { class: "stack tight" });
    const seen = new Map();
    closuresByDay.forEach((list) => {
      list.forEach((closure) => seen.set(closure.id, closure));
    });
    const closures = [...seen.values()].sort((a, b) =>
      `${a.date_from} ${a.start} ${this._closureScopeLabel(a)}`
        .localeCompare(`${b.date_from} ${b.start} ${this._closureScopeLabel(b)}`)
    );

    if (!closures.length) {
      // Say it once, so the reason the calendar looks plain is never a guess.
      if (!(this._data.closures || []).length) {
        wrap.appendChild(el("div", { class: "hint" },
          "Le chiusure inserite in Configurazione → Fasce bloccate compaiono qui, " +
          "giornata intera oppure con il loro orario."));
      }
      return wrap;
    }

    wrap.appendChild(el("h3", {}, `Chiusure di ${MESI[month.getMonth()].toLowerCase()}`));
    closures.forEach((closure) => {
      wrap.appendChild(
        el("div", { class: "row item" },
          el("ha-icon", {
            class: closure.scope === "facility" ? "" : "soft",
            icon: closure.scope === "facility" ? "mdi:lock" : "mdi:lock-outline",
          }),
          el("div", { class: "grow" },
            el("div", { class: "row" },
              el("span", {}, this._closureScopeLabel(closure)),
              closure.label ? el("span", { class: "chip" }, closure.label) : null),
            el("div", { class: "dim small" }, this._closureWhen(closure))))
      );
    });
    return wrap;
  }

  /**
   * Every appointment of the month, one per line, under its day.
   *
   * All of them, not only the coming days: the same view is the way to read a
   * month that is already over, and a column that empties itself when you page
   * back through the calendar answers nothing. Cancelled ones are already gone
   * here, because they are not part of the month that is still to come.
   */
  _renderMonthAgenda(monthAppointments, month, total, totalMin) {
    const side = el("div", { class: "stack tight month-side" });
    side.appendChild(
      el("h3", {}, `Appuntamenti di ${MESI[month.getMonth()].toLowerCase()}`)
    );
    side.appendChild(
      el("div", { class: "dim small" },
        `${counted(total, "appuntamento", "appuntamenti")} · ${minutesLabel(totalMin)}`)
    );

    const days = [...monthAppointments.entries()].sort((a, b) => a[0].localeCompare(b[0]));
    if (!days.length) {
      side.appendChild(el("div", { class: "hint" }, "Nessun appuntamento in questo mese."));
      return side;
    }

    const list = el("div", { class: "month-list" });
    const today = todayStr();
    days.forEach(([key, items]) => {
      const isToday = key === today;
      list.appendChild(
        el("div", { class: `month-day${isToday ? " today" : ""}` },
          el("button", {
            class: "month-day-head",
            on: {
              click: () => {
                this._day = key;
                this._tab = "agenda";
                this._render();
              },
            },
          },
          el("span", {}, shortDay(new Date(`${key}T00:00:00`))),
          isToday ? el("span", { class: "chip" }, "oggi") : null,
          el("span", { class: "badge" }, String(items.length))))
      );

      [...items]
        .sort((a, b) => String(a.start).localeCompare(String(b.start)))
        .forEach((item) => {
          list.appendChild(
            el("div", { class: "month-row" },
              el("span", { class: "month-time" }, timeOf(parseDate(item.start))),
              el("span", { class: "grow month-body" },
                el("div", { class: "month-client" }, this._clientName(item)),
                el("div", { class: "dim small" },
                  `${this._treatmentName(item)} · ${minutesLabel(this._durationOf(item))}`)),
              el("span", { class: "dim small month-op" }, this._operatorName(item)))
          );
        });
    });
    side.appendChild(list);
    return side;
  }

  _renderCalendar() {
    const wrap = el("div", { class: "stack" });
    const month = this._month;
    const monthAppointments = this._appointmentsOfMonth(month);
    const total = [...monthAppointments.values()].reduce((sum, list) => sum + list.length, 0);

    wrap.appendChild(
      el(
        "div",
        { class: "row" },
        // Agenda button: returns to agenda day view. Left of left arrow.
        el("button", {
          class: "btn primary small",
          on: { click: () => { this._agendaTab = "agenda"; this._tab = "agenda"; this._render(); } },
        },
          el("ha-icon", { icon: "mdi:view-day" }),
          el("span", { class: "btn-label" }, "Agenda")
        ),
        el("button", {
          class: "icon-btn",
          on: { click: () => { this._month = addMonths(month, -1); this._render(); } },
        }, el("ha-icon", { icon: "mdi:chevron-left" })),
        el("div", { class: "month-title" }, `${MESI[month.getMonth()]} ${month.getFullYear()}`),
        el("button", {
          class: "icon-btn",
          on: { click: () => { this._month = addMonths(month, 1); this._render(); } },
        }, el("ha-icon", { icon: "mdi:chevron-right" })),
        el("div", { class: "spacer" }),
        el("button", {
          class: "btn small",
          on: { click: () => { this._month = new Date(); this._render(); } },
        }, "Oggi")
      )
    );

    const grid = el("div", { class: "cal" });
    GIORNI.forEach((label) => grid.appendChild(el("div", { class: "cal-dow" }, label)));

    const first = new Date(month.getFullYear(), month.getMonth(), 1);
    const offset = (first.getDay() + 6) % 7;
    const start = addDays(first, -offset);
    const today = new Date();

    // The closures of the very cells being drawn, resolved once for the grid.
    const cells = [];
    for (let index = 0; index < 42; index += 1) {
      const day = addDays(start, index);
      cells.push({ day, key: ymd(day) });
    }
    const closuresByDay = this._closuresByDay(cells.map((cell) => cell.key));

    // Two columns: the month on the left, what happens in it on the right.
    const layout = el("div", { class: "cal-layout" });
    const left = el("div", { class: "stack" });

    cells.forEach(({ day, key }) => {
      const inMonth = day.getMonth() === month.getMonth();
      const items = monthAppointments.get(key) || [];
      const closures = closuresByDay.get(key) || [];
      // A facility closure shuts the door, so it gets the strong mark; a
      // category or an operator closure only takes that part of the offer.
      const shut = closures.some((closure) => closure.scope === "facility");
      const classes = ["cal-day"];
      if (!inMonth) classes.push("dim");
      if (isSameDay(day, today)) classes.push("today");
      if (key === this._day) classes.push("sel");
      if (items.length) classes.push("has");
      if (shut) classes.push("closed");
      else if (closures.length) classes.push("closed-soft");

      // The tooltip is the full answer: the cell is too small for it.
      const tip = [
        items.length ? `${longDay(day)} — ${items.length} appuntamenti` : longDay(day),
        ...closures.map(
          (closure) =>
            `${this._closureScopeLabel(closure)}${closure.label ? ` · ${closure.label}` : ""} — ${this._closureWhen(closure)}`
        ),
      ].join("\n");

      grid.appendChild(
        el(
          "button",
          {
            class: classes.join(" "),
            title: tip,
            on: {
              click: () => {
                this._day = key;
                this._agendaTab = "agenda";
                this._tab = "agenda";
                this._render();
              },
            },
          },
          el("span", { class: "cal-num" }, String(day.getDate())),
          items.length
            ? el("span", { class: "cal-count" },
                String(items.length),
                el("span", { class: "sr-only" }, " appuntamenti"))
            : null,
          closures.length
            ? el("span", { class: "cal-lock" },
                el("ha-icon", { icon: shut ? "mdi:lock" : "mdi:lock-outline" }),
                el("span", { class: "sr-only" },
                  closures.length === 1
                    ? " giorno chiuso"
                    : ` giorni con ${closures.length} chiusure`))
            : null
        )
      );
    });
    left.appendChild(grid);
    add(left, this._renderMonthClosures(closuresByDay, month));

    const monthTotalMin = [...monthAppointments.values()]
      .flat()
      .reduce((sum, item) => sum + (this._durationOf(item) || 0), 0);

    layout.appendChild(left);
    layout.appendChild(
      this._renderMonthAgenda(monthAppointments, month, total, monthTotalMin)
    );
    wrap.appendChild(layout);

    return wrap;
  }

  // ----------------------------------------------------------------- CLIENTI

  // ----------------------------------------------------------------- VOUCHER

  /** Voucher date as it is read in Italy: dd/mm/yyyy from yyyy-mm-dd. */
  _dateIt(value) {
    return value ? String(value).split("-").reverse().join("/") : "";
  }

  _voucherDraftState() {
    if (!this._voucherDraft) {
      this._voucherDraft = {
        buyer_name: "",
        buyer_phone: "",
        recipient_name: "",
        recipient_phone: "",
        people: [{ name: "", treatment_ids: [], extras: [] }],
      };
    }
    return this._voucherDraft;
  }

  /** A voucher can be redeemed only while it is unused and not expired. */
  _voucherUsable(voucher) {
    return voucher.status !== "redeemed" && !voucher.expired;
  }

  _voucherStatusText(voucher) {
    if (voucher.status === "redeemed") return "Riscattato";
    if (voucher.expired) return `Scaduto il ${this._dateIt(voucher.expires_on)}`;
    return `Valido fino al ${this._dateIt(voucher.expires_on)}`;
  }

  /** Vouchers whose code, buyer or recipient match the query. */
  _vouchersMatching(query) {
    const needle = query.trim().toLowerCase();
    return (this._data.vouchers || [])
      .filter((voucher) => {
        if (!needle) return true;
        const haystack = [
          voucher.code, voucher.buyer_name, voucher.buyer_phone,
          voucher.recipient_name, voucher.recipient_phone,
        ].filter(Boolean).join(" ").toLowerCase();
        return haystack.includes(needle);
      })
      .sort((a, b) => String(b.created_at).localeCompare(String(a.created_at)));
  }

  /** Voucher search next to the people stepper: a found voucher fills the booking. */
  _voucherField() {
    const form = this._form;
    const box = el("div", { class: "voucher-find" });
    const applied = form.payment && form.payment.voucher && form.payment.voucher_code;
    if (applied) {
      box.appendChild(
        el("div", { class: "voucher-applied" },
          el("ha-icon", { icon: "mdi:ticket-confirmation-outline" }),
          el("span", {}, applied),
          el("button", {
            class: "icon-btn",
            title: "Togli il voucher",
            on: { click: () => this._clearVoucher() },
          }, el("ha-icon", { icon: "mdi:close" })))
      );
      return box;
    }
    const voucherSearch = el("input", {
      class: "input voucher-form-search",
      type: "search",
      placeholder: "Cerca voucher",
      value: form.voucher_query || "",
    });
    this._searchInputRedraw(voucherSearch, ".voucher-form-search", (value) => {
      form.voucher_query = value;
    });
    box.appendChild(voucherSearch);
    const query = (form.voucher_query || "").trim();
    if (query) {
      const hits = this._vouchersMatching(query).slice(0, 6);
      if (!hits.length) box.appendChild(el("div", { class: "hint small" }, "Nessun voucher trovato."));
      hits.forEach((voucher) => {
        const usable = this._voucherUsable(voucher);
        box.appendChild(
          el("button", {
            class: "search-hit",
            disabled: !usable,
            on: { click: () => this._applyVoucher(voucher) },
          },
            el("span", {}, `${voucher.code} · ${voucher.buyer_name || "—"} → ${voucher.recipient_name || "—"}`),
            el("span", { class: "dim small" }, this._voucherStatusText(voucher)))
        );
      });
    }
    return box;
  }

  /** Fill the booking from the voucher: one person per voucher person, her treatments and accessories. */
  _applyVoucher(voucher) {
    const people = voucher.people && voucher.people.length
      ? voucher.people
      : [{ treatment_ids: [], extras: [] }];
    const persons = people.map((person) => {
      const treatments = (person.treatment_ids || []).map((id) => ({
        ...this._blankTreatment(),
        treatment_id: id,
      }));
      return this._personFrom({
        treatments: treatments.length ? treatments : [this._blankTreatment()],
        extras: [...(person.extras || [])],
      });
    });
    if (persons.length > 1) {
      this._form.persons = persons;
      this._form.people = persons.length;
    } else {
      this._form.persons = null;
      this._form.people = 1;
      this._form.treatments = persons[0].treatments;
      this._form.extras = [...persons[0].extras];
    }
    this._form.payment = { ...(this._form.payment || {}), voucher: true, voucher_code: voucher.code };
    this._form.voucher_query = "";
    this._render();
  }

  _clearVoucher() {
    this._form.payment = { ...(this._form.payment || {}), voucher: false, voucher_code: "" };
    this._render();
  }

  _renderVouchers() {
    const wrap = el("div", { class: "stack" });
    wrap.appendChild(
      el("div", { class: "spa-head" },
        el("div", { class: "spa-head-title" },
          el("ha-icon", { icon: "mdi:ticket-percent-outline" }),
          el("span", {}, "Voucher")))
    );
    const canManage = this._can("manage_clients");
    if (canManage) wrap.appendChild(this._voucherForm());
    wrap.appendChild(this._voucherListBox(canManage));
    wrap.appendChild(this._promoVoucherListBox(canManage));
    return wrap;
  }

  _voucherForm() {
    const draft = this._voucherDraftState();
    const box = el("div", { class: "cfg-box" }, el("h3", {}, "Nuovo voucher"));
    const field = (label, key, placeholder) => el("label", { class: "field" },
      el("span", {}, label),
      el("input", {
        class: "input", type: "text", value: draft[key] || "", placeholder: placeholder || "",
        on: { input: (event) => { draft[key] = event.target.value; } },
      }));
    box.appendChild(el("div", { class: "row tight" },
      field("Nome acquirente", "buyer_name"),
      field("Telefono acquirente", "buyer_phone", "333..."),
      field("Nome destinatario", "recipient_name"),
      field("Telefono destinatario", "recipient_phone", "333...")));

    // Group active treatments by category.
    const activeTreatments = this._data.treatments.filter((treatment) => treatment.active);
    const categories = this._data.categories || [];
    const catOrder = ((this._data.settings && this._data.settings.categories_order) || {});
    const orderedCats = [...categories].sort((a, b) => {
      const leftA = (catOrder.left || []).indexOf(a.id);
      const leftB = (catOrder.left || []).indexOf(b.id);
      const rightA = (catOrder.right || []).indexOf(a.id);
      const rightB = (catOrder.right || []).indexOf(b.id);
      const rankA = leftA >= 0 ? leftA : rightA >= 0 ? rightA + 1000 : 2000;
      const rankB = leftB >= 0 ? leftB : rightB >= 0 ? rightB + 1000 : 2000;
      return rankA - rankB || a.name.localeCompare(b.name);
    });
    const treatmentsByCat = new Map();
    orderedCats.forEach((cat) => {
      const trts = activeTreatments.filter((t) => t.category_id === cat.id);
      if (trts.length) treatmentsByCat.set(cat.id, { category: cat, treatments: trts.sort((a, b) => a.name.localeCompare(b.name)) });
    });
    // Treatments without a category.
    const uncategorized = activeTreatments.filter((t) => !t.category_id || !categories.some((c) => c.id === t.category_id));
    if (uncategorized.length) treatmentsByCat.set("__none__", { category: { id: "__none__", name: "Altri" }, treatments: uncategorized.sort((a, b) => a.name.localeCompare(b.name)) });

    draft.people.forEach((person, index) => {
      const block = el("div", { class: "cfg-box" },
        el("h3", {}, `Persona ${index + 1}`),
        el("label", { class: "field" }, el("span", {}, "Nome (facoltativo)"),
          el("input", {
            class: "input", type: "text", value: person.name || "",
            on: { input: (event) => { person.name = event.target.value; } },
          })));

      // Treatments grouped by category.
      treatmentsByCat.forEach(({ category, treatments }) => {
        const catBox = el("div", { class: "cfg-box cat-box" });
        catBox.appendChild(el("h4", { class: "cat-header" }, category.name));
        const grid = el("div", { class: "checks-grid" });
        treatments.forEach((treatment) => {
          grid.appendChild(el("label", { class: "check" },
            el("input", {
              type: "checkbox",
              checked: person.treatment_ids.includes(treatment.id),
              on: { change: (event) => {
                const on = event.target.checked;
                person.treatment_ids = on
                  ? [...person.treatment_ids, treatment.id]
                  : person.treatment_ids.filter((id) => id !== treatment.id);
              } },
            }),
            el("span", {}, `${treatment.name}${treatment.price ? ` · ${euro(treatment.price)}` : ""}`)));
        });
        catBox.appendChild(grid);
        block.appendChild(catBox);
      });

      // Gift card (monetary value) — not a treatment.
      const giftCardBox = el("div", { class: "cfg-box" });
      giftCardBox.appendChild(el("div", { class: "hint small" }, "Gift card (valore in denaro)"));
      giftCardBox.appendChild(el("label", { class: "field" },
        el("span", {}, "Importo (€)"),
        el("input", {
          class: "input", type: "number", step: "0.01", min: "0",
          value: person.gift_card_amount || "",
          placeholder: "es. 50.00",
          on: { input: (event) => { person.gift_card_amount = event.target.value ? parseFloat(event.target.value) : null; } },
        })));
      giftCardBox.appendChild(el("label", { class: "check" },
        el("input", {
          type: "checkbox",
          checked: !!person.gift_card_amount,
          on: { change: (event) => {
            if (!event.target.checked) person.gift_card_amount = null;
          } },
        }),
        el("span", {}, "Aggiungi gift card a questo voucher")));
      block.appendChild(giftCardBox);

      const extras = el("div", { class: "checks-grid" });
      this._accessories().forEach((extra) => {
        extras.appendChild(el("label", { class: "check" },
          el("input", {
            type: "checkbox",
            checked: person.extras.includes(extra.id),
            on: { change: (event) => {
              const on = event.target.checked;
              person.extras = on
                ? [...person.extras, extra.id]
                : person.extras.filter((id) => id !== extra.id);
            } },
          }),
          el("span", {}, extra.label)));
      });
      block.appendChild(el("div", { class: "hint small" }, "Accessori"));
      block.appendChild(extras);

      if (draft.people.length > 1) {
        block.appendChild(el("button", {
          class: "btn small danger",
          on: { click: () => { draft.people = draft.people.filter((_, i) => i !== index); this._render(); } },
        }, el("ha-icon", { icon: "mdi:delete" }), "Rimuovi persona"));
      }
      // "Copia dalla prima persona" button for persons 2+.
      if (index > 0 && draft.people.length > 1) {
        block.appendChild(el("button", {
          class: "btn small",
          disabled: this._busy,
          on: { click: () => {
            const first = draft.people[0];
            person.treatment_ids = [...first.treatment_ids];
            person.extras = [...first.extras];
            person.gift_card_amount = first.gift_card_amount;
            this._render();
          } },
        }, el("ha-icon", { icon: "mdi:content-copy" }), "Copia dalla prima persona"));
      }
      box.appendChild(block);
    });

    box.appendChild(el("div", { class: "row tight" },
      el("button", {
        class: "btn small",
        disabled: this._busy,
        on: { click: () => { draft.people.push({ name: "", treatment_ids: [], extras: [] }); this._render(); } },
      }, el("ha-icon", { icon: "mdi:plus" }), "Aggiungi persona"),
      el("button", {
        class: "btn primary small",
        disabled: this._busy,
        on: { click: () => this._createVoucher() },
      }, el("ha-icon", { icon: "mdi:ticket-confirmation-outline" }), "Crea voucher")));
    return box;
  }

  async _createVoucher() {
    const draft = this._voucherDraftState();
    // Allow gift card without treatments: each person needs either treatments or a gift card amount.
    if (draft.people.some((person) => !person.treatment_ids.length && !person.gift_card_amount)) {
      this._message = { kind: "error", text: "Ogni persona deve avere almeno un trattamento o una gift card." };
      this._render();
      return;
    }
    try {
      const response = await this._call("create_voucher", {
        buyer_name: draft.buyer_name.trim(),
        buyer_phone: draft.buyer_phone.trim(),
        recipient_name: draft.recipient_name.trim(),
        recipient_phone: draft.recipient_phone.trim(),
        people: draft.people.map((person) => ({
          name: person.name.trim(),
          treatment_ids: person.treatment_ids,
          extras: person.extras,
          gift_card_amount: person.gift_card_amount,
        })),
      });
      this._voucherDraft = null;
    this._waReplyTo = null;
    this._waReplyText = "";
    this._waBusy = false;
    this._waReplyTo = null;
    this._waReplyText = "";
    this._waBusy = false;
      const code = response && response.voucher ? response.voucher.code : "";
      this._message = { kind: "ok", text: `Voucher creato: ${code}` };
      this._render();
    } catch (error) { /* shown */ }
  }

  _voucherListBox(canManage) {
    const box = el("div", { class: "cfg-box" }, el("h3", {}, "Voucher emessi"));
    const voucherListSearch = el("input", {
      class: "input voucher-list-search",
      type: "search",
      placeholder: "Cerca per codice, acquirente o destinatario",
      value: this._voucherQuery || "",
    });
    this._searchInputRedraw(voucherListSearch, ".voucher-list-search", (value) => {
      this._voucherQuery = value;
    });
    box.appendChild(voucherListSearch);
    const list = this._vouchersMatching(this._voucherQuery || "");
    if (!list.length) {
      box.appendChild(el("div", { class: "hint" }, "Nessun voucher."));
      return box;
    }
    list.forEach((voucher) => box.appendChild(this._voucherRow(voucher, canManage)));
    return box;
  }

  _voucherRow(voucher, canManage) {
    const treatmentName = (id) => (this._lookup.treatment.get(id) || {}).name || id;
    const extraLabel = (id) => this._accessoryLabel(id);
    const isAdmin = this._userLevel() === "admin";
    const row = el("div", { class: "row item voucher-row" },
      el("div", { class: "grow" },
        el("div", {}, voucher.code, " · ", el("span", { class: "chip" }, this._voucherStatusText(voucher))),
        el("div", { class: "dim small" },
          `Acquirente ${voucher.buyer_name || "—"} ${voucher.buyer_phone || ""} → Destinatario ${voucher.recipient_name || "—"} ${voucher.recipient_phone || ""}`),
        ...voucher.people.map((person) => {
          const parts = [];
          if (person.treatment_ids.length) parts.push(person.treatment_ids.map(treatmentName).join(", "));
          if (person.gift_card_amount) parts.push(`Gift card: ${euro(person.gift_card_amount)}`);
          if (person.extras.length) parts.push(person.extras.map(extraLabel).join(", "));
          return el("div", { class: "dim small" },
            `${person.name || "Persona"}: ${parts.join(" · ") || "nessun trattamento"}`);
        })));
    // Ordine bottoni: Copia -> Nuovo appuntamento -> Estendi -> Elimina
    // Tutti i bottoni sono in un contenitore actions per l'ordine corretto
    const actions = el("div", { class: "op-actions" });
    
    // 1. Bottone "Copia codice voucher" — visibile a tutti
    const copyBtn = el("button", {
      class: "btn small copy-voucher-code",
      title: "Copia codice voucher",
      disabled: this._busy,
      on: { click: () => {
        navigator.clipboard.writeText(voucher.code);
        this._message = { kind: "info", text: "Codice " + voucher.code + " copiato negli appunti" };
        this._render();
      } },
    });
    copyBtn.appendChild(el("ha-icon", { icon: "mdi:content-copy" }));
    actions.appendChild(copyBtn);
    
    // 2. Bottone "Crea appuntamento con codice" — visibile a tutti
    const appointmentBtn = el("button", {
      class: "btn small",
      title: "Crea appuntamento con codice",
      disabled: this._busy,
      on: { click: () => this._createAppointmentWithVoucher(voucher) }
    });
    appointmentBtn.appendChild(el("ha-icon", { icon: "mdi:calendar-plus" }));
    actions.appendChild(appointmentBtn);
    
    // 3. Bottone "Nuova scadenza" — solo se canManage e non riscattato
    if (canManage && voucher.status !== "redeemed") {
      const extendBtn = el("button", {
        class: "btn small",
        title: "Nuova scadenza",
        disabled: this._busy,
        on: { click: () => { this._voucherExtend = this._voucherExtend === voucher.id ? null : voucher.id; this._render(); } },
      }, el("ha-icon", { icon: "mdi:calendar-clock" }));
      actions.appendChild(extendBtn);
    }
    
    // 4. Bottone "Elimina" — solo se canManage (o admin se riscattato)
    if (canManage) {
      if (voucher.status !== "redeemed") {
        actions.appendChild(el("button", {
          class: "btn small danger",
          title: "Elimina",
          disabled: this._busy,
          on: { click: async () => {
            if (!window.confirm(`Eliminare il voucher ${voucher.code}?`)) return;
            try { await this._call("delete_voucher", { voucher_id: voucher.id }); } catch (error) { /* shown */ }
          } },
        }, el("ha-icon", { icon: "mdi:delete" })));
      } else if (isAdmin) {
        // Only admin can delete redeemed vouchers.
        actions.appendChild(el("button", {
          class: "btn small danger",
          title: "Elimina (solo admin)",
          disabled: this._busy,
          on: { click: async () => {
            if (!window.confirm(`Eliminare il voucher ${voucher.code}? (È già stato riscattato)`)) return;
            try { await this._call("delete_voucher", { voucher_id: voucher.id }); } catch (error) { /* shown */ }
          } },
        }, el("ha-icon", { icon: "mdi:delete" })));
      }
    }
    
    row.appendChild(actions);
    
    // Input per estendere la scadenza (mostrato quando si clicca "Nuova scadenza")
    if (this._voucherExtend === voucher.id) {
      const input = el("input", { class: "input", type: "date", value: voucher.expires_on || "" });
      row.appendChild(el("div", { class: "row tight" }, input,
        el("button", {
          class: "btn primary small",
          disabled: this._busy,
          on: { click: async () => {
            if (!input.value) return;
            try {
              await this._call("extend_voucher", { voucher_id: voucher.id, expires_on: input.value });
              this._voucherExtend = null;
            } catch (error) { /* shown */ }
          } },
        }, el("ha-icon", { icon: "mdi:content-save" }), "Salva scadenza")));
    }
    return row;
  }

  /** Apre la scheda Nuovo appuntamento con il codice voucher già compilato. */
  _createAppointmentWithVoucher(voucher) {
    // Imposta il form in modalità nuova richiesta con il codice voucher
    // Se il voucher ha più persone, usa l'array persons; altrimenti usa i campi flat.
    const voucherPeople = voucher.people || [];
    const hasMultiplePeople = voucherPeople.length > 1;
    // Crea i trattamenti per ogni persona del voucher
    const createPersonTreatments = (person) => {
      return (person.treatment_ids || []).map((id) => ({
        uid: this._uid(),
        treatment_id: id,
        operator_id: "",
        time: "10:00",
      }));
    };

    const voucherPeopleTreatments = voucherPeople.map((person) => ({
      uid: this._uid(),
      treatments: (person.treatment_ids || []).map((id) => ({
        uid: this._uid(),
        treatment_id: id,
        operator_id: "",
        time: "10:00",
      })),
      extras: person.extras || [],
    }));

    if (hasMultiplePeople) {
      // Modalità multi-persona: usa l'array persons
      this._form = {
        treatment_id: "",
        operator_id: "",
        date: todayStr(),
        time: "10:00",
        client_mode: "new",
        client_id: "",
        client_query: "",
        client_results: null,
        first_name: "",
        last_name: "",
        phone: "",
        email: "",
        client_notes: "",
        notes: "",
        treatments: [], // non usato in modalità multi-persona
        payment: {
          paid: false,
          paid_amount: "",
          deposit: false,
          deposit_amount: "",
          voucher: true,
          voucher_code: voucher.code,
          balance_due: false,
          balance_due_amount: "",
          methods: [],
        },
        pending: false,
        guest_type: GUEST_DEFAULT,
        extras: [],
        people: voucherPeopleTreatments.length,
        persons: voucherPeopleTreatments.map((p) => ({
          uid: this._uid(),
          treatments: p.treatments,
          extras: p.extras,
        })),
      };
    } else {
      // Modalità singola persona: usa i campi flat
      const firstPerson = (voucherPeople || [])[0] || {};
      const treatments = (firstPerson.treatment_ids || []).map((id) => ({
        uid: this._uid(),
        treatment_id: id,
        operator_id: "",
        time: "10:00",
      }));
      this._form = {
        treatment_id: "",
        operator_id: "",
        date: todayStr(),
        time: "10:00",
        client_mode: "new",
        client_id: "",
        client_query: "",
        client_results: null,
        first_name: "",
        last_name: "",
        phone: "",
        email: "",
        client_notes: "",
        notes: "",
        treatments: treatments,
        payment: {
          paid: false,
          paid_amount: "",
          deposit: false,
          deposit_amount: "",
          voucher: true,
          voucher_code: voucher.code,
          balance_due: false,
          balance_due_amount: "",
          methods: [],
        },
        pending: false,
        guest_type: GUEST_DEFAULT,
        extras: firstPerson.extras || [],
        people: 1,
        persons: null,
      };
    }
    // Apri la tab "Nuovo" (o "Nuova richiesta")
    this._tab = "nuovo";
    this._render();
  }

  // ------------------------------------------------------- voucher fedelta

  /** The loyalty vouchers matching the current search, newest first. */
  _promoVouchersMatching(query) {
    const needle = (query || "").trim().toLowerCase();
    const rows = (this._data.promo_vouchers || [])
      .slice()
      .sort((a, b) => String(b.created_at || "").localeCompare(String(a.created_at || "")));
    if (!needle) return rows;
    return rows.filter((voucher) => {
      const haystack = [
        voucher.code, voucher.first_name, voucher.last_name, voucher.phone,
      ].join(" ").toLowerCase();
      return haystack.includes(needle);
    });
  }

  _promoVoucherStatusText(voucher) {
    if (voucher.status === "redeemed") return "Riscattato";
    if (voucher.expired) return "Scaduto";
    if (voucher.status === "sent") return "Inviato";
    return "Da inviare";
  }

  _promoVoucherListBox(canManage) {
    const box = el("div", { class: "cfg-box" }, el("h3", {}, "Voucher fedeltà"));
    box.appendChild(el("div", { class: "hint" },
      "Codici personali assegnati ai clienti dopo l'uso dei servizi: sconto " +
      "in percentuale su una spesa minima."));
    const search = el("input", {
      class: "input promo-voucher-list-search",
      type: "search",
      placeholder: "Cerca per codice, nome o telefono",
      value: this._promoVoucherQuery || "",
    });
    this._searchInputRedraw(search, ".promo-voucher-list-search", (value) => {
      this._promoVoucherQuery = value;
    });
    box.appendChild(search);
    const list = this._promoVouchersMatching(this._promoVoucherQuery || "");
    if (!list.length) {
      box.appendChild(el("div", { class: "hint" }, "Nessun voucher fedeltà."));
      return box;
    }
    list.forEach((voucher) => box.appendChild(this._promoVoucherRow(voucher, canManage)));
    return box;
  }

  _promoVoucherRow(voucher, canManage) {
    const name = [voucher.first_name, voucher.last_name].filter(Boolean).join(" ") || "—";
    const expires = voucher.expires_on ? this._dateIt(voucher.expires_on) : "—";
    const statusClass = voucher.status === "redeemed" ? "ok" : (voucher.expired ? "danger" : "");
    const row = el("div", { class: "row item voucher-row" },
      el("div", { class: "grow" },
        el("div", {},
          el("strong", {}, voucher.code), " · ",
          el("span", { class: `chip ${statusClass}` }, this._promoVoucherStatusText(voucher))),
        el("div", { class: "dim small" },
          `${name}${voucher.phone ? " · " + voucher.phone : ""}`),
        el("div", { class: "dim small" },
          `Sconto ${voucher.discount_percent}% · Spesa ${euro(voucher.min_spend)}–${euro(voucher.max_spend)} · Scade ${expires}`)));
    if (canManage) {
      const actions = el("div", { class: "op-actions" });
      if (voucher.status !== "redeemed") {
        actions.appendChild(el("button", {
          class: "btn small",
          title: "Segna come riscattato",
          disabled: this._busy,
          on: { click: async () => {
            if (!window.confirm(`Segnare il voucher ${voucher.code} come riscattato?`)) return;
            try { await this._call("redeem_promo_voucher", { voucher_id: voucher.id }); }
            catch (error) { /* shown */ }
          } },
        }, el("ha-icon", { icon: "mdi:check-circle-outline" })));
      }
      actions.appendChild(el("button", {
        class: "btn small danger",
        title: "Elimina",
        disabled: this._busy,
        on: { click: async () => {
          if (!window.confirm(`Eliminare il voucher fedeltà ${voucher.code}?`)) return;
          try { await this._call("delete_promo_voucher", { voucher_id: voucher.id }); }
          catch (error) { /* shown */ }
        } },
      }, el("ha-icon", { icon: "mdi:delete" })));
      row.appendChild(actions);
    }
    return row;
  }

  // ------------------------------------------------------------ RICHIESTE

  _renderRichiestaForm() {
    const treatments = this._activeTreatments();
    if (!treatments.length) {
      return el("div", { class: "empty" }, "Non ci sono trattamenti attivi. Creane uno nella scheda Configurazione.");
    }
    const wrap = el("div", { class: "stack form-compact" });
    if (this._can("config")) wrap.appendChild(this._richiestaFormHeader());
    add(wrap, this._peopleRow());
    if (this._peopleMin() > 1) {
      wrap.appendChild(el("div", { class: "hint" }, `Questo trattamento richiede almeno ${this._peopleMin()} persone insieme nella stessa fascia.`));
    }

    // Two-column layout with draggable blocks (like Notifiche tab).
    const columns = this._colsGrid("richiesta");
    const left = el("div", { class: "stack tight form-col", "data-col": "left" });
    const right = el("div", { class: "stack tight form-col", "data-col": "right" });
    this._blockWire(columns, "richiesta");

    const block = (id, title, ...children) => {
      const node = el("div", { class: "cfg-box" }, el("h3", {}, title));
      add(node, children);
      return this._tagBlock(id, this._richiestaSection(id, node));
    };

    // Left column: Trattamenti (includes people picker, treatments, accessories)
    left.appendChild(block("trattamenti", "Trattamenti", this._richiestaBlock()));

    // Right column: Ospite + Cliente + Note
    right.appendChild(block("ospite", "Ospite", this._guestField(this._form)));
    right.appendChild(block("cliente", "Cliente", this._clientSection(this._form)));
    right.appendChild(block("note", "Note",
      el("label", { class: "field" },
        el("span", {}, "Note"),
        el("textarea", {
          class: "input", rows: "3",
          on: { input: (event) => { this._form.notes = event.target.value; } },
        }, this._form.notes || "")
      )
    ));
    right.appendChild(block("voucher", "Voucher",
      el("label", { class: "field" },
        el("span", {}, "Codice voucher"),
        el("input", {
          class: "input",
          placeholder: "VCH-XXXXXXXX",
          style: "text-transform: uppercase",
          on: { input: (event) => { this._form.voucher_code = event.target.value; } },
        }, this._form.voucher_code || "")
      ),
      el("div", { class: "hint" },
        "Se l'ospite ha un voucher regalo, il suo codice va qui: viene controllato subito e lo vede anche la reception.")
    ));

    this._placeBlocks(left, right, "richiesta_order");
    columns.appendChild(left);
    columns.appendChild(right);
    wrap.appendChild(columns);

    wrap.appendChild(
      el("div", { class: "row" },
        el("button", {
          class: "btn primary",
          disabled: this._busy,
          on: { click: () => this._saveRequest() },
        }, "Salva richiesta"),
        el("div", { class: "spacer" }),
        el("button", {
          class: "btn ghost",
          disabled: this._busy,
          on: { click: () => { this._resetForm(); this._render(); } },
        }, "Annulla")
      )
    );
    return wrap;
  }

  /** One box for the Richiesta form: treatments + shared accessories (like _bookingBlock). */
  _richiestaBlock() {
    const entry = this._form;
    const treats = entry.treatments && entry.treatments.length ? entry.treatments : [this._blankTreatment()];

    const box = el("div", { class: "bk-person" });

    box.appendChild(
      el("div", { class: "bk-person-head" },
        el("span", { class: "dim" }, "Trattamenti"),
        el("div", { class: "spacer" }))
    );

    treats.forEach((treat, j) => {
      box.appendChild(this._richiestaTreatRow(entry, treat, j, treats.length > 1));
    });

    // "Aggiungi trattamento" button inside the box.
    box.appendChild(
      el("button", {
        class: "btn primary small add-treat-btn",
        title: "Aggiungi un altro trattamento con un'altra fascia oraria",
        disabled: this._busy,
        on: { click: () => this._addRichiestaTreatment() },
      }, el("ha-icon", { icon: "mdi:plus-circle-outline" }), "Aggiungi trattamento")
    );

    // Shared accessories for all treatments (like Nuovo: per person, here per request).
    box.appendChild(this._extrasField(entry));

    return box;
  }

  /** One treatment row in the Richiesta form: no masseuse, no per-treatment accessories. */
  _richiestaTreatRow(entry, treat, j, hasMany) {
    const treatment = this._lookup.treatment.get(treat.treatment_id) || null;

    const row = el("div", { class: "bk-treat" });
    row.appendChild(el("span", { class: "bk-treat-label" }, `Trattamento ${j + 1}`));
    row.appendChild(this._treatmentSelect(treat, this._activeTreatments()));
    row.appendChild(this._timeFieldCompact(treat));
    if (hasMany) {
      row.appendChild(el("button", {
        class: "icon-btn bk-treat-x",
        title: "Rimuovi questo trattamento",
        disabled: this._busy,
        on: { click: () => this._removeRichiestaTreatmentAt(entry.treatments.indexOf(treat)) },
      }, el("ha-icon", { icon: "mdi:close" })));
    }

    const sub = el("div", { class: "bk-treat-sub" });
    // NO masseuse/operator field for requests — reception assigns later.
    add(sub, this._slotPreview(treat));
    // NO accessories here: they are shared at the bottom of the box.

    return el("div", { class: "bk-treat-block" }, row, sub);
  }

  /** Add a new treatment row to the request. */
  _addRichiestaTreatment() {
    const entry = this._form;
    if (!entry.treatments) entry.treatments = [];
    entry.treatments.push(this._blankTreatment());
    this._render();
  }

  /** Remove a treatment row from the request. */
  _removeRichiestaTreatmentAt(index) {
    const entry = this._form;
    const treats = entry.treatments || [];
    if (treats.length <= 1) return;
    treats.splice(index, 1);
    this._render();
  }

  _renderWhatsapp() {
    const wrap = el("div", { class: "wa-list" });
    const sensorState = this._hass.states["sensor.spa_booking_messaggi_whatsapp_esterni"];
    const messages = (sensorState && sensorState.attributes && sensorState.attributes.messages) || [];
    if (!messages.length) {
      return el("div", { class: "empty" }, "Nessun messaggio esterno ricevuto.");
    }
    messages.forEach((msg) => {
      const card = el("div", { class: "wa-card" });
      // Header: icon, sender, time
      add(card, el("div", { class: "wa-header" },
        el("ha-icon", { icon: "mdi:whatsapp" }),
        el("span", { class: "wa-sender" }, msg.chat_id || "Sconosciuto"),
        el("span", { class: "wa-time" }, msg.received_at ? msg.received_at.split("T")[1].substring(0, 5) : "")
      ));
      // Message text
      add(card, el("div", { class: "wa-text" }, msg.text || ""));
      // Actions
      add(card, el("div", { class: "wa-actions" },
        el("button", {
          class: "btn small",
          on: { click: (e) => { e.preventDefault(); this._replyToWhatsapp(msg.chat_id); } }
        }, el("ha-icon", { icon: "mdi:reply" }), "Rispondi"),
        el("button", {
          class: "btn small",
          on: { click: (e) => { e.preventDefault(); this._createRequestFromWhatsapp(msg.chat_id); } }
        }, el("ha-icon", { icon: "mdi:calendar-plus" }), "Crea richiesta"),
        el("button", {
          class: "btn small",
          on: { click: () => this._saveAsClient(msg.chat_id) }
        }, el("ha-icon", { icon: "mdi:account-group-plus" }), "Salva cliente")
      ));
      // Inline reply form for this specific message
      if (this._waReplyTo === msg.chat_id) {
        add(card, el("div", { class: "wa-reply" },
          el("input", {
            class: "wa-reply-input",
            type: "text",
            placeholder: "Scrivi la risposta...",
            value: this._waReplyText || "",
            on: { input: (event) => { this._waReplyText = event.target.value; } },
          }),
          el("button", {
            class: "btn small",
            disabled: this._waBusy,
            on: { click: () => this._sendWaReply(msg.chat_id) }
          }, this._waBusy ? "Invio..." : "Invia"),
          el("button", {
            class: "btn small ghost",
            on: { click: () => { this._waReplyTo = null; this._waReplyText = ""; this._render(); } }
          }, "Annulla")
        ));
      }
      add(wrap, card);
    });
    return wrap;
  }

  _replyToWhatsapp(chatId, originalText) {
    // Toggle an inline reply form for this chat
    if (this._waReplyTo === chatId) {
      this._waReplyTo = null;
      this._render();
      return;
    }
    this._waReplyTo = chatId;
    this._waReplyText = "";
    this._render();
  }

  _sendWaReply(chatId) {
    const text = (this._waReplyText || "").trim();
    if (!text) return;
    this._waBusy = true;
    this._call("send_external_message", { chat_id: chatId, text }).then(() => {
      this._waReplyTo = null;
      this._waReplyText = "";
      this._waBusy = false;
      this._message = { kind: "ok", text: "Risposta inviata." };
      this._render();
    }).catch(() => {
      this._waBusy = false;
      this._message = { kind: "error", text: "Invio fallito." };
      this._render();
    });
  }

  _createRequestFromWhatsapp(chatId) {
    let phone = (chatId || "").replace(/\s+/g, "");
    if (phone.includes("@")) phone = phone.split("@")[0];
    if (!phone.startsWith("39")) phone = "39" + phone;
    // The request form reads this._form, not this._draft: write the number
    // there and open it as a new client, so the phone field is the one shown.
    this._form = { ...this._form, phone, client_mode: "new" };
    this._tab = "nuovo";
    this._nuovoTab = "nuova";
    this._waReplyTo = null;
    this._waReplyText = "";
    this._render();
  }

  _saveAsClient(chatId) {
    let phone = (chatId || "").replace(/\s+/g, "");
    if (phone.includes("@")) phone = phone.split("@")[0];
    if (!phone.startsWith("39")) phone = "39" + phone;
    if (!this._draft) this._draft = {};
    this._call("save_client", {
      first_name: "Esterno",
      last_name: "",
      phone: phone,
      category_id: "external",
      client_notes: "Numero esterno WhatsApp - salvato da card",
    }).then(() => {
      this._message = { kind: "ok", text: "Salvato come cliente esterno." };
      this._render();
    }).catch(() => {
      this._message = { kind: "error", text: "Salvataggio fallito." };
    });
  }

  /** How many requests arrived from the website and nobody has opened yet. */
  _webUnreadCount() {
    const list = (this._data && this._data.requests) || [];
    return list.filter((req) => req.source === "web" && !req.seen).length;
  }

  /** Open the request list and consider the website's requests seen. */
  async _openWebRequests() {
    this._tab = "nuovo";
    this._nuovoTab = "lista";
    this._render();
    try {
      await this._service("mark_requests_seen", {});
      await this._loadData();
    } catch (error) {
      /* the badge stays where it was; the next click retries */
    }
    this._render();
  }

  _renderRichiesteList() {
    const wrap = el("div", { class: "stack" });
    const rawList = this._data.requests || [];
    if (!rawList.length) {
      return el("div", { class: "empty" }, "Nessuna richiesta in attesa.");
    }
    // Enrich raw requests with client info, formatted date, treatment names, etc.
    const list = rawList.map((req) => {
      const client = this._lookup.client.get(req.client_id) || null;
      const dateIt = req.date ? this._dateIt(req.date) : "—";
      const entries = (req.entries || []).map((e) => {
        const t = this._lookup.treatment.get(e.treatment_id) || {};
        return {
          ...e,
          treatment_name: t.name || e.treatment_id || "—",
          start: e.time || "",
        };
      });
      return {
        ...req,
        client: client
          ? {
              id: client.id,
              first_name: client.first_name || "",
              last_name: client.last_name || "",
              full_name: [client.first_name, client.last_name].filter(Boolean).join(" "),
              phone: client.phone || "",
              email: client.email || "",
            }
          : { id: "", first_name: "", last_name: "", full_name: "—", phone: "—", email: "" },
        entries,
        date_it: dateIt,
        is_confirmed: req.status === "confirmed",
        code: req.code || req.id || "—",
      };
    });

    list.forEach((req) => {
      const client = req.client || {};
      const name = client.full_name || "—";
      const phone = client.phone || "—";
      const dateIt = req.date_it || "—";
      const people = req.people || 1;
      const trList = (req.entries || []).map((e) =>
        `${e.treatment_name || "—"}${e.start ? ` · ${e.start}` : ""}`
      ).join(", ") || "—";
      const code = req.code || "—";
      const status = req.is_confirmed ? "Confermata" : "In attesa";
      const row = el("div", { class: "row tight request-card" },
        el("div", { class: "stack tight" },
          el("div", { class: "spa-title" }, name),
          el("div", { class: "dim small" }, `Tel: ${phone}`),
          el("div", { class: "dim small" }, `${dateIt} · Persone: ${people}`),
          el("div", { class: "dim small" }, trList),
          req.voucher_code
            ? el("div", { class: "dim small" }, `Voucher: ${req.voucher_code}`)
            : null,
          el("div", { class: "dim small" }, `Codice: ${code} · ${status}`)
        ),
        el("div", { class: "row tight" },
          !req.is_confirmed
            ? el("button", {
                class: "btn primary small",
                disabled: this._busy,
                on: { click: async () => {
                  try { await this._call("confirm_request", { request_id: req.id }); } catch (error) { /* shown */ }
                } },
              }, "Conferma")
            : null,
          el("button", {
            class: "btn ghost small",
            disabled: this._busy,
            on: { click: async () => {
              try { await this._call("send_request_message", { request_id: req.id }); } catch (error) { /* shown */ }
            } },
          }, "Invia messaggio"),
          el("button", {
            class: "btn ghost small",
            disabled: this._busy,
            on: { click: () => this._editRequest(req) },
          }, "Modifica"),
          el("button", {
            class: "icon-btn danger",
            title: "Elimina",
            disabled: this._busy,
            on: { click: async () => {
              if (!window.confirm("Eliminare questa richiesta?")) return;
              try { await this._call("delete_request", { request_id: req.id }); } catch (error) { /* shown */ }
            } },
          }, el("ha-icon", { icon: "mdi:delete" }))
        )
      );
      wrap.appendChild(row);
    });
    return wrap;
  }

    /** Load a request into the form for editing. */
  _editRequest(req) {
    this._nuovoTab = "nuova";
    this._form = {
      ...this._form,
      date: req.date,
      people: req.people,
      treatments: (req.entries || []).map((e) => ({
        uid: this._uid(),
        treatment_id: e.treatment_id,
        time: e.time || "10:00",
        operator_id: e.operator_id || "",
      })),
      extras: req.entries && req.entries.length ? (req.entries[0].extras || []) : [],
      client_mode: req.client_id ? "existing" : "new",
      client_id: req.client_id || "",
      first_name: req.client?.first_name || "",
      last_name: req.client?.last_name || "",
      phone: req.client?.phone || "",
      email: req.client?.email || "",
      client_notes: req.client?.client_notes || "",
      notes: req.notes || "",
      voucher_code: req.voucher_code || "",
      guest_type: req.guest_type || GUEST_DEFAULT,
      new_client: !req.client_id,
    };
    this._tab = "nuovo";
    this._nuovoTab = "nuova";
    this._render();
  }

_renderClients() {
    const wrap = el("div", { class: "stack" });
    // Only a manager and above may open or change a client card; lower levels
    // keep the search and the read-only detail.
    const canManageClients = this._can("manage_clients");

    const clientSearch = el("input", {
      class: "input grow client-search",
      type: "search",
      value: this._clientQuery,
      placeholder: "Cerca per nome, cognome, telefono o email",
    });
    this._searchInputRedraw(clientSearch, ".client-search", (value) => {
      this._clientQuery = value;
    });
    const searchRow = el("div", { class: "row" }, clientSearch);
    if (canManageClients) {
      searchRow.appendChild(
        el("button", {
          class: "btn small",
          on: {
            click: () => {
              // "Nuova scheda" opens the create form instead of just clearing
              // the selection: a missing client_id tells the backend to create
              // a brand new record.
              this._clientSelected = null;
              this._clientEditing = null;
              this._clientCreating = true;
              this._clientDraft = { first_name: "", last_name: "", phone: "", email: "", notes: "", promo_opt_in: true };
              this._clientQuery = "";
              this._render();
            },
          },
        }, el("ha-icon", { icon: "mdi:account-plus" }), "Nuova scheda")
      );
    }
    wrap.appendChild(searchRow);

    if (this._clientCreating && canManageClients) {
      add(wrap, this._renderNewClient());
      return wrap;
    }

    if (this._clientSelected) {
      add(wrap, this._clientDetail(this._clientSelected));
      return wrap;
    }

    const query = this._clientQuery.trim().toLowerCase();
    const clients = this._data.clients
      .filter((client) =>
        !query ||
        [client.first_name, client.last_name, client.phone, client.email, client.notes]
          .join(" ")
          .toLowerCase()
          .includes(query)
      )
      .sort((a, b) =>
        `${a.last_name} ${a.first_name}`.localeCompare(`${b.last_name} ${b.first_name}`)
      );

    if (!clients.length) {
      wrap.appendChild(el("div", { class: "empty" }, query ? "Nessun cliente trovato." : "Nessuna scheda cliente."));
      return wrap;
    }

    const list = el("div", { class: "stack tight" });
    clients.forEach((client) => {
      const appointments = this._clientAppointments(client.id);
      const last = appointments.find((appointment) => appointment.status !== "cancelled");
      const whatsapp = waLink(client.phone);
      const row = el("div", { class: "client-row" });

      const main = el(
        "button",
        {
          class: "client-main",
          on: {
            click: () => {
              this._clientSelected = client.id;
              this._clientEditing = null;
              this._render();
            },
          },
        },
        el("div", { class: "client-name" },
          [client.first_name, client.last_name].filter(Boolean).join(" ") || client.phone || "Senza nome",
          client.promo_opt_in === false
            ? el("span", { class: "promo-off", title: "Promo disattivate" },
                el("ha-icon", { icon: "mdi:bell-off-outline" }))
            : null),
        el("div", { class: "dim small" },
          [client.phone, client.email].filter(Boolean).join(" · ") || "—"),
        el("div", { class: "dim small" },
          last
            ? `Ultimo: ${shortDate(last.start)} · ${appointments.length} ${
                appointments.length === 1 ? "visita" : "visite"
              }`
            : "Nessuna visita")
      );
      row.appendChild(main);

      // The same three buttons, with the same look, as the operator list: filled
      // phone and WhatsApp, plain new appointment.
      const actions = el("div", { class: "appt-actions" });
      if (client.phone) {
        actions.appendChild(
          el("a", { class: "btn small tel", href: telHref(client.phone), title: client.phone },
            el("ha-icon", { icon: "mdi:phone" }))
        );
      }
      if (whatsapp) {
        actions.appendChild(
          el("a", { class: "btn small wa", href: whatsapp, target: "_blank", rel: "noopener", title: "WhatsApp" },
            el("ha-icon", { icon: "mdi:whatsapp" }))
        );
      }
      if (this._can("book")) {
        actions.appendChild(
          el("button", {
            class: "btn small",
            title: "Nuovo appuntamento",
            on: {
              click: () => {
                this._form.client_mode = "existing";
                this._form.client_id = client.id;
                this._form.client_query = [client.first_name, client.last_name].filter(Boolean).join(" ");
                this._form.client_results = null;
                this._clientSelected = null;
                this._tab = "nuovo";
                this._nuovoTab = "appuntamento";
                this._render();
              },
            },
          }, el("ha-icon", { icon: "mdi:calendar-plus" }))
        );
      }
      row.appendChild(actions);
      list.appendChild(row);
    });

    wrap.appendChild(list);
    return wrap;
  }

  /** "Iscritto alle promo" checkbox: one flag per client card, on by default.
   *  Unchecking it keeps the guest out of every promo, automatic or manual. */
  _promoOptInField(draft) {
    return el("label", { class: "check" },
      el("input", {
        type: "checkbox",
        checked: draft.promo_opt_in !== false,
        on: { change: (event) => { draft.promo_opt_in = event.target.checked; } },
      }),
      el("span", { class: "promo-choice" },
        el("span", {}, "Iscritto alle promo"),
        el("span", { class: "hint" },
          "Se lo togli, questo cliente non riceverà più i messaggi promozionali.")));
  }

  /** Create form: save_client without a client_id builds a brand new record. */
  _renderNewClient() {
    const wrap = el("div", { class: "stack tight" });
    const draft = this._clientDraft || { first_name: "", last_name: "", phone: "", email: "", notes: "", promo_opt_in: true };

    wrap.appendChild(
      el("div", { class: "row" },
        el("h3", {}, "Nuova scheda cliente"),
        el("div", { class: "spacer" }),
        el("button", {
          class: "btn small",
          on: {
            click: () => {
              this._clientCreating = false;
              this._clientDraft = null;
              this._render();
            },
          },
        }, el("ha-icon", { icon: "mdi:arrow-left" }), "Indietro")
      )
    );

    wrap.appendChild(
      el("div", { class: "row" },
        el("label", { class: "field" }, el("span", {}, "Nome"),
          el("input", { class: "input", type: "text", value: draft.first_name, autocomplete: "off",
            on: {
              input: (event) => { draft.first_name = event.target.value; },
              keydown: (event) => { event.stopPropagation(); },
              keyup: (event) => { event.stopPropagation(); },
              keypress: (event) => { event.stopPropagation(); },
            } })),
        el("label", { class: "field" }, el("span", {}, "Cognome"),
          el("input", { class: "input", type: "text", value: draft.last_name, autocomplete: "off",
            on: {
              input: (event) => { draft.last_name = event.target.value; },
              keydown: (event) => { event.stopPropagation(); },
              keyup: (event) => { event.stopPropagation(); },
              keypress: (event) => { event.stopPropagation(); },
            } })))
    );
    wrap.appendChild(
      el("div", { class: "row" },
        el("label", { class: "field" }, el("span", {}, "Telefono"),
          el("input", { class: "input", type: "tel", value: draft.phone, autocomplete: "off",
            placeholder: "es. 333 1234567 · estero: +41 79 1234567",
            on: {
              input: (event) => { draft.phone = event.target.value; },
              keydown: (event) => { event.stopPropagation(); },
              keyup: (event) => { event.stopPropagation(); },
              keypress: (event) => { event.stopPropagation(); },
            } })),
        el("label", { class: "field" }, el("span", {}, "Email"),
          el("input", { class: "input", type: "email", value: draft.email, autocomplete: "off",
            on: {
              input: (event) => { draft.email = event.target.value; },
              keydown: (event) => { event.stopPropagation(); },
              keyup: (event) => { event.stopPropagation(); },
              keypress: (event) => { event.stopPropagation(); },
            } })))
    );
    wrap.appendChild(
      el("label", { class: "field" }, el("span", {}, "Note e preferenze"),
        el("textarea", { class: "input", rows: "3",
          on: {
            input: (event) => { draft.notes = event.target.value; },
            keydown: (event) => { event.stopPropagation(); },
            keyup: (event) => { event.stopPropagation(); },
            keypress: (event) => { event.stopPropagation(); },
          } }, draft.notes))
    );

    wrap.appendChild(this._promoOptInField(draft));

    wrap.appendChild(
      el("div", { class: "row" },
        el("button", {
          class: "btn primary",
          disabled: this._busy,
          on: {
            click: async () => {
              if (![draft.first_name, draft.last_name, draft.phone].some((value) => String(value || "").trim())) {
                this._message = { kind: "error", text: "Inserisci almeno nome, cognome o telefono." };
                this._render();
                return;
              }
              try {
                const result = await this._call("save_client", { ...draft });
                const created = result && result.client;
                this._clientCreating = false;
                this._clientDraft = null;
                if (created && created.id) {
                  this._clientSelected = created.id;
                  this._message = { kind: "ok", text: "Scheda cliente creata." };
                } else {
                  this._message = { kind: "ok", text: "Scheda cliente salvata." };
                }
                this._render();
              } catch (error) {
                /* message already shown */
              }
            },
          },
        }, el("ha-icon", { icon: "mdi:check" }), "Crea scheda"),
        el("button", {
          class: "btn",
          on: {
            click: () => {
              this._clientCreating = false;
              this._clientDraft = null;
              this._render();
            },
          },
        }, "Annulla")
      )
    );

    wrap.appendChild(el("div", { class: "hint" },
      "Lascia vuoto il telefono se non lo conosci: la scheda verrà comunque registrata."));

    return wrap;
  }

  _clientDetail(clientId) {
    const client = this._lookup.client.get(clientId);
    const box = el("div", { class: "stack" });
    if (!client) return box;

    const canEditClient = this._can("manage_clients");
    const headerRow = el("div", { class: "row" },
      el("button", { class: "btn small", on: { click: () => { this._clientSelected = null; this._render(); } } },
        el("ha-icon", { icon: "mdi:arrow-left" }), "Indietro"),
      el("div", { class: "spacer" }));
    if (canEditClient) {
      headerRow.appendChild(
        el("button", {
          class: "btn small",
          title: this._clientEditing ? "Annulla le modifiche" : "Modifica scheda",
          on: {
            click: () => {
              this._clientEditing = this._clientEditing ? null : {
                first_name: client.first_name || "",
                last_name: client.last_name || "",
                phone: client.phone || "",
                email: client.email || "",
                notes: client.notes || "",
                promo_opt_in: client.promo_opt_in !== false,
              };
              this._render();
            },
          },
        }, el("ha-icon", { icon: this._clientEditing ? "mdi:close" : "mdi:pencil" }))
      );
      headerRow.appendChild(
        el("button", {
          class: "btn small danger",
          disabled: this._busy,
          title: "Elimina scheda cliente",
          on: { click: () => this._confirmDeleteClient(client) },
        }, el("ha-icon", { icon: "mdi:delete" }))
      );
    }
    // The phone on the card is the one the WhatsApp chat opens, and the one the
    // reminders and the summaries go to: same number, one place to correct.
    const clientPhone = String(client.phone || "").trim();
    if (clientPhone) {
      headerRow.appendChild(
        el("a", { class: "btn small tel", href: telHref(clientPhone), title: `Chiama ${clientPhone}` },
          el("ha-icon", { icon: "mdi:phone" }))
      );
      headerRow.appendChild(
        el("a", {
          class: "btn small wa", href: waLink(clientPhone), target: "_blank", rel: "noopener",
          title: `WhatsApp ${clientPhone}`,
        }, el("ha-icon", { icon: "mdi:whatsapp" }))
      );
    }
    box.appendChild(headerRow);

    // Two columns: who this client is on the left, what they came here for on
    // the right. The desk reads the card and the history side by side instead
    // of scrolling past every visit to reach the next thing. On a narrow screen
    // the columns stack, the history below.
    const columns = el("div", { class: "two-col" });
    const left = el("div", { class: "stack tight" });
    const right = el("div", { class: "stack tight" });

    left.appendChild(el("h3", {},
      [client.first_name, client.last_name].filter(Boolean).join(" ") || "Senza nome"));

    if (this._clientEditing) {
      const draft = this._clientEditing;
      left.appendChild(
        el("div", { class: "field-grid" },
          el("label", { class: "field" }, el("span", {}, "Nome"),
            el("input", { class: "input", type: "text", value: draft.first_name,
              on: { input: (event) => { draft.first_name = event.target.value; } } })),
          el("label", { class: "field" }, el("span", {}, "Cognome"),
            el("input", { class: "input", type: "text", value: draft.last_name,
              on: { input: (event) => { draft.last_name = event.target.value; } } })))
      );
      left.appendChild(
        el("div", { class: "field-grid" },
          el("label", { class: "field" }, el("span", {}, "Telefono"),
            el("input", { class: "input", type: "tel", value: draft.phone,
              on: { input: (event) => { draft.phone = event.target.value; } } })),
          el("label", { class: "field" }, el("span", {}, "Email"),
            el("input", { class: "input", type: "email", value: draft.email,
              on: { input: (event) => { draft.email = event.target.value; } } })))
      );
      left.appendChild(
        el("label", { class: "field" }, el("span", {}, "Note e preferenze"),
          el("textarea", { class: "input", rows: "3",
            on: { input: (event) => { draft.notes = event.target.value; } } }, draft.notes))
      );
      left.appendChild(this._promoOptInField(draft));
      left.appendChild(
        el("div", { class: "row" },
          el("button", {
            class: "btn primary",
            disabled: this._busy,
            on: {
              click: async () => {
                try {
                  await this._call("save_client", { client_id: client.id, ...draft });
                  this._clientEditing = null;
                } catch (error) { /* shown */ }
              },
            },
          }, "Salva"))
      );
    } else {
      const details = [];
      if (client.phone) details.push(client.phone);
      if (client.email) details.push(client.email);
      if (client.notes) details.push(client.notes);
      left.appendChild(el("div", { class: "dim small" }, details.join(" · ") || "—"));
      left.appendChild(el("div", { class: "dim small" },
        client.promo_opt_in === false ? "Promo: disattivate" : "Promo: iscritto"));
    }

    // Loyalty vouchers this client earned: shown always, with expiry, and
    // deletable by whoever manages clients.
    const promoVouchers = (this._data.promo_vouchers || [])
      .filter((voucher) => voucher.client_id === client.id)
      .sort((a, b) => String(b.created_at || "").localeCompare(String(a.created_at || "")));
    if (promoVouchers.length) {
      left.appendChild(el("h3", {}, "Voucher fedeltà"));
      promoVouchers.forEach((voucher) => {
        left.appendChild(this._promoVoucherRow(voucher, canEditClient));
      });
    }

    const appointments = this._clientAppointments(client.id);
    right.appendChild(el("h3", {}, `Storico (${appointments.length})`));
    if (!appointments.length) {
      right.appendChild(el("div", { class: "hint" }, "Nessun appuntamento registrato."));
    } else {
      appointments.slice(0, 25).forEach((appointment) => {
        const start = parseDate(appointment.start);
        const cancelled = appointment.status === "cancelled";
        right.appendChild(
          el("div", { class: `appt compact${cancelled ? " cancelled" : ""}` },
            el("div", { class: "appt-main" },
              el("div", { class: "appt-time" },
                `${pad(start.getDate())}/${pad(start.getMonth() + 1)}/${start.getFullYear()}`),
              el("div", { class: "appt-body" },
                el("div", { class: "appt-client" }, this._treatmentName(appointment)),
                el("div", { class: "appt-treat" },
                  `${timeOf(start)} · ${minutesLabel(this._durationOf(appointment))}`,
                  this._operatorName(appointment)
                    ? el("span", { class: "sep" }, "·")
                    : null,
                  this._operatorName(appointment)
                    ? el("span", { class: "dim" }, this._operatorName(appointment))
                    : null),
                cancelled ? el("span", { class: "chip warn" }, "annullato") : null,
                !cancelled && start >= new Date() && start <= addDays(new Date(), 2)
                  ? el("button", {
                      class: "btn small",
                      title: "Annulla appuntamento",
                      disabled: this._busy,
                      on: { click: () => this._confirmCancel(appointment) },
                    }, el("ha-icon", { icon: "mdi:calendar-remove" }))
                  : null,
                cancelled
                  ? el("button", {
                      class: "btn small danger",
                      title: "Elimina definitivamente",
                      disabled: this._busy,
                      on: { click: () => this._confirmDeleteAppointment(appointment) },
                    }, el("ha-icon", { icon: "mdi:delete" }))
                  : null))
          )
        );
      });
    }

    columns.appendChild(left);
    columns.appendChild(right);
    box.appendChild(columns);

    return box;
  }

  /**
   * Light/dark switch. It has its own configuration sub-tab rather than sitting
   * among the data tabs, and it is stored in the settings, so the choice
   * follows the operator to every device of the spa instead of staying in the
   * browser that made it.
   */
  _appearanceBox() {
    const settings = this._data.settings || {};
    const raw = String(settings.appearance || "").trim().toLowerCase();
    const current = APPEARANCE_MODES.includes(raw) ? raw : "auto";

    const select = el("select", {
      class: "input",
      disabled: this._busy,
      on: {
        change: async (event) => {
          const mode = event.target.value;
          try {
            await this._call("update_settings", { appearance: mode });
          } catch (error) {
            /* shown by _call */
          }
        },
      },
    });
    APPEARANCE_MODES.forEach((mode) =>
      select.appendChild(
        el("option", { value: mode, selected: mode === current }, APPEARANCE_LABELS[mode])
      )
    );

    const box = el("div", { class: "cfg-box" }, el("h3", {}, "Aspetto"));
    box.appendChild(
      el("label", { class: "field" }, el("span", {}, "Modalità"), select)
    );
    box.appendChild(
      el("div", { class: "hint" },
        current === "auto"
          ? "La card segue il tema attivo di Home Assistant. Scegliendo Chiaro o Scuro vale solo per questa card, su tutti i dispositivi."
          : `La card resta ${APPEARANCE_LABELS[current].toLowerCase()} su tutti i dispositivi, indipendentemente dal tema di Home Assistant.`)
    );
    // Titolo in testata: written here, stored in the settings so it follows the
    // operator to every device. The draft keeps a half-typed title across the
    // redraws the card does while other settings load.
    const draft = this._appearanceDraft || (this._appearanceDraft = {});
    const titleValue = draft.card_title != null
      ? draft.card_title
      : (settings.card_title || this._config.title || "Gestione SPA");
    box.appendChild(
      el("div", { class: "row tight" },
        el("label", { class: "field" },
          el("span", {}, "Titolo della card"),
          el("input", { class: "input", type: "text", maxlength: "60",
            value: titleValue,
            on: { input: (event) => { draft.card_title = event.target.value; } } })),
        el("button", {
          class: "btn small",
          disabled: this._busy,
          on: { click: async () => {
            try {
              await this._call("update_settings", {
                card_title: (draft.card_title || "").trim(),
              });
              this._appearanceDraft = null;
              this._message = { kind: "ok", text: "Titolo salvato." };
            } catch (error) { /* shown by _call */ }
          } },
        }, "Salva titolo"))
    );
    box.appendChild(el("div", { class: "hint" },
      "Il titolo in testata della card, su tutti i dispositivi. Lascia vuoto " +
      "per tornare al titolo della configurazione della card."));
    return box;
  }

  /**
   * Sito web: the switch for the public booking API, the token the website
   * must send, and the window the site may offer.
   *
   * The website is another origin and has no Lovelace session, so the public
   * views it calls cannot ask who is speaking; the token is what keeps a
   * stranger from filing requests, and it is shown here on purpose — the desk
   * has to copy it into the site. The hours are the reception's, not the spa's
   * real opening times: they only say which starts the website may propose,
   * and they can be changed here whenever the season changes them.
   */
  _webBox() {
    const settings = this._data.settings || {};
    const enabled = !!settings.web_enabled;
    const token = String(settings.web_token || "");
    const draft = this._webDraft || (this._webDraft = {});
    const openTime = draft.open_time != null
      ? draft.open_time : (settings.web_open_time || "09:00");
    const closeTime = draft.close_time != null
      ? draft.close_time : (settings.web_close_time || "20:00");
    const stepMin = draft.step_min != null
      ? draft.step_min
      : (settings.web_step_min != null ? settings.web_step_min : 30);
    const maxDays = draft.max_days_ahead != null
      ? draft.max_days_ahead
      : (settings.web_max_days_ahead != null ? settings.web_max_days_ahead : 60);
    // The address the website must reach: the one the desk is using right now,
    // which is the public one when the card is opened from outside.
    const base = `${location.origin}/api/spa_booking/public`;

    const copy = async (value, label) => {
      try {
        await navigator.clipboard.writeText(value);
        this._message = { kind: "ok", text: label + " copiato." };
      } catch (error) {
        this._message = {
          kind: "error",
          text: "Copia non riuscita: seleziona il testo e copialo a mano.",
        };
      }
      this._render();
    };

    const box = el("div", { class: "cfg-box" }, el("h3", {}, "Sito web"));

    box.appendChild(
      el("label", { class: "check" },
        el("input", {
          type: "checkbox",
          checked: enabled,
          on: { change: async (event) => {
            const on = event.target.checked;
            try {
              await this._call("update_settings", { web_enabled: on });
              this._message = {
                kind: "ok",
                text: on ? "Sito web attivato." : "Sito web disattivato.",
              };
              this._render();
            } catch (error) { /* shown by _call */ }
          } },
        }),
        el("span", {}, "Accetta richieste dal sito web"))
    );
    box.appendChild(el("div", { class: "hint" },
      "Quando è attivo, il sito può leggere trattamenti e orari liberi e " +
      "inviare le richieste degli ospiti, che compaiono in Nuovo › Lista " +
      "richieste solo dopo la conferma della reception. Quando è spento " +
      "l'indirizzo non risponde."));

    if (!enabled && !token) {
      box.appendChild(el("div", { class: "hint" },
        "Attiva il sito per generare il token da copiare nella pagina web."));
    } else {
      box.appendChild(
        el("label", { class: "field" },
          el("span", {}, "Token per il sito"),
          el("input", { class: "input", type: "text", readonly: true, value: token }))
      );
      box.appendChild(
        el("div", { class: "row tight" },
          el("button", {
            class: "btn small",
            disabled: this._busy || !token,
            on: { click: () => copy(token, "Token") },
          }, el("ha-icon", { icon: "mdi:content-copy" }), "Copia token"),
          el("button", {
            class: "btn small",
            disabled: this._busy,
            on: { click: async () => {
              if (!window.confirm(
                "Rigenerare il token?\n\nIl sito smette subito di funzionare " +
                "finché non incolli il nuovo token nella pagina web."
              )) return;
              try {
                await this._call("regenerate_public_token", {});
              } catch (error) { /* shown by _call */ }
            } },
          }, el("ha-icon", { icon: "mdi:refresh" }), "Rigenera token"))
      );
      box.appendChild(el("div", { class: "hint" },
        "Il sito deve inviare il token a ogni chiamata (Authorization: Bearer). " +
        "Rigeneralo se è finito in mano a qualcuno che non dovrebbe averlo."));
    }

    box.appendChild(
      el("label", { class: "field" },
        el("span", {}, "Indirizzo per il sito"),
        el("input", { class: "input", type: "text", readonly: true, value: base }))
    );
    box.appendChild(
      el("div", { class: "row tight" },
        el("button", {
          class: "btn small",
          disabled: this._busy,
          on: { click: () => copy(base, "Indirizzo") },
        }, el("ha-icon", { icon: "mdi:content-copy" }), "Copia indirizzo"))
    );
    box.appendChild(el("div", { class: "hint" },
      "Da qui il sito legge i trattamenti, gli orari liberi e invia le " +
      "richieste. È l'indirizzo con cui apri ora Home Assistant: se lo apri " +
      "dalla rete interna, copia l'indirizzo pubblico."));

    // The offered day may be cut in two by the break: the morning runs from
    // the opening to "Mattina: alle", the afternoon from "Pomeriggio: dalle"
    // to the closing. With the afternoon left empty the day is whole.
    box.appendChild(
      el("div", { class: "row tight" },
        el("label", { class: "field" },
          el("span", {}, "Mattina: dalle"),
          el("input", { class: "input", type: "time", value: openTime,
            on: { input: (event) => { draft.open_time = event.target.value; } } })),
        el("label", { class: "field" },
          el("span", {}, "Mattina: alle"),
          el("input", { class: "input", type: "time", value: draft.break_start || "",
            on: { input: (event) => { draft.break_start = event.target.value; } } })))
    );
    box.appendChild(
      el("div", { class: "row tight" },
        el("label", { class: "field" },
          el("span", {}, "Pomeriggio: dalle"),
          el("input", { class: "input", type: "time", value: draft.break_end || "",
            on: { input: (event) => { draft.break_end = event.target.value; } } })),
        el("label", { class: "field" },
          el("span", {}, "Pomeriggio: alle"),
          el("input", { class: "input", type: "time", value: closeTime,
            on: { input: (event) => { draft.close_time = event.target.value; } } })))
    );
    box.appendChild(
      el("div", { class: "row tight" },
        el("label", { class: "field" },
          el("span", {}, "Propone ogni (minuti)"),
          el("input", { class: "input", type: "number", min: "5", max: "240", step: "5",
            value: String(stepMin),
            on: { input: (event) => {
              const value = parseInt(event.target.value, 10);
              draft.step_min = Number.isFinite(value) && value >= 5 ? value : 5;
            } } })),
        el("label", { class: "field" },
          el("span", {}, "Giorni in avanti"),
          el("input", { class: "input", type: "number", min: "1", max: "365", step: "1",
            value: String(maxDays),
            on: { input: (event) => {
              const value = parseInt(event.target.value, 10);
              draft.max_days_ahead = Number.isFinite(value) && value >= 1 ? value : 1;
            } } })))
    );
    box.appendChild(el("div", { class: "hint" },
      "Sono gli orari che il sito può proporre, non quelli reali della spa: la " +
      "reception li cambia quando cambia la stagione. Con il pomeriggio vuoto " +
      "il sito propone un solo orario continuo; se lasci vuota solo una delle " +
      "due fasce, offre quella sola. Le chiusure e le prenotazioni " +
      "dell'agenda vengono comunque rispettate."));
    box.appendChild(
      el("label", { class: "field" },
        el("span", {}, "WhatsApp avvisi dal sito"),
        el("input", { class: "input", type: "tel", placeholder: "391234567890",
          value: draft.notify_whatsapp != null
            ? draft.notify_whatsapp : (settings.web_notify_whatsapp || ""),
          on: { input: (event) => { draft.notify_whatsapp = event.target.value; } } }))
    );
    box.appendChild(el("div", { class: "hint" },
      "Numero della reception che riceve un messaggio quando un ospite manda " +
      "una richiesta dal sito. Vuoto = nessun avviso: la richiesta arriva " +
      "comunque in Nuovo › Lista richieste."));
    box.appendChild(
      el("div", { class: "row tight" },
        el("button", {
          class: "btn primary small",
          disabled: this._busy,
          on: { click: async () => {
            try {
              await this._call("update_settings", {
                web_open_time: (draft.open_time || "").trim(),
                web_close_time: (draft.close_time || "").trim(),
                web_break_start: (draft.break_start || "").trim(),
                web_break_end: (draft.break_end || "").trim(),
                web_step_min: draft.step_min ?? 30,
                web_max_days_ahead: draft.max_days_ahead ?? 60,
                web_notify_whatsapp: (draft.notify_whatsapp || "").trim(),
              });
              this._message = { kind: "ok", text: "Impostazioni del sito salvate." };
              this._render();
            } catch (error) { /* shown by _call */ }
          } },
        }, "Salva orari"))
    );
    box.appendChild(
      el("div", { class: "row tight" },
        el("button", {
          class: "btn small",
          disabled: this._busy,
          on: { click: async () => {
            try {
              const result = await this._service("web_snippet", {});
              const text = String((result && result.snippet) || "");
              if (!text) {
                this._message = { kind: "error",
                  text: "Codice non trovato in www/spa_booking/spa-booking-form.txt." };
                this._render();
                return;
              }
              try {
                if (navigator.clipboard && typeof navigator.clipboard.writeText === "function") {
                  await navigator.clipboard.writeText(text);
                  this._message = { kind: "ok", text: "Codice per il sito copiato negli appunti." };
                  this._render();
                  return;
                }
              } catch (e) {}
              try {
                const ta = document.createElement("textarea");
                ta.value = text;
                ta.style.position = "fixed";
                ta.style.left = "-9999px";
                document.body.appendChild(ta);
                ta.focus();
                ta.select();
                document.execCommand("copy");
                document.body.removeChild(ta);
                this._message = { kind: "ok", text: "Codice per il sito copiato negli appunti." };
                this._render();
                return;
              } catch (e2) {
                try {
                  if (typeof this._copyToClipboard === "function") {
                    await this._copyToClipboard(text, "Codice per il sito");
                    return;
                  }
                } catch (e3) {}
              }
              this._message = { kind: "error", text: "Copia non riuscita: seleziona il testo e copialo a mano." };
              this._render();
            } catch (error) {
              this._message = { kind: "error", text: "Copia non riuscita." };
              this._render();
            }
          } },
        }, el("ha-icon", { icon: "mdi:content-copy" }), "Copia codice per il sito"))
    );

    return box;
  }

  /** Settings tab: every box on two columns (see _renderSettings). */
  _renderSettings() {
    const wrap = el("div", { class: "stack" + (this._settingsEditMode ? " form-edit" : "") });
    // Pencil toggle: in edit mode the four boxes drag by their handle.
    if (this._can("config")) wrap.appendChild(this._settingsHeader());

    const columns = this._colsGrid("settings");
    const left = el("div", { class: "stack tight form-col", "data-col": "left" });
    const right = el("div", { class: "stack tight form-col", "data-col": "right" });

    // One wrapper per box, so edit mode can tag and drag them.
    const block = (id, node) => this._tagBlock(id, this._settingsSection(id, node));

    const exportBox = el("div", { class: "cfg-box" },
      el("h3", {}, "Backup / Ripristino"),
      el("div", { class: "hint" },
        "Esporta o ripristina l'intero backup dell'integrazione in formato JSON."),
      el("div", { class: "row tight" },
        el("button", {
          class: "btn small",
          disabled: this._busy,
          on: { click: async () => {
            try {
              this._busy = true;
              this._render();
              const result = await this._service("export_all", {});
              const payload = (result && result.data) || result;
              if (!payload) {
                this._message = { kind: "error", text: "Esportazione JSON fallita." };
                return;
              }
              const json = JSON.stringify(payload, null, 2);
              const blob = new Blob([json], { type: "application/json;charset=utf-8;" });
              const url = window.URL.createObjectURL(blob);
              const date = new Date().toISOString().slice(0, 10);
              const link = document.createElement("a");
              link.href = url;
              link.download = `spa_booking_backup_${date}.json`;
              document.body.appendChild(link);
              link.click();
              document.body.removeChild(link);
              window.URL.revokeObjectURL(url);
              this._message = { kind: "ok", text: "Backup JSON scaricato." };
            } catch (e) {
              this._message = { kind: "error", text: "Errore: " + (e.message || e) };
            } finally {
              this._busy = false;
              this._render();
            }
          } },
        }, el("ha-icon", { icon: "mdi:database-export" }), "Esporta JSON"),
        el("button", {
          class: "btn small",
          disabled: this._busy,
          on: { click: () => {
            const input = document.createElement("input");
            input.type = "file";
            input.accept = ".json,application/json";
            input.style.display = "none";
            input.onchange = async (event) => {
              const file = event.target.files && event.target.files[0];
              if (!file) return;
              try {
                this._busy = true;
                this._render();
                const text = await file.text();
                let parsed;
                try {
                  parsed = JSON.parse(text);
                } catch (err) {
                  this._message = { kind: "error", text: "File JSON non valido." };
                  return;
                }
                await this._service("import_all", { payload: parsed });
                this._message = { kind: "ok", text: "Backup JSON ripristinato correttamente." };
              } catch (e) {
                this._message = { kind: "error", text: "Errore ripristino: " + (e.message || e) };
              } finally {
                this._busy = false;
                this._render();
                if (input.parentNode) input.parentNode.removeChild(input);
              }
            };
            document.body.appendChild(input);
            input.click();
          } },
        }, el("ha-icon", { icon: "mdi:database-import" }), "Ripristina JSON"))
    );

    left.appendChild(block("export_all", exportBox));

    const versionBox = el("div", { class: "cfg-box" }, el("h3", {}, "Versione del programma"));
    const line = (label, value) =>
      el("div", { class: "detail-line" },
        el("span", { class: "detail-label" }, label),
        el("span", { class: "detail-value" }, value));
    versionBox.appendChild(line("Card", CARD_VERSION));
    versionBox.appendChild(line("Integrazione", this._integrationVersion || "—"));
    versionBox.appendChild(line("Home Assistant",
      (this._hass && this._hass.config && this._hass.config.version) || "—"));
    versionBox.appendChild(el("div", { class: "hint" },
      "La versione della card si aggiorna con il comando di ricarica della card."));

    // Client import / export.
    const clientsBox = el("div", { class: "cfg-box" }, el("h3", {}, "Clienti"));
    clientsBox.appendChild(
      el("div", { class: "row tight" },
        el("button", {
          class: "btn small",
          disabled: this._busy,
          on: { click: async () => {
            try {
              this._busy = true;
              this._render();
              const result = await this._call("export_clienti_csv", {});
              const blob = new Blob([result.csv || ""], { type: "text/csv;charset=utf-8;" });
              const url = URL.createObjectURL(blob);
              const link = document.createElement("a");
              link.href = url;
              link.download = "clienti_spa_booking.csv";
              document.body.appendChild(link);
              link.click();
              document.body.removeChild(link);
              URL.revokeObjectURL(url);
            } catch (error) { /* shown */ }
            finally { this._busy = false; this._render(); }
          } },
        }, el("ha-icon", { icon: "mdi:download" }), "Esporta CSV")));
    clientsBox.appendChild(el("div", { class: "hint" },
      "Scarica un file CSV con Nome, Cognome, Telefono, Email, Note di tutti i clienti. " +
      "Modificalo in un foglio di calcolo e re-importalo qui sotto."));
    const fileInput = el("input", {
      type: "file", accept: ".csv,text/csv",
      style: "display: none",
      on: { change: async (event) => {
        const file = event.target.files && event.target.files[0];
        if (!file) return;
        try {
          this._busy = true;
          this._render();
          const text = await file.text();
          const result = await this._call("import_clienti_csv", { csv: text });
          this._message = {
            kind: "ok",
            text: result.created + " clienti importati, " + result.skipped + " gia' presenti.",
          };
        } catch (error) { /* shown */ }
        finally { event.target.value = ""; this._busy = false; this._render(); }
      } },
    });
    clientsBox.appendChild(fileInput);
    clientsBox.appendChild(
      el("button", {
        class: "btn small",
        disabled: this._busy,
        on: { click: () => fileInput.click() },
      }, el("ha-icon", { icon: "mdi:upload" }), "Importa CSV"));
    clientsBox.appendChild(el("div", { class: "hint" },
      "Carica un CSV (Nome, Cognome, Telefono, Email, Note). I clienti con telefono " +
      "gia' esistente vengono ignorati."));

    // Four boxes on two columns: appearance + version on the left, clients +
    // website on the right, until the user drags them somewhere else (the
    // saved order of impostazioni_order is applied below). On a phone the
    // grid falls back to one column (see the 720px media query).
    left.appendChild(block("aspetto", this._appearanceBox()));
    left.appendChild(block("versione", versionBox));
    right.appendChild(block("clienti", clientsBox));
    right.appendChild(block("sito", this._webBox()));
    this._placeBlocks(left, right, "impostazioni_order");

    columns.appendChild(left);
    columns.appendChild(right);
    wrap.appendChild(columns);
    return wrap;
  }

  // ----------------------------------------------------------------- TELECAMERE

  /**
   * Telecamere tab: every configured camera as a still feed, one tile each.
   * The list is edited in place (pencil menu → Modifica) and stored in the
   * settings as camera_entities; a camera that no longer exists shows an off
   * tile instead of a broken image. Tap a feed to open Home Assistant's own
   * camera dialog.
   */
  /** Flat, user-ordered camera tiles of the Telecamere tab, normalised. */
  _camTiles() {
    const settings = (this._data && this._data.settings) || {};
    const raw = settings.camera_entities || [];
    return raw
      .map((item) => this._spaNormTile(item))
      .filter((tile) => tile && tile.entity_id);
  }

  _renderTelecamere() {
    const wrap = el("div", { class: "stack" });
    if (this._can("config")) wrap.appendChild(this._camHeader());
    const tiles = this._camTiles();
    if (!tiles.length && !this._camEditMode) {
      wrap.appendChild(
        el("div", { class: "empty" },
          "Nessuna telecamera configurata. Usa la matita in alto a destra, poi Modifica, per aggiungere le telecamere.")
      );
    } else {
      wrap.appendChild(this._renderCameraGrid(tiles));
    }
    if (this._camTileDlg) wrap.appendChild(this._camTileDialog());
    if (this._camAddDlg) wrap.appendChild(this._camAddDialog());
    return wrap;
  }

  /** Title row of the Telecamere tab: the pencil menu, or the edit actions. */
  _camHeader() {
    const head = el("div", { class: "spa-head" });
    head.appendChild(
      el("div", { class: "spa-head-title" },
        el("ha-icon", { icon: "mdi:cctv" }),
        el("span", {}, this._camEditMode ? "Modifica Telecamere" : "Telecamere"))
    );
    if (this._camEditMode) {
      head.appendChild(
        el("div", { class: "spa-head-actions" },
          el("button", {
            class: "btn small",
            title: "Aggiungi telecamera",
            on: { click: () => this._camAddOpen() },
          }, el("ha-icon", { icon: "mdi:plus" })),
          el("button", {
            class: "btn primary small",
            title: "Fine modifica",
            on: { click: () => this._camEditExit() },
          }, el("ha-icon", { icon: "mdi:check" })))
      );
      return head;
    }
    head.appendChild(
      el("button", {
        class: "icon-btn spa-menu-btn",
        title: "Modifica telecamere",
        on: { click: () => this._camEditEnter() },
      }, el("ha-icon", { icon: "mdi:pencil" }))
    );
    return head;
  }

  /** The pencil itself toggles edit mode: no intermediate Modifica menu. */
  _camEditEnter() {
    this._camEditMode = true;
    this._render();
  }

  /** Leave edit mode; nothing to save, every change was already written. */
  _camEditExit() {
    this._camEditMode = false;
    this._camTileDlg = null;
    this._camAddDlg = false;
    this._camDrag = null;
    this._render();
  }

  /** One single flat grid with every configured camera, in user order. */
  _renderCameraGrid(tiles) {
    const grid = el("div", {
      class: "cameras" + (this._camEditMode ? " editing" : ""),
    });
    (tiles || this._camTiles()).forEach((tile) => {
      const state = this._hass && this._hass.states ? this._hass.states[tile.entity_id] : null;
      grid.appendChild(this._camTile(tile, state));
    });
    if (this._camEditMode) grid.appendChild(this._camAddTile());
    return grid;
  }

  /** One camera tile: a still feed, plus the edit affordances while editing. */
  _camTile(item, state) {
    const cam = item.entity_id;
    const editing = this._camEditMode;
    const name = item.name || this._cameraLabel(cam);

    const tile = el("div", {
      class: "camera-tile" + (editing ? " editing" : ""),
      "data-eid": cam,
      style: "grid-column: span " + (item.span || 1) + ";",
    });

    // The name and the status live at the bottom inside the frame, over a dark
    // gradient so they stay readable on any still; clicks pass through.
    const caption =
      (item.show_name !== false || item.show_icon !== false || item.show_state !== false)
        ? el("div", { class: "camera-caption" })
        : null;
    if (caption) {
      if (item.show_icon !== false) {
        caption.appendChild(
          el("ha-icon", { icon: item.icon || "mdi:cctv", class: "camera-icon" }));
      }
      if (item.show_name !== false) {
        caption.appendChild(el("span", { class: "camera-name" }, name));
      }
      if (item.show_state !== false) {
        caption.appendChild(el("span", { class: "camera-sub" }, this._cameraState(state)));
      }
    }

    const frame = el("div", { class: "camera-frame" });
    if (!state || state.state === "unavailable" || state.state === "unknown") {
      frame.appendChild(
        el("div", { class: "camera-off" },
          el("ha-icon", { icon: "mdi:cctv-off" }),
          el("span", {},
            state ? "Telecamera non disponibile" : "Entità non trovata"))
      );
    } else {
      const picture =
        (state.attributes && state.attributes.entity_picture) || "";
      const image = el("img", {
        class: "camera-img",
        alt: name,
        loading: "eager",
        decoding: "async",
      });
      if (!editing) {
        image.addEventListener("click", () => {
          image.dispatchEvent(
            new CustomEvent("hass-more-info", {
              detail: { entityId: cam },
              bubbles: true,
              composed: true,
            })
          );
        });
      }
      const fallback = el("div", { class: "camera-off" },
        el("ha-icon", { icon: "mdi:cctv-off" }),
        el("span", {}, "Immagine non disponibile"));
      frame.appendChild(image);
      if (picture) {
        // Plain <img> on the camera proxy URL (entity_picture), refreshed every
        // 5s so the still follows the scene closely. Avoids hui-image, whose
        // registration may not resolve on patched frontends (black tile) and
        // which needs a live stream.
        let timer = null;
        const refresh = () => {
          if (!image.isConnected) {
            if (timer) window.clearInterval(timer);
            return;
          }
          image.src =
            picture + (picture.includes("?") ? "&" : "?") + "t=" + Date.now();
        };
        refresh();
        timer = window.setInterval(refresh, 5000);
        image.addEventListener("load", () => image.classList.add("loaded"));
        image.addEventListener("error", () => {
          if (timer) window.clearInterval(timer);
          image.replaceWith(fallback);
        });
      } else {
        image.replaceWith(fallback);
      }
    }
    if (caption) frame.appendChild(caption);
    tile.appendChild(frame);

    if (editing) {
      // ⋮ opens the per-camera popup; a long press on the rest starts the drag.
      tile.appendChild(
        el("button", {
          class: "spa-tile-menu icon-btn",
          title: "Opzioni telecamera",
          on: {
            click: (event) => { event.stopPropagation(); this._camTileDlgOpen(cam); },
            pointerdown: (event) => event.stopPropagation(),
          },
        }, el("ha-icon", { icon: "mdi:dots-vertical" }))
      );
      this._camWireDrag(tile, cam);
    }
    return tile;
  }

  /**
   * Friendly name of a camera entity, or its id when unknown.
   */
  _cameraLabel(id) {
    const state = this._hass && this._hass.states && this._hass.states[id];
    return (state && state.attributes && state.attributes.friendly_name) || id;
  }

  /** Short, human state of a camera ("In diretta", "Inattiva", …). */
  _cameraState(state) {
    if (!state) return "";
    if (state.state === "unavailable" || state.state === "unknown") {
      return "Non disponibile";
    }
    const map = {
      idle: "Inattiva",
      streaming: "In diretta",
      recording: "Registrazione",
    };
    return map[state.state] || String(state.state);
  }

  /** Open the per-camera popup of one tile. */
  _camTileDlgOpen(id) {
    this._camTileDlg = id;
    this._render();
  }

  _camTileDlgClose() {
    this._camTileDlg = null;
    this._render();
  }

  _camAddOpen() {
    this._camAddDlg = true;
    this._render();
  }

  /** Replace one camera tile in the stored list and save immediately. */
  async _camUpdateTile(id, patch) {
    const tiles = this._camTiles();
    const index = tiles.findIndex((tile) => tile.entity_id === id);
    if (index < 0) return;
    const updated = Object.assign({}, tiles[index], patch);
    tiles[index] = updated;
    if (patch && Object.prototype.hasOwnProperty.call(patch, "entity_id")) {
      // Replacing the camera: keep the popup on the tile we just changed.
      this._camTileDlg = updated.entity_id;
    }
    await this._camPersist(tiles);
  }

  /** Drop one camera tile and save immediately. */
  async _camRemoveTile(id) {
    const tiles = this._camTiles().filter((tile) => tile.entity_id !== id);
    this._camTileDlg = null;
    await this._camPersist(tiles);
  }

  /** Append a camera as a new tile and save immediately. */
  async _camAddTileCommit(entityId) {
    const id = String(entityId || "").trim().toLowerCase();
    if (!/^[a-z0-9_]+\.[a-z0-9_]+$/.test(id)) {
      this._message = { kind: "error", text: `Entità non valida: ${id}` };
      this._render();
      return;
    }
    if (!this._hass || !this._hass.states || !this._hass.states[id]) {
      this._message = { kind: "error", text: `Entità non trovata: ${id}` };
      this._render();
      return;
    }
    const tiles = this._camTiles();
    if (tiles.some((tile) => tile.entity_id === id)) {
      this._message = { kind: "error", text: `${id} è già nella scheda.` };
      this._render();
      return;
    }
    tiles.push({
      entity_id: id,
      name: null,
      icon: null,
      show_name: true,
      show_icon: true,
      show_state: true,
      span: 1,
      card_type: "auto",
      tap_action: "toggle",
      hold_action: "more-info",
      features: ["state"],
    });
    this._camAddDlg = false;
    await this._camPersist(tiles);
  }

  /** Save the whole camera list right away (no draft, no Salva button). */
  async _camPersist(tiles) {
    try {
      await this._service("update_settings", {
        camera_entities: tiles.map((tile) => ({
          entity_id: tile.entity_id,
          name: tile.name || null,
          icon: tile.icon || null,
          show_name: tile.show_name !== false,
          show_icon: tile.show_icon !== false,
          show_state: tile.show_state !== false,
          span: tile.span || 1,
          card_type: tile.card_type || "auto",
          tap_action: tile.tap_action || "toggle",
          hold_action: tile.hold_action || "more-info",
          features: Array.isArray(tile.features) ? tile.features : ["state"],
        })),
      });
      await this._loadData();
    } catch (error) {
      this._message = {
        kind: "error",
        text: this._friendlyError(error, "Salvataggio non riuscito."),
      };
      this._render();
    }
  }

  /** Popup for a single camera: entity, name, icon, visibility, span, delete. */
  _camTileDialog() {
    const id = this._camTileDlg;
    const tile = this._camTiles().find((item) => item.entity_id === id);
    if (!tile) return el("div");
    const overlay = el("div", {
      class: "detail-backdrop",
      on: {
        click: (event) => { if (event.target === overlay) this._camTileDlgClose(); },
      },
    });
    const sheet = el("div", {
      class: "detail-sheet spa-edit-sheet",
      role: "dialog",
      "aria-modal": "true",
      "aria-label": "Modifica telecamera",
    });
    sheet.appendChild(
      el("div", { class: "detail-head" },
        el("div", {},
          el("div", { class: "detail-title" }, "Modifica telecamera"),
          el("div", { class: "detail-sub" }, this._entityLabel(tile.entity_id))),
        el("button", {
          class: "icon-btn",
          title: "Chiudi",
          on: { click: () => this._camTileDlgClose() },
        }, el("ha-icon", { icon: "mdi:close" })))
    );

    // ----- Which camera -----
    const picker = document.createElement("ha-entity-picker");
    picker.hass = this._hass;
    picker.value = tile.entity_id;
    picker.label = "Entità";
    picker.includeDomains = ["camera"];
    picker.allowCustomEntity = true;
    picker.addEventListener("value-changed", (event) => {
      const value = event.detail && event.detail.value;
      if (value && value !== tile.entity_id) {
        this._camUpdateTile(tile.entity_id, { entity_id: value });
      }
    });
    sheet.appendChild(
      el("div", { class: "detail-section" },
        el("h4", {}, "Entità"),
        picker,
        el("div", { class: "hint" },
          "Scegli un'altra telecamera: nome e icona tornano ai valori dell'entità.")
      )
    );

    // ----- Name and icon overrides -----
    const nameInput = el("input", {
      type: "text",
      placeholder: this._entityLabel(tile.entity_id),
      value: tile.name || "",
    });
    nameInput.addEventListener("change", () => {
      const value = nameInput.value.trim();
      this._camUpdateTile(tile.entity_id, { name: value || null });
    });
    const iconPicker = document.createElement("ha-icon-picker");
    iconPicker.hass = this._hass;
    iconPicker.value = tile.icon || "";
    iconPicker.label = "Icona";
    iconPicker.addEventListener("value-changed", (event) => {
      const value = (event.detail && event.detail.value) || "";
      this._camUpdateTile(tile.entity_id, { icon: value || null });
    });
    sheet.appendChild(
      el("div", { class: "detail-section" },
        el("h4", {}, "Nome"),
        nameInput,
        el("h4", { style: "margin-top: 12px;" }, "Icona"),
        iconPicker,
        el("div", { class: "hint" },
          "Lascia vuoti nome e icona per usare quelli dell'entità.")
      )
    );

    // ----- Tap action -----
    const tapSelect = document.createElement("select");
    tapSelect.className = "select";
    [["toggle", "Toggle (accensione/spegnimento)"], ["more-info", "Apri info entità"], ["none", "Nessuna azione"]].forEach(([value, label]) => {
      const option = document.createElement("option");
      option.value = value;
      option.textContent = label;
      option.selected = (tile.tap_action || "toggle") === value;
      tapSelect.appendChild(option);
    });
    tapSelect.addEventListener("change", () => {
      this._spaUpdateTile(tile.entity_id, { tap_action: tapSelect.value });
    });
    sheet.appendChild(
      el("div", { class: "detail-section" },
        el("h4", {}, "Tap action"),
        tapSelect)
    );
    // ----- Features -----
    const featureBox = el("div", { class: "detail-section" });
    featureBox.appendChild(el("h4", {}, "Features"));
    const featureNames = ["state","power","brightness","temperature","hvac","color"];
    featureNames.forEach((name) => {
      const checked = Array.isArray(tile.features) && tile.features.includes(name);
      const sw = document.createElement("ha-switch");
      sw.checked = checked;
      const sync = () => {
        const set = new Set(tile.features || []);
        if (sw.checked) set.add(name); else set.delete(name);
        this._spaUpdateTile(tile.entity_id, { features: Array.from(set) });
      };
      sw.addEventListener("change", sync);
      sw.addEventListener("value-changed", sync);
      featureBox.appendChild(el("label", { class: "spa-toggle" }, sw, el("span", {}, name)));
    });
    sheet.appendChild(featureBox);

    const holdSelect = document.createElement("select");
    holdSelect.className = "select";
    [["more-info", "Apri info entità"], ["none", "Nessuna azione"], ["toggle", "Toggle"]].forEach(([value, label]) => {
      const option = document.createElement("option");
      option.value = value;
      option.textContent = label;
      option.selected = (tile.hold_action || "more-info") === value;
      holdSelect.appendChild(option);
    });
    holdSelect.addEventListener("change", () => {
      this._spaUpdateTile(tile.entity_id, { hold_action: holdSelect.value });
    });
    sheet.appendChild(
      el("div", { class: "detail-section" },
        el("h4", {}, "Hold action"),
        holdSelect)
    );

    // ----- Visibility -----
    const toggle = (label, key, checked) => {
      const sw = document.createElement("ha-switch");
      sw.checked = checked;
      const sync = () => {
        this._camUpdateTile(tile.entity_id, { [key]: Boolean(sw.checked) });
      };
      sw.addEventListener("change", sync);
      sw.addEventListener("value-changed", sync);
      return el("label", { class: "spa-toggle" }, sw, el("span", {}, label));
    };
    sheet.appendChild(
      el("div", { class: "detail-section" },
        el("h4", {}, "Cosa mostrare"),
        toggle("Nome", "show_name", tile.show_name !== false),
        toggle("Icona", "show_icon", tile.show_icon !== false),
        toggle("Stato", "show_state", tile.show_state !== false))
    );

    // ----- Column span -----
    const spanChips = el("div", { class: "spa-chips" });
    [1, 2, 3, 4].forEach((value) => {
      spanChips.appendChild(
        el("button", {
          class: "spa-chip" + (tile.span === value ? " on" : ""),
          title: value === 1 ? "1 colonna" : value + " colonne",
          on: { click: () => this._camUpdateTile(tile.entity_id, { span: value }) },
        }, el("span", {}, String(value)))
      );
    });
    sheet.appendChild(
      el("div", { class: "detail-section" },
        el("h4", {}, "Dimensione (colonne)"),
        spanChips,
        el("div", { class: "hint" }, "Quante colonne occupa il riquadro, da 1 a 4."))
    );

    sheet.appendChild(
      el("div", { class: "detail-actions" },
        el("button", {
          class: "btn danger",
          on: { click: () => this._camRemoveTile(tile.entity_id) },
        }, el("ha-icon", { icon: "mdi:delete" }), el("span", {}, "Elimina")),
        el("div", { style: "flex: 1;" }),
        el("button", {
          class: "btn primary",
          on: { click: () => this._camTileDlgClose() },
        }, "Chiudi"))
    );
    overlay.appendChild(sheet);
    return overlay;
  }

  /** Add-camera picker, opened by the + tile and by the bar button. */
  _camAddDialog() {
    const overlay = el("div", {
      class: "detail-backdrop",
      on: {
        click: (event) => {
          if (event.target === overlay) { this._camAddDlg = false; this._render(); }
        },
      },
    });
    const sheet = el("div", {
      class: "detail-sheet spa-edit-sheet",
      role: "dialog",
      "aria-modal": "true",
      "aria-label": "Aggiungi telecamera",
    });
    sheet.appendChild(
      el("div", { class: "detail-head" },
        el("div", {},
          el("div", { class: "detail-title" }, "Aggiungi telecamera"),
          el("div", { class: "detail-sub" }, "Scegli la telecamera da mostrare")),
        el("button", {
          class: "icon-btn",
          title: "Chiudi",
          on: { click: () => { this._camAddDlg = false; this._render(); } },
        }, el("ha-icon", { icon: "mdi:close" })))
    );
    const picker = document.createElement("ha-entity-picker");
    picker.hass = this._hass;
    picker.label = "Telecamera da aggiungere";
    picker.includeDomains = ["camera"];
    picker.allowCustomEntity = true;
    const confirm = el("button", {
      class: "btn primary",
      disabled: !picker.value,
      on: { click: () => this._camAddTileCommit(picker.value) },
    }, el("ha-icon", { icon: "mdi:plus" }), el("span", {}, "Aggiungi"));
    picker.addEventListener("value-changed", (event) => {
      const value = (event.detail && event.detail.value) || "";
      picker.value = value;
      confirm.disabled = !value;
    });
    sheet.appendChild(el("div", { class: "detail-section" }, picker));
    sheet.appendChild(
      el("div", { class: "detail-actions" },
        el("div", { style: "flex: 1;" }),
        el("button", {
          class: "btn",
          on: { click: () => { this._camAddDlg = false; this._render(); } },
        }, "Annulla"),
        confirm)
    );
    overlay.appendChild(sheet);
    return overlay;
  }

  /** The dashed "+" tile appended while editing. */
  _camAddTile() {
    return el("button", {
      class: "spa-add-tile cam-add-tile",
      title: "Aggiungi telecamera",
      on: { click: (event) => { event.stopPropagation(); this._camAddOpen(); } },
    },
      el("ha-icon", { icon: "mdi:plus" }),
      el("span", {}, "Aggiungi"));
  }

  /** Hold-to-drag a camera tile: mouse drags at once, touch needs a short hold. */
  _camWireDrag(tile, id) {
    let press = null;
    let timer = null;

    const clearTimer = () => {
      if (timer) { clearTimeout(timer); timer = null; }
    };

    const cleanup = () => {
      clearTimer();
      window.removeEventListener("pointermove", onMove);
      window.removeEventListener("pointerup", onUp);
      window.removeEventListener("pointercancel", onUp);
      press = null;
    };

    const begin = () => {
      if (!press) return;
      this._camDrag = { id, node: tile };
      tile.classList.add("dragging");
      try { tile.setPointerCapture(press.pointerId); } catch (error) { /* ignore */ }
    };

    const onMove = (event) => {
      if (this._camDrag && this._camDrag.node === tile) {
        this._camReorder(tile, event.clientX, event.clientY);
        if (event.cancelable) event.preventDefault();
        return;
      }
      if (!press) return;
      if (Math.hypot(event.clientX - press.x, event.clientY - press.y) > 10) {
        cleanup(); // a scroll, not a long press
      }
    };

    const onUp = () => {
      const wasDragging = this._camDrag && this._camDrag.node === tile;
      cleanup();
      if (!wasDragging) return;
      tile.classList.remove("dragging");
      this._camDrag = null;
      this._camCommitOrder();
    };

    tile.addEventListener("pointerdown", (event) => {
      if (event.button && event.button !== 0) return;
      const target = event.target;
      if (target && target.closest && target.closest("button")) return;
      press = { x: event.clientX, y: event.clientY, pointerId: event.pointerId };
      window.addEventListener("pointermove", onMove, { passive: false });
      window.addEventListener("pointerup", onUp);
      window.addEventListener("pointercancel", onUp);
      if (event.pointerType === "mouse") begin();
      else timer = setTimeout(begin, 300);
    });

    // Block the page scroll only once the drag is actually running.
    tile.addEventListener("touchmove", (event) => {
      if (this._camDrag && this._camDrag.node === tile && event.cancelable) {
        event.preventDefault();
      }
    }, { passive: false });
  }

  /** Move the dragged camera next to whichever sibling is closest. */
  _camReorder(node, x, y) {
    const grid = node.parentNode;
    if (!grid) return;
    const tiles = Array.from(grid.querySelectorAll(".camera-tile")).filter((item) => item !== node);
    let best = null;
    let bestDist = Infinity;
    tiles.forEach((item) => {
      const rect = item.getBoundingClientRect();
      const cx = rect.left + rect.width / 2;
      const cy = rect.top + rect.height / 2;
      const dist = (cx - x) ** 2 + (cy - y) ** 2;
      if (dist < bestDist) { bestDist = dist; best = item; }
    });
    if (!best) return;
    const rect = best.getBoundingClientRect();
    const cx = rect.left + rect.width / 2;
    const cy = rect.top + rect.height / 2;
    const sameRow = Math.abs(y - cy) < rect.height / 2;
    const before = y < cy || (sameRow && x < cx);
    grid.insertBefore(node, before ? best : best.nextSibling);
  }

  /** After a drag: read the new visual order and save it if it changed. */
  async _camCommitOrder() {
    const grid = this.shadowRoot && this.shadowRoot.querySelector(".cameras");
    if (!grid) return;
    const tiles = this._camTiles();
    const byId = new Map(tiles.map((tile) => [tile.entity_id, tile]));
    const order = Array.from(grid.querySelectorAll(".camera-tile[data-eid]"))
      .map((node) => node.getAttribute("data-eid"));
    const reordered = order.map((item) => byId.get(item)).filter(Boolean);
    if (reordered.length !== tiles.length) return;
    if (reordered.every((tile, index) => tile.entity_id === tiles[index].entity_id)) {
      return; // nothing moved
    }
    await this._camPersist(reordered);
  }

  // --------------------------------------------------------------------- SPA

  /** Friendly name of any entity, or its id when unknown. */
  _entityLabel(id) {
    const state = this._hass && this._hass.states && this._hass.states[id];
    const name = state && state.attributes && state.attributes.friendly_name;
    return String(name || id);
  }

  /** The flat, user-ordered tiles of the Spa tab, normalised to objects. */
  _spaTiles() {
    const settings = (this._data && this._data.settings) || {};
    const raw = settings.spa_entities || [];
    return raw
      .map((item) => this._spaNormTile(item))
      .filter((tile) => tile && tile.entity_id);
  }

  /** One tile as an object, accepting the legacy bare entity-id string. */
  _spaNormTile(item) {
    if (typeof item === "string") {
      return {
        entity_id: item,
        name: null,
        icon: null,
        show_name: true,
        show_icon: true,
        show_state: true,
        span: 1,
      };
    }
    if (!item || typeof item !== "object") return null;
    const entity_id = String(item.entity_id || "").trim();
    if (!entity_id) return null;
    const text = (value) => {
      const out = value === null || value === undefined ? "" : String(value).trim();
      return out || null;
    };
    let span = Number(item.span);
    if (!Number.isFinite(span)) span = 1;
    span = Math.min(4, Math.max(1, Math.round(span)));
    const supported = ["auto", "tile", "button", "switch", "climate", "sensor", "entity", "thermostat", "gauge"];
    const allowedFeatures = ["brightness", "temperature", "power", "hvac", "color", "state"];
    const tap_action = String(item.tap_action || "toggle").trim().toLowerCase();
    const hold_action = String(item.hold_action || "more-info").trim().toLowerCase();
    const rawFeatures = item && Array.isArray(item.features) ? item.features : null;
    const features = rawFeatures ? rawFeatures.filter((f) => allowedFeatures.includes(String(f).trim().toLowerCase()))
      .map((f) => String(f).trim().toLowerCase()) : ["brightness", "state"];
    let card_type = String(item.card_type || item.type || "auto").trim().toLowerCase();
    if (!supported.includes(card_type)) card_type = "auto";
    return {
      entity_id,
      name: text(item.name),
      icon: text(item.icon),
      show_name: item.show_name !== false,
      show_icon: item.show_icon !== false,
      show_state: item.show_state !== false,
      span,
      card_type,
      tap_action: ["toggle","more-info","none","brightness"].includes(tap_action) ? tap_action : "toggle",
      hold_action: ["toggle","more-info","none","brightness"].includes(hold_action) ? hold_action : "more-info",
      features: features.length ? features : ["state"],
    };
  }

  /**
   * Spa tab: a container with its own sub-tab bar, exactly like
   * Configurazione. The controls and the cameras share the tab; on a phone the
   * bar turns into a vertical icon strip on the left (see the CSS below).
   */
  _renderSpa() {
    const wrap = el("div", { class: "stack spa" });

    // A sub-tab an account may not see must not stay selected; fall back to
    // the first one it is allowed to see.
    const allowed = this._visibleSpaTabs();
    if (!allowed.some((tab) => tab.id === this._spaTab)) {
      this._spaTab = allowed.length ? allowed[0].id : "controlli";
    }

    const tabButton = (tab) =>
      el("button", {
        class: `tab small${this._spaTab === tab.id ? " active" : ""}`,
        title: tab.label,
        on: {
          click: () => {
            this._spaTab = tab.id;
            this._render();
          },
        },
      }, el("ha-icon", { icon: tab.icon }),
         el("span", { class: "tab-label" }, tab.label));
    wrap.appendChild(el("div", { class: "tabs tight" }, allowed.map(tabButton)));

    if (this._spaTab === "telecamere") add(wrap, this._renderTelecamere());
    else add(wrap, this._renderSpaControlli());
    return wrap;
  }

  /** Spa sub-tab: the configurable control tiles, in user order. */
  _renderSpaControlli() {
    const wrap = el("div", { class: "stack" });
    if (this._can("config")) wrap.appendChild(this._spaSpaHeader());
    const tiles = this._spaTiles();
    if (!tiles.length && !this._spaEditMode) {
      wrap.appendChild(
        el("div", { class: "empty" },
          "Nessun controllo configurato. Usa «…» in alto a destra, poi Modifica, per aggiungere le entità.")
      );
    } else {
      wrap.appendChild(this._renderSpaGrid(tiles));
    }
    if (this._spaTileDlg) wrap.appendChild(this._spaTileDialog());
    if (this._spaBrightnessDlg) wrap.appendChild(this._spaBrightnessDialog());
    if (this._spaAddDlg) wrap.appendChild(this._spaAddDialog());
    return wrap;
  }

  /** Title row of the Spa tab: the «…» menu, or the edit-mode actions. */
  _spaSpaHeader() {
    const head = el("div", { class: "spa-head" });
    head.appendChild(
      el("div", { class: "spa-head-title" },
        el("ha-icon", { icon: "mdi:spa" }),
        el("span", {}, this._spaEditMode ? "Modifica Spa" : "Spa"))
    );
    if (this._spaEditMode) {
      head.appendChild(
        el("div", { class: "spa-head-actions" },
          el("button", {
            class: "btn small",
            title: "Aggiungi entità",
            on: { click: () => this._spaAddOpen() },
          }, el("ha-icon", { icon: "mdi:plus" })),
          el("button", {
            class: "btn primary small",
            title: "Fine modifica",
            on: { click: () => this._spaEditExit() },
          }, el("ha-icon", { icon: "mdi:check" })))
      );
      return head;
    }
    head.appendChild(
      el("button", {
        class: "icon-btn spa-menu-btn",
        title: "Modifica entità",
        on: { click: () => this._spaEditEnter() },
      }, el("ha-icon", { icon: "mdi:pencil" }))
    );
    return head;
  }

  /** The pencil itself toggles edit mode: no intermediate Modifica menu. */
  _spaEditEnter() {
    this._spaEditMode = true;
    this._render();
  }

  /** Leave edit mode; nothing to save, every change was already written. */
  _spaEditExit() {
    this._spaEditMode = false;
    this._spaTileDlg = null;
    this._spaAddDlg = false;
    this._spaBrightnessDlg = null;
    this._spaDrag = null;
    this._render();
  }

  /** One single flat grid with every configured tile, in user order. */
  _renderSpaGrid(tiles) {
    const grid = el("div", {
      class: "spa-grid" + (this._spaEditMode ? " editing" : ""),
    });
    (tiles || this._spaTiles()).forEach((tile) => {
      const state = this._hass && this._hass.states ? this._hass.states[tile.entity_id] : null;
      grid.appendChild(this._spaTile(tile, state));
    });
    if (this._spaEditMode) grid.appendChild(this._spaAddTile());
    return grid;
  }

  _spaIcon(domain, id, state) {
    const on = state && state.state === "on";
    const locked = state && state.state === "locked";
    return {
      light: on ? "mdi:lightbulb-on" : "mdi:lightbulb-outline",
      switch: on ? "mdi:toggle-switch" : "mdi:toggle-switch-off-outline",
      input_boolean: on ? "mdi:check-circle" : "mdi:check-circle-outline",
      fan: on ? "mdi:fan" : "mdi:fan-off",
      lock: locked ? "mdi:lock" : "mdi:lock-open-variant",
      climate: "mdi:thermostat",
    }[domain] || "mdi:power-plug-outline";
  }

  _moreInfo(entityId) {
    this.dispatchEvent(
      new CustomEvent("hass-more-info", {
        detail: { entityId },
        bubbles: true,
        composed: true,
      })
    );
  }

  /** The secondary line under the tile name. */
  _spaSub(domain, id, state) {
    if (!state || state.state === "unavailable") return "Non disponibile";
    if (domain === "light" || domain === "switch" || domain === "input_boolean" || domain === "fan") {
      if (state.state !== "on") return "Spenta";
      const attrs = state.attributes || {};
      const pct = attrs.brightness != null
        ? ` · ${Math.round((attrs.brightness / 255) * 100)}%`
        : "";
      return "Accesa" + pct;
    }
    if (domain === "lock") return state.state === "locked" ? "Chiusa" : "Aperta";
    if (domain === "climate") {
      if (state.state === "off") return "Spento";
      const attrs = state.attributes || {};
      const current = attrs.current_temperature;
      const target = attrs.temperature;
      return `Ora ${current != null ? Math.round(current) + "°" : "—"} · Target ${target != null ? Math.round(target) + "°" : "—"}`;
    }
    return String(state.state);
  }

  /** The round on/off button on the right of a tile. */
  /** Brightness slider under a light that is on and supports dimming. */
  _spaSlider(domain, id, state) {
    if (domain !== "light" || !state || state.state !== "on") return null;
    const attrs = state.attributes || {};
    const supports = Number(attrs.supported_features || 0);
    if ((supports & 1) !== 1) return null; // SUPPORT_BRIGHTNESS
    const pct = attrs.brightness != null
      ? Math.round((attrs.brightness / 255) * 100)
      : 100;
    return el("div", {
      class: "spa-slider",
      on: { click: (event) => event.stopPropagation() },
    },
      el("input", {
        type: "range",
        min: "1",
        max: "100",
        value: String(pct),
        on: {
          change: (event) => this._spaSetBrightness(id, Number(event.target.value)),
        },
      })
    );
  }

  /** Temperature +/− row under a climate that is on. */
  _spaClimaRow(domain, id, state) {
    if (domain !== "climate" || !state || state.state === "off" || state.state === "unavailable") return null;
    const target = (state.attributes || {}).temperature;
    return el("div", { class: "spa-clima" },
      el("span", { class: "dim" },
        target != null ? `Target ${Math.round(target)}°` : "Target —"),
      el("div", { class: "row", style: "gap: 6px;" },
        el("button", {
          class: "btn small",
          disabled: this._busySpa,
          on: { click: (event) => { event.stopPropagation(); this._spaClimateTemp(id, -1); } },
        }, el("ha-icon", { icon: "mdi:minus" })),
        el("button", {
          class: "btn small",
          disabled: this._busySpa,
          on: { click: (event) => { event.stopPropagation(); this._spaClimateTemp(id, 1); } },
        }, el("ha-icon", { icon: "mdi:plus" }))
      )
    );
  }

  /** One mushroom-like control tile. Tap toggles; in edit mode it shows ⋮
      (per-entity options) and can be held to drag it into a new position. */
  /** Effective card type for a tile, resolving "auto" by entity domain. */
  _resolveSpaCardType(item) {
    const card_type = String((item && item.card_type) ? item.card_type : "auto").trim().toLowerCase();
    if (card_type !== "auto") return card_type;
    const id = String((item && item.entity_id) || "").trim();
    const domain = id.split(".")[0];
    const defaults = {
      light: "tile",
      switch: "switch",
      input_boolean: "switch",
      climate: "climate",
      fan: "button",
      media_player: "button",
      sensor: "sensor",
      binary_sensor: "tile",
      number: "gauge",
      input_number: "gauge",
      cover: "tile",
      lock: "tile",
    };
    return defaults[domain] || "tile";
  }

  _spaTile(item, state) {
    const id = item.entity_id;
    const domain = String(id || "").split(".")[0];
    const editing = this._spaEditMode;
    const type = this._resolveSpaCardType(item);
    const active =
      domain === "lock" ? (state && state.state === "locked")
        : domain === "climate" ? (state && state.state !== "off" && state.state !== "unavailable")
          : (state && state.state === "on");
    const tile = el("div", {
      class:
        "spa-tile spa-tile--" + type +
        ((state && state.state === "on") ? " on" : "") +
        (domain === "climate" && state && state.state === "heat" ? " heating" : "") +
        (domain === "climate" && state && state.state === "cool" ? " cooling" : "") +
        (editing ? " editing" : ""),
      "data-card-type": type,
      "data-eid": id,
      style: "grid-column: span " + (item.span || 1) + ";",
    });

    const attrs = (state && state.attributes) || {};
    const current = attrs.current_temperature;
    const target = attrs.temperature;

    if (!editing) {
      tile.addEventListener("click", (event) => {
        const tap = String((item && item.tap_action) || "toggle").trim().toLowerCase();
        if (tap === "more-info") { event.stopPropagation(); this._moreInfo(id); return; }
        if (tap === "none") { event.stopPropagation(); return; }
        if (!state || state.state === "unavailable") {
          this._moreInfo(id);
          return;
        }
        if (domain === "lock") {
          this._spaLock(id, state.state === "locked");
        } else if (domain === "climate") {
          const on = state.state !== "off" && state.state !== "unavailable";
          this._spaClimatePower(id, on);
        } else {
          this._spaToggle(domain, id);
        }
      });

      // Long press / hold action.
      let holdTimer = null;
      tile.addEventListener("pointerdown", () => {
        holdTimer = setTimeout(() => {
          holdTimer = null;
          const action = String(item.hold_action || "more-info").trim().toLowerCase();
          if (action === "none") return;
          if (action === "toggle") {
            if (domain === "lock") this._spaLock(id, state.state === "locked");
            else if (domain === "climate") this._spaClimatePower(id, state.state !== "off");
            else this._spaToggle(domain, id);
            return;
          }
          if (action === "brightness" && domain === "light") {
            this._spaBrightnessDlg = id;
            this._render();
            return;
          }
          this._moreInfo(id);
        }, 600);
      });
      const cancelHold = () => { if (holdTimer) { clearTimeout(holdTimer); holdTimer = null; } };
      tile.addEventListener("pointerup", cancelHold);
      tile.addEventListener("pointerleave", cancelHold);
      tile.addEventListener("pointermove", cancelHold);
    }

    if ((type === "climate" || type === "thermostat") && !editing) {
      if (item.show_icon !== false) {
        tile.appendChild(
          el("div", { class: "spa-tile-icon" + (active ? "" : " off") },
            el("ha-icon", { icon: item.icon || this._spaIcon(domain, id, state) }))
        );
      }
      if (item.show_name !== false) {
        tile.appendChild(el("span", { class: "spa-tile-name" }, item.name || this._entityLabel(id)));
      }
      tile.appendChild(el("div", { class: "spa-tile-sub" },
        `${current != null ? current : "—"}° / ${target != null ? Math.round(target) : "—"}°`));
      const row = el("div", { class: "row", style: "gap: 6px; flex-wrap: wrap; justify-content:center; width:100%;" });
      row.appendChild(el("button", {
        class: "btn small",
        disabled: this._busySpa,
        title: state.state === "off" ? "Accendi" : "Spegni",
        on: { click: (event) => { event.stopPropagation(); this._spaClimatePower(id, state.state !== "off" && state.state !== "unavailable"); } },
      }, el("ha-icon", { icon: state.state === "off" ? "mdi:power-off" : "mdi:power" })));
      row.appendChild(el("button", {
        class: "btn small",
        disabled: this._busySpa,
        title: "Riscaldamento",
        on: { click: (event) => { event.stopPropagation(); this._spaClimateMode(id, "heat"); } },
      }, el("ha-icon", { icon: "mdi:fire" })));
      row.appendChild(el("button", {
        class: "btn small",
        disabled: this._busySpa,
        title: "Freddo",
        on: { click: (event) => { event.stopPropagation(); this._spaClimateMode(id, "cool"); } },
      }, el("ha-icon", { icon: "mdi:snowflake" })));
      row.appendChild(el("button", {
        class: "btn small",
        disabled: this._busySpa,
        on: { click: (event) => { event.stopPropagation(); this._spaClimateTemp(id, -1); } },
      }, el("ha-icon", { icon: "mdi:minus" })));
      row.appendChild(el("button", {
        class: "btn small",
        disabled: this._busySpa,
        on: { click: (event) => { event.stopPropagation(); this._spaClimateTemp(id, 1); } },
      }, el("ha-icon", { icon: "mdi:plus" })));
      tile.appendChild(row);
      return tile;
    }

    if (item.show_icon !== false) {
      tile.appendChild(
        el("div", { class: "spa-tile-icon" + (active ? "" : " off") },
          el("ha-icon", { icon: item.icon || this._spaIcon(domain, id, state) }))
      );
    }
    const main = el("div", { class: "spa-tile-main" });
    if (item.show_name !== false) {
      main.appendChild(el("span", { class: "spa-tile-name" }, item.name || this._entityLabel(id)));
    }
    if (item.show_state !== false && type !== "button") {
      main.appendChild(el("span", { class: "spa-tile-sub" }, this._spaSub(domain, id, state)));
    }
    if (type === "gauge") {
      const raw = state && state.state;
      const val = Number(raw);
      if (Number.isFinite(val)) {
        const pct = Math.max(0, Math.min(100, val));
        tile.appendChild(el("progress", { class: "spa-tile-gauge", value: pct, max: 100 }));
      }
    }
    if (main.childNodes.length) tile.appendChild(main);

    if (editing) {
      // ⋮ opens the per-entity popup; a long press on the rest starts the drag.
      tile.appendChild(
        el("button", {
          class: "spa-tile-menu icon-btn",
          title: "Opzioni riquadro",
          on: {
            click: (event) => { event.stopPropagation(); this._spaTileDlgOpen(id); },
            pointerdown: (event) => event.stopPropagation(),
          },
        }, el("ha-icon", { icon: "mdi:dots-vertical" }))
      );
      this._spaWireDrag(tile, id);
      return tile;
    }

    const brightness = typeof attrs.brightness === "number" ? Math.round(attrs.brightness / 2.55) : (state.state === "on" ? 100 : 0);
    if (domain === "light" && !editing && state && (attrs.supported_color_modes || []).includes("brightness")) {
      const slider = document.createElement("input");
      slider.type = "range";
      slider.min = 0;
      slider.max = 100;
      slider.step = 1;
      slider.value = brightness;
      slider.className = "spa-tile-brightness";
      slider.addEventListener("input", (event) => {
        const label = tile.querySelector(".spa-tile-brightness-value");
        if (label) { label.textContent = `${event.target.value}%`; label.classList.add("show"); }
      });
      slider.addEventListener("change", (event) => {
        const value = Number(event.target.value);
        const label = tile.querySelector(".spa-tile-brightness-value");
        if (value <= 0) this._spaCall("light", "turn_off", id);
        else this._spaSetBrightness(id, value);
        setTimeout(() => { if (label) label.classList.remove("show"); }, 1200);
      });
      slider.addEventListener("blur", () => {
        const label = tile.querySelector(".spa-tile-brightness-value");
        if (label) label.classList.remove("show");
      });
      slider.addEventListener("pointerdown", (event) => event.stopPropagation());
      const row = el("div", { class: "spa-tile-bright-row" },
        el("span", { class: "dim spa-tile-brightness-value" }, `${brightness}%`),
        slider
      );
      tile.appendChild(row);
    }
    add(tile, this._spaSlider(domain, id, state));
    add(tile, this._spaClimaRow(domain, id, state));
    return tile;
  }

  /** Open the per-entity popup of one tile. */
  _spaTileDlgOpen(id) {
    this._spaTileDlg = id;
    this._render();
  }

  _spaTileDlgClose() {
    this._spaTileDlg = null;
    this._render();
  }

  _spaBrightnessDlgClose() {
    this._spaBrightnessDlg = null;
    this._render();
  }

  _spaBrightnessDialog() {
    const id = this._spaBrightnessDlg;
    if (!id) return el("div");
    const state = this._hass && this._hass.states ? this._hass.states[id] : null;
    const attrs = (state && state.attributes) || {};
    const brightness = typeof attrs.brightness === "number" ? Math.round(attrs.brightness / 2.55) : (state.state === "on" ? 100 : 0);
    const overlay = el("div", {
      class: "detail-backdrop",
      on: { click: (event) => { if (event.target === overlay) this._spaBrightnessDlgClose(); } },
    });
    const sheet = el("div", { class: "detail-sheet", role: "dialog", "aria-modal": "true", "aria-label": "Luminosità" });
    sheet.appendChild(
      el("div", { class: "detail-head" },
        el("div", {}, el("div", { class: "detail-title" }, "Luminosità"), el("div", { class: "detail-sub" }, this._entityLabel(id))),
        el("button", { class: "icon-btn", title: "Chiudi", on: { click: () => this._spaBrightnessDlgClose() } }, el("ha-icon", { icon: "mdi:close" })))
    );
    const pctLabel = el("div", { class: "detail-text" }, `${brightness}%`);
    const slider = document.createElement("input");
    slider.type = "range";
    slider.min = 1;
    slider.max = 100;
    slider.step = 1;
    slider.value = brightness;
    slider.addEventListener("input", (event) => { pctLabel.textContent = `${event.target.value}%`; });
    slider.addEventListener("change", (event) => {
      this._spaSetBrightness(id, Number(event.target.value));
    });
    sheet.appendChild(el("div", { class: "detail-section" },
      pctLabel,
      slider,
      el("div", { class: "row", style: "gap:6px; justify-content:center; margin-top:8px;" },
        el("button", { class: "btn small", disabled: this._busySpa,
          on: { click: (event) => { event.stopPropagation(); this._spaSetBrightness(id, Math.max(1, brightness - 10)); } } }, el("ha-icon", { icon: "mdi:minus" })),
        el("button", { class: "btn small", disabled: this._busySpa,
          on: { click: (event) => { event.stopPropagation(); this._spaSetBrightness(id, 100); } } }, el("ha-icon", { icon: "mdi:white-balance-sunny" })))
    ));
    overlay.appendChild(sheet);
    return overlay;
  }

  _spaAddOpen() {
    this._spaAddDlg = true;
    this._render();
  }

  /** Replace one tile in the stored list and save immediately. */
  async _spaUpdateTile(id, patch) {
    const tiles = this._spaTiles();
    const index = tiles.findIndex((tile) => tile.entity_id === id);
    if (index < 0) return;
    const updated = Object.assign({}, tiles[index], patch);
    tiles[index] = updated;
    if (patch && Object.prototype.hasOwnProperty.call(patch, "entity_id")) {
      // Replacing the entity: keep the popup on the tile we just changed.
      this._spaTileDlg = updated.entity_id;
    }
    await this._spaPersist(tiles);
  }

  /** Drop one tile and save immediately. */
  async _spaRemoveTile(id) {
    const tiles = this._spaTiles().filter((tile) => tile.entity_id !== id);
    this._spaTileDlg = null;
    await this._spaPersist(tiles);
  }

  /** Append an entity as a new tile and save immediately. */
  async _spaAddTileCommit(entityId) {
    const id = String(entityId || "").trim().toLowerCase();
    if (!/^[a-z0-9_]+\.[a-z0-9_]+$/.test(id)) {
      this._message = { kind: "error", text: `Entità non valida: ${id}` };
      this._render();
      return;
    }
    if (!this._hass || !this._hass.states || !this._hass.states[id]) {
      this._message = { kind: "error", text: `Entità non trovata: ${id}` };
      this._render();
      return;
    }
    const tiles = this._spaTiles();
    if (tiles.some((tile) => tile.entity_id === id)) {
      this._message = { kind: "error", text: `${id} è già nella scheda.` };
      this._render();
      return;
    }
    tiles.push({
      entity_id: id,
      name: null,
      icon: null,
      show_name: true,
      show_icon: true,
      show_state: true,
      span: 1,
    });
    this._spaAddDlg = false;
    await this._spaPersist(tiles);
  }

  /** Save the whole tile list right away (no draft, no Salva button). */
  async _spaPersist(tiles) {
    try {
      await this._service("update_settings", {
        spa_entities: tiles.map((tile) => ({
          entity_id: tile.entity_id,
          name: tile.name || null,
          icon: tile.icon || null,
          show_name: tile.show_name !== false,
          show_icon: tile.show_icon !== false,
          show_state: tile.show_state !== false,
          span: tile.span || 1,
          card_type: tile.card_type || "auto",
          tap_action: tile.tap_action || "toggle",
          hold_action: tile.hold_action || "more-info",
          features: Array.isArray(tile.features) ? tile.features : ["state"],
        })),
      });
      await this._loadData();
    } catch (error) {
      this._message = {
        kind: "error",
        text: this._friendlyError(error, "Salvataggio non riuscito."),
      };
      this._render();
    }
  }

  /** Popup for a single tile: entity, name, icon, visibility, span, delete. */
  _spaTileDialog() {
    const id = this._spaTileDlg;
    const tile = this._spaTiles().find((item) => item.entity_id === id);
    if (!tile) return el("div");
    const overlay = el("div", {
      class: "detail-backdrop",
      on: {
        click: (event) => { if (event.target === overlay) this._spaTileDlgClose(); },
      },
    });
    const sheet = el("div", {
      class: "detail-sheet spa-edit-sheet",
      role: "dialog",
      "aria-modal": "true",
      "aria-label": "Modifica riquadro",
    });
    sheet.appendChild(
      el("div", { class: "detail-head" },
        el("div", {},
          el("div", { class: "detail-title" }, "Modifica riquadro"),
          el("div", { class: "detail-sub" }, this._entityLabel(tile.entity_id))),
        el("button", {
          class: "icon-btn",
          title: "Chiudi",
          on: { click: () => this._spaTileDlgClose() },
        }, el("ha-icon", { icon: "mdi:close" })))
    );

    // ----- Which entity -----
    const picker = document.createElement("ha-entity-picker");
    picker.hass = this._hass;
    picker.value = tile.entity_id;
    picker.label = "Entità";
    picker.allowCustomEntity = true;
    picker.addEventListener("value-changed", (event) => {
      const value = event.detail && event.detail.value;
      if (value && value !== tile.entity_id) {
        this._spaUpdateTile(tile.entity_id, { entity_id: value });
      }
    });
    sheet.appendChild(
      el("div", { class: "detail-section" },
        el("h4", {}, "Entità"),
        picker,
        el("div", { class: "hint" },
          "Scegli un'altra entità (qualsiasi tipo): nome e icona tornano ai valori dell'entità.")
      )
    );

    // ----- Name and icon overrides -----
    const nameInput = el("input", {
      type: "text",
      placeholder: this._entityLabel(tile.entity_id),
      value: tile.name || "",
    });
    nameInput.addEventListener("change", () => {
      const value = nameInput.value.trim();
      this._spaUpdateTile(tile.entity_id, { name: value || null });
    });
    const iconPicker = document.createElement("ha-icon-picker");
    iconPicker.hass = this._hass;
    iconPicker.value = tile.icon || "";
    iconPicker.label = "Icona";
    iconPicker.addEventListener("value-changed", (event) => {
      const value = (event.detail && event.detail.value) || "";
      this._spaUpdateTile(tile.entity_id, { icon: value || null });
    });
    sheet.appendChild(
      el("div", { class: "detail-section" },
        el("h4", {}, "Nome"),
        nameInput,
        el("h4", { style: "margin-top: 12px;" }, "Icona"),
        iconPicker,
        el("div", { class: "hint" },
          "Lascia vuoti nome e icona per usare quelli dell'entità.")
      )
    );

    // ----- Visibility -----
    const toggle = (label, key, checked) => {
      const sw = document.createElement("ha-switch");
      sw.checked = checked;
      const sync = () => {
        this._spaUpdateTile(tile.entity_id, { [key]: Boolean(sw.checked) });
      };
      sw.addEventListener("change", sync);
      sw.addEventListener("value-changed", sync);
      return el("label", { class: "spa-toggle" }, sw, el("span", {}, label));
    };
    sheet.appendChild(
      el("div", { class: "detail-section" },
        el("h4", {}, "Cosa mostrare"),
        toggle("Nome", "show_name", tile.show_name !== false),
        toggle("Icona", "show_icon", tile.show_icon !== false),
        toggle("Stato", "show_state", tile.show_state !== false))
    );

    // ----- Column span -----
    const spanChips = el("div", { class: "spa-chips" });
    [1, 2, 3, 4].forEach((value) => {
      spanChips.appendChild(
        el("button", {
          class: "spa-chip" + (tile.span === value ? " on" : ""),
          title: value === 1 ? "1 colonna" : value + " colonne",
          on: { click: () => this._spaUpdateTile(tile.entity_id, { span: value }) },
        }, el("span", {}, String(value)))
      );
    });
    sheet.appendChild(
      el("div", { class: "detail-section" },
        el("h4", {}, "Dimensione (colonne)"),
        spanChips,
        el("div", { class: "hint" }, "Quante colonne occupa il riquadro, da 1 a 4."))
    );

    sheet.appendChild(
      el("div", { class: "detail-actions" },
        el("button", {
          class: "btn danger",
          on: { click: () => this._spaRemoveTile(tile.entity_id) },
        }, el("ha-icon", { icon: "mdi:delete" }), el("span", {}, "Elimina")),
        el("div", { style: "flex: 1;" }),
        el("button", {
          class: "btn primary",
          on: { click: () => this._spaTileDlgClose() },
        }, "Chiudi"))
    );
    overlay.appendChild(sheet);
    return overlay;
  }

  /** Add-entity picker, opened by the + tile and by the bar button. */
  _spaAddDialog() {
    const overlay = el("div", {
      class: "detail-backdrop",
      on: {
        click: (event) => {
          if (event.target === overlay) { this._spaAddDlg = false; this._render(); }
        },
      },
    });
    const sheet = el("div", {
      class: "detail-sheet spa-edit-sheet",
      role: "dialog",
      "aria-modal": "true",
      "aria-label": "Aggiungi entità",
    });
    sheet.appendChild(
      el("div", { class: "detail-head" },
        el("div", {},
          el("div", { class: "detail-title" }, "Aggiungi entità"),
          el("div", { class: "detail-sub" }, "Scegli l'entità da mostrare nella scheda Spa")),
        el("button", {
          class: "icon-btn",
          title: "Chiudi",
          on: { click: () => { this._spaAddDlg = false; this._render(); } },
        }, el("ha-icon", { icon: "mdi:close" })))
    );
    const picker = document.createElement("ha-entity-picker");
    picker.hass = this._hass;
    picker.label = "Entità da aggiungere";
    picker.allowCustomEntity = true;
    const confirm = el("button", {
      class: "btn primary",
      disabled: !picker.value,
      on: { click: () => this._spaAddTileCommit(picker.value) },
    }, el("ha-icon", { icon: "mdi:plus" }), el("span", {}, "Aggiungi"));
    picker.addEventListener("value-changed", (event) => {
      const value = (event.detail && event.detail.value) || "";
      picker.value = value;
      confirm.disabled = !value;
    });
    sheet.appendChild(el("div", { class: "detail-section" }, picker));
    sheet.appendChild(
      el("div", { class: "detail-actions" },
        el("div", { style: "flex: 1;" }),
        el("button", {
          class: "btn",
          on: { click: () => { this._spaAddDlg = false; this._render(); } },
        }, "Annulla"),
        confirm)
    );
    overlay.appendChild(sheet);
    return overlay;
  }

  /** The dashed "+" tile appended while editing. */
  _spaAddTile() {
    return el("button", {
      class: "spa-add-tile",
      title: "Aggiungi entità",
      on: { click: (event) => { event.stopPropagation(); this._spaAddOpen(); } },
    },
      el("ha-icon", { icon: "mdi:plus" }),
      el("span", {}, "Aggiungi"));
  }

  /** Hold-to-drag a tile: mouse drags at once, touch needs a short hold. */
  _spaWireDrag(tile, id) {
    let press = null;
    let timer = null;

    const clearTimer = () => {
      if (timer) { clearTimeout(timer); timer = null; }
    };

    const cleanup = () => {
      clearTimer();
      window.removeEventListener("pointermove", onMove);
      window.removeEventListener("pointerup", onUp);
      window.removeEventListener("pointercancel", onUp);
      press = null;
    };

    const begin = () => {
      if (!press) return;
      this._spaDrag = { id, node: tile };
      tile.classList.add("dragging");
      try { tile.setPointerCapture(press.pointerId); } catch (error) { /* ignore */ }
    };

    const onMove = (event) => {
      if (this._spaDrag && this._spaDrag.node === tile) {
        this._spaReorder(tile, event.clientX, event.clientY);
        if (event.cancelable) event.preventDefault();
        return;
      }
      if (!press) return;
      if (Math.hypot(event.clientX - press.x, event.clientY - press.y) > 10) {
        cleanup(); // a scroll, not a long press
      }
    };

    const onUp = () => {
      const wasDragging = this._spaDrag && this._spaDrag.node === tile;
      cleanup();
      if (!wasDragging) return;
      tile.classList.remove("dragging");
      this._spaDrag = null;
      this._spaCommitOrder();
    };

    tile.addEventListener("pointerdown", (event) => {
      if (event.button && event.button !== 0) return;
      const target = event.target;
      if (target && target.closest && target.closest("button")) return;
      press = { x: event.clientX, y: event.clientY, pointerId: event.pointerId };
      window.addEventListener("pointermove", onMove, { passive: false });
      window.addEventListener("pointerup", onUp);
      window.addEventListener("pointercancel", onUp);
      if (event.pointerType === "mouse") begin();
      else timer = setTimeout(begin, 300);
    });

    // Block the page scroll only once the drag is actually running.
    tile.addEventListener("touchmove", (event) => {
      if (this._spaDrag && this._spaDrag.node === tile && event.cancelable) {
        event.preventDefault();
      }
    }, { passive: false });
  }

  /** Move the dragged tile next to whichever sibling is closest to the pointer. */
  _spaReorder(node, x, y) {
    const grid = node.parentNode;
    if (!grid) return;
    const tiles = Array.from(grid.querySelectorAll(".spa-tile")).filter((item) => item !== node);
    let best = null;
    let bestDist = Infinity;
    tiles.forEach((item) => {
      const rect = item.getBoundingClientRect();
      const cx = rect.left + rect.width / 2;
      const cy = rect.top + rect.height / 2;
      const dist = (cx - x) ** 2 + (cy - y) ** 2;
      if (dist < bestDist) { bestDist = dist; best = item; }
    });
    if (!best) return;
    const rect = best.getBoundingClientRect();
    const cx = rect.left + rect.width / 2;
    const cy = rect.top + rect.height / 2;
    const sameRow = Math.abs(y - cy) < rect.height / 2;
    const before = y < cy || (sameRow && x < cx);
    grid.insertBefore(node, before ? best : best.nextSibling);
  }

  /** After a drag: read the new visual order and save it if it changed. */
  async _spaCommitOrder() {
    const grid = this.shadowRoot && this.shadowRoot.querySelector(".spa-grid");
    if (!grid) return;
    const tiles = this._spaTiles();
    const byId = new Map(tiles.map((tile) => [tile.entity_id, tile]));
    const order = Array.from(grid.querySelectorAll(".spa-tile[data-eid]"))
      .map((node) => node.getAttribute("data-eid"));
    const reordered = order.map((item) => byId.get(item)).filter(Boolean);
    if (reordered.length !== tiles.length) return;
    if (reordered.every((tile, index) => tile.entity_id === tiles[index].entity_id)) {
      return; // nothing moved
    }
    await this._spaPersist(reordered);
  }

  /** Call one service on the entity and surface any error in the toast. */
  async _spaCall(domain, service, entity_id, data) {
    this._busySpa = true;
    this._render();
    try {
      await this._hass.callService(domain, service, Object.assign(
        { entity_id }, data || {}
      ));
    } catch (error) {
      this._message = {
        kind: "error",
        text: this._friendlyError(error, "Comando non riuscito."),
      };
    }
    this._busySpa = false;
    this._render();
  }

  _spaToggle(group, id) {
    const state = this._hass && this._hass.states && this._hass.states[id];
    const on = state && state.state === "on";
    this._spaCall(group, on ? "turn_off" : "turn_on", id);
  }

  _spaLock(id, locked) {
    this._spaCall("lock", locked ? "unlock" : "lock", id);
  }

  _spaClimatePower(id, on) {
    this._spaCall("climate", on ? "turn_off" : "turn_on", id);
  }

  _spaClimateMode(id, mode) {
    this._spaCall("climate", "set_hvac_mode", id, { hvac_mode: mode });
  }

  _spaClimateTemp(id, delta) {
    const state = this._hass && this._hass.states && this._hass.states[id];
    const attrs = (state && state.attributes) || {};
    const base = attrs.temperature != null ? Number(attrs.temperature) : 21;
    this._spaCall("climate", "set_temperature", id, {
      temperature: Math.round((base + delta) * 10) / 10,
    });
  }

  _spaSetBrightness(id, pct) {
    this._spaCall("light", "turn_on", id, { brightness_pct: pct });
  }

  // ----------------------------------------------------------------- ACCESSI

  /**
   * Load the Home Assistant users once and cache them. Kept out of the render
   * path so the window never paints an unresolved promise: the tab draws what
   * it has and redraws when the answer arrives.
   */
  async _loadUsers() {
    if (this._usersLoading) return;
    this._usersLoading = true;
    this._usersError = "";
    try {
      const response = await this._service("get_users");
      this._users = (response && response.users) || [];
    } catch (error) {
      this._users = [];
      this._usersError = this._friendlyError(
        error,
        "Impossibile leggere gli utenti Home Assistant. La card deve essere aggiornata all'ultima versione del programma."
      );
    } finally {
      this._usersLoading = false;
      if (this._cfgTab === "accessi") this._render();
    }
  }

  /**
   * Accessi tab: every Home Assistant user and the level of access they have
   * to this dashboard. An admin or owner of Home Assistant is always locked to
   * "Amministratore", so the people who run Home Assistant can never be shut
   * out of the card by an accidental click.
   */
  _renderAccessi() {
    if (this._users === null && !this._usersLoading) this._loadUsers();

    const wrap = el("div", { class: "stack config" });
    const levels = {
      none: "Nessun accesso",
      read: "Solo lettura",
      operator: "Operatore",
      manager: "Gestore",
      admin: "Amministratore",
    };
    const permissions =
      (this._data.settings && this._data.settings.permissions) || {};

    wrap.appendChild(
      el("div", { class: "hint" },
        "Scegli per ogni utente di Home Assistant cosa può vedere e fare in questa dashboard. ",
        "Gli amministratori e il proprietario di Home Assistant restano sempre Amministratori della card, ",
        "per non lasciare mai nessuno chiuso fuori.")
    );
    wrap.appendChild(
      el("div", { class: "hint" },
        "Solo lettura: vede agenda e offerte. Operatore: gestisce la giornata (prenota, check-in/out, conferme). ",
        "Gestore: anche clienti e messaggi. Amministratore: anche la configurazione.")
    );

    if (this._usersLoading) {
      wrap.appendChild(el("div", { class: "empty" }, "Caricamento utenti…"));
      return wrap;
    }
    if (this._usersError) {
      wrap.appendChild(el("div", { class: "empty" }, this._usersError));
      return wrap;
    }
    if (!this._users || !this._users.length) {
      wrap.appendChild(
        el("div", { class: "empty" }, "Nessun utente Home Assistant attivo trovato.")
      );
      return wrap;
    }

    const box = el("div", { class: "cfg-box" }, el("h3", {}, "Utenti Home Assistant"));
    this._users.forEach((user) => {
      const locked = Boolean(user.is_admin || user.is_owner);
      const level = locked
        ? "admin"
        : permissions[user.id] || "none";
      const name = user.name || user.id;
      const initials = name
        .split(/\s+/)
        .filter(Boolean)
        .slice(0, 2)
        .map((part) => part[0].toUpperCase())
        .join("");

      const badges = el("span", { class: "accessi-badges" });
      if (user.is_owner) badges.appendChild(el("span", { class: "badge" }, "Proprietario"));
      if (user.is_admin) badges.appendChild(el("span", { class: "badge" }, "Admin HA"));

      const select = el("select", {
        class: "input",
        disabled: this._busy || locked,
        on: {
          change: async (event) => {
            const chosen = event.target.value;
            try {
              await this._call("set_user_permissions", {
                user_id: user.id,
                level: chosen,
              });
            } catch (error) {
              /* shown by _call */
            }
          },
        },
      });
      Object.entries(levels).forEach(([value, label]) =>
        select.appendChild(
          el("option", { value, selected: value === level }, label)
        )
      );

      box.appendChild(
        el("div", { class: "accessi-row" },
          el("span", { class: "accessi-avatar" }, initials || "?"),
          el("div", { class: "accessi-who" },
            el("span", { class: "accessi-name" }, name),
            badges),
          select)
      );
    });

    if (this._users.some((user) => user.is_admin || user.is_owner)) {
      box.appendChild(
        el("div", { class: "hint" },
          "Le righe con «Proprietario» o «Admin HA» non sono modificabili: sono gli amministratori di Home Assistant.")
      );
    }
    wrap.appendChild(box);
    return wrap;
  }

  // ------------------------------------------------------------ CONFIGURAZIONE

  _renderConfig() {
    const wrap = el("div", { class: "stack config" });

    // The configuration, the Accessi tab included, is for card administrators:
    // the level the Accessi tab itself hands out. A Home Assistant admin who is
    // not listed is an administrator here too (see _userLevel).
    if (!this._can("config")) {
      return el("div", { class: "empty" },
        "La configurazione è riservata agli amministratori.");
    }

    const tabButton = (tab) =>
      el("button", {
        class: `tab small${this._cfgTab === tab.id ? " active" : ""}`,
        title: tab.label,
        on: {
          click: () => {
            this._cfgTab = tab.id;
            this._editing = null;
            this._notifyEditMode = false;
            this._settingsEditMode = false;
            this._settingsDrag = null;
            this._promoEditMode = false;
            this._trtEditMode = false;
            this._opEditMode = false;
            this._operatorFormMode = false;
            this._operatorDrag = null;
            this._accEditMode = false;
            this._accDlg = null;
            this._render();
          },
        },
      }, el("ha-icon", { icon: tab.icon }),
         el("span", { class: "tab-label" }, tab.label));
    wrap.appendChild(
      el("div", { class: "tabs tight" },
        CFG_TABS.filter((tab) => tab.id !== "impostazioni").map(tabButton),
        // Impostazioni sits apart, at the far right.
        el("div", { class: "spacer" }),
        tabButton(CFG_TABS.find((tab) => tab.id === "impostazioni")))
    );

    if (this._cfgTab === "categorie") add(wrap, this._renderCategories());
    if (this._cfgTab === "trattamenti") add(wrap, this._renderTreatments());
    if (this._cfgTab === "accessori") add(wrap, this._renderAccessori());
    if (this._cfgTab === "operatori") add(wrap, this._renderOperators());
    if (this._cfgTab === "blocchi") add(wrap, this._renderBlocks());
    if (this._cfgTab === "notifiche") add(wrap, this._renderNotify());
    if (this._cfgTab === "promo") add(wrap, this._renderPromo());
    if (this._cfgTab === "accessi") add(wrap, this._renderAccessi());
    if (this._cfgTab === "impostazioni") add(wrap, this._renderSettings());

    return wrap;
  }

  // ----------------------------------------------------------- notifications

  /**
   * Form for a new closure. The scope decides which target picker is shown:
   * the facility closes without any, a category and an operator each need
   * theirs, otherwise the closure would silently apply to nothing.
   */
  _closureForm() {
    const draft = this._closureDraft || (this._closureDraft = {
      scope: "facility",
      operator_id: "",
      category_id: "",
      date_from: todayStr(),
      date_to: "",
      start: "",
      end: "",
      label: "",
    });

    const scopeSelect = el("select", {
      class: "input",
      on: {
        change: (event) => {
          draft.scope = event.target.value;
          this._render();
        },
      },
    });
    [
      ["facility", "Struttura intera"],
      ["category", "Una categoria"],
      ["operator", "Una operatrice"],
    ].forEach(([value, label]) =>
      scopeSelect.appendChild(
        el("option", { value, selected: draft.scope === value }, label)
      )
    );

    const targetSelect = (values, selected, onPick) => {
      const select = el("select", {
        class: "input",
        on: {
          change: (event) => {
            onPick(event.target.value);
            this._render();
          },
        },
      });
      values.forEach(([value, label]) =>
        select.appendChild(
          el("option", { value, selected: value === selected }, label)
        )
      );
      return select;
    };

    const categories = [...this._data.categories]
      .sort((a, b) => a.name.localeCompare(b.name))
      .map((c) => [c.id, c.name]);
    const operators = [...this._data.operators]
      .sort((a, b) => a.name.localeCompare(b.name))
      .map((o) => [o.id, o.name]);

    const box = el("div", { class: "row" },
      el("label", { class: "field" }, el("span", {}, "Chiudi"), scopeSelect));

    if (draft.scope === "category") {
      box.appendChild(
        el("label", { class: "field" }, el("span", {}, "Categoria"),
          targetSelect(categories, draft.category_id, (value) => {
            draft.category_id = value;
          }))
      );
    } else if (draft.scope === "operator") {
      box.appendChild(
        el("label", { class: "field" }, el("span", {}, "Operatrice"),
          targetSelect(operators, draft.operator_id, (value) => {
            draft.operator_id = value;
          }))
      );
    }

    box.appendChild(
      el("label", { class: "field" }, el("span", {}, "Dal giorno"),
        el("input", {
          class: "input", type: "date", value: draft.date_from,
          on: { change: (event) => { draft.date_from = event.target.value || todayStr(); } },
        }))
    );
    box.appendChild(
      el("label", { class: "field" }, el("span", {}, "Al giorno"),
        el("input", {
          class: "input", type: "date", value: draft.date_to,
          on: { change: (event) => { draft.date_to = event.target.value; } },
        }))
    );
    box.appendChild(
      el("label", { class: "field" }, el("span", {}, "Dalle"),
        el("input", {
          class: "input", type: "time", value: draft.start,
          on: { change: (event) => { draft.start = event.target.value || ""; } },
        }))
    );
    box.appendChild(
      el("label", { class: "field" }, el("span", {}, "Alle"),
        el("input", {
          class: "input", type: "time", value: draft.end,
          on: { change: (event) => { draft.end = event.target.value || ""; } },
        }))
    );
    box.appendChild(
      el("label", { class: "field grow" }, el("span", {}, "Motivo"),
        el("input", {
          class: "input", type: "text", value: draft.label,
          placeholder: "es. Ferie, manutenzione",
          on: { input: (event) => { draft.label = event.target.value; } },
        }))
    );

    const outer = el("div", { class: "stack tight" });
    outer.appendChild(box);
    outer.appendChild(el("div", { class: "hint" },
      "Lascia vuote le fasce per chiudere la giornata intera, e vuota la data di fine per un solo giorno. " +
      "Struttura e categoria rifiutano la prenotazione; per un'operatrice la fascia resta libera e viene proposta a una collega."));
    outer.appendChild(
      el("button", {
        class: "btn primary",
        disabled: this._busy,
        on: {
          click: async () => {
            try {
              await this._call("add_closure", {
                scope: draft.scope,
                operator_id: draft.operator_id,
                category_id: draft.category_id,
                date_from: draft.date_from,
                date_to: draft.date_to,
                start: draft.start,
                end: draft.end,
                label: draft.label,
              });
              this._closureDraft = null;
              this._render();
            } catch (error) {
              /* shown */
            }
          },
        },
      }, "Chiudi")
    );
    return outer;
  }

  /** One closure in the list, with the button that reopens it. */
  /** Who a closure applies to: the whole facility, one category, one operator. */
  _closureScopeLabel(closure) {
    if (closure.scope === "category") {
      return (this._lookup.category.get(closure.category_id) || {}).name || "Categoria";
    }
    if (closure.scope === "operator") {
      return (this._lookup.operator.get(closure.operator_id) || {}).name || "Operatrice";
    }
    return "Struttura intera";
  }

  /** The days and the clock of a closure, as one readable line. */
  _closureWhen(closure) {
    const days = closure.date_from +
      (closure.date_to && closure.date_to !== closure.date_from ? ` → ${closure.date_to}` : "");
    // Half a range means the whole day, exactly as the backend reads it.
    const clock = closure.start && closure.end ? ` · ${closure.start}–${closure.end}` : " · giornata intera";
    return `${days}${clock}`;
  }

  /**
   * The closures touching each of the days being drawn, keyed by day.
   *
   * One pass over the closures for the whole grid, so the calendar asks the
   * question once instead of once per cell. Dates are stored as plain local
   * calendar days, so a plain string comparison is the right one.
   */
  _closuresByDay(days) {
    const byDay = new Map();
    (this._data.closures || []).forEach((closure) => {
      const from = closure.date_from;
      if (!from) return;
      const rawTo = closure.date_to || from;
      const to = rawTo < from ? from : rawTo;
      days.forEach((key) => {
        if (key < from || key > to) return;
        if (!byDay.has(key)) byDay.set(key, []);
        byDay.get(key).push(closure);
      });
    });
    return byDay;
  }

  _closureRow(closure) {
    const scopeLabel = this._closureScopeLabel(closure);
    const when = this._closureWhen(closure);

    return el(
      "div",
      { class: "row item" },
      el(
        "div",
        { class: "grow" },
        el("div", { class: "row" },
          el("span", {}, scopeLabel),
          closure.label ? el("span", { class: "chip" }, closure.label) : null),
        el("div", { class: "dim small" }, when)),
      el(
        "button",
        {
          class: "icon-btn danger",
          title: "Riapri",
          disabled: this._busy,
          on: {
            click: async () => {
              try {
                await this._call("delete_closure", { closure_id: closure.id });
              } catch (error) {
                /* shown */
              }
            },
          },
        },
        el("ha-icon", { icon: "mdi:lock-open" }))
    );
  }

  /** Closures and refused windows: who cannot work, when, and how to reopen. */
  _renderBlocks() {
    const wrap = el("div", { class: "stack" });
    const closures = [...(this._data.closures || [])].sort((a, b) =>
      `${a.date_from} ${a.start}`.localeCompare(`${b.date_from} ${b.start}`)
    );
    const blocks = [...(this._data.slot_blocks || [])]
      .sort((a, b) => `${a.date} ${a.start}`.localeCompare(`${b.date} ${b.start}`));

    // Two columns: the form on the left, the blocked days and slots on the
    // right, so the list is read while a new closure is entered.
    const columns = el("div", { class: "two-col" });
    const left = el("div", { class: "stack tight" });
    const right = el("div", { class: "stack tight" });

    left.appendChild(el("h3", {}, "Nuova chiusura"));
    add(left, this._closureForm());

    right.appendChild(el("h3", {}, "Giorni e fasce chiuse"));
    if (!closures.length) {
      right.appendChild(el("div", { class: "empty" },
        "Nessuna chiusura: si possono chiudere giorni o fasce per la struttura, " +
        "per una categoria o per una singola operatrice."));
    } else {
      closures.forEach((closure) => add(right, this._closureRow(closure)));
    }

    right.appendChild(el("h3", {}, "Fasce orarie rifiutate"));
    if (!blocks.length) {
      right.appendChild(el("div", { class: "empty" },
        "Nessuna fascia rifiutata: quando una massaggiatrice rifiuta un turno, " +
        "la fascia viene bloccata solo per lei."));
    } else {
      blocks.forEach((block) => {
        const operator = this._lookup.operator.get(block.operator_id);
        const appointment = this._lookup.appointment.get(block.appointment_id);
        const treatment = appointment
          ? this._lookup.treatment.get(appointment.treatment_id)
          : null;
        const clientName = appointment ? this._clientName(appointment) : "";

        right.appendChild(
          el("div", { class: "row block-row" },
            el("div", { class: "stack tight" },
              el("div", {},
                operator ? operator.name : "Operatrice sconosciuta",
                el("span", { class: "dim" }, ` · ${shortDay(parseLocal(block.date, block.start))} ${block.start}–${block.end}`)),
              el("div", { class: "dim small" },
                [treatment ? treatment.name : null, clientName].filter(Boolean).join(" · ") || "fascia senza appuntamento")),
            el("div", { class: "spacer" }),
            el("button", {
              class: "btn small",
              disabled: this._busy,
              title: "Riapre questa fascia per la massaggiatrice",
              on: {
                click: async () => {
                  try {
                    await this._call("clear_slot_block", {
                      operator_id: block.operator_id,
                      appointment_id: block.appointment_id,
                    });
                  } catch (error) { /* shown */ }
                },
              },
            }, el("ha-icon", { icon: "mdi:lock-open-variant" }), "Riapri")
          )
        );
      });

      right.appendChild(el("div", { class: "hint" },
        "«Riapri» rende di nuovo contattabile la massaggiatrice per quella fascia: se l'appuntamento " +
        "è ancora senza operatrice le verrà riproposta."));
    }

    columns.appendChild(left);
    columns.appendChild(right);
    wrap.appendChild(columns);

    return wrap;
  }

  _renderNotify() {
    const wrap = el("div", { class: "stack" + (this._notifyEditMode ? " form-edit" : "") });
    const settings = this._data.settings || {};
    const draft = this._notifyDraft || (this._notifyDraft = { ...settings });

    // Edit mode toggle in the header.
    if (this._can("config")) wrap.appendChild(this._notifyHeader());

    // Two columns of blocks. In edit mode the blocks drag by their handle, the
    // same way the booking form does.
    const columns = this._colsGrid("notifiche");
    const left = el("div", { class: "stack tight form-col", "data-col": "left" });
    const right = el("div", { class: "stack tight form-col", "data-col": "right" });

    // One field appended to a given box, so the layout can be reorganised
    // without touching the fields themselves.
    const field = (box, label, key, placeholder, hint) => {
      box.appendChild(
        el("label", { class: "field" }, el("span", {}, label),
          el("input", { class: "input", type: "text", value: draft[key] || "",
            placeholder: placeholder || "",
            on: { input: (event) => { draft[key] = event.target.value; } } }))
      );
      if (hint) box.appendChild(el("div", { class: "hint" }, hint));
    };
    const box = (id, title, ...children) => {
      const node = el("div", { class: "cfg-box" }, el("h3", {}, title));
      add(node, children);
      return this._tagBlock(id, this._notifySection(id, node));
    };

    // Left column: the two channels, one box each, with a test button per chat.
    const telegramBox = box("telegram", "Telegram");
    field(telegramBox, "ID configurazione bot", "telegram_config_entry_id", "01JZ6G7...",
      "ID della configurazione del bot Telegram da usare per i messaggi.");
    field(telegramBox, "Chat Telegram del report", "report_telegram_chats", "933728087, 5400097873",
      "Separate da virgola. Ricevono il report completo di ogni mese.");
    add(telegramBox, this._testRows("telegram", draft.report_telegram_chats));
    left.appendChild(telegramBox);

    const whatsappBox = box("whatsapp", "WhatsApp");
    field(whatsappBox, "Chat WhatsApp del report", "report_whatsapp_chat", "120363@g.us",
      "Lascia vuoto se il report completo non deve andare su WhatsApp.");
    add(whatsappBox, this._testRows("whatsapp", draft.report_whatsapp_chat));
    whatsappBox.appendChild(
      el("label", { class: "field" }, el("span", {}, "Prova su un numero"),
        el("input", {
          class: "input", type: "tel", placeholder: "es. 333 1234567 · estero: +41 79 1234567",
          value: draft.report_whatsapp_test || "",
          on: { input: (event) => { draft.report_whatsapp_test = event.target.value; } },
        }))
    );
    whatsappBox.appendChild(
      el("div", { class: "row tight" },
        el("button", {
          class: "btn small",
          disabled: this._busy,
          on: {
            click: () => {
              const raw = String(draft.report_whatsapp_test || "").trim();
              if (!raw) {
                this._message = { kind: "error", text: "Inserisci un numero o una chat WhatsApp da provare." };
                this._render();
                return;
              }
              const id = raw.includes("@") ? raw : this._whatsappIdOf({ phone: raw, whatsapp_chat_id: "" });
              this._testChannel("whatsapp", id);
            },
          },
        }, el("ha-icon", { icon: "mdi:whatsapp" }), "Prova WhatsApp"))
    );
    left.appendChild(whatsappBox);

    // The WAHA gateway: where the add-on is, its key, the session, and the two
    // buttons that prove it. Everything here is local to this installation:
    // with an URL set, every WhatsApp send goes straight to the add-on, and the
    // webhook below brings the operators' answers back with no other
    // integration and no automation in the way.
    const wahaBox = box("waha", "Gateway WhatsApp (WAHA)");
    field(wahaBox, "Indirizzo WAHA", "waha_url", "http://homeassistant:3000",
      "Indirizzo dell'add-on WAHA. Vuoto = si usa il rest_command del pacchetto, come prima.");
    wahaBox.appendChild(
      el("label", { class: "field" }, el("span", {}, "Chiave API"),
        el("input", { class: "input", type: "password",
          value: draft.waha_api_key || "",
          placeholder: "chiave dell'add-on",
          autocomplete: "new-password",
          on: { input: (event) => { draft.waha_api_key = event.target.value; } } }))
    );
    wahaBox.appendChild(el("div", { class: "hint" },
      "La stessa chiave configurata nell'add-on WAHA. È nascosta e non viene mai mostrata."));
    field(wahaBox, "Sessione", "waha_session", "default",
      "Nome della sessione WAHA che porta il numero dell'hotel.");
    field(wahaBox, "Indirizzo Home Assistant (solo se WAHA è su un altro host)", "waha_ha_url",
      "http://homeassistant:8123",
      "Come l'add-on raggiunge Home Assistant, usato per il webhook delle risposte. Vuoto = rete Supervisor.");
    wahaBox.appendChild(
      el("div", { class: "row tight" },
        el("button", {
          class: "btn small",
          disabled: this._busy,
          on: { click: () => this._checkWaha() },
        }, el("ha-icon", { icon: "mdi:lan-check" }), "Verifica connessione"),
        el("button", {
          class: "btn small primary",
          disabled: this._busy,
          on: { click: () => this._enableWaha() },
        }, el("ha-icon", { icon: "mdi:webhook" }), "Attiva ricezione risposte"))
    );
    if (this._wahaStatus) {
      wahaBox.appendChild(
        el("div", { class: "hint" }, this._wahaStatus)
      );
    }
    wahaBox.appendChild(el("div", { class: "hint" },
      "«Verifica connessione» chiede all'add-on la sua versione, senza inviare messaggi. " +
      "«Attiva ricezione» iscrive la sessione al webhook di Spa Booking: da quel momento le " +
      "risposte delle massaggiatrici (testo o reazione) arrivano qui, senza altre integrazioni."));
    wahaBox.appendChild(
      el("div", { class: "row tight" },
        el("button", {
          class: "btn primary small",
          disabled: this._busy,
          on: {
            click: async () => {
              try {
                await this._call("update_settings", {
                  waha_url: (draft.waha_url || "").trim(),
                  waha_api_key: draft.waha_api_key || "",
                  waha_session: (draft.waha_session || "").trim(),
                  waha_ha_url: (draft.waha_ha_url || "").trim(),
                });
                this._wahaStatus = "Impostazioni gateway salvate.";
                this._render();
              } catch (error) { /* shown */ }
            },
          },
        }, el("ha-icon", { icon: "mdi:content-save" }), "Salva gateway"))
    );
    left.appendChild(wahaBox);

    // Right column: how the report goes out, the offer timings, deposit request
    // and guest headline.
    const reportBox = box("report", "Invio report");
    reportBox.appendChild(
      el("label", { class: "check" },
        el("input", { type: "checkbox", checked: draft.report_per_operator !== false,
          on: { change: (event) => { draft.report_per_operator = event.target.checked; } } }),
        el("span", {}, "Invia a ogni massaggiatrice anche il suo riepilogo personale"))
    );
    reportBox.appendChild(
      el("div", { class: "row" },
        el("button", {
          class: "btn primary",
          disabled: this._busy,
          on: {
            click: async () => {
              try {
                await this._call("update_settings", {
                  report_telegram_chats: draft.report_telegram_chats || "",
                  report_whatsapp_chat: draft.report_whatsapp_chat || "",
                  telegram_config_entry_id: draft.telegram_config_entry_id || "",
                  report_per_operator: draft.report_per_operator !== false,
                  offer_timeout_hours: Number(draft.offer_timeout_hours) || 24,
                  offer_reminder_hours: Number(draft.offer_reminder_hours) || 2,
                });
              } catch (error) { /* shown */ }
            },
          },
        }, "Salva destinatari"),
        el("button", {
          class: "btn",
          disabled: this._busy,
          on: {
            click: async () => {
              if (!window.confirm("Inviare subito il report del mese scorso?")) return;
              try {
                const result = await this._call("get_monthly_report", { notify: true });
                const sent = (result && result.sent) || 0;
                const failed = (result && result.failed) || 0;
                this._message = {
                  kind: failed ? "error" : "ok",
                  text: "Report inviato: " + sent + " canali ok, " + failed + " falliti.",
                };
                this._render();
              } catch (error) { /* shown */ }
            },
          },
        }, el("ha-icon", { icon: "mdi:send" }), "Invia ora"))
    );
    reportBox.appendChild(el("div", { class: "hint" },
      "L'automazione «SPA: report mensile massaggi» invia il report del mese precedente il 1° di ogni mese alle 08:00."));
    right.appendChild(reportBox);

    const offerBox = box("offers", "Offerte alle massaggiatrici");
    offerBox.appendChild(
      el("div", { class: "row" },
        el("label", { class: "field" },
          el("span", {}, "Scadenza offerta (ore)"),
          el("input", {
            class: "input",
            type: "number",
            min: "1",
            step: "1",
            value: draft.offer_timeout_hours != null ? draft.offer_timeout_hours : 24,
            on: { input: (event) => { draft.offer_timeout_hours = Number(event.target.value) || 24; } },
          })),
        el("label", { class: "field" },
          el("span", {}, "Promemoria (ore)"),
          el("input", {
            class: "input",
            type: "number",
            min: "0",
            step: "1",
            value: draft.offer_reminder_hours != null ? draft.offer_reminder_hours : 2,
            on: { input: (event) => { draft.offer_reminder_hours = Number(event.target.value) || 0; } },
          })))
    );
    offerBox.appendChild(el("div", { class: "hint" },
      "Alla scadenza l'offerta passa automaticamente alla successiva massaggiatrice abile. " +
      "Chi rifiuta non viene ricontattata per la stessa fascia oraria finche' non si segnala di nuovo disponibile."));
    right.appendChild(offerBox);

    // Deposit request: bank details and the message the guest receives.
    const depositBox = box("deposit", "Richiesta acconto");
    depositBox.appendChild(
      el("label", { class: "field" },
        el("span", {}, "Intestatario bonifico"),
        el("input", { class: "input", type: "text",
          value: draft.deposit_intestatario || "",
          placeholder: "IL MARCHESE SOC COOP ARL",
          on: { input: (event) => { draft.deposit_intestatario = event.target.value; } } }))
    );
    depositBox.appendChild(
      el("label", { class: "field" },
        el("span", {}, "IBAN"),
        el("input", { class: "input", type: "text",
          value: draft.deposit_iban || "",
          placeholder: "IT92Q0326882970052705511040",
          on: { input: (event) => { draft.deposit_iban = event.target.value; } } }))
    );
    depositBox.appendChild(el("div", { class: "hint" },
      "Compare nella richiesta inviata all'ospite."));
    depositBox.appendChild(
      el("label", { class: "field" },
        el("span", {}, "Messaggio all'ospite"),
        el("textarea", { class: "input", rows: "12",
          on: { input: (event) => { draft.deposit_message = event.target.value; } },
        }, draft.deposit_message || ""))
    );
    depositBox.appendChild(el("div", { class: "hint" },
      "Inviato dal pulsante nell'appuntamento, o chiedendolo quando la richiesta " +
      "viene salvata. Segnaposti: {nome} nome, " +
      "{importo} acconto, {intestatario} e {iban} dati sopra, {codice} codice prenotazione."));
    depositBox.appendChild(
      el("label", { class: "field" },
        el("span", {}, "Numero di prova"),
        el("input", { class: "input", type: "tel", placeholder: "es. 333 1234567 · estero: +41 79 1234567",
          value: draft.deposit_test_phone || "",
          on: { input: (event) => { draft.deposit_test_phone = event.target.value; } } }))
    );
    depositBox.appendChild(
      el("div", { class: "row tight" },
        el("button", {
          class: "btn small",
          disabled: this._busy,
          on: {
            click: () => {
              const raw = String(draft.deposit_test_phone || "").trim();
              if (!raw) {
                this._message = { kind: "error", text: "Inserisci un numero di prova." };
                this._render();
                return;
              }
              const id = raw.includes("@") ? raw : this._whatsappIdOf({ phone: raw, whatsapp_chat_id: "" });
              this._testChannel("whatsapp", id, this._sampleMessage(draft.deposit_message, {
                intestatario: draft.deposit_intestatario || "IL MARCHESE SOC COOP ARL",
                iban: draft.deposit_iban || "IT92Q0326882970052705511040",
              }));
            },
          },
        }, el("ha-icon", { icon: "mdi:whatsapp" }), "Prova su WhatsApp"))
    );
    right.appendChild(depositBox);

    // Guest-facing summary headline.
    const guestBox = box("guest_header", "Intestazione riepilogo");
    guestBox.appendChild(
      el("label", { class: "field" },
        el("span", {}, "Nome hotel / intestazione"),
        el("input", { class: "input", type: "text",
          value: draft.guest_header || "",
          placeholder: "Il Marchese Hotel & Spa",
          on: { input: (event) => { draft.guest_header = event.target.value; } } }))
    );
    guestBox.appendChild(el("div", { class: "hint" },
      "Compare come titolo nel riepilogo inviato all'ospite (dopo RIEPILOGO APPUNTAMENTO)."));
    right.appendChild(guestBox);

    // Riepilogo appuntamento: il testo che l'ospite riceve alla conferma.
    const summaryBox = box("summary", "Riepilogo appuntamento");
    summaryBox.appendChild(
      el("label", { class: "field" },
        el("span", {}, "Testo del riepilogo"),
        el("textarea", { class: "input", rows: "16",
          on: { input: (event) => { draft.summary_message = event.target.value; } },
        }, draft.summary_message || ""))
    );
    summaryBox.appendChild(el("div", { class: "hint" },
      "Inviato via WhatsApp all'ospite quando l'appuntamento viene confermato. " +
      "Segnaposti: {nome}, {cognome}, {cliente} nome e cognome, {hotel} intestazione qui sopra, " +
      "{codice} codice prenotazione, {trattamento}, {durata} minuti, {data}, {ora}, {fine}, " +
      "{totale} prezzo, {acconto} acconto richiesto, {versato} incassato, {residuo} da saldare, " +
      "{pagamenti} elenco dei versamenti registrati."));
    summaryBox.appendChild(
      el("label", { class: "field" },
        el("span", {}, "Numero di prova"),
        el("input", { class: "input", type: "tel", placeholder: "es. 333 1234567 · estero: +41 79 1234567",
          value: draft.summary_test_phone || "",
          on: { input: (event) => { draft.summary_test_phone = event.target.value; } } }))
    );
    summaryBox.appendChild(
      el("div", { class: "row tight" },
        el("button", {
          class: "btn small",
          disabled: this._busy,
          on: {
            click: () => {
              const raw = String(draft.summary_test_phone || "").trim();
              if (!raw) {
                this._message = { kind: "error", text: "Inserisci un numero di prova." };
                this._render();
                return;
              }
              const id = raw.includes("@") ? raw : this._whatsappIdOf({ phone: raw, whatsapp_chat_id: "" });
              this._testChannel("whatsapp", id, this._sampleMessage(draft.summary_message));
            },
          },
        }, el("ha-icon", { icon: "mdi:whatsapp" }), "Prova su WhatsApp"))
    );
    right.appendChild(summaryBox);

    // Messaggio richiesta: il testo inviato al richiedente quando salva la richiesta.
    const reqMsgBox = box("request_message", "Messaggio richiesta");
    reqMsgBox.appendChild(
      el("label", { class: "field" },
        el("span", {}, "Testo messaggio"),
        el("textarea", { class: "input", rows: "14",
          on: { input: (event) => { draft.request_message = event.target.value; } },
        }, draft.request_message || ""))
    );
    reqMsgBox.appendChild(el("div", { class: "hint" },
      "Inviato automaticamente via WhatsApp al richiedente (se ha il telefono) " +
      "quando la richiesta viene salvata. Segnaposti: {nome} nome, {cognome} cognome, " +
      "{data} data, {ora} orario del primo trattamento, {persone} numero persone, " +
      "{trattamenti} elenco trattamenti, {codice} codice richiesta."));
    right.appendChild(reqMsgBox);

    // Appointment reminder: customizable message sent before the appointment.
    const apptReminderBox = box("appointment_reminder", "Prememoria appuntamento");
    apptReminderBox.appendChild(
      el("label", { class: "field" },
        el("span", {}, "Testo messaggio"),
        el("textarea", { class: "input", rows: "12",
          on: { input: (event) => { draft.appointment_reminder_message = event.target.value; } },
        }, draft.appointment_reminder_message || ""))
    );
    apptReminderBox.appendChild(el("div", { class: "hint" },
      "Inviato via WhatsApp al cliente prima dell'appuntamento. " +
      "Segnaposti: {nome} nome, {cognome} cognome, {data} data (dd/mm/yyyy), " +
      "{ora} orario, {trattamenti} elenco trattamenti, {codice} codice prenotazione."));
    apptReminderBox.appendChild(
      el("label", { class: "check" },
        el("input", {
          type: "checkbox",
          checked: draft.appointment_reminder_auto !== false,
          on: { change: (event) => {
            draft.appointment_reminder_auto = event.target.checked;
            this._render();
          } },
        }),
        el("span", {}, "Invio automatico (ricorda l'appuntamento a tutti i clienti)"))
    );
    if (draft.appointment_reminder_auto !== false) {
      apptReminderBox.appendChild(
        el("label", { class: "field" },
          el("span", {}, "Ore prima dell'appuntamento"),
          el("input", {
            class: "input", type: "number", min: "1", max: "168",
            value: draft.appointment_reminder_hours || 24,
            on: { input: (event) => { draft.appointment_reminder_hours = Number(event.target.value) || 24; } },
          })));
      apptReminderBox.appendChild(el("div", { class: "hint" },
        "Il messaggio viene inviato automaticamente quando mancano le ore indicate all'appuntamento."));
    } else {
      apptReminderBox.appendChild(el("div", { class: "hint" },
        "Invio manuale: usa il pulsante qui sotto per inviare la prememoria."));
    }
    apptReminderBox.appendChild(
      el("div", { class: "row tight" },
        el("button", {
          class: "btn small",
          disabled: this._busy,
          on: { click: async () => {
            try {
              this._busy = true; this._render();
              await this._call("send_reminders", { appointment_id: null });
              this._message = { kind: "ok", text: "Prememoria inviati." };
            } catch (error) { /* shown */ }
            this._busy = false; this._render();
          } },
        }, el("ha-icon", { icon: "mdi:send-outline" }), "Invia prememoria manualmente"))
    );
    right.appendChild(apptReminderBox);

    // Review request: the text a guest receives, whether it goes out on its own
    // and after how long, a test number, and the ready-made placeholders.
    const reviewBox = box("review", "Richiesta recensione");
    reviewBox.appendChild(
      el("label", { class: "field" },
        el("span", {}, "Testo messaggio"),
        el("textarea", { class: "input", rows: "12",
          on: { input: (event) => { draft.review_request_message = event.target.value; } },
        }, draft.review_request_message || ""))
    );
    reviewBox.appendChild(el("div", { class: "hint" },
      "Inviato via WhatsApp al cliente dopo il trattamento, o dal pulsante nel " +
      "popup dell'appuntamento. Usa {nome} per il nome del cliente."));
    reviewBox.appendChild(
      el("label", { class: "check" },
        el("input", {
          type: "checkbox",
          checked: draft.review_request_auto !== false,
          on: { change: (event) => {
            draft.review_request_auto = event.target.checked;
            this._render();
          } },
        }),
        el("span", {}, "Invio automatico (chiede la recensione a tutti i clienti)"))
    );
    if (draft.review_request_auto !== false) {
      reviewBox.appendChild(
        el("label", { class: "field" },
          el("span", {}, "Ore dopo il trattamento"),
          el("input", {
            class: "input", type: "number", min: "1", max: "168",
            value: draft.review_request_after_hours || 6,
            on: { input: (event) => { draft.review_request_after_hours = Number(event.target.value) || 6; } },
          })));
      reviewBox.appendChild(el("div", { class: "hint" },
        "La richiesta parte da sola quando sono passate le ore indicate dalla fine del trattamento."));
    } else {
      reviewBox.appendChild(el("div", { class: "hint" },
        "Invio manuale: usa il pulsante nel popup dell'appuntamento per chiedere la recensione."));
    }
    reviewBox.appendChild(
      el("label", { class: "field" },
        el("span", {}, "Numero di prova"),
        el("input", { class: "input", type: "tel", placeholder: "es. 333 1234567 · estero: +41 79 1234567",
          value: draft.review_request_test_phone || "",
          on: { input: (event) => { draft.review_request_test_phone = event.target.value; } } }))
    );
    reviewBox.appendChild(
      el("div", { class: "row tight" },
        el("button", {
          class: "btn small",
          disabled: this._busy,
          on: {
            click: () => {
              const raw = String(draft.review_request_test_phone || "").trim();
              if (!raw) {
                this._message = { kind: "error", text: "Inserisci un numero di prova." };
                this._render();
                return;
              }
              const id = raw.includes("@") ? raw : this._whatsappIdOf({ phone: raw, whatsapp_chat_id: "" });
              this._testChannel("whatsapp", id, this._sampleMessage(draft.review_request_message));
            },
          },
        }, el("ha-icon", { icon: "mdi:whatsapp" }), "Prova su WhatsApp"))
    );
    right.appendChild(reviewBox);

    // Anteprima report: a real, movable block like the others. It is added
    // before the order is applied, so a saved position (either column) sticks.
    left.appendChild(box("preview", "Anteprima report", this._reportControls()));

    this._placeBlocks(left, right, "notifiche_order");
    columns.appendChild(left);
    columns.appendChild(right);
    wrap.appendChild(columns);

    // Save the deposit request and guest headline.
    const saveBox = el("div", { class: "cfg-box" }, el("h3", {}, "Salva modifiche"));
    saveBox.appendChild(
      el("div", { class: "row tight" },
        el("button", {
          class: "btn primary small",
          disabled: this._busy,
          on: {
            click: async () => {
              try {
                await this._call("update_settings", {
                  deposit_intestatario: draft.deposit_intestatario || "",
                  deposit_iban: draft.deposit_iban || "",
                  deposit_message: draft.deposit_message || "",
                  deposit_test_phone: draft.deposit_test_phone || "",
                  guest_header: draft.guest_header || "",
                  summary_message: draft.summary_message || "",
                  summary_test_phone: draft.summary_test_phone || "",
                  request_message: draft.request_message || "",
                  appointment_reminder_message: draft.appointment_reminder_message || "",
                  appointment_reminder_auto: draft.appointment_reminder_auto !== false,
                  appointment_reminder_hours: draft.appointment_reminder_hours || 24,
                  review_request_message: draft.review_request_message || "",
                  review_request_auto: draft.review_request_auto !== false,
                  review_request_after_hours: draft.review_request_after_hours || 6,
                  review_request_test_phone: draft.review_request_test_phone || "",
                });
                this._message = { kind: "ok", text: "Impostazioni notifiche salvate." };
                this._render();
              } catch (error) { /* shown */ }
            },
          },
        }, el("ha-icon", { icon: "mdi:content-save" }), "Salva notifiche"))
    );
    wrap.appendChild(saveBox);

    return wrap;
  }

  // --------------------------------------------------------------- PROMO

  /** Wrap a promo block for edit mode: only the drag handle is added. */
  _promoSection(id, content) {
    if (!this._promoEditMode) return content;
    const sec = el("div", { class: "form-sec", "data-section": id });
    sec.appendChild(content);
    sec.appendChild(
      el("button", {
        class: "icon-btn form-grip",
        title: "Sposta blocco",
      }, el("ha-icon", { icon: "mdi:drag-horizontal-variant" }))
    );
    sec.draggable = true;
    return sec;
  }

  /** Title row of the promo tab: pencil toggle for edit mode. */
  _promoHeader() {
    const head = el("div", { class: "spa-head" });
    if (this._promoEditMode) head.appendChild(this._colChooser("promo"));
    head.appendChild(
      el("div", { class: "spa-head-title" },
        el("ha-icon", { icon: "mdi:bullhorn-outline" }),
        el("span", {}, this._promoEditMode ? "Modifica promo" : "Promo"))
    );
    if (this._promoEditMode) {
      head.appendChild(
        el("div", { class: "spa-head-actions" },
          el("button", {
            class: "btn primary small",
            title: "Fine modifica",
            on: { click: () => { this._promoEditMode = false; this._render(); } },
          }, el("ha-icon", { icon: "mdi:check" })))
      );
      return head;
    }
    head.appendChild(
      el("button", {
        class: "icon-btn spa-menu-btn",
        title: "Modifica scheda promo",
        on: { click: () => { this._promoEditMode = true; this._render(); } },
      }, el("ha-icon", { icon: "mdi:pencil" }))
    );
    return head;
  }

  /** Count clients that have a phone number (eligible for the broadcast). */
  _promoRecipients() {
    const clients = (this._data && this._data.clients) || [];
    return clients.filter(
      (c) => (c.phone || "").trim() && c.promo_opt_in !== false
    ).length;
  }

  _renderPromo() {
    const settings = (this._data && this._data.settings) || {};
    if (!this._promoDraft) {
      this._promoDraft = {
        promo_message: settings.promo_message || "",
        promo_time: settings.promo_time || "",
        promo_interval_sec: settings.promo_interval_sec != null ? settings.promo_interval_sec : 3,
        promo_max_sends: settings.promo_max_sends || 0,
        promo_window_min: settings.promo_window_min || 10,
        promo_date: settings.promo_date || "",
        promo_code: settings.promo_code || "",
        promo_expiry: settings.promo_expiry || "",
        promo_voucher_message: settings.promo_voucher_message || "",
        promo_voucher_days: settings.promo_voucher_days != null
          ? settings.promo_voucher_days : 30,
        promo_voucher_discount: settings.promo_voucher_discount != null
          ? settings.promo_voucher_discount : 10,
        promo_voucher_min_spend: settings.promo_voucher_min_spend != null
          ? settings.promo_voucher_min_spend : 100,
        promo_voucher_max_spend: settings.promo_voucher_max_spend != null
          ? settings.promo_voucher_max_spend : 500,
        promo_voucher_after_hours: settings.promo_voucher_after_hours != null
          ? settings.promo_voucher_after_hours : 24,
        promo_voucher_auto: settings.promo_voucher_auto === true,
      };
    }
    const draft = this._promoDraft;
    const wrap = el("div", { class: "stack" });
    const canOffer = this._can("offers");

    // Edit mode toggle in the header.
    if (canOffer) wrap.appendChild(this._promoHeader());

    // Two columns of blocks for drag-and-drop in edit mode.
    const columns = this._colsGrid("promo");
    const left = el("div", { class: "stack tight form-col", "data-col": "left" });
    const right = el("div", { class: "stack tight form-col", "data-col": "right" });
    this._blockWire(columns, "promo");

    const box = (id, title, ...children) => {
      const node = el("div", { class: "cfg-box" }, el("h3", {}, title));
      add(node, children);
      return this._tagBlock(id, this._promoSection(id, node));
    };

    // Left: message editor + manual send.
    const messageBox = box("message", "Messaggio promo");
    messageBox.appendChild(
      el("label", { class: "field" },
        el("span", {}, "Testo del messaggio"),
        el("textarea", { class: "input", rows: "12",
          on: { input: (event) => { draft.promo_message = event.target.value; } },
        }, draft.promo_message || ""))
    );
    messageBox.appendChild(
      el("label", { class: "field" }, el("span", {}, "Codice promo"),
        el("input", { class: "input", type: "text", value: draft.promo_code || "",
          placeholder: "es. ESTATE20",
          on: { input: (event) => { draft.promo_code = event.target.value; } } }))
    );
    messageBox.appendChild(
      el("label", { class: "field" }, el("span", {}, "Scadenza promo"),
        el("input", { class: "input", type: "date", value: draft.promo_expiry || "",
          on: { input: (event) => { draft.promo_expiry = event.target.value; } } }))
    );
    messageBox.appendChild(el("div", { class: "hint" },
      "Segnaposti nel testo: {nome}, {cognome}, {codice} (prenotazione), " +
      "{codice_promo}, {scadenza_promo} (gg/mm/aaaa)."));
    messageBox.appendChild(el("div", { class: "hint" },
      "Segnaposti: {nome} nome, {cognome} cognome, {codice} codice ultima " +
      "prenotazione. Il messaggio viene inviato ai soli clienti iscritti alle promo."));
    left.appendChild(messageBox);

    const sendBox = box("send", "Invio manuale");
    sendBox.appendChild(
      el("div", { class: "hint" },
        this._promoRecipients() + " clienti iscritti alle promo riceveranno il messaggio.")
    );
    sendBox.appendChild(
      el("div", { class: "row tight" },
        el("button", {
          class: "btn small primary",
          disabled: this._busy || !canOffer || !this._promoRecipients(),
          on: { click: async () => {
            try {
              this._busy = true;
              this._render();
              const result = await this._call("send_promo", {
                message: draft.promo_message || "",
              });
              this._message = {
                kind: "ok",
                text: "Promo inviato a " + result.sent + " clienti (" + result.failed + " falliti).",
              };
            } catch (error) { /* shown */ }
            finally { this._busy = false; this._render(); }
          } },
        }, el("ha-icon", { icon: "mdi:send" }), "Invia promo ora"))
    );
    left.appendChild(sendBox);

    // Loyalty voucher: the thank-you message and its rules.
    const postBox = box("message_post", "Messaggio Promo");
    postBox.appendChild(el("div", { class: "hint" },
      "Messaggio di ringraziamento inviato al cliente dopo che ha usato i " +
      "servizi, con il suo codice voucher personale."));
    postBox.appendChild(
      el("label", { class: "field" },
        el("span", {}, "Testo del messaggio"),
        el("textarea", { class: "input", rows: "12",
          on: { input: (event) => { draft.promo_voucher_message = event.target.value; } },
        }, draft.promo_voucher_message || ""))
    );
    postBox.appendChild(el("div", { class: "hint" },
      "Segnaposti: {nome}, {cognome}, {codice}, {sconto} (percentuale), " +
      "{spesa_minima}, {scadenza} (gg/mm/aaaa)."));
    postBox.appendChild(
      el("div", { class: "row tight" },
        el("label", { class: "field" }, el("span", {}, "Sconto (%)"),
          el("input", { class: "input", type: "number", min: "1", max: "100", step: "1",
            value: String(draft.promo_voucher_discount ?? 10),
            on: { input: (event) => {
              const value = parseInt(event.target.value, 10);
              draft.promo_voucher_discount = Number.isFinite(value) && value >= 1 ? value : 10;
            } } })),
        el("label", { class: "field" }, el("span", {}, "Spesa minima (EUR)"),
          el("input", { class: "input", type: "number", min: "0", step: "1",
            value: String(draft.promo_voucher_min_spend ?? 100),
            on: { input: (event) => {
              const value = parseInt(event.target.value, 10);
              draft.promo_voucher_min_spend = Number.isFinite(value) && value >= 0 ? value : 0;
            } } })))
    );
    postBox.appendChild(
      el("div", { class: "row tight" },
        el("label", { class: "field" }, el("span", {}, "Spesa massima (EUR)"),
          el("input", { class: "input", type: "number", min: "0", step: "1",
            value: String(draft.promo_voucher_max_spend ?? 500),
            on: { input: (event) => {
              const value = parseInt(event.target.value, 10);
              draft.promo_voucher_max_spend = Number.isFinite(value) && value >= 0 ? value : 0;
            } } })),
        el("label", { class: "field" }, el("span", {}, "Giorni di scadenza"),
          el("input", { class: "input", type: "number", min: "1", max: "3650", step: "1",
            value: String(draft.promo_voucher_days ?? 30),
            on: { input: (event) => {
              const value = parseInt(event.target.value, 10);
              draft.promo_voucher_days = Number.isFinite(value) && value >= 1 ? value : 30;
            } } })))
    );
    postBox.appendChild(
      el("label", { class: "field" },
        el("span", {}, "Ore dopo il check-out"),
        el("input", { class: "input", type: "number", min: "0", max: "8760", step: "1",
          value: String(draft.promo_voucher_after_hours ?? 24),
          on: { input: (event) => {
            const value = parseInt(event.target.value, 10);
            draft.promo_voucher_after_hours = Number.isFinite(value) && value >= 0 ? value : 0;
          } } }))
    );
    postBox.appendChild(
      el("label", { class: "row tight" },
        el("input", { type: "checkbox", checked: draft.promo_voucher_auto === true,
          on: { change: (event) => { draft.promo_voucher_auto = event.target.checked; } } }),
        el("span", {}, "Invio automatico al check-out"))
    );
    postBox.appendChild(el("div", { class: "hint" },
      "Se attivo, al check-out si genera il codice e il messaggio parte dopo " +
      "le ore indicate. Il voucher non usato si elimina da solo dopo la scadenza."));
    postBox.appendChild(
      el("div", { class: "row tight" },
        el("button", {
          class: "btn small primary",
          disabled: this._busy || !canOffer,
          on: { click: async () => {
            try {
              this._busy = true;
              this._render();
              await this._call("update_settings", {
                promo_voucher_message: draft.promo_voucher_message || "",
                promo_voucher_days: draft.promo_voucher_days ?? 30,
                promo_voucher_discount: draft.promo_voucher_discount ?? 10,
                promo_voucher_min_spend: draft.promo_voucher_min_spend ?? 100,
                promo_voucher_max_spend: draft.promo_voucher_max_spend ?? 500,
                promo_voucher_after_hours: draft.promo_voucher_after_hours ?? 24,
                promo_voucher_auto: draft.promo_voucher_auto === true,
              });
              this._message = { kind: "ok", text: "Messaggio Promo salvato." };
              this._render();
            } catch (error) { /* shown */ }
          } },
        }, el("ha-icon", { icon: "mdi:content-save" }), "Salva"))
    );
    left.appendChild(postBox);

    // Right: scheduling + save.
    const schedBox = box("schedule", "Invio automatico");
    schedBox.appendChild(
      el("label", { class: "field" },
        el("span", {}, "Orario giornaliero (vuoto = disabilitato)"),
        el("input", { class: "input", type: "time", value: draft.promo_time || "",
          on: { input: (event) => { draft.promo_time = event.target.value; } } }))
    );
    schedBox.appendChild(
      el("label", { class: "field" },
        el("span", {}, "Pausa tra invii (secondi)"),
        el("input", { class: "input", type: "number", min: "0", step: "1",
          value: String(draft.promo_interval_sec ?? 3),
          on: { input: (event) => {
            const value = parseInt(event.target.value, 10);
            draft.promo_interval_sec = Number.isFinite(value) && value >= 0 ? value : 0;
          } } }))
    );
    schedBox.appendChild(
      el("label", { class: "field" },
        el("span", {}, "Data singola (vuota = solo orario giornaliero)"),
        el("input", { class: "input", type: "date", value: draft.promo_date || "",
          on: { input: (event) => { draft.promo_date = event.target.value; } } }))
    );
    schedBox.appendChild(
      el("div", { class: "row tight" },
        el("label", { class: "field" }, el("span", {}, "Invii massimi"),
          el("input", { class: "input", type: "number", min: "0", step: "1",
            value: String(draft.promo_max_sends ?? 0),
            on: { input: (event) => {
              const value = parseInt(event.target.value, 10);
              draft.promo_max_sends = Number.isFinite(value) && value >= 0 ? value : 0;
            } } })),
        el("label", { class: "field" }, el("span", {}, "ogni (minuti)"),
          el("input", { class: "input", type: "number", min: "1", step: "1",
            value: String(draft.promo_window_min ?? 10),
            on: { input: (event) => {
              const value = parseInt(event.target.value, 10);
              draft.promo_window_min = Number.isFinite(value) && value >= 1 ? value : 1;
            } } })))
    );
    schedBox.appendChild(el("div", { class: "hint" },
      "Invii massimi = 0: nessun limite. La data singola viene svuotata dopo l'invio."));
    schedBox.appendChild(el("div", { class: "hint" },
      "Se impostato, l'automazione giornaliera invia il promo a quell'orario " +
      "(controlla ogni 15 minuti). La pausa evita di sovraccaricare WAHA."));
    schedBox.appendChild(
      el("div", { class: "row tight" },
        el("button", {
          class: "btn small",
          disabled: this._busy || !canOffer,
          on: { click: async () => {
            try {
              this._busy = true;
              this._render();
              await this._call("update_settings", {
                promo_message: draft.promo_message || "",
                promo_time: (draft.promo_time || "").trim(),
                promo_interval_sec: draft.promo_interval_sec ?? 3,
                promo_max_sends: draft.promo_max_sends ?? 0,
                promo_window_min: draft.promo_window_min ?? 10,
                promo_date: draft.promo_date || "",
                promo_code: (draft.promo_code || "").trim(),
                promo_expiry: draft.promo_expiry || "",
              });
              this._message = { kind: "ok", text: "Impostazioni promo salvate." };
              this._render();
            } catch (error) { /* shown */ }
          } },
        }, el("ha-icon", { icon: "mdi:content-save" }), "Salva impostazioni"))
    );
    right.appendChild(schedBox);

    this._placeBlocks(left, right, "promo_order");
    columns.appendChild(left);
    columns.appendChild(right);
    wrap.appendChild(columns);

    return wrap;
  }

  // ---------------------------------------------------------- report preview

  /** The appointments passing the report filters (scope, category, treatment). */
  _reportBase(filter) {
    return this._data.appointments.filter((appointment) => {
      if (appointment.status === "cancelled") return false;
      // "Massaggi" means an operator is on the booking; "prenotazioni" is all.
      if (filter.scope === "massages" && !appointment.operator_id) return false;
      if (filter.category_id) {
        const treatment = this._lookup.treatment.get(appointment.treatment_id);
        const category = this._categoryOf(treatment);
        if (!category || category.id !== filter.category_id) return false;
      }
      if (filter.treatment_id && appointment.treatment_id !== filter.treatment_id) return false;
      return true;
    });
  }

  /** The period key of one appointment for the chosen period kind. */
  _reportPeriodKey(appointment, period) {
    const start = parseDate(appointment.start);
    if (!start) return "";
    if (period === "day") return ymd(start);
    if (period === "year") return String(start.getFullYear());
    return `${start.getFullYear()}-${pad(start.getMonth() + 1)}`;
  }

  _reportPeriodLabel(key, period) {
    if (!key) return "";
    if (period === "day") return longDay(parseLocal(key, "00:00"));
    if (period === "year") return key;
    const [year, month] = key.split("-");
    return `${MESI[Number(month) - 1]} ${year}`;
  }

  _reportControls() {
    const filter = this._reportFilter;
    const base = this._reportBase(filter);

    // Only the periods that hold bookings, so the list never offers an empty one.
    const keys = [...new Set(base.map((a) => this._reportPeriodKey(a, filter.period)))]
      .filter(Boolean)
      .sort()
      .reverse();
    if (!keys.includes(filter.periodKey)) filter.periodKey = keys[0] || "";

    // Categories and treatments that actually have bookings under the scope.
    const scopeBase = this._reportBase({ ...filter, category_id: "", treatment_id: "" });
    const catIds = new Set();
    scopeBase.forEach((a) => {
      const category = this._categoryOf(this._lookup.treatment.get(a.treatment_id));
      if (category) catIds.add(category.id);
    });
    const categories = [...this._data.categories]
      .filter((category) => catIds.has(category.id))
      .sort((a, b) => a.name.localeCompare(b.name));

    const treatIds = new Set();
    this._reportBase({ ...filter, treatment_id: "" })
      .forEach((a) => treatIds.add(a.treatment_id));
    const treatments = [...this._data.treatments]
      .filter((treatment) => treatIds.has(treatment.id))
      .sort((a, b) => a.name.localeCompare(b.name));

    const wrap = el("div", { class: "stack tight" });

    const seg = (label, options, value, onPick) =>
      el("div", { class: "field" },
        el("span", {}, label),
        el("div", { class: "role-choice" },
          options.map((opt) =>
            el("button", {
              type: "button",
              class: `role-opt${value === opt.id ? " on" : ""}`,
              on: { click: () => { onPick(opt.id); this._render(); } },
            }, opt.label))));

    wrap.appendChild(el("div", { class: "row" },
      seg("Includi", [
        { id: "massages", label: "Massaggi" },
        { id: "bookings", label: "Prenotazioni" },
      ], filter.scope, (value) => { filter.scope = value; filter.periodKey = ""; }),
      seg("Periodo", [
        { id: "day", label: "Giorno" },
        { id: "month", label: "Mese" },
        { id: "year", label: "Anno" },
      ], filter.period, (value) => { filter.period = value; filter.periodKey = ""; })));

    const periodSelect = el("select", {
      class: "input",
      on: { change: (event) => { filter.periodKey = event.target.value; this._render(); } },
    });
    if (!keys.length) {
      periodSelect.appendChild(el("option", { value: "" }, "Nessun periodo con prenotazioni"));
    } else {
      keys.forEach((key) =>
        periodSelect.appendChild(el("option", { value: key, selected: key === filter.periodKey },
          this._reportPeriodLabel(key, filter.period))));
    }
    wrap.appendChild(el("label", { class: "field" }, el("span", {}, "Scegli"), periodSelect));

    const catSelect = el("select", {
      class: "input",
      on: { change: (event) => {
        filter.category_id = event.target.value;
        filter.treatment_id = "";
        filter.periodKey = "";
        this._render();
      } },
    });
    catSelect.appendChild(el("option", { value: "" }, "Tutte le categorie"));
    categories.forEach((category) =>
      catSelect.appendChild(el("option", { value: category.id, selected: category.id === filter.category_id }, category.name)));
    wrap.appendChild(el("label", { class: "field" }, el("span", {}, "Categoria"), catSelect));

    const treatSelect = el("select", {
      class: "input",
      on: { change: (event) => { filter.treatment_id = event.target.value; filter.periodKey = ""; this._render(); } },
    });
    treatSelect.appendChild(el("option", { value: "" }, "Tutti i trattamenti"));
    treatments.forEach((treatment) =>
      treatSelect.appendChild(el("option", { value: treatment.id, selected: treatment.id === filter.treatment_id }, treatment.name)));
    wrap.appendChild(el("label", { class: "field" }, el("span", {}, "Trattamento"), treatSelect));

    wrap.appendChild(el("div", { class: "row" },
      el("button", {
        class: "btn primary",
        disabled: this._busy || !keys.length,
        on: { click: () => this._openReportPreview() },
      }, el("ha-icon", { icon: "mdi:file-pdf-box" }), "Apri anteprima")));

    wrap.appendChild(el("div", { class: "hint" },
      "L'anteprima si apre in una nuova pagina, pronta da stampare o salvare in PDF. " +
      "Negli elenchi compaiono solo i periodi che hanno prenotazioni."));

    return wrap;
  }

  _openReportPreview() {
    const filter = this._reportFilter;
    const rows = this._reportBase(filter)
      .filter((appointment) => this._reportPeriodKey(appointment, filter.period) === filter.periodKey)
      .sort((a, b) => String(a.start).localeCompare(String(b.start)));
    this._openHtmlPage(
      `Spa Booking — Report ${this._reportPeriodLabel(filter.periodKey, filter.period)}`,
      this._reportNode(rows, filter)
    );
  }

  _reportNode(rows, filter) {
    const totalMin = rows.reduce((sum, appointment) => sum + (this._durationOf(appointment) || 0), 0);
    const doc = el("div", { class: "report-page" });
    doc.appendChild(el("h1", {},
      `Spa Booking — Report ${this._reportPeriodLabel(filter.periodKey, filter.period)}`));
    const bits = [filter.scope === "massages" ? "Massaggi" : "Prenotazioni"];
    const category = filter.category_id ? this._lookup.category.get(filter.category_id) : null;
    if (category) bits.push(category.name);
    const treatment = filter.treatment_id ? this._lookup.treatment.get(filter.treatment_id) : null;
    if (treatment) bits.push(treatment.name);
    doc.appendChild(el("div", { class: "report-date" }, bits.join(" · ")));
    doc.appendChild(el("div", { class: "report-summary" },
      `${counted(rows.length, "appuntamento", "appuntamenti")} · ${minutesLabel(totalMin) || "0 min"}`));

    if (!rows.length) {
      doc.appendChild(el("div", { class: "r-note" }, "Nessun appuntamento per questo filtro."));
      return doc;
    }

    doc.appendChild(el("div", { class: "report-row report-head" },
      el("div", { class: "r-time" }, "Data / Ora"),
      el("div", { class: "r-code" }, "Codice"),
      el("div", { class: "r-client" }, "Cliente"),
      el("div", { class: "r-treat" }, "Trattamento"),
      el("div", { class: "r-op" }, "Operatrice"),
      el("div", { class: "r-cat" }, "Categoria"),
      el("div", { class: "r-dur" }, "Durata")));

    rows.forEach((appointment) => {
      const start = parseDate(appointment.start);
      const treat = this._lookup.treatment.get(appointment.treatment_id);
      const cat = this._categoryOf(treat);
      doc.appendChild(el("div", { class: "report-row" },
        el("div", { class: "r-time" },
          start ? `${shortDate(start)} ${timeOf(start)}` : "—"),
        el("div", { class: "r-code" }, appointment.code || "—"),
        el("div", { class: "r-client" }, this._clientName(appointment)),
        el("div", { class: "r-treat" }, this._treatmentName(appointment)),
        el("div", { class: "r-op" }, this._operatorName(appointment) || "—"),
        el("div", { class: "r-cat" }, cat ? cat.name : "—"),
        el("div", { class: "r-dur" }, minutesLabel(this._durationOf(appointment)))));
    });
    return doc;
  }

  /** One test button per chat of a channel, so a bad id is caught here. */
  _testRows(channel, rawChats) {
    const chats = String(rawChats || "")
      .split(/[,\n]/)
      .map((chat) => chat.trim())
      .filter(Boolean);
    if (!chats.length) return null;
    return el("div", { class: "stack tight" },
      chats.map((chat) =>
        el("div", { class: "row tight" },
          el("span", { class: "dim small" }, chat),
          el("div", { class: "spacer" }),
          el("button", {
            class: "btn small",
            disabled: this._busy,
            on: { click: () => this._testChannel(channel, chat) },
          }, el("ha-icon", { icon: "mdi:send" }), "Prova"))));
  }

  /**
   * Fill the placeholders of a message with sample values.
   *
   * A test send is only worth reading when it looks like the real thing: sent
   * raw, a template would show {nome} and {importo} and hide a broken sentence
   * behind a placeholder. ``extra`` overrides the shared samples, which is how
   * the deposit box shows the real IBAN instead of a made-up one.
   */
  _sampleMessage(text, extra = {}) {
    const samples = {
      nome: "Mario",
      cognome: "Rossi",
      cliente: "Mario Rossi",
      hotel: this._notifyDraft?.guest_header || "Il Marchese Hotel & Spa",
      codice: "ABC12",
      trattamento: "Massaggio rilassante",
      trattamenti: "Massaggio rilassante",
      durata: "60",
      data: "12/10/2026",
      ora: "15:00",
      fine: "16:00",
      persone: "2",
      totale: euro(80),
      acconto: euro(50),
      versato: euro(50),
      residuo: euro(30),
      pagamenti: `- 12/10/2026 · Bonifico · ${euro(50)}`,
      ...extra,
    };
    let out = String(text || "");
    Object.entries(samples).forEach(([key, value]) => {
      // split/join replaces every occurrence without a regex to escape.
      out = out.split(`{${key}}`).join(String(value));
    });
    return out;
  }

  async _testChannel(channel, chatId, message = "") {
    this._busy = true;
    this._render();
    try {
      const payload = { channel, chat_id: chatId };
      // The notification boxes send their own text, so the reception reads the
      // very message a guest will get; the channel tests keep the generic one.
      if (message) payload.message = message;
      const response = await this._service("send_test_message", payload);
      const result = response && response.result;
      const ok = Boolean(result && result.sent);
      this._message = {
        kind: ok ? "ok" : "error",
        text: ok
          ? `Test inviato su ${channel} a ${chatId}.`
          : `Test non riuscito su ${channel} a ${chatId}: ${(result && result.error) || "errore"}.`,
      };
    } catch (error) {
      this._message = { kind: "error", text: this._friendlyError(error, "Test non riuscito.") };
    } finally {
      this._busy = false;
      this._render();
    }
  }

  _hoursLabel(minutes) {
    const total = Number(minutes || 0);
    const hours = Math.floor(total / 60);
    const rest = total % 60;
    return hours ? `${hours}h ${String(rest).padStart(2, "0")}` : `${rest} min`;
  }

  /** One-line calendar/overlap summary of a category, for its list row. */
  _categorySummary(category) {
    const parts = [];
    const label = (days) => days.map((day) => GIORNI[day]).join(" · ");
    const morning = category.morning_days || [];
    const afternoon = category.afternoon_days || [];
    if (morning.length) parts.push(`mattina ${label(morning)}`);
    if (afternoon.length) parts.push(`pomeriggio ${label(afternoon)}`);
    if (!morning.length && !afternoon.length && category.days && category.days.length) {
      parts.push(`solo ${label(category.days)}`);
    }
    const windows = [
      [category.morning_start, category.morning_end],
      [category.afternoon_start, category.afternoon_end],
    ]
      .filter(([start, end]) => start || end)
      .map(([start, end]) => `${start || "--:--"}-${end || "--:--"}`);
    if (windows.length) parts.push(`fasce ${windows.join(" / ")}`);
    const names = (category.exclusive_with || [])
      .map((id) => this._lookup.category.get(id))
      .filter(Boolean)
      .map((other) => other.name);
    if (names.length) parts.push(`esclusiva con ${names.join(", ")}`);
    return parts.join(" · ");
  }

  _renderCategories() {
    const wrap = el("div", { class: "stack tight" });
    const categories = [...this._data.categories].sort((a, b) => a.name.localeCompare(b.name));

    if (this._editing && this._editing.kind === "category") {
      const draft = this._editing.draft;
      wrap.appendChild(
        el("label", { class: "field" }, el("span", {}, "Nome"),
          el("input", { class: "input", type: "text", value: draft.name,
            on: { input: (event) => { draft.name = event.target.value; } } }))
      );
      wrap.appendChild(
        el("label", { class: "check" },
          el("input", { type: "checkbox", checked: draft.requires_operator,
            on: { change: (event) => { draft.requires_operator = event.target.checked; } } }),
          el("span", {}, "Richiede un operatore (es. Massaggi)"))
      );
      wrap.appendChild(
        el("div", { class: "row" },
          el("label", { class: "field grow" }, el("span", {}, "Colore sfondo"),
            el("div", { class: "row" },
              el("input", {
                type: "color",
                class: "cat-color",
                value: draft.color || "#ffffff",
                // No redraw here: rebuilding the form would replace the colour
                // input and close the picker while it is dragged. Only the two
                // spots that read the choice are changed.
                on: { input: (event) => {
                  draft.color = event.target.value;
                  const label = this.shadowRoot && this.shadowRoot.querySelector(".cat-color-label");
                  if (label) label.textContent = draft.color || "nessun colore";
                  const clear = this.shadowRoot && this.shadowRoot.querySelector(".cat-color-clear");
                  if (clear) clear.disabled = !draft.color;
                } },
              }),
              el("span", { class: "dim small cat-color-label" }, draft.color ? draft.color : "nessun colore"))),
          el("button", {
            class: "btn small cat-color-clear",
            disabled: !draft.color,
            on: { click: () => { draft.color = ""; this._render(); } },
          }, "Rimuovi")
        )
      );
      wrap.appendChild(
        el("label", { class: "field" }, el("span", {}, "Pausa dopo l'appuntamento (min)"),
          el("input", {
            class: "input", type: "number", min: "0", max: "120", step: "5",
            value: draft.pause_min,
            on: { input: (event) => { draft.pause_min = Number(event.target.value) || 0; } },
          }))
      );
      const dayGrid = (label, key) =>
        el("div", { class: "field" }, el("span", {}, label),
          el("div", { class: "days-grid" },
            GIORNI.map((dayLabel, index) =>
              el("label", { class: "check" },
                el("input", {
                  type: "checkbox",
                  checked: (draft[key] || []).includes(index),
                  on: {
                    change: (event) => {
                      const days = new Set(draft[key] || []);
                      if (event.target.checked) days.add(index);
                      else days.delete(index);
                      draft[key] = [...days].sort((a, b) => a - b);
                    },
                  },
                }),
                el("span", {}, dayLabel)))));
      wrap.appendChild(dayGrid("Giorni prenotabili di mattina", "morning_days"));
      wrap.appendChild(dayGrid("Giorni prenotabili il pomeriggio", "afternoon_days"));
      wrap.appendChild(el("div", { class: "hint" }, "Lascia tutto deselezionato per accettare tutti i giorni."));
      const windowRow = (label, startKey, endKey) =>
        el("label", { class: "field" }, el("span", {}, label),
          el("div", { class: "row tight" },
            el("input", {
              class: "input", type: "time", value: draft[startKey] || "",
              on: { change: (event) => { draft[startKey] = event.target.value || ""; } },
            }),
            el("span", { class: "dim" }, "–"),
            el("input", {
              class: "input", type: "time", value: draft[endKey] || "",
              on: { change: (event) => { draft[endKey] = event.target.value || ""; } },
            })));
      wrap.appendChild(windowRow("Fascia mattutina (dalle – alle)", "morning_start", "morning_end"));
      wrap.appendChild(windowRow("Fascia pomeridiana (dalle – alle)", "afternoon_start", "afternoon_end"));
      wrap.appendChild(el("div", { class: "hint" }, "Inizio e fine dell'appuntamento devono stare dentro la stessa fascia. Lascia vuoto per nessun vincolo orario."));
      const others = this._data.categories
        .filter((category) => category.id !== this._editing.id)
        .sort((a, b) => a.name.localeCompare(b.name));
      if (others.length) {
        wrap.appendChild(
          el("div", { class: "field" }, el("span", {}, "Non sovrapporre con"),
            el("div", { class: "checks" },
              others.map((category) =>
                el("label", { class: "check" },
                  el("input", {
                    type: "checkbox",
                    checked: (draft.exclusive_with || []).includes(category.id),
                    on: {
                      change: (event) => {
                        const list = new Set(draft.exclusive_with || []);
                        if (event.target.checked) list.add(category.id);
                        else list.delete(category.id);
                        draft.exclusive_with = [...list];
                      },
                    },
                  }),
                  el("span", {}, category.name)))))
        );
        wrap.appendChild(el("div", { class: "hint" }, "L'esclusione vale in entrambe le direzioni: nessuna sovrapposizione di orario tra le due categorie."));
      }
      add(wrap, this._saveRow("add_category", "update_category", "category_id", "category"));
      return wrap;
    }

    wrap.appendChild(
      el("button", {
        class: "btn primary small",
        on: {
          click: () => {
            this._editing = { kind: "category", id: null, draft: { name: "", requires_operator: false, color: "", pause_min: 10, days: [], morning_days: [], afternoon_days: [], morning_start: "", morning_end: "", afternoon_start: "", afternoon_end: "", exclusive_with: [] } };
            this._render();
          },
        },
      }, el("ha-icon", { icon: "mdi:plus" }), "Nuova categoria")
    );

    if (!categories.length) {
      wrap.appendChild(el("div", { class: "hint" }, "Nessuna categoria definita."));
      return wrap;
    }

    categories.forEach((category) => {
      const treatments = this._data.treatments.filter((t) => t.category_id === category.id);
      wrap.appendChild(
        el("div", { class: "row item" },
          el("div", { class: "grow" },
            el("div", { class: "row" },
              category.color
                ? el("span", { class: "swatch", style: `background:${category.color}` })
                : null,
              el("span", {}, category.name)),
            el("div", { class: "dim small" },
              [
                `${treatments.length} trattamenti · ${category.requires_operator ? "richiede operatore" : "senza operatore"} · pausa ${category.pause_min ?? 10}′`,
                this._categorySummary(category),
              ].filter(Boolean).join(" · "))),
          el("button", {
            class: "icon-btn",
            title: "Modifica",
            on: {
              click: () => {
                this._editing = {
                  kind: "category",
                  id: category.id,
                  draft: {
                    name: category.name,
                    requires_operator: category.requires_operator,
                    color: category.color || "",
                    pause_min: category.pause_min ?? 10,
                    days: [...(category.days || [])],
                    morning_days: [...(category.morning_days || category.days || [])],
                    afternoon_days: [...(category.afternoon_days || category.days || [])],
                    morning_start: category.morning_start || "",
                    morning_end: category.morning_end || "",
                    afternoon_start: category.afternoon_start || "",
                    afternoon_end: category.afternoon_end || "",
                    exclusive_with: [...(category.exclusive_with || [])],
                  },
                };
                this._render();
              },
            },
          }, el("ha-icon", { icon: "mdi:pencil" })),
          el("button", {
            class: "icon-btn danger",
            title: "Elimina",
            disabled: this._busy,
            on: {
              click: async () => {
                if (!window.confirm(`Eliminare la categoria «${category.name}»?`)) return;
                const force = treatments.length
                  ? window.confirm(
                      `Ci sono ${treatments.length} trattamenti collegati. Eliminare comunque?\nI trattamenti resteranno senza categoria.`
                    )
                  : false;
                if (treatments.length && !force) return;
                try { await this._call("delete_category", { category_id: category.id, force }); } catch (e) { /* shown */ }
              },
            },
          }, el("ha-icon", { icon: "mdi:delete" })))
      );
    });

    return wrap;
  }

  // ---------------------------------------------------------------- ACCESSORI

  /**
   * Accessori tab (Configurazione): the accessories a booking can carry. Same
   * in-place editor as the Spa tiles — the pencil toggles edit mode, a row
   * opens its popup, the + adds one — but nothing is saved until Salva, so a
   * half-filled accessory is never stored. The price is only shown here: it
   * never enters a total or the deposit.
   */
  _renderAccessori() {
    const wrap = el("div", { class: "stack tight" });
    wrap.appendChild(this._accHeader());
    const items = this._accessories();
    if (!items.length && !this._accEditMode) {
      wrap.appendChild(
        el("div", { class: "empty" },
          "Nessun accessorio configurato. Usa la matita in alto a destra per aggiungerne.")
      );
    } else {
      wrap.appendChild(this._accList(items));
    }
    if (this._accDlg) wrap.appendChild(this._accDialog());
    return wrap;
  }

  /** Title row of the Accessori tab: the pencil, or the edit-mode actions. */
  _accHeader() {
    const head = el("div", { class: "spa-head" });
    head.appendChild(
      el("div", { class: "spa-head-title" },
        el("ha-icon", { icon: "mdi:gift-outline" }),
        el("span", {}, this._accEditMode ? "Modifica Accessori" : "Accessori"))
    );
    if (this._accEditMode) {
      head.appendChild(
        el("div", { class: "spa-head-actions" },
          el("button", {
            class: "btn small",
            title: "Aggiungi accessorio",
            on: { click: () => this._accOpen("__new__") },
          }, el("ha-icon", { icon: "mdi:plus" })),
          el("button", {
            class: "btn primary small",
            title: "Fine modifica",
            on: { click: () => this._accEditExit() },
          }, el("ha-icon", { icon: "mdi:check" })))
      );
      return head;
    }
    head.appendChild(
      el("button", {
        class: "icon-btn spa-menu-btn",
        title: "Modifica accessori",
        on: { click: () => { this._accEditMode = true; this._render(); } },
      }, el("ha-icon", { icon: "mdi:pencil" }))
    );
    return head;
  }

  /** Leave edit mode; every change was already saved. */
  _accEditExit() {
    this._accEditMode = false;
    this._accDlg = null;
    this._accDraft = null;
    this._accDrag = null;
    this._render();
  }

  /** The accessory rows, in configured order; draggable while editing. */
  _accList(items) {
    const list = el("div", {
      class: "stack tight acc-list" + (this._accEditMode ? " editing" : ""),
    });
    items.forEach((item) => list.appendChild(this._accRow(item)));
    if (this._accEditMode) {
      list.appendChild(
        el("button", {
          class: "btn small acc-add",
          title: "Aggiungi accessorio",
          on: { click: () => this._accOpen("__new__") },
        }, el("ha-icon", { icon: "mdi:plus" }), el("span", {}, "Aggiungi")))
      ;
      list.addEventListener("dragstart", (event) => this._accStart(event));
      list.addEventListener("dragover", (event) => this._accOver(event));
      list.addEventListener("drop", (event) => this._accDrop(event));
      list.addEventListener("dragend", () => this._accEnd(list));
    }
    return list;
  }

  /** One accessory row: icon, name, and price/description underneath. */
  _accRow(item) {
    const sub = [
      item.price === null ? null : euro(item.price),
      item.description || null,
    ].filter(Boolean).join(" · ");
    const row = el("div", {
      class: "row item trt-item",
      "data-acc": item.id,
      draggable: this._accEditMode ? "true" : "false",
      on: {
        click: () => { if (this._accEditMode) this._accOpen(item.id); },
      },
    });
    if (this._accEditMode) {
      row.appendChild(
        el("span", { class: "trt-drag", title: "Trascina" },
          el("ha-icon", { icon: "mdi:drag-vertical" })));
    }
    row.appendChild(el("ha-icon", { icon: item.icon }));
    row.appendChild(
      el("div", { class: "grow" },
        el("div", {}, item.label),
        sub ? el("div", { class: "dim small" }, sub) : null));
    if (this._accEditMode) {
      row.appendChild(el("ha-icon", { icon: "mdi:pencil" }));
    }
    return row;
  }

  /** Open the popup: "__new__" for a fresh accessory, else its id. */
  _accOpen(id) {
    this._accDlg = id;
    const current = this._accessories().find((item) => item.id === id);
    this._accDraft = id === "__new__"
      ? { id: "", label: "", icon: ACC_DEFAULT_ICON, price: null, description: "" }
      : { ...(current || this._accessory(id)) };
    if (!this._accDraft.id && id !== "__new__") this._accDraft.id = id;
    this._render();
  }

  _accClose() {
    this._accDlg = null;
    this._accDraft = null;
    this._render();
  }

  /** Popup for one accessory: name, icon, price, description, delete. */
  _accDialog() {
    const isNew = this._accDlg === "__new__";
    const draft = this._accDraft ||
      { id: "", label: "", icon: ACC_DEFAULT_ICON, price: null, description: "" };
    const overlay = el("div", {
      class: "detail-backdrop",
      on: {
        click: (event) => { if (event.target === overlay) this._accClose(); },
      },
    });
    const sheet = el("div", {
      class: "detail-sheet spa-edit-sheet",
      role: "dialog",
      "aria-modal": "true",
      "aria-label": isNew ? "Nuovo accessorio" : "Modifica accessorio",
    });
    sheet.appendChild(
      el("div", { class: "detail-head" },
        el("div", {},
          el("div", { class: "detail-title" }, isNew ? "Nuovo accessorio" : "Modifica accessorio"),
          el("div", { class: "detail-sub" },
            isNew ? "Comparirà tra gli accessori di ogni prenotazione" : (draft.label || ""))),
        el("button", {
          class: "icon-btn",
          title: "Chiudi",
          on: { click: () => this._accClose() },
        }, el("ha-icon", { icon: "mdi:close" })))
    );

    const saveBtn = el("button", {
      class: "btn primary",
      disabled: !String(draft.label || "").trim(),
      on: { click: () => this._accSave(draft, isNew) },
    }, isNew ? "Aggiungi" : "Salva");

    const nameInput = el("input", {
      type: "text",
      value: draft.label || "",
      placeholder: "Es. Accappatoio",
    });
    nameInput.addEventListener("input", () => {
      draft.label = nameInput.value;
      saveBtn.disabled = !nameInput.value.trim();
    });
    sheet.appendChild(el("div", { class: "detail-section" },
      el("h4", {}, "Nome"), nameInput));

    const iconPicker = document.createElement("ha-icon-picker");
    iconPicker.hass = this._hass;
    iconPicker.value = draft.icon || "";
    iconPicker.label = "Icona";
    iconPicker.addEventListener("value-changed", (event) => {
      draft.icon = (event.detail && event.detail.value) || "";
    });
    sheet.appendChild(el("div", { class: "detail-section" },
      el("h4", {}, "Icona"), iconPicker,
      el("div", { class: "hint" },
        "Compare accanto al nome dell'accessorio nelle prenotazioni.")));

    const priceInput = el("input", {
      type: "number",
      min: "0",
      step: "0.01",
      value: draft.price === null || draft.price === undefined ? "" : String(draft.price),
      placeholder: "—",
    });
    priceInput.addEventListener("input", () => {
      const text = priceInput.value.replace(",", ".").trim();
      draft.price = text === "" ? null : Number(text);
    });
    sheet.appendChild(el("div", { class: "detail-section" },
      el("h4", {}, "Prezzo €"), priceInput,
      el("div", { class: "hint" },
        "Solo informativo: non entra nei totali né nella caparra. Lascia vuoto se non ha un prezzo.")));

    const descInput = el("textarea", { rows: "2", placeholder: "Facoltativa" });
    descInput.value = draft.description || "";
    descInput.addEventListener("input", () => { draft.description = descInput.value; });
    sheet.appendChild(el("div", { class: "detail-section" },
      el("h4", {}, "Descrizione"), descInput,
      el("div", { class: "hint" },
        "Mostrata in questa scheda e sotto al nome nella prenotazione.")));

    const actions = el("div", { class: "detail-actions" });
    if (!isNew) {
      actions.appendChild(el("button", {
        class: "btn danger",
        on: { click: () => this._accDelete(draft.id) },
      }, el("ha-icon", { icon: "mdi:delete" }), el("span", {}, "Elimina")));
    }
    actions.appendChild(el("div", { style: "flex: 1;" }));
    actions.appendChild(el("button", {
      class: "btn",
      on: { click: () => this._accClose() },
    }, "Annulla"));
    actions.appendChild(saveBtn);
    sheet.appendChild(actions);

    overlay.appendChild(sheet);
    return overlay;
  }

  /** Save one accessory: a new one gets a fresh id, the order never changes. */
  async _accSave(draft, isNew) {
    const label = String(draft.label || "").trim();
    if (!label) return;
    const items = this._accessories();
    const id = isNew ? this._accNewId(items) : String(draft.id || "").trim();
    if (!id) return;
    const entry = {
      id,
      label,
      icon: String(draft.icon || "").trim() || ACC_DEFAULT_ICON,
      price: this._accPrice(draft.price),
      description: String(draft.description || "").trim(),
    };
    const index = items.findIndex((item) => item.id === id);
    if (index < 0) items.push(entry);
    else items[index] = entry;
    this._accDlg = null;
    this._accDraft = null;
    await this._accPersist(items);
  }

  /** A fresh accessory id, prefixed the way the integration mints its own. */
  _accNewId(items) {
    const taken = new Set((items || []).map((item) => item.id));
    const hex = "0123456789abcdef";
    let id = "";
    do {
      id = "acc_" + Array.from({ length: 12 },
        () => hex[Math.floor(Math.random() * 16)]).join("");
    } while (taken.has(id));
    return id;
  }

  /**
   * Drop one accessory. The appointments that already carry it keep it: the
   * backend remembers its last name (settings accessory_labels), so nothing
   * disappears from the bookings that had it.
   */
  async _accDelete(id) {
    const label = this._accessoryLabel(id);
    if (!window.confirm(
      `Eliminare l'accessorio «${label}»?\n\n` +
      "Restano sulle prenotazioni che lo hanno già; sparirà solo dalle nuove.")) return;
    const items = this._accessories().filter((entry) => entry.id !== id);
    this._accDlg = null;
    this._accDraft = null;
    await this._accPersist(items);
  }

  /** Save the whole accessory list right away (no draft, no Salva button). */
  async _accPersist(items) {
    try {
      await this._service("update_settings", {
        accessories: (items || []).map((item) => ({
          id: item.id,
          label: item.label || item.id,
          icon: item.icon || ACC_DEFAULT_ICON,
          price: this._accPrice(item.price),
          description: item.description || "",
        })),
      });
      await this._loadData();
    } catch (error) {
      this._message = {
        kind: "error",
        text: this._friendlyError(error, "Salvataggio non riuscito."),
      };
      this._render();
    }
  }

  /** Drag start: remember which accessory row is being moved. */
  _accStart(event) {
    const row = event.target.closest("[data-acc]");
    if (!row) return;
    this._accDrag = row.dataset.acc;
    event.dataTransfer.effectAllowed = "move";
    event.dataTransfer.setData("text/plain", row.dataset.acc);
    row.classList.add("dragging");
  }

  /** Highlight the row the dragged accessory would land on. */
  _accOver(event) {
    if (!this._accDrag) return;
    const list = event.currentTarget;
    list.querySelectorAll(".drag-over").forEach((node) => node.classList.remove("drag-over"));
    const row = event.target.closest("[data-acc]");
    if (!row || row.dataset.acc === this._accDrag) return;
    event.preventDefault();
    event.dataTransfer.dropEffect = "move";
    row.classList.add("drag-over");
  }

  /** Drop: move the dragged accessory to the target position and save. */
  _accDrop(event) {
    const drag = this._accDrag;
    if (!drag) return;
    const row = event.target.closest("[data-acc]");
    const items = this._accessories();
    const from = items.findIndex((item) => item.id === drag);
    this._accEnd(event.currentTarget);
    if (!row || row.dataset.acc === drag || from < 0) return;
    event.preventDefault();
    const [moved] = items.splice(from, 1);
    let to = items.findIndex((item) => item.id === row.dataset.acc);
    if (to < 0) items.push(moved);
    else {
      if (this._trtBelowMiddle(event, row)) to += 1;
      items.splice(to, 0, moved);
    }
    this._accPersist(items);
  }

  /** Clear drag state and highlights after a drop or when the drag ends. */
  _accEnd(list) {
    this._accDrag = null;
    if (!list || !list.querySelectorAll) return;
    list.querySelectorAll(".dragging, .drag-over").forEach((node) =>
      node.classList.remove("dragging", "drag-over"));
  }

  _renderTreatments() {
    const wrap = el("div", { class: "stack tight" });
    const treatments = [...this._data.treatments].sort((a, b) => a.name.localeCompare(b.name));

    if (this._editing && this._editing.kind === "treatment") {
      const draft = this._editing.draft;
      const categorySelect = el("select", {
        class: "input",
        on: { change: (event) => { draft.category_id = event.target.value; } },
      });
      categorySelect.appendChild(el("option", { value: "" }, "— Nessuna categoria —"));
      this._data.categories
        .slice()
        .sort((a, b) => a.name.localeCompare(b.name))
        .forEach((category) =>
          categorySelect.appendChild(
            el("option", { value: category.id, selected: draft.category_id === category.id }, category.name)
          )
        );

      wrap.appendChild(
        el("label", { class: "field" }, el("span", {}, "Nome"),
          el("input", { class: "input", type: "text", value: draft.name,
            on: { input: (event) => { draft.name = event.target.value; } } }))
      );
      wrap.appendChild(el("label", { class: "field" }, el("span", {}, "Categoria"), categorySelect));
      wrap.appendChild(
        el("div", { class: "row" },
          el("label", { class: "field" }, el("span", {}, "Durata (minuti)"),
            el("input", { class: "input", type: "number", min: "5", max: "600", step: "5", value: draft.duration_min,
              on: { input: (event) => { draft.duration_min = parseInt(event.target.value, 10) || 90; } } })),
          el("label", { class: "field" }, el("span", {}, "Prezzo €"),
            el("input", { class: "input", type: "number", min: "0", step: "0.01", value: draft.price ?? "",
              on: { input: (event) => { draft.price = event.target.value === "" ? null : Number(event.target.value); } } })))
      );

      wrap.appendChild(
        el("div", { class: "row" },
          el("label", { class: "field" }, el("span", {}, "Min. persone insieme"),
            el("input", { class: "input", type: "number", min: "0", max: "100", step: "1", value: draft.min_parallel || 0,
              on: { input: (event) => { draft.min_parallel = Math.max(0, parseInt(event.target.value, 10) || 0); } } })),
          el("label", { class: "field" }, el("span", {}, "Max. persone insieme"),
            el("input", { class: "input", type: "number", min: "0", max: "1000", step: "1", value: draft.max_parallel || 0,
              on: { input: (event) => { draft.max_parallel = Math.max(0, parseInt(event.target.value, 10) || 0); } } }))
        )
      );
      wrap.appendChild(
        el("div", { class: "hint" },
          "Quante persone possono avere questo trattamento alla stessa ora (0 = nessun limite). Non si applica agli appuntamenti con operatrice.")
      );
      wrap.appendChild(
        el("div", { class: "hint" },
          "Le operatrici abilitate si impostano dalle rispettive schede nella tab Operatori.")
      );
      wrap.appendChild(
        el("label", { class: "check" },
          el("input", { type: "checkbox", checked: draft.active,
            on: { change: (event) => { draft.active = event.target.checked; } } }),
          el("span", {}, "Trattamento attivo"))
      );
      wrap.appendChild(
        el("label", { class: "check" },
          el("input", { type: "checkbox", checked: draft.web_visible,
            on: { change: (event) => { draft.web_visible = event.target.checked; } } }),
          el("span", {}, "Visibile sul sito web"))
      );
      wrap.appendChild(
        el("div", { class: "hint" },
          "Se spento, il trattamento non compare sul sito web e gli ospiti non possono richiederlo: resta visibile solo alla reception.")
      );
      // Operator selection: pick which masseuses can perform this treatment.
      const enabledOperators = new Set(draft.operator_ids || []);
      const operatorChecks = (this._data.operators || [])
        .slice()
        .sort((a, b) => a.name.localeCompare(b.name))
        .map((operator) =>
          el("label", { class: "check" },
            el("input", {
              type: "checkbox",
              checked: enabledOperators.has(operator.id),
              on: { change: (event) => {
                if (event.target.checked) enabledOperators.add(operator.id);
                else enabledOperators.delete(operator.id);
                draft.operator_ids = [...enabledOperators];
              } },
            }),
            el("span", {}, operator.name || "—")));
      if (operatorChecks.length) {
        wrap.appendChild(el("div", { class: "cfg-box" }, el("h3", {}, "Operatrici abilitate")));
        const checksGrid = el("div", { class: "checks-grid" });
        operatorChecks.forEach((check) => checksGrid.appendChild(check));
        wrap.appendChild(checksGrid);
      }
      add(wrap, this._saveRow("add_treatment", "update_treatment", "treatment_id", "treatment"));
      return wrap;
    }

    wrap.appendChild(this._trtHeader());
    wrap.appendChild(
      el("button", {
        class: "btn primary small",
        on: {
          click: () => {
            this._editing = {
              kind: "treatment",
              id: null,
              draft: {
                name: "",
                category_id: this._data.categories.length ? this._data.categories[0].id : "",
                duration_min: 90,
                price: null,
                active: true,
                web_visible: true,
                min_parallel: 0,
                max_parallel: 0,
              },
            };
            this._render();
          },
        },
      }, el("ha-icon", { icon: "mdi:plus" }), "Nuovo trattamento")
    );

    if (!treatments.length) {
      wrap.appendChild(el("div", { class: "hint" }, "Nessun trattamento definito."));
      return wrap;
    }

    // In edit mode the categories become draggable between columns and the
    // treatments draggable up and down within each category.
    if (this._trtEditMode && this._can("config")) {
      wrap.appendChild(el("div", { class: "hint small" },
        "Trascina le categorie tra le colonne e i trattamenti su/giù nella loro categoria."));
      const columns = this._trtColumns();
      wrap.appendChild(columns);
      return wrap;
    }

    // Normal view: two columns, one block per category.
    const grid = el("div", { class: "trt-grid" });
    this._treatmentGroups().forEach((group) => {
      const block = el("div", { class: "trt-group" });
      block.appendChild(
        el("div", { class: "trt-group-head" },
          group.category.color
            ? el("span", { class: "swatch", style: `background:${group.category.color}` })
            : null,
          el("span", {}, group.category.name),
          el("span", { class: "badge" }, String(group.items.length)))
      );
      group.items.forEach((treatment) => add(block, this._treatmentRow(treatment)));
      grid.appendChild(block);
    });
    wrap.appendChild(grid);

    return wrap;
  }

  /** Title row of the Trattamenti tab: icon and name on the left, pencil (or done) on the right. */
  _trtHeader() {
    const head = el("div", { class: "spa-head" });
    head.appendChild(
      el("div", { class: "spa-head-title" },
        el("ha-icon", { icon: "mdi:spa-outline" }),
        el("span", {}, "Trattamenti"))
    );
    if (this._trtEditMode) {
      head.appendChild(
        el("div", { class: "spa-head-actions" },
          el("button", {
            class: "btn primary small",
            title: "Fine modifica",
            on: { click: () => { this._trtEditMode = false; this._render(); } },
          }, el("ha-icon", { icon: "mdi:check" })))
      );
      return head;
    }
    head.appendChild(
      el("button", {
        class: "icon-btn spa-menu-btn",
        title: "Modifica ordine categorie e trattamenti",
        on: { click: () => { this._trtEditMode = true; this._render(); } },
      }, el("ha-icon", { icon: "mdi:pencil" }))
    );
    return head;
  }

  /** Build the two-column grid of draggable category blocks (edit mode). */
  _trtColumns() {
    const columns = el("div", { class: "two-col" });
    const left = el("div", { class: "stack tight form-col", "data-col": "left" });
    const right = el("div", { class: "stack tight form-col", "data-col": "right" });

    const settings = (this._data && this._data.settings) || {};
    const order = settings.categories_order || {};
    const leftCats = order.left || [];
    const rightCats = order.right || [];

    // Build a map of category -> treatments (sorted by treatments_order).
    const orderedTrt = this._trtOrderedMap();
    const groups = new Map();
    this._data.categories.forEach((category) => {
      const trts = (orderedTrt.get(category.id) || [])
        .map((id) => this._lookup.treatment.get(id))
        .filter(Boolean);
      groups.set(category.id, { category, items: trts });
    });
    // Uncategorised treatments.
    const loose = (orderedTrt.get("") || [])
      .map((id) => this._lookup.treatment.get(id))
      .filter(Boolean);

    const makeBlock = (group) => {
      const block = el("div", { class: "trt-group", draggable: group.category.id ? "true" : "false", "data-cat": group.category.id });
      block.appendChild(
        el("div", { class: "trt-group-head" },
          el("span", { class: "trt-drag", title: "Trascina" }, el("ha-icon", { icon: "mdi:drag" })),
          group.category.color
            ? el("span", { class: "swatch", style: `background:${group.category.color}` })
            : null,
          el("span", {}, group.category.name),
          el("span", { class: "badge" }, String(group.items.length)))
      );
      group.items.forEach((treatment, index) => {
        const row = this._trtDraggableRow(treatment, group.category.id, index);
        block.appendChild(row);
      });
      return block;
    };

    leftCats.forEach((catId) => {
      const group = groups.get(catId);
      if (group && group.items.length) left.appendChild(makeBlock(group));
    });
    rightCats.forEach((catId) => {
      const group = groups.get(catId);
      if (group && group.items.length) right.appendChild(makeBlock(group));
    });
    // Categories not in either column go to the left.
    this._data.categories.forEach((category) => {
      if (!leftCats.includes(category.id) && !rightCats.includes(category.id)) {
        const group = groups.get(category.id);
        if (group && group.items.length) left.appendChild(makeBlock(group));
      }
    });
    // Uncategorised treatments.
    if (loose.length) {
      const group = { category: { name: "Senza categoria", id: "", color: "" }, items: loose };
      left.appendChild(makeBlock(group));
    }

    columns.appendChild(left);
    columns.appendChild(right);
    columns.addEventListener("dragstart", (event) => this._trtStart(event));
    columns.addEventListener("dragover", (event) => this._trtOver(event));
    columns.addEventListener("drop", (event) => this._trtDrop(event));
    columns.addEventListener("dragend", () => this._trtEnd(columns));
    return columns;
  }

  /** Map of category_id -> ordered treatment ids (from settings). */
  _trtOrderedMap() {
    const settings = (this._data && this._data.settings) || {};
    const order = (settings.treatments_order || []);
    const map = new Map();
    // Group treatments by their category in the saved order.
    this._data.treatments.forEach((treatment) => {
      const catId = treatment.category_id || "";
      if (!map.has(catId)) map.set(catId, []);
      map.get(catId).push(treatment.id);
    });
    // Reorder each category's treatments by the saved order.
    const result = new Map();
    for (const [catId, trts] of map) {
      const sorted = order.length
        ? trts.sort((a, b) => order.indexOf(a) - order.indexOf(b))
        : trts;
      result.set(catId, sorted);
    }
    return result;
  }

  /** A draggable treatment row (edit mode). */
  _trtDraggableRow(treatment, catId, index) {
    const row = el("div", { class: "row item trt-item", draggable: "true", "data-trt": treatment.id, "data-cat": catId, "data-index": String(index) });
    row.appendChild(
      el("span", { class: "trt-drag", title: "Trascina" }, el("ha-icon", { icon: "mdi:drag-vertical" })),
    );
    const category = this._categoryOf(treatment);
    row.appendChild(
      el("div", { class: "grow" },
        el("div", {}, treatment.name,
          treatment.active ? null : el("span", { class: "chip warn" }, "disattivato"),
          treatment.web_visible === false ? el("span", { class: "chip" }, "non sul sito") : null),
        el("div", { class: "dim small" },
          [
            category ? category.name : "senza categoria",
            minutesLabel(treatment.duration_min),
            treatment.price ? euro(treatment.price) : null,
          ].filter(Boolean).join(" · "))));
    return row;
  }

  /** Drag start: remember what is dragged (a category block or a treatment row). */
  _trtStart(event) {
    const target = event.target.closest("[draggable='true']");
    if (!target) return;
    const isCategory = target.classList.contains("trt-group");
    this._trtDrag = isCategory
      ? { type: "category", catId: target.dataset.cat }
      : { type: "treatment", trtId: target.dataset.trt, catId: target.dataset.cat };
    event.dataTransfer.effectAllowed = "move";
    event.dataTransfer.setData("text/plain", target.dataset.trt || target.dataset.cat || "");
    target.classList.add("dragging");
  }

  /** Drag over: highlight the category or treatment under the pointer. */
  _trtOver(event) {
    const drag = this._trtDrag;
    if (!drag) return;
    const dest = this._trtDestination(event, drag);
    event.currentTarget.querySelectorAll(".drag-over").forEach((node) => node.classList.remove("drag-over"));
    if (!dest) return;
    event.preventDefault();
    event.dataTransfer.dropEffect = "move";
    dest.node.classList.add("drag-over");
  }

  /** Find where a drag would land: the node under the pointer and whether it is in the lower half. */
  _trtDestination(event, drag) {
    if (drag.type === "category") {
      const node = event.target.closest(".trt-group[data-cat]");
      if (node && node.dataset.cat !== drag.catId) return { node, after: this._trtBelowMiddle(event, node) };
      const col = event.target.closest(".form-col");
      return col ? { node: col, after: true } : null;
    }
    const row = event.target.closest(".trt-item");
    if (row && row.dataset.cat === drag.catId && row.dataset.trt !== drag.trtId) {
      return { node: row, after: this._trtBelowMiddle(event, row) };
    }
    const block = event.target.closest(".trt-group");
    if (block && block.dataset.cat === drag.catId) return { node: block, after: true };
    return null;
  }

  _trtBelowMiddle(event, node) {
    const rect = node.getBoundingClientRect();
    return event.clientY > rect.top + rect.height / 2;
  }

  /** Drop: move a category to another column/position, or reorder a treatment inside its category. */
  _trtDrop(event) {
    const drag = this._trtDrag;
    this._trtDrag = null;
    if (!drag) return;
    const dest = this._trtDestination(event, drag);
    if (!dest) return;
    event.preventDefault();
    const columns = event.currentTarget;
    this._trtEnd(columns);

    const settings = (this._data && this._data.settings) || {};
    if (drag.type === "category") {
      this._trtDropCategory(columns, drag, dest);
    } else {
      this._trtDropTreatment(drag, dest, settings);
    }
  }

  _trtDropCategory(columns, drag, dest) {
    const settings = (this._data && this._data.settings) || {};
    const oldOrder = settings.categories_order || {};
    const colIds = (name) => [...columns.querySelectorAll(`.form-col[data-col='${name}'] > .trt-group[data-cat]`)]
      .map((node) => node.dataset.cat)
      .filter((id) => id && id !== drag.catId);
    const lists = { left: colIds("left"), right: colIds("right") };

    const destCol = dest.node.classList.contains("form-col")
      ? dest.node.dataset.col
      : dest.node.closest(".form-col").dataset.col;
    const list = lists[destCol];
    const idx = dest.node.classList.contains("form-col") ? -1 : list.indexOf(dest.node.dataset.cat);
    list.splice(idx < 0 ? list.length : idx + (dest.after ? 1 : 0), 0, drag.catId);

    // Categories with no treatments are not drawn in edit mode: keep their saved column.
    const shown = new Set([...lists.left, ...lists.right]);
    ["left", "right"].forEach((name) => {
      (oldOrder[name] || []).forEach((id) => {
        if (!shown.has(id) && id !== drag.catId) {
          lists[name].push(id);
          shown.add(id);
        }
      });
    });

    const categoriesOrder = { left: lists.left, right: lists.right };
    this._trtApply({ categories_order: categoriesOrder });
  }

  _trtDropTreatment(drag, dest, settings) {
    const block = dest.node.classList.contains("trt-group")
      ? dest.node
      : dest.node.closest(".trt-group");
    const rows = [...block.querySelectorAll(".trt-item")]
      .map((node) => node.dataset.trt)
      .filter((id) => id !== drag.trtId);
    if (dest.node.classList.contains("trt-item")) {
      const idx = rows.indexOf(dest.node.dataset.trt);
      rows.splice(idx + (dest.after ? 1 : 0), 0, drag.trtId);
    } else {
      rows.push(drag.trtId);
    }

    // Full treatment order: saved order, then any treatment it does not list yet.
    const order = (settings.treatments_order || []).filter((id) =>
      this._data.treatments.some((t) => t.id === id));
    this._data.treatments.forEach((t) => { if (!order.includes(t.id)) order.push(t.id); });

    // Replace this category's treatments in place, at the position of its first treatment.
    const inCat = new Set(rows);
    const firstPos = order.findIndex((id) => inCat.has(id));
    const remaining = order.filter((id) => !inCat.has(id));
    remaining.splice(firstPos < 0 ? remaining.length : firstPos, 0, ...rows);

    this._trtApply({ treatments_order: remaining });
  }

  /** Show the new order at once, then save it. */
  _trtApply(patch) {
    const settings = { ...((this._data && this._data.settings) || {}), ...patch };
    this._data.settings = settings;
    this._render();
    this._trtSaveOrder(settings);
  }

  /** Clear drag state and highlights after a drop or when the drag ends. */
  _trtEnd(columns) {
    this._trtDrag = null;
    columns.querySelectorAll(".dragging, .drag-over").forEach((node) =>
      node.classList.remove("dragging", "drag-over"));
  }

  /** Persist the new order to the backend. */
  async _trtSaveOrder(settings) {
    try {
      await this._call("update_settings", {
        categories_order: settings.categories_order || {},
        treatments_order: settings.treatments_order || [],
      });
    } catch (error) { /* shown */ }
  }

  /** The treatments split by category, the uncategorised ones last. */
  _treatmentGroups() {
    // Honor the dragged order: categories in column order, treatments in the
    // saved order. Anything never ordered falls back to alphabetical, so a
    // new treatment appears without breaking the saved layout.
    const settings = (this._data && this._data.settings) || {};
    const catOrder = [
      ...((settings.categories_order && settings.categories_order.left) || []),
      ...((settings.categories_order && settings.categories_order.right) || []),
    ];
    const trtOrder = settings.treatments_order || [];
    const catRank = (id) => {
      const index = catOrder.indexOf(id);
      return index < 0 ? Infinity : index;
    };
    const trtRank = (id) => {
      const index = trtOrder.indexOf(id);
      return index < 0 ? Infinity : index;
    };
    const byCategory = new Map();
    [...this._data.categories]
      .sort((a, b) => catRank(a.id) - catRank(b.id) || a.name.localeCompare(b.name))
      .forEach((category) => byCategory.set(category.id, []));
    const loose = [];

    [...this._data.treatments]
      .sort((a, b) => trtRank(a.id) - trtRank(b.id) || a.name.localeCompare(b.name))
      .forEach((treatment) => {
        if (treatment.category_id && byCategory.has(treatment.category_id)) {
          byCategory.get(treatment.category_id).push(treatment);
        } else {
          loose.push(treatment);
        }
      });

    const groups = [...byCategory.entries()]
      .filter(([, items]) => items.length)
      .map(([categoryId, items]) => ({
        category: this._lookup.category.get(categoryId) || { name: "Categoria", id: categoryId },
        items,
      }));
    if (loose.length) {
      groups.push({ category: { name: "Senza categoria", id: "" }, items: loose });
    }
    return groups;
  }

  /** One treatment in the list, with its edit and delete buttons. */
  _treatmentRow(treatment) {
    const category = this._categoryOf(treatment);
    return el("div", { class: "row item" },
      el("div", { class: "grow" },
        el("div", {}, treatment.name,
          treatment.active ? null : el("span", { class: "chip warn" }, "disattivato"),
          treatment.web_visible === false ? el("span", { class: "chip" }, "non sul sito") : null),
        el("div", { class: "dim small" },
          [
            category ? category.name : "senza categoria",
            minutesLabel(treatment.duration_min),
            treatment.price ? euro(treatment.price) : null,
            this._operatorNamesFor(treatment).length
              ? this._operatorNamesFor(treatment).join(", ")
              : "nessuna operatrice",
            treatment.min_parallel > 1 ? `min ${treatment.min_parallel} insieme` : null,
            treatment.max_parallel > 0 ? `max ${treatment.max_parallel} insieme` : null,
          ].filter(Boolean).join(" · "))),
      el("button", {
        class: "icon-btn",
        title: "Modifica",
        on: {
          click: () => {
            this._editing = {
              kind: "treatment",
              id: treatment.id,
              draft: {
                name: treatment.name,
                category_id: treatment.category_id || "",
                duration_min: treatment.duration_min,
                price: treatment.price === null || treatment.price === undefined ? null : treatment.price,
                active: treatment.active,
                web_visible: treatment.web_visible !== false,
                min_parallel: treatment.min_parallel || 0,
                max_parallel: treatment.max_parallel || 0,
                operator_ids: [...(treatment.operator_ids || [])],
              },
            };
            this._render();
          },
        },
      }, el("ha-icon", { icon: "mdi:pencil" }))
    );
  }

  /**
   * What this operator has in the book, folded under her configuration row.
   *
   * Folded because the list is long by nature and the configuration page is
   * not a report: the summary carries the counts, so the receptionist sees how
   * much there is before deciding to open it.
   */
  _operatorHistoryBlock(operator) {
    const entries = this._operatorHistory(operator);
    const counts = { effettuato: 0, "in programma": 0, annullato: 0, "in attesa": 0 };
    entries.forEach((entry) => {
      counts[entry.state] += 1;
    });
    const tally = [
      counted(counts.effettuato, "effettuato", "effettuati"),
      counted(counts["in programma"], "in programma", "in programma"),
      counted(counts.annullato, "annullato", "annullati"),
      // Only worth saying when there is one: a fourth figure on every masseuse
      // would be noise nine times out of ten.
      counts["in attesa"] ? counted(counts["in attesa"], "in attesa", "in attesa") : null,
    ]
      .filter(Boolean)
      .join(" · ");

    const box = el("details", { class: "hist-box" },
      el("summary", {},
        el("ha-icon", { icon: "mdi:history" }),
        `Storico (${entries.length})`));

    if (!entries.length) {
      box.appendChild(el("div", { class: "hint" },
        "Nessun appuntamento per questa operatrice."));
      return box;
    }

    box.appendChild(el("div", { class: "hint" }, tally));

    const list = el("div", { class: "hist-list" });
    entries.forEach(({ appointment, when, end, state }) => {
      list.appendChild(
        el("div", { class: `row hist-row ${state}` },
          el("span", { class: "hist-when" },
            `${shortDate(when)} · ${timeOf(when)}–${timeOf(end)}`),
          el("span", { class: "grow hist-client" }, this._clientName(appointment)),
          el("span", { class: "dim hist-treat" },
            `${this._treatmentName(appointment)} · ${minutesLabel(this._durationOf(appointment))}`),
          state === "annullato"
            ? el("span", { class: "chip danger" },
                appointment.cancel_reason ? `Annullato · ${appointment.cancel_reason}` : "Annullato")
            : state === "in programma"
              ? el("span", { class: "chip" }, "In programma")
              : null)
      );
    });
    box.appendChild(list);
    return box;
  }

  /** Title row of the Operatori tab: icon and name on the left, pencil (or done) on the right. */
  _opHeader() {
    const head = el("div", { class: "spa-head" });
    head.appendChild(
      el("div", { class: "spa-head-title" },
        el("ha-icon", { icon: "mdi:account-group-outline" }),
        el("span", {}, "Operatori"))
    );
    if (this._opEditMode) {
      head.appendChild(
        el("div", { class: "spa-head-actions" },
          el("button", {
            class: "btn primary small",
            title: "Fine modifica",
            on: { click: () => { this._opEditMode = false; this._render(); } },
          }, el("ha-icon", { icon: "mdi:check" })))
      );
      return head;
    }
    head.appendChild(
      el("button", {
        class: "icon-btn spa-menu-btn",
        title: "Modifica ordine operatrici",
        on: { click: () => { this._opEditMode = true; this._render(); } },
      }, el("ha-icon", { icon: "mdi:pencil" }))
    );
    return head;
  }

  /** Edit mode: each column's operators, draggable up and down. Their order becomes the priority. */
  _opEditColumns(massaggiatori, altri) {
    const wrap = el("div", { class: "stack tight" });
    wrap.appendChild(el("div", { class: "hint small" },
      "Trascina le operatrici su/giù nella loro colonna: l'ordine diventa la priorità (la prima ha priorità 0)."));
    const columns = el("div", { class: "operators-columns" });
    const block = (title, list, icon, colId) => {
      const column = el("div", { class: "operators-column", "data-col": colId });
      column.appendChild(
        el("div", { class: "column-header" },
          el("ha-icon", { icon }),
          el("span", {}, title),
          el("span", { class: "column-count" }, String(list.length)))
      );
      list.forEach((operator) => {
        column.appendChild(
          el("div", { class: "row item op-drag-item", draggable: "true", "data-op": operator.id, "data-col": colId },
            el("span", { class: "trt-drag" }, el("ha-icon", { icon: "mdi:drag-vertical" })),
            el("div", { class: "grow" },
              el("div", {}, operator.name,
                operator.active === false ? el("span", { class: "chip warn" }, "non attiva") : null),
              el("div", { class: "dim small" }, `priorità ${operator.priority || 0}`)))
        );
      });
      columns.appendChild(column);
    };
    block("Massaggiatori", massaggiatori, "mdi:hand-heart", "mass");
    block("Spa Manager", altri, "mdi:account-tie-outline", "other");
    columns.addEventListener("dragstart", (event) => this._opStart(event));
    columns.addEventListener("dragover", (event) => this._opOver(event));
    columns.addEventListener("drop", (event) => this._opDrop(event));
    columns.addEventListener("dragend", () => this._opEnd(columns));
    wrap.appendChild(columns);
    return wrap;
  }

  _opStart(event) {
    const target = event.target.closest("[draggable='true']");
    if (!target) return;
    this._opDrag = { id: target.dataset.op, col: target.dataset.col };
    event.dataTransfer.effectAllowed = "move";
    event.dataTransfer.setData("text/plain", target.dataset.op);
    target.classList.add("dragging");
  }

  _opOver(event) {
    const drag = this._opDrag;
    if (!drag) return;
    const col = event.target.closest(".operators-column");
    if (!col || col.dataset.col !== drag.col) return;
    event.preventDefault();
    event.dataTransfer.dropEffect = "move";
    event.currentTarget.querySelectorAll(".drag-over").forEach((node) => node.classList.remove("drag-over"));
    const row = event.target.closest(".op-drag-item");
    (row && row.dataset.op !== drag.id ? row : col).classList.add("drag-over");
  }

  /** Drop inside the same column: the new order sets each operator's priority. */
  _opDrop(event) {
    const drag = this._opDrag;
    this._opDrag = null;
    if (!drag) return;
    const columns = event.currentTarget;
    this._opEnd(columns);
    const col = [...columns.querySelectorAll(".operators-column")].find((node) => node.dataset.col === drag.col);
    if (!col) return;
    const ids = [...col.querySelectorAll(".op-drag-item")]
      .map((node) => node.dataset.op)
      .filter((id) => id !== drag.id);
    let idx = ids.length;
    const row = event.target.closest(".op-drag-item");
    if (row && row.dataset.col === drag.col && row.dataset.op !== drag.id) {
      idx = ids.indexOf(row.dataset.op) + (this._trtBelowMiddle(event, row) ? 1 : 0);
    }
    ids.splice(idx, 0, drag.id);

    const changes = [];
    ids.forEach((id, position) => {
      const operator = this._data.operators.find((o) => o.id === id);
      if (operator && (Number(operator.priority) || 0) !== position) {
        changes.push({ id, priority: position });
        operator.priority = position;
      }
    });
    this._render();
    if (changes.length) this._opSaveOrder(changes);
  }

  async _opSaveOrder(changes) {
    for (const change of changes) {
      try {
        await this._call("update_operator", { operator_id: change.id, priority: change.priority });
      } catch (error) {
        return; /* shown */
      }
    }
  }

  _opEnd(columns) {
    this._opDrag = null;
    columns.querySelectorAll(".dragging, .drag-over").forEach((node) =>
      node.classList.remove("dragging", "drag-over"));
  }

  _renderOperators() {
    const wrap = el("div", { class: "stack tight" });
    // Group operators by role for the two-column display: massaggiatori on the
    // left, spa_managers (and any other non-massaggiatore role) on the right.
    // Both lists read in priority order (lower first), then by name.
    const byPriority = (a, b) =>
      (Number(a.priority) || 0) - (Number(b.priority) || 0) || a.name.localeCompare(b.name);
    const massaggiatori = this._data.operators
      .filter((o) => o.role === "massaggiatore")
      .sort(byPriority);
    const altri = this._data.operators
      .filter((o) => o.role !== "massaggiatore")
      .sort(byPriority);

    if (this._editing && this._editing.kind === "operator") {
      const draft = this._editing.draft;
      // The operator card is editable exactly like the booking forms: the
      // pencil turns its boxes into draggable blocks, so the reception can put
      // the fields, the channels and the treatments where she wants them. Only
      // the order changes; nothing is added or removed.
      if (this._operatorFormMode) wrap.classList.add("form-edit");
      const head = el("div", { class: "row" },
        el("h3", {}, this._operatorFormMode
          ? "Modifica scheda operatrice"
          : (draft.name ? `Scheda operatrice: ${draft.name}` : "Nuova operatrice")),
        el("div", { class: "spacer" }));
      if (this._operatorFormMode) {
        head.appendChild(el("button", {
          class: "btn primary small",
          title: "Fine modifica",
          on: { click: () => { this._operatorFormMode = false; this._operatorDrag = null; this._render(); } },
        }, el("ha-icon", { icon: "mdi:check" })));
      } else {
        head.appendChild(el("button", {
          class: "icon-btn",
          title: "Modifica scheda",
          on: { click: () => { this._operatorFormMode = true; this._render(); } },
        }, el("ha-icon", { icon: "mdi:pencil" })));
      }
      wrap.appendChild(head);
      if (this._operatorFormMode) {
        wrap.appendChild(el("div", { class: "hint" },
          "Trascina i box con la maniglia per spostarli fra le due colonne e " +
          "verso l'alto o il basso. L'ordine vale per tutte le schede."));
      }

      // One box per draggable block, filled in the default order and then
      // placed by the saved layout (settings.operator_form_order).
      const nomeBox = el("div", { class: "stack tight" });
      const contattiBox = el("div", { class: "stack tight" });
      const prioritaBox = el("div", { class: "stack tight" });
      const notificheBox = el("div", { class: "stack tight" });
      const trattamentiBox = el("div", { class: "stack tight" });
      let messaggiBox = null;

      nomeBox.appendChild(
        el("label", { class: "field" }, el("span", {}, "Nome"),
          el("input", { class: "input", type: "text", value: draft.name,
            on: { input: (event) => { draft.name = event.target.value; } } }))
      );

      // A pair of buttons rather than a dropdown: there are exactly two roles,
      // the choice is made once and then left alone, and a select would hide the
      // alternative behind an extra tap on a phone.
      nomeBox.appendChild(
        el("div", { class: "field" },
          el("span", {}, "Ruolo"),
          el("div", { class: "role-choice" },
            OPERATOR_ROLES.map((role) =>
              el("button", {
                type: "button",
                class: `role-opt${draft.role === role.id ? " on" : ""}`,
                title: role.label,
                on: {
                  click: () => { draft.role = role.id; this._render(); },
                },
              },
                el("ha-icon", { icon: role.icon }),
                role.label))))
      );
      nomeBox.appendChild(
        el("div", { class: "hint" },
          "Il ruolo serve solo a distinguerle a colpo d'occhio: entrambe fanno " +
          "massaggi, ricevono le proposte e vengono avvisate.")
      );

      contattiBox.appendChild(
        el("div", { class: "field" }, el("span", {}, "Telefono"),
          el("div", { class: "row tight" },
            el("input", { class: "input grow", type: "tel", value: draft.phone,
              on: { input: (event) => { draft.phone = event.target.value; } } }),
            el("button", {
              class: "btn small tel",
              title: "Chiama",
              on: {
                click: () => {
                  const value = String(draft.phone || "").trim();
                  if (!value) {
                    this._message = { kind: "error", text: "Inserisci un telefono prima di chiamare." };
                    this._render();
                    return;
                  }
                  window.location.href = telHref(value);
                },
              },
            }, el("ha-icon", { icon: "mdi:phone" }),
               el("span", { class: "btn-label" }, "Chiama"))))
      );

      const whatsappPreview = this._whatsappIdOf({
        phone: draft.phone,
        whatsapp_chat_id: draft.whatsapp_chat_id,
      });
      contattiBox.appendChild(
        el("div", { class: "field" },
          el("span", {}, "Chat WhatsApp"),
          el("div", { class: "row tight" },
            el("input", { class: "input grow", type: "text", value: draft.whatsapp_chat_id,
              placeholder: whatsappPreview || "39…@c.us",
              on: { input: (event) => { draft.whatsapp_chat_id = event.target.value; } } }),
            el("button", {
              class: "btn small wa",
              title: "WhatsApp",
              on: {
                click: () => {
                  const raw = String(draft.whatsapp_chat_id || "").trim();
                  const phone = String(draft.phone || "").trim();
                  const target = raw && !raw.includes("@g.us") ? raw : phone;
                  const url = target ? waLink(target) : null;
                  if (!url) {
                    this._message = { kind: "error", text: "Inserisci un numero WhatsApp o un telefono." };
                    this._render();
                    return;
                  }
                  window.open(url, "_blank", "noopener");
                },
              },
            }, el("ha-icon", { icon: "mdi:whatsapp" }),
               el("span", { class: "btn-label" }, "WhatsApp"))))
      );
      contattiBox.appendChild(
        el("div", { class: "hint" },
          whatsappPreview
            ? `Le notifiche andranno a ${whatsappPreview}${draft.whatsapp_chat_id ? " (chat esplicita)." : " (dal telefono)."}`
            : "Indica il telefono, o un chat id di gruppo, per ricevere su WhatsApp.")
      );

      contattiBox.appendChild(
        el("label", { class: "field" }, el("span", {}, "Chat Telegram"),
          el("input", { class: "input", type: "text", value: draft.telegram_chat_id,
            placeholder: "933728087",
            on: { input: (event) => { draft.telegram_chat_id = event.target.value; } } }))
      );

      // Test buttons: send a real message on this operator's own channels, so
      // a wrong number or chat id is caught while her card is open. The ids
      // are read at click time, not at draw time, because the contact fields
      // do not redraw on every keystroke.
      contattiBox.appendChild(
        el("div", { class: "row tight" },
          el("button", {
            class: "btn small",
            disabled: this._busy,
            on: {
              click: () => {
                const id = this._whatsappIdOf({
                  phone: draft.phone,
                  whatsapp_chat_id: draft.whatsapp_chat_id,
                });
                if (!id) {
                  this._message = { kind: "error", text: "Inserisci un telefono o una chat WhatsApp prima di provare." };
                  this._render();
                  return;
                }
                this._testChannel("whatsapp", id);
              },
            },
          }, el("ha-icon", { icon: "mdi:whatsapp" }), "Prova WhatsApp"),
          el("button", {
            class: "btn small",
            disabled: this._busy,
            on: {
              click: () => {
                const id = String(draft.telegram_chat_id || "").trim();
                if (!id) {
                  this._message = { kind: "error", text: "Inserisci un chat id Telegram prima di provare." };
                  this._render();
                  return;
                }
                this._testChannel("telegram", id);
              },
            },
          }, el("ha-icon", { icon: "mdi:send" }), "Prova Telegram"))
      );

      trattamentiBox.appendChild(el("h3", {}, "Tipi di massaggi che sa fare"));
      // Offer every treatment that needs an operator, not only the ones
      // already ticked: filtering on the current selection made the list come
      // out empty exactly when there was something left to choose.
      const assignable = this._data.treatments.filter(
        (treatment) => (this._categoryOf(treatment) || {}).requires_operator
      );
      if (!assignable.length) {
        trattamentiBox.appendChild(el("div", { class: "hint" },
          "Non ci sono trattamenti che richiedono un operatore: creane nella scheda Trattamenti."));
      } else {
        trattamentiBox.appendChild(el("div", { class: "checks" },
          assignable
            .slice()
            .sort((a, b) => a.name.localeCompare(b.name))
            .map((treatment) => {
              const id = treatment.id;
              return el("label", { class: "check" },
                el("input", {
                  type: "checkbox",
                  checked: (draft.treatment_ids || []).includes(id),
                  on: {
                    change: (event) => {
                      const current = new Set(draft.treatment_ids || []);
                      if (event.target.checked) current.add(id);
                      else current.delete(id);
                      draft.treatment_ids = [...current];
                    },
                  },
                }),
                el("span", {}, `${treatment.name} · ${minutesLabel(treatment.duration_min)}`));
            })
        ));
        if (!(draft.treatment_ids || []).length) {
          trattamentiBox.appendChild(el("div", { class: "hint" },
            "Nessun trattamento spuntato: non le verranno proposti massaggi nel modulo Nuovo e non comparirà nel report mensile."));
        }
      }
      trattamentiBox.appendChild(el("div", { class: "hint" },
        "Questi sono i trattamenti che il modulo «Nuovo» proporrà per questa operatrice."));

      prioritaBox.appendChild(
        el("div", { class: "row" },
          el("label", { class: "field" },
            el("span", {}, "Priorità (più basso = prima)"),
            el("input", { class: "input", type: "number", min: "0", max: "999", step: "1",
              value: draft.priority ?? 0,
              on: { input: (event) => { draft.priority = Number(event.target.value) || 0; } } })),
          el("label", { class: "check" },
            el("input", { type: "checkbox", checked: draft.active !== false,
              on: { change: (event) => { draft.active = event.target.checked; } } }),
            el("span", {}, "Attiva (riceve le proposte)"))
        )
      );

      notificheBox.appendChild(el("h3", {}, "Canali di notifica"));
      notificheBox.appendChild(
        el("label", { class: "check" },
          el("input", { type: "checkbox", checked: draft.notify_whatsapp,
            on: { change: (event) => { draft.notify_whatsapp = event.target.checked; } } }),
          el("span", {}, "Avvisa su WhatsApp"))
      );
      notificheBox.appendChild(
        el("label", { class: "check" },
          el("input", { type: "checkbox", checked: draft.notify_telegram,
            on: { change: (event) => { draft.notify_telegram = event.target.checked; } } }),
          el("span", {}, "Avvisa su Telegram"))
      );
      notificheBox.appendChild(
        el("label", { class: "field" },
          el("span", {}, "Servizio notifiche (es. notify.mobile_app_stefano)"),
          el("input", { class: "input", type: "text", value: draft.notify_service,
            placeholder: "notify.…",
            on: { input: (event) => { draft.notify_service = event.target.value; } } }))
      );
      notificheBox.appendChild(el("div", { class: "hint" },
        "Lascia vuoto se l'operatrice non riceve notifiche via Home Assistant."));
      notificheBox.appendChild(
        el("label", { class: "check" },
          el("input", { type: "checkbox", checked: draft.notify_on_create,
            on: { change: (event) => { draft.notify_on_create = event.target.checked; } } }),
          el("span", {}, "Avvisa su ogni nuovo appuntamento"))
      );

      // Existing operators only: a new one has no id to send to yet.
      if (this._editing.id) {
        const messageButtons = [
          ["guide", "Guida", "mdi:help-circle-outline"],
          ["today", "Oggi", "mdi:calendar-today"],
          ["tomorrow", "Domani", "mdi:calendar-arrow-right"],
          ["week", "Settimana", "mdi:calendar-week"],
          ["month", "Mese", "mdi:calendar-month"],
          ["upcoming", "Futuri", "mdi:calendar-clock"],
          ["pending", "Da confermare", "mdi:calendar-question"],
        ];
        messaggiBox = el("div", { class: "detail-section" },
          el("h3", {}, "Messaggi all'operatrice"),
          el("div", { class: "row tight" },
            messageButtons.map(([kind, label, icon]) =>
              el("button", {
                class: "btn small",
                disabled: this._busy,
                title: `Invia: ${label}`,
                on: {
                  click: () =>
                    this._call("send_operator_message", {
                      operator_id: this._editing.id,
                      kind,
                    }),
                },
              }, el("ha-icon", { icon }),
                 el("span", { class: "btn-label" }, label)))),
          el("div", { class: "hint" },
            "Invia un messaggio WhatsApp (e Telegram, se configurato). " +
            "Se l'operatrice scrive AIUTO, OGGI, DOMANI, SETTIMANA, MESE, " +
            "FUTURI o CONFERMARE riceve il messaggio corrispondente."));
      }

      const blocks = {
        nome: nomeBox,
        contatti: contattiBox,
        priorita: prioritaBox,
        notifiche: notificheBox,
        trattamenti: trattamentiBox,
        messaggi: messaggiBox,
      };
      const cols = el("div", { class: "two-col" });
      const left = el("div", { class: "stack tight form-col", "data-col": "left" });
      const right = el("div", { class: "stack tight form-col", "data-col": "right" });
      this._operatorFormOrder("left").forEach((id) => {
        if (blocks[id]) add(left, this._operatorFormSection(id, blocks[id]));
      });
      this._operatorFormOrder("right").forEach((id) => {
        if (blocks[id]) add(right, this._operatorFormSection(id, blocks[id]));
      });
      cols.appendChild(left);
      cols.appendChild(right);
      wrap.appendChild(cols);

      add(wrap, this._saveRow("add_operator", "update_operator", "operator_id", "operatrice"));
      return wrap;
    }

    wrap.appendChild(this._opHeader());
    if (this._opEditMode && this._can("config")) {
      wrap.appendChild(this._opEditColumns(massaggiatori, altri));
      return wrap;
    }

    wrap.appendChild(
      el("button", {
        class: "btn primary small",
        on: {
          click: () => {
            this._editing = {
              kind: "operator",
              id: null,
              draft: {
                name: "",
                role: OPERATOR_ROLES[0].id,
                phone: "",
                whatsapp_chat_id: "",
                telegram_chat_id: "",
                treatment_ids: [],
                notify_whatsapp: true,
                notify_telegram: true,
                notify_service: "",
                notify_on_create: true,
                priority: 0,
                active: true,
              },
            };
            this._render();
          },
        },
      }, el("ha-icon", { icon: "mdi:plus" }), "Nuova operatrice")
    );

    const allOperators = [...massaggiatori, ...altri];
    if (!allOperators.length) {
      wrap.appendChild(el("div", { class: "hint" }, "Nessun operatore configurato."));
      return wrap;
    }

    // Two-column layout: massaggiatori on the left, others on the right
    const columns = el("div", { class: "operators-columns" });
    wrap.appendChild(columns);

    const renderColumn = (title, operators, icon) => {
      if (!operators.length) return;
      const column = el("div", { class: "operators-column" });
      column.appendChild(
        el("div", { class: "column-header" },
          el("ha-icon", { icon }),
          el("span", {}, title),
          el("span", { class: "column-count" }, operators.length)
        )
      );
      operators.forEach((operator) => {
        const upcoming = this._data.appointments.filter((appointment) => {
          const start = parseDate(appointment.start);
          return (
            appointment.operator_id === operator.id &&
            appointment.status !== "cancelled" &&
            start && start > new Date()
          );
        }).length;
        const massages = this._treatmentsOfOperator(operator);
        const channels = [];
        if (operator.notify_whatsapp) channels.push("WhatsApp");
        if (operator.notify_telegram) channels.push("Telegram");
        const role = roleOf(operator);
        const opCard = el("div", { class: "op-card" });
        opCard.appendChild(
          el("div", { class: "row item op-head" },
            el("div", { class: "op-role" },
              el("span", { class: `role-badge ${operator.role === "spa_manager" ? "mgr" : "mass"}` },
                el("ha-icon", { icon: role.icon }),
                role.label),
              el("div", { class: "op-priority" },
                el("span", { class: "dim small" }, `Priorità ${operator.priority || 0}`),
                el("button", {
                  class: `btn small${operator.active === false ? "" : " primary"}`,
                  title: operator.active === false ? "Attiva" : "Disattiva",
                  disabled: this._busy,
                  on: {
                    click: async () => {
                      try {
                        await this._call("update_operator", {
                          operator_id: operator.id,
                          active: operator.active === false,
                        });
                      } catch (error) { /* shown */ }
                    },
                  },
                }, el("ha-icon", { icon: operator.active === false ? "mdi:toggle-switch-off-outline" : "mdi:toggle-switch" })))),
            el("div", { class: "grow" },
              el("div", {}, operator.name),
              el("div", { class: "dim small" },
                [
                  operator.active === false ? "NON ATTIVA" : "attiva",
                  `priorità ${operator.priority || 0}`,
                  operator.phone || "senza telefono",
                  massages.length
                    ? `${massages.length} massaggi: ${massages.map((t) => t.name).join(", ")}`
                    : "nessun massaggio assegnato",
                  channels.length ? channels.join(" + ") : "nessuna notifica",
                  `${upcoming} futuri`,
                ].join(" · "))),
            el("div", { class: "op-actions" },
              el("button", {
                class: "btn small",
                title: "Modifica",
                on: {
                  click: () => {
                    this._editing = {
                      kind: "operator",
                      id: operator.id,
                      draft: {
                        name: operator.name,
                        role: roleOf(operator).id,
                        phone: operator.phone || "",
                        whatsapp_chat_id: operator.whatsapp_chat_id || "",
                        telegram_chat_id: operator.telegram_chat_id || "",
                        treatment_ids: [...(operator.treatment_ids || [])],
                        notify_whatsapp: operator.notify_whatsapp !== false,
                        notify_telegram: operator.notify_telegram !== false,
                        notify_service: operator.notify_service || "",
                        notify_on_create: operator.notify_on_create !== false,
                        priority: operator.priority ?? 0,
                        active: operator.active !== false,
                      },
                    };
                    this._render();
                  },
                },
              }, el("ha-icon", { icon: "mdi:pencil" })),
              el("button", {
                class: "btn small danger",
                title: "Elimina",
                disabled: this._busy,
                on: {
                  click: async () => {
                    if (!window.confirm(`Eliminare l'operatore «${operator.name}»?`)) return;
                    let force = false;
                    if (upcoming) {
                      if (!window.confirm(`Ci sono ${upcoming} appuntamenti futuri. Eliminare comunque?`)) return;
                      force = true;
                    }
                    try { await this._call("delete_operator", { operator_id: operator.id, force }); } catch (e) { /* shown */ }
                  },
                },
              }, el("ha-icon", { icon: "mdi:delete" })),
              operator.phone
                ? el("a", { class: "btn small tel", href: telHref(operator.phone), title: operator.phone },
                    el("ha-icon", { icon: "mdi:phone" }))
                : el("span", { class: "op-slot" }),
              operator.phone
                ? el("a", { class: "btn small wa", href: waLink(operator.phone), target: "_blank", rel: "noopener", title: "WhatsApp" },
                    el("ha-icon", { icon: "mdi:whatsapp" }))
                : el("span", { class: "op-slot" })))
      );
      add(opCard, this._operatorHistoryBlock(operator));
      column.appendChild(opCard);
    });
      columns.appendChild(column);
    };

    renderColumn("Massaggiatori", massaggiatori, "mdi:hand-heart");
    renderColumn("Spa Manager", altri, "mdi:account-tie-outline");

    return wrap;
  }

  /**
   * People sharing this appointment's slot. Shown only when the treatment
   * carries a capacity: a massage is one to one, so a number there would be
   * meaningless. Changing it resizes the whole group in one call, which is why
   * the stepper is disabled while the call is in flight.
   */
  _groupStepper() {
    const anchor = this._lookup.appointment.get(this._editing.id);
    if (!anchor) return null;
    // Only a confirmed anchor can be resized: a waiting one is refused by the
    // backend, so offering the buttons would only produce an error.
    if (anchor.status !== "confirmed") return null;
    const treatment = this._lookup.treatment.get(anchor.treatment_id);
    if (!treatment) return null;
    const max = Number(treatment.max_parallel) || 0;
    const min = Math.max(1, Number(treatment.min_parallel) || 0);
    if (!max && !treatment.min_parallel) return null;

    const current = this._groupSize(anchor);
    const lower = Math.max(1, min);
    const upper = max > 0 ? Math.max(lower, max) : Math.max(lower, current + 50);

    const box = el("div", { class: "row" },
      el("label", { class: "field" },
        el("span", {}, "Persone nella fascia"),
        el("div", { class: "row tight stepper" },
          el("button", {
            class: "icon-btn",
            title: "Meno persone",
            disabled: this._busy || current <= lower,
            on: { click: () => this._resizeGroup(current - 1) },
          }, el("ha-icon", { icon: "mdi:minus" })),
          el("span", { class: "stepper-num" }, String(current)),
          el("button", {
            class: "icon-btn",
            title: "Più persone",
            disabled: this._busy || current >= upper,
            on: { click: () => this._resizeGroup(current + 1) },
          }, el("ha-icon", { icon: "mdi:plus" })))),
      el("div", { class: "spacer" })
    );
    box.appendChild(
      el("div", { class: "hint" },
        `${treatment.name}: da ${min} a ${max > 0 ? max : "∞"} persone nella stessa fascia. ` +
        "Ogni persona è un appuntamento proprio; quello che stai modificando resta il riferimento.")
    );
    return box;
  }

  /**
   * The people who share this slot under the same client card, this one
   * included: same client, same treatment, same start. That is exactly the
   * group the people stepper resizes, so what the row shows and what the
   * button acts on can never disagree.
   */
  _groupOf(appointment) {
    // Same treatment, client, slot AND operator: two party members with
    // different masseuses are two separate rows, not one shared party.
    // A waiting member counts too: she holds the same slot and the backend
    // already counts her as a person of the group, so leaving her out here
    // would make the count the stepper shows disagree with the one it acts on.
    return this._data.appointments.filter(
      (other) =>
        (other.status === "confirmed" || other.status === "pending") &&
        other.treatment_id === appointment.treatment_id &&
        other.client_id === appointment.client_id &&
        other.start === appointment.start &&
        (other.operator_id || null) === (appointment.operator_id || null)
    );
  }

  _relatedOf(appointment) {
    if (!appointment) return [appointment];
    const candidates = (this._data.appointments || []).filter((a) => a.status !== "cancelled");

    const targetDate = String(appointment.start || "").slice(0, 10);
    // Vista Raggruppata: mostra **tutti gli appuntamenti attivi** dello stesso
    // cliente nella stessa giornata (massaggi e spa, mattina e pomeriggio).
    // Questo include gli appuntamenti legati al batch e quelli legacy.
    const perClientDay = candidates.filter((a) =>
      a.client_id === appointment.client_id &&
      String(a.start || "").slice(0, 10) === targetDate
    );
    if (perClientDay.length > 1) {
      return perClientDay.sort((a, b) => parseDate(a.start) - parseDate(b.start));
    }
    // Fallback: batch_id se esiste ed ha almeno un collegamento
    if (appointment.batch_id) {
      const byBatch = candidates.filter((a) => a.batch_id === appointment.batch_id);
      if (byBatch.length > 1) {
        return byBatch.sort((a, b) => parseDate(a.start) - parseDate(b.start));
      }
    }
    return [appointment];
  }

  _relatedTotals(appointment) {
    const related = this._relatedOf(appointment);
    const people = related.filter((a) => a.status === "confirmed" || a.status === "pending");
    const source = people.length ? people : [appointment];
    let price = 0;
    let extras = 0;
    let collected = 0;
    source.forEach((member) => {
      const line = this._lineBreakdown(member);
      price += line.price;
      extras += line.extras;
      collected += line.collected;
    });
    const total = Math.round((price + extras) * 100) / 100;
    return {
      total,
      collected: Math.round(collected * 100) / 100,
      due: Math.max(0, Math.round((total - collected) * 100) / 100),
      persons: source.length,
      members: related,
    };
  }

  _singleTotals(appointment) {
    const line = this._lineBreakdown(appointment);
    const total = Math.round((line.price + line.extras) * 100) / 100;
    return {
      total,
      collected: Math.round(line.collected * 100) / 100,
      due: Math.max(0, Math.round((total - line.collected) * 100) / 100),
      persons: 1,
    };
  }

  /**
   * One distinct colour for the group of this appointment, or "" for a lone
   * booking. Colours are handed out in the order the group is first rendered
   * of the day, so every group of the agenda reads as its own and two groups
   * never share a bar.
   */
  _groupColor(appointment) {
    if (this._groupOf(appointment).length < 2) return "";
    const key = [
      appointment.client_id,
      appointment.treatment_id,
      appointment.start,
      appointment.operator_id || "",
    ].join("|");
    if (!this._groupColorMap.has(key)) {
      this._groupColorMap.set(
        key,
        GROUP_COLORS[this._groupColorMap.size % GROUP_COLORS.length]
      );
    }
    return this._groupColorMap.get(key);
  }

  /** How many appointments share this one's treatment, client and slot. */
  _groupSize(appointment) {
    return this._groupOf(appointment).length;
  }

  /** Open or close the single rows of a party under its one row. */
  _toggleParty(appointment) {
    if (!this._expandedGroups) this._expandedGroups = new Set();
    const key = [
      appointment.treatment_id,
      appointment.client_id,
      appointment.start,
      appointment.operator_id || "",
    ].join("|");
    if (this._expandedGroups.has(key)) this._expandedGroups.delete(key);
    else this._expandedGroups.add(key);
    this._render();
  }

  async _resizeGroup(persons) {
    try {
      const response = await this._call("resize_appointment_group", {
        appointment_id: this._editing.id,
        persons,
      });
      // The backend answers "done" even when the slot already holds that many
      // people. Saying "updated" then would read as a change that never
      // happened, so the no-op gets its own sentence.
      if (response && !response.created && !response.cancelled) {
        this._message = {
          kind: "ok",
          text: `Nessuna modifica: la fascia ha già ${response.persons} persone.`,
        };
      }
      this._editing = null;
      this._render();
    } catch (error) {
      /* shown */
    }
  }

  /** Edit an existing appointment: pre-filled form with all fields. */
  _renderEditAppointment() {
    const { draft } = this._editing;
    const treatments = this._activeTreatments();
    const treatmentSelect = el("select", {
      class: "input",
      on: { change: (event) => { draft.treatment_id = event.target.value; this._render(); } },
    });
    treatmentSelect.appendChild(el("option", { value: "" }, "— Scegli il trattamento —"));
    const categories = [...this._data.categories].sort((a, b) => a.name.localeCompare(b.name));
    const grouped = new Map();
    treatments.forEach((treatment) => {
      if (treatment.category_id && this._lookup.category.has(treatment.category_id)) {
        if (!grouped.has(treatment.category_id)) grouped.set(treatment.category_id, []);
        grouped.get(treatment.category_id).push(treatment);
      } else {
        grouped.set("__none__", [...(grouped.get("__none__") || []), treatment]);
      }
    });
    [...categories, { id: "__none__", name: "Senza categoria" }].forEach((category) => {
      const list = grouped.get(category.id) || [];
      if (!list.length) return;
      const optgroup = el("optgroup", { label: category.name });
      list.forEach((treatment) =>
        optgroup.appendChild(el("option", { value: treatment.id, selected: draft.treatment_id === treatment.id }, treatment.name))
      );
      treatmentSelect.appendChild(optgroup);
    });

    const clientSelect = el("select", {
      class: "input",
      on: { change: (event) => { draft.client_id = event.target.value || null; } },
    });
    clientSelect.appendChild(el("option", { value: "" }, "— Stesso cliente —"));
    [...this._data.clients].sort((a, b) => (a.last_name || "").localeCompare(b.last_name || "")).forEach((client) => {
      const label = [client.first_name, client.last_name].filter(Boolean).join(" ") || client.phone || "senza nome";
      clientSelect.appendChild(el("option", { value: client.id, selected: draft.client_id === client.id }, label));
    });

    const operatorSelect = el("select", {
      class: "input",
      on: { change: (event) => { draft.operator_id = event.target.value || ""; } },
    });
    operatorSelect.appendChild(el("option", { value: "" }, "— Nessun operatore —"));
    this._data.operators.forEach((operator) =>
      operatorSelect.appendChild(el("option", { value: operator.id, selected: draft.operator_id === operator.id }, operator.name))
    );

    const wrap = el("div", {
      class: "stack form-compact" + (this._editFormMode ? " form-edit" : ""),
    });
    const head = el("div", { class: "row" },
      el("h3", {}, this._editFormMode ? "Modifica scheda" : "Modifica appuntamento"),
      el("div", { class: "spacer" }));
    if (this._editFormMode) {
      head.appendChild(el("button", {
        class: "btn primary small",
        title: "Fine modifica",
        on: { click: () => { this._editFormMode = false; this._editDrag = null; this._render(); } },
      }, el("ha-icon", { icon: "mdi:check" })));
    } else {
      head.appendChild(el("button", {
        class: "icon-btn",
        title: "Modifica scheda",
        on: { click: () => { this._editFormMode = true; this._render(); } },
      }, el("ha-icon", { icon: "mdi:pencil" })));
    }
    head.appendChild(el("button", {
      class: "icon-btn",
      title: "Chiudi",
      on: { click: () => { this._editing = null; this._editFormMode = false; this._render(); } },
    }, el("ha-icon", { icon: "mdi:close" })));
    wrap.appendChild(head);
    if (this._editFormMode) {
      wrap.appendChild(el("div", { class: "hint" },
        "Trascina i box con la maniglia per spostarli fra le due colonne e " +
        "verso l'alto o il basso. L'ordine resta salvato."));
    }
    // Two columns driven by the saved layout, like the Nuovo form: in edit
    // mode the blocks cross columns and move up and down, then keep the
    // order. The old pagamento block is gone: Totali and Incassi replace it.
    const columns = el("div", { class: "two-col" });
    const left = el("div", { class: "stack tight form-col", "data-col": "left" });
    const right = el("div", { class: "stack tight form-col", "data-col": "right" });
    const current = this._data.appointments.find(
      (item) => item.id === this._editing.id
    );
    const editTotals = this._editTotaliBlock(draft);
    const blocks = {
      trattamento: el("label", { class: "field" }, el("span", {}, "Trattamento"), treatmentSelect),
      quando: (() => {
        const startDay = (draft.start || "").split("T")[0] || todayStr();
        // A tiny proxy: the time control writes "HH:MM" through this object,
        // and the setter keeps the day the date field chose.
        const timeState = {
          get time() { return ((draft.start || "").split("T")[1] || "10:00").slice(0, 5); },
          set time(value) {
            const day = (draft.start || "").split("T")[0] || todayStr();
            draft.start = `${day}T${value}`;
          },
        };
        const box = el("div", { class: "stack tight" });
        box.appendChild(
          el("label", { class: "field" }, el("span", {}, "Data"),
            el("input", { class: "input", type: "date", value: startDay,
              on: { change: (event) => {
                const day = event.target.value || todayStr();
                const time = ((draft.start || "").split("T")[1] || "10:00").slice(0, 5);
                draft.start = `${day}T${time}`;
                this._render();
              } } }))
        );
        box.appendChild(this._timeField(timeState, "Ora"));
        return box;
      })(),
      operatore: (() => {
        const box = el("div", { class: "stack tight" });
        box.appendChild(el("label", { class: "field" }, el("span", {}, "Operatore"), operatorSelect));
        add(box, this._groupStepper());
        return box;
      })(),
      note: el("label", { class: "field" }, el("span", {}, "Note"),
        el("textarea", { class: "input", rows: "2", value: draft.notes || "",
          on: { input: (event) => { draft.notes = event.target.value; } } })),
      totali: editTotals.box,
      incassi: current ? this._editIncassiBlock(current, editTotals.total) : null,
      cliente: el("label", { class: "field" }, el("span", {}, "Cliente"), clientSelect),
      ospite: this._guestField(draft),
      accessori: this._extrasField(draft),
    };
    this._editFormOrder("left").forEach((id) => {
      if (blocks[id]) add(left, this._editFormSection(id, blocks[id]));
    });
    this._editFormOrder("right").forEach((id) => {
      if (blocks[id]) add(right, this._editFormSection(id, blocks[id]));
    });

    columns.appendChild(left);
    columns.appendChild(right);
    wrap.appendChild(columns);

    const groupSize = current ? this._groupSize(current) : 1;
    const save = async (pending, wholeGroup) => {
      try {
        await this._call("update_appointment", {
          appointment_id: this._editing.id,
          treatment_id: draft.treatment_id || undefined,
          start: draft.start || undefined,
          client_id: draft.client_id || undefined,
          operator_id: draft.operator_id || undefined,
          notes: draft.notes || "",
          payment: this._paymentData(draft),
          guest_type: draft.guest_type || GUEST_DEFAULT,
          // Always sent, so an edit that clears every accessory really
          // clears them (an empty list, not an omission that would keep the
          // old set).
          extras: draft.extras || [],
          // Prices travel as numbers; null would mean "keep", so only a
          // real number is sent and clearing a field leaves the old price.
          ...(draft.list_price != null ? { list_price: draft.list_price } : {}),
          ...(draft.price != null ? { price: draft.price } : {}),
          ...(pending ? { pending: true } : {}),
          ...(wholeGroup ? { whole_group: true } : {}),
        });
        this._editing = null;
        this._render();
      } catch (error) {
        /* shown */
      }
    };
    wrap.appendChild(
      el("div", { class: "row edit-actions" },
        el("button", {
          class: "btn primary",
          disabled: this._busy,
          title: "Salva le modifiche di questo appuntamento",
          on: { click: () => save(false, false) },
        }, el("ha-icon", { icon: "mdi:account" }),
           el("span", { class: "btn-label" }, "Salva")),
        groupSize > 1
          ? el("button", {
              class: "btn primary",
              disabled: this._busy,
              title: "Salva le modifiche su tutti gli appuntamenti del gruppo",
              on: { click: () => save(false, true) },
            }, el("ha-icon", { icon: "mdi:account-group" }),
               el("span", { class: "btn-label" }, "Salva gruppo"))
          : null,
        el("button", {
          class: "btn warn",
          disabled: this._busy,
          title: "Salva mettendo la prenotazione in attesa di conferma",
          on: { click: () => save(true, false) },
        }, el("ha-icon", { icon: "mdi:clock-outline" }),
           el("span", { class: "btn-label" }, "In attesa")),
        el("button", {
          class: "btn",
          on: { click: () => { this._editing = null; this._render(); } },
        }, el("ha-icon", { icon: "mdi:close" }),
           el("span", { class: "btn-label" }, "Annulla"))
      )
    );
    return wrap;
  }

  /** Shared save/cancel row for the three configuration editors. */
  _saveRow(addService, updateService, idField, label) {
    const { kind, id, draft } = this._editing;
    const isEditing = Boolean(id);

    const saveBtnProps = {
      class: "btn primary",
      disabled: this._busy,
      on: {
        click: async () => {
          let service = addService;
          const data = { ...draft };
          if (id) {
            service = updateService;
            data[idField] = id;
          }
          try {
            await this._call(service, data);
            this._editing = null;
            this._render();
          } catch (error) { /* shown */ }
        },
      },
    };

    const cancelBtnProps = {
      class: "btn",
      on: { click: () => { this._editing = null; this._render(); } },
    };

    const row = el("div", { class: "row" });
    row.appendChild(el("button", saveBtnProps, "Salva " + label));
    row.appendChild(el("button", cancelBtnProps, "Annulla"));

    if (isEditing && kind === "treatment") {
      const deleteBtnProps = {
        class: "btn danger",
        disabled: this._busy,
        on: {
          click: async () => {
            const future = this._data.appointments.filter((appointment) => {
              const start = parseDate(appointment.start);
              return (
                appointment.treatment_id === id &&
                appointment.status !== "cancelled" &&
                start && start > new Date()
              );
            }).length;
            if (!window.confirm("Eliminare il trattamento " + draft.name + "?")) return;
            if (future && !window.confirm("Ci sono " + future + " appuntamenti futuri. Eliminare comunque?")) return;
            try { await this._call("delete_treatment", { treatment_id: id, force: Boolean(future) }); } catch (e) { /* shown */ }
          },
        },
      };
      row.appendChild(el("button", deleteBtnProps, el("ha-icon", { icon: "mdi:delete" }), "Elimina"));
    }

    return row;
  }


  _style() {
    return el("style", {}, `
      :host {
        display: block;
        background: var(--primary-background-color, #f6f7f9);
        color: var(--primary-text-color, #212121);
        font-size: 14px;
        line-height: 1.45;
        -webkit-font-smoothing: antialiased;
      }
      * { box-sizing: border-box; }

      /* Forced appearance. Redefining the same variables the card already reads
         repaints every rule at once, so "dark" only has to name the surfaces
         and the text. --primary-color is deliberately left alone to keep the
         brand colour of the active Home Assistant theme. */
      :host([data-spa-theme="dark"]) {
        --primary-background-color: #121417;
        --card-background-color: #1b1f24;
        --ha-card-background: #1b1f24;
        --secondary-background-color: #262b32;
        --divider-color: #3a4149;
        --primary-text-color: #e9ecef;
        --secondary-text-color: #a9b2bc;
        --disabled-text-color: #6f7882;
        --error-color: #ff7b72;
        --success-color: #5fd08a;
        /* Deposit, voucher and the ways of paying need hues the theme does not
           define. They are tuned per theme: the light ones are darker so they
           hold up on white, the dark ones are lighter so they do not glow. */
        --pay-amber: #e0a33a;
        --pay-violet: #b39dff;
        --pay-blue: #7db4f5;
      }
      :host([data-spa-theme="light"]) {
        --primary-background-color: #f6f7f9;
        --card-background-color: #fff;
        --ha-card-background: #fff;
        --secondary-background-color: #f1f3f5;
        --divider-color: #e0e2e5;
        --primary-text-color: #212121;
        --secondary-text-color: #5f656b;
        --disabled-text-color: #9aa0a6;
        --error-color: #e53953;
        --success-color: #4caf50;
        --pay-amber: #a86a00;
        --pay-violet: #5b3fd1;
        --pay-blue: #1c62c4;
      }

      /* A category tint keeps the colour the desk picked in both themes; the
         ink is chosen from that colour's brightness so the row stays readable. */
      :host([data-spa-theme="dark"]) .appt.tinted :where(.appt-time, .dim, .appt-note, .appt-treat, .appt-client, ha-icon.guest-icon, .extra-icon) {
        color: var(--appt-fg, inherit);
      }
      :host([data-spa-theme="dark"]) .msg,
      :host([data-spa-theme="dark"]) .hint,
      :host([data-spa-theme="dark"]) .selected-client {
        background: var(--secondary-background-color);
      }
      :host([data-spa-theme="dark"]) .msg.error { background: rgba(255, 123, 114, .16); }
      :host([data-spa-theme="dark"]) .msg.ok { background: rgba(95, 208, 138, .16); }
      :host([data-spa-theme="dark"]) .hint.warn { background: rgba(255, 123, 114, .14); }
      :host([data-spa-theme="dark"]) .selected-client { background: rgba(95, 208, 138, .14); }
      :host([data-spa-theme="dark"]) .topbar { box-shadow: 0 1px 4px rgba(0, 0, 0, .45); }
      /* Chips carry white text by default; on the dark error/success colours
         that is still legible, but the muted ones need a light ink. */
      :host([data-spa-theme="dark"]) .chip.danger,
      :host([data-spa-theme="dark"]) .chip.warn {
        color: #1b1f24;
      }

      .topbar {
        position: sticky; top: 0; z-index: 4;
        padding: 12px 24px 0;
        background: var(--card-background-color, var(--ha-card-background, #fff));
        border-bottom: 1px solid var(--divider-color);
        box-shadow: 0 1px 4px rgba(0, 0, 0, .06);
      }
      .head { display: flex; align-items: center; gap: 12px; margin-bottom: 10px; }
      .head > ha-icon { color: var(--primary-color); --mdc-icon-size: 28px; }
      /* The hamburger sits outside that rule on purpose: it is a control, not
         the brand mark, so it keeps the ordinary button look. */
      .head .menu-btn { flex: 0 0 auto; }
      .head-text { flex: 1 1 auto; min-width: 0; overflow: hidden; }
      .title { font-size: 22px; font-weight: 600; letter-spacing: -.01em;
               white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
      .subtitle { font-size: 12px; color: var(--secondary-text-color); }
      .clock { text-align: right; line-height: 1.2; }
      .clock-time { font-size: 20px; font-weight: 600; letter-spacing: .01em;
                    font-variant-numeric: tabular-nums; }
      .clock-date { font-size: 11px; color: var(--secondary-text-color);
                    text-transform: capitalize; }
      /* Search field in the agenda header: a text input on desktop, a
         magnifier icon on mobile that opens a prompt. */
      .search-results { display: flex; flex-direction: column; gap: 2px; margin: 4px 12px 8px;
                        max-height: 40vh; overflow-y: auto; padding: 6px;
                        background: var(--card-background-color);
                        border: 1px solid var(--divider-color); border-radius: 10px; }
      .search-results-head { display: flex; align-items: center; justify-content: space-between; }
      .search-hit { display: flex; flex-direction: column; align-items: flex-start; gap: 2px;
                    width: 100%; text-align: left; background: none; border: none;
                    border-bottom: 1px solid var(--divider-color); padding: 6px 4px;
                    color: inherit; font: inherit; cursor: pointer; }
      .search-hit:last-child { border-bottom: none; }
      .voucher-find { display: flex; flex-direction: column; gap: 4px; min-width: 200px; }
      .voucher-applied { display: flex; align-items: center; gap: 6px; font-weight: 600; }
      .voucher-row { align-items: flex-start; }
      .search-hit:hover { background: var(--secondary-background-color, rgba(0,0,0,.04)); }
      .head .search-input { flex: 1 1 auto; max-width: 220px; }
      .head .search-toggle { display: none; }
      .wrap, .stack { display: flex; flex-direction: column; gap: 12px; }
      .wrap { max-width: 1240px; margin: 0 auto; padding: 12px 16px 32px;
              container-type: inline-size; }
      .wrap.config { padding: 8px 12px 24px; }
      .stack.config { gap: 6px; }
      .stack.spa { gap: 6px; }
      .stack.agenda { gap: 6px; }
      .stack.tight { gap: 6px; }
      .row { display: flex; gap: 8px; align-items: flex-end; flex-wrap: wrap; }
      .row.tight { gap: 6px; }
      .row.item { align-items: center; padding: 8px 0; border-bottom: 1px solid var(--divider-color); }

      /* Payment: a fold, because a booking usually says nothing about it, and the
         detail lines only exist while their own flag is ticked. */
      .pay-details { border: 1px solid var(--divider-color); border-radius: 8px; }
      .pay-details > summary { display: flex; align-items: center; gap: 6px;
                              padding: 8px 10px; cursor: pointer; font-size: 13px;
                              color: var(--secondary-text-color); }
      .pay-details > summary ha-icon { --mdc-icon-size: 16px; width: 16px; height: 16px; }
      .pay-details[open] > summary { color: var(--primary-text-color);
                                     border-bottom: 1px solid var(--divider-color); }
      .pay-box { padding: 10px; display: flex; flex-direction: column; gap: 8px; }
      .pay-box .checks { display: flex; flex-wrap: wrap; gap: 6px 16px; }
      .pay-check { display: inline-flex; align-items: center; gap: 5px; }
      .pay-check ha-icon { --mdc-icon-size: 15px; width: 15px; height: 15px;
                           color: var(--secondary-text-color); }
      .pay-detail { display: flex; align-items: center; gap: 8px; }
      .pay-detail > span { white-space: nowrap; }
      .pay-detail .input { max-width: 220px; }
      /* Payment lines: the checkbox with its label on the left, the field for
         the value on the right of the same row, always visible. */
      .pay-lines { display: flex; flex-direction: column; gap: 6px; }
      .pay-line { display: flex; align-items: center; justify-content: space-between; gap: 10px; }
      .pay-line .pay-check { white-space: nowrap; }
      .pay-amount { max-width: 170px; min-width: 110px; }
      /* A payment chip carries its icon: on the day of the appointment the row has to
         be readable without relying on the colour alone. */
      /* The ways of paying are quiet next to the amounts in the payment block:
         they say how, not how much, so they stay readable without competing
         with the totals. In the agenda row they lose the border entirely and
         become plain coloured icons. */
      .chip.method { background: transparent; color: var(--secondary-text-color);
                     border: 1px solid var(--divider-color); }
      /* The detail popup: a sheet over the agenda, so the day behind it stays
         where the reader left it. It scrolls inside itself rather than growing
         past the bottom of a phone. */
      .detail-backdrop {
        position: fixed; inset: 0; z-index: 20;
        background: rgba(0, 0, 0, .45);
        display: flex; align-items: center; justify-content: center;
        padding: max(16px, env(safe-area-inset-top)) 16px max(16px, env(safe-area-inset-bottom));
      }
      .detail-sheet {
        background: var(--card-background-color, var(--ha-card-background, #fff));
        border-radius: 14px; width: 100%; max-width: 560px;
        max-height: 100%; overflow-y: auto;
        padding: 16px 18px 18px;
        box-shadow: 0 12px 40px rgba(0, 0, 0, .3);
      }
      .detail-head { display: flex; align-items: flex-start; gap: 12px; margin-bottom: 4px; }
      .detail-head > div { flex: 1 1 auto; min-width: 0; }
      .detail-title { font-size: 18px; font-weight: 600; overflow-wrap: anywhere; }
      .detail-sub { font-size: 12px; color: var(--secondary-text-color);
                    overflow-wrap: anywhere; }
      .detail-section { border-top: 1px solid var(--divider-color); padding-top: 10px; margin-top: 10px; }
      .detail-section h4 {
        margin: 0 0 6px; font-size: 11px; font-weight: 600; letter-spacing: .06em;
        text-transform: uppercase; color: var(--secondary-text-color);
      }
      .detail-rows { display: flex; flex-direction: column; gap: 4px; }
      .detail-line { display: flex; gap: 12px; align-items: baseline; font-size: 14px; }
      .detail-label { flex: 0 0 40%; color: var(--secondary-text-color); font-size: 13px; }
      .detail-value { flex: 1 1 auto; min-width: 0; overflow-wrap: anywhere; }
      .detail-value.ok { color: var(--success-color, #4caf50); }
      .detail-value.pending { color: var(--pay-amber, #c98209); }
      /* A booking still waiting: amber, like the acconto icon, and hollow so
         it reads as "not yet" rather than as another filled label. */
      .chip.pending {
        background: transparent; color: var(--pay-amber, #c98209);
        border: 1px solid var(--pay-amber, #c98209);
      }
      .detail-value.deposit { color: var(--pay-amber, #c98209); }
      .detail-value.due { color: var(--error-color, #e53953); }
      .detail-value.voucher { color: var(--pay-violet, #7a5af5); }
      /* The hotel/external flag in the popup: icon and words together. */
      .detail-guest { display: inline-flex; align-items: center; gap: 4px; }
      .detail-guest ha-icon { --mdc-icon-size: 16px; color: var(--secondary-text-color); }
      .detail-guest.hotel ha-icon { color: var(--guest-gold, #b98f2f); }
      /* The accessories in the popup: one pill per chosen extra, icon first. */
      .detail-extras { display: inline-flex; flex-wrap: wrap; gap: 6px; }
      .extra-pill { display: inline-flex; align-items: center; gap: 4px;
                    padding: 2px 8px; border-radius: 999px; font-size: 12px;
                    background: var(--secondary-background-color); }
      .extra-pill ha-icon { --mdc-icon-size: 15px; color: var(--primary-color); }
      .detail-role { display: inline-flex; align-items: center; gap: 6px; }
      .detail-role ha-icon { --mdc-icon-size: 17px; }
      .detail-role.mass { color: var(--pay-blue, #2f7de1); }
      .detail-role.mgr { color: var(--pay-violet, #7a5af5); }
      .detail-method { display: inline-flex; align-items: center; gap: 5px; margin-right: 12px; }
      .detail-method ha-icon { --mdc-icon-size: 17px; }
      .detail-method.card { color: var(--pay-blue, #2f7de1); }
      .detail-method.cash { color: var(--success-color, #4caf50); }
      .detail-method.bank_transfer { color: var(--pay-violet, #7a5af5); }
      .detail-text { font-size: 14px; overflow-wrap: anywhere; }
      .detail-actions {
        display: flex; flex-wrap: wrap; gap: 8px;
        border-top: 1px solid var(--divider-color); padding-top: 12px; margin-top: 14px;
      }
      /* Contact buttons on the left, the management actions on the right. */
      .detail-contacts { display: flex; gap: 6px; margin-left: auto; }
      .btn.tel { background: var(--primary-color); border-color: var(--primary-color);
                 color: var(--text-primary-color, #fff); padding: 8px 10px; }
      .btn.wa { background: #25d366; border-color: #25d366; color: #fff; padding: 8px 10px; }
      /* "Copia persona 1 a tutte", on the + of the people stepper: a filled
         button like the contacts, so it is read as an action and not as a
         label. */
      .btn.copy-all { background: var(--primary-color); border-color: var(--primary-color);
                       color: var(--text-primary-color, #fff); padding: 8px 10px;
                       margin-left: 6px; }
      .btn.copy-all ha-icon { --mdc-icon-size: 18px; width: 18px; height: 18px; }

      /* The role of an operator. Two tones, and they are the only ones on this
         screen that mean "who this person is" rather than "what is owed": blue
         for the ones who give massages, violet for the spa managers, so the
         two groups read apart in a list without reading a word. */
      .role-choice { display: flex; gap: 8px; flex-wrap: wrap; }
      .role-opt {
        display: inline-flex; align-items: center; gap: 6px;
        padding: 8px 12px; border-radius: 999px; cursor: pointer;
        border: 1px solid var(--divider-color);
        background: transparent; color: var(--secondary-text-color);
        font-size: 13px;
      }
      .role-opt ha-icon { --mdc-icon-size: 18px; }
      .role-opt.on {
        border-color: var(--primary-color); color: var(--primary-color);
        background: var(--secondary-background-color);
      }
      .role-badge {
        display: inline-flex; align-items: center; gap: 5px; flex: 0 0 auto;
        padding: 2px 9px; border-radius: 999px; font-size: 11px;
        border: 1px solid currentColor;
      }
      .role-badge ha-icon { --mdc-icon-size: 14px; }
      .role-badge.mass { color: var(--pay-blue, #2f7de1); }
      .role-badge.mgr { color: var(--pay-violet, #7a5af5); }

      /* Payment icons in the agenda row: a horizontal strip, no text.
         Colour is the only carrier of meaning here, so each state gets a hue
         that survives both themes and never collides with the category tint
         behind the row: green paid, amber deposit, red still owed. */
      .pay-icons { display: inline-flex; align-items: center; gap: 6px; }
      .pay-icon { display: inline-flex; line-height: 0; }
      .pay-icon ha-icon { --mdc-icon-size: 15px; }
      .pay-icon.ok { color: var(--success-color, #4caf50); }
      .pay-icon.due { color: var(--error-color, #e53953); }
      /* Deposit and voucher have no semantic colour in the theme, so they get
         their own: amber reads as "partly settled", violet as a document. */
      .pay-icon.deposit { color: var(--pay-amber, #c98209); }
      .pay-icon.voucher { color: var(--pay-violet, #7a5af5); }
      /* The ways of paying each have a hue, so card and cash are told apart
         without reading. They sit apart from the state colours on purpose. */
      .pay-icon.card { color: var(--pay-blue, #2f7de1); }
      .pay-icon.cash { color: var(--success-color, #4caf50); }
      .pay-icon.bank_transfer { color: var(--pay-violet, #7a5af5); }
      .pay-icon.gift_card { color: var(--pay-gold, #b8860b); }
      /* Overlap question popup: danger icon and message centred, the
         message in red. */
      .overlap-sheet .overlap-icon { display: flex; justify-content: center; }
      .overlap-sheet .overlap-icon ha-icon { --mdc-icon-size: 44px; color: var(--error-color, #e53953); }
      .overlap-sheet .overlap-title { text-align: center; }
      .overlap-sheet .overlap-text { text-align: center; color: var(--error-color, #e53953); font-weight: 600; }
      .pay-methods { display: flex; flex-direction: column; gap: 6px;
                     border-top: 1px solid var(--divider-color); padding-top: 8px; }

      /* The operator's history, folded under her configuration row. The row is
         a grid so the date column stays aligned down the whole list, and it
         collapses to one line per field on a narrow screen. */
      .op-card { border: 1px solid var(--divider-color); border-radius: 10px;
                 margin-bottom: 8px; overflow: hidden; }
      .op-card > .item { border-bottom: none; padding: 8px 10px; }
      /* The head of an operator card: text on the left (wraps freely), the
         contact buttons stacked on the right and always in place. */
      .op-head { align-items: flex-start; gap: 8px; flex-wrap: nowrap; }
      /* Role badge on top, priority and the on/off switch under it. */
      .op-role { display: flex; flex-direction: column; gap: 4px; align-items: flex-start;
                 flex: 0 0 auto; }
      .op-priority { display: flex; align-items: center; gap: 4px; }
      /* Four buttons in a 2x2 block on the right: pencil/cancel on top,
         phone/WhatsApp below. */
      .op-actions { display: grid; grid-template-columns: auto auto; gap: 4px;
                    flex: 0 0 auto; }
      .op-actions .btn { justify-content: center; align-items: center;
                         padding: 8px; min-width: 38px; box-sizing: border-box; }
      .op-slot { display: block; }
      .op-head .grow { overflow-wrap: anywhere; min-width: 0; }

      /* Two-column layout for operators: massaggiatori on the left, others
         on the right. Each column has a header with count and its own list. */
      /* Two fixed columns (massaggiatori / spa manager) that share the width,
         so they stay side by side even on a narrow dashboard column. */
      .operators-columns { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr));
                           gap: 16px; align-items: start; }
      .operators-column { min-width: 0; }
      .column-header { display: flex; align-items: center; gap: 8px;
                       padding: 8px 10px; margin-bottom: 8px;
                       background: var(--secondary-background-color);
                       border-radius: 8px 8px 0 0; }
      .column-header ha-icon { --mdc-icon-size: 20px; color: var(--primary-color); }
      .column-header > span:not(.column-count) { flex: 1 1 auto; font-weight: 600; font-size: 14px; }
      .column-count { background: var(--primary-color); color: var(--text-primary-color, #fff);
                      padding: 2px 8px; border-radius: 999px; font-size: 12px; }
      @media (max-width: 720px) {
        .operators-columns { grid-template-columns: minmax(0, 1fr); }
      }

      /* The operator's history, folded under her configuration row. The row is
         a grid so the date column stays aligned down the whole list, and it
         collapses to one line per field on a narrow screen. */
      .hist-box summary {
        display: flex; align-items: center; gap: 6px;
        padding: 9px 12px; cursor: pointer; font-size: 13px;
        border: 1px solid var(--divider-color); border-radius: 8px;
        background: var(--secondary-background-color);
        color: var(--primary-text-color); font-weight: 500; list-style: none;
      }
      .hist-box summary ha-icon { --mdc-icon-size: 16px; width: 16px; height: 16px; }
      .hist-box[open] summary { color: var(--primary-text-color); }
      .hist-box .hint { padding: 0 10px 6px; }
      .hist-list { max-height: 300px; overflow-y: auto;
                   border-top: 1px solid var(--divider-color); }
      .hist-row { display: grid; grid-template-columns: 148px minmax(0, 1fr) minmax(0, 1.2fr) auto;
                  gap: 10px; align-items: baseline; padding: 7px 10px;
                  border-top: 1px solid var(--divider-color); font-size: 13px; }
      .hist-row:first-child { border-top: none; }
      .hist-when { color: var(--secondary-text-color); font-size: 12px;
                   font-variant-numeric: tabular-nums; white-space: nowrap; }
      .hist-client, .hist-treat { overflow: hidden; text-overflow: ellipsis;
                                  white-space: nowrap; }
      .hist-row.annullato { opacity: .7; }
      .hist-row.annullato .hist-client { text-decoration: line-through; }
      @media (max-width: 720px) {
        .hist-row { grid-template-columns: 1fr; gap: 2px; }
        .hist-client, .hist-treat { white-space: normal; }
      }

      /* The new-booking form: date and people first, one compact block per
         person. Tighter gaps so the card stops feeling padded out. */
      .form-compact { gap: 8px; }
      .form-compact .row { gap: 6px; }
      /* The edit buttons share the width and wrap, so they never overflow on a
         phone; there the labels are hidden (see the small-screen rule) and only
         the icons remain: person, group, clock, close. */
      .edit-actions .btn { flex: 1 1 auto; justify-content: center; }
      .form-compact .field { gap: 2px; }
      .form-compact .bk-person { padding: 8px 10px; margin-top: 6px; }
      .form-compact .bk-person-head { margin-bottom: 4px; }
      .form-compact .preview { padding: 6px 10px; }
      /* Two-column form layouts (new booking, operator, edit): the main data
         on the left, the client (or the massages) on the right. Falls back
         to one column on a narrow screen. */
      .two-col { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr));
                 gap: 16px; align-items: start; }
      /* One column chosen from the pencil: the blocks stack, each full width. */
      .two-col.one-col { grid-template-columns: minmax(0, 1fr); }
      @media (max-width: 720px) {
        .two-col { grid-template-columns: minmax(0, 1fr); }
      }
      /* The two buttons that pick one column or two, left of the tab title. */
      .col-chooser { display: flex; align-items: center; gap: 6px; }
      .col-chooser-label { font-size: 12px; color: var(--secondary-text-color); }
      .col-chooser .btn { display: inline-flex; align-items: center; gap: 4px; }
      .col-chooser .btn.on { background: rgba(var(--rgb-primary-color, 77, 87, 240), .15);
                             border-color: var(--primary-color); color: var(--primary-color);
                             font-weight: 600; }
      /* Nuovo appuntamento edit mode: the blocks inside each column get a
         visible outline and a drag handle; only their order can change. */
      .form-col { min-width: 0; }
      .form-sec { position: relative; }
      .form-sec .form-grip { position: absolute; top: 6px; right: 6px;
                             width: 28px; height: 28px; display: none;
                             color: var(--secondary-text-color);
                             background: var(--card-background-color); }
      .form-edit .form-sec { border: 1px dashed var(--divider-color);
                             border-radius: 10px; padding: 8px 34px 8px 10px;
                             background: rgba(var(--rgb-primary-color, 77, 87, 240), .04); }
      .form-edit .form-sec .form-grip { display: inline-flex; }
      .form-sec.dragging { opacity: .7; outline: 2px dashed var(--primary-color); }
      /* One settings section, boxed so a config tab reads as a set of cards. */
      .cfg-box { border: 1px solid var(--divider-color); border-radius: 10px;
                 padding: 10px 12px; display: flex; flex-direction: column; gap: 6px;
                 min-width: 0; }
      .cfg-box > h3 { margin: 0; }
      /* One Home Assistant user per row in the Accessi tab: avatar, name and
         badges, then the access level. The level select is pushed to the
         right and stays put when the name is long. */
      .accessi-row { display: flex; align-items: center; gap: 10px;
                     padding: 6px 0; border-top: 1px solid var(--divider-color, #e0e0e0); }
      .accessi-row:first-of-type { border-top: 0; }
      .accessi-avatar { flex: 0 0 auto; width: 34px; height: 34px; border-radius: 50%;
                        display: flex; align-items: center; justify-content: center;
                        background: var(--primary-color); color: var(--text-primary-color);
                        font-weight: 600; font-size: 13px; text-transform: uppercase; }
      .accessi-who { flex: 1 1 auto; min-width: 0; display: flex; flex-direction: column; gap: 2px; }
      .accessi-name { font-weight: 500; overflow: hidden; text-overflow: ellipsis;
                      white-space: nowrap; }
      .accessi-badges { display: flex; gap: 4px; flex-wrap: wrap; }
      .badge { font-size: 10px; line-height: 1; padding: 2px 6px; border-radius: 999px;
               background: var(--secondary-background-color, #eee);
               color: var(--secondary-text-color); text-transform: uppercase;
               letter-spacing: .03em; }
      /* Bell in the header: the count of the website's requests not yet seen. */
      .notify-btn { position: relative; }
      .notify-badge {
        position: absolute; top: -3px; right: -3px; min-width: 15px; height: 15px;
        padding: 0 4px; border-radius: 999px; background: var(--error-color, #d32f2f);
        color: #fff; font-size: 10px; font-weight: 600; line-height: 15px;
        text-align: center; pointer-events: none;
      }
      .accessi-row .input { flex: 0 0 auto; width: auto; max-width: 180px; }
      .stepper-field { flex: 0 0 120px; }
      .stepper { display: flex; align-items: center; gap: 2px; }
      .stepper-num { min-width: 26px; text-align: center; font-variant-numeric: tabular-nums;
                     font-size: 14px; color: var(--primary-text-color); }
      .stepper .icon-btn { width: 30px; height: 30px; }
      .grow { flex: 1 1 auto; min-width: 0; }
      .spacer { flex: 1 1 auto; }
      /* The agenda bar never wraps: today, the day arrows and the two actions
         stay on one line. The filter chips live on their own row below. */
      .agenda-bar { flex-wrap: nowrap; align-items: center; }
      .agenda-bar > * { flex: 0 0 auto; }
      .agenda-bar .date-input { flex: 1 1 auto; min-width: 0; }
      .agenda-filters { align-items: center; }
      @media (max-width: 720px) {
        .agenda-bar { gap: 4px; }
        .agenda-bar .btn { padding: 6px 8px; }
        .head { gap: 8px; }
        .head > ha-icon { display: none; }
        .title { font-size: 18px; }
        .head .search-input { display: none; }
        .head .search-toggle { display: inline-flex; }
        /* Configuration, Spa, Agenda and Nuovo: sidebar layout. The sub-tabs become a
           narrow vertical strip on the left, the active page fills the rest on
           the right. */
        .stack.config, .stack.spa, .stack.agenda, .stack.nuovo { flex-direction: row; align-items: stretch; gap: 8px; }
        .stack.config > .tabs, .stack.spa > .tabs, .stack.agenda > .tabs, .stack.nuovo > .tabs { flex-direction: column; flex: 0 0 auto; width: auto;
          min-width: 44px; gap: 4px; padding-bottom: 0; margin-bottom: 0; }
        .stack.config > .tabs .spacer, .stack.spa > .tabs .spacer, .stack.agenda > .tabs .spacer, .stack.nuovo > .tabs .spacer { display: none; }
        .stack.config > .tabs .tab, .stack.spa > .tabs .tab, .stack.agenda > .tabs .tab, .stack.nuovo > .tabs .tab { flex-direction: column; gap: 0; padding: 10px 4px;
          border-radius: 10px; justify-content: center; width: 100%; }
        .stack.config > .tabs .tab .tab-label, .stack.spa > .tabs .tab .tab-label, .stack.agenda > .tabs .tab .tab-label, .stack.nuovo > .tabs .tab .tab-label { display: none; }
        .stack.config > *:not(.tabs), .stack.spa > *:not(.tabs), .stack.agenda > *:not(.tabs), .stack.nuovo > *:not(.tabs) { flex: 1 1 auto; min-width: 0;
          display: flex; flex-direction: column; align-items: stretch; }
      }
      h3 { margin: 6px 0 0; font-size: 12px; font-weight: 600; letter-spacing: .06em;
           text-transform: uppercase; color: var(--secondary-text-color); }
      .dim { color: var(--secondary-text-color); }
      .small { font-size: 12px; }
      /* Hide secondary small text in operators list on mobile to save space. */
      @media (max-width: 720px) {
        .operators-column .dim.small { display: none; }
      }
      .sep { margin: 0 4px; color: var(--disabled-text-color); }
      .sr-only { position: absolute; width: 1px; height: 1px; overflow: hidden; clip: rect(0 0 0 0); }

      .tabs { display: flex; gap: 6px; flex-wrap: wrap; margin-bottom: 0; padding-bottom: 12px; }
      /* Detail popup: visible icon-only buttons on mobile */
      .detail-toggle .btn .ha-icon { --mdc-icon-size: 18px; display: inline-flex; }
      .detail-toggle .btn-label { margin-left: 4px; }
      .detail-actions .btn .ha-icon { --mdc-icon-size: 18px; }
      .detail-actions .btn-label { margin-left: 4px; }
      @media (max-width: 720px) {
        /* force ***ha-icon visible*** on these buttons even if theme overrides */
        .detail-toggle .btn { padding: 8px 10px; min-width: 36px; min-height: 36px; }
        .detail-actions .btn { padding: 6px 8px; min-width: 36px; min-height: 32px; }
        .detail-actions .btn .ha-icon,
        .detail-toggle .btn .ha-icon {
          --mdc-icon-size: 22px !important;
          --ha-icon-size: 22px !important;
          width: 22px !important; height: 22px !important;
          display: inline-block !important;
          opacity: 1 !important;
        }
        /* keep label hidden on phone */
        .detail-toggle .btn .btn-label, .detail-actions .btn .btn-label { display: none !important; }
      }
      /* also base (desktop/mobile) explicit icon sizes */
      .detail-toggle .btn .ha-icon,
      .detail-actions .btn .ha-icon {
        --mdc-icon-size: 18px; --ha-icon-size: 18px; width: 18px; height: 18px; display:inline-flex;
      }
      .tab {
        display: inline-flex; align-items: center; gap: 6px;
        padding: 8px 12px; border-radius: 999px; cursor: pointer;
        border: 1px solid var(--divider-color); background: transparent;
        color: var(--secondary-text-color); font: inherit; font-size: 13px;
      }
      .tab.small, .tab.small.active { padding: 6px 10px; font-size: 12px; }
      .tab ha-icon { --mdc-icon-size: 18px; }
      .tab.active { background: var(--primary-color); border-color: var(--primary-color);
                    color: var(--text-primary-color, #fff); }
      /* On a phone the tab bar and the agenda buttons keep the icons only:
         the labels are dropped to leave room to the day. */
      @media (max-width: 720px) {
        .tab .tab-label, .btn .btn-label { display: none; }
        .tab { padding: 8px 10px; }
        /* The group chip keeps only icon and count, and the waiting chip only
           its icon, so the row stays light on a phone. */
        .chip.group .group-label { display: none; }
        .chip.group { padding: 1px 5px; font-size: 10px; }
        .chip.pending .chip-text { display: none; }
        .chip.pending { padding: 1px 5px; }
        .chip.group .chip-icon, .chip.pending .chip-icon { width: 12px; height: 12px; --mdc-icon-size: 12px; }
      }

      /* A field takes exactly the width its content needs and never grows: a fixed
         basis made it reserve 180px of height when stacked in a column, and
         of width when sharing a row. Shrinking is still allowed so a narrow
         screen squeezes the fields instead of overflowing. */
      .field { display: flex; flex-direction: column; gap: 4px;
               font-size: 12px; color: var(--secondary-text-color);
               flex: 0 1 auto; min-width: 0; }
      /* Declared after .field, so a field explicitly marked "grow" still
         fills the free width of its row (used by the colour swatch editor). */
      .field.grow { flex: 1 1 auto; }
      /* Pairs of fields side by side (nome/cognome, telefono/email): two
         columns at every width, because a name or a phone number never needs a
         whole row to itself. */
      .field-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr));
                    gap: 8px; align-items: end; }
      /* Totali of a booking: the treatment and its two prices stay on one
         line, so a figure is always read against the treatment it belongs to.
         The two price columns keep their width at every size and the
         treatment column takes whatever is left. */
      .totali-grid { display: grid;
                     grid-template-columns: minmax(0, 1fr) 96px 96px;
                     gap: 6px 8px; align-items: center; }
      .totali-grid .totali-head { font-size: 11px; font-weight: 600;
                                  letter-spacing: .04em; text-transform: uppercase;
                                  color: var(--secondary-text-color); }
      .totali-name { min-width: 0; font-size: 13px; }
      /* The deposit asked for, on the same two-column rhythm as the prices:
         the label takes the free width, the amount sits where the price
         column sits, so the two figures line up. */
      .deposit-row { display: grid; grid-template-columns: minmax(0, 1fr) 96px;
                     gap: 6px 8px; align-items: center; }
      .deposit-label { min-width: 0; font-size: 12px;
                       color: var(--secondary-text-color); }
      /* On a phone the three columns still stand: the prices are what the desk
         came to check, so only the treatment column narrows. */
      @media (max-width: 720px) {
        .totali-grid { grid-template-columns: minmax(0, 1fr) 86px 86px; gap: 6px; }
        .totali-grid .totali-head { font-size: 10px; letter-spacing: .02em; }
        .totali-name { font-size: 12px; }
        .deposit-row { grid-template-columns: minmax(0, 1fr) 86px; gap: 6px; }
      }
      .input {
        width: 100%; padding: 9px 10px; font: inherit; color: var(--primary-text-color);
        background: var(--card-background-color); border: 1px solid var(--divider-color);
        border-radius: 8px; min-width: 0;
      }
      .input:focus { outline: none; border-color: var(--primary-color); }
      textarea.input { resize: vertical; }
      .date-input { padding: 7px 8px; font: inherit; border: 1px solid var(--divider-color);
                    border-radius: 8px; background: var(--card-background-color);
                    color: var(--primary-text-color); }
      /* Time entry: two selects (hours, minutes) and a clock button that opens
         the native picker, which is the round clock on a phone. */
      .time-row { align-items: center; gap: 6px; position: relative; }
      .time-row select.input { width: auto; min-width: 58px; }
      .time-native { position: absolute; width: 1px; height: 1px; opacity: 0;
                     pointer-events: none; }
      .check { display: flex; align-items: center; gap: 8px; font-size: 13px;
               color: var(--primary-text-color); }
      .checks { display: flex; flex-direction: column; gap: 6px; }
      /* "Come ha pagato": the ways of paying stay on two columns even on a
         phone, where one per line would make the block taller than the
         amounts above it. */
      .pay-methods .checks { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr));
                             gap: 6px 12px; }
      .pay-methods .check { min-width: 0; }

      .btn {
        display: inline-flex; align-items: center; gap: 6px; padding: 9px 14px;
        border-radius: 8px; border: 1px solid var(--divider-color); cursor: pointer;
        background: transparent; color: var(--primary-text-color); font: inherit; font-size: 13px;
      }
      .btn small { padding: 6px 10px; font-size: 12px; }
      .btn ha-icon { --mdc-icon-size: 18px; }
      .btn:disabled { opacity: .5; cursor: not-allowed; }
      .btn.primary { background: var(--primary-color); border-color: var(--primary-color);
                      color: var(--text-primary-color, #fff); }
      .icon-btn {
        display: inline-flex; align-items: center; justify-content: center;
        width: 34px; height: 34px; border-radius: 50%; border: none; cursor: pointer;
        background: transparent; color: var(--secondary-text-color);
        text-decoration: none; flex: 0 0 auto;
      }
      .icon-btn ha-icon { --mdc-icon-size: 20px; }
      .icon-btn:hover { background: var(--secondary-background-color); }
      .icon-btn.danger { color: var(--error-color); }
      .btn.danger { color: var(--error-color); }
      .btn.warn { background: var(--warning-color, #ffa726);
                  border-color: var(--warning-color, #ffa726); color: #212121; }
      /* Confirmation state of an appointment with an operator: green once she
         confirmed, amber while the offer is still open. */
      .btn.offer-ok { background: #2e7d32; border-color: #2e7d32; color: #fff; }
      .btn.offer-wait { background: #f9a825; border-color: #f9a825; color: #212121; }
      .offer-check { cursor: pointer; --mdc-icon-size: 18px; }
      .offer-check.ok { color: #2e7d32; }
      .offer-check.wait { color: #f9a825; }
      .offer-check.static { cursor: default; }
      .icon-btn.primary { color: var(--primary-color); }

      .hint { font-size: 12px; color: var(--secondary-text-color); padding: 8px 10px;
              background: var(--secondary-background-color); border-radius: 8px; }
      .hint.warn { color: var(--error-color); background: rgba(229, 57, 53, .1); }
      .empty { padding: 18px 12px; text-align: center; color: var(--secondary-text-color);

      /* WhatsApp external messages tab */
      .wa-list { display: flex; flex-direction: column; gap: 12px; }
      .wa-card {
        border: 1px solid var(--divider-color);
        border-radius: 12px;
        padding: 12px 14px;
        background: var(--card-background-color, var(--ha-card-background, #fff));
        display: flex;
        flex-direction: column;
        gap: 8px;
      }
      .wa-header { display: flex; align-items: center; gap: 8px; }
      .wa-header ha-icon { color: #25d366; --mdc-icon-size: 20px; }
      .wa-sender { font-weight: 600; font-size: 13px; flex: 1; }
      .wa-time { font-size: 12px; color: var(--secondary-text-color); }
      .wa-text { font-size: 14px; line-height: 1.4; word-break: break-word;
                 padding: 8px 10px; background: var(--secondary-background-color);
                 border-radius: 8px; }
      .wa-actions { display: flex; flex-wrap: nowrap; gap: 8px; margin-top: 8px; align-items: center; }
      .wa-actions .btn { font-size: 12px; padding: 4px 10px; flex: 0 0 auto; }
      .wa-reply { display: flex; gap: 6px; margin-top: 8px; padding-top: 8px; border-top: 1px solid var(--divider-color); }
      .wa-reply-input {
        flex: 1; padding: 6px 10px; border: 1px solid var(--divider-color);
        border-radius: 8px; font: inherit; font-size: 13px;
        background: var(--input-background-color, transparent);
        color: var(--primary-text-color, #000);
      }
      .wa-reply .btn { font-size: 12px; padding: 4px 10px; }
               border: 1px dashed var(--divider-color); border-radius: 8px; }
      /* The full-screen message an account without access to the dashboard
         gets. Centred and quiet, with no data behind it. */
      .denied { max-width: 420px; margin: 12vh auto 0; padding: 24px 20px;
                text-align: center; display: flex; flex-direction: column;
                gap: 8px; align-items: center; }
      .denied h2 { margin: 0; font-size: 20px; }
      .denied p { margin: 0; color: var(--secondary-text-color); }
      .denied-icon { --mdc-icon-size: 48px; color: var(--secondary-text-color); }
      .meta { font-size: 12px; color: var(--secondary-text-color);
              display: flex; flex-wrap: wrap; gap: 2px 10px; align-items: baseline; }
      .meta-hours { color: var(--secondary-text-color); }
      .day-title { font-size: 16px; font-weight: 500; }
      .month-title { flex: 1 1 auto; text-align: center; font-size: 16px; font-weight: 500; }

      .msg { display: flex; align-items: center; gap: 8px; padding: 10px 12px; border-radius: 8px; font-size: 13px; }
      .msg span { flex: 1 1 auto; }
      .msg.error { background: rgba(229, 57, 53, .12); color: var(--error-color); }
      .msg.ok { background: rgba(76, 175, 80, .14); color: var(--success-color, #4caf50); }

      /* Agenda in two columns: everything else on the left, massages on the
         right; on a narrow screen they stack into one. */
      .agenda-columns { display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
                        gap: 12px; align-items: start; }
      .agenda-column { min-width: 0; display: flex; flex-direction: column; gap: 10px; }
      /* Mobile: one column. The @container rule keys off the card's own width
         (not the viewport), so it also fires inside the Companion app and in
         sidebars; the @media rule is a fallback where containers are
         unsupported. Both come after the two-column definition, so they win. */
      @container (max-width: 720px) {
        .agenda-columns { grid-template-columns: minmax(0, 1fr); }
      }
      @media (max-width: 720px) {
        .agenda-columns { grid-template-columns: minmax(0, 1fr); }
      }
      .group { border: 1px solid var(--divider-color); border-radius: 10px; padding: 10px; }
      .group-head { display: flex; align-items: center; gap: 8px; font-weight: 500; margin-bottom: 8px; }
      .group-head ha-icon { --mdc-icon-size: 18px; color: var(--primary-color); }
      /* A party of several people under one booking: a header that opens and
         closes to reveal the single rows. */
      .party-head { display: flex; align-items: center; gap: 6px; padding: 6px 8px;
                    border-radius: 8px; cursor: pointer; font-size: 13px;
                    color: var(--secondary-text-color); }
      .party-head:hover { background: var(--secondary-background-color); }
      .party-head.open { color: var(--primary-text-color); }
      .party-head .party-caret { --mdc-icon-size: 18px; }
      .party-head .party-label { font-weight: 500; }
      .badge { margin-left: auto; min-width: 22px; text-align: center; padding: 1px 6px;
               border-radius: 999px; font-size: 12px; font-weight: 500;
               background: var(--secondary-background-color); color: var(--secondary-text-color); }

      /* Every row keeps the same left gutter, so the group bar can appear
         without shifting any text in the list. */
      .appt { display: flex; gap: 8px; align-items: center; padding: 8px 0 8px 10px;
              border-top: 1px solid var(--divider-color); }
      .appt:first-of-type { border-top: none; }
      .appt.compact { padding: 6px 0 6px 10px; }
      .appt.cancelled { opacity: .55; }
      .appt.cancelled .appt-client { text-decoration: line-through; }
      .appt.tinted { background: var(--appt-bg); border-radius: 6px; padding: 8px 12px;
                     color: var(--appt-fg, inherit); }
      /* The neutral action buttons ride the same ink as the row, so their
         icons stay readable on whatever colour the category carries. The
         coloured ones (phone, WhatsApp, primary, danger, offer) keep theirs. */
      .appt.tinted .appt-actions .btn:not(.tel):not(.wa):not(.primary):not(.danger):not(.offer-ok):not(.offer-wait):not(.warn) {
        color: var(--appt-fg, inherit);
        border-color: var(--appt-fg, var(--divider-color));
      }
      /* People of one group: a bar in the gutter plus a chip with the count.
         The bar takes the group's own colour, so every group of the day reads
         as its own; alone rows have no bar at all. */
      .appt.grouped { box-shadow: inset 3px 0 0 var(--group-color, var(--primary-color)); }
      /* The whole main block of a row is the tap target for the detail popup,
         so it needs to look clickable and to stay reachable from the
         keyboard, not just the little pencil in the actions. */
      .appt-main { display: flex; gap: 12px; align-items: flex-start; flex: 1 1 auto; min-width: 0;
                   cursor: pointer; border-radius: 6px; }
      .appt-main:focus-visible { outline: 2px solid var(--primary-color); outline-offset: 2px; }
      .appt-main:hover { background: var(--secondary-background-color); }
      .appt-time { font-variant-numeric: tabular-nums; font-weight: 500; white-space: nowrap;
                   color: var(--primary-color); }
      /* Time and category stacked on the left, so the icons on the right have
         the whole width to themselves. */
      .appt-left { display: flex; flex-direction: column; align-items: flex-start; gap: 3px;
                   flex: 0 0 auto; }
      /* The booking reference under the time on every agenda row: small,
         monospotted, the reception spots it at a glance. */
      .appt-code { font-size: 10px; font-weight: 600; letter-spacing: 0.5px;
                   color: var(--secondary-text-color); font-variant-numeric: tabular-nums; }
      /* Category and group chip on one line, under the time. */
      .appt-tags { display: flex; align-items: center; gap: 4px; flex-wrap: wrap; }
      .appt-body { min-width: 0; display: flex; flex-direction: column; gap: 2px; }
      .appt-client { font-weight: 500; }
      /* The hotel/external flag riding with the client's name: quiet grey for
         an external guest, gold for a hotel one. */
      ha-icon.guest-icon {
        --mdc-icon-size: 15px; color: var(--secondary-text-color);
      }
      ha-icon.guest-icon.hotel { color: var(--guest-gold, #b98f2f); }
      .appt-treat { font-size: 13px; display: flex; align-items: center; gap: 5px;
                    flex-wrap: wrap; }
      /* The icons of one row (accessories, payments, group) on their own line. */
      .appt-icons { display: flex; align-items: center; gap: 8px; flex-wrap: wrap;
                    margin-top: 1px; }
      /* The accessories this person chose, one icon each. */
      .appt-extras { display: inline-flex; gap: 4px; align-items: center; }
      .appt-extras .extra-icon { --mdc-icon-size: 15px; color: var(--secondary-text-color); }
      /* La stella: segnala che la richiesta di recensione è già partita per
         questo appuntamento. Piccola e dorata, sempre visibile nella riga. */
      .review-star { --mdc-icon-size: 16px; color: #e0a800; }
      /* Pulsante "Recensione inviata": verde, spento, non premibile due volte. */
      .btn.review-sent { color: var(--success-color, #2e9e5b);
                         border-color: var(--success-color, #2e9e5b);
                         opacity: 1; }
      .appt-note { font-size: 12px; color: var(--secondary-text-color); font-style: italic; }
      /* Phone and WhatsApp always on their own row, under the management
         actions (pencil, cancel, confirm, entry, notes), on every screen. */
      .appt-actions { display: flex; gap: 2px; flex: 0 0 auto; flex-wrap: wrap;
                      justify-content: flex-end; }
      /* The action buttons in the agenda share the look of the operator list:
         square, icon centred, one fixed minimum width. */
      .appt-actions .btn { justify-content: center; align-items: center;
                           padding: 8px; min-width: 38px; box-sizing: border-box; }
      .appt-actions .btn.checkin { min-width: 80px; height: 32px; padding: 0 8px; }
      .appt-actions .btn[class*="pencil"],
      .appt-actions .btn.danger { min-width: 38px; height: 32px; padding: 0; border-color: var(--appt-fg, var(--divider-color)); }
      .appt-actions-break { flex-basis: 100%; height: 0; order: 5; }
      .appt-actions .appt-contact { order: 10; }
      /* On mobile, the Entrata (check-in) button sits on its own row above
         Modifica and Annulla, aligned right at natural width. */
      .appt-actions .btn.checkin { order: 0; }
      .appt-actions .checkin-break { flex-basis: 100%; height: 0; order: 0; }
      .appt-actions .btn[class*="pencil"] { order: 1; }
      .appt-actions .btn.danger { order: 2; }
      .chip { display: inline-block; padding: 1px 8px; border-radius: 999px; font-size: 11px;
              background: var(--primary-color); color: var(--text-primary-color, #fff);
              width: fit-content; }
      .chip.warn { background: var(--error-color); border-radius: 5px; }
      /* The group chip stays hollow so it reads as a link between rows and
         not as another filled label like the category one. */
      .chip.group { background: transparent; color: var(--primary-color);
                    border: 1px solid var(--primary-color); padding: 1px 6px;
                    display: inline-flex; align-items: center; gap: 3px; }
      .chip-icon { width: 14px; height: 14px; --mdc-icon-size: 14px; flex: 0 0 auto; }

      /* Agenda category filter chips, inline next to "Oggi". */
      .fchip {
        display: inline-flex; align-items: center; gap: 4px;
        padding: 5px 10px; border-radius: 999px; cursor: pointer;
        border: 1px solid var(--divider-color); background: transparent;
        color: var(--secondary-text-color); font: inherit; font-size: 12px;
        white-space: nowrap;
      }
      .fchip.active { background: var(--primary-color); border-color: var(--primary-color);
                      color: var(--text-primary-color, #fff); }
      .fchip ha-icon { --mdc-icon-size: 14px; }

      .swatch { display: inline-block; width: 12px; height: 12px; border-radius: 3px;
                border: 1px solid var(--divider-color); vertical-align: -1px; }
      .field input[type="color"] { height: 32px; width: 56px; padding: 2px; border: 1px solid
                var(--divider-color); border-radius: 4px; background: var(--card-background-color); }

      .preview { padding: 10px 12px; border-radius: 8px;
                 background: var(--secondary-background-color); display: flex;
                 flex-direction: column; gap: 4px; }
      .preview-time { display: flex; align-items: center; gap: 6px; }
      .preview-time ha-icon { --mdc-icon-size: 18px; color: var(--primary-color); }

      .selected-client { display: flex; align-items: center; gap: 10px; padding: 8px 10px;
                         border-radius: 8px; background: rgba(76, 175, 80, .12); }
      .selected-client ha-icon { --mdc-icon-size: 20px; color: var(--success-color, #4caf50); }
      .sc-body { flex: 1 1 auto; min-width: 0; }
      .results { display: flex; flex-direction: column; border: 1px solid var(--divider-color);
                 border-radius: 8px; overflow: hidden; max-height: 220px; overflow-y: auto; }
      .result { display: flex; justify-content: space-between; gap: 8px; padding: 9px 10px;
                border: none; background: transparent; color: var(--primary-text-color);
                cursor: pointer; font: inherit; font-size: 13px; text-align: left; }
      .result:hover { background: var(--secondary-background-color); }

      .chip.danger { background: var(--error-color); }
      .chip.ok { background: var(--success-color, #4caf50); }

      /* Check-out panel above today's agenda. */
      .exit-panel { border: 1px solid var(--divider-color); border-radius: 10px;
                    padding: 10px; background: var(--secondary-background-color); }
      .exit-head { display: flex; align-items: center; gap: 8px; font-weight: 500; }
      .exit-head ha-icon { --mdc-icon-size: 18px; color: var(--primary-color); }
      .exit-row { display: flex; align-items: center; gap: 8px; padding: 6px 0; }
      .exit-row + .exit-row { border-top: 1px solid var(--divider-color); }
      .exit-time { font-variant-numeric: tabular-nums; font-weight: 500;
                   color: var(--primary-color); }

      /* Weekday toggles in the category editor. */
      .days-grid { display: flex; gap: 4px; flex-wrap: wrap; }
      .days-grid .check { font-size: 12px; padding: 4px 10px; border: 1px solid
                           var(--divider-color); border-radius: 999px; }

      .bk-row { border: 1px solid var(--divider-color); border-radius: 10px; padding: 12px; }
      .bk-row + .bk-row { margin-top: 10px; }
      /* Category boxes in voucher form. */
      .cat-box { border: 1px solid var(--divider-color); border-radius: 10px; padding: 10px 12px;
                 margin-top: 8px; background: var(--secondary-background-color); }
      .cat-header { margin: 0 0 8px; font-size: 12px; font-weight: 600; color: var(--primary-color);
                    text-transform: uppercase; letter-spacing: .04em; }

      /* Treatments, two columns grouped by category. Falls back to one column
         on a narrow screen so the rows keep a readable width. */
      .trt-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr));
                  gap: 10px; align-items: start; }
      .trt-group { border: 1px solid var(--divider-color); border-radius: 10px;
                   padding: 4px 10px 6px; min-width: 0; }
      .trt-group-head { display: flex; align-items: center; gap: 8px; font-size: 12px;
                        font-weight: 600; text-transform: uppercase;
                        letter-spacing: .05em; color: var(--secondary-text-color);
                        padding: 6px 0 2px; }
      .trt-group .row.item:last-child { border-bottom: none; }
      /* Accessori (Configurazione): the same rows, without the category block. */
      .acc-list > .row.item { gap: 8px; }
      .acc-list > .row.item:last-of-type { border-bottom: none; }
      .acc-list.editing > .row.item { cursor: pointer; }
      .acc-list > .acc-add { align-self: flex-start; margin-top: 8px; }
      /* Drag handles and highlights in edit mode (Trattamenti and Operatori). */
      .trt-drag { cursor: grab; color: var(--secondary-text-color); --mdc-icon-size: 18px;
                  flex: 0 0 auto; opacity: .6; }
      .trt-drag:active { cursor: grabbing; }
      .trt-group.dragging, .trt-item.dragging { opacity: .6; outline: 2px dashed var(--primary-color); }
      .trt-group.drag-over, .trt-item.drag-over { outline: 2px solid var(--primary-color);
                                                   outline-offset: -2px; border-radius: 6px; }
      [draggable] { user-select: none; }
      [draggable] input, [draggable] textarea, [draggable] select,
      [draggable] .search-hit, [draggable] button.search-hit {
        user-select: text; -webkit-user-select: text;
        pointer-events: auto; touch-action: manipulation;
      }
      .op-drag-item { cursor: grab; }
      .op-drag-item.dragging { opacity: .6; }
      .op-drag-item.drag-over, .operators-column.drag-over { outline: 2px solid var(--primary-color); outline-offset: -2px; }
      /* Checkbox grid: operators enabled for a treatment. Two columns, one on phone. */
      .checks-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 4px 12px; }
      .checks-grid .check { font-size: 13px; }
      @media (max-width: 720px) {
        .checks-grid { grid-template-columns: minmax(0, 1fr); }
      }
      @media (max-width: 720px) {
        .trt-grid { grid-template-columns: minmax(0, 1fr); }
      }
      .bk-person { border: 1px solid var(--divider-color); border-radius: 8px;
                   padding: 10px; margin-top: 10px; background: var(--secondary-background-color); }
      .bk-person-head { display: flex; align-items: center; gap: 8px; font-size: 12px;
                        font-weight: 500; margin-bottom: 8px; color: var(--secondary-text-color); }
      /* One treatment of a person: label, picker and clock on the same line,
         so "Trattamento 1/2/…" keeps its own time right next to it. */
      .bk-treat { display: flex; align-items: center; gap: 6px; flex-wrap: wrap; }
      .bk-treat-label { flex: 0 0 auto; font-size: 12px; font-weight: 600; min-width: 92px;
                        color: var(--secondary-text-color); white-space: nowrap; }
      .bk-treat select.input { flex: 1 1 auto; min-width: 150px; }
      .bk-treat .time-row { flex: 0 0 auto; }
      .bk-treat .time-row select.input { min-width: 46px; }
      .bk-treat-x { flex: 0 0 auto; }
      .bk-treat-block { margin-top: 8px; }
      .bk-treat-block + .bk-treat-block { margin-top: 12px; padding-top: 10px;
                                          border-top: 1px dashed var(--divider-color); }
      .bk-treat-sub { margin-top: 8px; }
      .add-treat-btn { align-self: flex-start; white-space: nowrap; margin-top: 10px; }
      @media (max-width: 720px) {
        .bk-treat { gap: 4px; }
        .bk-treat-label { min-width: 0; width: 100%; }
        .bk-treat select.input { min-width: 120px; }
      }
      .bk-add { display: flex; gap: 8px; justify-content: flex-end; }
      .block-row { border: 1px solid var(--divider-color); border-radius: 8px; padding: 8px 10px; }

      .cal { display: grid; grid-template-columns: repeat(7, 1fr); gap: 4px; }
      .cal-dow { text-align: center; font-size: 11px; color: var(--secondary-text-color); padding-bottom: 2px; }
      .cal-day { position: relative; aspect-ratio: 1 / 1; min-height: 34px; border: 1px solid transparent;
                 border-radius: 8px; background: var(--secondary-background-color); cursor: pointer;
                 display: flex; align-items: center; justify-content: center; font: inherit;
                 color: var(--primary-text-color); padding: 0; }
      .cal-day.dim { opacity: .35; }
      .cal-day.today { border-color: var(--primary-color); font-weight: 600; }
      .cal-day.sel { outline: 2px solid var(--primary-color); }
      .cal-day.has { background: var(--primary-color); color: var(--text-primary-color, #fff); }
      /* A shut facility is hatched, and the hatch deliberately beats the blue
         "has appointments" fill: being closed matters more than being booked,
         so the number goes back to the normal text colour. A category or an
         operator closure only takes that part of the offer, so it gets a quiet
         bar along the bottom instead. */
      .cal-day.closed { background-image: repeating-linear-gradient(135deg,
                     transparent 0 4px, var(--error-color) 4px 6px);
                     background-color: transparent; color: var(--primary-text-color); }
      .cal-day.closed-soft { box-shadow: inset 0 -3px 0 var(--warning-color, #ff9800); }
      .cal-lock { position: absolute; bottom: 2px; left: 3px; display: inline-flex; }
      .cal-lock ha-icon { --mdc-icon-size: 13px; width: 13px; height: 13px;
                           color: var(--primary-text-color); }
      .cal-day.closed-soft .cal-lock ha-icon { color: var(--warning-color, #ff9800); }
      /* The lock list under the calendar uses the same two weights. */
      .item > ha-icon.soft { --mdc-icon-size: 18px; color: var(--warning-color, #ff9800); }
      .cal-num { font-size: 13px; }
      .cal-count { position: absolute; top: 2px; right: 4px; font-size: 10px; font-weight: 700; }
      /* The month on the left, its appointments on the right. The right column
         keeps a bounded height so the grid beside it stays whole. */
      .cal-layout { display: grid; grid-template-columns: minmax(0, 1fr) minmax(240px, 340px);
                    gap: 18px; align-items: start; }
      .month-side { position: sticky; top: 0; }
      .month-list { max-height: 520px; overflow-y: auto;
                    border-top: 1px solid var(--divider-color); }
      .month-day { border-bottom: 1px solid var(--divider-color); }
      .month-day-head { display: flex; align-items: center; gap: 8px; width: 100%;
                        padding: 7px 4px; border: none; background: transparent;
                        color: var(--primary-text-color); font: inherit; font-size: 13px;
                        font-weight: 500; text-align: left; cursor: pointer; }
      .month-day-head:hover { background: var(--secondary-background-color); }
      .month-day.today .month-day-head { color: var(--primary-color); }
      .month-day-head .badge { margin-left: auto; }
      .month-row { display: flex; align-items: baseline; gap: 8px; padding: 4px 4px 7px; }
      .month-time { font-variant-numeric: tabular-nums; font-size: 12px;
                    color: var(--secondary-text-color); white-space: nowrap;
                    min-width: 42px; }
      .month-body { min-width: 0; }
      .month-client { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
      .month-op { white-space: nowrap; flex: 0 0 auto; max-width: 34%;
                  overflow: hidden; text-overflow: ellipsis; }
      @media (max-width: 900px) {
        .cal-layout { grid-template-columns: minmax(0, 1fr); }
        .month-side { position: static; }
      }

      .client-row { display: flex; align-items: center; gap: 6px;
                    border-bottom: 1px solid var(--divider-color); padding: 4px 0; }
      .client-main { flex: 1 1 auto; min-width: 0; text-align: left; border: none; cursor: pointer;
                     background: transparent; color: var(--primary-text-color); font: inherit;
                     padding: 8px 0; }
      .client-main:hover .client-name { color: var(--primary-color); }
      .client-name { font-weight: 500; }
      /* A guest who asked not to receive promos: a small crossed bell next to
         the name, so the desk sees at a glance who is left out of a send. */
      .promo-off { margin-left: 6px; color: var(--secondary-text-color);
                   vertical-align: middle; }
      .promo-off ha-icon { --mdc-icon-size: 16px; vertical-align: middle; }
      /* "Iscritto alle promo" checkbox on the client form, with its hint. */
      .promo-choice { display: flex; flex-direction: column; gap: 2px; }

      .cancelled-box summary, .exited-box summary {
        cursor: pointer; font-size: 13px; color: var(--secondary-text-color);
      }

      /* Telecamere: one snapshot tile per camera in the tab, and the editable
         entity list in Impostazioni. */
      .cameras { display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
                 gap: 12px; align-items: start; }
      .camera-tile { position: relative; border: 1px solid var(--divider-color);
                     border-radius: 10px; overflow: hidden;
                     background: var(--card-background-color); }
      .camera-tile.editing { cursor: grab; }
      .camera-tile.dragging { opacity: .75; outline: 2px dashed var(--primary-color);
                              cursor: grabbing; z-index: 5; }
      .camera-caption { position: absolute; left: 0; right: 0; bottom: 0;
                        display: flex; align-items: center; gap: 6px;
                        padding: 12px 9px 6px;
                        background: linear-gradient(transparent, rgba(0, 0, 0, .6));
                        color: #fff; font-size: 12px; pointer-events: none; }
      .camera-icon { --mdc-icon-size: 14px; color: rgba(255, 255, 255, .85); }
      .camera-name { flex: 1 1 auto; min-width: 0; font-weight: 500;
                     white-space: normal; overflow-wrap: anywhere;
                     text-shadow: 0 1px 2px rgba(0, 0, 0, .6); }
      .camera-sub { margin-left: auto; font-size: 11px; white-space: nowrap;
                    padding: 2px 7px; border-radius: 10px;
                    background: rgba(0, 0, 0, .45);
                    text-shadow: 0 1px 2px rgba(0, 0, 0, .6); }
      .camera-frame { position: relative; aspect-ratio: 16 / 9; background: #000; }
      .camera-frame img.camera-img { position: absolute; inset: 0; width: 100%; height: 100%;
                                     object-fit: contain; transition: opacity .2s; opacity: 0; }
      .camera-frame img.camera-img.loaded { opacity: 1; }
      .camera-off { position: absolute; inset: 0; display: flex; flex-direction: column;
                    align-items: center; justify-content: center; gap: 6px;
                    color: var(--disabled-text-color); font-size: 12px; }
      .camera-off ha-icon { --mdc-icon-size: 32px; }
      @media (max-width: 720px) {
        .cameras { grid-template-columns: minmax(0, 1fr); }
      }

      /* Spa tab: mushroom-like control tiles, the single top-right «…» menu,
         the in-place edit mode (⋮ per tile, drag to reorder) and the
         per-entity popup. */
      .spa-head { position: relative; display: flex; align-items: center; gap: 8px;
                  margin: 0 0 10px; }
      .spa-head-title { display: flex; align-items: center; gap: 8px;
                        font-size: 17px; font-weight: 600; }
      .spa-head-title ha-icon { --mdc-icon-size: 22px; color: var(--primary-color); }
      .spa-menu-btn { margin-left: auto; }
      .spa-menu-btn.active { background: rgba(var(--rgb-primary-color, 77, 87, 240), .15);
                             color: var(--primary-color); }
      .spa-head-pop { position: absolute; top: 38px; right: 0; }
      .spa-chips { display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 12px; }
      .spa-chip { display: inline-flex; align-items: center; gap: 5px;
                  padding: 7px 12px; border: 1px solid var(--divider-color);
                  border-radius: 999px; background: transparent; cursor: pointer;
                  font: inherit; font-size: 13px; color: var(--secondary-text-color); }
      .spa-chip:hover { background: var(--secondary-background-color); }
      .spa-chip.on { background: rgba(var(--rgb-primary-color, 77, 87, 240), .15);
                     border-color: var(--primary-color); color: var(--primary-color);
                     font-weight: 600; }
      .spa-grid { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr));
                  gap: 12px; align-items: stretch; }
      .spa-tile { position: relative; display: flex; flex-direction: row; align-items: center;
                  gap: 8px 12px; padding: 12px 14px; border: 1px solid var(--divider-color);
                  border-radius: 12px; background: var(--card-background-color); cursor: pointer;
                  transition: box-shadow .15s; text-align: left; }
      .spa-tile .spa-tile-icon { --mdc-icon-size: 30px; flex-shrink: 0; }
      .spa-tile .spa-tile-main { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 2px; }
      .spa-tile .spa-tile-name { font-weight: 500; font-size: 13px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
      .spa-tile .spa-tile-sub { font-size: 12px; opacity: 0.9; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
      .spa-tile:hover { box-shadow: 0 2px 10px rgba(0, 0, 0, .12); }
      .spa-tile.editing { cursor: grab; }
      .spa-tile.dragging { opacity: .75; outline: 2px dashed var(--primary-color);
                            cursor: grabbing; z-index: 5; }
      /* yellow più soft per le tile accese */
      .spa-tile.on { background: linear-gradient(180deg, var(--card-background-color, #ffffff) 0%, #fff59d 200%) !important; border-color: #f9e79f !important; }
      .spa-tile.on .spa-tile-icon { color: #b7950b !important; }
      .spa-tile.on .spa-tile-icon ha-icon { color: #b7950b !important; }
      .spa-tile.on .spa-tile-name { color: #1a202c !important; font-weight: 700; }
      .spa-tile.on .spa-tile-sub { color: #1a202c !important; }
      .spa-tile-bright-row { display: flex; align-items: center; gap: 6px; width: 100%; margin-top: 4px; padding: 0 2px; box-sizing: border-box; overflow: hidden; }
      .spa-tile-bright-row input[type=range] { flex: 1; min-width: 0; height: 12px; cursor: pointer; accent-color: var(--primary-color, #009ac7); }
      .spa-tile-bright-row .spa-tile-brightness-value { display: none; font-size: 11px; min-width: 34px; text-align: right; white-space: nowrap; }
      .spa-tile-bright-row .spa-tile-brightness-value.show { display: inline; }
      /* termostato: bordo/icone riscaldamento/arancio; raffreddamento/azzurro */
      .spa-tile--climate.heating { border-color: #ed8936 !important; }
      .spa-tile--climate.heating .spa-tile-icon,
      .spa-tile--climate.heating .spa-tile-icon ha-icon { color: #ed8936 !important; }
      .spa-tile--climate.heating .btn ha-icon { color: #ed8936 !important; }
      .spa-tile--climate.cooling { border-color: #3182ce !important; }
      .spa-tile--climate.cooling .spa-tile-icon,
      .spa-tile--climate.cooling .spa-tile-icon ha-icon { color: #3182ce !important; }
      .spa-tile--climate.cooling .btn ha-icon { color: #3182ce !important; }
      /* Phase 2: card types (visual variants) */
      /* Phase 2 stronger visuals */
      .spa-tile--button { justify-content: center; min-height: 74px; background: var(--secondary-background-color, #f1f3f5); }
      .spa-tile--button .spa-tile-icon { --mdc-icon-size: 34px; }
      .spa-tile--button .spa-tile-name { font-weight: 700; font-size: 13px; margin-top: 4px; }
      .spa-tile--switch { cursor: pointer; background: linear-gradient(180deg, var(--card-background-color) 0%, var(--primary-color) 200%); }
      .spa-tile--switch .spa-tile-icon { color: var(--primary-color); }
      .spa-tile--switch.on { background: linear-gradient(180deg, var(--card-background-color, #ffffff) 0%, #fff59d 200%) !important; }
      .spa-tile--switch.on .spa-tile-icon { color: #b7950b !important; }
      .spa-tile--climate { border: 2px solid var(--primary-color); padding-bottom: 10px; background: var(--card-background-color); }
      .spa-tile--climate .spa-tile-sub { font-size: 12px; font-weight: 500; }
      .spa-tile--sensor .spa-tile-name { font-size: 11px; color: var(--secondary-text-color); }
      .spa-tile--sensor .spa-tile-sub { font-size: 20px; font-weight: 700; }
      .spa-tile--gauge { padding-bottom: 8px; }
      .spa-tile--gauge .spa-tile-gauge { width: 100%; height: 8px; border-radius: 4px; accent-color: var(--primary-color); }
      .spa-tile--entity { text-align: left; align-items: flex-start; background: var(--secondary-background-color, #f1f3f5); }
      .spa-tile--thermostat .spa-tile-sub { font-size: 14px; }
      .spa-tile--thermostat .spa-tile-main { width: 100%; }
      .spa-tile--tile .spa-tile-icon { --mdc-icon-size: 20px; }
      .spa-tile-menu { position: absolute; top: 4px; right: 4px; z-index: 3;
                        width: 30px; height: 30px; padding: 0;
                        background: var(--card-background-color);
                        border: 1px solid var(--divider-color); }
      .spa-tile-menu:hover { border-color: var(--primary-color);
                             color: var(--primary-color); }
      .spa-add-tile { display: flex; flex-direction: column; align-items: center;
                       justify-content: center; gap: 6px; min-height: 64px; padding: 12px;
                       border: 1px dashed var(--divider-color); border-radius: 14px;
                       background: transparent; color: var(--secondary-text-color);
                       cursor: pointer; font: inherit; font-size: 13px; }
      .spa-add-tile:hover { border-color: var(--primary-color);
                            color: var(--primary-color); }
      .spa-add-tile ha-icon { --mdc-icon-size: 26px; }

      .spa-popover { position: absolute; top: 46px; right: 8px; z-index: 30;
                     background: var(--card-background-color); border: 1px solid var(--divider-color);
                     border-radius: 10px; box-shadow: 0 6px 20px rgba(0, 0, 0, .25);
                     padding: 4px; display: flex; flex-direction: column; min-width: 150px; }
      .spa-pop-item { display: flex; align-items: center; gap: 8px; padding: 8px 10px;
                      border: none; background: transparent; cursor: pointer; border-radius: 8px;
                      font: inherit; font-size: 13px; color: var(--primary-text-color);
                      text-align: left; }
      .spa-pop-item:hover { background: rgba(var(--rgb-primary-color, 77, 87, 240), .1); }
      .spa-pop-item.danger { color: var(--error-color, #e53953); }
      .spa-pop-item.danger:hover { background: rgba(229, 57, 83, .1); }
      .spa-pop-item ha-icon { --mdc-icon-size: 18px; }
      .spa-edit-sheet input[type="text"] {
        width: 100%; padding: 9px 10px; border-radius: 8px; box-sizing: border-box;
        border: 1px solid var(--divider-color); background: transparent;
        color: var(--primary-text-color); font: inherit; font-size: 14px;
      }
      .btn.small { padding: 6px 10px; font-size: 12px; }
      .btn.danger { color: var(--error-color, #e53953); }
      .spa-head-actions { display: flex; align-items: center; gap: 6px; margin-left: auto; }
      .spa-head-actions .btn { display: inline-flex; align-items: center; gap: 4px; }
      .spa-toggle { display: flex; align-items: center; gap: 10px; padding: 6px 0; }
      .spa-toggle span { flex: 1 1 auto; }
      @media (max-width: 720px) {
        .spa-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
        .spa-head { margin-bottom: 8px; }
        .spa-head-title { font-size: 16px; }
        .spa-tile { padding: 13px 12px; gap: 4px 10px; }
        .spa-tile-icon { width: 40px; height: 40px; }
        .spa-tile-icon ha-icon { --mdc-icon-size: 22px; }
        .spa-tile-name { font-size: 15px; }
        .spa-tile-sub { font-size: 12px; }
        .spa-menu-btn { width: 40px; height: 40px; }
        .spa-chip { padding: 9px 14px; font-size: 14px; }
      }
    `);
  }
}

if (!customElements.get("spa-booking-card")) {
  customElements.define("spa-booking-card", SpaBookingCard);
}

window.customCards = window.customCards || [];
if (!window.customCards.find((card) => card.type === "spa-booking-card")) {
  window.customCards.push({
    type: "spa-booking-card",
    name: "Gestione SPA",
    description: "Agenda, creazione appuntamenti, calendario, schede clienti, telecamere e configurazione.",
    preview: false,
    documentationURL: "https://github.com/home-assistant/core",
  });
}

// eslint-disable-next-line no-console
console.info(`spa-booking-card ${CARD_VERSION} registrata`);


// Run: node tests/frontend/card_login_test.js custom_components/spa_booking/frontend/spa-booking-card.js
// 2.2: international prefix, roles and own appointments, PIN screen, vouchers.
"use strict";
const { loadCard, assert, all, byClass, sandbox } = require("./card_harness");

const Card = loadCard(process.argv[2]);
const { splitPhone, joinPhone, phoneInput } = sandbox;

// --- phone numbers -------------------------------------------------------
const sp = (v) => { const r = splitPhone(v); return `${r.cc}|${r.number}`; };
assert(sp("") === "39|", "empty opens as +39");
assert(sp("333 1234567") === "39|3331234567", "old Italian mobile opens as +39");
assert(sp("392 1234567") === "39|3921234567", "TIM 392 stays Italian, not +39 21...");
assert(sp("393921234567") === "39|3921234567", "39 + Italian number");
assert(sp("0925 992446") === "39|0925992446", "landline keeps its 0");
assert(sp("+41 79 123 4567") === "41|791234567", "Swiss number");
assert(sp("0049 151 2345678") === "49|1512345678", "00 prefix");
assert(sp("+1809 555 1234") === "1809|5551234", "longest code wins");
assert(joinPhone("41", "79 123 4567") === "+41 79 123 4567", "stored as +CC number");
assert(joinPhone("39", "  ") === "", "no number, nothing stored");
let value = null;
const field = phoneInput("+41 79 123 4567", (v) => { value = v; });
const select = all(field).find((n) => n.tagName === "SELECT");
const input = all(field).find((n) => n.tagName === "INPUT");
assert(all(select).some((n) => n.tagName === "OPTION" && n.selected && n.value === "41"), "prefix select on +41");
assert(input.value === "791234567", "number without the prefix");
select.listeners.change[0]({ target: { value: "49" } });
assert(value === "+49 791234567", "changing the prefix keeps the number");
input.listeners.input[0]({ target: { value: "+43 664 1234567" } });
assert(value === "+43 6641234567", "a typed +43 moves into the prefix");

// --- roles ---------------------------------------------------------------
function makeCard(me) {
  const card = Object.create(Card.prototype);
  card._me = me;
  card._hass = { user: { id: me.user_id, name: me.name } };
  card._data = { settings: {}, appointments: [], operators: [], vouchers: [], treatments: [], categories: [], clients: [] };
  card._lookup = { treatment: new Map(), client: new Map(), operator: new Map() };
  card._render = () => {};
  return card;
}
const giulia = makeCard({ user_id: "u_g", name: "Giulia", level: "therapist", operator_id: "op_g" });
assert(giulia._can("book") && !giulia._can("payments") && !giulia._can("create_voucher"), "masseuse books, no payments, no vouchers");
assert(giulia._ownsAppointment({ operator_id: "op_g" }) && !giulia._ownsAppointment({ operator_id: "op_m" }), "masseuse edits only her own");
assert(giulia._visibleTabs().map((t) => t.id).join() === "agenda,nuovo,spa", "masseuse tabs");
assert((giulia._uid = () => "x", giulia._blankTreatment().operator_id) === "op_g", "her own operator preselected");
const laura = makeCard({ user_id: "u_l", name: "Laura", level: "operator", operator_id: "" });
assert(laura._can("payments") && laura._can("create_voucher") && !laura._can("totals") && !laura._can("manage_clients"), "reception rights");
assert(laura._ownsAppointment({ operator_id: "op_m" }), "reception edits everybody");
const marco = makeCard({ user_id: "u_m", name: "Marco", level: "manager" });
assert(marco._can("totals") && marco._can("manage_clients") && !marco._can("config"), "manager rights");

// --- PIN screen ----------------------------------------------------------
const tablet = makeCard({ user_id: null, name: "", level: "none", shared: true,
  people: [{ user_id: "u_l", name: "Laura", level: "operator" }, { user_id: "u_g", name: "Giulia", level: "therapist" }] });
assert(tablet._pinNeeded(), "shared tablet without a PIN asks for one");
let screen = tablet._renderPinScreen();
assert(byClass(screen, "pin-person").length === 2, "one face per person");
assert(byClass(screen, "pin-key").length === 0, "keypad after choosing");
tablet._pinPerson = "u_l";
let sent = null;
tablet._service = async (service, data) => { sent = [service, data]; throw new Error("PIN sbagliato"); };
tablet._friendlyError = (e) => e.message;
screen = tablet._renderPinScreen();
const keys = byClass(screen, "pin-key");
assert(keys.length === 11, "keypad with 10 digits and delete");
["1", "2", "3", "4"].forEach((d) => {
  const key = byClass(tablet._renderPinScreen(), "pin-key").find((k) => k.attrs["aria-label"] === d);
  key.listeners.click[0]();
});
setTimeout(() => {
  assert(sent && sent[0] === "pin_login" && sent[1].pin === "1234" && sent[1].user_id === "u_l", "four digits send the PIN");
  assert(tablet._pinError === "PIN sbagliato" && tablet._pinTyped === "", "wrong PIN clears the dots");

  // --- vouchers ----------------------------------------------------------
  const today = new Date();
  const ymd = (d) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
  const plus = (n) => { const d = new Date(today); d.setDate(d.getDate() + n); return ymd(d); };
  assert(laura._voucherState({ status: "active", expires_on: plus(90) }) === "attivo", "active voucher");
  assert(laura._voucherState({ status: "active", expires_on: plus(10) }) === "scadenza", "expiring within 30 days");
  assert(laura._voucherState({ status: "active", expires_on: plus(-3) }) === "scaduto", "expired by date alone");
  assert(laura._voucherState({ status: "redeemed", expires_on: plus(-3) }) === "riscattato", "redeemed wins");
  const draft = laura._voucherDraftState();
  assert(laura._voucherStepProblem(draft, 1) !== "", "empty first step refused");
  const who = laura._voucherStepWho(draft);
  assert(who.textContent.includes("PIN"), "the who step says the voucher is signed with the PIN");
  draft.buyer_name = "Marco";
  assert(laura._voucherStepProblem(draft, 1) === "", "first step ok");
  assert(laura._voucherStepProblem(draft, 2) !== "", "a person needs a treatment or gift card");
  draft.people[0].gift_card_amount = 50;
  assert(laura._voucherStepProblem(draft, 3) === "", "summary ok");
  // 2.3.0: Crea voucher opens the PIN pad; four digits send the voucher with the PIN.
  const sentVoucher = [];
  laura._voucherDraft = draft;
  laura._service = async (name, data) => { sentVoucher.push([name, data]); return { voucher: { id: "v1", code: "VCH-1", created_by_name: "Laura" } }; };
  laura._loadData = async () => {};
  laura._createVoucher();
  assert(laura._voucherPin && laura._voucherPin.typed === "", "PIN pad opened");
  laura._submitVoucher("1234").then(() => {
    assert(sentVoucher[0][0] === "create_voucher" && sentVoucher[0][1].pin === "1234", "voucher sent with the PIN");
    assert(!("created_by" in sentVoucher[0][1]), "no free-text signature any more");
    assert(laura._voucherPin === null && laura._voucherCreated === "v1", "pad closed, voucher shown");
    console.log("VOUCHER PIN TEST PASSED");
  }).catch((error) => { console.error(error); process.exit(1); });
  const v = { code: "VCH-ABC", recipient_name: "Giulia Verdi", buyer_name: "Marco", expires_on: "2027-05-10",
    people: [{ name: "", treatment_ids: [], extras: [], gift_card_amount: 50 }] };
  laura._dateIt = (d) => d;
  laura._accessoryLabel = (id) => id;
  const msg = laura._voucherMessage(v, false);
  assert(msg.startsWith("Ciao Giulia,") && msg.includes("*VCH-ABC*") && msg.includes("2027-05-10"), "WhatsApp text of the voucher");
  console.log("ALL CARD LOGIN TESTS PASSED");
}, 50);

// --- category rules: the warning that can be forced ------------------------
{
  const card = makeCard({ user_id: "u_l", name: "Laura", level: "operator" });
  assert(card._isCategoryRule("La categoria 'Privata' accetta prenotazioni di mattina solo Lun, Mar, Mer, Gio, Ven"), "day rule recognised");
  assert(card._isCategoryRule("La categoria 'Massaggi' accetta appuntamenti solo nelle fasce 09:00-13:00"), "time window recognised");
  assert(card._isCategoryRule("La categoria 'Spa' non può sovrapporsi a 'Massaggi': ..."), "exclusion recognised");
  assert(!card._isCategoryRule("L'appuntamento si sovrappone a quello di cliente Anna"), "an overlap is not a category rule");
  card._overlapPopup = { kind: "rules", message: "La categoria 'Privata' accetta prenotazioni di mattina solo Lun" };
  const pop = card._renderOverlapPopup();
  assert(pop.textContent.includes("Prenota comunque") && pop.textContent.includes("Annulla e modifica"), "reception may book anyway");
  const masseuse = makeCard({ user_id: "u_g", name: "Giulia", level: "therapist", operator_id: "op_g" });
  masseuse._overlapPopup = card._overlapPopup;
  assert(!masseuse._renderOverlapPopup().textContent.includes("Prenota comunque"), "a masseuse cannot force it");
}

// --- updates banner ----------------------------------------------------------
{
  const admin = makeCard({ user_id: "u_s", name: "Stefano", level: "admin" });
  admin._hass.states = {};
  assert(admin._updateBanner() === null, "no status, no banner");
  admin._updateStatus = { running_version: "2.2.0b4", disk_version: "2.2.0b4", restart_needed: false, reload_only: false,
    update: { entity_id: "update.spa_booking_update", available: true, latest_version: "v2.2.0", release_url: "https://x" } };
  let banner = admin._updateBanner();
  assert(banner.textContent.includes("v2.2.0") && banner.textContent.includes("Installa"), "new version: Installa");
  admin._updateStatus = { running_version: "2.2.0b4", disk_version: "2.2.0", restart_needed: true, reload_only: false, update: null };
  banner = admin._updateBanner();
  assert(banner.textContent.includes("Riavvia ora") && !banner.textContent.includes("Installa"), "code changed: restart");
  admin._updateStatus = { running_version: "2.2.0b4", disk_version: "2.2.0b5", restart_needed: false, reload_only: true, update: null };
  assert(admin._updateBanner().textContent.includes("Ricarica la pagina"), "card only: reload");
  const reception = makeCard({ user_id: "u_l", name: "Laura", level: "operator" });
  reception._updateStatus = admin._updateStatus;
  assert(reception._updateBanner() === null, "only the administrator sees updates");
}

// --- «Proponi data» on a request -----------------------------------------------
{
  const card = makeCard({ user_id: "u_l", name: "Laura", level: "operator" });
  const calls = [];
  card._service = async (service, data) => { calls.push([service, data]); return { text: "Gentile Elena, la prima data disponibile è domenica 15 novembre alle 10:00." }; };
  card._friendlyError = (e, d) => d;
  const req = { id: "req1", code: "R1", date: "2030-03-09", client: { first_name: "Elena" },
    entries: [{ start: "10:00", treatment_name: "Massaggio" }], is_confirmed: false };
  card._openProposePopup(req);
  assert(card._proposePopup.date === "2030-03-10", "proposes the day after the one asked for");
  assert(card._proposePopup.time === "10:00", "keeps the hour asked for");
  setTimeout(() => {
    assert(calls[0][0] === "propose_request_date" && calls[0][1].dry_run === true, "the preview sends nothing");
    assert(card._proposePopup.text.includes("domenica 15 novembre"), "text from the notifications tab");
    const sheet = card._renderProposePopup();
    assert(sheet.textContent.includes("Invia su WhatsApp") && sheet.textContent.includes("Prima data disponibile"), "popup with date and send");
    console.log("ALL PROPOSE TESTS PASSED");
  }, 20);
}

// Run: node tests/frontend/card_nuovo_test.js custom_components/spa_booking/frontend/spa-booking-card.js
// 2.3.10: Nuovo appuntamento in five steps, operator chips, live summary.
"use strict";
const { loadCard, assert, all, byClass } = require("./card_harness");

const Card = loadCard(process.argv[2]);
const card = Object.create(Card.prototype);
card._me = { level: "admin" };
card._hass = { user: { id: "u", name: "Stefano" } };
const treatment = { id: "t1", name: "Massaggio schiena", duration_min: 50, price: 60, active: true, category_id: "" };
const today = new Date();
const day = `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, "0")}-${String(today.getDate()).padStart(2, "0")}`;
card._data = {
  settings: {}, vouchers: [], categories: [], clients: [], treatments: [treatment],
  operators: [
    { id: "o1", name: "Maria", gender: "F", active: true, treatment_ids: ["t1"], priority: 1 },
    { id: "o2", name: "Marco", gender: "M", active: true, treatment_ids: ["t1"], priority: 2 },
  ],
  appointments: [{ id: "a1", operator_id: "o2", treatment_id: "t1", client_id: "c9", status: "confirmed",
    start: `${day}T10:00:00`, end: `${day}T10:50:00` }],
};
card._render = () => {};
card._can = () => true;
card._buildLookups && card._buildLookups();
card._lookup = card._lookup || {};
card._lookup.treatment = new Map([["t1", treatment]]);
card._lookup.operator = new Map(card._data.operators.map((o) => [o.id, o]));
card._lookup.client = new Map();
card._lookup.category = new Map();
card._byDay = new Map([[day, card._data.appointments]]);
card._resetForm();
card._form.date = day;
const treat = card._treatmentsOf(card._form)[0];
treat.treatment_id = "t1";
treat.time = "10:00";
card._form.first_name = "Anna";
card._form.last_name = "Bianchi";

const page = card._renderNuovoForm();
const text = page.textContent;
assert(byClass(page, "pg-num").length === 5, "five numbered steps");
["Quando e quante persone", "Trattamenti", "Cliente", "Prezzo e pagamento", "Stato e note"].forEach((title) =>
  assert(text.includes(title), `step «${title}»`));
const chips = byClass(page, "nv-chip").map((n) => n.textContent);
assert(chips.join("|") === "Automatica|Massaggiatrice|Massaggiatore|Maria|Marco", "operator chips in order");
assert(byClass(page, "nv-dot busy").length === 1 && byClass(page, "nv-dot free").length === 1, "Marco busy at 10:00, Maria free");
const side = byClass(page, "nv-side")[0];
assert(side.textContent.includes("Anna Bianchi") && side.textContent.includes("10:00–10:50"), "summary with client and time");
assert(side.textContent.includes("Crea appuntamento"), "create in the summary");
assert(byClass(page, "nv-bar")[0].textContent.includes("Crea"), "phone bar with create");
// Picking Maria from the chips.
const maria = all(page).find((n) => n.attrs && n.attrs.class && n.attrs.class.startsWith("nv-chip") && n.textContent === "Maria");
maria.listeners.click[0]();
assert(treat.operator_id === "o1", "chip sets the operator");

// «Una scheda cliente per ogni persona» is off unless ticked.
card._resetForm();
assert(card._form.new_client === false, "per-person client cards off by default");
// The request form: same steps, no operator chips, «Salva richiesta».
card._form.date = day;
card._treatmentsOf(card._form)[0].treatment_id = "t1";
const request = card._renderRichiestaForm();
assert(byClass(request, "pg-num").length === 4, "four steps in the request form");
assert(byClass(request, "nv-chip").length === 0, "no masseuse for a request");
assert(byClass(request, "nv-side")[0].textContent.includes("Salva richiesta"), "save in the summary");

// 2.5.1: VAT in the summary, «di cui IVA».
card._data.settings.vat_default = 22;
card._resetForm();
card._form.date = day;
card._treatmentsOf(card._form)[0].treatment_id = "t1";
const withVat = card._renderNuovoForm();
assert(byClass(withVat, "nv-side")[0].textContent.includes("di cui IVA 22%"), "VAT line in the summary");
assert(JSON.stringify(card._vatLines([[61, 22], [11, 10]])) === JSON.stringify([[22, 50, 11], [10, 10, 1]]), "VAT split by rate");

// 2.5.2: Impostazioni › Dati fatturazione holds the VAT, not Generale.
card._config = {};
const draft = { vat_default: 22, billing_company: "", appearance: "auto" };
const general = card._settingsGeneral({ ...draft }, () => {});
assert(!general.textContent.includes("Aliquota IVA"), "no VAT in Generale");
const billing = card._settingsBilling(draft, () => {});
assert(billing.textContent.includes("Aliquota IVA predefinita") && billing.textContent.includes("Ragione sociale"), "billing tab");
assert(byClass(billing, "pg-num").length === 4, "four billing steps");
// Accessories have their VAT.
card._data.accessories = [{ id: "x1", label: "Accappatoio", price: 5, vat_rate: 10 }];
card._accOpen("__new__");
assert(card._accDraft.vat_rate === -1, "new accessory uses the default VAT");
// The edit form closes when the tab changes.
assert(Card.prototype._render.toString().includes('this._editing.kind === "appointment" && this._tab !== "agenda"'), "edit closed off the agenda");

// 2.5.3: the agenda detail closes on another tab; lanes only for busy operators.
assert(Card.prototype._render.toString().includes("this._detailTab !== this._viewKey()"), "detail closed off its tab and the month");
card._lookup.appointment = new Map(card._data.appointments.map((a) => [a.id, a]));
card._agParties = (list) => list.map((a) => [a]);
card._pauseOfAppointment = () => 0;
card._day = day;
const lanesText = card._agTimeline(card._data.appointments).textContent;
assert(lanesText.includes("Marco") && !lanesText.includes("Maria"), "only operators with appointments");

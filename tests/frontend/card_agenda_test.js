// Run: node tests/frontend/card_agenda_test.js custom_components/spa_booking/frontend/spa-booking-card.js
// 2.3.12: Agenda with week strip, pills, timeline per masseuse and phone cards.
"use strict";
const { loadCard, assert, all, byClass } = require("./card_harness");

const Card = loadCard(process.argv[2]);
const card = Object.create(Card.prototype);
card._me = { level: "admin" };
card._hass = { user: { id: "u", name: "Stefano" }, states: {} };
const day = "2030-05-14";
const massage = { id: "t1", name: "Massaggio schiena", duration_min: 50, price: 60, active: true, category_id: "cm", pause_min: 10 };
const spa = { id: "t2", name: "Ingresso Spa", duration_min: 90, price: 30, active: true, category_id: "cs" };
const appt = (id, treatment, operator, start, end, extra = {}) => ({
  id, treatment_id: treatment, operator_id: operator, client_id: "c" + id, start: `${day}T${start}:00`, end: `${day}T${end}:00`,
  status: "confirmed", payments: [], extras: [], ...extra });
card._data = {
  settings: {}, vouchers: [], requests: [],
  categories: [{ id: "cm", name: "Massaggi", requires_operator: true, pause_min: 10 }, { id: "cs", name: "Ingresso Spa", requires_operator: false }],
  clients: ["1", "2", "3", "4"].map((n) => ({ id: "c" + n, first_name: `Ospite${n}`, last_name: "" })),
  treatments: [massage, spa],
  operators: [
    { id: "o1", name: "Maria", active: true, priority: 1, treatment_ids: ["t1"] },
    { id: "o2", name: "Marco", active: true, priority: 2, treatment_ids: ["t1"] },
  ],
  appointments: [
    appt("1", "t1", "o1", "10:00", "10:50"),
    appt("2", "t1", "o1", "15:00", "15:50", { status: "pending" }),
    appt("3", "t2", "", "10:00", "11:30"),
    appt("4", "t2", "", "11:00", "12:30"),
  ],
};
card._render = () => {};
card._can = () => true;
card._applyAppearance = () => {};
card._reindex();
card._day = day;
card._ownsAppointment = () => true;

const page = card._renderAgendaDay();
assert(byClass(page, "ag-wd").length === 7, "week strip of seven days");
assert(byClass(page, "ag-wd on")[0].textContent.includes("14"), "the shown day is selected");
const lanes = byClass(page, "ag-lane");
assert(lanes.length === 3, "Maria, Marco (free) and the no-operator lane");
assert(lanes[1].textContent.includes("libera"), "Marco free all day");
assert(byClass(page, "ag-ev").length === 4, "one block per appointment");
assert(byClass(page, "ag-ev wait").length === 1, "pending in amber");
assert(byClass(page, "ag-pause").length === 2, "the masseuse's pause after her treatments");
const spaBlocks = byClass(lanes[2], "ag-ev");
assert(spaBlocks[0].attrs.style.includes("top:6px") && spaBlocks[1].attrs.style.includes("top:64px"), "overlapping spa entries stack");
assert(byClass(page, "ag-card").length === 4, "phone cards too");
assert(byClass(page, "ag-side")[0].textContent.includes("Da confermare"), "pending listed beside");
assert(page.textContent.includes("Conferma"), "one action: confirm the pending one");

// The pill filters the day.
card._agQuick = "waiting";
const filtered = card._renderAgendaDay();
assert(byClass(filtered, "ag-ev").length === 1, "pill «da confermare» leaves only the pending one");
card._agQuick = "";
// The list view is still there.
card._agendaView = "elenco";
const list = card._renderAgendaDay();
assert(byClass(list, "appt").length >= 3, "Elenco keeps the classic rows");

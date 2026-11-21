// Run: node tests/frontend/card_interrupt_test.js custom_components/spa_booking/frontend/spa-booking-card.js
// 3.20.5: a spa entry interrupted by a massage is offered the massage's minutes, each time.
"use strict";
const { loadCard, assert, sandbox } = require("./card_harness");

const Card = loadCard(process.argv[2]);
const card = Object.create(Card.prototype);
const spaCat = { id: "s", name: "Ingresso spa condiviso", interruptible: true };
const massCat = { id: "m", name: "Massaggi" };
const spa = { id: "ts", name: "Ingresso Spa 120 min", category_id: "s", duration_min: 120 };
const mass = { id: "tm", name: "Massaggio Relax", category_id: "m", duration_min: 60 };
card._lookup = { treatment: new Map([["ts", spa], ["tm", mass]]), category: new Map([["s", spaCat], ["m", massCat]]) };
const person = { treatments: [{ treatment_id: "ts", time: "16:00" }, { treatment_id: "tm", time: "17:00" }] };
card._treatmentsOf = (p) => p.treatments;
card._form = { persons: [person] };

let asked = [];
sandbox.confirm = (text) => { asked.push(text); return true; };
card._proposeInterruptions();
assert(asked.length === 1, "asked once");
assert(/Massaggio Relax delle 17:00 interrompe Ingresso Spa 120 min \(16:00–18:00\)/.test(asked[0]), asked[0]);
assert(/di 60 minuti, fino alle 19:00/.test(asked[0]), asked[0]);
assert(person.treatments[0].extra_min === 60, "lengthened");
// A retry («Prenota comunque») does not ask again.
card._proposeInterruptions();
assert(asked.length === 1, "not asked twice");
// Same minutes already on the entry (an edit): not asked again.
person.treatments[1].time = "17:30";
card._proposeInterruptions();
assert(asked.length === 1 && person.treatments[0].extra_min === 60, "unchanged extension");
// A longer massage, ending past the window: asked again, 90 minutes.
mass.duration_min = 90;
sandbox.confirm = (text) => { asked.push(text); return false; };
card._proposeInterruptions();
assert(asked.length === 2 && /delle 17:30/.test(asked[1]) && /di 90 minuti, fino alle 19:30/.test(asked[1]), String(asked[1]));
assert(person.treatments[0].extra_min === 0, "declined");
mass.duration_min = 60;
// Not interruptible: nothing asked, nothing added.
spaCat.interruptible = false;
asked = [];
card._form = { persons: [{ treatments: [{ treatment_id: "ts", time: "16:00" }, { treatment_id: "tm", time: "18:30" }] }] };
card._proposeInterruptions();
assert(asked.length === 0, "flag off");

// Agenda line.
spaCat.interruptible = true;
card._data = { appointments: [
  { id: "a", client_id: "c", person: 0, treatment_id: "ts", status: "confirmed", start: "2026-11-16T16:00:00", end: "2026-11-16T19:00:00", extra_min: 60 },
  { id: "b", client_id: "c", person: 0, treatment_id: "tm", status: "confirmed", start: "2026-11-16T17:00:00", end: "2026-11-16T18:00:00" },
] };
card._treatmentName = (a) => card._lookup.treatment.get(a.treatment_id).name;
const line = card._interruptionText(card._data.appointments[0]);
assert(line === "Interrotto 17:00–18:00 per Massaggio Relax · allungato di 60 min", line);
assert(card._interruptionText(card._data.appointments[1]) === "", "massage has no line");
console.log("ok");

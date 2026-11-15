// Run: node tests/frontend/card_capacity_test.js custom_components/spa_booking/frontend/spa-booking-card.js
// 3.4.0: the card says a rigid capacity at once; a forceable one goes to the server.
"use strict";
const { loadCard, assert } = require("./card_harness");

const Card = loadCard(process.argv[2]);
const card = Object.create(Card.prototype);
const massaggi = { id: "m", name: "Massaggi", capacity_max: 3 };
const spa = { id: "s", name: "Spa", capacity_max: 16, entry_max: 6, entry_minutes: 15, capacity_force: false };
const t = { id: "tm", category_id: "m", duration_min: 60 };
const ts = { id: "ts", category_id: "s", duration_min: 90 };
card._data = { categories: [massaggi, spa], treatments: [t, ts], appointments: [] };
const appt = (id, tid, start, end) => ({ id, treatment_id: tid, status: "confirmed", start: `2026-11-16T${start}:00`, end: `2026-11-16T${end}:00` });
card._data.appointments.push(appt("a", "tm", "17:00", "18:00"), appt("b", "tm", "17:00", "18:00"), appt("c", "tm", "16:30", "17:30"));
for (let i = 0; i < 6; i++) card._data.appointments.push(appt(`s${i}`, "ts", "16:00", "17:30"));
card._lookup = { treatment: new Map([["tm", t], ["ts", ts]]), category: new Map([["m", massaggi], ["s", spa]]) };
card._categoryOf = (tr) => card._lookup.category.get(tr && tr.category_id);
let text = card._exclusionClash([{ treatment_id: "tm", start: "2026-11-16T17:15" }]);
assert(/Massaggi' è al completo alle 17:15, massimo 3/.test(text), text);
assert(card._exclusionClash([{ treatment_id: "tm", start: "2026-11-16T18:00" }]) === "", "free at 18");
text = card._exclusionClash([{ treatment_id: "ts", start: "2026-11-16T16:10" }]);
assert(/6 ingressi in 15 minuti dalle 16:00, il prossimo ingresso è alle 16:15/.test(text), text);
assert(card._exclusionClash([{ treatment_id: "ts", start: "2026-11-16T16:15" }]) === "", "16:15 ok");
spa.capacity_force = true;
assert(card._exclusionClash([{ treatment_id: "ts", start: "2026-11-16T16:10" }]) === "", "forceable: the server asks");
assert(card._isExclusionRule("La categoria 'Massaggi' è al completo alle 17:00, massimo 3 persone insieme"), "rigid");
assert(!card._isExclusionRule("La categoria 'Spa' ha già 6 ingressi in 15 minuti dalle 16:00, il prossimo ingresso è alle 16:15"), "forceable");
assert(card._isCategoryRule("La categoria 'Spa' ha già 6 ingressi in 15 minuti dalle 16:00, il prossimo ingresso è alle 16:15"), "rule");
console.log("ok");

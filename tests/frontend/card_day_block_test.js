// Run: node tests/frontend/card_day_block_test.js custom_components/spa_booking/frontend/spa-booking-card.js
// 3.22.0: two taps on the same day open «Blocca giorni».
"use strict";
const { loadCard, assert } = require("./card_harness");

const Card = loadCard(process.argv[2]);
const card = Object.create(Card.prototype);
card._config = {};
card._me = { level: "admin" };
card._data = { closures: [], categories: [], operators: [], appointments: [], settings: {} };
card._lookup = { category: new Map(), operator: new Map(), appointment: new Map(), treatment: new Map() };
card._render = () => {};
card._appointmentsOfDay = () => [];
let singles = 0;
card._dayTap("2026-11-30", () => { singles += 1; });
assert(singles === 1 && !card._dayBlock, "first tap opens the day");
card._dayTap("2026-12-01", () => { singles += 1; });
assert(singles === 2 && !card._dayBlock, "another day is a first tap");
card._dayTap("2026-12-01", () => { singles += 1; });
assert(card._dayBlock && card._dayBlock.key === "2026-12-01" && singles === 2, "second tap opens the popup");
const draft = card._closureDraft;
assert(draft.date_from === "2026-12-01" && draft.date_to === "2026-12-01", "the day");
let text = card._renderDayBlock().textContent;
assert(text.includes("Verrà bloccato 1 giorno") && text.includes("Blocca il giorno"), text);
// Until 20 December, Saturdays open.
draft.date_to = "2026-12-20";
draft.skip_weekdays = [5];
text = card._renderDayBlock().textContent;
assert(text.includes("Verranno bloccati 17 giorni") && text.includes("restano aperti: sabato") && text.includes("Blocca 17 giorni"), text);
// A therapist without «Fasce bloccate» only opens the day.
card._dayBlock = null;
card._me = { level: "therapist", menus: ["agenda"] };
card._lastDayTap = null;
card._dayTap("2026-12-02", () => {});
card._dayTap("2026-12-02", () => {});
assert(!card._dayBlock, "no popup without the right");
console.log("ok");

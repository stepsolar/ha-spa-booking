// Run: node tests/frontend/card_submenu_test.js custom_components/spa_booking/frontend/spa-booking-card.js
// 3.12.0: each tab's sub-menu look on a phone, chosen in Impostazioni › Generale.
"use strict";
const { loadCard, assert } = require("./card_harness");

const Card = loadCard(process.argv[2]);
const card = Object.create(Card.prototype);
card._data = { settings: { submenu_styles: { nuovo: "bar", spa: "pills" } } };
assert(card._subStyle("nuovo") === " sub-bar", "bar");
assert(card._subStyle("spa") === " sub-pills", "pills");
assert(card._subStyle("config") === "", "vertical by default");
card._data.settings.submenu_styles = { config: "strano" };
assert(card._subStyle("config") === "", "unknown look = vertical");
console.log("card_submenu_test: ok");

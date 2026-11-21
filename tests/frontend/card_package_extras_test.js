// Run: node tests/frontend/card_package_extras_test.js custom_components/spa_booking/frontend/spa-booking-card.js
// 3.20.6: a package's accessories are «incluso» in the totals; one added on top is paid.
"use strict";
const { loadCard, assert } = require("./card_harness");

const Card = loadCard(process.argv[2]);
const card = Object.create(Card.prototype);
const t = { id: "t1", name: "Massaggio", price: 80, active: true };
card._lookup = { treatment: new Map([["t1", t]]), category: new Map(), appointment: new Map() };
card._data = { partners: [], settings: {
  wp_products: [{ key: "p1", name: "Coccole", price: 70 }],
  wp_product_map: { p1: { people: 1, treatment_ids: ["t1"], extras: ["kit"] } },
} };
card._accessories = () => [{ id: "kit", label: "Kit spa", price: 6 }, { id: "glass", label: "Calice", price: 8 }];
card._treatmentsOf = (p) => p.treatments;
const person = { package: { key: "p1", group: "g", name: "Coccole" }, extras: ["kit", "glass"],
  treatments: [{ treatment_id: "t1", price: 70, list_price: 80, package_key: "p1" }] };
card._form = { persons: [person] };
const { people, total } = card._bookingTotals();
assert(total === 78, `package 70 + glass 8, kit included: ${total}`);
assert(people[0].extras[0].included === true && people[0].extras[0].price === 0, "kit included");
assert(people[0].extras[1].included === false && people[0].extras[1].price === 8, "glass paid");
const text = card._totaliBlock().textContent;
assert(text.includes("Kit spa · incluso"), text);
assert(/Calice · 8,00/.test(text), text);
// A saved appointment of the package: the same rule.
const line = card._lineBreakdown({ treatment_id: "t1", price: 70, extras: ["kit", "glass"], extras_included: true, package_key: "p1" });
assert(line.extras === 8, `only the glass: ${line.extras}`);
console.log("ok");

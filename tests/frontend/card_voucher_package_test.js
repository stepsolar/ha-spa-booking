// Run: node tests/frontend/card_voucher_package_test.js custom_components/spa_booking/frontend/spa-booking-card.js
// 3.20.3: «Nuovo voucher»: a package fills every person at once.
"use strict";
const { loadCard, assert } = require("./card_harness");

const Card = loadCard(process.argv[2]);
const card = Object.create(Card.prototype);
card._can = () => true;
card._render = () => {};
card._data = {
  settings: { wp_products: [{ key: "p2", name: "Spa di coppia", price: 120 }],
    wp_product_map: { p2: { treatment_ids: ["t1", "t2"], people: 2, extras: ["acc_kit"] } }, accessories: [{ id: "acc_kit", label: "Kit" }] },
  treatments: [{ id: "t1", name: "Ingresso Spa", active: true, price: 40 }, { id: "t2", name: "Massaggio", active: true, price: 60 }],
  categories: [],
};
card._lookup = { treatment: new Map(card._data.treatments.map((t) => [t.id, t])) };
const draft = { people: [{ name: "Anna", treatment_ids: [], extras: [] }], step: 2 };
const box = card._voucherPackageChoice(draft);
assert(box && box.textContent.includes("Spa di coppia"), "the packages are offered");
// Choose it as the click would.
const pkg = card._shopPackages().find((p) => p.key === "p2");
assert(pkg && pkg.people === 2, "the package is for two");
// Simulate the click handler through the rendered tree.
function find(node, text) {
  if (node.textContent && node.textContent.includes(text) && node.tagName === "BUTTON") return node;
  for (const child of node.childNodes || []) { const hit = find(child, text); if (hit) return hit; }
  return null;
}
const pick = find(box, "Spa di coppia");
pick.listeners.click[0]();
assert(draft.package_key === "p2" && draft.people.length === 2, "two people");
assert(draft.people[0].name === "Anna" && draft.people[1].treatment_ids.join() === "t1,t2", "each with the package's treatments, names kept");
assert(draft.people[1].extras.join() === "acc_kit", "and its accessories");
assert(card._voucherValue({ ...draft, package_key: "p2" }) === 120, "the value is the package price");

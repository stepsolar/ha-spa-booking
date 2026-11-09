// Run: node tests/frontend/card_request_test.js custom_components/spa_booking/frontend/spa-booking-card.js
// The Richiesta form of the management card: one box per person, what is
// sent to create_request, editing an existing request, WhatsApp numbers.
"use strict";
const fs = require("fs");
const vm = require("vm");

class Node {
  constructor(tag) {
    this.tagName = String(tag).toUpperCase(); this.children = []; this.attrs = {};
    this.listeners = {}; this._text = ""; this.style = {}; this.classList = { add() {}, remove() {}, toggle() {}, contains: () => false };
  }
  appendChild(c) { this.children.push(c); return c; }
  append(...c) { c.forEach((x) => this.appendChild(x)); }
  insertBefore(c) { this.children.unshift(c); return c; }
  removeChild(c) { this.children = this.children.filter((x) => x !== c); }
  setAttribute(k, v) { this.attrs[k] = String(v); }
  getAttribute(k) { return this.attrs[k]; }
  addEventListener(ev, fn) { (this.listeners[ev] = this.listeners[ev] || []).push(fn); }
  set textContent(v) { this._text = String(v); this.children = []; }
  get textContent() { return this._text + this.children.map((c) => c.textContent).join(""); }
  set innerHTML(v) { this._text = ""; this.children = []; }
  querySelector() { return null; }
  querySelectorAll() { return []; }
  *walk() { for (const c of this.children) { yield c; if (c.walk) yield* c.walk(); } }
}
class TextNode extends Node { constructor(t) { super("#text"); this._text = t; } }

let Card = null;
const sandbox = {
  console,
  Node,
  HTMLElement: class {},
  document: { createElement: (t) => new Node(t), createTextNode: (t) => new TextNode(t) },
  customElements: { get: () => undefined, define: (name, cls) => { Card = cls; } },
  window: {},
  setTimeout, clearTimeout,
};
sandbox.window = sandbox;
vm.createContext(sandbox);
vm.runInContext(fs.readFileSync(process.argv[2], "utf8"), sandbox, { filename: "card.js" });

const assert = (cond, msg) => { if (!cond) { console.error("FAIL:", msg); process.exit(1); } console.log("ok -", msg); };

function makeCard() {
  const card = Object.create(Card.prototype);
  const treatments = [
    { id: "t1", name: "Massaggio", duration_min: 60, active: true, category_id: "c1", operator_ids: [] },
    { id: "t2", name: "Ingresso Spa", duration_min: 90, active: true, category_id: "c2", operator_ids: [] },
  ];
  card._data = { treatments, categories: [], operators: [], clients: [], appointments: [], requests: [], settings: {}, accessories: [] };
  card._lookup = { treatment: new Map(treatments.map((t) => [t.id, t])), client: new Map(), operator: new Map(), category: new Map() };
  card._busy = false;
  card._byDay = new Map();
  card._render = () => {};
  card._form = { date: "2026-11-20", first_name: "Anna", phone: "333 1234567", client_mode: "new", treatments: [], persons: null, people: 1 };
  return card;
}

const boxes = (node) => [node, ...node.walk()].filter((n) => n.attrs && n.attrs.class === "bk-person");

// One person: one box, entries without "person".
let card = makeCard();
assert(boxes(card._richiestaBlock()).length === 1, "one person: one box");
card._form.treatments = [{ ...card._blankTreatment(), treatment_id: "t1", time: "10:00" }];
let payload = card._requestRows();
assert(payload.people === 1 && payload.entries.length === 1 && payload.entries[0].person === undefined, "one person: entry for her, no person tag");

// Two people: two boxes, each with her own treatments.
card._setPeople(2);
assert(Array.isArray(card._form.persons) && card._form.persons.length === 2, "stepper makes two persons");
const block = card._richiestaBlock();
assert(boxes(block).length === 2, "two people: two boxes");
assert(block.textContent.includes("Persona 1") && block.textContent.includes("Persona 2"), "boxes are labelled Persona 1 and Persona 2");
assert(card._form.persons[0].treatments[0].treatment_id === "t1", "first person keeps what was typed");
card._form.persons[1].treatments = [{ ...card._blankTreatment(), treatment_id: "t2", time: "11:00" }];
card._addTreatment(card._form.persons[1]);
card._form.persons[1].treatments[1].treatment_id = "t1";
card._form.persons[1].treatments[1].time = "15:00";
payload = card._requestRows();
assert(payload.people === 2, "people sent");
assert(JSON.stringify(payload.entries.map((e) => [e.treatment_id, e.time, e.person])) ===
  JSON.stringify([["t1", "10:00", 0], ["t2", "11:00", 1], ["t1", "15:00", 1]]), "each treatment tagged with its person");
assert(payload.request_id === undefined, "new request has no request_id");

// Editing a request saved per person rebuilds the boxes and keeps its id.
card = makeCard();
card._editRequest({ id: "req_1", date: "2026-11-20", people: 2, client_id: "", client: { first_name: "Anna" },
  entries: [{ treatment_id: "t1", time: "10:00", person: 0 }, { treatment_id: "t2", time: "11:00", person: 1 }] });
assert(card._form.persons.length === 2, "edit: two persons rebuilt");
assert(card._form.persons[1].treatments[0].treatment_id === "t2", "edit: person 2 gets her own treatment");
payload = card._requestRows();
assert(payload.request_id === "req_1", "edit: saving rewrites the same request");

// An old request (entries for everybody) shows every entry in every box.
card = makeCard();
card._editRequest({ id: "req_2", date: "2026-11-20", people: 2, client_id: "", client: { first_name: "Luca" },
  entries: [{ treatment_id: "t2", time: "16:00" }] });
assert(card._form.persons.every((p) => p.treatments.length === 1 && p.treatments[0].treatment_id === "t2"), "legacy request: same treatment in both boxes");

// One-person request edits stay on the flat form.
card = makeCard();
card._editRequest({ id: "req_3", date: "2026-11-20", people: 1, client_id: "", client: {},
  entries: [{ treatment_id: "t1", time: "09:00" }] });
assert(card._form.persons === null && card._form.treatments.length === 1, "single-person edit uses the flat form");

// WhatsApp chat ids: no more "39" glued to foreign numbers.
card = makeCard();
assert(card._phoneFromChat("393331234567@c.us") === "+393331234567", "Italian chat id");
assert(card._phoneFromChat("41791234567@c.us") === "+41791234567", "Swiss chat id stays Swiss");
assert(card._phoneFromChat("123456789@lid") === "", "a LID is not a phone number");
assert(card._phoneFromChat("1203630@g.us") === "", "a group is not a phone number");

console.log("ALL CARD REQUEST TESTS PASSED");

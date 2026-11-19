// Run: node tests/frontend/card_accounting_test.js custom_components/spa_booking/frontend/spa-booking-card.js
// 3.19.0: Configurazione › Contabilità › Incassi, with its PDF and Excel.
"use strict";
const { loadCard, assert, sandbox } = require("./card_harness");

const Card = loadCard(process.argv[2]);
const card = Object.create(Card.prototype);
card._can = () => true;
card._render = () => {};
card._data = {
  settings: {},
  clients: [{ id: "c1", first_name: "Anna", last_name: "Rossi" }, { id: "c2", first_name: "Bea", last_name: "Neri" }],
  treatments: [{ id: "t1", name: "Ingresso Spa" }],
  appointments: [
    { id: "a1", client_id: "c1", treatment_id: "t1", start: "2026-11-16T15:00:00", status: "confirmed", code: "AB1",
      payments: [{ id: "p1", method: "cash", date: "2026-11-15", amount: 40, split_id: "s1" }, { id: "p2", method: "card", date: "2026-10-30", amount: 10 }] },
    { id: "a2", client_id: "c1", treatment_id: "t1", start: "2026-11-16T15:00:00", status: "confirmed", code: "AB1",
      payments: [{ id: "p3", method: "cash", date: "2026-11-15", amount: 40, split_id: "s1" }] },
    { id: "a3", client_id: "c2", treatment_id: "t1", start: "2026-11-20T10:00:00", status: "confirmed", code: "CD2",
      payments: [{ id: "p4", method: "card", date: "2026-11-18", amount: 65 }] },
  ],
};
card._lookup = { client: new Map(card._data.clients.map((c) => [c.id, c])), treatment: new Map([["t1", card._data.treatments[0]]]), operator: new Map() };

card._accFilter = { mode: "mese", day: "2026-11-15", month: "2026-11", year: "2026", from: "2026-11-01", to: "2026-11-30", methods: [], q: "" };
let rows = card._accRows();
assert(rows.length === 2, "November: the split taking is one row, October's is out");
assert(rows[1].amount === 80 && rows[1].people === 2, "the split taking sums its parts");
card._accFilter.methods = ["card"];
const page = card._renderAccounting();
assert(page.textContent.includes("Bea Neri") && !page.textContent.includes("Anna Rossi"), "filtered by type");
card._accFilter.methods = [];
card._accFilter.mode = "anno";
assert(card._accRows().length === 3, "the year has October too");
card._accFilter.q = "neri";
assert(card._accRows().length === 1, "search by client");
card._accFilter.q = "";

(async () => {
  card._accExport("xlsx", card._accRows(), []);
  let bytes = new Uint8Array(await sandbox.lastBlob.arrayBuffer());
  assert(bytes[0] === 0x50 && bytes[1] === 0x4b && sandbox.lastDownload === "incassi_2026-01-01_2026-12-31.xlsx", "an .xlsx (zip)");
  card._accExport("pdf", card._accRows(), []);
  bytes = new Uint8Array(await sandbox.lastBlob.arrayBuffer());
  const head = String.fromCharCode(...bytes.slice(0, 8));
  const text = Array.from(bytes, (b) => String.fromCharCode(b)).join("");
  assert(head.startsWith("%PDF-1.4") && text.includes("%%EOF") && text.includes("\x80"), "a PDF, with the euro sign in WinAnsi");
})();

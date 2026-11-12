// Run: node tests/frontend/card_partners_test.js custom_components/spa_booking/frontend/spa-booking-card.js
// 2.6.0: partners from a CSV file, newsletter status in the list.
"use strict";
const { loadCard, assert, byClass, sandbox } = require("./card_harness");

const Card = loadCard(process.argv[2]);
const csv = "﻿Nome struttura;Tipo;Titolare;Città;Telefono;WhatsApp;Email\r\n"
  + "\"Hotel Mare; Spa\";Hotel;Giulia Rossi Bianchi;Menfi;0925 123;sì;info@hotelmare.it\r\n"
  + "B&B Sole;B&B;;Sciacca;;;sole@example.com\r\n\r\n";
const rows = sandbox.partnersFromCsv(csv);
assert(rows.length === 2, "two partners, the empty line ignored");
assert(rows[0].company === "Hotel Mare; Spa" && rows[0].city === "Menfi" && rows[0].email === "info@hotelmare.it", "quoted cell with the separator");
assert(rows[0].first_name === "Giulia" && rows[0].last_name === "Rossi Bianchi", "owner split in name and surname");
assert(rows[0].whatsapp === "sì" && rows[1].structure_type === "B&B", "WhatsApp and type columns");
const comma = sandbox.partnersFromCsv("Company,Email,City\nAgriturismo Uliveto,uliveto@example.com,Ribera\n");
assert(comma.length === 1 && comma[0].city === "Ribera", "comma CSV with English headers");

const card = Object.create(Card.prototype);
card._me = { level: "admin" };
card._can = () => true;
card._render = () => {};
card._data = { partners: [
  { id: "p1", company: "Hotel Mare", city: "Menfi", structure_type: "Hotel", code: "PRT-1", email: "a@b.it", subscribed: true },
  { id: "p2", company: "B&B Sole", city: "Sciacca", code: "PRT-2", email: "s@b.it", subscribed: false, unsubscribed_at: "2026-11-12T10:00:00" },
], partner_points: {} };
card._searchInputRedraw = () => {};
let page = card._renderPartners();
assert(page.textContent.includes("2 partner · 1 iscritti"), "count of the subscribed");
assert(page.textContent.includes("Importa file") && page.textContent.includes("Disiscritto"), "import button and unsubscribed tag");
card._partnerFilter = "unsub";
page = card._renderPartners();
assert(page.textContent.includes("B&B Sole") && !page.textContent.includes("Hotel Mare"), "filter: unsubscribed only");

// 2.6.1: import in batches from the panel, no browser dialog.
(async () => {
  const sent = [];
  card._service = async (service, data) => { sent.push(data.partners.length); return { added: data.partners.length, updated: 0, skipped: 0 }; };
  card._loadData = async () => {};
  card._friendlyError = (e) => String(e);
  card._partnerImport = { name: "x.csv", partners: Array.from({ length: 320 }, (_, i) => ({ company: `S${i}`, email: `s${i}@x.it` })), withEmail: 320 };
  assert(card._renderPartners().textContent.includes("Importa 320 partner"), "preview panel with the import button");
  await card._partnerImportRun();
  assert(JSON.stringify(sent) === "[150,150,20]", "sent in batches of 150");
  assert(card._partnerImport === null && card._message.text.includes("Importati 320"), "result shown");
  card._service = async () => { throw new Error("Unknown service spa_booking.import_partners"); };
  card._partnerImport = { name: "x.csv", partners: [{ company: "A", email: "a@x.it" }], withEmail: 1 };
  await card._partnerImportRun();
  assert(card._partnerImport.error.includes("riavvia Home Assistant"), "missing service: restart hint");
})();

// 2.7.3: the partners come with the data (they were never loaded before).
(async () => {
  const fresh = Object.create(Card.prototype);
  fresh._hass = { callWS: async () => ({ response: { data: { partners: [{ id: "p9", company: "Hotel Mare", city: "Menfi", code: "PRT-9" }], loyalty: { c1: { balance: 5 } }, partner_points: { p9: { balance: 3 } }, settings: {} } } }) };
  fresh._render = () => {};
  fresh._loadMe = async () => {};
  fresh._pinNeeded = () => false;
  fresh._reindex = () => {};
  fresh._checkUpdates = () => {};
  try { await fresh._loadData(); } catch (error) { /* the rest of the load is not under test */ }
  assert(fresh._data && fresh._data.partners && fresh._data.partners.length === 1, "partners loaded with the data");
  assert(fresh._data.partner_points.p9.balance === 3 && fresh._data.loyalty.c1.balance === 5, "points loaded too");
  // City filter in the list.
  card._partnerFilter = "";
  card._partnerCity = "Menfi";
  const byCity = card._renderPartners();
  assert(byCity.textContent.includes("Hotel Mare") && !byCity.textContent.includes("B&B Sole"), "filter by town");
  card._partnerCity = "";
})();

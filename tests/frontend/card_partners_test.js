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

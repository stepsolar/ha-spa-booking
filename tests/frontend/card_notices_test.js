// Run: node tests/frontend/card_notices_test.js custom_components/spa_booking/frontend/spa-booking-card.js
// 3.10.0: the bell lists every new notice — website requests and WhatsApp.
"use strict";
const { loadCard, assert, all } = require("./card_harness");

const Card = loadCard(process.argv[2]);
const card = Object.create(Card.prototype);
card._me = { level: "manager" };
card._userLevel = () => "manager";
card._can = () => true;
card._render = () => {};
card._visibleNuovoTabs = () => [{ id: "lista" }];
card._service = async () => ({});
const iso = (m) => new Date(Date.now() - m * 60000).toISOString();
card._data = {
  clients: [{ id: "c1", first_name: "Anna", last_name: "Rossi", phone: "+39 392 123 4567" }],
  treatments: [{ id: "t1", name: "Ingresso Spa" }],
  operators: [],
  requests: [
    { id: "r1", source: "web", seen: false, client_id: "c1", date: "2026-11-21", entries: [{ treatment_id: "t1" }], created_at: iso(40) },
    { id: "r2", source: "web", seen: true, client_id: "c1", created_at: iso(90) },
    { id: "r3", source: "desk", seen: false, client_id: "c1", created_at: iso(5) }],
};
card._lookup = { client: new Map([["c1", card._data.clients[0]]]), treatment: new Map([["t1", card._data.treatments[0]]]), operator: new Map() };
card._waChats = [
  { chat_id: "393921234567@c.us", read_at: iso(300), messages: [{ dir: "in", text: "Posso portare mia sorella?", at: iso(6) }] },
  { chat_id: "393405551212@c.us", read_at: iso(1), messages: [{ dir: "in", text: "già letto", at: iso(30) }] },
  { chat_id: "4915123456789@c.us", read_at: "", messages: [{ dir: "in", media: { mimetype: "image/jpeg" }, at: iso(2) }, { dir: "in", text: "Ecco", at: iso(1) }] }];

const notices = card._notices();
assert(notices.length === 3, "one web request not seen and two chats with unread messages");
assert(notices[0].kind === "whatsapp" && notices[0].count === 2 && notices[0].text === "Ecco", "newest first, with how many messages");
assert(notices.find((n) => n.kind === "whatsapp" && n.title === "Anna Rossi"), "the chat is named after the client");
assert(notices.find((n) => n.kind === "request" && n.title.includes("Anna Rossi") && n.text.includes("Ingresso Spa")), "the website request");

card._noticePanel = true;
let panel = card._renderNoticePanel();
assert(panel.textContent.includes("Avvisi") && panel.textContent.includes("Segna tutto come letto"), "the panel");
card._noticeFilter = "request";
panel = card._renderNoticePanel();
assert(panel.textContent.includes("Richiesta dal sito") && !panel.textContent.includes("Posso portare"), "filter by kind");

// A receptionist without the chat sees only the requests.
card._userLevel = () => "reception";
assert(card._notices().every((n) => n.kind === "request"), "no WhatsApp notices without the chat");
console.log("card_notices_test: ok");

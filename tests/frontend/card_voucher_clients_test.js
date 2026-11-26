// Run: node tests/frontend/card_voucher_clients_test.js custom_components/spa_booking/frontend/spa-booking-card.js
// 3.23.0: after a voucher, buyer and recipient among the clients, the buyer's points.
"use strict";
const { loadCard, assert } = require("./card_harness");

const Card = loadCard(process.argv[2]);
const card = Object.create(Card.prototype);
card._render = () => {};
card._lookup = { treatment: new Map() };
const voucher = { id: "v1", code: "VCH-AB12", buyer_name: "Anna Rossi", buyer_phone: "+39 347 1112223",
  recipient_name: "Sara Bianchi", recipient_phone: "333 4445556", value: 100, points_state: "pending",
  people: [{ name: "Sara", treatment_ids: [], gift_card_amount: 100 }] };
card._data = {
  vouchers: [voucher],
  clients: [{ id: "c1", first_name: "Anna", phone: "3471112223" }],
  loyalty: { c1: { balance: 240 } },
  settings: { loyalty_enabled: true, loyalty_points_per_euro: 1 },
};
card._openVoucherClients("v1", true);
const state = card._voucherClients;
assert(state.register_buyer && state.award_points && state.send_message && state.register_recipient, "all on");
const text = card._renderVoucherClients().textContent;
assert(text.includes("Assegna 100 punti per l'acquisto") && text.includes("saldo 340 punti"), text);
assert(text.includes("già cliente") && text.includes("nuovo cliente"), "who is known");
assert(text.includes("Nessun punto: il voucher è un regalo") && text.includes("Non ora"), text);
// Saving sends the choices.
let sent = null;
card._service = async (service, data) => { sent = { service, data }; return { points: 100, sent: true }; };
card._loadData = async () => {};
card._friendlyError = (e) => String(e);
card._saveVoucherClients().then(() => {
  assert(sent.service === "voucher_clients" && sent.data.award_points && sent.data.send_message, JSON.stringify(sent));
  assert(card._voucherClients === null && /100 punti/.test(card._message.text), card._message.text);
  // Loyalty off: no points rows.
  card._data.settings.loyalty_enabled = false;
  card._openVoucherClients("v1", true);
  const off = card._renderVoucherClients().textContent;
  assert(!off.includes("Assegna") && off.includes("I punti fedeltà sono spenti"), off);
  console.log("ok");
});

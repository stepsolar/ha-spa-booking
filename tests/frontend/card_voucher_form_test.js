// Run: node tests/frontend/card_voucher_form_test.js custom_components/spa_booking/frontend/spa-booking-card.js
// 3.20.2: a voucher fills the guest's name; a request finds vouchers; one «Registra incasso».
"use strict";
const { loadCard, assert } = require("./card_harness");

const Card = loadCard(process.argv[2]);
const card = Object.create(Card.prototype);
card._can = () => true;
card._render = () => {};
card._searchInputRedraw = (input) => input;
card._data = { settings: {}, treatments: [], vouchers: [
  { code: "VCH-AAA111", buyer_name: "Bea Neri", recipient_name: "Anna Maria Rossi", recipient_phone: "333 1", status: "active",
    people: [{ name: "Anna Maria Rossi", treatment_ids: [], extras: [], gift_card_amount: 100 }], credit_left: 100, created_at: "2026-11-01" },
] };

card._form = { first_name: "", last_name: "", phone: "", client_mode: "new", payment: {}, voucher_query: "" };
card._applyVoucher(card._data.vouchers[0]);
assert(card._form.first_name === "Anna" && card._form.last_name === "Maria Rossi" && card._form.phone === "333 1", "the voucher names the guest");
assert(card._form.voucher_code === "VCH-AAA111" && card._form.payment.voucher_code === "VCH-AAA111", "the code is kept (request and booking)");

card._form = { first_name: "Luca", last_name: "", phone: "", client_mode: "new", payment: {}, voucher_query: "" };
card._applyVoucher(card._data.vouchers[0]);
assert(card._form.first_name === "Luca", "a name already written stays");

// A request: the search finds the voucher by name.
card._nvKind = "richiesta";
card._form = { payment: {}, voucher_query: "rossi" };
const field = card._voucherField();
assert(field.textContent.includes("VCH-AAA111"), "a request finds the voucher");
card._form = { payment: {}, voucher_query: "WEB-7788" };
assert(card._voucherField().textContent.includes("Usa il codice WEB-7788"), "an outside code can be used on a request");

// The bill: one button.
let other = null;
const conto = card._contoView({ total: 80, rows: [], onPay: () => {}, onOther: (due) => { other = due; } });
assert(conto.textContent.includes("Registra incasso") && !conto.textContent.includes("Contante"), "one «Registra incasso» button");

// Run: node tests/frontend/card_whatsapp_test.js custom_components/spa_booking/frontend/spa-booking-card.js
// The "Collegamento WhatsApp" box: engine choice, states, QR code, link code.
"use strict";
const { loadCard, assert, byClass, all } = require("./card_harness");

const Card = loadCard(process.argv[2]);

function makeCard(status) {
  const card = Object.create(Card.prototype);
  card._busy = false;
  card._render = () => {};
  card._waStatus = status;
  card.calls = [];
  card._call = async (service, data) => { card.calls.push([service, data]); return service === "whatsapp_pair_code" ? { code: "ABCD-1234" } : {}; };
  card._service = async (service) => { card.calls.push([service]); return status; };
  card._waStartPolling = () => { card.polling = true; };
  card._waStopPolling = () => { card.polling = false; };
  return card;
}
const boxFn = (id, title) => { const { Node } = require("./card_harness"); const n = new Node("div"); n.attrs.class = "cfg-box"; n.attrs["data-id"] = id; n.appendChild(Object.assign(new Node("h3"), { _text: title })); return n; };
const buttons = (node) => all(node).filter((n) => n.tagName === "BUTTON").map((n) => n.textContent.trim());
const radios = (node) => all(node).filter((n) => n.tagName === "INPUT" && n.attrs.type === "radio");

// WAHA chosen: only the choice, no polling.
let card = makeCard(null);
let box = card._whatsappEngineBox(boxFn, { whatsapp_engine: "waha" });
assert(radios(box).length === 2, "two engine choices");
assert(box.textContent.includes("WhatsApp integrato (beta)") && box.textContent.includes("Add-on WAHA"), "choices labelled");
assert(buttons(box).length === 0 && card.polling === false, "WAHA: no link buttons, no polling");

// Not linked: link button.
card = makeCard({ state: "not_linked", label: "Non collegato" });
box = card._whatsappEngineBox(boxFn, { whatsapp_engine: "integrated" });
assert(box.textContent.includes("Non collegato"), "state shown");
assert(buttons(box).includes("Collega WhatsApp") && !buttons(box).includes("Scollega"), "not linked: Collega WhatsApp");

// Pairing: QR image, code field, polling on.
card = makeCard({ state: "pairing", label: "In attesa del collegamento", qr: "data:image/png;base64,AAAA" });
box = card._whatsappEngineBox(boxFn, { whatsapp_engine: "integrated" });
assert(all(box).some((n) => n.tagName === "IMG" && n.attrs.src === "data:image/png;base64,AAAA"), "QR code shown");
assert(buttons(box).includes("Ottieni codice") && buttons(box).includes("Nuovo codice QR"), "pairing: code and new QR buttons");
assert(card.polling === true, "pairing: state polled");

// Connected: number shown, unlink button, polling off.
card = makeCard({ state: "connected", label: "Connesso", phone: "393331234567", push_name: "Hotel" });
box = card._whatsappEngineBox(boxFn, { whatsapp_engine: "integrated" });
assert(box.textContent.includes("+393331234567 (Hotel)"), "linked number shown");
assert(buttons(box).includes("Scollega") && !buttons(box).includes("Collega WhatsApp"), "connected: Scollega");
assert(card.polling === false, "connected: no polling");

// Actions.
(async () => {
  card = makeCard({ state: "pairing" });
  radios(card._whatsappEngineBox(boxFn, { whatsapp_engine: "waha" }))[0].listeners.change[0]({});
  await new Promise((r) => setTimeout(r, 0));
  assert(JSON.stringify(card.calls[0]) === JSON.stringify(["update_settings", { whatsapp_engine: "integrated" }]), "choosing the engine saves it");
  card._waPairPhone = "333 1234567";
  await card._waPairCode();
  assert(card._waCode === "ABCD-1234", "link code requested and kept");
  card._waPairPhone = "";
  card._message = null;
  await card._waPairCode();
  assert(card._message && card._message.kind === "error", "link code needs a number");
  console.log("ALL CARD WHATSAPP TESTS PASSED");
})();

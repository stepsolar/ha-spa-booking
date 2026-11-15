// Run: node tests/frontend/card_wp_variations_test.js custom_components/spa_booking/frontend/spa-booking-card.js
// 3.9.0: shop variations enabled or disabled (WooCommerce «Abilitata»).
"use strict";
const { loadCard, assert, all } = require("./card_harness");

const Card = loadCard(process.argv[2]);
const card = Object.create(Card.prototype);
card._me = { level: "admin" };
card._userLevel = () => "admin";
card._can = () => true;
card._render = () => {};
card._searchInputRedraw = () => {};
card._lookup = { treatment: new Map() };
card._data = {
  treatments: [], vouchers: [],
  settings: { wp_enabled: true, wp_url: "https://shop.example.it", wp_secret: "abc",
    wp_products: [
      { key: "4097:5117", product_id: 4097, variation_id: 5117, name: "You&Me - con kit", price: 100, status: "publish", enabled: true },
      { key: "4097:5118", product_id: 4097, variation_id: 5118, name: "You&Me - senza kit", price: 80, status: "publish", enabled: false },
      { key: "5000:0", product_id: 5000, variation_id: 0, name: "Pacchetto Relax", price: 120, status: "publish", enabled: true }],
    wp_product_map: {} },
};

let page = card._renderShop();
assert(page.textContent.includes("Variante disattivata"), "a disabled variation is marked in the list");
assert(page.textContent.includes("Variante attiva"), "an enabled variation is marked too");
assert(page.textContent.includes("Varianti disattivate 1"), "filter for disabled variations");
card._shopState = "disabled";
page = card._renderShop();
assert(page.textContent.includes("You&Me - senza kit") && !page.textContent.includes("You&Me - con kit") && !page.textContent.includes("Pacchetto Relax"),
  "the filter shows only disabled variations");
card._shopState = "";

// The product sheet: each variation with its switch, saved as «enabled».
card._wpProduct = { id: 4097, data: { id: 4097, type: "variable", status: "publish", name: "You&Me", category_ids: [], categories: [],
  variations: [{ id: 5117, name: "con kit", regular_price: "100", sale_price: "", enabled: true },
    { id: 5118, name: "senza kit", regular_price: "80", sale_price: "", enabled: false, stock_status: "outofstock" }] } };
const plain = (v) => (v == null ? "" : String(v));
const data = card._wpProduct.data;
card._wpProduct.draft = { name: data.name, short_description: "", description: "", regular_price: "", sale_price: "", category_ids: [],
  status: "publish", stock_status: "instock", stock_quantity: "",
  variations: data.variations.map((v) => ({ id: v.id, name: v.name, sku: "", regular_price: plain(v.regular_price), sale_price: plain(v.sale_price),
    stock_status: v.stock_status || "instock", enabled: v.enabled !== false })) };
const sheet = card._renderWpProduct();
assert(sheet.textContent.includes("Varianti (2, 1 disattivata)"), "how many variations and how many disabled");
assert(sheet.textContent.includes("Disattivata") && sheet.textContent.includes("Esaurito"), "state and stock of each variation");
const boxes = all(sheet).filter((n) => n.tagName === "INPUT" && n.attrs && n.attrs.type === "checkbox");
assert(boxes.length === 2, "one switch per variation");
const fire = (node, type, target) => { const h = node.listeners && node.listeners[type]; if (h) h[0]({ target, currentTarget: node }); };
fire(boxes[1], "change", { checked: true });
fire(boxes[0], "change", { checked: false });
let sent = null;
card._call = async (service, payload) => { sent = { service, payload }; };
const saveBtn = all(card._renderWpProduct()).find((n) => n.tagName === "BUTTON" && /Salva/.test(n.textContent));
assert(saveBtn, "save button");
(async () => {
  await saveBtn.listeners.click[0]({});
  assert(sent && sent.service === "wp_product_update", "saved on the site");
  const rows = sent.payload.variations;
  assert(rows.length === 2 && rows.find((r) => r.id === 5118).enabled === true && rows.find((r) => r.id === 5117).enabled === false,
    "the switches are sent as enabled true/false");
  console.log("card_wp_variations_test: ok");
})().catch((e) => { console.error(e); process.exit(1); });

// Run: node tests/frontend/card_shop_test.js custom_components/spa_booking/frontend/spa-booking-card.js
// 2.7.0: Configurazione › Shop online, products paired with treatments.
"use strict";
const { loadCard, assert, all, byClass } = require("./card_harness");

const Card = loadCard(process.argv[2]);
const card = Object.create(Card.prototype);
card._me = { level: "admin" };
card._userLevel = () => "admin";
card._can = () => true;
card._render = () => {};
card._searchInputRedraw = () => {};
card._lookup = { treatment: new Map([["t1", { id: "t1", name: "Ingresso Spa 90", price: 40 }]]) };
card._data = {
  treatments: [{ id: "t1", name: "Ingresso Spa 90", active: true }, { id: "t2", name: "Massaggio schiena", active: true }],
  vouchers: [{ id: "v1", code: "FILIPPO-ISYM-1", source: "wordpress", status: "active", people: [], value: 80, wp_product_name: "You&Me" }],
  settings: { wp_enabled: true, wp_url: "https://shop.example.it", wp_secret: "abc", wp_last_sync: "2026-11-12T20:00:00Z", wp_last_result: "2 codici letti",
    wp_products: [{ key: "4097:5118", name: "You&Me - senza kit", sku: "ISYM-SK", price: 80 }, { key: "5000:0", name: "Pacchetto Relax", sku: "PR", price: 120 }],
    wp_product_map: {} },
};
let page = card._renderShop();
assert(page.textContent.includes("0 di 2 prodotti abbinati"), "nothing paired yet");
assert(page.textContent.includes("abc") && page.textContent.includes("/api/spa_booking/wp/notify"), "key and notify address for the admin");
// Pair the package with two treatments and two people.
const chip = (name) => all(page).find((n) => n.attrs && n.attrs.class && n.attrs.class.startsWith("shop-chip") && n.textContent === name);
chip("Ingresso Spa 90").listeners.click[0]();
page = card._renderShop();
chip("Massaggio schiena").listeners.click[0]();
assert(JSON.stringify(card._shopDraft.wp_product_map["4097:5118"].treatment_ids) === '["t1","t2"]', "more treatments for one product");
page = card._renderShop();
assert(page.textContent.includes("1 di 2 prodotti abbinati"), "count updated");
// The voucher from the site shows its badge and value.
const row = card._voucherRow(card._data.vouchers[0], true);
assert(row.textContent.includes("Sito") && row.textContent.includes("da abbinare"), "site badge and unpaired product");
assert(card._voucherValue(card._data.vouchers[0]) === 80, "value from the shop");

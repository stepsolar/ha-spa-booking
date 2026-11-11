// Run: node tests/frontend/card_promo_test.js custom_components/spa_booking/frontend/spa-booking-card.js
// 2.3.9: promo themes on their next date, and the saved-promo list.
"use strict";
const vm = require("vm");
const { loadCard, assert, all, byClass, sandbox } = require("./card_harness");

const Card = loadCard(process.argv[2]);
const get = (name) => vm.runInContext(name, sandbox);
const PROMO_THEMES = get("PROMO_THEMES");
const promoFromTheme = get("promoFromTheme");
const easterOf = get("easterOf");
const ymd = get("ymd");
const theme = (id) => PROMO_THEMES.find((t) => t.id === id);

assert(ymd(easterOf(2026)) === "2026-04-05" && ymd(easterOf(2027)) === "2027-03-28", "Easter dates");
const today = new Date(2026, 10, 11); // 11 Nov 2026
const bf = promoFromTheme(theme("blackfriday"), "Hotel", today);
assert(bf.date === "2026-11-27" && bf.time === "09:00" && bf.expiry === "2026-11-30", "Black Friday 2026 on Friday 27");
assert(bf.code === "BLACKFRIDAY26" && bf.mode === "giorno", "code with the year, one given day");
const xmas = promoFromTheme(theme("natale"), "Hotel", today);
assert(xmas.date === "2026-12-01" && xmas.expiry === "2027-01-06" && xmas.name === "Natale 2026", "Christmas this year");
const easter = promoFromTheme(theme("pasqua"), "Hotel", today);
assert(easter.date === "2027-03-11" && easter.expiry === "2027-04-05", "Easter next year");
const summer = promoFromTheme(theme("estate"), "Hotel", new Date(2026, 6, 20));
assert(summer.date === "2026-07-20" && summer.expiry === "2026-09-15", "a running season starts today");
const bday = promoFromTheme(theme("compleanno"), "Hotel", today);
assert(bday.mode === "adesso" && bday.expiry === "2027-01-10", "by hand, valid 60 days");
assert(PROMO_THEMES.every((t) => promoFromTheme(t, "Hotel Prova", today).message.includes("Lo Staff - Hotel Prova")), "every text signed by the hotel");
assert(PROMO_THEMES.every((t) => t.text.includes("{codice_promo}") && t.text.includes("{scadenza_promo}")), "every text has code and expiry");

// The list and the editor.
const card = Object.create(Card.prototype);
card._me = { level: "admin" };
card._data = { settings: { promos: [
  { id: "a", name: "Black Friday 2026", theme: "blackfriday", mode: "giorno", date: "2099-11-27", time: "09:00", code: "BF", expiry: "2099-11-30", message: "x", sent_count: 0 },
  { id: "b", name: "Vecchia", mode: "adesso", expiry: "2000-01-01", message: "y", sent_count: 3 },
] }, clients: [], promo_vouchers: [] };
card._render = () => {};
card._can = () => true;
const page = card._renderPromo();
const rows = byClass(page, "pm-row");
assert(rows.length === 2, "two saved promos listed");
const text = (node) => node.textContent;
assert(text(rows[0]).includes("Programmata") && text(rows[0]).includes("alle 09:00"), "scheduled one shows its start");
assert(text(rows[1]).includes("Scaduta"), "expired one says so");
assert(byClass(page, "pm-theme").length === PROMO_THEMES.length, "every theme in the gallery");
card._promoNew(theme("natale"));
assert(card._promoDraft.promos.length === 3 && card._promoEditId === card._promoDraft.promos[0].id, "new promo opened");
assert(card._promoDraft.promos[0].theme === "natale", "from the theme");

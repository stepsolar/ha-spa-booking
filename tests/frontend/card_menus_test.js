// Run: node tests/frontend/card_menus_test.js custom_components/spa_booking/frontend/spa-booking-card.js
// 3.21.0: the menus follow what the server says (role + administrator's eyes).
"use strict";
const { loadCard, assert } = require("./card_harness");

const Card = loadCard(process.argv[2]);
const card = Object.create(Card.prototype);
card._hass = { config: { version: "2026.11" }, user: { id: "u1" } };
card._data = { settings: { permissions: { u1: "operator" } } };
card._me = { level: "operator", menus: ["agenda", "nuovo", "nuovo.appuntamento", "clienti", "config", "config.trattamenti", "config.blocchi"] };
const tabs = card._visibleTabs().map((t) => t.id);
assert(JSON.stringify(tabs) === JSON.stringify(["agenda", "nuovo", "clienti", "config"]), tabs.join());
assert(card._visibleNuovoTabs().map((t) => t.id).join() === "appuntamento", "nuovo sub");
assert(card._visibleCfgTabs().map((t) => t.id).join() === "trattamenti,blocchi", card._visibleCfgTabs().map((t) => t.id).join());
card._tab = "config"; card._cfgTab = "trattamenti";
assert(card._can("config") === true, "usable where turned on");
card._cfgTab = "accessi";
assert(card._can("config") === false, "accessi locked");
card._tab = "agenda";
assert(card._can("config") === false, "not outside configuration");
// Without the server's list: the role.
card._me = { level: "operator" };
assert(card._visibleTabs().map((t) => t.id).includes("whatsapp"), "role default");
assert(card._visibleCfgTabs().length === 0, "no config by default");
// The administrator always sees everything, Accessi included.
card._me = { level: "admin", menus: [] };
assert(card._visibleCfgTabs().some((t) => t.id === "accessi"), "admin accessi");
console.log("ok");

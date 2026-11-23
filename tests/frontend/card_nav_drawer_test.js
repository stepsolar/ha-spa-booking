// Run: node tests/frontend/card_nav_drawer_test.js custom_components/spa_booking/frontend/spa-booking-card.js
// 3.21.1: on a phone the hamburger opens Spa Booking's menu.
"use strict";
const { loadCard, assert } = require("./card_harness");

const Card = loadCard(process.argv[2]);
const card = Object.create(Card.prototype);
card._config = {};
card._data = { settings: { card_title: "Spa Il Marchese" } };
card._me = { level: "admin", name: "Stefano" };
card._tab = "agenda";
let rendered = 0;
card._render = () => { rendered += 1; };
let haMenu = 0;
card._toggleHaMenu = () => { haMenu += 1; };
card._resetForm = () => {};

// Inside Home Assistant on a phone: the drawer, with the Home Assistant row.
card._hass = { config: { version: "2026.11.1" }, user: { id: "u", name: "Stefano" } };
card._isPhone = () => true;
card._onMenuButton();
assert(card._navOpen === true && haMenu === 0, "phone: Spa Booking menu");
let text = card._renderNavDrawer().textContent;
assert(text.includes("Configurazione") && text.includes("Menu di Home Assistant"), text);
card._goTab("clienti");
assert(card._tab === "clienti" && card._navOpen === false, "tap closes and opens the tab");
// Spa Booking Web: no Home Assistant row.
card._hass = { config: { version: "Spa Booking Web 0.1.0" }, user: { id: "u", name: "Stefano" } };
text = card._renderNavDrawer().textContent;
assert(!text.includes("Home Assistant"), text);
// A computer: Home Assistant's menu as before, no drawer.
card._hass = { config: { version: "2026.11.1" }, user: { id: "u", name: "Stefano" } };
card._isPhone = () => false;
card._navOpen = false;
card._onMenuButton();
assert(haMenu === 1 && !card._navOpen, "desktop unchanged");
console.log("ok");

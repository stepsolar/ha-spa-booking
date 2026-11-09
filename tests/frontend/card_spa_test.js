// Run: node tests/frontend/card_spa_test.js custom_components/spa_booking/frontend/spa-booking-card.js
// The Spa tab tiles: sections by kind, colours by kind, one brightness bar,
// the thermostat, sensors and missing entities.
"use strict";
const { loadCard, assert, byClass } = require("./card_harness");

const Card = loadCard(process.argv[2]);

const STATES = {
  "light.relax": { state: "on", attributes: { brightness: 178, supported_color_modes: ["brightness"], friendly_name: "Sala relax" } },
  "light.esterno": { state: "off", attributes: { supported_color_modes: ["onoff"], friendly_name: "Esterno" } },
  "climate.sauna": { state: "heat", attributes: { current_temperature: 78, temperature: 85, hvac_action: "heating", friendly_name: "Sauna" } },
  "switch.idro": { state: "on", attributes: { friendly_name: "Idromassaggio" } },
  "sensor.acqua": { state: "29.46", attributes: { unit_of_measurement: "°C", friendly_name: "Acqua piscina" } },
};

function makeCard(tiles, settings = {}) {
  const card = Object.create(Card.prototype);
  card._hass = { states: STATES };
  card._data = { settings: { spa_entities: tiles, ...settings } };
  card._spaEditMode = false;
  card._busySpa = false;
  card._render = () => {};
  card.calls = [];
  card._spaCall = (domain, service, id, data) => card.calls.push([domain, service, id, data || {}]);
  card._moreInfo = (id) => card.calls.push(["more-info", id]);
  card._spaWireDrag = () => {};
  return card;
}
const tile = (entity_id, extra = {}) => ({ entity_id, ...extra });
const click = (node) => (node.listeners.click || []).forEach((fn) => fn({ stopPropagation() {} }));

// Sections by kind, with summaries.
let card = makeCard([
  tile("light.relax"), tile("switch.idro"), tile("climate.sauna"),
  tile("light.esterno"), tile("sensor.acqua"), tile("climate.sparito"),
]);
let view = card._renderSpaGrid();
const heads = byClass(view, "spa-section-head").map((h) => h.textContent);
assert(heads.length === 3, "three sections");
assert(heads[0].startsWith("Luci") && heads[0].includes("1 accesa su 2"), "lights section with summary");
assert(heads[1].startsWith("Clima") && heads[1].includes("1 attivo"), "climate section with summary");
assert(heads[2].startsWith("Servizi e sensori") && heads[2].includes("1 acceso su 1"), "services section counts switches only");
const lightGrid = byClass(view, "spa-grid")[0];
assert(lightGrid.children.map((t) => t.attrs["data-eid"]).join() === "light.relax,light.esterno", "user order kept inside a section");

// Colour by kind.
const tiles = Object.fromEntries(byClass(view, "spa-tile").map((t) => [t.attrs["data-eid"], t.attrs.class]));
assert(tiles["light.relax"].includes("spa-kind--light") && tiles["light.relax"].includes(" on"), "light on: amber kind");
assert(tiles["switch.idro"].includes("spa-kind--service"), "switch: teal kind");
assert(tiles["climate.sauna"].includes("heating"), "heating thermostat marked");
assert(tiles["climate.sparito"].includes("unavailable"), "missing entity shown as unavailable, no crash");

// One brightness bar per dimmable light that is on.
const relax = byClass(view, "spa-tile").find((t) => t.attrs["data-eid"] === "light.relax");
assert(byClass(relax, "spa-tile-brightness").length === 1, "one brightness slider");
assert(relax.textContent.includes("Accesa · 70%"), "brightness in percent");
const esterno = byClass(view, "spa-tile").find((t) => t.attrs["data-eid"] === "light.esterno");
assert(byClass(esterno, "spa-tile-brightness").length === 0, "no slider on an on/off light");

// Thermostat: big temperature, target, − and + only.
const sauna = byClass(view, "spa-tile").find((t) => t.attrs["data-eid"] === "climate.sauna");
assert(byClass(sauna, "spa-clima-temp")[0].textContent === "78°", "big current temperature");
assert(sauna.textContent.includes("obiettivo 85°") && sauna.textContent.includes("Riscalda"), "target and mode label");
assert(byClass(sauna, "btn").length === 2, "only − and + buttons");
assert(sauna.attrs.style.includes("span 2"), "thermostat takes two columns");

// Sensor: value with Italian decimals and unit; a tap opens the details.
const acqua = byClass(view, "spa-tile").find((t) => t.attrs["data-eid"] === "sensor.acqua");
assert(byClass(acqua, "spa-tile-value")[0].textContent === "29,5 °C", "sensor value formatted");
click(acqua);
assert(JSON.stringify(card.calls.pop()) === JSON.stringify(["more-info", "sensor.acqua"]), "tap on a sensor opens its details");

// Tap on a light still toggles it.
card._spaToggle = (domain, id) => card.calls.push(["toggle", id]);
click(relax);
assert(JSON.stringify(card.calls.pop()) === JSON.stringify(["toggle", "light.relax"]), "tap on a light toggles it");

// Grouping off: the single grid of before.
card = makeCard([tile("light.relax"), tile("climate.sauna")], { spa_grouped: false });
view = card._renderSpaGrid();
assert(view.attrs.class.startsWith("spa-grid") && byClass(view, "spa-section-head").length === 0, "grouping off: one grid");

// Edit mode: always the flat grid, with the add tile, drag and ⋮ menu.
card = makeCard([tile("light.relax"), tile("climate.sauna")]);
card._spaEditMode = true;
card._spaAddTile = () => ({ attrs: { class: "spa-add-tile" }, walk: function* () {}, listeners: {} });
view = card._renderSpaGrid();
assert(view.attrs.class === "spa-grid editing", "edit mode: flat grid");
assert(byClass(view, "spa-tile-menu").length === 2, "edit mode: ⋮ on every tile, thermostat included");

console.log("ALL CARD SPA TESTS PASSED");

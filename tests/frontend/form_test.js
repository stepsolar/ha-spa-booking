// Run: node tests/frontend/form_test.js custom_components/spa_booking/frontend/spa-booking-form.txt
// Minimal DOM stub to exercise the WordPress form script end to end.
"use strict";
const fs = require("fs");
const html = fs.readFileSync(process.argv[2], "utf8");
const script = html.match(/<script>([\s\S]*?)<\/script>/)[1];

// WordPress rewrites "&" and splits blocks on blank lines: both would break
// the pasted form, so neither may appear inside <script> or <style>.
for (const [, , body] of html.matchAll(/<(script|style)>([\s\S]*?)<\/\1>/g)) {
  if (body.includes("&")) { console.error("FAIL: '&' inside a script/style block"); process.exit(1); }
  if (/\n\s*\n/.test(body)) { console.error("FAIL: blank line inside a script/style block"); process.exit(1); }
}

class Node {
  constructor(tag) {
    this.tagName = tag.toUpperCase(); this.children = []; this.parent = null;
    this.attrs = {}; this.listeners = {}; this._text = ""; this.className = "";
    this.style = {}; this.hidden = false; this.disabled = false; this._value = "";
    this.selected = false; this.type = "";
  }
  appendChild(c) { c.parent = this; this.children.push(c); return c; }
  set innerHTML(v) { this.children = []; if (v) this._text = String(v).replace(/<[^>]+>/g, ""); else this._text = ""; }
  get innerHTML() { return ""; }
  set textContent(v) { this.children = []; this._text = String(v); }
  get textContent() { return this._text + this.children.map((c) => c.textContent).join(""); }
  setAttribute(k, v) { this.attrs[k] = v; if (k === "id") this.id = v; }
  addEventListener(ev, fn) { (this.listeners[ev] = this.listeners[ev] || []).push(fn); }
  fire(ev, extra) { (this.listeners[ev] || []).forEach((fn) => fn(Object.assign({ preventDefault() {} }, extra || {}))); }
  get value() {
    if (this.tagName === "SELECT") {
      const opts = this.children.filter((c) => c.tagName === "OPTION");
      const sel = opts.filter((o) => o.selected).pop() || opts[0];
      return sel ? sel.value : "";
    }
    return this._value;
  }
  set value(v) {
    if (this.tagName === "SELECT") {
      this.children.forEach((o) => { o.selected = String(o.value) === String(v); });
    } else if (this.tagName === "OPTION") { this._value = String(v); } else { this._value = String(v); }
  }
  *walk() { for (const c of this.children) { yield c; yield* c.walk(); } }
  querySelector(sel) { return this.querySelectorAll(sel)[0] || null; }
  querySelectorAll(sel) {
    const all = [...this.walk()];
    let out;
    if (sel.startsWith("#")) out = all.filter((n) => n.id === sel.slice(1));
    else if (sel.startsWith(".")) out = all.filter((n) => (" " + n.className + " ").includes(" " + sel.slice(1) + " "));
    else out = all.filter((n) => n.tagName === sel.toUpperCase());
    return out;
  }
}

// Build the static widget from the ids the script needs.
const root = new Node("div"); root.id = "sbw-widget";
const ids = { "sbw-date": "input", "sbw-people": "select", "sbw-persons": "div", "sbw-voucher": "input",
  "sbw-voucher-check": "button", "sbw-voucher-info": "span", "sbw-first": "input", "sbw-last": "input",
  "sbw-phone": "input", "sbw-email": "input", "sbw-notes": "textarea", "sbw-send": "button",
  "sbw-status": "span", "sbw-website": "input", "sbw-form": "div", "sbw-done": "div" };
const els = {};
for (const [id, tag] of Object.entries(ids)) { const n = new Node(tag); n.id = id; root.appendChild(n); els[id] = n; }
for (let i = 1; i <= 6; i++) { const o = new Node("option"); o.value = String(i); els["sbw-people"].appendChild(o); }
els["sbw-people"].children[0].selected = true;

global.document = {
  getElementById: (id) => (id === "sbw-widget" ? root : root.querySelector("#" + id)),
  createElement: (t) => new Node(t),
};
global.window = {};
const calls = [];
const VOUCHER = { code: "VCH-AAAA2222", people: [{ name: "Anna", treatment_ids: ["t1", "t2"] }] };
global.fetch = (url, opts) => {
  calls.push({ url, opts });
  let body;
  if (url.endsWith("/treatments")) body = { treatments: [{ id: "t1", name: "Massaggio", duration_min: 60 }, { id: "t2", name: "Sauna", duration_min: 30 }] };
  else if (url.includes("/treatments?code=")) body = { treatments: [], voucher: VOUCHER };
  else if (url.includes("/availability")) body = { slots: [{ time: "10:00" }, { time: "11:00" }] };
  else if (url.endsWith("/requests")) body = { code: "R1234", status: "pending" };
  return Promise.resolve({ ok: true, status: 200, text: () => Promise.resolve(JSON.stringify(body)) });
};
const tick = () => new Promise((r) => setTimeout(r, 5));
const assert = (c, m) => { if (!c) { console.error("FAIL:", m); process.exit(1); } console.log("ok -", m); };

(async () => {
  new Function(script)();
  await tick();
  assert(window.__sbwStarted === true, "script runs to the end");
  assert(els["sbw-persons"].querySelectorAll(".sbw-person").length === 1, "one person rendered");
  // Three people.
  els["sbw-people"].value = "3"; els["sbw-people"].fire("change"); await tick();
  assert(els["sbw-persons"].querySelectorAll(".sbw-person").length === 3, "three persons after change");
  // Pick a treatment without a date: asks for date.
  const row = els["sbw-persons"].querySelectorAll(".sbw-entry")[0];
  let [tSel, hSel] = row.querySelectorAll("select");
  tSel.value = "t1"; tSel.fire("change"); await tick();
  assert(hSel.children[0].textContent.includes("data"), "asks for date first");
  els["sbw-date"].value = "2030-01-10"; els["sbw-date"].fire("change"); await tick();
  assert(hSel.children.some((o) => o.value === "10:00"), "date change refreshes slots");
  hSel.value = "10:00";
  // Voucher with one person but three selected keeps... voucher sets people to 1.
  els["sbw-voucher"].value = "vch-aaaa2222"; els["sbw-voucher-check"].fire("click"); await tick(); await tick();
  const voucherCalls = calls.filter((c) => c.url.includes("code=")).length;
  assert(voucherCalls === 1, "voucher verified once (no duplicate listener)");
  assert(els["sbw-people"].value === "1", "people set from voucher");
  const vRows = els["sbw-persons"].querySelectorAll(".sbw-entry");
  assert(vRows.length === 2, "voucher treatments pre-filled");
  assert(vRows[0].querySelectorAll("select")[0].disabled, "voucher treatment locked");
  // More people than voucher people: extra people are free rows.
  els["sbw-people"].value = "2"; els["sbw-people"].fire("change"); await tick();
  assert(els["sbw-persons"].querySelectorAll(".sbw-person").length === 2, "people beyond voucher still rendered");
  // Choose times and submit.
  for (const r of els["sbw-persons"].querySelectorAll(".sbw-entry")) { const s = r.querySelectorAll("select"); if (!s[0].value) { s[0].value = "t2"; s[0].fire("change"); } }
  await tick();
  els["sbw-persons"].querySelectorAll(".sbw-entry").forEach((r) => { r.querySelectorAll("select")[1].value = "11:00"; });
  els["sbw-first"].value = "Anna"; els["sbw-phone"].value = "333 1234567";
  els["sbw-send"].fire("click"); els["sbw-send"].fire("click"); await tick(); await tick();
  const posts = calls.filter((c) => c.opts.method === "POST");
  assert(posts.length === 1, "double click sends once");
  const payload = JSON.parse(posts[0].opts.body);
  assert(payload.entries.length === 3 && payload.voucher_code === "VCH-AAAA2222" && payload.people === 2, "payload complete");
  assert(calls.every((c) => c.opts.headers.Authorization === "Bearer INCOLLA_QUI_IL_TOKEN"), "token header sent");
  assert(els["sbw-done"].textContent.includes("R1234"), "receipt shows request code");
  console.log("ALL FORM TESTS PASSED");
})();

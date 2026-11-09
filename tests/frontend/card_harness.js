// Load the management card in Node with a tiny DOM, for the card tests.
"use strict";
const fs = require("fs");
const vm = require("vm");

class Node {
  constructor(tag) {
    this.tagName = String(tag).toUpperCase(); this.children = []; this.attrs = {};
    this.listeners = {}; this._text = ""; this.style = { setProperty(k, v) { this[k] = v; } }; this.classList = { add() {}, remove() {}, toggle() {}, contains: () => false };
  }
  appendChild(c) { this.children.push(c); return c; }
  append(...c) { c.forEach((x) => this.appendChild(x)); }
  insertBefore(c) { this.children.unshift(c); return c; }
  removeChild(c) { this.children = this.children.filter((x) => x !== c); }
  setAttribute(k, v) { this.attrs[k] = String(v); }
  getAttribute(k) { return this.attrs[k]; }
  addEventListener(ev, fn) { (this.listeners[ev] = this.listeners[ev] || []).push(fn); }
  set textContent(v) { this._text = String(v); this.children = []; }
  get textContent() { return this._text + this.children.map((c) => c.textContent).join(""); }
  set innerHTML(v) { this._text = ""; this.children = []; }
  querySelector() { return null; }
  querySelectorAll() { return []; }
  get childNodes() { return this.children; }
  get className() { return this.attrs.class || ""; }
  set className(v) { this.attrs.class = String(v); }
  *walk() { for (const c of this.children) { yield c; if (c.walk) yield* c.walk(); } }
}
class TextNode extends Node { constructor(t) { super("#text"); this._text = t; } }

let Card = null;
const sandbox = {
  console,
  Node,
  HTMLElement: class {},
  document: { createElement: (t) => new Node(t), createTextNode: (t) => new TextNode(t) },
  customElements: { get: () => undefined, define: (name, cls) => { Card = cls; } },
  window: {},
  setTimeout, clearTimeout,
};
sandbox.window = sandbox;
vm.createContext(sandbox);

function loadCard(path) {
  vm.runInContext(fs.readFileSync(path, "utf8"), sandbox, { filename: "card.js" });
  return Card;
}

const assert = (cond, msg) => { if (!cond) { console.error("FAIL:", msg); process.exit(1); } console.log("ok -", msg); };

/** Every node of a tree, the root included. */
const all = (node) => [node, ...node.walk()];
const byClass = (node, cls) => all(node).filter((n) => (" " + ((n.attrs && n.attrs.class) || "") + " ").includes(" " + cls + " "));

module.exports = { loadCard, assert, all, byClass, Node };

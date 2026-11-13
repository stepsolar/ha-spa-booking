/*
 * Spa Booking — the request form of the hotel website, in steps.
 *
 * WordPress only holds two lines:
 *
 *   <div id="spa-booking"></div>
 *   <script src="https://HOME-ASSISTANT/api/spa_booking/public/form.js"
 *           data-token="..." async></script>
 *
 * This file is served by Home Assistant, so a new version of Spa Booking
 * updates the form on the site without touching WordPress. It draws inside a
 * shadow root: the theme of the site cannot break the form and the form
 * cannot restyle the site.
 *
 * Optional attributes of the <script> tag:
 *   data-token   the token of Configurazione › Sito web (required)
 *   data-target  CSS selector of the box (default "#spa-booking"; when it is
 *                missing the form goes right after the script)
 *   data-lang    "it", "en" or "de" (default: the visitor's browser)
 *   data-accent  the main colour, e.g. "#0a84a8" (default: the setting of
 *                Configurazione › Sito web)
 */
(function () {
  "use strict";
  if (typeof fetch !== "function") return;

  var script = document.currentScript || (function () {
    var list = document.querySelectorAll('script[src*="spa_booking/public/form.js"]');
    return list[list.length - 1];
  })();
  if (!script) return;

  var API = new URL(script.src, location.href).origin + "/api/spa_booking/public";
  var TOKEN = script.getAttribute("data-token") || "";
  var MAX_PEOPLE = 6;

  // ------------------------------------------------------------- languages

  var T = {
    it: {
      step: "Passo {n} di 4",
      s1: "Quando vuoi venire?", s2: "Cosa scegliete?", s3: "I tuoi dati", s4: "Controlla e invia",
      date: "Data", people: "Persone", person: "Persona {n}",
      voucher: "Hai un voucher regalo?", voucherPh: "VCH-7K2M9Q4P", check: "Verifica",
      voucherOk: "Voucher valido fino al {d}: trattamenti già scelti.", voucherBad: "Voucher non valido o scaduto.",
      treatments: "Trattamenti", time: "Orario", noSlots: "Nessun orario libero in questa data.",
      loading: "Caricamento…", sameAs1: "Come la persona 1", fromVoucher: "dal voucher",
      first: "Nome", last: "Cognome", phone: "Telefono", phoneHint: "Ti confermiamo l'orario su WhatsApp.",
      email: "Email", notes: "Note", notesPh: "Allergie, preferenze, orario migliore…",
      total: "Totale indicativo", when: "Data", contact: "Contatto",
      partnerDiscount: "Con questo link hai lo sconto del {p}% sui trattamenti.", discount: "Sconto {p}%",
      notYet: "Non è ancora una prenotazione: la reception ti conferma l'orario su WhatsApp.",
      back: "Indietro", next: "Avanti", send: "Invia richiesta", sending: "Invio in corso…",
      sent: "Richiesta inviata", sentText: "Ti scriviamo su WhatsApp per confermare. Il codice della tua richiesta:",
      again: "Nuova richiesta",
      errDate: "Scegli la data.", errPick: "Scegli almeno un trattamento con il suo orario per ogni persona.",
      errName: "Scrivi il tuo nome.", errPhone: "Scrivi un numero di telefono: serve per confermare.",
      errSend: "Invio non riuscito. Riprova o chiamaci.", errOffline: "Connessione non riuscita. Riprova tra poco.",
      errLoad: "Il modulo non è disponibile in questo momento.",
      min: "min", required: "obbligatorio",
      pref: "Per il massaggio preferisci…", prefAny: "Indifferente", prefF: "Una massaggiatrice", prefM: "Un massaggiatore",
    },
    en: {
      step: "Step {n} of 4",
      s1: "When would you like to come?", s2: "What would you like?", s3: "Your details", s4: "Check and send",
      date: "Date", people: "Guests", person: "Guest {n}",
      voucher: "Do you have a gift voucher?", voucherPh: "VCH-7K2M9Q4P", check: "Check",
      voucherOk: "Voucher valid until {d}: treatments already chosen.", voucherBad: "The voucher is not valid or has expired.",
      pref: "For the massage you would prefer…", prefAny: "No preference", prefF: "A female therapist", prefM: "A male therapist",
      treatments: "Treatments", time: "Time", noSlots: "No free time on this date.",
      loading: "Loading…", sameAs1: "Same as guest 1", fromVoucher: "from the voucher",
      first: "First name", last: "Last name", phone: "Phone", phoneHint: "We confirm the time on WhatsApp.",
      email: "Email", notes: "Notes", notesPh: "Allergies, preferences, best time…",
      total: "Estimated total", when: "Date", contact: "Contact",
      partnerDiscount: "With this link you get {p}% off the treatments.", discount: "Discount {p}%",
      notYet: "This is not a booking yet: our reception will confirm the time on WhatsApp.",
      back: "Back", next: "Next", send: "Send request", sending: "Sending…",
      sent: "Request sent", sentText: "We will write to you on WhatsApp to confirm. Your request code:",
      again: "New request",
      errDate: "Choose a date.", errPick: "Choose at least one treatment and its time for every guest.",
      errName: "Enter your name.", errPhone: "Enter a phone number: we need it to confirm.",
      errSend: "Your request could not be sent. Try again or call us.", errOffline: "Connection failed. Try again shortly.",
      errLoad: "The form is not available right now.",
      min: "min", required: "required",
    },
    de: {
      step: "Schritt {n} von 4",
      s1: "Wann möchten Sie kommen?", s2: "Was wünschen Sie?", s3: "Ihre Daten", s4: "Prüfen und senden",
      date: "Datum", people: "Personen", person: "Person {n}",
      voucher: "Haben Sie einen Gutschein?", voucherPh: "VCH-7K2M9Q4P", check: "Prüfen",
      voucherOk: "Gutschein gültig bis {d}: Behandlungen bereits ausgewählt.", voucherBad: "Der Gutschein ist ungültig oder abgelaufen.",
      pref: "Für die Massage bevorzugen Sie…", prefAny: "Egal", prefF: "Eine Masseurin", prefM: "Einen Masseur",
      treatments: "Behandlungen", time: "Uhrzeit", noSlots: "An diesem Tag ist keine Uhrzeit frei.",
      loading: "Wird geladen…", sameAs1: "Wie Person 1", fromVoucher: "aus dem Gutschein",
      first: "Vorname", last: "Nachname", phone: "Telefon", phoneHint: "Wir bestätigen die Uhrzeit per WhatsApp.",
      email: "E-Mail", notes: "Hinweise", notesPh: "Allergien, Wünsche, beste Uhrzeit…",
      total: "Voraussichtlicher Preis", when: "Datum", contact: "Kontakt",
      partnerDiscount: "Mit diesem Link erhalten Sie {p}% Rabatt auf die Behandlungen.", discount: "Rabatt {p}%",
      notYet: "Dies ist noch keine Buchung: Die Rezeption bestätigt die Uhrzeit per WhatsApp.",
      back: "Zurück", next: "Weiter", send: "Anfrage senden", sending: "Wird gesendet…",
      sent: "Anfrage gesendet", sentText: "Wir schreiben Ihnen per WhatsApp zur Bestätigung. Ihr Anfragecode:",
      again: "Neue Anfrage",
      errDate: "Wählen Sie ein Datum.", errPick: "Wählen Sie für jede Person mindestens eine Behandlung mit Uhrzeit.",
      errName: "Geben Sie Ihren Namen ein.", errPhone: "Geben Sie eine Telefonnummer ein: Wir brauchen sie zur Bestätigung.",
      errSend: "Die Anfrage konnte nicht gesendet werden. Bitte erneut versuchen oder anrufen.", errOffline: "Keine Verbindung. Bitte gleich erneut versuchen.",
      errLoad: "Das Formular ist gerade nicht verfügbar.",
      min: "Min.", required: "Pflichtfeld",
    },
  };
  var LOCALES = { it: "it-IT", en: "en-GB", de: "de-DE" };
  var COUNTRIES = [
    ["IT", "39"], ["CH", "41"], ["DE", "49"], ["AT", "43"], ["FR", "33"], ["GB", "44"], ["US", "1"],
    ["NL", "31"], ["BE", "32"], ["ES", "34"], ["SM", "378"], ["MT", "356"], ["PL", "48"], ["CZ", "420"],
    ["DK", "45"], ["SE", "46"], ["NO", "47"], ["FI", "358"], ["IE", "353"], ["PT", "351"], ["GR", "30"],
    ["HU", "36"], ["RO", "40"], ["SI", "386"], ["HR", "385"], ["SK", "421"], ["LU", "352"], ["MC", "377"],
    ["IL", "972"], ["AE", "971"], ["RU", "7"], ["UA", "380"], ["TR", "90"], ["BR", "55"], ["AR", "54"],
    ["AU", "61"], ["CN", "86"], ["JP", "81"], ["IN", "91"], ["ZA", "27"],
  ];

  function pickLang(value) {
    var code = String(value || "").slice(0, 2).toLowerCase();
    return T[code] ? code : null;
  }

  // ----------------------------------------------------------------- state

  var host = document.querySelector(script.getAttribute("data-target") || "#spa-booking");
  if (!host) {
    host = document.createElement("div");
    script.parentNode.insertBefore(host, script.nextSibling);
  }
  var root = host.attachShadow ? host.attachShadow({ mode: "open" }) : host;

  var state = {
    lang: pickLang(script.getAttribute("data-lang")) || pickLang(navigator.language) || "it",
    step: 1,
    date: "",
    people: 1,
    voucherCode: "",
    voucher: null,
    voucherMsg: "",
    persons: [{ picks: [] }],
    first: "", last: "", cc: "39", phone: "", email: "", notes: "",
    error: "",
    sending: false,
    code: "",
  };
  var config = { treatments: [], showPrices: false, accent: "", maxDays: 60, title: "" };
  var slotCache = {};

  function t(key, values) {
    var text = (T[state.lang] || T.it)[key] || T.it[key] || key;
    Object.keys(values || {}).forEach(function (name) { text = text.split("{" + name + "}").join(values[name]); });
    return text;
  }

  // ------------------------------------------------------------------- api

  function api(path, options) {
    options = options || {};
    var headers = { Authorization: "Bearer " + TOKEN };
    if (options.body) headers["Content-Type"] = "application/json";
    return fetch(API + path, {
      method: options.method || "GET",
      headers: headers,
      body: options.body ? JSON.stringify(options.body) : undefined,
      mode: "cors",
      cache: "no-store",
    }).then(function (response) {
      return response.text().then(function (raw) {
        var data = null;
        try { data = raw ? JSON.parse(raw) : null; } catch (e) { data = null; }
        if (!response.ok) {
          var failure = new Error((data && data.message) || "HTTP " + response.status);
          failure.status = response.status;
          throw failure;
        }
        return data;
      });
    }, function () {
      var offline = new Error("offline");
      offline.status = 0;
      throw offline;
    });
  }

  function slots(treatmentId) {
    var key = state.date + "|" + treatmentId;
    if (!slotCache[key]) {
      slotCache[key] = { loading: true, list: [] };
      api("/availability?date=" + encodeURIComponent(state.date) + "&treatment_id=" + encodeURIComponent(treatmentId))
        .then(function (data) { slotCache[key] = { loading: false, list: (data && data.slots) || [] }; render(); })
        .catch(function () { slotCache[key] = { loading: false, list: [] }; render(); });
    }
    return slotCache[key];
  }

  // --------------------------------------------------------------- helpers

  function h(tag, attrs) {
    var node = document.createElement(tag);
    Object.keys(attrs || {}).forEach(function (key) {
      var value = attrs[key];
      if (value === null || value === undefined || value === false) return;
      if (key.slice(0, 2) === "on") node.addEventListener(key.slice(2), value);
      else if (key === "value") node.value = value;
      else if (key === "text") node.textContent = value;
      else node.setAttribute(key, value === true ? "" : value);
    });
    for (var i = 2; i < arguments.length; i++) {
      var child = arguments[i];
      if (child === null || child === undefined || child === false) continue;
      if (Array.isArray(child)) child.forEach(function (c) { if (c) node.appendChild(c); });
      else node.appendChild(typeof child === "string" ? document.createTextNode(child) : child);
    }
    return node;
  }

  function treatment(id) {
    for (var i = 0; i < config.treatments.length; i++) if (config.treatments[i].id === id) return config.treatments[i];
    return null;
  }

  function money(value) {
    try {
      return new Intl.NumberFormat(LOCALES[state.lang], { style: "currency", currency: "EUR" }).format(value);
    } catch (e) { return value + " €"; }
  }

  function longDate(iso) {
    if (!iso) return "";
    var d = new Date(iso + "T12:00:00");
    try {
      return d.toLocaleDateString(LOCALES[state.lang], { weekday: "long", day: "numeric", month: "long" });
    } catch (e) { return iso; }
  }

  function plainDate(iso) {
    if (!iso) return "";
    try {
      return new Date(iso + "T12:00:00").toLocaleDateString(LOCALES[state.lang], { day: "numeric", month: "long", year: "numeric" });
    } catch (e) { return iso; }
  }

  function flag(iso) {
    return String.fromCodePoint.apply(null, iso.split("").map(function (c) { return 0x1f1a5 + c.charCodeAt(0); }));
  }

  function today(offset) {
    var d = new Date();
    d.setDate(d.getDate() + (offset || 0));
    return d.getFullYear() + "-" + String(d.getMonth() + 1).padStart(2, "0") + "-" + String(d.getDate()).padStart(2, "0");
  }

  function setPeople(count) {
    state.people = Math.max(1, Math.min(MAX_PEOPLE, count));
    while (state.persons.length < state.people) state.persons.push({ picks: [] });
    state.persons.length = state.people;
  }

  function pctText(value) {
    return String(Math.round(value * 100) / 100).replace(".", state.lang === "en" ? "." : ",");
  }

  function total() {
    var sum = 0;
    state.persons.forEach(function (person) {
      person.picks.forEach(function (pick) {
        var item = treatment(pick.id);
        if (item && item.price && !pick.voucher) sum += Number(item.price) || 0;
      });
    });
    return sum;
  }

  // ------------------------------------------------------------- validation

  function problem(step) {
    if (step === 1 && !state.date) return t("errDate");
    if (step === 2) {
      var bad = state.persons.some(function (person) {
        return !person.picks.length || person.picks.some(function (pick) { return !pick.time; });
      });
      if (bad) return t("errPick");
    }
    if (step === 3) {
      if (!state.first.trim() && !state.last.trim()) return t("errName");
      if (state.phone.replace(/\D/g, "").length < 6) return t("errPhone");
    }
    return "";
  }

  function go(delta) {
    if (delta > 0) {
      var issue = problem(state.step);
      if (issue) { state.error = issue; render(); return; }
    }
    state.error = "";
    state.step = Math.max(1, Math.min(4, state.step + delta));
    render();
    try { host.scrollIntoView({ behavior: "smooth", block: "start" }); } catch (e) { /* old browser */ }
  }

  function checkVoucher() {
    var code = state.voucherCode.trim().toUpperCase();
    if (!code) return;
    state.voucherMsg = t("loading");
    render();
    api("/treatments?code=" + encodeURIComponent(code)).then(function (data) {
      var voucher = data && data.voucher;
      if (!voucher) throw new Error("bad");
      state.voucher = voucher;
      var people = (voucher.people || []).length || 1;
      setPeople(Math.max(state.people, people));
      (voucher.people || []).forEach(function (person, index) {
        state.persons[index].picks = (person.treatment_ids || []).map(function (id) {
          return { id: id, time: "", voucher: true };
        });
      });
      if (!state.first && voucher.recipient_name) {
        var parts = voucher.recipient_name.split(" ");
        state.first = parts.shift() || "";
        state.last = parts.join(" ");
      }
      state.voucherMsg = t("voucherOk", { d: plainDate(voucher.expires_on) || voucher.expires_on || "" });
      render();
    }).catch(function () {
      state.voucher = null;
      state.voucherMsg = t("voucherBad");
      render();
    });
  }

  function send() {
    if (state.sending) return;
    if (root.querySelector && root.querySelector("#sb-website") && root.querySelector("#sb-website").value) return;
    var entries = [];
    state.persons.forEach(function (person, index) {
      person.picks.forEach(function (pick) {
        var entry = { treatment_id: pick.id, time: pick.time, person: index };
        var item = treatment(pick.id);
        if (item && item.gender_choice && person.pref) entry.therapist_preference = person.pref;
        entries.push(entry);
      });
    });
    var phone = state.phone.trim();
    if (!/^(\+|00)/.test(phone)) phone = "+" + state.cc + " " + phone;
    state.sending = true;
    state.error = "";
    render();
    api("/requests", { method: "POST", body: {
      date: state.date,
      entries: entries,
      people: state.people,
      first_name: state.first.trim(),
      last_name: state.last.trim(),
      phone: phone,
      email: state.email.trim(),
      notes: state.notes.trim(),
      voucher_code: state.voucher ? state.voucher.code : "",
      partner_code: partnerCode(),
      language: state.lang,
    } }).then(function (data) {
      state.sending = false;
      state.code = (data && data.code) || "";
      state.step = 5;
      render();
    }).catch(function (err) {
      state.sending = false;
      if (err.status === 0) state.error = t("errOffline");
      else if (state.lang === "it" && err.status === 400) state.error = err.message;
      else state.error = t("errSend");
      render();
    });
  }

  // The partner who sent the guest (2.5.0): ?partner=CODE on the page,
  // remembered for 30 days in this browser in case she comes back later.
  function partnerCode() {
    var code = "";
    try { code = (new URLSearchParams(window.location.search).get("partner") || "").trim().toUpperCase(); } catch (e) { code = ""; }
    try {
      if (code) {
        window.localStorage.setItem("spaBookingPartner", JSON.stringify({ code: code, at: Date.now() }));
      } else {
        var saved = JSON.parse(window.localStorage.getItem("spaBookingPartner") || "null");
        if (saved && saved.code && Date.now() - saved.at < 30 * 86400000) code = saved.code;
      }
    } catch (e) { /* storage blocked: the link alone counts */ }
    return code.slice(0, 20);
  }
  partnerCode();

  // ---------------------------------------------------------------- render

  var CSS = [
    ":host{all:initial;display:block}",
    "*{box-sizing:border-box}",
    ".sb{--a:" + "var(--sb-accent,#0a84a8)" + ";font:15px/1.45 system-ui,-apple-system,'Segoe UI',Roboto,sans-serif;color:#1f2328;max-width:620px;margin:0 auto;background:#fff;border:1px solid #e3e6ea;border-radius:18px;padding:22px 22px 18px;text-align:left}",
    ".top{display:flex;align-items:center;gap:10px;margin-bottom:12px}",
    ".bars{flex:1;display:flex;gap:6px}.bars i{flex:1;height:4px;border-radius:2px;background:#e3e6ea}.bars i.on{background:var(--a)}",
    ".langs{display:flex;gap:2px;font-size:12px}.langs button{border:0;background:none;padding:4px 6px;border-radius:6px;color:#5f656b;cursor:pointer;font:inherit}.langs button.on{background:#eef5f8;background:color-mix(in srgb,var(--a) 12%,#fff);color:var(--a);font-weight:600}",
    ".lbl{font-size:12px;color:#5f656b;margin:0 0 4px}",
    "h2{font-size:20px;font-weight:600;margin:0 0 16px;letter-spacing:-.01em}",
    "input,select,textarea{width:100%;font:inherit;color:inherit;padding:10px 12px;border:1px solid #cfd5db;border-radius:10px;background:#fff}",
    "input:focus,select:focus,textarea:focus{outline:none;border-color:var(--a);box-shadow:0 0 0 3px rgba(10,132,168,.15);box-shadow:0 0 0 3px color-mix(in srgb,var(--a) 20%,transparent)}",
    ".grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:12px}",
    ".field{margin-bottom:12px}",
    ".stepper{display:flex;align-items:center;gap:14px}.stepper button{width:40px;height:40px;border-radius:50%;border:1px solid #cfd5db;background:#fff;font-size:20px;cursor:pointer;color:inherit}.stepper b{font-size:20px;min-width:20px;text-align:center}",
    ".row{display:flex;gap:8px}.row>*{min-width:0}.row>.btn{flex:0 0 auto}",
    ".btn{font:inherit;font-weight:600;padding:11px 18px;border-radius:10px;border:1px solid #cfd5db;background:#fff;color:inherit;cursor:pointer}",
    ".btn.pri{background:var(--a);border-color:var(--a);color:#fff}.btn[disabled]{opacity:.6;cursor:default}",
    ".hint{font-size:13px;color:#5f656b;margin:6px 0 0}.ok{color:#2e7d32}.bad{color:#c62828}",
    ".promo{margin:8px 0 4px;padding:10px 12px;border-radius:10px;background:#fff6e0;color:#6b4a00;font-size:14px}",
    ".person{border:1px solid #e3e6ea;border-radius:14px;padding:14px;margin-bottom:12px}",
    ".phead{display:flex;justify-content:space-between;align-items:center;margin-bottom:10px;font-weight:600}",
    ".link{border:0;background:none;color:var(--a);font:inherit;font-size:13px;cursor:pointer;padding:0}",
    ".cards{display:grid;grid-template-columns:repeat(auto-fill,minmax(140px,1fr));gap:8px}",
    ".card{border:1px solid #cfd5db;border-radius:12px;padding:10px 12px;background:#fff;text-align:left;cursor:pointer;font:inherit;color:inherit}",
    ".card small{display:block;color:#5f656b;font-size:12px;margin-top:2px}",
    ".card.on{border:2px solid var(--a);background:#eef5f8;background:color-mix(in srgb,var(--a) 10%,#fff);padding:9px 11px}.card.lock{cursor:default}",
    ".cat{font-size:11px;font-weight:600;letter-spacing:.06em;text-transform:uppercase;color:#5f656b;margin:12px 0 6px}",
    ".times{margin-top:10px;padding-top:10px;border-top:1px dashed #e3e6ea}",
    ".tname{font-size:13px;font-weight:600;margin-bottom:6px}",
    ".chips{display:flex;flex-wrap:wrap;gap:6px}.chip{border:1px solid #cfd5db;border-radius:999px;padding:6px 13px;font:inherit;font-size:14px;background:#fff;color:inherit;cursor:pointer}",
    ".chip.on{background:var(--a);border-color:var(--a);color:#fff}",
    ".sum{border:1px solid #e3e6ea;border-radius:12px;overflow:hidden}.sum div{display:flex;justify-content:space-between;gap:12px;padding:9px 12px;border-top:1px solid #e3e6ea;font-size:14px}.sum div:first-child{border-top:0}.sum span:first-child{color:#5f656b}.sum span:last-child{text-align:right}",
    ".nav{display:flex;justify-content:space-between;align-items:center;margin-top:18px;gap:10px}",
    ".err{color:#c62828;font-size:14px;margin-top:10px;min-height:1px}",
    ".done{text-align:center;padding:12px 0}.tick{width:56px;height:56px;border-radius:50%;background:#e8f5e9;color:#2e7d32;font-size:30px;display:inline-flex;align-items:center;justify-content:center}",
    ".code{display:inline-block;margin:10px 0 16px;padding:8px 20px;font-size:24px;font-weight:700;letter-spacing:.08em;border:2px dashed #cfd5db;border-radius:12px;font-family:ui-monospace,Menlo,monospace}",
    ".ph{flex-wrap:wrap}.ph select{flex:0 0 108px}.ph input{flex:1 1 140px;min-width:0}",
    ".honey{position:absolute;left:-9999px;width:1px;height:1px;overflow:hidden}",
    "@media(max-width:520px){.sb{padding:18px 14px;border-radius:14px}h2{font-size:18px}.nav .btn{padding:11px 14px}}",
  ].join("\n");

  function render() {
    root.innerHTML = "";
    var style = document.createElement("style");
    style.textContent = CSS;
    root.appendChild(style);
    var box = h("div", { class: "sb", lang: state.lang });
    if (config.accent) box.style.setProperty("--sb-accent", config.accent);
    var accent = script.getAttribute("data-accent");
    if (accent) box.style.setProperty("--sb-accent", accent);
    root.appendChild(box);

    var langs = h("div", { class: "langs", role: "group", "aria-label": "Lingua / Language / Sprache" },
      ["it", "en", "de"].map(function (code) {
        return h("button", {
          type: "button", class: state.lang === code ? "on" : "", "aria-pressed": state.lang === code ? "true" : "false",
          onclick: function () { state.lang = code; render(); },
        }, code.toUpperCase());
      }));

    if (state.step === 5) {
      box.appendChild(h("div", { class: "top" }, h("div", { class: "bars" }), langs));
      box.appendChild(h("div", { class: "done", role: "status" },
        h("div", { class: "tick", "aria-hidden": "true" }, "✓"),
        h("h2", { style: "margin:12px 0 6px" }, t("sent")),
        h("p", { class: "hint" }, t("sentText")),
        state.code ? h("div", { class: "code" }, state.code) : null,
        h("div", null, h("button", { type: "button", class: "btn", onclick: reset }, t("again")))));
      return;
    }

    box.appendChild(h("div", { class: "top" },
      h("div", { class: "bars", "aria-hidden": "true" },
        [1, 2, 3, 4].map(function (n) { return h("i", { class: n <= state.step ? "on" : "" }); })),
      langs));
    box.appendChild(h("p", { class: "lbl" }, t("step", { n: state.step })));
    if (config.partnerDiscount > 0) {
      box.appendChild(h("p", { class: "promo" }, "🎁 " + t("partnerDiscount", { p: pctText(config.partnerDiscount) })));
    }

    if (!config.treatments.length && config.error) {
      box.appendChild(h("p", { class: "err" }, config.error));
      return;
    }

    if (state.step === 1) stepWhen(box);
    if (state.step === 2) stepWhat(box);
    if (state.step === 3) stepWho(box);
    if (state.step === 4) stepCheck(box);

    box.appendChild(h("div", { class: "err", role: "alert" }, state.error));
    box.appendChild(h("div", { class: "nav" },
      state.step > 1 ? h("button", { type: "button", class: "btn", onclick: function () { go(-1); } }, "← " + t("back")) : h("span"),
      state.step < 4
        ? h("button", { type: "button", class: "btn pri", onclick: function () { go(1); } }, t("next") + " →")
        : h("button", { type: "button", class: "btn pri", disabled: state.sending, onclick: send }, state.sending ? t("sending") : t("send"))));
  }

  function stepWhen(box) {
    box.appendChild(h("h2", null, t("s1")));
    box.appendChild(h("div", { class: "grid" },
      h("div", { class: "field" },
        h("p", { class: "lbl" }, t("date")),
        h("input", {
          type: "date", value: state.date, min: today(0), max: today(config.maxDays),
          "aria-label": t("date"),
          onchange: function (e) { state.date = e.target.value; state.persons.forEach(function (p) { p.picks.forEach(function (x) { x.time = ""; }); }); state.error = ""; },
        })),
      h("div", { class: "field" },
        h("p", { class: "lbl" }, t("people")),
        h("div", { class: "stepper" },
          h("button", { type: "button", "aria-label": "−", onclick: function () { setPeople(state.people - 1); render(); } }, "−"),
          h("b", null, String(state.people)),
          h("button", { type: "button", "aria-label": "+", onclick: function () { setPeople(state.people + 1); render(); } }, "+")))));
    box.appendChild(h("p", { class: "lbl", style: "margin-top:4px" }, t("voucher")));
    box.appendChild(h("div", { class: "row" },
      h("input", {
        value: state.voucherCode, placeholder: t("voucherPh"), autocomplete: "off", "aria-label": t("voucher"),
        style: "text-transform:uppercase",
        oninput: function (e) { state.voucherCode = e.target.value; },
        onkeydown: function (e) { if (e.key === "Enter") checkVoucher(); },
      }),
      h("button", { type: "button", class: "btn", onclick: checkVoucher }, t("check"))));
    if (state.voucherMsg) {
      box.appendChild(h("p", { class: "hint " + (state.voucher ? "ok" : "bad") }, state.voucherMsg));
    }
  }

  function stepWhat(box) {
    box.appendChild(h("h2", null, t("s2")));
    var groups = {};
    var order = [];
    config.treatments.forEach(function (item) {
      var cat = item.category_name || "";
      if (!groups[cat]) { groups[cat] = []; order.push(cat); }
      groups[cat].push(item);
    });
    state.persons.forEach(function (person, index) {
      var card = h("div", { class: "person" });
      card.appendChild(h("div", { class: "phead" },
        h("span", null, state.people > 1 ? t("person", { n: index + 1 }) : t("treatments")),
        index > 0 ? h("button", {
          type: "button", class: "link",
          onclick: function () {
            person.picks = state.persons[0].picks.map(function (p) { return { id: p.id, time: p.time, voucher: false }; });
            render();
          },
        }, t("sameAs1")) : null));
      order.forEach(function (cat) {
        if (order.length > 1 && cat) card.appendChild(h("div", { class: "cat" }, cat));
        card.appendChild(h("div", { class: "cards" }, groups[cat].map(function (item) {
          var pick = person.picks.filter(function (p) { return p.id === item.id; })[0];
          var locked = pick && pick.voucher;
          var sub = item.duration_min + " " + t("min") + (config.showPrices && item.price ? " · " + money(item.price) : "");
          return h("button", {
            type: "button", class: "card" + (pick ? " on" : "") + (locked ? " lock" : ""),
            "aria-pressed": pick ? "true" : "false",
            onclick: function () {
              if (locked) return;
              if (pick) person.picks = person.picks.filter(function (p) { return p !== pick; });
              else person.picks.push({ id: item.id, time: "" });
              state.error = "";
              render();
            },
          }, item.name, h("small", null, locked ? t("fromVoucher") : sub));
        })));
      });
      person.picks.forEach(function (pick) {
        var item = treatment(pick.id);
        var free = slots(pick.id);
        var times = h("div", { class: "times" }, h("div", { class: "tname" }, (item ? item.name : "") + " · " + t("time")));
        if (free.loading) times.appendChild(h("p", { class: "hint" }, t("loading")));
        else if (!free.list.length) times.appendChild(h("p", { class: "hint bad" }, t("noSlots")));
        else times.appendChild(h("div", { class: "chips" }, free.list.map(function (slot) {
          return h("button", {
            type: "button", class: "chip" + (pick.time === slot.time ? " on" : ""),
            "aria-pressed": pick.time === slot.time ? "true" : "false",
            onclick: function () { pick.time = slot.time; state.error = ""; render(); },
          }, slot.time);
        })));
        card.appendChild(times);
      });
      if (wantsPref(person)) card.appendChild(prefChips(person));
      box.appendChild(card);
    });
  }

  // A woman or a man for the massage, person by person: asked only when a
  // massage she chose is done by both (the site says so with gender_choice).
  function wantsPref(person) {
    return person.picks.some(function (pick) {
      var item = treatment(pick.id);
      return item && item.gender_choice;
    });
  }

  function prefChips(person) {
    return h("div", { class: "times pref" },
      h("div", { class: "tname" }, t("pref")),
      h("div", { class: "chips" }, [["", "prefAny"], ["F", "prefF"], ["M", "prefM"]].map(function (choice) {
        var on = (person.pref || "") === choice[0];
        return h("button", {
          type: "button", class: "chip" + (on ? " on" : ""),
          "aria-pressed": on ? "true" : "false",
          onclick: function () { person.pref = choice[0]; render(); },
        }, t(choice[1]));
      })));
  }

  function stepWho(box) {
    box.appendChild(h("h2", null, t("s3")));
    var input = function (key, label, attrs) {
      return h("div", { class: "field" },
        h("p", { class: "lbl" }, label),
        h("input", Object.assign({
          value: state[key], "aria-label": label,
          oninput: function (e) { state[key] = e.target.value; state.error = ""; },
        }, attrs || {})));
    };
    box.appendChild(h("div", { class: "grid" },
      input("first", t("first") + " *", { autocomplete: "given-name", maxlength: "60" }),
      input("last", t("last"), { autocomplete: "family-name", maxlength: "60" })));
    box.appendChild(h("div", { class: "field" },
      h("p", { class: "lbl" }, t("phone") + " *"),
      h("div", { class: "row ph" },
        h("select", {
          "aria-label": "+", autocomplete: "tel-country-code",
          onchange: function (e) { state.cc = e.target.value; },
        }, COUNTRIES.map(function (row) {
          var option = h("option", { value: row[1] }, flag(row[0]) + " +" + row[1]);
          if (row[1] === state.cc) option.selected = true;
          return option;
        })),
        h("input", {
          type: "tel", inputmode: "tel", autocomplete: "tel-national", maxlength: "30", value: state.phone,
          placeholder: "333 1234567", "aria-label": t("phone"),
          oninput: function (e) { state.phone = e.target.value; state.error = ""; },
        })),
      h("p", { class: "hint" }, t("phoneHint"))));
    box.appendChild(input("email", t("email"), { type: "email", autocomplete: "email", maxlength: "120" }));
    box.appendChild(h("div", { class: "field" },
      h("p", { class: "lbl" }, t("notes")),
      h("textarea", {
        rows: "2", maxlength: "1000", placeholder: t("notesPh"), "aria-label": t("notes"),
        oninput: function (e) { state.notes = e.target.value; },
      }, state.notes)));
    box.appendChild(h("div", { class: "honey", "aria-hidden": "true" },
      h("input", { id: "sb-website", tabindex: "-1", autocomplete: "off" })));
  }

  function stepCheck(box) {
    box.appendChild(h("h2", null, t("s4")));
    var rows = [[t("when"), longDate(state.date)]];
    state.persons.forEach(function (person, index) {
      var text = person.picks.map(function (pick) {
        var item = treatment(pick.id);
        return (item ? item.name : "") + " · " + pick.time;
      }).join(", ");
      if (wantsPref(person) && person.pref) text += " · " + t(person.pref === "F" ? "prefF" : "prefM").toLowerCase();
      rows.push([state.people > 1 ? t("person", { n: index + 1 }) : t("treatments"), text]);
    });
    var phone = /^(\+|00)/.test(state.phone.trim()) ? state.phone.trim() : "+" + state.cc + " " + state.phone.trim();
    rows.push([t("contact"), [state.first, state.last].join(" ").trim() + " · " + phone]);
    if (config.showPrices && total() > 0) {
      // The partner's guests see their discount (2.8.6).
      var pct = config.partnerDiscount || 0;
      if (pct > 0) {
        var cut = Math.round(total() * pct) / 100;
        rows.push([t("discount", { p: pctText(pct) }), "−" + money(cut)]);
        rows.push([t("total"), money(total() - cut)]);
      } else rows.push([t("total"), money(total())]);
    }
    box.appendChild(h("div", { class: "sum" }, rows.map(function (row) {
      return h("div", null, h("span", null, row[0]), h("span", null, row[1]));
    })));
    box.appendChild(h("p", { class: "hint" }, t("notYet")));
  }

  function reset() {
    state.step = 1;
    state.date = "";
    state.people = 1;
    state.persons = [{ picks: [] }];
    state.voucher = null;
    state.voucherCode = "";
    state.voucherMsg = "";
    state.notes = "";
    state.code = "";
    state.error = "";
    slotCache = {};
    render();
  }

  // ------------------------------------------------------------------ start

  render();
  // With a partner's link the site says the guest's discount (2.8.6); the
  // partner's code itself is sent with the request, never shown.
  var startPartner = partnerCode();
  api("/treatments" + (startPartner ? "?partner=" + encodeURIComponent(startPartner) : "")).then(function (data) {
    config.treatments = (data && data.treatments) || [];
    var site = (data && data.site) || {};
    config.showPrices = !!site.show_prices;
    config.accent = site.accent || "";
    config.maxDays = site.max_days_ahead || 60;
    config.partnerDiscount = Number(site.partner_discount) || 0;
    render();
  }).catch(function () {
    config.error = t("errLoad");
    render();
  });
})();

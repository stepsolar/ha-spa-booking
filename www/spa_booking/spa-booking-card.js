    (function () {
      "use strict";
      /* ------------------------------- CONFIG ------------------------------- */
      var API_BASE = "https://hailmarchese.it/api/spa_booking/public";
      var TOKEN = "INCOLLA_QUI_IL_TOKEN";
      var MAX_DAYS_AHEAD = 60;
      /* L'ampersand non puo' stare scritto nel codice (vedi regola 2 in
         testa al file): lo costruiamo quando serve per la query string. */
      var AMP = String.fromCharCode(38);
      /* --------------------------------------------------------------------- */
      var root = document.getElementById("sbw-widget");
      if (!root || typeof fetch !== "function") return;
      function node(tag, attrs, children) {
        var el = document.createElement(tag);
        if (attrs) {
          Object.keys(attrs).forEach(function (key) {
            var value = attrs[key];
            if (value === null || value === undefined) return;
            if (key === "class") el.className = value;
            else if (key === "text") el.textContent = value;
            else if (key === "on") Object.keys(value).forEach(function (ev) {
              el.addEventListener(ev, value[ev]);
            });
            else el.setAttribute(key, value);
          });
        }
        (children || []).forEach(function (child) { if (child) el.appendChild(child); });
        return el;
      }
      function $(id) { return root.querySelector("#" + id); }
      var boxTreatment = $("sbw-treatment");
      var voucherInput = $("sbw-voucher");
      var voucherCheck = $("sbw-voucher-check");
      var voucherInfo = $("sbw-voucher-info");
      var voucherDetails = null;
      var inputDate = $("sbw-date");
      var inputPeople = $("sbw-people");
      var slotsBox = $("sbw-slots");
      var windowHint = $("sbw-window");
      var statusBox = $("sbw-status");
      var sendButton = $("sbw-send");
      var honey = $("sbw-website");
      var chosenTime = "";
      var sending = false;
      function say(text, kind) {
        statusBox.textContent = text || "";
        statusBox.className = "sbw-status" + (kind ? " " + kind : "");
      }
      function pad2(value) { return (value < 10 ? "0" : "") + value; }
      function isoDay(day) {
        return day.getFullYear() + "-" + pad2(day.getMonth() + 1) + "-" + pad2(day.getDate());
      }
      /* A gentle sentence for the guest; the server's own message wins when
         it has one (it is written for a person, in Italian). */
      function describe(error) {
        var status = error ? error.status : 0;
        if (status === 404) {
          return "Il servizio di prenotazione online non \u00e8 attivo in questo momento: chiama la reception per prenotare.";
        }
        if (status === 401) {
          return "Il modulo non \u00e8 configurato correttamente. Avvisa la reception.";
        }
        if (status) {
          if (error.message) return error.message;
        }
        return "Non riesco a contattare il servizio di prenotazione: controlla la connessione e riprova, o chiama la reception.";
      }
      function api(path, options) {
        options = options || {};
        var headers = { Authorization: "Bearer " + TOKEN };
        if (options.body) headers["Content-Type"] = "application/json";
        return fetch(API_BASE + path, {
          method: options.method || "GET",
          headers: headers,
          body: options.body ? JSON.stringify(options.body) : undefined,
          mode: "cors",
          cache: "no-store",
        }).then(function (response) {
          return response.text().then(function (raw) {
            var data = null;
            try { data = raw ? JSON.parse(raw) : null; } catch (err) { data = null; }
            if (!response.ok) {
              var failure = new Error((data ? data.message : null) || "HTTP " + response.status);
              failure.status = response.status;
              throw failure;
            }
            return data;
          });
        });
      }
      function safeLabel(row) { return (row || "").replace(/</g, "&lt;"); }
      function loadVoucher() {
        if (!voucherInput) return;
        var code = voucherInput.value.trim().toUpperCase();
        if (!code) { if (voucherInfo) voucherInfo.textContent = ""; voucherDetails = null; return; }
        if (voucherInfo) voucherInfo.textContent = "Verifica in corso&hellip;";
        api("/voucher?code=" + encodeURIComponent(code)).then(function (data) {
          voucherDetails = data;
          var people = (data ? data.people : null) || [];
          if (voucherInfo) voucherInfo.textContent = "Voucher valido: " + code + " (" + people.length + " persona/e)";
          if (data) {
            if (data.recipient_name) {
              var first = $("sbw-first"); var last = $("sbw-last"); var phone = $("sbw-phone");
              if (first) { if (!first.value) first.value = data.recipient_name.split(" ")[0] || ""; }
              if (last) { if (!last.value) last.value = data.recipient_name.split(" ").slice(1).join(" ") || ""; }
              if (phone) { if (!phone.value) { if (data.recipient_phone) phone.value = data.recipient_phone; } }
            }
          }
          if (people.length > 1) {
            if (voucherInfo) {
              voucherInfo.textContent += " - il sistema ha proposto i trattamenti per la prima persona; completare manualmente per le altre.";
            }
          }
          if (people.length === 1) {
            if (people[0].treatments) {
              if (people[0].treatments.length === 1) {
                var t = people[0].treatments[0].treatment_id;
                if (t) { boxTreatment.value = t; }
              }
            }
          }
        }).catch(function (err) {
          voucherDetails = null;
          if (voucherInfo) voucherInfo.textContent = err ? (err.message ? err.message : "Voucher non valido.") : "Voucher non valido.";
        });
      }
      if (voucherCheck) {
        voucherCheck.addEventListener("click", loadVoucher);
      }
      /* ---------------------------- trattamenti ---------------------------- */
      function loadTreatments() {
        return api("/treatments").then(function (data) {
          var list = (data ? data.treatments : null) || [];
          boxTreatment.innerHTML = "";
          if (!list.length) {
            boxTreatment.appendChild(node("option", { value: "", text: "Nessun trattamento disponibile" }));
            say("Nessun trattamento prenotabile online in questo momento.", "err");
            return;
          }
          boxTreatment.appendChild(node("option", { value: "", text: "\u2014 scegli un trattamento \u2014" }));
          var groups = {};
          list.forEach(function (treatment) {
            var key = treatment.category_name || "Altri trattamenti";
            (groups[key] = groups[key] || []).push(treatment);
          });
          Object.keys(groups).forEach(function (category) {
            var group = node("optgroup", { label: category });
            groups[category].forEach(function (treatment) {
              var parts = [treatment.name, treatment.duration_min + " min"];
              group.appendChild(node("option", { value: treatment.id, text: parts.join(" \u00b7 ") }));
            });
            boxTreatment.appendChild(group);
          });
        }).catch(function (error) { say(describe(error), "err"); });
      }
      /* ------------------------------- orari ------------------------------- */
      function clearSlots(hint) {
        chosenTime = "";
        slotsBox.innerHTML = "";
        windowHint.textContent = "";
        if (hint) slotsBox.appendChild(node("span", { class: "sbw-hint", text: hint }));
      }
      function selectTime(time) {
        chosenTime = time;
        var buttons = slotsBox.querySelectorAll(".sbw-slot");
        Array.prototype.forEach.call(buttons, function (button) {
          button.setAttribute("aria-pressed", button.textContent === time ? "true" : "false");
        });
        say("");
      }
      function loadSlots() {
        var treatmentId = boxTreatment.value;
        var day = inputDate.value;
        if (!treatmentId || !day) {
          clearSlots("Scegli prima il trattamento e la data.");
          return Promise.resolve();
        }
        clearSlots("Cerco gli orari liberi\u2026");
        var query = "/availability?date=" + encodeURIComponent(day) +
                    AMP + "treatment_id=" + encodeURIComponent(treatmentId);
        return api(query).then(function (data) {
          var slots = (data ? data.slots : null) || [];
          clearSlots("");
          if (!slots.length) {
            slotsBox.appendChild(node("span", { class: "sbw-hint",
              text: "Nessun orario libero in questa data: prova un altro giorno o chiama la reception." }));
            return;
          }
          var windowText = data.open_time + "\u2013" + data.close_time;
          if (data.break_start) {
            if (data.break_end) {
              windowText = data.open_time + "\u2013" + data.break_start +
                           " e " + data.break_end + "\u2013" + data.close_time;
            } else {
              windowText = data.open_time + "\u2013" + data.break_start;
            }
          } else if (data.break_end) {
            windowText = data.break_end + "\u2013" + data.close_time;
          }
          windowHint.textContent = "Orari proposti: " + windowText +
                                   " \u00b7 durata " + data.duration_min + " min";
          slots.forEach(function (slot) {
            slotsBox.appendChild(node("button", {
              type: "button", class: "sbw-slot", text: slot.time,
              "aria-pressed": "false", "aria-label": "Orario " + slot.time,
              on: { click: function () { selectTime(slot.time); } },
            }));
          });
        }).catch(function (error) {
          clearSlots("");
          slotsBox.appendChild(node("span", { class: "sbw-hint", text: describe(error) }));
        });
      }
      /* ------------------------------ invio ------------------------------- */
      function receipt(data) {
        $("sbw-form").hidden = true;
        var done = $("sbw-done");
        done.innerHTML = "";
        done.hidden = false;
        done.appendChild(node("div", { class: "sbw-receipt" }, [
          node("div", { class: "sbw-ok", text: "\u2713" }),
          node("h3", { class: "sbw-title", text: "Richiesta inviata" }),
          node("p", { text: "Codice della richiesta" }),
          node("div", { class: "sbw-code", text: String((data ? data.code : null) || "\u2014") }),
          node("p", { text: "La reception ti ricontatta al numero indicato per confermare l'appuntamento." }),
          node("button", { type: "button", class: "sbw-btn", text: "Fai un'altra richiesta",
            on: { click: function () { resetForm(); } } }),
        ]));
      }
      function resetForm() {
        ["sbw-first", "sbw-last", "sbw-phone", "sbw-email", "sbw-notes", "sbw-voucher"].forEach(function (id) {
          $(id).value = "";
        });
        $("sbw-done").hidden = true;
        $("sbw-form").hidden = false;
        sendButton.disabled = false;
        spin(false);
        say("");
        clearSlots("Scegli prima il trattamento e la data.");
        loadSlots();
      }
      function spin(on) {
        sending = on;
        sendButton.disabled = on;
        sendButton.setAttribute("aria-busy", on ? "true" : "false");
      }
      function send() {
        if (sending) return;
        if (honey.value) return; /* esca: un robot l'ha compilata, si finge inviato */
        if (!boxTreatment.value) { say("Scegli il trattamento.", "err"); return; }
        if (!inputDate.value) { say("Scegli la data.", "err"); return; }
        if (!chosenTime) { say("Scegli l'orario.", "err"); return; }
        var first = $("sbw-first").value.trim();
        var last = $("sbw-last").value.trim();
        var phone = $("sbw-phone").value.trim();
        var email = $("sbw-email").value.trim();
        var notes = $("sbw-notes").value.trim();
        var voucher = $("sbw-voucher").value.trim().toUpperCase();
        if (!(first || last)) { say("Indica il tuo nome.", "err"); return; }
        if (!phone) { say("Indica un numero di telefono: serve per confermare.", "err"); return; }
        spin(true);
        say("Invio la richiesta\u2026");
        api("/requests", {
          method: "POST",
          body: {
            date: inputDate.value,
            entries: [{ treatment_id: boxTreatment.value, time: chosenTime }],
            first_name: first,
            last_name: last,
            phone: phone,
            email: email,
            notes: notes,
            voucher_code: voucher,
            people: Number(inputPeople.value) || 1,
          },
        }).then(function (data) {
          spin(false);
          receipt(data || {});
        }).catch(function (error) {
          spin(false);
          say(describe(error), "err");
        });
      }
      /* ------------------------------ avvio ------------------------------- */
      if (TOKEN.indexOf("INCOLLA") === 0) {
        say("Modulo non configurato: manca il token. Avvisa la reception.", "err");
      }
      var start = new Date();
      start.setHours(12, 0, 0, 0);
      var end = new Date(start.getTime() + MAX_DAYS_AHEAD * 86400000);
      inputDate.min = isoDay(start);
      inputDate.max = isoDay(end);
      if (boxTreatment) boxTreatment.addEventListener("change", function () { say(""); loadSlots(); });
      if (inputDate) inputDate.addEventListener("change", function () { say(""); loadSlots(); });
      if (sendButton) sendButton.addEventListener("click", send);
      clearSlots("Scegli prima il trattamento e la data.");
      loadTreatments();
      window.__sbwStarted = true;
    })();
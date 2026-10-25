"""Serve the management card with revalidation instead of a long cache.

Home Assistant serves everything under ``/local`` with ``Cache-Control:
public, max-age=2678400`` (31 days). That is why a phone could keep showing an
old version of the card even after the file changed. This view answers the same
file with ``Cache-Control: no-cache`` and an ``ETag``: every load revalidates,
a changed card is picked up immediately, and an unchanged one costs only a
cheap 304.

Also serves a standalone HTML page at ``/spa_booking`` with a loading spinner
while the card loads.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os

from aiohttp import web

from homeassistant.components.http import HomeAssistantView

from .mdi_paths import MDI_PATHS

_LOGGER = logging.getLogger(__name__)

#: Where the card is served from. It is not under /local on purpose: the static
#: /local route is the one with the month-long cache we are avoiding.
CARD_VIEW_URL = "/api/spa_booking/card.js"
#: Standalone HTML page for the SPA booking interface.
SPA_BOOKING_PAGE_URL = "/spa_booking"

#: The standalone page. It is a plain string (not an f-string): the ``.replace``
#: below only substitutes ``CARD_VIEW_URL``, so braces stay as they are and the
#: CSS/JS reach the browser exactly as written.
PAGE_TEMPLATE = """<!DOCTYPE html>
<html lang="it">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Gestione SPA</title>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        /* La pagina standalone non carica il frontend di Home Assistant, quindi
           nessun tema definisce queste variabili: senza di esse il browser
           scarta i bordi (1px solid var(--divider-color)) e gli sfondi dei box.
           I valori sono quelli del tema chiaro della card, così l'aspetto
           "auto" si comporta come "light"; chi forza "dark" nelle impostazioni
           li sovrascrive dall'host della card. */
        :root {
            --primary-color: #009ac7;
            --rgb-primary-color: 0, 154, 199;
            --primary-background-color: #f6f7f9;
            --card-background-color: #ffffff;
            --ha-card-background: #ffffff;
            --secondary-background-color: #f1f3f5;
            --divider-color: #e0e2e5;
            --primary-text-color: #212121;
            --secondary-text-color: #5f656b;
            --disabled-text-color: #9aa0a6;
            --error-color: #e53953;
            --success-color: #4caf50;
            --warning-color: #ff9800;
            --text-primary-color: #ffffff;
            --guest-gold: #b98f2f;
            --pay-amber: #a86a00;
            --pay-violet: #5b3fd1;
            --pay-blue: #1c62c4;
            --input-background-color: #ffffff;
        }
        html, body {
            height: 100%;
        }
        body {
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
            background: #f5f5f5;
            min-height: 100vh;
            display: flex;
            flex-direction: column;
        }
        #loadingOverlay {
            position: fixed;
            inset: 0;
            background: rgba(255, 255, 255, 0.97);
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            z-index: 9999;
            transition: opacity 0.3s ease, visibility 0.3s ease;
        }
        #loadingOverlay.hidden {
            opacity: 0;
            visibility: hidden;
        }
        #loadingSpinner {
            width: 60px;
            height: 60px;
            border: 4px solid #e0e0e0;
            border-top-color: #1976d2;
            border-radius: 50%;
            animation: spin 1s linear infinite;
        }
        #loadingOverlay.error #loadingSpinner {
            display: none;
        }
        @keyframes spin {
            to { transform: rotate(360deg); }
        }
        #loadingText {
            margin-top: 16px;
            font-size: 16px;
            color: #555;
            font-weight: 500;
            text-align: center;
            max-width: 32rem;
            padding: 0 1rem;
            line-height: 1.5;
        }
        #loadingText a {
            color: #1976d2;
            display: inline-block;
            margin-top: 12px;
        }
        .app-container {
            flex: 1;
            display: flex;
            flex-direction: column;
            min-height: 100vh;
        }
        spa-booking-card {
            flex: 1;
            display: block;
        }
    </style>
</head>
<body>
    <div id="loadingOverlay">
        <div id="loadingSpinner"></div>
        <div id="loadingText">Caricamento Gestione SPA...</div>
    </div>

    <div class="app-container">
        <spa-booking-card></spa-booking-card>
    </div>

    <script>
    (function () {
        "use strict";

        var overlay = document.getElementById("loadingOverlay");
        var loadingText = document.getElementById("loadingText");
        var settled = false;

        function showError(message, href, label) {
            overlay.classList.add("error");
            overlay.classList.remove("hidden");
            loadingText.textContent = message;
            if (href) {
                var link = document.createElement("a");
                link.href = href;
                link.textContent = label || "Ricarica";
                loadingText.appendChild(document.createElement("br"));
                loadingText.appendChild(link);
            }
        }

        function hideOverlay() {
            if (settled) return;
            settled = true;
            if (overlay && !overlay.classList.contains("hidden")) {
                overlay.classList.add("hidden");
                setTimeout(function () { overlay.remove(); }, 400);
            }
        }

        // The card fires this once its data is loaded, so the spinner stays up
        // until there is something to show.
        document.addEventListener("spa-booking-ready", hideOverlay);

        // ---------------------------------------------------------------- auth
        // Modern Home Assistant keeps the session in localStorage ("hassTokens"),
        // not in a cookie, so read (and if needed refresh) it from there.
        function storedTokens() {
            try {
                // Try common HA storage keys
                var keys = ["hassTokens", "tokens", "authToken"];
                for (var k = 0; k < keys.length; k++) {
                    var raw = localStorage.getItem(keys[k]);
                    if (raw) {
                        var parsed = JSON.parse(raw);
                        if (parsed && (parsed.access_token || parsed.token)) return parsed;
                    }
                }
                // Search all localStorage keys
                for (var i = 0; i < localStorage.length; i++) {
                    var key = localStorage.key(i);
                    if (!key) continue;
                    if (key.indexOf("token") >= 0 || key.indexOf("auth") >= 0 || key.slice(-10) === "hassTokens") {
                        try {
                            var raw2 = localStorage.getItem(key);
                            if (!raw2) continue;
                            var parsed2 = JSON.parse(raw2);
                            if (parsed2 && (parsed2.access_token || parsed2.refresh_token || parsed2.token)) {
                                // Normalize if it's just {token: ...}
                                if (!parsed2.access_token && parsed2.token) {
                                    parsed2.access_token = parsed2.token;
                                }
                                return parsed2;
                            }
                        } catch (e) {}
                    }
                }
                // Try sessionStorage too
                for (var j = 0; j < sessionStorage.length; j++) {
                    var key2 = sessionStorage.key(j);
                    if (!key2) continue;
                    if (key2.indexOf("token") >= 0 || key2.indexOf("auth") >= 0) {
                        try {
                            var raw3 = sessionStorage.getItem(key2);
                            if (!raw3) continue;
                            var parsed3 = JSON.parse(raw3);
                            if (parsed3 && (parsed3.access_token || parsed3.token)) {
                                if (!parsed3.access_token && parsed3.token) parsed3.access_token = parsed3.token;
                                return parsed3;
                            }
                        } catch (e) {}
                    }
                }
            } catch (error) {
                console.warn("Token non leggibile:", error);
            }
            return null;
        }

        function saveTokens(tokens) {
            try {
                localStorage.setItem("hassTokens", JSON.stringify(tokens));
            } catch (error) {
                console.warn("Token non salvabile:", error);
            }
        }

        function getAccessToken() {
            var tokens = storedTokens();
            if (!tokens) return Promise.resolve(null);
            var usable = tokens.access_token &&
                (!tokens.expires || tokens.expires - 60000 > Date.now());
            if (usable) return Promise.resolve(tokens.access_token);
            if (!tokens.refresh_token) return Promise.resolve(tokens.access_token || null);

            var body = new URLSearchParams();
            body.set("grant_type", "refresh_token");
            body.set("refresh_token", tokens.refresh_token);
            body.set("client_id", tokens.clientId ||
                (window.location.protocol + "//" + window.location.host + "/"));
            return fetch("/auth/token", { method: "POST", body: body })
                .then(function (response) {
                    if (!response.ok) return null;
                    return response.json().then(function (fresh) {
                        var merged = Object.assign({}, tokens, fresh, {
                            expires: Date.now() + (fresh.expires_in || 1800) * 1000
                        });
                        saveTokens(merged);
                        return fresh.access_token;
                    });
                })
                .catch(function () { return tokens.access_token || null; });
        }

        // --------------------------------------------------------------- socket
        var socket = null;
        var nextId = 1;
        var pending = new Map();
        var stateSubscribers = new Map();
        var states = {};
        var accessToken = null;

        function send(message) {
            return new Promise(function (resolve, reject) {
                if (!socket || socket.readyState !== WebSocket.OPEN) {
                    reject(new Error("Connessione a Home Assistant non disponibile"));
                    return;
                }
                var id = nextId++;
                pending.set(id, { resolve: resolve, reject: reject });
                socket.send(JSON.stringify(Object.assign({}, message, { id: id })));
            });
        }

        function connect() {
            return new Promise(function (resolve, reject) {
                var url = new URL("/api/websocket", window.location.href);
                url.protocol = url.protocol.replace("http", "ws");
                socket = new WebSocket(url.href);
                var authenticated = false;

                socket.onopen = function () {
                    socket.send(JSON.stringify({ type: "auth", access_token: accessToken }));
                };

                socket.onmessage = function (event) {
                    var message;
                    try { message = JSON.parse(event.data); } catch (error) { return; }

                    if (message.type === "auth_ok") {
                        authenticated = true;
                        resolve();
                        return;
                    }
                    // "auth_required" is the normal first message of the
                    // protocol: only a rejected token is a failure.
                    if (message.type === "auth_invalid") {
                        reject(new Error("Token non valido"));
                        return;
                    }
                    if (message.type === "result") {
                        var call = pending.get(message.id);
                        if (!call) return;
                        pending.delete(message.id);
                        if (message.success) call.resolve(message.result);
                        else call.reject(new Error((message.error && message.error.message) || "Errore"));
                        return;
                    }
                    if (message.type === "event" && message.event &&
                        message.event.event_type === "state_changed") {
                        var data = message.event.data || {};
                        var entityId = data.entity_id;
                        if (!entityId) return;
                        if (data.new_state) states[entityId] = data.new_state;
                        else delete states[entityId];
                        var subscribers = stateSubscribers.get(entityId);
                        if (subscribers) {
                            subscribers.forEach(function (callback) {
                                callback(data.new_state, data.old_state);
                            });
                        }
                    }
                };

                socket.onerror = function () {
                    if (!authenticated) reject(new Error("Connessione non riuscita"));
                };

                socket.onclose = function () {
                    if (!authenticated) {
                        reject(new Error("Connessione chiusa"));
                        return;
                    }
                    // Teardown happened after a working session: reconnect.
                    setTimeout(start, 5000);
                };
            });
        }

        // ------------------------------------------------------------- hass shim
        var hass = {
            states: states,
            config: {},
            user: null,
            callWS: send,
            callService: function (domain, service, data) {
                return send({
                    type: "call_service",
                    domain: domain,
                    service: service,
                    service_data: data || {}
                });
            },
            subscribeEntities: function (entityIds, callback) {
                (entityIds || []).forEach(function (entityId) {
                    if (!stateSubscribers.has(entityId)) stateSubscribers.set(entityId, new Set());
                    stateSubscribers.get(entityId).add(callback);
                    if (states[entityId]) callback(states[entityId], null);
                });
            },
            unsubscribeEntities: function (entityIds, callback) {
                (entityIds || []).forEach(function (entityId) {
                    if (!stateSubscribers.has(entityId)) return;
                    stateSubscribers.get(entityId).delete(callback);
                });
            }
        };

        function apiGet(path) {
            return fetch(path, { headers: { Authorization: "Bearer " + accessToken } })
                .then(function (response) {
                    if (!response.ok) throw new Error(path + ": HTTP " + response.status);
                    return response.json();
                });
        }

        function start() {
            overlay.classList.remove("error");
            loadingText.textContent = "Caricamento Gestione SPA...";

            // Safety net: never leave the spinner forever if the card module
            // fails to load or renders nothing.
            setTimeout(function () {
                if (!settled) {
                    showError("La card non si è caricata. Verifica la connessione e ricarica la pagina.", "/spa_booking", "Ricarica");
                }
            }, 20000);

            getAccessToken().then(function (token) {
                if (!token) throw new Error("no-token");
                accessToken = token;
                return connect();
            }).then(function () {
                return Promise.all([
                    send({ type: "auth/current_user" }),
                    apiGet("/api/config"),
                    apiGet("/api/states")
                ]);
            }).then(function (result) {
                var user = result[0];
                var config = result[1];
                var allStates = result[2];

                Object.keys(states).forEach(function (entityId) { delete states[entityId]; });
                (allStates || []).forEach(function (state) { states[state.entity_id] = state; });

                hass.user = user || null;
                hass.config = config || {};
                window.hassStates = states;
                window.hass = hass;

                return send({ type: "subscribe_events", event_type: "state_changed" });
            }).then(function () {
                return customElements.whenDefined("spa-booking-card");
            }).then(function () {
                var card = document.querySelector("spa-booking-card");
                if (!card) throw new Error("card-missing");
                card.hass = hass;
            }).catch(function (error) {
                console.error("Gestione SPA:", error);
                if (error && error.message === "no-token") {
                    showError("Sessione Home Assistant non trovata. Accedi a Home Assistant, poi ricarica questa pagina.", "/", "Vai al login");
                } else if (!settled) {
                    showError("Impossibile caricare la Gestione SPA: " + (error && error.message ? error.message : "errore sconosciuto"), "/spa_booking", "Riprova");
                }
            });
        }

        start();
    })();
    </script>

    <!-- Icone MDI come SVG inline.
    In questa pagina standalone il frontend di Home Assistant non viene
    caricato, quindi ``ha-icon`` non viene mai definito e il font delle icone
    non viene applicato: gli elementi restano vuoti. Qui disegniamo i percorsi
    MDI dentro lo stesso elemento ``ha-icon``, così i CSS della card (colore,
    --mdc-icon-size, display) continuano a valere. -->
    <script>
    (function () {
        "use strict";

        var PATHS = /*MDI_PATHS*/;
        var NS = "http://www.w3.org/2000/svg";

        function iconSize(el) {
            var cs = window.getComputedStyle(el);
            var size = (cs.getPropertyValue("--mdc-icon-size") || "").trim();
            if (!size) {
                var w = (cs.width || "").trim();
                size = w && w !== "auto" && w.indexOf("px") > 0 ? w : "24px";
            }
            var n = parseFloat(size);
            return isFinite(n) && n > 0 ? n + "px" : "24px";
        }

        function paint(icon) {
            // Dentro Home Assistant l'elemento è definito e il font funziona:
            // lì non serve (e non si vedrebbe) nulla di tutto questo.
            if (icon.shadowRoot) return;
            var name = icon.getAttribute("icon") || "";
            if (name.indexOf("mdi:") !== 0) return;
            var paths = PATHS[name.slice(4)];
            if (!paths) return;
            if (icon.__spaIcon === name) return;
            icon.__spaIcon = name;

            var size = iconSize(icon);
            var svg = document.createElementNS(NS, "svg");
            svg.setAttribute("viewBox", "0 0 24 24");
            svg.setAttribute("width", size);
            svg.setAttribute("height", size);
            svg.setAttribute("fill", "currentColor");
            svg.setAttribute("aria-hidden", "true");
            svg.style.verticalAlign = "middle";
            svg.style.display = "inline-block";
            for (var i = 0; i < paths.length; i++) {
                var path = document.createElementNS(NS, "path");
                path.setAttribute("d", paths[i]);
                svg.appendChild(path);
            }
            icon.textContent = "";
            icon.appendChild(svg);
        }

        function paintAll(root) {
            if (!root) return;
            var icons = root.querySelectorAll ? root.querySelectorAll("ha-icon") : [];
            for (var i = 0; i < icons.length; i++) paint(icons[i]);
        }

        function watch(card) {
            paintAll(card.shadowRoot);
            if (card.__spaObserver || !card.shadowRoot) return;
            var observer = new MutationObserver(function () {
                paintAll(card.shadowRoot);
            });
            observer.observe(card.shadowRoot, {
                childList: true,
                subtree: true,
                attributes: true,
                attributeFilter: ["icon"],
            });
            card.__spaObserver = observer;
        }

        function start() {
            var card = document.querySelector("spa-booking-card");
            if (!card || !card.shadowRoot) {
                window.setTimeout(start, 150);
                return;
            }
            watch(card);
        }

        document.addEventListener("spa-booking-ready", function () {
            start();
        });
        start();
    })();
    </script>

    <script type="module" src="CARD_VIEW_URL"></script>
</body>
</html>
"""


class SpaBookingCardView(HomeAssistantView):
    """Serve the card JavaScript file without a long cache."""

    url = CARD_VIEW_URL
    name = "api:spa_booking:card"
    #: Loaded as a plain module by the frontend, which cannot send the auth
    #: header; the file is not secret (it was public under /local too).
    requires_auth = False

    def __init__(self, path: str) -> None:
        """Store the file path to serve."""
        self._path = path

    async def get(self, request: web.Request) -> web.Response:
        """Return the card file, or 304 when the client already has it."""
        try:
            with open(self._path, "rb") as handle:
                content = handle.read()
        except OSError:
            return web.Response(status=404, text="Card not found")

        etag = '"' + hashlib.sha256(content).hexdigest()[:32] + '"'
        if request.headers.get("If-None-Match") == etag:
            return web.Response(status=304, headers={"ETag": etag})

        return web.Response(
            body=content,
            content_type="text/javascript",
            headers={"Cache-Control": "no-cache", "ETag": etag},
        )


class SpaBookingPageView(HomeAssistantView):
    """Serve the standalone HTML page for the SPA Booking interface."""

    url = SPA_BOOKING_PAGE_URL
    name = "api:spa_booking:page"
    requires_auth = False  # Same as the card JS: the page itself holds no secret

    def __init__(self, path: str) -> None:
        """Store the card path so the page can load the same script."""
        self._js_path = path
        self._html = PAGE_TEMPLATE.replace("CARD_VIEW_URL", CARD_VIEW_URL).replace(
            "/*MDI_PATHS*/", json.dumps(MDI_PATHS, separators=(",", ":"))
        )

    async def get(self, request: web.Request) -> web.Response:
        """Return the HTML page."""
        return web.Response(
            text=self._html,
            content_type="text/html",
            headers={"Cache-Control": "no-cache, no-store, must-revalidate"},
        )

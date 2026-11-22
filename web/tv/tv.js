(function () {
  "use strict";

  var esc = Core.esc;
  var stage = document.getElementById("stage");
  var unlockButton = document.getElementById("unlock");
  var offline = document.getElementById("offline");
  var state = null;
  var lastFx = null;
  var lastTick = null;
  var net;
  var ROOM_KEY = "teleturniej.tv";

  /* Pokój i jego klucz zostają w telewizorze, żeby po odświeżeniu lub wyłączeniu ekranu
     wrócić do tej samej gry, zamiast zakładać nową. */
  function loadRoom() {
    try {
      var saved = JSON.parse(localStorage.getItem(ROOM_KEY) || "null");
      return saved && saved.code ? saved : {};
    } catch (e) {
      return {};
    }
  }

  function saveRoom(code, key) {
    try { localStorage.setItem(ROOM_KEY, JSON.stringify({ code: code, key: key })); } catch (e) { /* bez pamięci */ }
  }

  var room = loadRoom();

  /* Wszystkie wymiary są w rem, a 1 rem to 1/96 szerokości ekranu 16:9. Dzięki temu układ
     wygląda tak samo przy każdej rozdzielczości, którą zgłasza przeglądarka telewizora. */
  function fit() {
    var size = Math.min(window.innerWidth / 96, window.innerHeight / 54);
    document.documentElement.style.fontSize = size + "px";
  }
  window.addEventListener("resize", fit);
  fit();

  function gameCard(g, selected) {
    return '<div class="game-tile tile-' + esc(g.id) + (selected ? " on" : "") + '" data-key="g' + esc(g.id) + '"><strong>' + esc(g.title) +
      "</strong><small>" + esc(g.tagline) + "</small></div>";
  }

  function renderPlayers() {
    if (!state.players.length) {
      return '<div class="no-players">Pierwsza osoba, która dołączy, zostanie gospodarzem i wybierze grę.</div>';
    }
    var html = '<div class="lobby-players' + (state.players.length > 8 ? " many" : "") + '">';
    state.players.forEach(function (p) {
      html += '<div class="lobby-player' + (p.connected ? "" : " away") + '" data-key="p' + esc(p.id) + '">' + TV.avatar(p) +
        '<div class="lobby-player-text"><span class="chip-name">' + esc(p.name) + "</span>" +
        (p.id === state.hostId ? '<small>gospodarz</small>' : "") + "</div></div>";
    });
    return html + "</div>";
  }

  function renderLobby() {
    var selected = null;
    state.catalog.forEach(function (g) { if (g.id === state.selected) selected = g; });
    var right = "";
    if (selected) {
      right += '<div class="selected-game tile-' + esc(selected.id) + '"><div class="selected-title">' + esc(selected.title) + "</div>" +
        '<ul class="selected-rules">';
      selected.rules.forEach(function (r) { right += "<li>" + esc(r) + "</li>"; });
      right += "</ul></div>";
    } else {
      right += '<div class="game-tiles">';
      state.catalog.forEach(function (g) { right += gameCard(g, false); });
      right += "</div>";
    }
    var host = state.joinUrl.replace(/^https?:\/\//, "").split("/")[0];
    // Adres w sieci domowej działa tylko w tym samym Wi-Fi, a adres w internecie wszędzie.
    var local = /^(10\.|192\.168\.|172\.(1[6-9]|2\d|3[01])\.|localhost|127\.)/.test(host);
    return '<div class="lobby">' +
      '<div class="lobby-left">' +
      '<div class="brand">Sutoliada</div>' +
      '<div class="qr-card"><img class="qr" src="/qr.svg?r=' + encodeURIComponent(state.room) + '" alt="Kod QR"></div>' +
      '<div class="join-title">Zeskanuj telefonem</div>' +
      '<div class="join-url">albo wejdź na <b>' + esc(host) + "</b> i wpisz kod</div>" +
      '<div class="room-code">' + esc(state.room) + "</div>" +
      (local ? '<div class="join-note">Telefon musi być w tej samej sieci Wi-Fi</div>' : "") +
      "</div>" +
      '<div class="lobby-right' + (state.players.length > 8 ? " crowded" : "") + '">' + right +
      '<div class="section-title">W grze: ' + state.players.length + "</div>" + renderPlayers() +
      (state.notice ? '<div class="notice">' + esc(state.notice) + "</div>" : "") +
      "</div></div>";
  }

  function render() {
    if (!state) return;
    var game = state.game;
    document.body.className = game ? "theme-" + game.id : "theme-lobby";
    var html;
    if (!game) html = renderLobby();
    else if (game.screen === "results") html = TV.results(game);
    else html = TV.games[game.id](game, state);
    if (game && game.tournament) {
      html = '<div class="tour-badge">Turniej · gra ' + game.tournament.number + " z " + game.tournament.total + "</div>" + html;
    }
    // Zmiana gry wymienia całą scenę, żeby nie animować elementów poprzedniej.
    var scene = game ? game.id : "lobby";
    if (stage.getAttribute("data-scene") !== scene) {
      stage.setAttribute("data-scene", scene);
      stage.innerHTML = "";
    }
    Core.patch(stage, html);
    Sound.apply(game && game.audio ? game.audio : null);
    // W trakcie gry bez muzyki przypomnienie nie może zasłaniać pytań.
    unlockButton.className = game && game.id !== "melody" ? "unlock compact" : "unlock";
  }

  function playEffects() {
    var effects = state.fx || [];
    if (lastFx === null) {
      lastFx = effects.length ? effects[effects.length - 1].id : 0;
      return;
    }
    effects.forEach(function (e) {
      if (e.id > lastFx) {
        Sound.effect(e.name);
        lastFx = e.id;
      }
    });
  }

  Core.onSecond = function (seconds) {
    if (seconds !== lastTick) {
      lastTick = seconds;
      if (seconds > 0 && seconds <= 5) Sound.effect("tick");
    }
  };

  /* --- Odblokowanie dźwięku i pełny ekran --- */

  function unlock() {
    Sound.unlock();
    unlockButton.hidden = true;
    document.documentElement.className = "unlocked";
    var el = document.documentElement;
    var request = el.requestFullscreen || el.webkitRequestFullscreen;
    if (request && !document.fullscreenElement) {
      try {
        var promise = request.call(el);
        if (promise && promise.catch) promise.catch(function () { /* pełny ekran jest opcjonalny */ });
      } catch (e) { /* j.w. */ }
    }
  }

  document.addEventListener("keydown", unlock);
  document.addEventListener("click", unlock);

  Sound.configure(function (event, token) {
    net.send({ t: "tv", e: event, token: token });
  }, function () {
    unlockButton.hidden = false;
    unlockButton.focus();
  });

  unlockButton.focus();

  net = Core.connect({
    onOpen: function () {
      offline.hidden = true;
      net.send({ t: "hello", role: "tv", room: room.code || null, key: room.key || null });
    },
    onClose: function () {
      offline.hidden = false;
    },
    onMessage: function (msg) {
      if (msg.t === "room") {
        room = { code: msg.code, key: msg.key };
        saveRoom(msg.code, msg.key);
      } else if (msg.t === "busy") {
        net.stop();
        stage.innerHTML = TV.splash("Sutoliada", "Serwer jest teraz zajęty", "Spróbuję ponownie za minutę");
        setTimeout(function () { location.reload(); }, 60000);
      } else if (msg.t === "state") {
        state = msg.state;
        render();
        playEffects();
      }
    }
  });
})();

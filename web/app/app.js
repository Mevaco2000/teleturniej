/* Pilot na telefonie. Ekrany gier opisuje serwer listą bloków, więc nowa gra nie wymaga
   zmian w tym pliku. */
(function () {
  "use strict";

  var esc = Core.esc;
  var TOKEN_KEY = "teleturniej.token";
  var ROOM_KEY = "teleturniej.room";
  var NAME_KEY = "teleturniej.name";
  var HINT_KEY = "teleturniej.hint";
  var root = document.getElementById("root");
  var joinForm = document.getElementById("join");
  var roomInput = document.getElementById("room");
  var nameInput = document.getElementById("name");
  var joinError = document.getElementById("join-error");
  var offline = document.getElementById("offline");

  var state = null;
  var joined = false;
  var deferredInstall = null;
  var hintDismissed = load(HINT_KEY) === "1";
  var lastUrgent = false;
  var pendingName = null;
  var lastView = null;
  var net;

  function load(key) {
    try { return localStorage.getItem(key); } catch (e) { return null; }
  }

  function save(key, value) {
    try {
      if (value === null) localStorage.removeItem(key);
      else localStorage.setItem(key, value);
    } catch (e) { /* tryb prywatny: po odświeżeniu trzeba dołączyć ponownie */ }
  }

  function cleanCode(raw) {
    return String(raw || "").toUpperCase().replace(/[^A-Z]/g, "").slice(0, 4);
  }

  /* Kod gry przychodzi z kodu QR (?r=ABCD) albo z poprzedniej wizyty. Żeton gracza pasuje
     tylko do pokoju, w którym go wydano. */
  var fromUrl = /[?&]r=([A-Za-z]{4})(&|$)/.exec(location.search);
  var room = fromUrl ? cleanCode(fromUrl[1]) : cleanCode(load(ROOM_KEY));
  var token = room && room === load(ROOM_KEY) ? load(TOKEN_KEY) : null;
  if (fromUrl && window.history && history.replaceState) {
    // Czysty adres, żeby „Dodaj do ekranu głównego” nie zapamiętało jednej konkretnej gry.
    history.replaceState(null, "", location.pathname);
  }

  function vibrate(pattern) {
    if (navigator.vibrate) {
      try { navigator.vibrate(pattern); } catch (e) { /* bez wibracji */ }
    }
  }

  function action(name, value, extra) {
    var msg = { t: "action", a: name, v: value === undefined ? null : value };
    if (extra) Object.keys(extra).forEach(function (k) { msg[k] = extra[k]; });
    net.send(msg);
  }

  /* --- Bloki opisane przez serwer --- */

  function dataAttrs(act, value) {
    return ' data-action="' + esc(act) + '" data-value="' + esc(JSON.stringify(value === undefined ? null : value)) + '"';
  }

  function blockMsg(b) {
    return '<div class="msg ' + esc(b.tone) + (b.big ? " big" : "") + '">' + esc(b.text) + "</div>";
  }

  function blockOptions(b) {
    var html = '<div class="options cols-' + b.columns + '">';
    b.items.forEach(function (item) {
      if (item.state === "gone") {
        html += '<div class="option gone" data-key="o' + item.v + '"></div>';
        return;
      }
      var off = item.state === "disabled";
      html += '<button class="option ' + esc(item.state) + '" data-key="o' + item.v + '"' + (off ? " disabled" : "") +
        dataAttrs(b.action, item.v) + ">" +
        (item.key ? '<b class="letter">' + esc(item.key) + "</b>" : "") +
        "<span>" + esc(item.label) + "</span></button>";
    });
    return html + "</div>";
  }

  function blockBuzz(b) {
    return '<button class="buzz"' + dataAttrs(b.action, null) + ' data-instant="1"><span>' + esc(b.label) + "</span></button>";
  }

  function blockButtons(b) {
    var cls = b.items.length && b.items[0].style === "tile" ? "tiles" :
      b.items.length && b.items[0].style === "small" ? "row" : "stack";
    var html = '<div class="buttons ' + cls + '">';
    b.items.forEach(function (item) {
      html += '<button class="btn ' + esc(item.style) + '"' + (item.disabled ? " disabled" : "") +
        dataAttrs(item.action, item.v) + ">" +
        (item.color ? '<i class="dot" style="background:' + esc(item.color) + '"></i>' : "") +
        '<span class="btn-label">' + esc(item.label) + "</span>" +
        (item.hint ? '<small>' + esc(item.hint) + "</small>" : "") + "</button>";
    });
    return html + "</div>";
  }

  function blockRanking(b) {
    var html = '<ol class="ranking">';
    b.items.forEach(function (r) {
      html += '<li class="' + (r.me ? "me" : "") + '"><b>' + r.place + '.</b><i class="dot" style="background:' + esc(r.color) + '"></i>' +
        '<span class="rank-name">' + esc(r.name) + "</span><em>" + esc(r.label) + "</em></li>";
    });
    return html + "</ol>";
  }

  /* --- Odpowiedź z głowy: rozpoznawanie mowy wbudowane w przeglądarkę telefonu ---
     Chrome na Androidzie i Safari na iPhonie zamieniają mowę na tekst (wymaga HTTPS i internetu).
     Tekst z kilkoma wariantami rozpoznania idzie do serwera, który ocenia odpowiedź. Gdy mowy
     nie ma, zostaje pole tekstowe, a w nim dyktowanie z klawiatury telefonu. */

  var MIC_ICON = '<svg viewBox="0 0 24 24" aria-hidden="true"><path fill="currentColor" d="M12 14.5a3.5 3.5 0 0 0 3.5-3.5V5.5a3.5 3.5 0 0 0-7 0V11a3.5 3.5 0 0 0 3.5 3.5zm6-3.5a6 6 0 0 1-12 0H4.2a7.8 7.8 0 0 0 6.9 7.7V21h1.8v-2.3a7.8 7.8 0 0 0 6.9-7.7z"/></svg>';

  var Voice = (function () {
    var SR = window.SpeechRecognition || window.webkitSpeechRecognition;
    var api = { supported: !!SR && !!window.isSecureContext };
    var rec = null;
    var form = null;
    var sticky = false;
    var auto = false;
    var restartTimer = null;

    function alive(f) {
      return !!f && document.body.contains(f);
    }

    function status(f, text, cls) {
      var el = f && f.querySelector(".heard");
      if (!el) return;
      el.textContent = text || "";
      el.className = "heard" + (cls ? " " + cls : "");
    }

    function listening(f, on) {
      if (!f) return;
      if (on) f.classList.add("listening"); else f.classList.remove("listening");
      var label = f.querySelector(".mic-label");
      if (label) label.textContent = on ? "Słucham… mów teraz" : "Stuknij i powiedz";
    }

    function deliver(f, texts) {
      if (!alive(f) || !texts.length) return;
      if (f.getAttribute("data-auto")) {
        api.send(f, texts[0], texts.slice(1));
      } else {
        f.elements.say.value = texts[0];
        f.recognized = texts[0];
        f.alts = texts.slice(1);
        status(f, "", "");
      }
    }

    function halt() {
      if (restartTimer) {
        clearTimeout(restartTimer);
        restartTimer = null;
      }
      if (rec) {
        var r = rec;
        rec = null;
        try { r.abort(); } catch (e) { /* już zatrzymane */ }
      }
      listening(form, false);
    }

    function start(f, automatic) {
      if (!api.supported || !alive(f)) return;
      halt();
      form = f;
      auto = !!automatic;
      sticky = !!f.getAttribute("data-sticky");
      var r = new SR();
      r.lang = "pl-PL";
      r.interimResults = true;
      r.maxAlternatives = 5;
      // The Floor: mikrofon słucha przez cały czas gracza, a każda wypowiedź to osobna odpowiedź.
      r.continuous = sticky;
      r.onresult = function (e) {
        if (rec !== r) return;
        for (var i = e.resultIndex; i < e.results.length; i++) {
          var result = e.results[i];
          if (!result.isFinal) {
            status(form, result[0].transcript, "interim");
            continue;
          }
          var texts = [];
          for (var j = 0; j < result.length; j++) {
            var t = String(result[j].transcript || "").trim();
            if (t && texts.indexOf(t) < 0) texts.push(t);
          }
          deliver(form, texts);
        }
      };
      r.onerror = function (e) {
        if (rec !== r) return;
        var why = e.error;
        if (why === "not-allowed" || why === "service-not-allowed") {
          sticky = false;
          status(form, auto ? "Stuknij mikrofon, żeby mówić." :
            "Brak zgody na mikrofon. Zezwól na niego w ustawieniach przeglądarki albo wpisz odpowiedź.", "bad");
        } else if (why === "audio-capture") {
          sticky = false;
          status(form, "Nie znaleziono mikrofonu. Wpisz odpowiedź.", "bad");
        } else if (why === "network") {
          sticky = false;
          status(form, "Rozpoznawanie mowy potrzebuje internetu. Wpisz odpowiedź.", "bad");
        } else if (why === "no-speech" && !sticky) {
          status(form, "Nic nie usłyszałem. Stuknij i spróbuj jeszcze raz.", "bad");
        }
      };
      r.onend = function () {
        if (rec !== r) return;
        rec = null;
        listening(form, false);
        // Przeglądarka sama kończy nasłuch po chwili ciszy; w The Floor wznawiamy go od razu.
        if (sticky && alive(form)) {
          restartTimer = setTimeout(function () {
            restartTimer = null;
            if (sticky && !rec && alive(form)) start(form, true);
          }, 200);
        }
      };
      rec = r;
      try {
        r.start();
        listening(f, true);
        if (!automatic) status(f, "", "");
      } catch (err) {
        rec = null;
        sticky = false;
        status(f, "Nie udało się włączyć mikrofonu. Wpisz odpowiedź.", "bad");
      }
    }

    api.send = function (f, text, alts) {
      action(f.getAttribute("data-answer"), text, { alts: alts || [] });
      vibrate(15);
      status(f, "Wysłano: „" + text + "”", "sent");
      f.elements.say.value = "";
      f.recognized = null;
    };

    api.toggle = function (f) {
      if (rec && form === f) {
        sticky = false;
        halt();
      } else {
        start(f, false);
      }
    };

    /* Po każdym odświeżeniu ekranu: wyniki trafiają do aktualnego pola, a bez pola mikrofon milknie.
       W The Floor mikrofon wraca sam przy kolejnym haśle i po turze rywala. */
    api.sync = function (typing) {
      var f = document.querySelector("form.answer-box");
      if (f === form) return;
      var keep = sticky;
      if (!f) {
        halt();
        sticky = keep;
        form = null;
        return;
      }
      var stickyNext = keep && !!f.getAttribute("data-sticky");
      if (rec && stickyNext) {
        form = f;
        listening(f, true);
      } else {
        halt();
        form = f;
        sticky = stickyNext;
        if (stickyNext) start(f, true);
      }
      if (typing && f.getAttribute("data-sticky")) f.elements.say.focus();
    };

    api.reset = function () {
      sticky = false;
      halt();
      form = null;
    };

    return api;
  })();

  function blockAnswer(b) {
    var voice = Voice.supported;
    return '<form class="answer-box" data-key="ans-' + esc(b.key) + '" data-keep="1" data-answer="' + esc(b.action) + '"' +
      (b.auto ? ' data-auto="1"' : "") + (b.sticky ? ' data-sticky="1"' : "") + ' autocomplete="off">' +
      (voice ? '<button type="button" class="mic" data-mic="1">' + MIC_ICON + '<span class="mic-label">Stuknij i powiedz</span></button>' : "") +
      '<div class="heard" aria-live="polite"></div>' +
      '<div class="type-row"><input name="say" type="text" maxlength="160" autocomplete="off" autocorrect="off" ' +
      'autocapitalize="sentences" spellcheck="false" enterkeyhint="send" aria-label="Odpowiedź" placeholder="' +
      (voice ? "…albo wpisz" : "Wpisz odpowiedź") + '"><button type="submit" class="btn primary send">Wyślij</button></div>' +
      (voice ? "" : '<small class="voice-hint">Możesz też dyktować: stuknij pole, a potem mikrofon na klawiaturze.</small>') +
      "</form>";
  }

  var BLOCKS = { msg: blockMsg, options: blockOptions, buzz: blockBuzz, buttons: blockButtons, ranking: blockRanking,
    answer: blockAnswer };

  function renderGame(view) {
    var hasClock = view.clock || view.timer;
    var head = '<header class="bar"><div><strong>' + esc(view.title) + "</strong>" +
      (view.sub ? "<small>" + esc(view.sub) + "</small>" : "") + "</div>" +
      (hasClock ? '<div class="bar-clock">' + Core.clock(view.clock || view.timer, view.clock ? "tenths" : "seconds") + "</div>" : "") +
      (state.isHost ? '<button class="quit" data-confirm="Zakończyć grę dla wszystkich?"' + dataAttrs("end_game", null) + ' aria-label="Zakończ grę">✕</button>' : "") +
      "</header>";
    var body = "";
    if (view.timer) body += Core.timerBar(view.timer);
    if (view.flag) body += '<div class="flag-box">' + Core.flag(view.flag) + "</div>";
    if (view.prompt) body += '<div class="prompt">' + esc(view.prompt) + "</div>";
    view.blocks.forEach(function (b) { body += BLOCKS[b.type](b); });
    return '<div class="screen theme-' + esc(view.theme) + '"' +
      (view.accent ? ' style="--accent:' + esc(view.accent) + '"' : "") + ">" + head + '<main class="content">' + body + "</main></div>";
  }

  /* --- Poczekalnia --- */

  function selectedGame() {
    for (var i = 0; i < state.catalog.length; i++) {
      if (state.catalog[i].id === state.selected) return state.catalog[i];
    }
    return null;
  }

  function isIos() {
    return /iPhone|iPad|iPod/.test(navigator.userAgent) ||
      (navigator.platform === "MacIntel" && navigator.maxTouchPoints > 1);
  }

  function installHint() {
    if (hintDismissed || window.matchMedia("(display-mode: standalone)").matches || window.navigator.standalone) return "";
    var close = '<button class="hint-close" data-dismiss="1" aria-label="Zamknij">✕</button>';
    if (deferredInstall) {
      return '<div class="hint"><button class="btn small primary" data-install="1">Zainstaluj aplikację</button>' + close + "</div>";
    }
    var how = isIos()
      ? "Stuknij „Udostępnij”, a potem „Do ekranu początkowego”."
      : "W menu przeglądarki (⋮) wybierz „Zainstaluj aplikację” lub „Dodaj do ekranu głównego”.";
    return '<div class="hint"><span>Chcesz mieć grę jako aplikację? ' + how + "</span>" + close + "</div>";
  }

  function renderPlayers() {
    var html = '<ul class="players">';
    state.players.forEach(function (p) {
      var isMe = p.id === state.me;
      html += '<li class="' + (p.connected ? "" : "away") + '" data-key="p' + esc(p.id) + '">' +
        '<i class="dot" style="background:' + esc(p.color) + '"></i><span class="pl-name">' + esc(p.name) +
        (isMe ? " (Ty)" : "") + (p.id === state.hostId ? ' <small>gospodarz</small>' : "") + "</span>" +
        (state.isHost && !isMe ? '<button class="kick" data-confirm="Usunąć tę osobę z gry?"' + dataAttrs("kick", p.id) + ' aria-label="Usuń">✕</button>' : "") +
        "</li>";
    });
    return html + "</ul>";
  }

  function renderLobbyHost() {
    var game = selectedGame();
    if (!game) {
      var list = '<div class="game-list">';
      state.catalog.forEach(function (g) {
        list += '<button class="game-card card-' + esc(g.id) + '"' + dataAttrs("select_game", g.id) + "><strong>" + esc(g.title) + "</strong><small>" + esc(g.tagline) + "</small></button>";
      });
      return '<h2>Wybierz grę</h2>' + list + "</div>";
    }
    var html = '<button class="back"' + dataAttrs("select_game", null) + '>‹ Inna gra</button>' +
      '<h2>' + esc(game.title) + "</h2>";
    var values = state.options[game.id];
    game.options.forEach(function (def) {
      html += '<div class="option-group"><label>' + esc(def.label) + '</label><div class="chips">';
      def.choices.forEach(function (c) {
        html += '<button class="chip ' + (values[def.key] === c.v ? "on" : "") + '" data-option="' + esc(def.key) +
          '" data-value="' + esc(JSON.stringify(c.v)) + '">' + esc(c.l) + "</button>";
      });
      html += "</div></div>";
    });
    html += '<ul class="rules">';
    game.rules.forEach(function (r) { html += "<li>" + esc(r) + "</li>"; });
    html += '</ul><button class="btn primary big-start"' + dataAttrs("start_game", null) + ">Zaczynamy!</button>";
    return html;
  }

  function renderLobby() {
    var html = '<div class="screen lobby"><header class="bar"><div><strong>Sutoliada</strong><small>Kod gry: ' + esc(state.room) +
      " · Graczy: " + state.players.length + "</small></div></header>" +
      '<main class="content">';
    if (state.notice) html += '<div class="msg bad">' + esc(state.notice) + "</div>";
    html += installHint();
    if (state.isHost) {
      if (!state.tvCount) {
        html += '<div class="msg info tv-missing">Telewizor się rozłączył. Otwórz na nim ponownie:<br><b>' +
          esc(state.tvUrl.replace(/^https?:\/\//, "")) + "</b></div>";
      }
      html += renderLobbyHost();
    } else {
      var game = selectedGame();
      html += '<div class="msg big">' + (game ? "Gospodarz wybrał: " + esc(game.title) : "Gospodarz wybiera grę…") + "</div>";
      if (game) {
        html += '<ul class="rules">';
        game.rules.forEach(function (r) { html += "<li>" + esc(r) + "</li>"; });
        html += "</ul>";
      }
    }
    html += "<h3>W grze</h3>" + renderPlayers();
    html += '<button class="btn ghost leave" data-confirm="Na pewno chcesz opuścić grę?"' + dataAttrs("leave", null) + ">Opuść grę</button>";
    return html + "</main></div>";
  }

  function render() {
    if (!joined || !state) return;
    var active = document.activeElement;
    var typing = !!(active && active.name === "say" && active.form && active.form.getAttribute("data-answer"));
    Core.patch(root, state.game ? renderGame(state.game) : renderLobby());
    if (state.game) Voice.sync(typing);
    else Voice.reset();
    // Nowy ekran zaczyna się od góry, żeby pytanie i przycisk powrotu nie zostały poza widokiem.
    var view = state.game ? "game|" + state.game.prompt : "lobby|" + state.selected;
    if (view !== lastView) {
      lastView = view;
      window.scrollTo(0, 0);
    }
    var urgent = !!(state.game && state.game.blocks && state.game.blocks.some(function (b) {
      return b.type === "options" || b.type === "buzz" || b.type === "buttons" || b.type === "answer";
    }));
    if (urgent && !lastUrgent) vibrate(60);
    lastUrgent = urgent;
  }

  /* --- Zdarzenia --- */

  function handleTap(target) {
    if (target.getAttribute("data-reload")) {
      location.reload();
      return;
    }
    if (target.getAttribute("data-install")) {
      if (deferredInstall) {
        deferredInstall.prompt();
        deferredInstall = null;
        render();
      }
      return;
    }
    if (target.getAttribute("data-dismiss")) {
      hintDismissed = true;
      save(HINT_KEY, "1");
      render();
      return;
    }
    var option = target.getAttribute("data-option");
    if (option) {
      action("set_option", JSON.parse(target.getAttribute("data-value")), { key: option });
      return;
    }
    var question = target.getAttribute("data-confirm");
    if (question && !window.confirm(question)) return;
    var name = target.getAttribute("data-action");
    if (!name) return;
    var value = JSON.parse(target.getAttribute("data-value"));
    if (target.classList.contains("option") || target.classList.contains("btn")) vibrate(15);
    action(name, value);
  }

  function findControl(el) {
    while (el && el !== document) {
      if (el.tagName === "BUTTON" && !el.disabled) return el;
      el = el.parentNode;
    }
    return null;
  }

  // Zgłoszenie liczy się od razu po dotknięciu, bo o wygranej decydują ułamki sekundy.
  var instantHandled = 0;
  document.addEventListener("pointerdown", function (e) {
    var control = findControl(e.target);
    if (control && control.getAttribute("data-instant")) {
      instantHandled = Date.now();
      vibrate(40);
      control.classList.add("pressed");
      action(control.getAttribute("data-action"));
    }
  });

  document.addEventListener("click", function (e) {
    var control = findControl(e.target);
    if (control && control.getAttribute("data-mic")) {
      vibrate(20);
      Voice.toggle(control.form);
      return;
    }
    if (!control || control.form) return;
    if (control.getAttribute("data-instant") && Date.now() - instantHandled < 1000) return;
    handleTap(control);
  });

  document.addEventListener("submit", function (e) {
    var form = e.target;
    if (!form.getAttribute || !form.getAttribute("data-answer")) return;
    e.preventDefault();
    var input = form.elements.say;
    var text = input.value.trim();
    if (!text) return;
    // Warianty rozpoznania mowy pasują tylko do niezmienionego tekstu.
    Voice.send(form, text, form.recognized === text ? form.alts : []);
    if (!form.getAttribute("data-sticky")) input.blur();
  });

  roomInput.addEventListener("input", function () {
    var code = cleanCode(roomInput.value);
    if (roomInput.value !== code) roomInput.value = code;
  });

  joinForm.addEventListener("submit", function (e) {
    e.preventDefault();
    var code = cleanCode(roomInput.value);
    var name = nameInput.value.trim();
    if (code.length !== 4) {
      showJoinError("Wpisz 4-literowy kod z telewizora.");
      return;
    }
    if (!name) {
      showJoinError("Podaj imię.");
      return;
    }
    save(NAME_KEY, name);
    if (code !== room) {
      room = code;
      token = null;
    }
    // Bez połączenia imię czeka i zostanie wysłane zaraz po jego odzyskaniu.
    pendingName = name;
    net.send({ t: "join", room: room, name: name });
  });

  function showJoinError(text) {
    joinError.textContent = text;
    joinError.hidden = false;
  }

  function showJoin() {
    joined = false;
    root.innerHTML = "";
    joinForm.hidden = false;
    roomInput.value = roomInput.value || room;
    nameInput.value = nameInput.value || load(NAME_KEY) || "";
  }

  window.addEventListener("beforeinstallprompt", function (e) {
    e.preventDefault();
    deferredInstall = e;
    render();
  });

  window.addEventListener("appinstalled", function () {
    deferredInstall = null;
    hintDismissed = true;
    render();
  });

  // Bez kodu nie ma na co czekać, a z kodem formularz pokaże się dopiero, gdy serwer o niego poprosi.
  if (room) offline.hidden = false;
  else showJoin();

  net = Core.connect({
    onOpen: function () {
      offline.hidden = true;
      if (room) net.send({ t: "hello", role: "player", room: room, token: token });
    },
    onClose: function () {
      offline.hidden = false;
    },
    onMessage: function (msg) {
      if (msg.t === "welcome") {
        token = msg.token;
        save(TOKEN_KEY, token);
        save(ROOM_KEY, room);
        pendingName = null;
        joined = true;
        joinForm.hidden = true;
        joinError.hidden = true;
        render();
      } else if (msg.t === "need_name") {
        token = null;
        save(TOKEN_KEY, null);
        if (pendingName) net.send({ t: "join", room: room, name: pendingName });
        else showJoin();
      } else if (msg.t === "no_room") {
        // Kod wpisany ręcznie mógł być błędny, a zapamiętana gra mogła się już skończyć.
        showJoinError(pendingName
          ? "Nie ma gry o kodzie " + room + ". Sprawdź kod na telewizorze."
          : "Ta gra już się skończyła. Wpisz kod z telewizora.");
        if (!pendingName) roomInput.value = "";
        pendingName = null;
        room = "";
        token = null;
        save(ROOM_KEY, null);
        save(TOKEN_KEY, null);
        state = null;
        showJoin();
      } else if (msg.t === "removed") {
        token = null;
        save(TOKEN_KEY, null);
        state = null;
        showJoin();
      } else if (msg.t === "replaced") {
        net.stop();
        joined = false;
        offline.hidden = true;
        root.innerHTML = '<div class="screen"><main class="content"><div class="msg big">Gra jest otwarta w innym oknie.</div>' +
          '<button class="btn primary" data-reload="1">Graj tutaj</button></main></div>';
      } else if (msg.t === "error") {
        pendingName = null;
        showJoinError(msg.message);
      } else if (msg.t === "state") {
        state = msg.state;
        render();
      }
    }
  });

  if ("serviceWorker" in navigator && window.isSecureContext) {
    navigator.serviceWorker.register("/app/sw.js", { scope: "/app/" }).catch(function () { /* działa też bez niego */ });
  }
})();

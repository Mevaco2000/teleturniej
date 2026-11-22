/* Wspólny rdzeń klientów. Składnia celowo zachowawcza: przeglądarki w telewizorach bywają
   wiele lat starsze niż w telefonach, a kod nie przechodzi przez żaden kompilator. */
(function () {
  "use strict";

  var Core = {};
  var lastStateAt = 0;

  Core.esc = function (value) {
    return String(value === null || value === undefined ? "" : value)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
  };

  /* --- Aktualizacja DOM bez niszczenia elementów, żeby przejścia CSS działały --- */

  function keyOf(node) {
    return node.nodeType === 1 ? node.getAttribute("data-key") : null;
  }

  function morphAttributes(from, to) {
    var i, attr;
    for (i = from.attributes.length - 1; i >= 0; i--) {
      attr = from.attributes[i];
      if (!to.hasAttribute(attr.name)) from.removeAttribute(attr.name);
    }
    for (i = 0; i < to.attributes.length; i++) {
      attr = to.attributes[i];
      if (from.getAttribute(attr.name) !== attr.value) from.setAttribute(attr.name, attr.value);
    }
  }

  function morphNode(from, to) {
    if (from.nodeType !== 1) {
      if (from.nodeValue !== to.nodeValue) from.nodeValue = to.nodeValue;
      return;
    }
    morphAttributes(from, to);
    morphChildren(from, to);
  }

  function sameKind(a, b) {
    return a.nodeType === b.nodeType && a.nodeName === b.nodeName;
  }

  function morphChildren(parent, target) {
    var keyed = {};
    var unkeyed = [];
    var child = parent.firstChild;
    while (child) {
      var key = keyOf(child);
      if (key) keyed[key] = child; else unkeyed.push(child);
      child = child.nextSibling;
    }
    var cursor = parent.firstChild;
    var wanted = Array.prototype.slice.call(target.childNodes);
    for (var i = 0; i < wanted.length; i++) {
      var node = wanted[i];
      var wantedKey = keyOf(node);
      var match = null;
      if (wantedKey) {
        match = keyed[wantedKey] || null;
        if (match && !sameKind(match, node)) match = null;
        if (match) delete keyed[wantedKey];
      } else if (unkeyed.length && sameKind(unkeyed[0], node)) {
        match = unkeyed.shift();
      } else {
        for (var j = 1; j < unkeyed.length; j++) {
          if (sameKind(unkeyed[j], node)) {
            match = unkeyed.splice(j, 1)[0];
            break;
          }
        }
      }
      if (match) {
        if (match === cursor) cursor = cursor.nextSibling;
        else parent.insertBefore(match, cursor);
        morphNode(match, node);
      } else {
        parent.insertBefore(node.cloneNode(true), cursor);
      }
    }
    Object.keys(keyed).forEach(function (k) { parent.removeChild(keyed[k]); });
    unkeyed.forEach(function (n) { parent.removeChild(n); });
  }

  var scratch = document.createElement("div");

  Core.patch = function (element, html) {
    scratch.innerHTML = html;
    morphChildren(element, scratch);
    scratch.innerHTML = "";
    Core.tick();
  };

  /* --- Odliczanie: serwer podaje pozostały czas, a klient płynnie go zmniejsza --- */

  function timeLeft(el) {
    var ms = parseInt(el.getAttribute("data-ms"), 10) || 0;
    if (el.getAttribute("data-run") !== "1") return ms;
    return Math.max(0, ms - (Date.now() - lastStateAt));
  }

  Core.onSecond = null;

  Core.tick = function () {
    var bars = document.querySelectorAll("[data-bar]");
    var i, left;
    for (i = 0; i < bars.length; i++) {
      var total = parseInt(bars[i].getAttribute("data-total"), 10) || 1;
      left = timeLeft(bars[i]);
      var fill = bars[i].firstChild;
      if (fill) fill.style.width = Math.min(100, left * 100 / total) + "%";
      bars[i].className = bars[i].className.replace(/ ?low/g, "") + (left < 5000 ? " low" : "");
    }
    var clocks = document.querySelectorAll("[data-clock]");
    for (i = 0; i < clocks.length; i++) {
      left = timeLeft(clocks[i]);
      var text = clocks[i].getAttribute("data-clock") === "tenths" && left < 10000
        ? (left / 1000).toFixed(1) : String(Math.ceil(left / 1000));
      if (clocks[i].firstChild && clocks[i].firstChild.nodeValue === text) continue;
      clocks[i].textContent = text;
    }
    if (Core.onSecond) {
      var main = document.querySelector("[data-main-timer]");
      if (main && main.getAttribute("data-run") === "1") Core.onSecond(Math.ceil(timeLeft(main) / 1000));
    }
  };

  setInterval(Core.tick, 100);

  Core.timerBar = function (timer, extra) {
    if (!timer) return "";
    return '<div class="timer-bar ' + (extra || "") + '" data-bar data-main-timer data-ms="' + timer.ms +
      '" data-total="' + timer.total + '" data-run="' + (timer.running ? "1" : "0") + '"><i></i></div>';
  };

  Core.clock = function (timer, mode) {
    if (!timer) return "";
    return '<span class="clock" data-clock="' + (mode || "seconds") + '"' + (mode === "tenths" ? "" : " data-main-timer") +
      ' data-ms="' + timer.ms + '" data-run="' + (timer.running ? "1" : "0") + '"></span>';
  };

  /* --- Flagi rysowane z danych, bo emoji flag nie działają na Windows i wielu telewizorach --- */

  Core.flag = function (flag) {
    if (!flag) return "";
    var c = flag.colors, body = "", i;
    if (flag.dir === "h") {
      for (i = 0; i < c.length; i++) {
        body += '<rect x="0" y="' + (i * 200 / c.length) + '" width="300" height="' + (200 / c.length + 0.5) + '" fill="' + c[i] + '"/>';
      }
    } else if (flag.dir === "v") {
      for (i = 0; i < c.length; i++) {
        body += '<rect x="' + (i * 300 / c.length) + '" y="0" width="' + (300 / c.length + 0.5) + '" height="200" fill="' + c[i] + '"/>';
      }
    } else if (flag.dir === "disc") {
      body = '<rect width="300" height="200" fill="' + c[0] + '"/><circle cx="150" cy="100" r="60" fill="' + c[1] + '"/>';
    } else {
      body = '<rect width="300" height="200" fill="' + c[0] + '"/>' +
        '<rect x="90" y="0" width="40" height="200" fill="' + c[1] + '"/><rect x="0" y="80" width="300" height="40" fill="' + c[1] + '"/>';
      if (c[2]) {
        body += '<rect x="100" y="0" width="20" height="200" fill="' + c[2] + '"/><rect x="0" y="90" width="300" height="20" fill="' + c[2] + '"/>';
      }
    }
    return '<svg class="flag" viewBox="0 0 300 200" xmlns="http://www.w3.org/2000/svg">' + body + "</svg>";
  };

  /* --- Połączenie --- */

  Core.connect = function (opts) {
    var ws = null;
    var attempts = 0;
    var stopped = false;
    var api = { connected: false };

    /* Darmowy hosting usypia serwer po kilkunastu minutach bez wiadomości, a przerwa w grze
       albo długie pytanie nie może go uśpić. */
    setInterval(function () { api.send({ t: "ping" }); }, 60000);

    api.send = function (obj) {
      if (ws && ws.readyState === 1) ws.send(JSON.stringify(obj));
    };

    api.stop = function () {
      stopped = true;
      if (ws) ws.close();
    };

    function open() {
      var scheme = location.protocol === "https:" ? "wss://" : "ws://";
      ws = new WebSocket(scheme + location.host + "/ws");
      ws.onopen = function () {
        attempts = 0;
        api.connected = true;
        if (opts.onOpen) opts.onOpen();
      };
      ws.onmessage = function (event) {
        var msg;
        try { msg = JSON.parse(event.data); } catch (e) { return; }
        if (msg.t === "state") lastStateAt = Date.now();
        opts.onMessage(msg);
      };
      ws.onclose = function () {
        api.connected = false;
        if (stopped) return;
        if (opts.onClose) opts.onClose();
        attempts += 1;
        setTimeout(open, Math.min(4000, 400 * attempts));
      };
      ws.onerror = function () { try { ws.close(); } catch (e) { /* zamknięte */ } };
    }

    open();
    return api;
  };

  window.Core = Core;
})();

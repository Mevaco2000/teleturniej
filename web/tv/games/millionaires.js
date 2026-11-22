(function () {
  "use strict";

  var esc = TV.esc;
  var LETTERS = "ABCD";

  function ladder(g) {
    var html = '<div class="ladder">';
    var climbing = g.mode === "all" ? g.screen !== "intro" : !!g.hot;
    for (var i = g.ladder.length - 1; i >= 0; i--) {
      var cls = "rung";
      if (g.guaranteed.indexOf(i) >= 0) cls += " safe";
      if (climbing && i === g.level) cls += " current";
      if (climbing && i < g.level) cls += " passed";
      html += '<div class="' + cls + '" data-key="l' + i + '"><b>' + (i + 1) + "</b><span>" + esc(g.ladder[i]) + "</span></div>";
    }
    return html + "</div>";
  }

  function lifelines(g) {
    var names = { fifty: "50:50", audience: "Publiczność", phone: "Telefon" };
    var html = '<div class="lifelines">';
    ["fifty", "audience", "phone"].forEach(function (key) {
      html += '<div class="lifeline' + (g.lifelines[key] ? "" : " used") + '">' + names[key] + "</div>";
    });
    return html + "</div>";
  }

  function answers(g) {
    var html = '<div class="mil-answers">';
    g.q.options.forEach(function (opt, i) {
      var cls = "hex";
      if (opt.hidden) cls += " hidden-answer";
      if (g.selected === i) cls += g.screen === "question" ? " picked" : " locked";
      if (g.q.correct !== null && g.q.correct !== undefined) {
        if (i === g.q.correct) cls += " correct";
        else if (i === g.selected) cls += " wrong";
      }
      html += '<div class="' + cls + '" data-key="h' + i + '"><div class="hex-inner"><b>' + LETTERS.charAt(i) + ":</b> <span>" +
        (opt.hidden ? "" : esc(opt.label)) + "</span></div></div>";
    });
    return html + "</div>";
  }

  function pollBars(poll) {
    var html = '<div class="poll">';
    poll.forEach(function (pct, i) {
      html += '<div class="poll-col"><div class="poll-track"><i style="height:' + pct + '%"></i></div><b>' + LETTERS.charAt(i) + "</b><span>" + pct + "%</span></div>";
    });
    return html + "</div>";
  }

  function sidePanel(g) {
    if (g.screen === "audience") {
      return '<div class="side-card"><h3>Pytanie do publiczności</h3><div class="side-big">Głosy: ' + g.votesIn + "</div>" + Core.timerBar(g.helperTimer) + "</div>";
    }
    if (g.screen === "phone_pick") {
      return '<div class="side-card"><h3>Telefon do przyjaciela</h3><div class="side-big">Do kogo dzwonimy?</div>' + Core.timerBar(g.helperTimer) + "</div>";
    }
    if (g.screen === "phone_call") {
      return '<div class="side-card"><h3>Telefon do przyjaciela</h3><div class="side-big">' + (g.friend ? esc(g.friend.name) : "Ekspert w studiu") + "</div>" +
        '<div class="side-clock">' + Core.clock(g.helperTimer) + "</div></div>";
    }
    if (g.poll) return '<div class="side-card"><h3>Publiczność</h3>' + pollBars(g.poll) + "</div>";
    if (g.call) {
      var said = g.call.choice === null ? "nie wie" : "Odpowiedź " + LETTERS.charAt(g.call.choice);
      return '<div class="side-card"><h3>' + esc(g.call.who) + '</h3><div class="side-big">' + said + "</div></div>";
    }
    return "";
  }

  /* --- Zakłady w trybie jednego fotela --- */

  function betLine(g) {
    if (g.betResults && g.betResults.length) {
      return '<div class="bet-line">' + g.betResults.map(function (r) {
        var cls = r.delta > 0 ? "good" : r.delta < 0 ? "bad" : "";
        var delta = r.delta > 0 ? "+" + r.delta : r.delta < 0 ? String(r.delta) : "zwrot";
        return '<span class="' + cls + '">' + esc(r.player.name) + " " + delta + "</span>";
      }).join(" · ") + "</div>";
    }
    if (g.bets && g.bets.right + g.bets.wrong > 0) {
      return '<div class="bet-line">Zakłady widzów: <span class="good">dobrze ' + g.bets.right +
        '</span> · <span class="bad">pomyłka ' + g.bets.wrong + "</span></div>";
    }
    return "";
  }

  /* --- Tryb „Wszyscy na drabince” --- */

  function playerChip(p, g) {
    var cls = "mp " + p.status;
    var note = "";
    if (p.status === "playing") {
      if (g.screen === "reveal" && p.last === "right") {
        cls += " right";
        note = p.earned;
      } else {
        if (p.locked) cls += " locked";
        note = p.locked ? "zatwierdził(a)" : g.screen === "question" ? "myśli…" : "";
      }
    } else if (p.status === "top") {
      cls += " right";
      note = "MILION!";
    } else {
      if (g.screen === "reveal" && (p.last === "wrong" || p.last === "time")) cls += " wrong";
      note = (p.status === "walked" ? "wycofał(a) się · " : "odpada · ") + p.earned;
    }
    return '<div class="' + cls + '" data-key="p' + esc(p.id) + '">' + TV.avatar(p) + "<span>" + esc(p.name) + "</span>" +
      (note ? "<em>" + esc(note) + "</em>" : "") + "</div>";
  }

  function answersAll(g) {
    var html = '<div class="mil-answers">';
    var revealed = g.q.correct !== null && g.q.correct !== undefined;
    g.q.options.forEach(function (opt, i) {
      var pickers = g.players.filter(function (p) { return p.choice === i; });
      var cls = "hex";
      if (revealed && i === g.q.correct) cls += " correct";
      else if (revealed && pickers.length) cls += " wrong";
      html += '<div class="' + cls + '" data-key="h' + i + '"><div class="hex-inner"><b>' + LETTERS.charAt(i) + ":</b> <span>" +
        esc(opt.label) + '</span><span class="pickers">' + pickers.map(function (p) { return TV.avatar(p); }).join("") +
        "</span></div></div>";
    });
    return html + "</div>";
  }

  function renderAll(g) {
    if (g.screen === "intro") {
      return '<div class="mil">' + TV.splash("Milionerzy", "Wszyscy na drabince",
        "Odpowiadacie naraz na telefonach. Każdy sam decyduje, kiedy się wycofać.") + "</div>";
    }
    var line = g.screen === "question" ? "Zatwierdzone odpowiedzi: " + g.decided + " z " + g.playing :
      g.screen === "locked" ? "Sprawdzamy…" : "";
    if (g.screen === "question" && g.votesIn) line += " · głosy publiczności: " + g.votesIn;
    return '<div class="mil mil-game"><div class="mil-left">' +
      '<div class="mil-top"><div class="mil-seat">Pytanie ' + (g.level + 1) + " z " + g.ladder.length + " · za " + esc(g.prize) + "</div>" +
      '<div class="mil-time">' + (g.timer ? Core.clock(g.timer) : "") + "</div></div>" +
      '<div class="mil-players">' + g.players.map(function (p) { return playerChip(p, g); }).join("") + "</div>" +
      '<div class="mil-mid"><div class="mil-status">' + esc(line) + "</div></div>" +
      '<div class="hex hex-q"><div class="hex-inner ' + TV.sizeClass(g.q.text) + '">' + esc(g.q.text) + "</div></div>" +
      answersAll(g) + "</div>" + ladder(g) + "</div>";
  }

  TV.games.millionaires = function (g) {
    if (g.mode === "all") return renderAll(g);
    if (g.screen === "turn_end") {
      return '<div class="mil">' + TV.splash(g.hot.name, g.earned, g.remaining > 1 ? "Kolejne eliminacje za chwilę" : "") +
        betLine(g) + "</div>";
    }
    if (g.screen === "qualify" || g.screen === "qualify_reveal") {
      var reveal = g.screen === "qualify_reveal";
      var w = g.qualifyWinner;
      var line = !reveal ? "Pytanie eliminacyjne · odpowiedzi: " + g.qualifyIn + " z " + g.qualifyTotal :
        (w.seconds !== null ? "Na fotel siada " + esc(w.player.name) + " (" + w.seconds + " s)" : "Nikt nie trafił. Los wybrał: " + esc(w.player.name));
      return '<div class="mil mil-qualify"><div class="mil-tag">' + line + "</div>" +
        '<div class="hex hex-q"><div class="hex-inner ' + TV.sizeClass(g.q.text) + '">' + esc(g.q.text) + "</div></div>" +
        Core.timerBar(g.timer) + answers(g) + "</div>";
    }
    var outcome = "";
    if (g.outcome === "walked") outcome = '<div class="mil-outcome">Wycofuje się z kwotą ' + esc(g.earned) + "</div>";
    if (g.outcome === "wrong") outcome = '<div class="mil-outcome bad">Wygrana: ' + esc(g.earned) + "</div>";
    return '<div class="mil mil-game"><div class="mil-left">' +
      '<div class="mil-top"><div class="mil-seat">' + TV.chip(g.hot) + "</div>" + lifelines(g) +
      '<div class="mil-time">' + (g.timer && g.screen === "question" ? Core.clock(g.timer) : "") + "</div></div>" +
      '<div class="mil-mid">' + sidePanel(g) + outcome + betLine(g) + "</div>" +
      '<div class="hex hex-q"><div class="hex-inner ' + TV.sizeClass(g.q.text) + '">' + esc(g.q.text) + "</div></div>" + answers(g) + "</div>" + ladder(g) + "</div>";
  };
})();

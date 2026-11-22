(function () {
  "use strict";

  var esc = TV.esc;

  function board(g) {
    var seen = {};
    var html = '<div class="board" style="grid-template-columns:repeat(' + g.cols + ",1fr);grid-template-rows:repeat(" + g.rows + ',1fr)">';
    g.tiles.forEach(function (tile, i) {
      var owner = g.owners[tile.owner];
      var cls = "tile";
      if (tile.owner === g.challenger && g.screen !== "board") cls += " challenger";
      if (g.rivals && g.rivals.indexOf(tile.owner) >= 0) cls += " rival";
      else if (g.screen === "pick" && tile.owner !== g.challenger) cls += " dim";
      var first = !seen[tile.owner];
      seen[tile.owner] = true;
      // Kategoria tylko raz, ale nazwa na każdym polu: widać, kto ile już podbił.
      html += '<div class="' + cls + (first ? "" : " conquered") + '" data-key="t' + i + '" style="--tile:' + esc(owner.color) + '">' +
        '<div class="tile-name">' + esc(owner.name) + "</div>" +
        (first ? '<div class="tile-category">' + esc(owner.category) + "</div>" : "") + "</div>";
    });
    return html + "</div>";
  }

  function duelist(g, oid) {
    var owner = g.owners[oid];
    var clock = g.clocks[oid];
    var cls = "duelist" + (g.active === oid && g.screen === "duel" ? " active" : "") + (g.winner === oid ? " won" : "") +
      (g.winner && g.winner !== oid ? " lost" : "");
    return '<div class="' + cls + '" style="--tile:' + esc(owner.color) + '">' + TV.avatar(owner, "big") + '<div class="duelist-name">' + esc(owner.name) + "</div>" +
      '<div class="duelist-clock">' + Core.clock(clock, "tenths") + "</div></div>";
  }

  function card(g) {
    if (!g.card) return "";
    var c = g.card;
    var html = '<div class="card">' +
      (c.flag ? '<div class="card-flag">' + Core.flag(c.flag) + "</div>" : "") +
      '<div class="card-prompt">' + esc(c.prompt) + "</div>" +
      (c.clue ? '<div class="card-clue">' + esc(c.clue) + "</div>" : "");
    // W trybie „Z głowy” opcji nie ma: gracze mówią odpowiedź do telefonu.
    if (c.options) {
      html += '<div class="card-options">';
      c.options.forEach(function (label, i) {
        html += '<div class="card-option" data-key="o' + i + esc(label) + '">' + esc(label) + "</div>";
      });
      html += "</div>";
    }
    return html + "</div>";
  }

  function feedback(g) {
    if (!g.feedback || g.screen !== "duel") return '<div class="feedback"></div>';
    var f = g.feedback;
    var cls = f.correct === true ? "good" : f.correct === false ? "bad" : "pass";
    var who = g.owners[f.who] ? g.owners[f.who].name : "";
    var text = f.correct === true ? "Dobrze: " + f.label : f.correct === false ? "Źle: " + f.label : "Pas";
    return '<div class="feedback ' + cls + '">' + esc(who) + " · " + esc(text) + "</div>";
  }

  function duel(g) {
    var center = "";
    if (g.screen === "duel_intro") {
      center = TV.splash("Pojedynek", g.category, "Kategoria obrońcy. Zaczyna wyzywający.");
    } else if (g.screen === "duel_end") {
      center = TV.splash("Wygrywa", g.owners[g.winner].name, "Przejmuje pola rywala.");
    } else {
      center = '<div class="duel-category">' + esc(g.category) + "</div>" + card(g) + feedback(g);
    }
    return '<div class="duel-screen">' + duelist(g, g.challenger) + '<div class="duel-center">' + center + "</div>" + duelist(g, g.defender) + "</div>";
  }

  TV.games.floor = function (g) {
    if (g.screen === "duel" || g.screen === "duel_intro" || g.screen === "duel_end") {
      return '<div class="floor">' + duel(g) + "</div>";
    }
    var line = "";
    if (g.screen === "board") line = "Oto plansza. Każdy broni swojej kategorii.";
    if (g.screen === "challenger") line = "Losowanie: wyzywa " + esc(g.owners[g.challenger].name);
    if (g.screen === "pick") line = esc(g.owners[g.challenger].name) + " wybiera przeciwnika na telefonie";
    return '<div class="floor"><div class="floor-line">' + line + "</div>" + Core.timerBar(g.timer) + board(g) + "</div>";
  };
})();

(function () {
  "use strict";

  var esc = TV.esc;
  var ROUNDS = {
    1: ["Runda 1", "Po dwa pytania", "Każdy ma trzy szanse."],
    2: ["Runda 2", "Wskazywanie", "Kto odpowie dobrze, wskazuje kolejną osobę. Gramy, aż zostanie trójka."],
    3: ["Finał", "Walka o punkty", "Zgłaszajcie się na telefonach. Po dobrej odpowiedzi: +20 na siebie albo wskazanie rywala."]
  };

  function podiums(g) {
    var html = '<div class="pods pods-' + (g.players.length > 6 ? "many" : "few") + '">';
    g.players.forEach(function (p) {
      var lives = "";
      for (var i = 0; i < 3; i++) lives += '<i class="bulb' + (i < p.lives ? " on" : "") + '"></i>';
      html += '<div class="pod' + (p.active ? " active" : "") + (p.lives <= 0 ? " out" : "") + '" data-key="p' + esc(p.id) + '">' +
        '<div class="pod-name">' + esc(p.name) + '</div><div class="bulbs">' + lives + "</div>" +
        (g.round === 3 ? '<div class="pod-points">' + p.points + "</div>" : "") + "</div>";
    });
    return html + "</div>";
  }

  TV.games.one_of_ten = function (g) {
    var main = "";
    if (g.screen === "round") {
      var r = ROUNDS[g.round];
      main = TV.splash(r[0], r[1], r[2]);
    } else if (g.screen === "pick") {
      main = '<div class="status-big">' + TV.chip(g.picker, "big") + '<div class="status-text">wskazuje kolejną osobę</div></div>' + Core.timerBar(g.timer);
    } else if (g.screen === "choice") {
      main = '<div class="status-big">' + TV.chip(g.picker, "big") + '<div class="status-text">bierze pytanie na siebie (+20) czy wskazuje rywala?</div></div>' + Core.timerBar(g.timer);
    } else if (g.q) {
      var heading = g.screen === "buzz" ? "Kto pierwszy? Zgłaszajcie się na telefonach!" :
        g.answerer ? esc(g.answerer.name) + (g.value === 20 ? " odpowiada za 20 punktów" : " odpowiada") : "Nikt się nie zgłosił";
      main = '<div class="who-line">' + heading + "</div>" +
        '<div class="q-card ' + TV.sizeClass(g.q.text) + '">' + esc(g.q.text) + "</div>" +
        (g.screen === "buzz" ? "" : Core.timerBar(g.timer));
      if (g.q.options) {
        main += TV.answersGrid(g.q.options, g.q.correct, g.result ? g.result.chosen : null);
      } else {
        main += Core.timerBar(g.timer);
      }
      if (g.screen === "reveal" && g.result && g.result.correct === null) {
        main += '<div class="reveal-note">Nikt się nie zgłosił.</div>';
      }
    }
    return '<div class="oot"><div class="round-tag">' + esc(ROUNDS[g.round][0]) + '</div><div class="oot-main">' + main + "</div>" + podiums(g) + "</div>";
  };
})();

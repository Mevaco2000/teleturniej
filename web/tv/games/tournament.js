/* Ekrany turnieju między grami: typowanie podium, wyniki gry i tabela. W trakcie gry telewizor
   rysuje ekran samej gry, a tv.js dokłada tylko pasek „Turniej · gra X z Y”. */
(function () {
  "use strict";

  var esc = TV.esc;

  function progress(g) {
    var html = '<div class="tour-games">';
    g.games.forEach(function (title, i) {
      var cls = i + 1 < g.progress.number ? "done" : i + 1 === g.progress.number ? "now" : "";
      html += '<span class="' + cls + '">' + esc(title) + "</span>";
    });
    return html + "</div>";
  }

  function predict(g) {
    var html = TV.splash("Gra " + g.progress.number + " z " + g.progress.total, g.game,
      "Typujcie na telefonach, kto zajmie miejsca 1–" + g.tipSlots + ". Trafione miejsce: 3 pkt, o jedno obok: 1 pkt.");
    html += '<div class="tour-tipped">';
    g.tipped.forEach(function (p) {
      html += '<span class="mp' + (p.done ? " locked" : "") + '" data-key="p' + esc(p.id) + '">' + TV.avatar(p) +
        "<span>" + esc(p.name) + "</span><em>" + (p.done ? "gotowe" : "typuje…") + "</em></span>";
    });
    return html + "</div>" + Core.timerBar(g.timer);
  }

  function scores(g) {
    var last = g.last;
    var html = '<div class="tour-title">Wyniki: ' + esc(last.game) + '</div><table class="tour-table"><tr><th></th><th></th>' +
      "<th>Za miejsce</th>" + (g.tipSlots ? "<th>Typy</th><th>Za typy</th>" : "") + "<th>Razem</th></tr>";
    last.rows.forEach(function (r) {
      html += '<tr data-key="r' + esc(r.player.id) + '"><td class="tour-place">' + (r.place ? r.place + "." : "–") + "</td>" +
        "<td>" + TV.chip(r.player) + "</td><td>+" + r.placePoints + "</td>" +
        (g.tipSlots ? '<td class="tour-tips">' + esc(r.tips.join(", ") || "brak") + "</td><td>+" + r.tipPoints + "</td>" : "") +
        "<td><b>+" + (r.placePoints + r.tipPoints) + "</b></td></tr>";
    });
    return html + "</table>";
  }

  function table(g) {
    var html = '<div class="tour-title">Tabela turnieju po ' + g.progress.number + " z " + g.progress.total + " gier</div>" +
      '<table class="tour-table standings">';
    g.table.forEach(function (r) {
      html += '<tr data-key="t' + esc(r.player.id) + '"><td class="tour-place">' + r.place + ".</td><td>" + TV.chip(r.player) +
        '</td><td class="tour-gain">' + (r.gained ? "+" + r.gained : "") + '</td><td><b>' + r.points + " pkt</b></td></tr>";
    });
    return html + "</table>";
  }

  TV.games.tournament = function (g) {
    var body = "";
    if (g.screen === "predict") body = predict(g);
    else if (g.screen === "next") body = TV.splash("Gra " + g.progress.number + " z " + g.progress.total, g.game, "Zaczynamy za chwilę!");
    else if (g.screen === "scores" && g.last) body = scores(g);
    else if (g.screen === "table" && g.table) body = table(g);
    else if (g.screen === "skipped") body = TV.splash("Turniej", "Pomijamy grę", g.note);
    return '<div class="tour">' + progress(g) + body + "</div>";
  };
})();

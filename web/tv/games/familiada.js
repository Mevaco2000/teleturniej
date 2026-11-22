(function () {
  "use strict";

  var esc = TV.esc;

  function teamPanel(team, index, g) {
    var active = g.answerer && team.players.some(function (p) { return p.id === g.answerer.id; });
    var html = '<div class="team' + (active ? " active" : "") + (g.control === index ? " control" : "") + '" style="--team:' + esc(team.color) + '">' +
      '<div class="team-name">' + esc(team.name) + '</div><div class="team-score">' + team.score + '</div><div class="team-players">';
    team.players.forEach(function (p) {
      var isAnswerer = g.answerer && g.answerer.id === p.id;
      html += '<div class="team-player' + (isAnswerer ? " now" : "") + '" data-key="p' + esc(p.id) + '">' + esc(p.name) + "</div>";
    });
    return html + "</div></div>";
  }

  function boardRows(g) {
    var html = '<div class="fam-board">';
    g.board.forEach(function (row) {
      var shown = row.label !== null;
      html += '<div class="fam-row' + (shown ? " shown" : "") + (row.earned ? " earned" : "") + '" data-key="r' + row.n + '">' +
        '<span class="fam-n">' + row.n + '</span><span class="fam-label">' + (shown ? esc(row.label) : "") +
        '</span><span class="fam-points">' + (shown ? row.points : "--") + "</span></div>";
    });
    return html + '<div class="fam-row fam-sum"><span class="fam-n"></span><span class="fam-label">Suma' +
      (g.multiplier > 1 ? " × " + g.multiplier : "") + '</span><span class="fam-points">' + g.bank + "</span></div></div>";
  }

  function strikes(g) {
    var html = '<div class="strikes">';
    for (var i = 0; i < 3; i++) html += '<span class="strike' + (i < g.strikes ? " on" : "") + '">X</span>';
    return html + "</div>";
  }

  function statusLine(g) {
    if (g.screen === "duel_buzz") {
      return "Pojedynek: " + g.duelists.map(function (p) { return esc(p.name); }).join(" kontra ") + ". Kto pierwszy?";
    }
    if (g.screen === "answer") {
      var who = esc(g.answerer.name);
      if (g.mode === "steal") return who + " przejmuje pytanie! Jedna odpowiedź.";
      return who + " odpowiada";
    }
    if (g.screen === "picked" && g.lastPick) {
      var pick = g.lastPick;
      if (!pick.label) return esc(pick.player.name) + ": czas minął!";
      return esc(pick.player.name) + ": " + esc(pick.label) + (pick.hit ? " (+" + pick.points + ")" : " — nie ma na tablicy!");
    }
    if (g.screen === "round_end") {
      return "Rundę wygrywają " + esc(g.teams[g.roundWinner].name) + ": +" + g.bank * g.multiplier + " pkt";
    }
    return "";
  }

  TV.games.familiada = function (g) {
    if (g.screen === "teams") {
      var teams = '<div class="fam-teams">';
      g.teams.forEach(function (team) {
        teams += '<div class="fam-team" style="--team:' + esc(team.color) + '"><h2>' + esc(team.name) + "</h2>";
        team.players.forEach(function (p) { teams += "<div>" + esc(p.name) + "</div>"; });
        teams += "</div>";
      });
      return '<div class="fam"><div class="fam-title">Drużyny</div>' + teams + "</div></div>";
    }
    if (g.screen === "round") {
      return '<div class="fam">' + TV.splash("Runda " + g.round, g.multiplier > 1 ? "Punkty × " + g.multiplier : "Punkty × 1",
        g.round > g.rounds ? "Dogrywka!" : "Runda " + g.round + " z " + g.rounds) + "</div>";
    }
    var miss = g.screen === "picked" && g.lastPick && !g.lastPick.hit;
    return '<div class="fam"><div class="fam-question ' + TV.sizeClass(g.question) + '">' + esc(g.question) + "</div>" +
      '<div class="fam-layout">' + teamPanel(g.teams[0], 0, g) + '<div class="fam-center">' + boardRows(g) + strikes(g) + "</div>" + teamPanel(g.teams[1], 1, g) + "</div>" +
      '<div class="fam-status ' + (miss ? "bad" : "") + '">' + statusLine(g) + "</div>" + Core.timerBar(g.timer) +
      (miss ? '<div class="big-x">X</div>' : "") + "</div>";
  };
})();

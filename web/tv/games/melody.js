(function () {
  "use strict";

  var esc = TV.esc;
  var EQ_BARS = 28;

  function equalizer(playing) {
    var html = '<div class="eq' + (playing ? " playing" : "") + '">';
    for (var i = 0; i < EQ_BARS; i++) {
      // Deterministyczne wartości: przy każdej aktualizacji słupki zachowują ten sam rytm.
      var delay = ((i * 37) % 11) / 10;
      var speed = 0.5 + ((i * 53) % 7) / 10;
      html += '<i style="animation-delay:-' + delay + "s;animation-duration:" + speed + 's"></i>';
    }
    return html + "</div>";
  }

  function scoreboard(g) {
    var html = '<div class="scores' + (g.scores.length > 9 ? " many" : "") + '">';
    g.scores.forEach(function (p) {
      var cls = "score-row" + (p.locked ? " locked" : "") + (g.answerer && g.answerer.id === p.id ? " active" : "");
      html += '<div class="' + cls + '" data-key="p' + esc(p.id) + '">' + TV.avatar(p) + '<span class="chip-name">' + esc(p.name) + "</span>" +
        (g.screen === "bid" ? '<em class="' + (p.bid ? "bid-in" : "bid-wait") + '">' + (p.bid ? "✓" : "…") + "</em>" : "<b>" + p.points + "</b>") + "</div>";
    });
    return html + "</div>";
  }

  function main(g) {
    switch (g.screen) {
      case "loading":
        return '<div class="status-big"><div class="status-text">Przygotowuję utwory…</div><div class="status-sub">' +
          g.progress.done + " z " + g.progress.total + "</div></div>";
      case "round":
        return g.round === 1
          ? TV.splash("Runda 1", "Znasz to? Zgłoś się!", "Im szybciej, tym więcej punktów.")
          : TV.splash("Runda 2", "Licytacja", "Tajnie zadeklaruj, ile sekund wystarczy Ci, by rozpoznać utwór.");
      case "cue":
        return '<div class="status-big"><div class="status-text">Uwaga…</div></div>' + equalizer(false);
      case "play":
        return '<div class="mel-title">Jaka to melodia?</div>' + equalizer(true) + Core.timerBar(g.clip) +
          (g.result && g.result.wrong ? '<div class="reveal-note bad">' + esc(g.result.player.name) +
            (g.result.said ? ": „" + esc(g.result.said) + "”" : "") + " — źle! Muzyka gra dalej.</div>"
            : '<div class="reveal-note">Zgłoś się na telefonie!</div>');
      case "answer":
        return '<div class="status-big">' + TV.chip(g.answerer, "big") + '<div class="status-text">' + (g.voice ? "mówi tytuł" : "wybiera tytuł") +
          "</div></div>" + equalizer(false) + Core.timerBar(g.timer);
      case "bid":
        return '<div class="mel-title">Ile sekund Ci wystarczy?</div><div class="status-sub">Licytuj na telefonie. Najniższa oferta gra.</div>' + Core.timerBar(g.timer);
      case "bid_play":
        return '<div class="status-big">' + TV.chip(g.bidWinner, "big") + '<div class="status-text">gra w ' + g.bidValue + " s</div></div>" + equalizer(true) + Core.timerBar(g.clip);
      case "reveal":
        var r = g.result || {};
        var art = g.track && g.track.art
          ? '<img class="art" src="' + esc(g.track.art) + '" alt="">'
          : '<div class="art art-empty">♪</div>';
        var outcome = r.winner ? esc(r.winner.name) + ": +" + r.points + " pkt"
          : r.answeredBy ? esc(r.answeredBy.name) + (r.wrongAnswer ? ": „" + esc(r.wrongAnswer) + "” — źle" : ": czas minął") : "Nikt nie odgadł";
        return '<div class="reveal-track">' + art + '<div><div class="track-title">' + esc(g.track ? g.track.title : "") +
          '</div><div class="track-artist">' + esc(g.track ? g.track.artist : "") + '</div><div class="track-outcome ' + (r.winner ? "good" : "bad") + '">' + outcome + "</div></div></div>";
    }
    return "";
  }

  TV.games.melody = function (g) {
    var counter = g.total && g.number > 0 && g.number <= g.total ? "Utwór " + g.number + " z " + g.total : "";
    return '<div class="mel"><div class="mel-main"><div class="round-tag">' + (g.round === 2 ? "Licytacja" : "Zgłoszenia") +
      (counter ? " · " + counter : "") + '</div><div class="mel-center">' + main(g) + "</div></div>" + scoreboard(g) + "</div>";
  };
})();

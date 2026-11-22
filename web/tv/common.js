/* Elementy wspólne dla ekranów TV. */
(function () {
  "use strict";

  var esc = Core.esc;

  window.TV = {
    games: {},

    esc: esc,

    avatar: function (p, cls) {
      if (!p) return "";
      var letter = (p.name || "?").charAt(0).toUpperCase();
      return '<span class="avatar ' + (cls || "") + '" style="background:' + esc(p.color) + '">' + esc(letter) + "</span>";
    },

    chip: function (p, cls) {
      if (!p) return "";
      return '<span class="chip ' + (cls || "") + '">' + TV.avatar(p) + '<span class="chip-name">' + esc(p.name) + "</span></span>";
    },

    /* Dłuższe pytania dostają mniejszą czcionkę, żeby zawsze mieściły się na ekranie. */
    sizeClass: function (text) {
      var n = (text || "").length;
      return n > 110 ? "text-xl" : n > 70 ? "text-l" : "text-m";
    },

    splash: function (kicker, title, sub) {
      return '<div class="splash"><div class="splash-kicker">' + esc(kicker) + '</div><div class="splash-title">' + esc(title) +
        "</div>" + (sub ? '<div class="splash-sub">' + esc(sub) + "</div>" : "") + "</div>";
    },

    answersGrid: function (options, correct, chosen) {
      var html = '<div class="answers">';
      options.forEach(function (label, i) {
        var cls = "answer";
        if (correct !== null && correct !== undefined) {
          if (i === correct) cls += " correct";
          else if (i === chosen) cls += " wrong";
          else cls += " dim";
        }
        html += '<div class="' + cls + '" data-key="a' + i + '"><b>' + "ABCD".charAt(i) + "</b><span>" + esc(label) + "</span></div>";
      });
      return html + "</div>";
    },

    results: function (g) {
      var html = '<div class="results"><div class="results-title">' + esc(g.title) + '</div>';
      var podium = g.ranking.slice(0, 3);
      var order = podium.length === 3 ? [podium[1], podium[0], podium[2]] : podium;
      html += '<div class="podium">';
      order.forEach(function (r) {
        html += '<div class="step step-' + r.place + '">' + TV.avatar(r, "big") + '<div class="step-name">' + esc(r.name) +
          '</div><div class="step-score">' + esc(r.label) + '</div><div class="step-block">' + r.place + "</div></div>";
      });
      html += "</div>";
      var rest = g.ranking.slice(3);
      if (rest.length) {
        html += '<div class="rest">';
        rest.forEach(function (r) {
          html += '<span class="rest-item"><b>' + r.place + ".</b> " + esc(r.name) + " <em>" + esc(r.label) + "</em></span>";
        });
        html += "</div>";
      }
      if (g.note) html += '<div class="results-note">' + esc(g.note) + "</div>";
      return html + '<div class="results-hint">Gospodarz wraca do wyboru gry na telefonie</div></div>';
    }
  };
})();

/* Dźwięk na telewizorze: efekty i melodie są syntezowane, a utwory grane z plików serwera.
   Przeglądarki blokują dźwięk do pierwszego naciśnięcia klawisza, stąd funkcja unlock. */
(function () {
  "use strict";

  var ctx = null;
  var unlocked = false;
  var AudioContextClass = window.AudioContext || window.webkitAudioContext;

  function context() {
    if (!ctx && AudioContextClass) ctx = new AudioContextClass();
    return ctx;
  }

  function tone(freq, start, length, type, volume) {
    var c = context();
    if (!c) return;
    var osc = c.createOscillator();
    var gain = c.createGain();
    var at = c.currentTime + start;
    osc.type = type || "sine";
    osc.frequency.value = freq;
    gain.gain.setValueAtTime(0.0001, at);
    gain.gain.linearRampToValueAtTime(volume || 0.25, at + 0.012);
    gain.gain.exponentialRampToValueAtTime(0.0001, at + length);
    osc.connect(gain);
    gain.connect(c.destination);
    osc.start(at);
    osc.stop(at + length + 0.03);
  }

  function seq(notes, type, volume) {
    var time = 0;
    notes.forEach(function (n) {
      tone(n[0], time, n[1] * 1.4, type, volume);
      time += n[1];
    });
  }

  var EFFECTS = {
    good: function () { seq([[523, 0.09], [659, 0.09], [784, 0.2]], "triangle", 0.3); },
    bad: function () { seq([[196, 0.18], [147, 0.34]], "sawtooth", 0.18); },
    buzz: function () { tone(880, 0, 0.09, "square", 0.2); tone(1175, 0.08, 0.2, "square", 0.2); },
    reveal: function () { seq([[392, 0.07], [523, 0.07], [659, 0.16]], "triangle", 0.3); },
    strike: function () { tone(110, 0, 0.55, "sawtooth", 0.3); tone(116, 0, 0.55, "square", 0.14); },
    lock: function () { seq([[294, 0.14], [294, 0.14], [349, 0.3]], "triangle", 0.26); },
    question: function () { seq([[220, 0.12], [277, 0.12], [330, 0.24]], "sine", 0.22); },
    lifeline: function () { seq([[659, 0.08], [880, 0.08], [1047, 0.18]], "sine", 0.24); },
    phone: function () { for (var i = 0; i < 4; i++) { tone(800, i * 0.18, 0.08, "sine", 0.2); tone(960, i * 0.18 + 0.08, 0.08, "sine", 0.2); } },
    fanfare: function () { seq([[523, 0.14], [523, 0.07], [523, 0.07], [659, 0.18], [784, 0.18], [1047, 0.5]], "triangle", 0.32); },
    tick: function () { tone(1200, 0, 0.04, "square", 0.05); }
  };

  /* --- Melodie z nut --- */

  var NOTE_OFFSETS = { C: -9, D: -7, E: -5, F: -4, G: -2, A: 0, B: 2 };

  function noteFrequency(name) {
    var m = /^([A-G])(#?)(\d)$/.exec(name);
    if (!m) return 0;
    var semitones = NOTE_OFFSETS[m[1]] + (m[2] ? 1 : 0) + (parseInt(m[3], 10) - 4) * 12;
    return 440 * Math.pow(2, semitones / 12);
  }

  var synth = { melody: null, index: 0, nextTime: 0, timer: null };

  function synthStep() {
    var c = context();
    if (!c || !synth.melody) return;
    var beat = 60 / synth.melody.tempo;
    while (synth.nextTime < c.currentTime + 0.18) {
      var note = synth.melody.notes[synth.index];
      var length = note[1] * beat;
      var freq = noteFrequency(note[0]);
      if (freq) {
        var offset = Math.max(0, synth.nextTime - c.currentTime);
        tone(freq, offset, Math.max(0.12, length * 0.95), "triangle", 0.34);
        tone(freq * 2, offset, Math.max(0.1, length * 0.6), "sine", 0.07);
      }
      synth.nextTime += length;
      synth.index += 1;
      if (synth.index >= synth.melody.notes.length) {
        synth.index = 0;
        synth.nextTime += beat * 2;
      }
    }
  }

  function synthPlay() {
    var c = context();
    if (!c || synth.timer) return;
    synth.nextTime = c.currentTime + 0.05;
    synth.timer = setInterval(synthStep, 50);
    synthStep();
  }

  function synthPause() {
    if (synth.timer) {
      clearInterval(synth.timer);
      synth.timer = null;
    }
  }

  /* --- Odtwarzacz sterowany stanem z serwera --- */

  var element = new Audio();
  element.preload = "auto";
  var current = { token: null, kind: null, ready: false, wantPlay: false };
  var send = function () {};
  var onBlocked = function () {};

  function markReady() {
    if (current.ready || current.token === null) return;
    current.ready = true;
    send("audio_ready", current.token);
    applyPlaying();
  }

  element.addEventListener("loadedmetadata", function () {
    var start = current.start || 0;
    if (start && element.duration && start < element.duration - 5) {
      try { element.currentTime = start; } catch (e) { /* zagramy od początku */ }
    }
  });
  element.addEventListener("canplay", markReady);
  element.addEventListener("error", function () {
    if (current.kind === "file" && current.token !== null && !current.ready) {
      send("audio_error", current.token);
    }
  });

  function applyPlaying() {
    if (current.kind === "synth") {
      if (current.wantPlay) synthPlay(); else synthPause();
      return;
    }
    if (current.kind !== "file" || !current.ready) return;
    if (current.wantPlay) {
      var result = element.play();
      if (result && result.catch) {
        result.catch(function (err) {
          if (err && err.name === "NotAllowedError") {
            unlocked = false;
            onBlocked();
          }
        });
      }
    } else {
      element.pause();
    }
  }

  function stopAll() {
    synthPause();
    synth.melody = null;
    element.pause();
    if (element.getAttribute("src")) {
      element.removeAttribute("src");
      element.load();
    }
    current = { token: null, kind: null, ready: false, wantPlay: false };
  }

  window.Sound = {
    configure: function (sendFn, blockedFn) {
      send = sendFn;
      onBlocked = blockedFn;
    },

    isUnlocked: function () { return unlocked; },

    unlock: function () {
      var c = context();
      if (c && c.state === "suspended" && c.resume) c.resume();
      if (c) tone(1, 0, 0.01, "sine", 0.0002);
      unlocked = true;
      applyPlaying();
    },

    effect: function (name) {
      var c = context();
      if (c && c.state === "suspended" && c.resume) c.resume();
      if (EFFECTS[name]) EFFECTS[name]();
    },

    /* audio = {token, src, melody, start, playing} lub null */
    apply: function (audio) {
      if (!audio) {
        if (current.token !== null) stopAll();
        return;
      }
      if (audio.token !== current.token) {
        stopAll();
        current.token = audio.token;
        current.start = audio.start;
        if (audio.melody) {
          current.kind = "synth";
          synth.melody = audio.melody;
          synth.index = 0;
          current.wantPlay = audio.playing;
          markReady();
          return;
        }
        current.kind = "file";
        element.src = audio.src;
        element.load();
      }
      if (current.wantPlay !== audio.playing) {
        current.wantPlay = audio.playing;
        applyPlaying();
      }
    }
  };
})();

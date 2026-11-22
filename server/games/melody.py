"""Jaka to melodia: dźwięk gra na telewizorze, a telefony służą do zgłaszania się i odpowiedzi."""
from __future__ import annotations

from typing import Optional

from .base import Game, btn, buttons, buzz, msg, options

CLIP_SECONDS = 20
ANSWER_SECONDS = 8
BID_SECONDS = 10
REVEAL_SECONDS = 6
INTRO_SECONDS = 4
AUDIO_READY_TIMEOUT = 8
BIDS = (1, 2, 3, 5, 8, 12)
BID_POINTS = {1: 200, 2: 150, 3: 120, 5: 100, 8: 70, 12: 50}
MAX_CONSECUTIVE_AUDIO_ERRORS = 3


class Melody(Game):
    id = "melody"
    title = "Jaka to melodia"
    tagline = "Rozpoznaj utwór szybciej niż inni."
    min_players = 1
    needs_tv = True
    rules = [
        "Muzyka gra na telewizorze. Znasz utwór? Zgłoś się na telefonie.",
        "Kto zgłosi się pierwszy, wybiera tytuł spośród czterech. Im szybciej, tym więcej punktów.",
        "Zła odpowiedź blokuje Cię na ten utwór, a muzyka gra dalej dla pozostałych.",
        "Licytacja: tajnie deklarujesz, ile sekund potrzebujesz. Najniższa oferta gra i odpowiada.",
    ]
    option_defs = [
        {"key": "category", "label": "Muzyka", "default": "all", "choices": [
            {"v": "all", "l": "Wszystko"}, {"v": "pl", "l": "Polskie"}, {"v": "int", "l": "Zagraniczne"},
            {"v": "old", "l": "Do lat 70."}, {"v": "80", "l": "Lata 80."}, {"v": "90", "l": "Lata 90."},
            {"v": "00", "l": "Lata 2000"}, {"v": "10", "l": "Lata 2010"}, {"v": "20", "l": "Lata 2020"},
        ]},
        {"key": "count", "label": "Liczba utworów", "default": 9, "choices": [
            {"v": 6, "l": "6"}, {"v": 9, "l": "9"}, {"v": 12, "l": "12"}, {"v": 15, "l": "15"},
        ]},
        {"key": "source", "label": "Źródło", "default": "auto", "choices": [
            {"v": "auto", "l": "Hity + moje MP3"}, {"v": "own", "l": "Tylko moje MP3"},
            {"v": "builtin", "l": "Melodie wbudowane"},
        ]},
    ]

    def start(self) -> None:
        self.points = {p: 0 for p in self.roster}
        self.tracks: list = []
        self.index = -1
        self.track = None
        self.round = 1
        self.audio: Optional[dict] = None
        self._audio_token = 0
        self.locked: set[str] = set()
        self.answerer: Optional[str] = None
        self.option_labels: list[str] = []
        self.correct = 0
        self.result: Optional[dict] = None
        self.bids: dict[str, tuple[int, float]] = {}
        self.bid_winner: Optional[str] = None
        self.bid_value = 0
        self.progress = {"done": 0, "total": self.opts["count"]}
        self._errors = 0
        self.screen = "loading"
        self.s.spawn(self._prepare())

    async def _prepare(self) -> None:
        def progress(done: int, total: int) -> None:
            self.progress = {"done": done, "total": total}
            self.s.touch()

        try:
            tracks = await self.s.music.prepare(
                self.opts["count"], self.opts["category"], self.opts["source"], progress)
        except Exception:
            self.s.guard(self._raise_prepare_error)
            return
        if not self.stopped:
            self.tracks = tracks
            self.bid_start = len(tracks) - max(1, len(tracks) // 3)
            self.s.guard(self._begin)

    @staticmethod
    def _raise_prepare_error() -> None:
        raise RuntimeError("Nie udało się przygotować utworów")

    def _begin(self) -> None:
        self.screen = "round"
        self.set_timer(INTRO_SECONDS, self._next_song)

    # --- Utwory ------------------------------------------------------------

    def _next_song(self) -> None:
        self._stop_audio()
        self.index += 1
        if self.index >= len(self.tracks):
            self._finish()
            return
        if self.index == self.bid_start and self.round == 1 and len(self.tracks) > 1:
            self.round = 2
            self.screen = "round"
            self.index -= 1
            self.set_timer(INTRO_SECONDS, self._next_song)
            return
        self.track = self.tracks[self.index]
        self.option_labels, self.correct = self.s.music.options_for(self.track, self.tracks)
        self.locked = set()
        self.answerer = None
        self.result = None
        self.bids = {}
        self.bid_winner = None
        if self.round == 1:
            self._cue(self._start_buzz_clip)
        else:
            self._start_bidding()

    def _cue(self, on_ready) -> None:
        self.screen = "cue"
        self._audio_token += 1
        track = self.track
        self.audio = {
            "token": self._audio_token,
            "src": f"/media/song/{track.id}" if track.path else None,
            "melody": track.melody,
            "start": track.start,
            "playing": False,
        }
        self._on_ready = on_ready
        self.set_timer(AUDIO_READY_TIMEOUT, self._audio_failed, name="cue")

    def _audio_failed(self) -> None:
        self.cancel_timer("cue")
        self._errors += 1
        if self._errors >= MAX_CONSECUTIVE_AUDIO_ERRORS:
            self._stop_audio()
            self.s.abort_game("Telewizor nie może odtworzyć muzyki. Sprawdź ekran TV i spróbuj ponownie.")
            return
        self._next_song()

    def on_tv_event(self, event, m: dict) -> None:
        if not self.audio or m.get("token") != self.audio["token"] or self.screen != "cue":
            return
        if event == "audio_ready":
            self._errors = 0
            self.cancel_timer("cue")
            self._on_ready()
        elif event == "audio_error":
            self._audio_failed()

    def _stop_audio(self) -> None:
        self.audio = None

    def _set_playing(self, playing: bool) -> None:
        if self.audio:
            self.audio["playing"] = playing

    # --- Runda 1: zgłoszenia -----------------------------------------------

    def _start_buzz_clip(self) -> None:
        self.screen = "play"
        self._set_playing(True)
        self.set_timer(CLIP_SECONDS, self._clip_over, name="clip")

    def _clip_over(self) -> None:
        self._reveal(None, 0)

    def _buzzed(self, pid: str) -> None:
        self.fx("buzz")
        self.answerer = pid
        self.locked.add(pid)
        self._set_playing(False)
        self.pause_timer("clip")
        self.screen = "answer"
        self.set_timer(ANSWER_SECONDS, lambda: self._answered(None))

    def _answered(self, chosen: Optional[int]) -> None:
        self.cancel_timer()
        pid = self.answerer
        if self.round == 2:
            points = BID_POINTS[self.bid_value] if chosen == self.correct else 0
            self._reveal(pid if points else None, points, chosen=chosen, answered_by=pid)
        elif chosen == self.correct:
            left = self.time_left("clip") / CLIP_SECONDS
            self._reveal(pid, max(20, round(100 * left / 5) * 5), chosen=chosen, answered_by=pid)
        else:
            self.fx("bad")
            self.result = {"wrong": True, "player": self.s.pinfo(pid)}
            self.answerer = None
            everyone_locked = all(p in self.locked or not self.s.is_connected(p) for p in self.roster)
            if everyone_locked:
                self._reveal(None, 0)
            else:
                self.screen = "play"
                self._set_playing(True)
                self.resume_timer("clip")

    def _reveal(self, winner: Optional[str], points: int, chosen: Optional[int] = None,
                answered_by: Optional[str] = None) -> None:
        self.cancel_timer("clip")
        self.cancel_timer()
        if winner:
            self.points[winner] += points
            self.fx("good")
        elif answered_by:
            self.fx("bad")
        self.result = {
            "winner": self.pinfo(winner),
            "points": points,
            "answeredBy": self.pinfo(answered_by),
            "wrongAnswer": self.option_labels[chosen] if chosen is not None and not winner else None,
        }
        self.answerer = None
        self.screen = "reveal"
        self._set_playing(True)
        self.set_timer(REVEAL_SECONDS, self._next_song)

    # --- Runda 2: licytacja ------------------------------------------------

    def _start_bidding(self) -> None:
        self.screen = "bid"
        self.set_timer(BID_SECONDS, self._resolve_bids)

    def _resolve_bids(self) -> None:
        self.cancel_timer()
        if not self.bids:
            self._next_song()
            return
        winner = min(self.bids, key=lambda p: self.bids[p])
        self.bid_winner = winner
        self.bid_value = self.bids[winner][0]
        self.fx("lock")
        self._cue(self._start_bid_clip)

    def _start_bid_clip(self) -> None:
        self.screen = "bid_play"
        self._set_playing(True)
        self.set_timer(self.bid_value, self._bid_clip_over, name="clip", total=self.bid_value)

    def _bid_clip_over(self) -> None:
        self._set_playing(False)
        self.answerer = self.bid_winner
        self.screen = "answer"
        self.set_timer(ANSWER_SECONDS, lambda: self._answered(None))

    # --- Koniec ------------------------------------------------------------

    def _finish(self) -> None:
        ranking = []
        for pid in sorted(self.roster, key=lambda p: -self.points[p]):
            info = self.s.pinfo(pid)
            ranking.append({"id": pid, "name": info["name"], "color": info["color"],
                            "score": self.points[pid], "label": f"{self.points[pid]} pkt"})
        self.finish(ranking)

    def stop(self) -> None:
        self._stop_audio()
        super().stop()

    # --- Akcje -------------------------------------------------------------

    def on_action(self, pid: str, action: str, m: dict) -> None:
        value = m.get("v")
        if pid not in self.roster:
            return
        if action == "buzz" and self.screen == "play" and pid not in self.locked:
            self._buzzed(pid)
        elif action == "answer" and self.screen == "answer" and pid == self.answerer:
            if isinstance(value, int) and 0 <= value < len(self.option_labels):
                self._answered(value)
        elif action == "bid" and self.screen == "bid" and pid not in self.bids and value in BIDS:
            self.bids[pid] = (value, self.clock.now())
            if all(p in self.bids or not self.s.is_connected(p) for p in self.roster):
                self._resolve_bids()

    # --- Widoki ------------------------------------------------------------

    def _scoreboard(self) -> list[dict]:
        items = []
        guessing = self.screen in ("play", "answer") and self.round == 1
        for pid in sorted(self.roster, key=lambda p: -self.points[p]):
            items.append({**self.s.pinfo(pid), "points": self.points[pid],
                          "locked": guessing and pid in self.locked, "bid": pid in self.bids})
        return items

    def view_tv(self) -> dict:
        view = {
            "round": self.round,
            "number": self.index + 1,
            "total": len(self.tracks),
            "scores": self._scoreboard(),
            "audio": self.audio,
            "answerer": self.pinfo(self.answerer),
            "bidWinner": self.pinfo(self.bid_winner),
            "bidValue": self.bid_value,
            "result": self.result,
            "progress": self.progress,
            "clip": self.timer_view("clip"),
            "timer": self.timer_view(),
        }
        if self.screen == "reveal" and self.track:
            view["track"] = {
                "title": self.track.title,
                "artist": self.track.artist,
                "art": f"/media/art/{self.track.id}" if self.track.art else None,
            }
        return view

    def view_player(self, pid: str) -> dict:
        sub = f"{self.points[pid]} pkt"
        if self.screen == "loading":
            return self.pv(msg("Przygotowujemy utwory…", big=True), sub=sub)
        if self.screen == "round":
            return self.pv(msg("Licytacja!" if self.round == 2 else "Runda zgłoszeń", big=True), sub=sub)
        if self.screen == "cue":
            return self.pv(msg("Uwaga, zaraz zagra…", big=True), sub=sub)
        if self.screen == "play":
            if pid in self.locked:
                return self.pv(msg("Ten utwór masz już z głowy. Czekaj na kolejny.", "bad", big=True), sub=sub)
            return self.pv(buzz("ZNAM TO!"), sub=sub)
        if self.screen == "answer":
            if pid == self.answerer:
                return self.pv(options("answer", self.option_labels, letters=False), sub=sub,
                               prompt="Co to za utwór?", timer=self.timer_view())
            return self.pv(msg(f"Odpowiada {self.name(self.answerer)}.", big=True), sub=sub)
        if self.screen == "bid":
            if pid in self.bids:
                return self.pv(msg(f"Twoja oferta: {self.bids[pid][0]} s. Czekamy na resztę.", big=True), sub=sub)
            return self.pv(buttons(*[
                btn("bid", f"{b} s", v=b, hint=f"{BID_POINTS[b]} pkt", style="tile") for b in BIDS
            ]), sub=sub, prompt="Ile sekund wystarczy Ci, żeby rozpoznać utwór?", timer=self.timer_view())
        if self.screen == "bid_play":
            if pid == self.bid_winner:
                return self.pv(msg("Słuchaj uważnie!", "good", big=True), sub=sub)
            return self.pv(msg(f"Gra {self.name(self.bid_winner)}.", big=True), sub=sub)
        if self.screen == "reveal" and self.result:
            if self.result.get("winner") and self.result["winner"]["id"] == pid:
                return self.pv(msg(f'+{self.result["points"]} pkt!', "good", big=True), sub=sub)
            if self.result.get("answeredBy") and self.result["answeredBy"]["id"] == pid:
                return self.pv(msg("Niestety, to nie to.", "bad", big=True), sub=sub)
        return self.pv(msg("Patrz na telewizor.", big=True), sub=sub)

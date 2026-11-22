"""Turniej: kilka gier po kolei z jedną tabelą punktów.

Turniej jest grą-opakowaniem. Między grami ma własne ekrany (typowanie podium, wyniki gry,
tabela), a w trakcie gry przekazuje akcje i widoki bieżącej grze, więc same gry nie wiedzą,
że są częścią turnieju. Gra, która się wysypie lub nie może ruszyć (np. muzyka bez telewizora),
zostaje pominięta zamiast kończyć cały turniej.

Punkty: za miejsce w grze (PLACE_POINTS) i za typy podium: trafione miejsce 3 pkt, pomyłka
o jedno miejsce 1 pkt.
"""
from __future__ import annotations

from typing import Optional

from .base import Game, btn, buttons, msg

PLAYLISTS = {
    "all": ["one_of_ten", "familiada", "floor", "melody", "millionaires"],
    "nomusic": ["one_of_ten", "familiada", "floor", "millionaires"],
    "quick": ["floor", "familiada", "millionaires"],
}
PLACE_POINTS = [10, 7, 5, 3, 2]
MIN_PLACE_POINTS = 1
EXACT_TIP = 3
CLOSE_TIP = 1
TIP_PLACES = 3
PREDICT_SECONDS = 30
INTRO_SECONDS = 5
SCORES_SECONDS = 12
TABLE_SECONDS = 10
SKIPPED_SECONDS = 6


def place_points(place: int) -> int:
    return PLACE_POINTS[place - 1] if place <= len(PLACE_POINTS) else MIN_PLACE_POINTS


def player_places(ranking: list[dict], roster: list[str]) -> dict[str, int]:
    """Miejsca graczy z rankingu gry. Boty i nieobecni się nie liczą, drużyna daje miejsce każdemu członkowi.

    Miejsce gracza = 1 + liczba pozycji z graczami, które były w rankingu wyżej. Remis zostaje remisem.
    """
    entries = []
    for item in ranking:
        members = [m for m in (item.get("members") or [item.get("id")]) if m in roster]
        if members:
            entries.append((item.get("place", 1), members))
    places = {}
    for place, members in entries:
        better = sum(1 for other, _ in entries if other < place)
        for pid in members:
            places[pid] = better + 1
    return places


def tip_points(tips: list[str], places: dict[str, int]) -> int:
    total = 0
    for slot, pid in enumerate(tips, 1):
        actual = places.get(pid)
        if actual == slot:
            total += EXACT_TIP
        elif actual is not None and abs(actual - slot) == 1:
            total += CLOSE_TIP
    return total


class Tournament(Game):
    id = "tournament"
    title = "Turniej"
    tagline = "Wszystkie gry po kolei, punkty za miejsca i za typy."
    min_players = 1
    allow_spectators = True
    rules = [
        "Gry idą jedna po drugiej, a punkty z każdej trafiają do wspólnej tabeli.",
        "Za miejsce w grze: 10, 7, 5, 3, 2, a dalej po 1 pkt. Remis to te same punkty.",
        "Przed każdą grą typujesz podium. Trafione miejsce daje 3 pkt, pomyłka o jedno miejsce 1 pkt.",
        "W Familiadzie nie typujemy, bo drużyny są losowane. Ustawienia gier bierzemy z ich opcji w menu.",
    ]
    option_defs = [{
        "key": "games",
        "label": "Gry",
        "default": "all",
        "choices": [{"v": "all", "l": "Wszystkie (5)"}, {"v": "nomusic", "l": "Bez muzyki (4)"},
                    {"v": "quick", "l": "Szybki (3)"}],
    }, {
        "key": "tips",
        "label": "Typowanie podium",
        "default": "on",
        "choices": [{"v": "on", "l": "Tak"}, {"v": "off", "l": "Nie"}],
    }]

    def start(self) -> None:
        self.order: list[str] = list(PLAYLISTS[self.opts["games"]])
        self.index = -1
        self.points = {p: 0 for p in self.roster}
        self.place_total = {p: 0 for p in self.roster}
        self.tip_total = {p: 0 for p in self.roster}
        self.child: Optional[Game] = None
        self.child_id = ""
        self.tips: dict[str, list[str]] = {}
        self.tip_slots = 0
        self.last: Optional[dict] = None
        self.skip_note = ""
        self.history: list[dict] = []
        self._next_game()

    # --- Kolejne gry -------------------------------------------------------

    def _games(self):
        from . import GAMES
        return GAMES

    def _players(self) -> list[str]:
        return [p for p in self.roster if self.s.is_connected(p)]

    def _next_game(self) -> None:
        self.cancel_timer()
        self.child = None
        self.index += 1
        players = self._players()
        if self.index >= len(self.order) or not players:
            self._finish()
            return
        self.child_id = self.order[self.index]
        cls = self._games()[self.child_id]
        if cls.needs_tv and not self.s.tvs:
            self._skip(f"{cls.title}: pominięta, bo gra muzykę na telewizorze, a ekran TV jest wyłączony.")
            return
        self.tips = {}
        self.tip_slots = min(TIP_PLACES, len(players))
        if self.opts["tips"] == "on" and not cls.team_game and len(players) >= 2:
            self.screen = "predict"
            self.set_timer(PREDICT_SECONDS, self._launch)
        else:
            self.tip_slots = 0
            self.screen = "next"
            self.set_timer(INTRO_SECONDS, self._launch)

    def _launch(self) -> None:
        self.cancel_timer()
        players = self._players()
        if not players:
            self._finish()
            return
        cls = self._games()[self.child_id]
        child = cls(self.s, dict(self.s.options[cls.id]), players)
        child.on_finished = self._child_finished
        self.child = child
        self.screen = "playing"
        child.start()

    def _child_finished(self, child: Game) -> None:
        if child is not self.child:
            return
        self.child = None
        places = player_places(child.ranking or [], self.roster)
        rows = []
        for pid in self.roster:
            place = places.get(pid)
            earned = place_points(place) if place else 0
            tipped = tip_points(self.tips.get(pid, []), places) if self.tip_slots else 0
            self.points[pid] += earned + tipped
            self.place_total[pid] += earned
            self.tip_total[pid] += tipped
            rows.append({"player": self.s.pinfo(pid), "place": place, "placePoints": earned, "tipPoints": tipped,
                         "tips": [self.name(t) for t in self.tips.get(pid, [])]})
        rows.sort(key=lambda r: (r["place"] is None, r["place"] or 0, -r["tipPoints"]))
        self.last = {"game": child.title, "rows": rows}
        self.history.append(self.last)
        self.screen = "scores"
        self.set_timer(SCORES_SECONDS, self._show_table)

    def _show_table(self) -> None:
        self.screen = "table"
        last_game = self.index >= len(self.order) - 1
        self.set_timer(TABLE_SECONDS, self._finish if last_game else self._next_game)

    def _skip(self, note: str) -> None:
        self.child = None
        self.skip_note = note
        self.screen = "skipped"
        self.set_timer(SKIPPED_SECONDS, self._next_game)

    def absorb_abort(self, message: str) -> bool:
        """Błąd albo przerwanie bieżącej gry pomija tylko ją, a turniej toczy się dalej."""
        if self.child is None or self.stopped:
            return False
        child, self.child = self.child, None
        try:
            child.stop()
        except Exception:
            pass
        self._skip(f"{child.title}: {message} Gramy dalej.")
        return True

    def _standings(self) -> list[str]:
        return sorted(self.roster, key=lambda p: (-self.points[p], -self.place_total[p]))

    def _finish(self) -> None:
        ranking = []
        for pid in self._standings():
            info = self.s.pinfo(pid)
            ranking.append({"id": pid, "name": info["name"], "color": info["color"],
                            "score": self.points[pid], "label": f"{self.points[pid]} pkt"})
        note = ""
        if any(self.tip_total.values()):
            best = max(self.roster, key=lambda p: self.tip_total[p])
            note = f"Najlepszy typer: {self.name(best)} ({self.tip_total[best]} pkt za typy)."
        self.finish(ranking, note=note)

    def stop(self) -> None:
        if self.child:
            self.child.stop()
        super().stop()

    # --- Akcje -------------------------------------------------------------

    def on_action(self, pid: str, action: str, m: dict) -> None:
        if self.screen == "playing" and self.child:
            self.child.on_action(pid, action, m)
            return
        value = m.get("v")
        if self.screen == "predict" and pid in self.roster:
            tips = self.tips.setdefault(pid, [])
            if action == "tip" and value in self._players() and value not in tips and len(tips) < self.tip_slots:
                tips.append(value)
                if all(len(self.tips.get(p, [])) == self.tip_slots for p in self._players()):
                    self._launch()
            elif action == "tip_reset":
                self.tips[pid] = []
        elif action == "next" and pid == self.s.host_id and self.screen in ("scores", "table", "next", "skipped"):
            {"scores": self._show_table, "next": self._launch, "skipped": self._next_game,
             "table": self._finish if self.index >= len(self.order) - 1 else self._next_game}[self.screen]()

    def on_tv_event(self, event, m: dict) -> None:
        if self.screen == "playing" and self.child:
            self.child.on_tv_event(event, m)

    def on_player_away(self, pid: str) -> None:
        if self.screen == "playing" and self.child:
            self.child.on_player_away(pid)
        elif self.screen == "predict" and self._players() and all(
                len(self.tips.get(p, [])) == self.tip_slots for p in self._players()):
            self._launch()

    def on_player_back(self, pid: str) -> None:
        if self.screen == "playing" and self.child:
            self.child.on_player_back(pid)

    # --- Widoki ------------------------------------------------------------

    def _progress(self) -> dict:
        return {"number": self.index + 1, "total": len(self.order)}

    def _table(self) -> list[dict]:
        last_rows = {r["player"]["id"]: r for r in (self.last or {}).get("rows", [])}
        rows, place, previous = [], 0, None
        for index, pid in enumerate(self._standings(), 1):
            if self.points[pid] != previous:
                place, previous = index, self.points[pid]
            row = last_rows.get(pid, {})
            rows.append({"player": self.s.pinfo(pid), "place": place, "points": self.points[pid],
                         "gained": row.get("placePoints", 0) + row.get("tipPoints", 0)})
        return rows

    def tv_view(self) -> dict:
        if self.screen == "playing" and self.child:
            view = self.child.tv_view()
            view["tournament"] = self._progress()
            return view
        if self.screen == "results":
            return super().tv_view()
        upcoming = self._games().get(self.child_id) if self.child_id else None
        return {
            "id": self.id,
            "title": self.title,
            "screen": self.screen,
            "progress": self._progress(),
            "game": upcoming.title if upcoming else "",
            "games": [self._games()[g].title for g in self.order],
            "tipSlots": self.tip_slots,
            "tipped": [{**self.s.pinfo(p), "done": len(self.tips.get(p, [])) == self.tip_slots}
                       for p in self._players()],
            "last": self.last,
            "table": self._table() if self.screen in ("table", "scores") else None,
            "note": self.skip_note if self.screen == "skipped" else "",
            "timer": self.timer_view(),
        }

    def player_view(self, pid: str) -> dict:
        if self.screen == "playing" and self.child:
            return self.child.player_view(pid)
        return super().player_view(pid)

    def view_tv(self) -> dict:  # tv_view jest nadpisane w całości
        return {}

    def view_player(self, pid: str) -> dict:
        sub = f"Gra {self.index + 1} z {len(self.order)}  ·  {self.points.get(pid, 0)} pkt"
        title = self._games()[self.child_id].title if self.child_id else ""
        host_next = [buttons(btn("next", "Dalej", style="primary"))] if pid == self.s.host_id else []
        if self.screen == "predict":
            return self._predict_view(pid, title, sub)
        if self.screen == "next":
            return self.pv(msg(f"Następna gra: {title}", big=True), *host_next, sub=sub, timer=self.timer_view())
        if self.screen == "skipped":
            return self.pv(msg(self.skip_note, "bad", big=True), *host_next, sub=sub)
        if self.screen == "scores" and self.last:
            row = next((r for r in self.last["rows"] if r["player"]["id"] == pid), None)
            blocks = []
            if row:
                place = f'{row["place"]}. miejsce' if row["place"] else "Bez miejsca"
                blocks.append(msg(f'{place}: +{row["placePoints"]} pkt', "good" if row["place"] == 1 else "info",
                                  big=True))
                if self.tip_slots:
                    blocks.append(msg(f'Za typy: +{row["tipPoints"]} pkt', "good" if row["tipPoints"] else "info"))
            return self.pv(*blocks, *host_next, sub=sub)
        if self.screen == "table":
            rank = next((r for r in self._table() if r["player"]["id"] == pid), None)
            text = f'{rank["place"]}. miejsce w turnieju, {rank["points"]} pkt' if rank else "Tabela na telewizorze"
            return self.pv(msg(text, big=True), *host_next, sub=sub)
        return self.pv(msg("Patrz na telewizor.", big=True), sub=sub)

    def _predict_view(self, pid: str, title: str, sub: str) -> dict:
        timer = self.timer_view()
        if pid not in self.roster:
            return self.pv(msg(f"Gracze typują podium przed grą: {title}.", big=True), timer=timer)
        tips = self.tips.get(pid, [])
        chosen = "  ".join(f"{i}. {self.name(t)}" for i, t in enumerate(tips, 1))
        if len(tips) >= self.tip_slots:
            return self.pv(msg(f"Twoje typy: {chosen}", "good", big=True), msg("Czekamy na pozostałych."),
                           buttons(btn("tip_reset", "Zmień typy", style="ghost")), sub=sub, timer=timer)
        slot = len(tips) + 1
        blocks = [msg(f"Kto zajmie {slot}. miejsce?")]
        if chosen:
            blocks.append(msg(f"Na razie: {chosen}"))
        blocks.append(buttons(*[
            btn("tip", self.name(p), v=p, color=self.s.pinfo(p)["color"])
            for p in self._players() if p not in tips
        ]))
        if tips:
            blocks.append(buttons(btn("tip_reset", "Od nowa", style="ghost")))
        return self.pv(*blocks, sub=sub, prompt=f"Typuj podium: {title}", timer=timer)

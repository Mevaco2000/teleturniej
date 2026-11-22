"""Biblioteka utworów do „Jaka to melodia”.

Źródła: 30-sekundowe fragmenty z iTunes (oryginały z wokalem), 30-sekundowe fragmenty
wersji instrumentalnych z Deezer (karaoke, covery fortepianowe, albumy instrumentalne),
własne pliki z data/music oraz melodie syntezowane w przeglądarce TV (bez internetu).
Pobrane fragmenty leżą w data/cache. TV dostaje dźwięk z serwera pod nieprzezroczystym
identyfikatorem, więc sam adres nie zdradza tytułu.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import random
import re
import time
import unicodedata
from collections import deque
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path
from typing import Callable, Optional

import aiohttp

log = logging.getLogger("teleturniej.music")

ITUNES_SEARCH = "https://itunes.apple.com/search"
AUDIO_SUFFIXES = {".mp3", ".m4a", ".aac", ".ogg", ".wav"}
MAX_DOWNLOAD = 6 * 1024 * 1024
# Imitacje i przeróbki to nie jest utwór, o który pytamy.
REJECTED_VERSIONS = re.compile(
    r"\b(remix|karaoke|tribute|cover|instrumental|demo|medley|re-?recorded|in the style of|made famous)\b"
)
# Wersje poboczne są rozpoznawalne, więc zostają, gdy sklep nie ma studyjnej.
SIDE_VERSIONS = re.compile(r"\b(live|koncert|concert|mix|acoustic|akustycznie|unplugged|version|wersja|edit)\b")
SIDE_VERSION_PENALTY = 0.3
SIDE_ALBUM_PENALTY = 0.2
MISS_RETRY_SECONDS = 7 * 24 * 3600
OWN_FILE_START = 30.0
PREPARE_BUDGET_SECONDS = 30.0

DEEZER_API = "https://api.deezer.com"
DEEZER_QUOTA_ERROR = 4
DEEZER_QUOTA_PAUSE = 5.5
# API pozwala na 50 zapytań w 5 sekund; zostawiamy zapas.
DEEZER_RATE = 40
DEEZER_WINDOW = 5.0
# Wersja bez śpiewu: tytuł albo album mówi, że to podkład, karaoke lub cover instrumentalny.
INSTRUMENTAL_MARK = re.compile(
    r"\b(instrumental\w*|karaoke|backing tracks?|minus one|playback|piano|podklad\w*|wersj\w* instrumentaln\w*)\b")
# Chórki albo wokal prowadzący zdradzają tytuł.
SUNG_MARK = re.compile(
    r"\b(with (lead |guide |backing |background )?vocals?|(lead|guide|backing|background|demo) vocals?|"
    r"vocals? (version|guide)|z wokalem|z chorkami)\b")
NOT_THE_SONG = re.compile(r"\b(medley|mashup|megamix|nightcore|sped up|slowed|reverb|ringtone)\b")
# Melodia grana przez instrument (fortepian, „guide melody”) – najbliżej orkiestry z teleturnieju.
MELODY_MARK = re.compile(r"\b(melody|piano)\b")
# Przeróbki w innym stylu brzmią jak inny utwór.
RESTYLED_MARK = re.compile(
    r"\b(lullaby|lullabies|kolysank\w*|bossa|jazz\w*|lounge|chill\w*|relax\w*|reggae|8 bit|chiptune|music box|"
    r"orchestral|symphonic|string quartet|strings|cello|violin|guitar|acoustic|ukulele|harp|metal|punk|remix|"
    r"dance|edm|workout|lofi|lo fi|live|higher key|lower key|sleep\w*|bgm|meditation|spa|yoga|study|baby)\b")
TITLE_FILLER = re.compile(
    r"\b(instrumental\w*|karaoke|backing|track|tracks|minus one|playback|piano|version|versions|cover|tribute|"
    r"originally|performed|made|famous|popular|style|the|of|by|in|a|an)\b")
INSTRUMENTAL_MIN_SCORE = 0.85
MELODY_BONUS = 0.2
OFFICIAL_BONUS = 0.1
RESTYLED_PENALTY = 0.4


def normalize(text: str) -> str:
    text = text.replace("ł", "l").replace("Ł", "L")
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


def _key(*parts: str) -> str:
    return hashlib.sha1("|".join(parts).encode("utf-8")).hexdigest()[:16]


@dataclass
class Track:
    id: str
    title: str
    artist: str
    kind: str  # "hit" | "file" | "synth"
    path: Optional[Path] = None
    art: Optional[Path] = None
    melody: Optional[dict] = None
    start: float = 0.0
    lang: str = ""

    @property
    def label(self) -> str:
        return f"{self.artist} — {self.title}" if self.artist else self.title


def pick_itunes_result(results: list[dict], artist: str, title: str) -> Optional[dict]:
    """Wybiera właściwy utwór, najlepiej w wersji studyjnej, albo None, gdy nic nie pasuje."""
    want_artist, want_title = normalize(artist), normalize(title)
    best, best_score = None, 0.0
    for item in results:
        if not item.get("previewUrl"):
            continue
        got_artist = normalize(item.get("artistName", ""))
        got_title = normalize(item.get("trackName", ""))
        got_album = normalize(item.get("collectionName", ""))
        if want_artist not in got_artist and got_artist not in want_artist:
            continue
        ratio = SequenceMatcher(None, want_title, got_title).ratio()
        if want_title in got_title:
            ratio = max(ratio, 0.85)
        if ratio < 0.7:
            continue
        # Słowo-klucz w samym tytule utworu liczy się tylko, gdy nie należy ono do tytułu szukanego.
        if REJECTED_VERSIONS.search(got_title) and not REJECTED_VERSIONS.search(want_title):
            continue
        score = ratio
        if SIDE_VERSIONS.search(got_title) and not SIDE_VERSIONS.search(want_title):
            score -= SIDE_VERSION_PENALTY
        if SIDE_VERSIONS.search(got_album):
            score -= SIDE_ALBUM_PENALTY
        if score > best_score:
            best, best_score = item, score
    return best


def _title_core(title: str, artist_names: list[str]) -> str:
    """Sam tytuł: bez dopisków w nawiasach, słów typu „karaoke” i nazwy wykonawcy."""
    text = normalize(re.sub(r"\(.*?\)|\[.*?\]", " ", title))
    for name in artist_names:
        text = re.sub(rf"\b{re.escape(name)}\b", " ", text)
    return " ".join(TITLE_FILLER.sub(" ", text).split())


def _artist_names(artist: str) -> list[str]:
    """„Bob Marley & The Wailers” → ["bob marley", "wailers"]: każda nazwa wystarczy do rozpoznania."""
    names = []
    for part in re.split(r"\s*(?:&|,|\bfeat\b\.?|\bft\b\.?|\bx\b|\band\b)\s*", artist, flags=re.I):
        name = re.sub(r"^the ", "", normalize(part))
        if len(name) >= 2:
            names.append(name)
    return names


def _mentions(text: str, names: list[str]) -> bool:
    padded = f" {text} "
    return any(f" {name} " in padded for name in names)


def pick_instrumental(results: list[dict], artist: str, title: str) -> Optional[dict]:
    """Najlepsza wersja bez śpiewu z wyników wyszukiwania Deezer albo None.

    Wymaga wzmianki o oryginalnym wykonawcy („Originally Performed by…”, „in the Style of…”,
    album „Karaoke – Queen”), bo sam tytuł bywa wspólny dla wielu piosenek.
    """
    names = _artist_names(artist)
    want = _title_core(title, names)
    if not want or not names:
        return None
    best, best_score = None, 0.0
    for item in results:
        if not item.get("preview"):
            continue
        got_title = item.get("title", "")
        got_artist = normalize((item.get("artist") or {}).get("name", ""))
        got_album = normalize((item.get("album") or {}).get("title", ""))
        ratio = SequenceMatcher(None, want, _title_core(got_title, names)).ratio()
        if ratio < INSTRUMENTAL_MIN_SCORE:
            continue
        # Słowa z samego tytułu („Piano Man”) nie świadczą o wersji instrumentalnej.
        extra = f"{normalize(got_title)} {got_album}".replace(normalize(title), " ")
        blob = f"{extra} {got_artist}"
        if not INSTRUMENTAL_MARK.search(blob) or SUNG_MARK.search(blob) or NOT_THE_SONG.search(blob):
            continue
        official = _mentions(got_artist, names)
        if not official and not _mentions(f"{normalize(got_title)} {got_album} {got_artist}", names):
            continue
        score = ratio
        if MELODY_MARK.search(blob):
            score += MELODY_BONUS
        if official:
            score += OFFICIAL_BONUS
        if RESTYLED_MARK.search(blob):
            score -= RESTYLED_PENALTY
        score += min(item.get("rank") or 0, 1_000_000) / 100_000_000
        if score > best_score:
            best, best_score = item, score
    return best


class MusicLibrary:
    def __init__(self, data_dir: Path, cache_dir: Path, rng: random.Random):
        self.rng = rng
        self.music_dir = data_dir / "music"
        self.cache_dir = cache_dir
        self.meta_path = cache_dir / "itunes.json"
        with open(data_dir / "songs.json", encoding="utf-8") as fh:
            self.catalog: list[dict] = json.load(fh)
        with open(data_dir / "melodies.json", encoding="utf-8") as fh:
            self.melodies: list[dict] = json.load(fh)
        self.meta: dict[str, dict] = {}
        if self.meta_path.exists():
            try:
                self.meta = json.loads(self.meta_path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                log.warning("Nie można odczytać %s, buduję od nowa", self.meta_path)
        self.tracks: dict[str, Track] = {}
        self.played: set[str] = set()
        self._throttled_until = 0.0
        self._deezer_paused_until = 0.0
        self._deezer_calls: deque[float] = deque()
        self._deezer_lock: Optional[asyncio.Lock] = None
        self._deezer_loop: Optional[asyncio.AbstractEventLoop] = None

    # --- Serwowanie plików -------------------------------------------------

    def audio_path(self, track_id: str) -> Optional[Path]:
        track = self.tracks.get(track_id)
        return track.path if track and track.path and track.path.exists() else None

    def art_path(self, track_id: str) -> Optional[Path]:
        track = self.tracks.get(track_id)
        return track.art if track and track.art and track.art.exists() else None

    # --- Źródła ------------------------------------------------------------

    def own_tracks(self) -> list[Track]:
        tracks = []
        if not self.music_dir.exists():
            return tracks
        for path in sorted(self.music_dir.rglob("*")):
            if path.suffix.lower() not in AUDIO_SUFFIXES or not path.is_file():
                continue
            stem = re.sub(r"^\d+[\s._-]+", "", path.stem.replace("_", " ")).strip()
            artist, _, title = stem.partition(" - ")
            if not title:
                artist, title = "", stem
            track_id = _key("file", str(path.relative_to(self.music_dir)))
            tracks.append(Track(track_id, title.strip(), artist.strip(), "file", path=path, start=OWN_FILE_START))
        return tracks

    def synth_tracks(self) -> list[Track]:
        return [
            Track(_key("synth", m["title"]), m["title"], m.get("artist", ""), "synth", melody=m)
            for m in self.melodies
        ]

    def filter_catalog(self, category: str) -> list[dict]:
        if category == "pl":
            return [s for s in self.catalog if s["lang"] == "pl"]
        if category == "int":
            return [s for s in self.catalog if s["lang"] != "pl"]
        if category in ("old", "80", "90", "00", "10", "20"):
            return [s for s in self.catalog if s["decade"] == category]
        return list(self.catalog)

    # --- iTunes ------------------------------------------------------------

    def _save_meta(self) -> None:
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        tmp = self.meta_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.meta, ensure_ascii=False, indent=0), encoding="utf-8")
        tmp.replace(self.meta_path)

    @staticmethod
    async def _fetch(client: aiohttp.ClientSession, url: str) -> Optional[bytes]:
        """Cała zawartość pliku albo None. Sieć dostarcza dane porcjami, więc czytamy do końca."""
        async with client.get(url) as resp:
            if resp.status != 200:
                return None
            chunks, size = [], 0
            async for chunk in resp.content.iter_chunked(64 * 1024):
                size += len(chunk)
                if size > MAX_DOWNLOAD:
                    return None
                chunks.append(chunk)
        return b"".join(chunks)

    async def _download(self, client: aiohttp.ClientSession, url: str, dest: Path) -> bool:
        if not url.startswith("https://"):
            return False
        dest.parent.mkdir(parents=True, exist_ok=True)
        data = await self._fetch(client, url)
        if data is None or len(data) < 1024:
            return False
        tmp = dest.with_suffix(dest.suffix + ".tmp")
        tmp.write_bytes(data)
        tmp.replace(dest)
        return True

    async def _lookup(self, client: aiohttp.ClientSession, song: dict) -> Optional[dict]:
        """Metadane utworu z pamięci podręcznej lub z API. Zwraca None, gdy brak wyniku."""
        key = _key("hit", song["artist"], song["title"])
        meta = self.meta.get(key)
        if meta and meta.get("preview"):
            return meta
        if meta and time.time() - meta.get("missed_at", 0) < MISS_RETRY_SECONDS:
            return None
        if time.time() < self._throttled_until:
            return None
        params = {
            "term": f'{song["artist"]} {song["title"]}',
            "entity": "song",
            "country": "PL",
            "limit": "25",
        }
        async with client.get(ITUNES_SEARCH, params=params) as resp:
            if resp.status in (403, 429):
                self._throttled_until = time.time() + 60
                log.warning("iTunes ogranicza liczbę zapytań, przerywam na minutę")
                return None
            if resp.status != 200:
                return None
            payload = await resp.json(content_type=None)
        best = pick_itunes_result(payload.get("results", []), song["artist"], song["title"])
        if best is None:
            self.meta[key] = {"missed_at": time.time()}
            self._save_meta()
            return None
        meta = {
            "preview": best["previewUrl"],
            "art": best.get("artworkUrl100", "").replace("100x100bb", "600x600bb"),
        }
        self.meta[key] = meta
        self._save_meta()
        return meta

    async def _resolve_hit(self, client: aiohttp.ClientSession, song: dict) -> Optional[Track]:
        key = _key("hit", song["artist"], song["title"])
        audio = self.cache_dir / "previews" / f"{key}.m4a"
        art = self.cache_dir / "art" / f"{key}.jpg"
        try:
            if not audio.exists():
                meta = await self._lookup(client, song)
                if not meta or not await self._download(client, meta["preview"], audio):
                    return None
            if not art.exists():
                meta = self.meta.get(key) or {}
                if meta.get("art"):
                    await self._download(client, meta["art"], art)
        except (aiohttp.ClientError, asyncio.TimeoutError, OSError, ValueError) as exc:
            log.info("Utwór %s - %s niedostępny: %s", song["artist"], song["title"], exc)
            if not audio.exists():
                return None
        return Track(key, song["title"], song["artist"], "hit", path=audio,
                     art=art if art.exists() else None, lang=song.get("lang", ""))

    # --- Deezer: wersje instrumentalne -------------------------------------

    async def _deezer_slot(self) -> None:
        """Rozkłada zapytania w czasie, bo utwory przygotowujemy równolegle."""
        loop = asyncio.get_running_loop()
        if self._deezer_loop is not loop:
            self._deezer_loop, self._deezer_lock = loop, asyncio.Lock()
        async with self._deezer_lock:
            while True:
                now = time.monotonic()
                while self._deezer_calls and now - self._deezer_calls[0] > DEEZER_WINDOW:
                    self._deezer_calls.popleft()
                wait = max(self._deezer_paused_until - now,
                           DEEZER_WINDOW - (now - self._deezer_calls[0]) if len(self._deezer_calls) >= DEEZER_RATE else 0)
                if wait <= 0:
                    break
                await asyncio.sleep(wait)
            self._deezer_calls.append(time.monotonic())

    async def _deezer(self, client: aiohttp.ClientSession, path: str,
                      params: Optional[dict] = None) -> Optional[dict]:
        """Odpowiedź API Deezer albo None. Przy przekroczeniu limitu zapytań czeka i ponawia raz."""
        for attempt in range(2):
            await self._deezer_slot()
            async with client.get(DEEZER_API + path, params=params) as resp:
                if resp.status != 200:
                    return None
                data = await resp.json(content_type=None)
            error = data.get("error") if isinstance(data, dict) else None
            if not error:
                return data
            if error.get("code") != DEEZER_QUOTA_ERROR or attempt:
                return None
            log.info("Deezer ogranicza liczbę zapytań, czekam %.0f s", DEEZER_QUOTA_PAUSE)
            self._deezer_paused_until = time.monotonic() + DEEZER_QUOTA_PAUSE
        return None

    async def _find_instrumental(self, client: aiohttp.ClientSession, song: dict) -> Optional[int]:
        """Identyfikator utworu w Deezer: wskazany w katalogu albo wyszukany. 0 = brak takiej wersji."""
        if song.get("instr"):
            return int(song["instr"])
        for extra in ("instrumental", "karaoke"):
            params = {"q": f'{song["artist"]} {song["title"]} {extra}', "limit": "50"}
            data = await self._deezer(client, "/search", params)
            if data is None:
                return None
            best = pick_instrumental(data.get("data", []), song["artist"], song["title"])
            if best:
                return int(best["id"])
        return 0

    async def _original_cover(self, client: aiohttp.ClientSession, song: dict) -> str:
        """Okładka oryginalnego wydania, bo album z karaoke ma zwykle zastępczą."""
        # Filtr artist:"…" w wyszukiwarce Deezer bywa zepsuty, więc szukamy zwykłym zapytaniem.
        params = {"q": f'{song["artist"]} {song["title"]}', "limit": "10"}
        data = await self._deezer(client, "/search", params) or {}
        names = _artist_names(song["artist"])
        want = _title_core(song["title"], names)
        for item in data.get("data", []):
            if not _mentions(normalize(item["artist"]["name"]), names):
                continue
            if INSTRUMENTAL_MARK.search(normalize(item.get("title", ""))):
                continue
            if SequenceMatcher(None, want, _title_core(item.get("title", ""), names)).ratio() >= 0.85:
                return (item.get("album") or {}).get("cover_big") or ""
        return ""

    async def _lookup_instrumental(self, client: aiohttp.ClientSession, song: dict) -> Optional[dict]:
        key = _key("instr", song["artist"], song["title"])
        meta = self.meta.get(key)
        if meta and meta.get("deezer") and meta["deezer"] == song.get("instr", meta["deezer"]):
            return meta
        if meta and not song.get("instr") and time.time() - meta.get("missed_at", 0) < MISS_RETRY_SECONDS:
            return None
        track_id = await self._find_instrumental(client, song)
        if track_id is None:
            return None
        if not track_id:
            self.meta[key] = {"missed_at": time.time()}
            self._save_meta()
            return None
        meta = {"deezer": track_id, "art": await self._original_cover(client, song)}
        self.meta[key] = meta
        self._save_meta()
        return meta

    async def _resolve_instrumental(self, client: aiohttp.ClientSession, song: dict) -> Optional[Track]:
        key = _key("instr", song["artist"], song["title"])
        audio = self.cache_dir / "instrumental" / f"{key}.mp3"
        # Okładka oryginału jest wspólna z trybem hitów z iTunes.
        art = self.cache_dir / "art" / f'{_key("hit", song["artist"], song["title"])}.jpg'
        try:
            meta = self.meta.get(key) or {}
            if not audio.exists():
                meta = await self._lookup_instrumental(client, song)
                if not meta:
                    return None
                # Adresy podglądów Deezer wygasają, więc świeży bierzemy tuż przed pobraniem.
                track = await self._deezer(client, f'/track/{meta["deezer"]}')
                if not track or not track.get("preview") or not await self._download(client, track["preview"], audio):
                    return None
            if not art.exists() and meta.get("art"):
                await self._download(client, meta["art"], art)
        except (aiohttp.ClientError, asyncio.TimeoutError, OSError, ValueError) as exc:
            log.info("Wersja instrumentalna %s - %s niedostępna: %s", song["artist"], song["title"], exc)
            if not audio.exists():
                return None
        return Track(key, song["title"], song["artist"], "instr", path=audio,
                     art=art if art.exists() else None, lang=song.get("lang", ""))

    async def prefetch_all(self, delay: float = 3.2) -> tuple[int, int, int]:
        """Pobiera cały katalog z góry (oryginały i wersje instrumentalne), aby grać bez internetu."""
        hits = instrumentals = 0
        timeout = aiohttp.ClientTimeout(total=20)
        async with aiohttp.ClientSession(timeout=timeout) as client:
            for index, song in enumerate(self.catalog, 1):
                key = _key("hit", song["artist"], song["title"])
                cached = (self.cache_dir / "previews" / f"{key}.m4a").exists()
                hit = await self._resolve_hit(client, song)
                instrumental = await self._resolve_instrumental(client, song)
                hits += hit is not None
                instrumentals += instrumental is not None
                print(f'[{index}/{len(self.catalog)}] {"OK " if hit else "-- "}{"OK " if instrumental else "-- "}'
                      f'{song["artist"]} — {song["title"]}')
                if not cached:
                    await asyncio.sleep(delay)
        return hits, instrumentals, len(self.catalog)

    # --- Dobór utworów do gry ----------------------------------------------

    def _take_unplayed(self, items: list, key: Callable) -> list:
        fresh = [item for item in items if key(item) not in self.played]
        if not fresh:
            self.played.difference_update(key(item) for item in items)
            fresh = list(items)
        self.rng.shuffle(fresh)
        return fresh

    async def _collect(self, songs: list[dict], count: int, resolve: Callable, deadline: float,
                       progress: Callable[[int], None]) -> list[Track]:
        found: list[Track] = []
        timeout = aiohttp.ClientTimeout(total=10)
        async with aiohttp.ClientSession(timeout=timeout) as client:
            for start in range(0, len(songs), 6):
                if len(found) >= count or time.monotonic() > deadline:
                    break
                batch = songs[start:start + 6]
                results = await asyncio.gather(*(resolve(client, s) for s in batch))
                found.extend(track for track in results if track)
                progress(min(len(found), count))
        return found[:count]

    async def _collect_instrumentals(self, category: str, count: int,
                                     progress: Callable[[int, int], None]) -> list[Track]:
        songs = self._take_unplayed(self.filter_catalog(category),
                                    lambda s: _key("instr", s["artist"], s["title"]))
        deadline = time.monotonic() + PREPARE_BUDGET_SECONDS
        tracks = await self._collect(songs, count, self._resolve_instrumental, deadline,
                                     lambda done: progress(done, count))
        if len(tracks) < count:
            # Brakujące utwory z tej samej kategorii gramy w oryginale, a dopiero potem melodie wbudowane.
            log.info("Za mało wersji instrumentalnych (%d/%d), dopełniam oryginałami", len(tracks), count)
            have = {(t.artist, t.title) for t in tracks}
            rest = [s for s in songs if (s["artist"], s["title"]) not in have]
            got = len(tracks)
            tracks += await self._collect(rest, count - got, self._resolve_hit,
                                          deadline + PREPARE_BUDGET_SECONDS, lambda done: progress(got + done, count))
        return tracks

    async def prepare(self, count: int, category: str, source: str,
                      progress: Callable[[int, int], None] = lambda done, total: None) -> list[Track]:
        tracks: list[Track] = []
        if source in ("auto", "own") and (category == "all" or source == "own"):
            tracks.extend(self._take_unplayed(self.own_tracks(), lambda t: t.id))
        if source == "auto":
            # Własne pliki mieszają się z hitami zamiast je wypierać.
            share = tracks[: max(count // 3, 1)] if tracks else []
            songs = self._take_unplayed(self.filter_catalog(category),
                                        lambda s: _key("hit", s["artist"], s["title"]))
            wanted = count - len(share)
            hits = await self._collect(songs, wanted, self._resolve_hit,
                                       time.monotonic() + PREPARE_BUDGET_SECONDS, lambda done: progress(done, wanted))
            tracks = share + hits
        if source == "instr":
            tracks = await self._collect_instrumentals(category, count, progress)
        if len(tracks) < count and source != "builtin":
            log.info("Za mało utworów (%d/%d), dopełniam melodiami wbudowanymi", len(tracks), count)
        if len(tracks) < count:
            synth = self._take_unplayed(self.synth_tracks(), lambda t: t.id)
            tracks.extend(synth[: count - len(tracks)])
        tracks = tracks[:count]
        self.rng.shuffle(tracks)
        for track in tracks:
            self.tracks[track.id] = track
            self.played.add(track.id)
        progress(len(tracks), count)
        return tracks

    def options_for(self, track: Track, pool: list[Track]) -> tuple[list[str], int]:
        """Cztery podpisy: poprawny i trzy fałszywe, najlepiej w tym samym stylu."""
        decoys: list[str] = []
        if track.kind == "synth":
            decoys = [t.label for t in self.synth_tracks()]
        else:
            same = [s for s in self.catalog if s.get("lang") == track.lang] or self.catalog
            decoys = [f'{s["artist"]} — {s["title"]}' for s in same]
            decoys += [t.label for t in pool if t.kind != "synth"]
        unique = sorted({d for d in decoys if d != track.label and normalize(d) != normalize(track.label)})
        self.rng.shuffle(unique)
        options = [track.label, *unique[:3]]
        self.rng.shuffle(options)
        return options, options.index(track.label)

"""Dopasowanie wyników iTunes i Deezer oraz dobór utworów, bez sieci."""
import asyncio
import random
from pathlib import Path

import aiohttp
import pytest
from aiohttp import web
from aiohttp.test_utils import TestServer

from server.music import MAX_DOWNLOAD, MusicLibrary, Track, normalize, pick_instrumental, pick_itunes_result

DATA = Path(__file__).resolve().parent.parent / "data"


def result(artist, track, album="Album", preview="https://x/a.m4a"):
    return {"artistName": artist, "trackName": track, "collectionName": album, "previewUrl": preview}


def deezer(artist, title, album="Album", preview="https://x/a.mp3", rank=0, track_id=1):
    return {"id": track_id, "title": title, "artist": {"name": artist}, "album": {"title": album},
            "preview": preview, "rank": rank}


def test_normalize_handles_polish_letters():
    assert normalize("Dżem – Łódź Żółć") == "dzem lodz zolc"


def test_prefers_studio_version_over_live():
    results = [
        result("Queen", "Bohemian Rhapsody (Live in Budapest)", "Queen Budapest"),
        result("Queen", "Bohemian Rhapsody", "A Night at the Opera"),
    ]
    assert pick_itunes_result(results, "Queen", "Bohemian Rhapsody")["collectionName"] == "A Night at the Opera"


@pytest.mark.parametrize("track", ["Hey Jude (Karaoke)", "Hey Jude - Tribute", "Hey Jude (Instrumental)"])
def test_rejects_imitations(track):
    assert pick_itunes_result([result("The Beatles", track)], "The Beatles", "Hey Jude") is None


def test_rejects_remix():
    assert pick_itunes_result([result("Mata", "Patointeligencja (Remix)")], "Mata", "Patointeligencja") is None


def test_live_version_is_used_only_when_there_is_no_studio_one():
    live = result("Budka Suflera", "Jolka, Jolka pamiętasz (Live)")
    assert pick_itunes_result([live], "Budka Suflera", "Jolka, Jolka pamiętasz") is live
    studio = result("Budka Suflera", "Jolka, Jolka pamiętasz")
    assert pick_itunes_result([live, studio], "Budka Suflera", "Jolka, Jolka pamiętasz") is studio


def test_single_mix_of_original_is_accepted():
    mix = result("Haddaway", 'What Is Love (7" Mix)')
    assert pick_itunes_result([mix], "Haddaway", "What Is Love") is mix


def test_rejects_wrong_artist():
    assert pick_itunes_result([result("Cover Band", "Hey Jude")], "The Beatles", "Hey Jude") is None


def test_accepts_remaster_and_featured_artist():
    remaster = result("The Beatles", "Hey Jude - Remastered 2015")
    assert pick_itunes_result([remaster], "The Beatles", "Hey Jude") is remaster
    feat = result("Mark Ronson & Bruno Mars", "Uptown Funk (feat. Bruno Mars)")
    assert pick_itunes_result([feat], "Mark Ronson", "Uptown Funk") is feat


def test_ignores_results_without_preview():
    assert pick_itunes_result([result("Queen", "Bohemian Rhapsody", preview="")], "Queen", "Bohemian Rhapsody") is None


def test_title_containing_rejected_word_is_allowed_when_it_is_the_real_title():
    live = result("Foo", "Live Forever")
    assert pick_itunes_result([live], "Foo", "Live Forever") is live


def test_instrumental_needs_mention_of_the_original_artist():
    # Inna piosenka o tym samym tytule nie może wejść do gry.
    other = deezer("Country Band", "Whisky (Instrumental)", "Cowboy Instrumentals")
    assert pick_instrumental([other], "Dżem", "Whisky") is None
    cover = deezer("Sing Society", "Africa (Karaoke Version Originally Performed by Toto)", "The Best of Karaoke")
    assert pick_instrumental([cover], "Toto", "Africa") is cover
    album = deezer("Ameritz Karaoke Band", "Karaoke - Bohemian Rhapsody", "Karaoke - Queen")
    assert pick_instrumental([album], "Queen", "Bohemian Rhapsody") is album


def test_instrumental_rejects_sung_versions_and_originals():
    sung = deezer("Easy Karaoke Players",
                  "The Final Countdown (Instrumental Track With Background Vocals)[Karaoke in the style of Europe]")
    original = deezer("Europe", "The Final Countdown", "The Final Countdown (Expanded Edition)")
    assert pick_instrumental([sung, original], "Europe", "The Final Countdown") is None


def test_instrumental_title_word_does_not_count_as_marker():
    original = deezer("Billy Joel", "Piano Man", "Piano Man")
    assert pick_instrumental([original], "Billy Joel", "Piano Man") is None
    cover = deezer("Piano Dreamers", "Piano Man (Instrumental)", "Piano Dreamers Cover Billy Joel")
    assert pick_instrumental([original, cover], "Billy Joel", "Piano Man") is cover


def test_instrumental_prefers_played_melody_over_restyled_versions():
    lullaby = deezer("Rockabye Baby!", "Hey Jude (Instrumental)", "Lullaby Renditions of The Beatles", rank=900_000)
    karaoke = deezer("Zoom Karaoke", "Hey Jude (Karaoke Version) [Originally Performed By The Beatles]")
    piano = deezer("Matchstick Piano Man", "Hey Jude (Instrumental Piano)", "The Beatles (Instrumental Piano Covers)")
    assert pick_instrumental([lullaby, karaoke, piano], "The Beatles", "Hey Jude") is piano
    assert pick_instrumental([lullaby, karaoke], "The Beatles", "Hey Jude") is karaoke


def test_instrumental_accepts_official_instrumental_and_reordered_title():
    official = deezer("a-ha", "Take on Me (Instrumental; 2015 Remaster)", "Hunting High and Low")
    assert pick_instrumental([official], "a-ha", "Take On Me") is official
    stones = deezer("Hit The Button Karaoke", "Satisfaction (I Can't Get No) [Karaoke Instrumental]",
                    "Karaoke: The Rolling Stones")
    assert pick_instrumental([stones], "The Rolling Stones", "(I Can't Get No) Satisfaction") is stones


def test_instrumental_skips_medleys_and_missing_previews():
    medley = deezer("Karaoke Band", "Queen Medley (Instrumental)", "Karaoke - Queen")
    silent = deezer("Karaoke Band", "Bohemian Rhapsody (Instrumental)", "Karaoke - Queen", preview="")
    assert pick_instrumental([medley, silent], "Queen", "Bohemian Rhapsody") is None


@pytest.fixture
def library(tmp_path):
    music = tmp_path / "music"
    music.mkdir()
    lib = MusicLibrary(DATA, tmp_path / "cache", random.Random(1))
    lib.music_dir = music
    return lib


def fetch_from_chunked_server(size: int) -> bytes | None:
    """Serwer wysyła dane porcjami z przerwami, jak prawdziwa sieć."""

    async def handler(request):
        response = web.StreamResponse()
        await response.prepare(request)
        for _ in range(size // 50_000):
            await response.write(b"x" * 50_000)
            await asyncio.sleep(0.001)
        await response.write_eof()
        return response

    async def run():
        app = web.Application()
        app.router.add_get("/plik", handler)
        server = TestServer(app)
        await server.start_server()
        try:
            async with aiohttp.ClientSession() as client:
                return await MusicLibrary._fetch(client, str(server.make_url("/plik")))
        finally:
            await server.close()

    return asyncio.run(run())


def test_download_reads_the_whole_file_when_data_arrives_in_chunks():
    assert len(fetch_from_chunked_server(1_000_000)) == 1_000_000


def test_download_refuses_oversized_files():
    assert fetch_from_chunked_server(MAX_DOWNLOAD + 100_000) is None


def test_own_files_are_parsed(library):
    (library.music_dir / "01 Kult - Arahja.mp3").write_bytes(b"x")
    (library.music_dir / "Tylko_tytul.mp3").write_bytes(b"x")
    (library.music_dir / "notatki.txt").write_text("x")
    tracks = {t.title: t for t in library.own_tracks()}
    assert set(tracks) == {"Arahja", "Tylko tytul"}
    assert tracks["Arahja"].artist == "Kult"
    assert tracks["Tylko tytul"].artist == ""


def test_builtin_source_needs_no_network(library):
    tracks = asyncio.run(library.prepare(5, "all", "builtin"))
    assert len(tracks) == 5
    assert all(t.kind == "synth" and t.melody for t in tracks)


def test_own_source_falls_back_to_builtin_when_folder_is_empty(library):
    tracks = asyncio.run(library.prepare(3, "all", "own"))
    assert len(tracks) == 3 and all(t.kind == "synth" for t in tracks)


def test_offline_auto_mode_falls_back_to_builtin(library, monkeypatch):
    async def no_network(client, song):
        return None

    monkeypatch.setattr(library, "_resolve_hit", no_network)
    tracks = asyncio.run(library.prepare(4, "all", "auto"))
    assert len(tracks) == 4 and all(t.kind == "synth" for t in tracks)


def test_instrumental_mode_tops_up_with_originals_then_builtin(library, monkeypatch):
    def fake(kind, limit):
        found = []

        async def resolve(client, song):
            if len(found) >= limit:
                return None
            found.append(song)
            return Track(f'{kind}{len(found)}', song["title"], song["artist"], kind, path=Path("x"), lang=song["lang"])

        return resolve

    monkeypatch.setattr(library, "_resolve_instrumental", fake("instr", 3))
    monkeypatch.setattr(library, "_resolve_hit", fake("hit", 1))
    tracks = asyncio.run(library.prepare(6, "all", "instr"))
    kinds = sorted(t.kind for t in tracks)
    assert kinds == ["hit", "instr", "instr", "instr", "synth", "synth"]
    instrumental = {(t.artist, t.title) for t in tracks if t.kind == "instr"}
    assert not [t for t in tracks if t.kind == "hit" and (t.artist, t.title) in instrumental]


def test_instrumental_mode_ignores_own_files(library, monkeypatch):
    (library.music_dir / "Kult - Arahja.mp3").write_bytes(b"x")

    async def offline(client, song):
        return None

    monkeypatch.setattr(library, "_resolve_instrumental", offline)
    monkeypatch.setattr(library, "_resolve_hit", offline)
    tracks = asyncio.run(library.prepare(3, "all", "instr"))
    assert all(t.kind == "synth" for t in tracks)


def fake_deezer(library, monkeypatch, response):
    queries = []

    async def call(client, path, params=None):
        queries.append((path, (params or {}).get("q", "")))
        return response

    monkeypatch.setattr(library, "_deezer", call)
    return queries


def test_pinned_instrumental_is_used_without_searching(library, monkeypatch):
    queries = fake_deezer(library, monkeypatch, {"data": []})
    song = {"artist": "Lady Pank", "title": "Kryzysowa narzeczona", "instr": 71045148}
    meta = asyncio.run(library._lookup_instrumental(None, song))
    assert meta["deezer"] == 71045148
    assert not [q for _, q in queries if "instrumental" in q or "karaoke" in q]


def test_instrumental_search_miss_is_remembered_but_network_failure_is_not(library, monkeypatch):
    fake_deezer(library, monkeypatch, None)
    assert asyncio.run(library._lookup_instrumental(None, {"artist": "Nikt", "title": "Cisza"})) is None
    assert library.meta == {}
    queries = fake_deezer(library, monkeypatch, {"data": []})
    assert asyncio.run(library._lookup_instrumental(None, {"artist": "Nikt", "title": "Cisza"})) is None
    assert [m for m in library.meta.values() if "missed_at" in m]
    searched = len(queries)
    asyncio.run(library._lookup_instrumental(None, {"artist": "Nikt", "title": "Cisza"}))
    assert len(queries) == searched, "nieudane wyszukiwanie powtarza się dopiero po tygodniu"


def test_options_contain_correct_answer_once(library):
    tracks = asyncio.run(library.prepare(5, "all", "builtin"))
    for track in tracks:
        labels, correct = library.options_for(track, tracks)
        assert len(labels) == len(set(labels)) == 4
        assert labels[correct] == track.label


def test_media_paths_only_serve_registered_tracks(library):
    assert library.audio_path("../../etc/passwd") is None
    assert library.art_path("nieznany") is None


def test_filter_by_category(library):
    assert all(s["lang"] == "pl" for s in library.filter_catalog("pl"))
    assert all(s["lang"] != "pl" for s in library.filter_catalog("int"))
    assert all(s["decade"] == "90" for s in library.filter_catalog("90"))
    assert len(library.filter_catalog("all")) == len(library.catalog)

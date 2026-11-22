"""Dopasowanie wyników iTunes i dobór utworów, bez sieci."""
import asyncio
import random
from pathlib import Path

import aiohttp
import pytest
from aiohttp import web
from aiohttp.test_utils import TestServer

from server.music import MAX_DOWNLOAD, MusicLibrary, normalize, pick_itunes_result

DATA = Path(__file__).resolve().parent.parent / "data"


def result(artist, track, album="Album", preview="https://x/a.m4a"):
    return {"artistName": artist, "trackName": track, "collectionName": album, "previewUrl": preview}


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

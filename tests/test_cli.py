"""Adresy pokazywane graczom i serwowanie plików: tu pomyłka oznacza, że nikt nie dołączy."""
import asyncio

import pytest
from aiohttp.test_utils import TestClient, TestServer, make_mocked_request

from server.app import Links, build_app
from server.cli import _build_links, _build_rooms, _parse_args
from server.net import _rank

LAN = "192.168.1.13"


def links_for(*argv):
    return _build_links(_parse_args(list(argv)), LAN)


def request(host, **headers):
    return make_mocked_request("GET", "/ws", headers={"Host": host, **headers})


def test_tv_opened_as_localhost_sends_phones_to_lan_address():
    links = links_for()
    assert links.bases(request("localhost:8000")) == (f"http://{LAN}:8000", f"http://{LAN}:8000")
    assert links.bases(request("127.0.0.1:8000"))[0] == f"http://{LAN}:8000"
    assert links.bases(request("[::1]:8000"))[0] == f"http://{LAN}:8000"


def test_tv_opened_by_address_keeps_that_address():
    assert links_for().bases(request("192.168.1.20:8000")) == ("http://192.168.1.20:8000", "http://192.168.1.20:8000")


def test_certificate_moves_phones_to_https_but_keeps_tv_on_http():
    links = links_for("--cert", "c.pem", "--key", "k.pem", "--https-port", "9443")
    assert links.bases(request(f"{LAN}:8000")) == (f"https://{LAN}:9443", f"http://{LAN}:8000")


def test_public_url_wins():
    links = links_for("--public-url", "https://gra.example.pl:8443/")
    assert links.bases(request(f"{LAN}:8000"))[0] == "https://gra.example.pl:8443"


def test_cloud_uses_render_address(monkeypatch):
    monkeypatch.setenv("RENDER_EXTERNAL_URL", "https://teleturniej.onrender.com")
    links = links_for("--cloud")
    assert links.lan is None
    assert links.bases(request("teleturniej.onrender.com", **{"X-Forwarded-Proto": "https"})) == (
        "https://teleturniej.onrender.com", "https://teleturniej.onrender.com")
    # Adres znany z hostingu wygrywa z tym, co podał klient.
    assert links.bases(request("inny.example"))[1] == "https://teleturniej.onrender.com"


def test_cloud_without_known_address_trusts_proxy_scheme(monkeypatch):
    monkeypatch.delenv("RENDER_EXTERNAL_URL", raising=False)
    links = links_for("--cloud")
    assert links.bases(request("gra.example.com", **{"X-Forwarded-Proto": "https"}))[0] == "https://gra.example.com"
    # Telefon w chmurze nie może dostać adresu komputera, którego nie ma.
    assert links.bases(request("localhost:8000"))[0] == "http://localhost:8000"


def test_strange_host_header_does_not_reach_the_qr_code():
    assert Links().bases(request('evil"><script>'))[0] == "http://localhost"
    assert Links().bases(request("gra.example", **{"X-Forwarded-Proto": "javascript"}))[0] == "http://gra.example"


def test_port_comes_from_environment(monkeypatch):
    monkeypatch.setenv("PORT", "10000")
    assert _parse_args([]).port == 10000
    assert _parse_args(["--port", "8080"]).port == 8080


def test_certificate_requires_key():
    with pytest.raises(SystemExit):
        _parse_args(["--cert", "c.pem"])


def test_home_network_is_preferred_over_virtual_adapters():
    assert _rank("192.168.1.13") < _rank("172.20.192.1")
    assert _rank("10.0.0.5") < _rank("172.20.192.1")


def with_client(check):
    async def run():
        rooms, music = _build_rooms()
        client = TestClient(TestServer(build_app(rooms, music, links_for())))
        await client.start_server()
        try:
            await check(client, rooms)
        finally:
            await client.close()

    asyncio.run(run())


def test_entry_points_are_served():
    async def check(client, rooms):
        for path, needle in (("/tv/", "stage"), ("/app/", "manifest"), ("/app/manifest.webmanifest", "standalone"),
                             ("/healthz", "ok")):
            response = await client.get(path)
            assert response.status == 200, path
            assert needle in await response.text(), path
        root = await client.get("/", allow_redirects=False)
        assert root.status == 302 and root.headers["Location"] == "/app/"
        tv = await client.get("/tv", allow_redirects=False)
        assert tv.status == 302 and tv.headers["Location"] == "/tv/"

    with_client(check)


def test_qr_code_belongs_to_a_room():
    async def check(client, rooms):
        room = rooms.create("http://x", "http://x")
        response = await client.get(f"/qr.svg?r={room.code.lower()}")
        assert response.status == 200
        assert response.content_type == "image/svg+xml"
        assert "<svg" in await response.text()
        missing = "ZZZZ" if room.code != "ZZZZ" else "YYYY"
        assert (await client.get(f"/qr.svg?r={missing}")).status == 404
        assert (await client.get("/qr.svg")).status == 404

    with_client(check)


async def receive(ws, kind):
    while True:
        msg = await asyncio.wait_for(ws.receive_json(), timeout=3)
        if msg["t"] == kind:
            return msg


def test_tv_and_phone_meet_in_a_room_over_websocket():
    async def check(client, rooms):
        tv = await client.ws_connect("/ws")
        await tv.send_json({"t": "hello", "role": "tv"})
        code = (await receive(tv, "room"))["code"]
        state = (await receive(tv, "state"))["state"]
        # Testowy serwer działa pod 127.0.0.1, więc telefony dostają adres w sieci lokalnej.
        assert state["joinUrl"] == f"http://{LAN}:8000/app/?r={code}"

        phone = await client.ws_connect("/ws")
        await phone.send_json({"t": "hello", "role": "player", "room": code, "token": None})
        await receive(phone, "need_name")
        await phone.send_json({"t": "join", "room": code, "name": "Ania"})
        await receive(phone, "welcome")
        while True:
            state = (await receive(tv, "state"))["state"]
            if state["players"]:
                break
        assert [p["name"] for p in state["players"]] == ["Ania"]
        await phone.close()
        await tv.close()

    with_client(check)


@pytest.mark.parametrize("path", [
    "/media/song/nieznany",
    "/media/art/nieznany",
    "/app/../../server/cli.py",
    "/shared/..%2f..%2fserver%2fcli.py",
    "/tv/%2e%2e/%2e%2e/requirements.txt",
])
def test_files_outside_web_folder_are_not_reachable(path):
    async def check(client, rooms):
        response = await client.get(path)
        assert response.status in (403, 404), path

    with_client(check)

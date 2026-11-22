"""Warstwa HTTP i WebSocket."""
from __future__ import annotations

import asyncio
import io
import ipaddress
import json
import logging
import re
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import segno
from aiohttp import WSMsgType, web

from .music import MusicLibrary
from .rooms import Rooms

log = logging.getLogger("teleturniej")

ROOT = Path(__file__).resolve().parent.parent
WEB_DIR = ROOT / "web"
MAX_WS_MESSAGE = 16 * 1024
SAFE_HOST = re.compile(r"^[A-Za-z0-9.\-]+(:\d{1,5})?$|^\[[0-9A-Fa-f:.]+\](:\d{1,5})?$")


@dataclass
class Links:
    """Skąd telefony i telewizor mają wchodzić do gry.

    public: stały adres dla telefonów (adres w chmurze, --public-url albo HTTPS w sieci lokalnej).
    lan: adres komputera w sieci, podstawiany, gdy telewizor otwarto jako localhost, bo telefon
    pod „localhost” trafiłby do samego siebie.
    tv: stały adres ekranu TV (w chmurze ten sam co public); bez niego ten, pod którym otwarto TV.
    """
    public: Optional[str] = None
    lan: Optional[str] = None
    tv: Optional[str] = None

    def bases(self, request: web.Request) -> tuple[str, str]:
        seen = _seen_base(request)
        if self.lan and _is_loopback(request.host):
            seen = self.lan
        return (self.public or seen).rstrip("/"), (self.tv or seen).rstrip("/")


def _seen_base(request: web.Request) -> str:
    # Hosting w chmurze kończy HTTPS na swoim serwerze pośredniczącym i podaje to w nagłówku.
    proto = request.headers.get("X-Forwarded-Proto", request.scheme).split(",")[0].strip().lower()
    if proto not in ("http", "https"):
        proto = request.scheme
    host = request.host if SAFE_HOST.match(request.host or "") else "localhost"
    return f"{proto}://{host}"


def _is_loopback(host: str) -> bool:
    host = host or ""
    name = host[1:].split("]", 1)[0] if host.startswith("[") else host.split(":", 1)[0]
    if name == "localhost":
        return True
    try:
        return ipaddress.ip_address(name).is_loopback
    except ValueError:
        return False


ROOMS = web.AppKey("rooms", Rooms)
MUSIC = web.AppKey("music", MusicLibrary)
LINKS = web.AppKey("links", Links)


def _dumps(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"))


class WsConn:
    """Stan zastępuje poprzedni, jeśli klient nie nadąża: liczy się tylko najnowszy."""

    def __init__(self, ws: web.WebSocketResponse):
        self.ws = ws
        self.role: Optional[str] = None
        self.player_id: Optional[str] = None
        self.room = None
        self.bases: tuple[str, str] = ("", "")
        self._queue: deque = deque()
        self._latest: Optional[dict] = None
        self._wake = asyncio.Event()

    def send(self, obj: dict) -> None:
        if obj.get("t") == "state":
            self._latest = obj
        else:
            self._queue.append(obj)
        self._wake.set()

    def close(self) -> None:
        self._queue.append(None)
        self._wake.set()

    async def writer(self) -> None:
        while True:
            await self._wake.wait()
            self._wake.clear()
            while self._queue:
                item = self._queue.popleft()
                if item is None:
                    await self.ws.close()
                    return
                await self.ws.send_str(_dumps(item))
            if self._latest is not None:
                latest, self._latest = self._latest, None
                await self.ws.send_str(_dumps(latest))


async def ws_handler(request: web.Request) -> web.WebSocketResponse:
    rooms = request.app[ROOMS]
    ws = web.WebSocketResponse(heartbeat=20, max_msg_size=MAX_WS_MESSAGE)
    await ws.prepare(request)
    conn = WsConn(ws)
    conn.bases = request.app[LINKS].bases(request)
    writer = asyncio.ensure_future(conn.writer())
    try:
        async for message in ws:
            if message.type != WSMsgType.TEXT:
                continue
            try:
                payload = json.loads(message.data)
            except ValueError:
                continue
            if not isinstance(payload, dict):
                continue
            try:
                rooms.handle(conn, payload)
            except Exception:
                log.exception("Błąd obsługi wiadomości %r", payload.get("t"))
    finally:
        writer.cancel()
        rooms.disconnected(conn)
    return ws


def _qr_response(url: str) -> web.Response:
    code = segno.make(url, error="m")
    out = io.BytesIO()
    code.save(out, kind="svg", border=1, xmldecl=False, svgns=True, omitsize=True,
              dark="#0b1020", light="#ffffff")
    return web.Response(body=out.getvalue(), content_type="image/svg+xml",
                        headers={"Cache-Control": "no-store"})


async def qr_handler(request: web.Request) -> web.Response:
    room = request.app[ROOMS].get(request.query.get("r"))
    if room is None:
        raise web.HTTPNotFound()
    return _qr_response(room.session.join_url)


async def health_handler(request: web.Request) -> web.Response:
    return web.Response(text="ok")


async def song_handler(request: web.Request) -> web.StreamResponse:
    path = request.app[MUSIC].audio_path(request.match_info["id"])
    if path is None:
        raise web.HTTPNotFound()
    return web.FileResponse(path)


async def art_handler(request: web.Request) -> web.StreamResponse:
    path = request.app[MUSIC].art_path(request.match_info["id"])
    if path is None:
        raise web.HTTPNotFound()
    return web.FileResponse(path)


def _page(name: str):
    async def handler(request: web.Request) -> web.StreamResponse:
        return web.FileResponse(WEB_DIR / name)

    return handler


async def root_handler(request: web.Request) -> web.StreamResponse:
    raise web.HTTPFound("/app/")


async def tv_redirect(request: web.Request) -> web.StreamResponse:
    raise web.HTTPFound("/tv/")


@web.middleware
async def no_stale_files(request: web.Request, handler):
    response = await handler(request)
    if not request.path.startswith("/media/") and not isinstance(response, web.WebSocketResponse):
        response.headers.setdefault("Cache-Control", "no-cache")
    return response


def build_app(rooms: Rooms, music: MusicLibrary, links: Links) -> web.Application:
    app = web.Application(middlewares=[no_stale_files])
    app[ROOMS] = rooms
    app[MUSIC] = music
    app[LINKS] = links
    app.router.add_get("/", root_handler)
    app.router.add_get("/healthz", health_handler)
    app.router.add_get("/tv", tv_redirect)
    app.router.add_get("/tv/", _page("tv/index.html"))
    app.router.add_get("/app/", _page("app/index.html"))
    app.router.add_get("/ws", ws_handler)
    app.router.add_get("/qr.svg", qr_handler)
    app.router.add_get("/media/song/{id}", song_handler)
    app.router.add_get("/media/art/{id}", art_handler)
    app.router.add_static("/tv/", WEB_DIR / "tv")
    app.router.add_static("/app/", WEB_DIR / "app")
    app.router.add_static("/shared/", WEB_DIR / "shared")
    return app

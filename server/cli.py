"""Uruchamianie serwera: python -m server"""
from __future__ import annotations

import argparse
import asyncio
import logging
import os
import random
import ssl
import sys
import webbrowser
from pathlib import Path

from aiohttp import web

from .app import ROOT, Links, build_app
from .clock import RealClock
from .content import Content
from .music import MusicLibrary
from .net import lan_addresses, windows_public_network
from .rooms import Rooms
from .session import Session


def _env_port() -> int:
    # Hostingi w chmurze podają port w zmiennej PORT.
    try:
        return int(os.environ.get("PORT", "8000"))
    except ValueError:
        return 8000


def _parse_args(argv=None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="python -m server", description="Sutoliada: teleturnieje na telewizor i telefony")
    parser.add_argument("--port", type=int, default=_env_port(), help="port HTTP (domyślnie 8000 albo zmienna PORT)")
    parser.add_argument("--cloud", action="store_true",
                        help="serwer w internecie: bez wykrywania sieci lokalnej; adres z --public-url "
                             "albo ze zmiennej RENDER_EXTERNAL_URL")
    parser.add_argument("--ip", help="adres komputera w sieci, jeśli wykryty jest błędny")
    parser.add_argument("--open", action="store_true", help="otwórz ekran TV w przeglądarce tego komputera")
    parser.add_argument("--cert", type=Path, help="certyfikat TLS (PEM), włącza HTTPS i pełną instalację PWA")
    parser.add_argument("--key", type=Path, help="klucz prywatny TLS (PEM)")
    parser.add_argument("--https-port", type=int, default=8443, help="port HTTPS (domyślnie 8443)")
    parser.add_argument("--public-url", help="adres dla telefonów, np. https://gra.mojadomena.pl:8443")
    parser.add_argument("--prefetch-music", action="store_true",
                        help="pobierz fragmenty wszystkich utworów i zakończ, aby potem grać bez internetu")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args(argv)
    if bool(args.cert) != bool(args.key):
        parser.error("--cert i --key trzeba podać razem")
    return args


def _build_links(args: argparse.Namespace, ip: str) -> Links:
    if args.cloud:
        public = args.public_url or os.environ.get("RENDER_EXTERNAL_URL")
        public = public.rstrip("/") if public else None
        return Links(public=public, tv=public)
    if args.public_url:
        public = args.public_url.rstrip("/")
    elif args.cert:
        public = f"https://{ip}:{args.https_port}"
    else:
        public = None
    return Links(public=public, lan=f"http://{ip}:{args.port}")


def _build_rooms(data_dir: Path = ROOT / "data") -> tuple[Rooms, MusicLibrary]:
    content = Content(data_dir, random.Random())
    music = MusicLibrary(data_dir, data_dir / "cache", random.Random())
    clock = RealClock()

    def make_session(code: str, join_url: str, tv_url: str) -> Session:
        return Session(clock, content, music, join_url=join_url, tv_url=tv_url, rng=random.Random(), code=code)

    return Rooms(clock, make_session), music


def _print_cloud_banner(args: argparse.Namespace, links: Links) -> None:
    print(f"Serwer gry działa na porcie {args.port}.", flush=True)
    if links.public:
        print(f"Na telewizorze otwórz {links.public}/tv", flush=True)


def _print_banner(args: argparse.Namespace, links: Links, addresses: list[str]) -> None:
    line = "=" * 64
    print(line)
    print(f"  Na telewizorze otwórz:  {links.lan}/tv")
    print("  Telefony dołączają przez kod QR z ekranu TV")
    print(line)
    if args.ip is None and len(addresses) > 1:
        print("  Inne adresy tego komputera: " + ", ".join(addresses[1:]))
        print("  Jeśli telefon nie może się połączyć, wybierz właściwy: --ip ADRES")
    public = windows_public_network()
    if public:
        print()
        print(f'  UWAGA: sieć „{public}” ma w Windows profil Publiczna, więc zapora może')
        print("  blokować telefony i telewizor. Rozwiązanie (PowerShell jako administrator):")
        print(f'    Set-NetConnectionProfile -InterfaceAlias "{public}" -NetworkCategory Private')
        print("  a przy pierwszym uruchomieniu zezwól Pythonowi na dostęp w oknie zapory.")
    print()
    print("  Zatrzymanie serwera: Ctrl+C")


def _ignore_abrupt_disconnects(loop: asyncio.AbstractEventLoop, context: dict) -> None:
    # Wyłączony telefon to normalna sytuacja, a nie błąd, więc nie drukujemy śladu stosu.
    if isinstance(context.get("exception"), (ConnectionResetError, ConnectionAbortedError)):
        return
    loop.default_exception_handler(context)


async def _serve(args: argparse.Namespace, links: Links, addresses: list[str]) -> None:
    asyncio.get_running_loop().set_exception_handler(_ignore_abrupt_disconnects)
    rooms, music = _build_rooms()
    runner = web.AppRunner(build_app(rooms, music, links), access_log=None)
    await runner.setup()
    sites = [web.TCPSite(runner, "0.0.0.0", args.port)]
    if args.cert:
        context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
        context.load_cert_chain(args.cert, args.key)
        sites.append(web.TCPSite(runner, "0.0.0.0", args.https_port, ssl_context=context))
    for site in sites:
        await site.start()
    if args.cloud:
        _print_cloud_banner(args, links)
    else:
        _print_banner(args, links, addresses)
    if args.open:
        webbrowser.open(f"http://localhost:{args.port}/tv/")
    try:
        await asyncio.Event().wait()
    finally:
        await runner.cleanup()


def main(argv=None) -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)
    args = _parse_args(argv)
    logging.basicConfig(level=logging.INFO if args.verbose else logging.WARNING,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    if args.prefetch_music:
        library = MusicLibrary(ROOT / "data", ROOT / "data" / "cache", random.Random())
        hits, instrumentals, total = asyncio.run(library.prefetch_all())
        print(f"Gotowe. Bez internetu dostępne są {hits} z {total} utworów ze śpiewem "
              f"i {instrumentals} z {total} w wersji instrumentalnej.")
        return
    addresses = [] if args.cloud else lan_addresses()
    ip = args.ip or (addresses[0] if addresses else "127.0.0.1")
    links = _build_links(args, ip)
    try:
        asyncio.run(_serve(args, links, addresses))
    except KeyboardInterrupt:
        print("\nSerwer zatrzymany.")
    except OSError as exc:
        print(f"Nie można uruchomić serwera: {exc}\nCzy port {args.port} jest zajęty? Użyj --port.")
        sys.exit(1)

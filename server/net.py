"""Ustalanie adresu w sieci lokalnej i diagnostyka zapory Windows."""
from __future__ import annotations

import ipaddress
import socket
import subprocess
import sys
from typing import Optional


def _usable(address: str) -> bool:
    try:
        ip = ipaddress.ip_address(address)
    except ValueError:
        return False
    return ip.version == 4 and not ip.is_loopback and not ip.is_link_local


def _default_route_address() -> Optional[str]:
    # connect() na UDP nic nie wysyła, a jedynie wybiera interfejs z trasą domyślną.
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
        try:
            probe.connect(("192.0.2.1", 9))
            return probe.getsockname()[0]
        except OSError:
            return None


def _rank(address: str) -> int:
    # 172.16/12 to zwykle wirtualne karty WSL i Dockera, do których telefon nie dotrze.
    if address.startswith("192.168."):
        return 0
    if address.startswith("10."):
        return 1
    if address.startswith("172."):
        return 3
    return 2


def lan_addresses() -> list[str]:
    found: list[str] = []
    primary = _default_route_address()
    if primary and _usable(primary):
        found.append(primary)
    try:
        infos = socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET)
    except OSError:
        infos = []
    others = sorted({info[4][0] for info in infos if _usable(info[4][0])}, key=_rank)
    found.extend(a for a in others if a not in found)
    return found


def windows_public_network() -> Optional[str]:
    """Nazwa sieci z profilem Publiczna, bo wtedy zapora zwykle odcina telefony."""
    if sys.platform != "win32":
        return None
    command = ("Get-NetConnectionProfile | Where-Object NetworkCategory -eq 'Public' | "
               "Select-Object -First 1 -ExpandProperty InterfaceAlias")
    try:
        result = subprocess.run(["powershell", "-NoProfile", "-Command", command],
                                capture_output=True, text=True, timeout=8)
    except (OSError, subprocess.SubprocessError):
        return None
    return result.stdout.strip() or None

"""Czas i odroczone wywołania. Gry używają tylko tego interfejsu, dzięki czemu testy
mogą przewijać czas zamiast naprawdę czekać."""
from __future__ import annotations

import asyncio
import time
from typing import Callable


class RealClock:
    def now(self) -> float:
        return time.monotonic()

    def call_later(self, delay: float, fn: Callable[[], None]):
        return asyncio.get_running_loop().call_later(delay, fn)

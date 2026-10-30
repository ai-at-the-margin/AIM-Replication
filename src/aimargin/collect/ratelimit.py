"""Per-provider concurrency + requests-per-minute limiter and retry backoff."""

from __future__ import annotations

import asyncio
import random
import time
from collections import deque


class RateLimiter:
    """At most ``concurrency`` calls in flight and ``rpm`` call starts per rolling minute."""

    def __init__(self, concurrency: int, rpm: int):
        self.semaphore = asyncio.Semaphore(max(1, int(concurrency)))
        self.rpm = max(1, int(rpm))
        self.starts: deque[float] = deque()
        self.lock = asyncio.Lock()

    async def __aenter__(self) -> RateLimiter:
        await self.semaphore.acquire()
        await self._wait_for_slot()
        return self

    async def __aexit__(self, *exc: object) -> None:
        self.semaphore.release()

    async def _wait_for_slot(self) -> None:
        while True:
            async with self.lock:
                now = time.monotonic()
                while len(self.starts) > 0 and now - self.starts[0] > 60.0:
                    self.starts.popleft()
                if len(self.starts) < self.rpm:
                    self.starts.append(now)
                    return
                wait = 60.0 - (now - self.starts[0]) + 0.01
            await asyncio.sleep(max(0.01, wait))


def backoff_delay(attempt: int, base_s: float, max_s: float, retry_after: float | None = None,
                  rng: random.Random | None = None) -> float:
    """Exponential backoff with jitter; a server Retry-After always wins (plus jitter)."""
    generator = rng or random
    if retry_after is not None and retry_after >= 0:
        return min(max_s, retry_after + generator.uniform(0.0, 1.0))
    delay = base_s * (2.0 ** max(0, attempt - 1))
    return min(max_s, delay * generator.uniform(0.5, 1.5))

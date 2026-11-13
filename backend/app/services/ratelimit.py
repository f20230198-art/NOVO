"""In-memory sliding-window rate limits (one process; a hackathon server runs one).

Used for the voice assistant (protects the shared LLM key pool from one runaway phone) and
for community chat (protects everyone from spam). Never used on SOS or trip endpoints:
safety actions are not rate limited.
"""
from __future__ import annotations

import threading
import time
from collections import defaultdict, deque
from typing import Optional


class SlidingWindow:
    def __init__(self, limit: int, window_s: float):
        self.limit = limit
        self.window_s = window_s
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def hit(self, key: str, now: Optional[float] = None) -> float:
        """Record one request. Returns 0 when allowed, else seconds until the next one is allowed."""
        now = time.monotonic() if now is None else now
        with self._lock:
            q = self._hits[key]
            while q and q[0] <= now - self.window_s:
                q.popleft()
            if len(q) >= self.limit:
                return max(0.5, q[0] + self.window_s - now)
            q.append(now)
            return 0.0

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()


class Limiter:
    """Several windows that must all allow the request (e.g. per minute and per day)."""

    def __init__(self, *windows: SlidingWindow):
        self.windows = windows

    def check(self, key: str, now: Optional[float] = None) -> float:
        now = time.monotonic() if now is None else now
        # Check every window first so a refused request does not use up a slot in the others.
        waits = []
        for w in self.windows:
            with w._lock:
                q = w._hits[key]
                while q and q[0] <= now - w.window_s:
                    q.popleft()
                waits.append(max(0.5, q[0] + w.window_s - now) if len(q) >= w.limit else 0.0)
        if any(waits):
            return max(waits)
        for w in self.windows:
            w.hit(key, now)
        return 0.0

    def reset(self) -> None:
        for w in self.windows:
            w.reset()

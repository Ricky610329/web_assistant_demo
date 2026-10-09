"""Bounded in-memory admission control for exactly one application worker."""

from collections import deque
from collections.abc import Callable
from dataclasses import dataclass
from math import ceil
import time


class AdmissionError(Exception):
    def __init__(self, code: str, retry_after: int = 1):
        self.code = code
        self.retry_after = retry_after


@dataclass
class Lease:
    guard: "RequestGuard"
    released: bool = False

    def release(self) -> None:
        if not self.released:
            self.released = True
            self.guard.active -= 1


class RequestGuard:
    """Methods are synchronous: no await between checking and reserving a slot."""

    def __init__(self, concurrency: int, per_minute: int, clock: Callable = time.monotonic):
        self.concurrency = concurrency
        self.per_minute = per_minute
        self.clock = clock
        self.active = 0
        self._hits: dict[str, deque[float]] = {}
        self._last_sweep = clock()
        self._max_tracked_ips = 10000

    def acquire(self, client_ip: str) -> Lease:
        now = self.clock()
        cutoff = now - 60
        if now - self._last_sweep >= 30 or len(self._hits) >= self._max_tracked_ips:
            for ip in list(self._hits):
                if not self._hits[ip] or self._hits[ip][-1] <= cutoff:
                    del self._hits[ip]
            self._last_sweep = now
        hits = self._hits.get(client_ip)
        if hits is not None:
            while hits and hits[0] <= cutoff:
                hits.popleft()
            if len(hits) >= self.per_minute:
                raise AdmissionError("rate_limited", max(1, ceil(hits[0] + 60 - now)))
        if self.active >= self.concurrency:
            raise AdmissionError("busy")
        if hits is None:
            if len(self._hits) >= self._max_tracked_ips:
                raise AdmissionError("busy")
            hits = self._hits[client_ip] = deque()
        hits.append(now)
        self.active += 1
        return Lease(self)

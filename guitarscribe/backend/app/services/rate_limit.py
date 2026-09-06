"""Small, dependency-free per-client limiter for expensive analysis submissions."""

import time
from collections import deque


class SubmissionRateLimiter:
    def __init__(self, limit: int, window_seconds: int):
        self.limit = limit
        self.window_seconds = window_seconds
        self._attempts: dict[str, deque[float]] = {}

    def allow(self, client_key: str, now: float | None = None) -> tuple[bool, int]:
        if self.limit <= 0:
            return True, 0
        current = time.monotonic() if now is None else now
        attempts = self._attempts.setdefault(client_key, deque())
        cutoff = current - self.window_seconds
        while attempts and attempts[0] <= cutoff:
            attempts.popleft()
        if len(attempts) >= self.limit:
            retry_after = max(1, int(self.window_seconds - (current - attempts[0])))
            return False, retry_after
        attempts.append(current)
        return True, 0

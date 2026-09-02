"""In-memory sliding-window rate limiter (MASTER PROMPT §85: brute force).

Deliberately simple and dependency-free: a single-process in-memory counter
keyed by (client IP, route). This is correct and effective for a single
backend instance. If this is ever deployed behind multiple worker processes
or replicas, replace the store with something shared (Redis) — the limiter
interface below is small on purpose so that swap is a one-file change.
"""

import time
from collections import defaultdict, deque

from fastapi import Request

from app.core.exceptions import AppError
from fastapi import status


class RateLimitExceededError(AppError):
    def __init__(self, retry_after_seconds: int):
        super().__init__(
            code="RATE_LIMITED",
            message=f"Too many requests. Try again in {retry_after_seconds} seconds.",
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        )


class SlidingWindowRateLimiter:
    def __init__(self, max_requests: int, window_seconds: int):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._hits: dict[str, deque] = defaultdict(deque)

    def check(self, key: str) -> None:
        now = time.monotonic()
        window = self._hits[key]

        while window and now - window[0] > self.window_seconds:
            window.popleft()

        if len(window) >= self.max_requests:
            retry_after = max(1, int(self.window_seconds - (now - window[0])))
            raise RateLimitExceededError(retry_after)

        window.append(now)


def client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


# 10 attempts per minute per IP on the login endpoint — generous enough for a
# real user mistyping a password a few times, tight enough to blunt a
# credential-stuffing script that isn't even bothering to rotate IPs.
login_rate_limiter = SlidingWindowRateLimiter(max_requests=10, window_seconds=60)

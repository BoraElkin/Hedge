"""Rate limiting middleware for free tier."""

from __future__ import annotations

import time
from collections import defaultdict
from typing import Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

# Simple in-memory rate limiting
# In production, use Redis for distributed rate limiting


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Rate limiting middleware.

    Limits:
    - 100 requests per minute per IP for general endpoints
    - 10 requests per minute per IP for session start (free tier)
    """

    def __init__(
        self,
        app,
        requests_per_minute: int = 100,
        session_start_per_minute: int = 10,
    ):
        super().__init__(app)
        self.requests_per_minute = requests_per_minute
        self.session_start_per_minute = session_start_per_minute
        self.request_counts: dict[str, list[float]] = defaultdict(list)
        self.session_counts: dict[str, list[float]] = defaultdict(list)

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        client_ip = self._get_client_ip(request)
        now = time.time()
        minute_ago = now - 60

        # Clean old entries
        self.request_counts[client_ip] = [
            t for t in self.request_counts[client_ip] if t > minute_ago
        ]

        # Check general rate limit
        if len(self.request_counts[client_ip]) >= self.requests_per_minute:
            return Response(
                content='{"detail": "Rate limit exceeded. Please try again later."}',
                status_code=429,
                media_type="application/json",
            )

        # Check session start rate limit
        if request.url.path == "/sessions/start" and request.method == "POST":
            self.session_counts[client_ip] = [
                t for t in self.session_counts[client_ip] if t > minute_ago
            ]

            if len(self.session_counts[client_ip]) >= self.session_start_per_minute:
                return Response(
                    content='{"detail": "Too many session requests. Please wait before starting another session."}',
                    status_code=429,
                    media_type="application/json",
                )
            self.session_counts[client_ip].append(now)

        # Record this request
        self.request_counts[client_ip].append(now)

        return await call_next(request)

    def _get_client_ip(self, request: Request) -> str:
        """Get client IP, accounting for proxies."""
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            return forwarded.split(",")[0].strip()
        return request.client.host if request.client else "unknown"

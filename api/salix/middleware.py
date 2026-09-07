# -*- coding: utf-8 -*-
"""What stands between the internet and the analysis.

Salix was built as a single-tenant demo and had no gate at all: anyone who
could reach the port could read every call a company had ever recorded. That is
fine on a laptop and unacceptable anywhere else, so this module adds the three
things a live deployment needs and nothing it does not.

  1. A key on the door. Off when no key is configured, so a fresh clone still
     runs, but the startup log says loudly that it is open.
  2. A limit on the expensive doors. The Dojo turn costs model tokens, the
     voice route calls somebody else's undocumented endpoint, and an upload
     runs a seven-stage graph. One impatient click should not be able to run
     any of those a hundred times.
  3. A request id on everything, so a failure during a live demo can be traced
     from the browser console to the exact log line rather than guessed at.

Deliberately not here: sessions, users, roles. This build has one organisation,
and inventing a user model it does not need would be more code to be wrong
about. `routers/deps.py` is where that seam opens when it is time.
"""

from __future__ import annotations

import logging
import time
import uuid
from collections import defaultdict, deque
from typing import Callable

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from .signing import verify

log = logging.getLogger("salix.http")

#: Reachable without a key. Health and readiness are how a load balancer and a
#: deploy script find out whether the process is alive; requiring a secret to
#: answer that just means the secret ends up in the probe config.
PUBLIC_PATHS = frozenset({
    "/api/health",
    "/api/ready",
    "/docs",
    "/redoc",
    "/openapi.json",
})


def _client_key(request: Request) -> str:
    """Who to count a request against.

    Order matters, and the first entry is the one that makes this correct in
    deployment. Salix is served with Next in front, so by the time a request
    reaches this process the peer address is always the proxy: counting by it
    would give the whole sales floor one shared allowance, and the second rep
    to open the Dojo would be locked out by the first. So the proxy stamps a
    per-browser id and that is preferred.

    Then X-Forwarded-For, for a caller that reaches this port directly through
    an edge, and finally the peer address.

    All three are spoofable, which is fine and deliberate: this is a courtesy
    limit that stops a stuck retry loop and an impatient finger. The key on
    the door is what does access control.
    """
    stamped = request.headers.get("x-salix-client")
    if stamped:
        return stamped[:64]
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Give every request an id, a duration and one log line.

    The id goes back on the response so a screenshot of a browser console is
    enough to find the server side of the same request.
    """

    async def dispatch(self, request: Request, call_next: Callable):
        request_id = request.headers.get("x-request-id") or uuid.uuid4().hex[:12]
        request.state.request_id = request_id
        started = time.perf_counter()

        try:
            response = await call_next(request)
        except Exception:
            # Logged with the id so the traceback and the client's complaint
            # can be joined up. Re-raised for the handler that formats it.
            elapsed = (time.perf_counter() - started) * 1000
            log.exception(
                "%s %s -> unhandled after %.0fms [%s]",
                request.method, request.url.path, elapsed, request_id,
            )
            raise

        elapsed = (time.perf_counter() - started) * 1000
        response.headers["X-Request-Id"] = request_id
        # Slow requests are the ones worth seeing in a live demo; the rest stay
        # at debug so the log is readable.
        level = logging.WARNING if elapsed > 3000 else logging.DEBUG
        log.log(
            level, "%s %s %s %.0fms [%s]",
            request.method, request.url.path, response.status_code, elapsed, request_id,
        )
        return response


class ApiKeyMiddleware(BaseHTTPMiddleware):
    """Require a shared key on /api and /audio when one is configured.

    Accepts `X-API-Key: <key>` or `Authorization: Bearer <key>`, because the
    first is what a server-to-server caller reaches for and the second is what
    every HTTP client already knows how to send.

    `/audio` additionally accepts a signed, expiring URL, because the party
    fetching a recording in live mode is Model Studio and it has no header of
    ours to send. See `signing.py`.
    """

    def __init__(self, app, api_key: str | None):
        super().__init__(app)
        self.api_key = api_key

    async def dispatch(self, request: Request, call_next: Callable):
        if not self.api_key:
            return await call_next(request)

        path = request.url.path

        # Recordings. Not under /api, and for a long time therefore not
        # protected at all -- the most confidential thing in the system was
        # the one thing served without a credential.
        #
        # It cannot simply require the header: in live mode Model Studio
        # fetches the audio from its own servers and has nothing of ours to
        # present. So a signed, expiring URL is accepted as well, which is
        # exactly what the OSS path already hands out.
        if path.startswith("/audio/"):
            name = path.rsplit("/", 1)[-1]
            if verify(
                self.api_key,
                name,
                request.query_params.get("expires"),
                request.query_params.get("sig"),
            ):
                return await call_next(request)
            # Otherwise fall through: an operator or the app itself may hold
            # the key, and that is good enough too.

        elif not path.startswith("/api") or path in PUBLIC_PATHS:
            return await call_next(request)

        # A preflight carries no custom headers by definition.
        if request.method == "OPTIONS":
            return await call_next(request)

        presented = request.headers.get("x-api-key")
        if not presented:
            auth = request.headers.get("authorization", "")
            if auth.lower().startswith("bearer "):
                presented = auth[7:].strip()

        # Constant-time compare: a timing oracle on a shared secret is cheap to
        # avoid and awkward to explain afterwards.
        import hmac

        if not presented or not hmac.compare_digest(presented, self.api_key):
            log.warning("rejected %s %s from %s", request.method, path, _client_key(request))
            return JSONResponse(
                status_code=401,
                content={
                    "error": "unauthorized",
                    "detail": "This API requires a key. Send it as X-API-Key.",
                },
            )

        return await call_next(request)


class RateLimitMiddleware(BaseHTTPMiddleware):
    """A sliding window over the endpoints that cost real money or real time.

    In-process and per-address, which is the right size for one server. Behind
    several replicas this becomes advisory and the limit belongs in the proxy;
    it is still worth having, because the thing it actually prevents is one
    client's retry loop taking the demo down.
    """

    #: path prefix -> (requests, per seconds)
    LIMITS: dict[str, tuple[int, int]] = {
        "/api/dojo/turn": (30, 60),      # model tokens per turn
        "/api/dojo/voice": (60, 60),     # someone else's undocumented endpoint
        "/api/dojo/start": (20, 60),     # builds a persona from the archive
        "/api/calls/upload": (10, 300),  # a seven-stage graph per call
        "/api/reports/generate": (5, 300),
        "/api/search": (120, 60),
    }
    #: Everything else, so a runaway loop cannot flood the process.
    DEFAULT = (600, 60)

    def __init__(self, app, enabled: bool = True):
        super().__init__(app)
        self.enabled = enabled
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    def _limit_for(self, path: str) -> tuple[int, int]:
        for prefix, limit in self.LIMITS.items():
            if path.startswith(prefix):
                return limit
        return self.DEFAULT

    async def dispatch(self, request: Request, call_next: Callable):
        path = request.url.path
        if not self.enabled or not path.startswith("/api") or path in PUBLIC_PATHS:
            return await call_next(request)

        allowed, window = self._limit_for(path)
        bucket = f"{_client_key(request)}:{path}"
        now = time.monotonic()

        hits = self._hits[bucket]
        cutoff = now - window
        while hits and hits[0] < cutoff:
            hits.popleft()

        if len(hits) >= allowed:
            retry_after = max(1, int(window - (now - hits[0])))
            log.warning("rate limited %s for %s", path, _client_key(request))
            return JSONResponse(
                status_code=429,
                headers={"Retry-After": str(retry_after)},
                content={
                    "error": "rate_limited",
                    "detail": (
                        f"Too many requests to this endpoint. "
                        f"Try again in {retry_after}s."
                    ),
                    "retryable": True,
                },
            )

        hits.append(now)

        # Buckets for addresses that have gone quiet are dropped rather than
        # accumulating for the life of the process.
        if len(self._hits) > 4096:
            for key in [k for k, v in self._hits.items() if not v]:
                del self._hits[key]

        return await call_next(request)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Headers a browser should be told, even for a JSON API.

    The API is not meant to be framed or sniffed, and saying so costs nothing.
    A content-security-policy is deliberately absent: this process serves JSON
    and audio, and the page that renders them sets its own.
    """

    async def dispatch(self, request: Request, call_next: Callable):
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        return response

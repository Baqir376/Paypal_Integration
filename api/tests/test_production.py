# -*- coding: utf-8 -*-
"""The layer between the internet and the analysis.

Every test here builds its own app with the setting it is about, because these
are the behaviours that only exist when configured — asserting them against
the suite-wide open app would prove nothing.
"""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from salix.middleware import (
    ApiKeyMiddleware,
    RateLimitMiddleware,
    RequestContextMiddleware,
    SecurityHeadersMiddleware,
)

pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend():
    return "asyncio"


def _app(*, api_key=None, rate_limit=False):
    """A tiny app with the real middleware and a couple of stand-in routes.

    Deliberately not the full application: these tests are about the gate, and
    building the whole graph to prove a 401 would make them slow and couple
    them to everything else.
    """
    from fastapi import FastAPI
    from fastapi.responses import JSONResponse

    app = FastAPI()

    @app.get("/api/health")
    async def health():
        return {"status": "ok"}

    @app.get("/api/calls")
    async def calls():
        return []

    @app.post("/api/dojo/turn")
    async def turn():
        return {"ok": True}

    @app.get("/audio/{name}")
    async def audio(name: str):
        return {"served": name}

    @app.get("/api/boom")
    async def boom():
        raise RuntimeError("deliberate")

    @app.exception_handler(Exception)
    async def unhandled(request, exc):
        return JSONResponse(
            status_code=500,
            content={
                "error": "internal_error",
                "detail": "Something failed on our side.",
                "request_id": getattr(request.state, "request_id", "unknown"),
            },
        )

    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(RateLimitMiddleware, enabled=rate_limit)
    app.add_middleware(ApiKeyMiddleware, api_key=api_key)
    app.add_middleware(RequestContextMiddleware)
    return app


def _client(app, *, raise_errors=True):
    """`raise_errors=False` makes the transport behave like a real client.

    By default the ASGI transport re-raises whatever the app raised, which is
    convenient for debugging and wrong for testing the 500 handler: a browser
    never sees the exception, it sees the response the handler produced.
    """
    return AsyncClient(
        transport=ASGITransport(app=app, raise_app_exceptions=raise_errors),
        base_url="http://test",
    )


# --------------------------------------------------------------------------
# The key on the door
# --------------------------------------------------------------------------


class TestApiKey:
    async def test_without_a_configured_key_everything_is_open(self):
        """A fresh clone must still run. The startup log is what warns."""
        async with _client(_app(api_key=None)) as c:
            assert (await c.get("/api/calls")).status_code == 200

    async def test_a_configured_key_is_required(self):
        async with _client(_app(api_key="s3cret")) as c:
            response = await c.get("/api/calls")
            assert response.status_code == 401
            assert response.json()["error"] == "unauthorized"

    async def test_the_key_is_accepted_as_x_api_key(self):
        async with _client(_app(api_key="s3cret")) as c:
            r = await c.get("/api/calls", headers={"X-API-Key": "s3cret"})
            assert r.status_code == 200

    async def test_the_key_is_accepted_as_a_bearer_token(self):
        """Because every HTTP client already knows how to send one."""
        async with _client(_app(api_key="s3cret")) as c:
            r = await c.get("/api/calls", headers={"Authorization": "Bearer s3cret"})
            assert r.status_code == 200

    @pytest.mark.parametrize(
        "wrong",
        ["", "wrong", "s3cre", "s3crett", "S3CRET", " s3cret", "Bearer s3cret"],
    )
    async def test_a_near_miss_is_still_a_miss(self, wrong):
        async with _client(_app(api_key="s3cret")) as c:
            r = await c.get("/api/calls", headers={"X-API-Key": wrong})
            assert r.status_code == 401, wrong

    async def test_health_stays_reachable_without_the_key(self):
        """A probe that needs a secret is a secret in the probe config."""
        async with _client(_app(api_key="s3cret")) as c:
            assert (await c.get("/api/health")).status_code == 200

    async def test_the_rejection_does_not_describe_the_key(self):
        async with _client(_app(api_key="s3cret")) as c:
            body = (await c.get("/api/calls")).json()
            assert "s3cret" not in str(body)


class TestRecordings:
    """The recordings were the hole.

    `/audio` is not under `/api`, so the key never applied to it: the most
    confidential thing in the system -- somebody's actual sales call -- was
    the one thing served with no credential at all.

    It could not simply be made to require the header, because in live mode
    the party fetching the audio is Model Studio, from its own servers, with
    nothing of ours to present. Hence a signed URL that expires.
    """

    async def test_a_bare_filename_is_not_enough(self):
        async with _client(_app(api_key="s3cret")) as c:
            r = await c.get("/audio/call_abc123.mp3")
        assert r.status_code == 401

    async def test_the_key_opens_it(self):
        """For an operator, or the app fetching on a page's behalf."""
        async with _client(_app(api_key="s3cret")) as c:
            r = await c.get("/audio/call_abc123.mp3", headers={"X-API-Key": "s3cret"})
        assert r.status_code == 200

    async def test_a_signed_url_opens_it_without_any_header(self):
        """Which is the only thing Model Studio can do."""
        from salix.signing import sign

        expires, sig = sign("s3cret", "call_abc123.mp3")
        async with _client(_app(api_key="s3cret")) as c:
            r = await c.get(f"/audio/call_abc123.mp3?expires={expires}&sig={sig}")
        assert r.status_code == 200

    async def test_a_signature_does_not_travel_to_another_recording(self):
        """The filename is inside the message, so one URL is not a skeleton key."""
        from salix.signing import sign

        expires, sig = sign("s3cret", "call_mine.mp3")
        async with _client(_app(api_key="s3cret")) as c:
            r = await c.get(f"/audio/call_yours.mp3?expires={expires}&sig={sig}")
        assert r.status_code == 401

    async def test_an_expired_signature_is_refused(self):
        from salix.signing import sign

        expires, sig = sign("s3cret", "call_abc123.mp3", ttl=-10)
        async with _client(_app(api_key="s3cret")) as c:
            r = await c.get(f"/audio/call_abc123.mp3?expires={expires}&sig={sig}")
        assert r.status_code == 401

    async def test_the_expiry_cannot_simply_be_edited(self):
        """The obvious attack: keep the signature, move the deadline."""
        from salix.signing import sign

        expires, sig = sign("s3cret", "call_abc123.mp3", ttl=-10)
        async with _client(_app(api_key="s3cret")) as c:
            r = await c.get(f"/audio/call_abc123.mp3?expires={expires + 100000}&sig={sig}")
        assert r.status_code == 401

    @pytest.mark.parametrize("sig", ["", "deadbeef", "0" * 32, "not-hex"])
    async def test_a_guessed_signature_is_refused(self, sig):
        import time

        later = int(time.time()) + 600
        async with _client(_app(api_key="s3cret")) as c:
            r = await c.get(f"/audio/call_abc123.mp3?expires={later}&sig={sig}")
        assert r.status_code == 401

    async def test_a_signature_from_a_different_key_is_refused(self):
        from salix.signing import sign

        expires, sig = sign("someone-elses-secret", "call_abc123.mp3")
        async with _client(_app(api_key="s3cret")) as c:
            r = await c.get(f"/audio/call_abc123.mp3?expires={expires}&sig={sig}")
        assert r.status_code == 401

    async def test_without_a_configured_key_recordings_stay_open(self):
        """A fresh clone plays its own audio with no setup, as before."""
        async with _client(_app(api_key=None)) as c:
            assert (await c.get("/audio/call_abc123.mp3")).status_code == 200


class TestSignedUrls:
    """The signing itself, away from HTTP."""

    async def test_a_signature_verifies(self):
        from salix.signing import sign, verify

        expires, sig = sign("k", "a.mp3")
        assert verify("k", "a.mp3", expires, sig)

    async def test_every_malformed_input_is_false_not_an_exception(self):
        """This runs on a request path; the only question is whether to serve."""
        from salix.signing import verify

        for expires in (None, "", "abc", "1e9", [], {}):
            assert verify("k", "a.mp3", expires, "x" * 32) is False
        assert verify("k", "a.mp3", 99999999999, None) is False
        assert verify("", "a.mp3", 99999999999, "x" * 32) is False

    async def test_two_recordings_do_not_share_a_signature(self):
        from salix.signing import sign

        e1, s1 = sign("k", "a.mp3")
        e2, s2 = sign("k", "b.mp3")
        assert s1 != s2

    async def test_the_default_window_covers_a_long_transcription(self):
        """A twelve-hour recording must still be fetchable when its turn comes."""
        import time

        from salix.signing import DEFAULT_TTL, sign, verify

        expires, sig = sign("k", "a.mp3")
        assert expires - int(time.time()) >= 12 * 3600
        assert DEFAULT_TTL <= 60 * 60 * 24
        assert verify("k", "a.mp3", expires, sig)


# --------------------------------------------------------------------------
# Limits on the expensive doors
# --------------------------------------------------------------------------


class TestRateLimit:
    async def test_a_burst_past_the_limit_is_refused(self):
        app = _app(rate_limit=True)
        async with _client(app) as c:
            # /api/dojo/turn allows 30 a minute.
            codes = [(await c.post("/api/dojo/turn")).status_code for _ in range(34)]
        assert codes[:30] == [200] * 30
        assert 429 in codes[30:]

    async def test_the_refusal_says_when_to_come_back(self):
        app = _app(rate_limit=True)
        async with _client(app) as c:
            last = None
            for _ in range(34):
                last = await c.post("/api/dojo/turn")
            assert last.status_code == 429
            assert int(last.headers["Retry-After"]) >= 1
            body = last.json()
            assert body["retryable"] is True

    async def test_limits_are_per_endpoint(self):
        """Hammering the Dojo must not lock a manager out of the console."""
        app = _app(rate_limit=True)
        async with _client(app) as c:
            for _ in range(34):
                await c.post("/api/dojo/turn")
            assert (await c.get("/api/calls")).status_code == 200

    async def test_health_is_never_limited(self):
        app = _app(rate_limit=True)
        async with _client(app) as c:
            codes = [(await c.get("/api/health")).status_code for _ in range(50)]
        assert set(codes) == {200}

    async def test_two_browsers_get_separate_allowances(self):
        """The bug this exists to prevent.

        Next sits in front of the API, so every request arrives from the same
        address. Counting by that address gives the whole sales floor one
        allowance and the second rep to open the Dojo is refused because of
        the first. The proxy stamps a per-browser id; this is that working.
        """
        app = _app(rate_limit=True)
        async with _client(app) as c:
            for _ in range(34):
                await c.post("/api/dojo/turn", headers={"X-Salix-Client": "browser-a"})
            second = await c.post("/api/dojo/turn", headers={"X-Salix-Client": "browser-b"})
        assert second.status_code == 200

    async def test_one_browser_is_still_held_to_the_limit(self):
        """The other half: separate buckets must not mean no limit."""
        app = _app(rate_limit=True)
        async with _client(app) as c:
            codes = [
                (await c.post("/api/dojo/turn", headers={"X-Salix-Client": "same"})).status_code
                for _ in range(34)
            ]
        assert codes[-1] == 429

    async def test_the_stamped_id_wins_over_the_forwarded_address(self):
        """Both present is the normal deployment: an edge sets one, Next the
        other. The per-browser id is the more specific of the two."""
        app = _app(rate_limit=True)
        headers_a = {"X-Salix-Client": "a", "X-Forwarded-For": "203.0.113.7"}
        headers_b = {"X-Salix-Client": "b", "X-Forwarded-For": "203.0.113.7"}
        async with _client(app) as c:
            for _ in range(34):
                await c.post("/api/dojo/turn", headers=headers_a)
            assert (await c.post("/api/dojo/turn", headers=headers_b)).status_code == 200

    async def test_a_forwarded_address_still_separates_direct_callers(self):
        app = _app(rate_limit=True)
        async with _client(app) as c:
            for _ in range(34):
                await c.post("/api/dojo/turn", headers={"X-Forwarded-For": "198.51.100.1"})
            other = await c.post("/api/dojo/turn", headers={"X-Forwarded-For": "198.51.100.2"})
        assert other.status_code == 200

    async def test_a_absurd_client_id_cannot_grow_the_bucket_keys(self):
        """An id is truncated, so a caller cannot use it to consume memory."""
        app = _app(rate_limit=True)
        async with _client(app) as c:
            r = await c.post("/api/dojo/turn", headers={"X-Salix-Client": "z" * 10000})
        assert r.status_code == 200

    async def test_disabled_by_configuration(self):
        app = _app(rate_limit=False)
        async with _client(app) as c:
            codes = [(await c.post("/api/dojo/turn")).status_code for _ in range(40)]
        assert set(codes) == {200}


# --------------------------------------------------------------------------
# Traceability and failure
# --------------------------------------------------------------------------


class TestRequestContext:
    async def test_every_response_carries_an_id(self):
        async with _client(_app()) as c:
            r = await c.get("/api/calls")
            assert len(r.headers["X-Request-Id"]) >= 8

    async def test_a_supplied_id_is_kept(self):
        """So a trace started at the edge stays one trace."""
        async with _client(_app()) as c:
            r = await c.get("/api/calls", headers={"X-Request-Id": "abc123"})
            assert r.headers["X-Request-Id"] == "abc123"

    async def test_ids_differ_between_requests(self):
        async with _client(_app()) as c:
            a = (await c.get("/api/calls")).headers["X-Request-Id"]
            b = (await c.get("/api/calls")).headers["X-Request-Id"]
        assert a != b

    async def test_a_crash_returns_json_with_the_id_and_no_traceback(self):
        async with _client(_app(), raise_errors=False) as c:
            r = await c.get("/api/boom")
        assert r.status_code == 500
        body = r.json()
        assert body["error"] == "internal_error"
        assert body["request_id"] != "unknown"
        # The inside of the process stays inside it.
        assert "RuntimeError" not in str(body)
        assert "Traceback" not in str(body)
        assert "deliberate" not in str(body)


class TestBlankEnvironment:
    """A blank variable means unset.

    Every orchestrator passes optional settings through as empty strings --
    `SALIX_DATABASE_URL: ${SALIX_DATABASE_URL:-}` is the normal way to write an
    optional value in a compose file, and it arrives as "". Taken literally it
    replaced the SQLite default with an unparseable URL and the container died
    at startup, which is a miserable thing to read out of a deployment log.
    """

    @pytest.mark.parametrize(
        "var,field",
        [
            ("SALIX_DATABASE_URL", "database_url"),
            ("SALIX_CORS_ORIGINS", "cors_origins"),
            ("SALIX_DASHSCOPE_REGION", "dashscope_region"),
        ],
    )
    async def test_a_blank_value_falls_back_to_the_default(self, var, field, monkeypatch):
        from salix.config import Settings, get_settings

        get_settings.cache_clear()
        monkeypatch.setenv(var, "")
        try:
            value = getattr(get_settings(), field)
        finally:
            get_settings.cache_clear()

        assert value == Settings.model_fields[field].default
        assert value.strip()

    async def test_a_blank_key_still_means_no_key(self, monkeypatch):
        """The other direction: blank must not resurrect a default secret."""
        from salix.config import get_settings

        get_settings.cache_clear()
        monkeypatch.setenv("SALIX_API_KEY", "")
        monkeypatch.setenv("DASHSCOPE_API_KEY", "")
        try:
            settings = get_settings()
            assert not settings.api_key
            assert not settings.dashscope_api_key
        finally:
            get_settings.cache_clear()

    async def test_a_real_value_is_still_honoured(self, monkeypatch):
        from salix.config import get_settings

        get_settings.cache_clear()
        monkeypatch.setenv("SALIX_DATABASE_URL", "postgresql+asyncpg://u:p@h:5432/salix")
        try:
            assert get_settings().database_url.startswith("postgresql")
        finally:
            get_settings.cache_clear()


class TestSecurityHeaders:
    @pytest.mark.parametrize(
        "header,value",
        [
            ("X-Content-Type-Options", "nosniff"),
            ("X-Frame-Options", "DENY"),
            ("Referrer-Policy", "no-referrer"),
        ],
    )
    async def test_present(self, header, value):
        async with _client(_app()) as c:
            r = await c.get("/api/calls")
        assert r.headers[header] == value

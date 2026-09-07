"""Hostile and awkward input against the live HTTP surface.

Everything here goes through the real app with a real database. The bar is not
"returns 200" -- it is "never 500s, never writes outside its sandbox, and never
silently accepts something it should reject".
"""

from __future__ import annotations

import asyncio
import io
import os
from pathlib import Path

import pytest
import pytest_asyncio

os.environ.setdefault("SALIX_PROVIDER_MODE", "mock")


@pytest_asyncio.fixture(scope="module")
async def ctx(tmp_path_factory):
    import sys

    repo_root = Path(__file__).resolve().parent.parent.parent
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))

    tmp = tmp_path_factory.mktemp("salix-hostile")
    os.environ["SALIX_DATABASE_URL"] = f"sqlite+aiosqlite:///{(tmp / 'h.db').as_posix()}"
    os.environ["SALIX_STORAGE_DIR"] = str(tmp / "storage")

    from salix.config import get_settings
    from salix.store import db

    get_settings.cache_clear()
    await db.dispose()

    from salix.providers import build_providers
    from salix.routers.deps import reset_org_cache
    from seed.build import analyze, load_entities

    await db.init_db()
    await load_entities()
    await analyze(build_providers(get_settings()), {})
    reset_org_cache()

    from httpx import ASGITransport, AsyncClient

    from salix.app import create_app

    app = create_app()
    app.state.providers = build_providers(get_settings())

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        yield client, tmp

    await db.dispose()
    get_settings.cache_clear()


@pytest.fixture
def client(ctx):
    return ctx[0]


def audio(size: int = 512) -> io.BytesIO:
    return io.BytesIO(b"\x00" * size)


VALID = {"title": "T", "account": "A", "rep_id": "rep_zara"}


class TestUploadFilenames:
    """The stored name is derived from a UUID, never from user input. These
    prove it, because a filename is the classic path-traversal vector."""

    @pytest.mark.parametrize(
        "filename",
        [
            "../../../../etc/passwd.mp3",
            "..\\..\\..\\windows\\system32\\cfg.mp3",
            "/absolute/path/call.mp3",
            "C:\\Windows\\Temp\\call.mp3",
            "call\x00.mp3",
            "....//....//call.mp3",
        ],
    )
    async def test_traversal_attempts_are_neutralised(self, ctx, filename):
        client, tmp = ctx
        response = await client.post(
            "/api/calls/upload",
            files={"file": (filename, audio(), "audio/mpeg")},
            data=VALID,
        )
        assert response.status_code in (202, 415), response.text

        if response.status_code == 202:
            # Whatever was sent, the file must land inside the audio directory
            # under a generated name.
            call_id = response.json()["call_id"]
            written = list((tmp / "storage" / "audio").glob("*"))
            assert any(p.name.startswith(call_id) for p in written)
            for p in written:
                assert (tmp / "storage" / "audio") in p.parents

    @pytest.mark.parametrize(
        "filename",
        ["noextension", ".", "..", "file.", "archive.tar.gz", "script.mp3.exe"],
    )
    async def test_bad_extensions_are_rejected_cleanly(self, client, filename):
        response = await client.post(
            "/api/calls/upload",
            files={"file": (filename, audio(), "application/octet-stream")},
            data=VALID,
        )
        assert response.status_code == 415
        assert "detail" in response.json()

    async def test_empty_filename_is_a_missing_file(self, client):
        """An empty name means no file part was sent, so this is rejected by
        request validation before the handler ever sees it."""
        response = await client.post(
            "/api/calls/upload",
            files={"file": ("", audio(), "application/octet-stream")},
            data=VALID,
        )
        assert response.status_code == 422

    async def test_very_long_filename(self, client):
        response = await client.post(
            "/api/calls/upload",
            files={"file": ("a" * 3000 + ".mp3", audio(), "audio/mpeg")},
            data=VALID,
        )
        assert response.status_code in (202, 400, 413, 415)

    async def test_unicode_filename(self, client):
        response = await client.post(
            "/api/calls/upload",
            files={"file": ("通话录音-🎧.mp3", audio(), "audio/mpeg")},
            data=VALID,
        )
        assert response.status_code == 202

    async def test_uppercase_extension_is_accepted(self, client):
        response = await client.post(
            "/api/calls/upload",
            files={"file": ("CALL.MP3", audio(), "audio/mpeg")},
            data=VALID,
        )
        assert response.status_code == 202


class TestUploadFields:
    async def test_missing_required_fields(self, client):
        response = await client.post(
            "/api/calls/upload",
            files={"file": ("a.mp3", audio(), "audio/mpeg")},
            data={"title": "only title"},
        )
        assert response.status_code == 422

    async def test_no_file_at_all(self, client):
        response = await client.post("/api/calls/upload", data=VALID)
        assert response.status_code == 422

    async def test_hostile_text_in_metadata_is_stored_verbatim(self, client):
        payload = {
            "title": "<script>alert(1)</script>",
            "account": "'; DROP TABLE calls; --",
            "rep_id": "rep_zara",
        }
        response = await client.post(
            "/api/calls/upload",
            files={"file": ("a.mp3", audio(), "audio/mpeg")},
            data=payload,
        )
        assert response.status_code == 202
        call_id = response.json()["call_id"]

        # Give the background pipeline a moment, then read it back.
        for _ in range(60):
            detail = await client.get(f"/api/calls/{call_id}")
            if detail.status_code == 200:
                break
            await asyncio.sleep(0.05)

        body = detail.json()
        assert body["call"]["title"] == payload["title"]
        assert body["call"]["account"] == payload["account"]

    async def test_absurd_outcome_falls_back_to_open(self, client):
        response = await client.post(
            "/api/calls/upload",
            files={"file": ("a.mp3", audio(), "audio/mpeg")},
            data={**VALID, "outcome": "definitely-not-an-outcome"},
        )
        assert response.status_code == 202
        detail = await client.get(f"/api/calls/{response.json()['call_id']}")
        assert detail.json()["call"]["outcome"] == "open"

    async def test_non_numeric_speaker_id_is_ignored(self, client):
        response = await client.post(
            "/api/calls/upload",
            files={"file": ("a.mp3", audio(), "audio/mpeg")},
            data={**VALID, "rep_speaker_id": "not-a-number"},
        )
        assert response.status_code == 202


class TestQueryParameters:
    @pytest.mark.parametrize("limit", ["-1", "0", "999999", "abc", "1e9", ""])
    async def test_odd_limits_never_500(self, client, limit):
        response = await client.get(f"/api/calls?limit={limit}")
        assert response.status_code in (200, 422), response.text

    @pytest.mark.parametrize(
        "query",
        ["", "   ", "a", "'; DROP TABLE moments; --", "🎧" * 100, "x" * 5000],
    )
    async def test_search_never_500s(self, client, query):
        response = await client.get("/api/search", params={"q": query})
        assert response.status_code == 200
        assert isinstance(response.json(), list)

    async def test_search_with_unknown_filters(self, client):
        response = await client.get(
            "/api/search", params={"q": "pricing", "kind": "nonexistent", "outcome": "nope"}
        )
        assert response.status_code == 200
        assert response.json() == []

    @pytest.mark.parametrize("k", ["0", "-5", "10000"])
    async def test_search_k_bounds(self, client, k):
        response = await client.get("/api/search", params={"q": "objection", "k": k})
        assert response.status_code in (200, 422)


class TestUnknownIds:
    @pytest.mark.parametrize(
        "path",
        [
            "/api/calls/does-not-exist",
            "/api/calls/../../etc/passwd",
            "/api/reps/nope",
            "/api/plays/nope",
            "/api/deals/nope",
            "/api/reports/nope",
            "/api/calls/%00",
            "/api/reps/" + "x" * 2000,
        ],
    )
    async def test_unknown_ids_are_404_not_500(self, client, path):
        response = await client.get(path)
        assert response.status_code in (404, 400, 422), (
            f"{path} returned {response.status_code}"
        )

    async def test_coaching_unknown_rep(self, client):
        response = await client.post("/api/reps/nobody/coach")
        assert response.status_code == 404


class TestDojoHostile:
    async def test_start_with_bad_difficulty_is_clamped(self, client):
        for difficulty in (-99, 0, 99):
            response = await client.post(
                "/api/dojo/start", json={"rep_id": "rep_bilal", "difficulty": difficulty}
            )
            assert response.status_code == 200
            assert 1 <= response.json()["session"]["persona"]["difficulty"] <= 3

    async def test_end_with_a_malformed_session(self, client):
        response = await client.post("/api/dojo/end", json={"session": {"nonsense": 1}})
        assert response.status_code == 422

    async def test_turn_with_an_empty_message_is_refused(self, client):
        """An empty turn is refused rather than recorded.

        This used to answer 200 and duly record silence as something the rep
        said, which counted toward their turn total and diluted their talk
        ratio. The interface already refuses to send one; the endpoint now
        does too, and says why rather than merely dropping it.
        """
        started = (
            await client.post("/api/dojo/start", json={"rep_id": "rep_bilal"})
        ).json()
        for empty in ("", "   ", " 	 "):
            response = await client.post(
                "/api/dojo/turn",
                json={"session": started["session"], "text": empty},
            )
            assert response.status_code == 422, empty
            assert "turn" in response.json()["detail"].lower()

    async def test_a_long_but_plausible_turn_is_accepted(self, client):
        """Nobody speaks 3000 words in a turn, but a dictation glitch can
        produce one. It must still work rather than be refused."""
        started = (
            await client.post("/api/dojo/start", json={"rep_id": "rep_bilal"})
        ).json()
        async with client.stream(
            "POST",
            "/api/dojo/turn",
            json={"session": started["session"], "text": "word " * 3000},
        ) as response:
            assert response.status_code == 200
            body = "".join([c async for c in response.aiter_text()])
        assert "event: session" in body

    async def test_an_absurd_turn_is_refused_not_forwarded(self, client):
        """Past the cap the request is rejected at the boundary rather than
        billed to the model."""
        started = (
            await client.post("/api/dojo/start", json={"rep_id": "rep_bilal"})
        ).json()
        response = await client.post(
            "/api/dojo/turn",
            json={"session": started["session"], "text": "word " * 20000},
        )
        assert response.status_code == 422

    async def test_negative_timings_are_refused(self, client):
        started = (
            await client.post("/api/dojo/start", json={"rep_id": "rep_bilal"})
        ).json()
        response = await client.post(
            "/api/dojo/turn",
            json={"session": started["session"], "text": "hi", "start_ms": -5000},
        )
        assert response.status_code == 422


class TestPipelineIdempotency:
    async def test_reanalysing_a_call_does_not_duplicate_plays(self, ctx):
        """Re-running the pipeline is a normal operation -- a retry, a model
        upgrade. It must not inflate usage counts or the moment index."""
        client, _ = ctx
        from salix.config import get_settings
        from salix.pipeline.orchestrator import Pipeline
        from salix.providers import build_providers
        from salix.store import repo, session_scope

        providers = build_providers(get_settings())

        async with session_scope() as session:
            call = await repo.get_call(session, "call_northwind_1")
            before_plays = await repo.list_plays(session, call.org_id)
            before_usage = {p.id: p.usage_count for p in before_plays}
            before_moments = await repo.count_moments(session, call.org_id)

        from seed import scripts
        from salix.providers.mock import MockASR

        class Scripted:
            name = "scripted"

            async def transcribe(self, url, *, diarize=True, language_hints=("en",)):
                return MockASR.from_script(scripts.get("northwind_1_discovery"))

        providers.asr = Scripted()

        async with session_scope() as session:
            call = await repo.get_call(session, "call_northwind_1")
            await Pipeline(providers).run(session, call, rep_name="Zara Iqbal")

        async with session_scope() as session:
            after_plays = await repo.list_plays(session, call.org_id)
            after_moments = await repo.count_moments(session, call.org_id)

        assert len(after_plays) == len(before_plays), "play library grew on re-run"
        for play in after_plays:
            if play.id in before_usage:
                assert play.usage_count == before_usage[play.id], (
                    f"{play.name} usage inflated"
                )
        assert after_moments == before_moments, "moment index grew on re-run"


class TestConcurrentRequests:
    async def test_parallel_reads_are_consistent(self, client):
        responses = await asyncio.gather(
            *[client.get("/api/overview") for _ in range(12)]
        )
        assert all(r.status_code == 200 for r in responses)
        payloads = [r.json()["team"]["calls_analyzed"] for r in responses]
        assert len(set(payloads)) == 1, "concurrent reads disagreed"

    async def test_parallel_mixed_endpoints(self, client):
        paths = [
            "/api/health", "/api/overview", "/api/reps", "/api/plays",
            "/api/deals", "/api/calls", "/api/reports/latest",
        ]
        responses = await asyncio.gather(*[client.get(p) for p in paths * 3])
        assert all(r.status_code == 200 for r in responses)

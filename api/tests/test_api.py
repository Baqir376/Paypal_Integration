"""API surface tests.

These run against a real seeded database built through the real pipeline, so
they check the whole stack rather than a mocked repository. Anything that
breaks the contract the frontend depends on fails here.
"""

from __future__ import annotations

import asyncio
import io
import os

import pytest
import pytest_asyncio

os.environ.setdefault("SALIX_PROVIDER_MODE", "mock")


@pytest_asyncio.fixture(scope="module")
async def app_client(tmp_path_factory):
    """A seeded application, built once for the module."""
    import sys
    from pathlib import Path

    repo_root = Path(__file__).resolve().parent.parent.parent
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))

    tmp = tmp_path_factory.mktemp("salix-api")
    os.environ["SALIX_DATABASE_URL"] = f"sqlite+aiosqlite:///{(tmp / 'test.db').as_posix()}"
    os.environ["SALIX_STORAGE_DIR"] = str(tmp / "storage")

    from salix.config import get_settings
    from salix.store import db

    get_settings.cache_clear()
    await db.dispose()

    from seed.build import analyze, load_entities
    from salix.providers import build_providers
    from salix.routers.deps import reset_org_cache

    await db.init_db()
    await load_entities()
    await analyze(build_providers(get_settings()), {})
    reset_org_cache()

    from httpx import ASGITransport, AsyncClient
    from salix.app import create_app

    app = create_app()
    app.state.providers = build_providers(get_settings())

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client

    await db.dispose()
    get_settings.cache_clear()


class TestHealth:
    async def test_reports_ok_and_seeded(self, app_client):
        response = await app_client.get("/api/health")
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "ok"
        assert body["seeded"] is True
        assert body["calls"] == 10

    async def test_declares_the_models_in_use(self, app_client):
        body = (await app_client.get("/api/health")).json()
        assert "qwen" in body["models"]["reasoning"].lower()
        assert body["models"]["transcription"]
        assert body["provider_mode"] in ("mock", "live")

    async def test_indexed_moments_exist(self, app_client):
        body = (await app_client.get("/api/health")).json()
        assert body["moments"] > 0
        assert body["plays"] > 0


class TestOverview:
    async def test_returns_every_section(self, app_client):
        body = (await app_client.get("/api/overview")).json()
        for key in ("org", "team", "reps", "recent_calls", "risks", "top_plays"):
            assert key in body

    async def test_team_metrics_are_coherent(self, app_client):
        team = (await app_client.get("/api/overview")).json()["team"]
        assert team["calls_analyzed"] == 10
        assert 0.0 <= team["win_rate"] <= 1.0
        assert 0.0 <= team["avg_talk_ratio"] <= 1.0
        assert team["hours_analyzed"] > 0

    async def test_leaderboard_is_ranked(self, app_client):
        reps = (await app_client.get("/api/overview")).json()["reps"]
        scores = [r["overall_score"] for r in reps]
        assert scores == sorted(scores, reverse=True)
        assert [r["rank"] for r in reps] == list(range(1, len(reps) + 1))

    async def test_top_performer_leads_the_board(self, app_client):
        """The seed corpus is built so the designated top performer measures
        best. If this fails, the demo is telling the opposite of the truth."""
        reps = (await app_client.get("/api/overview")).json()["reps"]
        assert reps[0]["rep"]["is_top_performer"] is True
        assert reps[0]["rep"]["name"] == "Zara Iqbal"

    async def test_struggling_rep_is_last(self, app_client):
        reps = (await app_client.get("/api/overview")).json()["reps"]
        assert reps[-1]["rep"]["name"] == "Bilal Khan"

    async def test_recent_calls_carry_display_fields(self, app_client):
        calls = (await app_client.get("/api/overview")).json()["recent_calls"]
        assert calls
        assert all(c["rep_name"] for c in calls)


class TestCalls:
    async def test_list(self, app_client):
        calls = (await app_client.get("/api/calls")).json()
        assert len(calls) == 10
        assert all(c["rep_name"] for c in calls)

    async def test_filter_by_rep(self, app_client):
        calls = (await app_client.get("/api/calls?rep_id=rep_bilal")).json()
        assert len(calls) == 3
        assert all(c["call"]["rep_id"] == "rep_bilal" for c in calls)

    async def test_detail_includes_every_artifact(self, app_client):
        body = (await app_client.get("/api/calls/call_northwind_1")).json()
        assert body["transcript"]["segments"]
        assert body["metrics"]["talk_ratio_rep"] > 0
        assert body["scorecard"]["axes"]
        assert body["analysis"] is not None
        assert body["rep_name"] == "Zara Iqbal"
        assert body["deal"]["account"] == "Northwind Logistics"

    async def test_transcript_segments_carry_computed_fields(self, app_client):
        body = (await app_client.get("/api/calls/call_northwind_1")).json()
        segment = body["transcript"]["segments"][0]
        for key in ("id", "role", "start_ms", "end_ms", "text", "duration_ms", "wpm"):
            assert key in segment

    async def test_timeline_covers_the_call(self, app_client):
        body = (await app_client.get("/api/calls/call_northwind_1")).json()
        timeline = body["metrics"]["timeline"]
        assert timeline[0]["start_ms"] == 0
        assert timeline[-1]["end_ms"] == body["metrics"]["duration_ms"]

    async def test_monologue_call_is_visibly_worse(self, app_client):
        """Bilal's demo call is the deliberate disaster in the corpus."""
        body = (await app_client.get("/api/calls/call_halcyon_1")).json()
        assert body["metrics"]["talk_ratio_rep"] > 0.75
        assert body["metrics"]["longest_monologue_ms"] > 150_000

    async def test_unknown_call_is_404(self, app_client):
        assert (await app_client.get("/api/calls/nope")).status_code == 404

    async def test_upload_rejects_a_non_audio_file(self, app_client):
        response = await app_client.post(
            "/api/calls/upload",
            files={"file": ("notes.txt", io.BytesIO(b"hello"), "text/plain")},
            data={"title": "T", "account": "A", "rep_id": "rep_zara"},
        )
        assert response.status_code == 415

    async def test_upload_rejects_an_unknown_rep(self, app_client):
        response = await app_client.post(
            "/api/calls/upload",
            files={"file": ("call.mp3", io.BytesIO(b"\x00" * 64), "audio/mpeg")},
            data={"title": "T", "account": "A", "rep_id": "rep_nobody"},
        )
        assert response.status_code == 400

    async def test_upload_rejects_an_empty_file(self, app_client):
        response = await app_client.post(
            "/api/calls/upload",
            files={"file": ("call.mp3", io.BytesIO(b""), "audio/mpeg")},
            data={"title": "T", "account": "A", "rep_id": "rep_zara"},
        )
        assert response.status_code == 400


class TestReps:
    async def test_leaderboard(self, app_client):
        reps = (await app_client.get("/api/reps")).json()
        assert len(reps) == 5
        assert all("axes" in r and "team_axes" in r for r in reps)

    async def test_profile(self, app_client):
        body = (await app_client.get("/api/reps/rep_bilal")).json()
        assert body["snapshot"]["rep"]["name"] == "Bilal Khan"
        assert len(body["calls"]) == 3

    async def test_profile_carries_a_coaching_plan_shape(self, app_client):
        body = (await app_client.get("/api/reps/rep_bilal")).json()
        assert "coaching_plan" in body

    async def test_unknown_rep_is_404(self, app_client):
        assert (await app_client.get("/api/reps/rep_nobody")).status_code == 404

    async def test_coach_generates_a_grounded_plan(self, app_client):
        response = await app_client.post("/api/reps/rep_bilal/coach")
        assert response.status_code == 200
        plan = response.json()
        assert plan["gaps"]
        assert plan["script"] is not None
        assert plan["script"]["sections"]

    async def test_coaching_never_cites_the_rep_to_themselves(self, app_client):
        plan = (await app_client.post("/api/reps/rep_bilal/coach")).json()
        for source in plan["script"]["grounded_in"]:
            assert source["rep_name"] != "Bilal Khan"


class TestPlays:
    async def test_list(self, app_client):
        plays = (await app_client.get("/api/plays")).json()
        assert plays
        assert all("used_by" in p and "usage_count" in p for p in plays)

    async def test_detail_hydrates_instances_with_calls(self, app_client):
        plays = (await app_client.get("/api/plays")).json()
        body = (await app_client.get(f"/api/plays/{plays[0]['id']}")).json()
        assert body["instances"]
        assert all(i["call_title"] for i in body["instances"])

    async def test_unknown_play_is_404(self, app_client):
        assert (await app_client.get("/api/plays/nope")).status_code == 404


class TestDeals:
    async def test_list_is_ordered_by_health(self, app_client):
        deals = (await app_client.get("/api/deals")).json()
        health = [d["trajectory"]["health"] for d in deals]
        assert health == sorted(health), "sickest deals first"

    async def test_trajectory_has_points_and_a_verdict(self, app_client):
        body = (await app_client.get("/api/deals/deal_northwind")).json()
        assert body["trajectory"]["points"]
        assert body["trajectory"]["verdict"]
        assert body["owner_name"] == "Zara Iqbal"

    async def test_lost_deal_carries_risks(self, app_client):
        body = (await app_client.get("/api/deals/deal_halcyon")).json()
        assert body["trajectory"]["risks"], "a lost deal should show why"

    async def test_risks_name_a_cause(self, app_client):
        body = (await app_client.get("/api/deals/deal_halcyon")).json()
        for risk in body["trajectory"]["risks"]:
            assert risk["explanation"]
            assert risk["kind"]


class TestSearch:
    async def test_returns_scored_moments(self, app_client):
        hits = (await app_client.get("/api/search?q=pricing objection")).json()
        assert hits
        assert all(-1.0 <= h["score"] <= 1.0 for h in hits)

    async def test_filters_by_outcome(self, app_client):
        hits = (await app_client.get("/api/search?q=objection&outcome=won")).json()
        assert all(h["moment"]["outcome"] == "won" for h in hits)

    async def test_empty_query_returns_nothing(self, app_client):
        assert (await app_client.get("/api/search?q=  ")).json() == []


class TestDojo:
    async def test_start_builds_a_persona_from_real_calls(self, app_client):
        response = await app_client.post(
            "/api/dojo/start", json={"rep_id": "rep_bilal", "difficulty": 2}
        )
        assert response.status_code == 200
        body = response.json()
        persona = body["session"]["persona"]
        assert persona["objections"]
        assert persona["derived_from_call_ids"], "must be mined from this rep's calls"
        assert body["opening"]

    async def test_persona_objections_trace_to_this_reps_calls(self, app_client):
        body = (
            await app_client.post("/api/dojo/start", json={"rep_id": "rep_bilal"})
        ).json()
        calls = (await app_client.get("/api/calls?rep_id=rep_bilal")).json()
        owned = {c["call"]["id"] for c in calls}
        assert set(body["session"]["persona"]["derived_from_call_ids"]) <= owned

    async def test_difficulty_raises_hardness(self, app_client):
        easy = (
            await app_client.post(
                "/api/dojo/start", json={"rep_id": "rep_bilal", "difficulty": 1}
            )
        ).json()["session"]["persona"]
        hard = (
            await app_client.post(
                "/api/dojo/start", json={"rep_id": "rep_bilal", "difficulty": 3}
            )
        ).json()["session"]["persona"]
        assert max(o["hardness"] for o in hard["objections"]) > max(
            o["hardness"] for o in easy["objections"]
        )

    async def test_unknown_rep_is_404(self, app_client):
        response = await app_client.post("/api/dojo/start", json={"rep_id": "nope"})
        assert response.status_code == 404

    async def test_a_turn_streams_and_returns_session_state(self, app_client):
        started = (
            await app_client.post("/api/dojo/start", json={"rep_id": "rep_bilal"})
        ).json()

        async with app_client.stream(
            "POST",
            "/api/dojo/turn",
            json={
                "session": started["session"],
                "text": "What does your renewal process look like today?",
                "start_ms": 0,
                "end_ms": 4000,
            },
        ) as response:
            assert response.status_code == 200
            body = "".join([chunk async for chunk in response.aiter_text()])

        assert "event: delta" in body
        assert "event: session" in body

    async def test_ending_scores_the_session(self, app_client):
        started = (
            await app_client.post("/api/dojo/start", json={"rep_id": "rep_bilal"})
        ).json()
        session = started["session"]
        session["turns"] = [
            {"index": 0, "speaker": "rep", "text": "What does that look like today?",
             "start_ms": 0, "end_ms": 3000},
            {"index": 1, "speaker": "buyer",
             "text": "We track it in spreadsheets and it is honestly a mess right now.",
             "start_ms": 3600, "end_ms": 9000},
        ]
        response = await app_client.post("/api/dojo/end", json={"session": session})
        assert response.status_code == 200
        score = response.json()["score"]
        assert 0.0 <= score["overall"] <= 100.0
        assert score["verdict"]
        assert 0.0 <= score["talk_ratio_rep"] <= 1.0

    async def test_scored_session_is_persisted(self, app_client):
        sessions = (await app_client.get("/api/dojo/sessions?rep_id=rep_bilal")).json()
        assert sessions
        assert sessions[0]["score"] is not None


class TestReports:
    async def test_generate_then_fetch(self, app_client):
        generated = await app_client.post("/api/reports/generate?cycle_label=Q1%202026")
        assert generated.status_code == 200
        report = generated.json()
        assert report["team"]["calls_analyzed"] == 10
        assert report["reps"]
        assert report["headline"]

        latest = (await app_client.get("/api/reports/latest")).json()
        assert latest["id"] == report["id"]

    async def test_report_rows_cover_every_rep(self, app_client):
        report = (await app_client.get("/api/reports/latest")).json()
        assert len(report["reps"]) == 5

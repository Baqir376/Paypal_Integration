"""Tests for vector search and the persistence round trip."""

from __future__ import annotations

import math
from datetime import datetime, timezone

import numpy as np
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from salix.schemas.call import Call, CallStatus, Segment, Transcript
from salix.schemas.common import CallOutcome, PlayKind, SpeakerRole
from salix.schemas.metrics import CallMetrics
from salix.schemas.org import Org, Rep
from salix.schemas.play import Play
from salix.store import repo, vectors
from salix.store.models import Base


def unit(*values: float) -> list[float]:
    array = np.asarray(values, dtype=np.float32)
    return (array / np.linalg.norm(array)).tolist()


# --------------------------------------------------------------------------
# Vectors
# --------------------------------------------------------------------------


class TestEncoding:
    def test_round_trip_preserves_values(self):
        original = [0.5, -0.25, 0.125]
        restored = vectors.decode(vectors.encode(original))
        assert np.allclose(restored, original)

    def test_encoding_is_float32(self):
        assert len(vectors.encode([1.0, 2.0, 3.0])) == 12

    def test_stable_bytes_for_same_input(self):
        assert vectors.encode([1.0, 2.0]) == vectors.encode([1.0, 2.0])


class TestCosine:
    def test_identical_vector_scores_one(self):
        v = unit(1, 2, 3)
        scores = vectors.cosine_scores(v, [vectors.encode(v)])
        assert scores[0] == pytest.approx(1.0, abs=1e-6)

    def test_orthogonal_scores_zero(self):
        scores = vectors.cosine_scores([1, 0], [vectors.encode([0, 1])])
        assert scores[0] == pytest.approx(0.0, abs=1e-6)

    def test_opposite_scores_minus_one(self):
        scores = vectors.cosine_scores([1, 0], [vectors.encode([-1, 0])])
        assert scores[0] == pytest.approx(-1.0, abs=1e-6)

    def test_unnormalised_input_still_scores_correctly(self):
        # Magnitude must not affect cosine similarity.
        scores = vectors.cosine_scores([10, 0], [vectors.encode([3, 0])])
        assert scores[0] == pytest.approx(1.0, abs=1e-6)

    def test_empty_index(self):
        assert vectors.cosine_scores([1, 0], []).size == 0

    def test_dimension_mismatch_is_explicit(self):
        with pytest.raises(ValueError, match="does not match"):
            vectors.cosine_scores([1, 0, 0], [vectors.encode([1, 0])])

    def test_ragged_index_is_rejected(self):
        with pytest.raises(ValueError, match="dimensions differ"):
            vectors.matrix([vectors.encode([1, 0]), vectors.encode([1, 0, 0])])


class TestTopK:
    BANK = [
        vectors.encode(unit(1, 0, 0)),
        vectors.encode(unit(0.9, 0.1, 0)),
        vectors.encode(unit(0, 1, 0)),
        vectors.encode(unit(0, 0, 1)),
    ]

    def test_orders_by_similarity(self):
        result = vectors.top_k(unit(1, 0, 0), self.BANK, k=2)
        assert [i for i, _ in result] == [0, 1]

    def test_scores_descend(self):
        result = vectors.top_k(unit(1, 0, 0), self.BANK, k=4)
        scores = [s for _, s in result]
        assert scores == sorted(scores, reverse=True)

    def test_k_larger_than_index_is_safe(self):
        assert len(vectors.top_k(unit(1, 0, 0), self.BANK, k=99)) == 4

    def test_min_score_filters(self):
        result = vectors.top_k(unit(1, 0, 0), self.BANK, k=4, min_score=0.5)
        assert len(result) == 2

    def test_empty_index(self):
        assert vectors.top_k([1, 0, 0], [], k=3) == []


class TestMMR:
    def test_prefers_diversity_over_near_duplicates(self):
        # Three near-identical vectors, then a distinct one. Plain top-k would
        # return the three duplicates; MMR should reach for the outlier.
        bank = [
            vectors.encode(unit(1, 0, 0)),
            vectors.encode(unit(0.99, 0.01, 0)),
            vectors.encode(unit(0.98, 0.02, 0)),
            vectors.encode(unit(0.4, 0.9, 0)),
        ]
        plain = [i for i, _ in vectors.top_k(unit(1, 0, 0), bank, k=3)]
        diverse = [i for i, _ in vectors.mmr(unit(1, 0, 0), bank, k=3, diversity=0.6)]
        assert plain == [0, 1, 2]
        assert 3 in diverse

    def test_returns_requested_count(self):
        bank = [vectors.encode(unit(1, i * 0.3, 0)) for i in range(1, 8)]
        assert len(vectors.mmr(unit(1, 0, 0), bank, k=4)) == 4

    def test_first_pick_is_the_most_relevant(self):
        bank = [
            vectors.encode(unit(0, 1, 0)),
            vectors.encode(unit(1, 0, 0)),
        ]
        assert vectors.mmr(unit(1, 0, 0), bank, k=2)[0][0] == 1

    def test_empty_index(self):
        assert vectors.mmr([1, 0, 0], [], k=3) == []


# --------------------------------------------------------------------------
# Persistence
# --------------------------------------------------------------------------


@pytest_asyncio.fixture
async def session():
    """A fresh in-memory database per test."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as s:
        yield s
    await engine.dispose()


def a_call(call_id="c1", rep_id="r1", deal_id="d1") -> Call:
    return Call(
        id=call_id,
        org_id="o1",
        deal_id=deal_id,
        rep_id=rep_id,
        title="Discovery with Northwind",
        account="Northwind",
        occurred_at=datetime(2026, 3, 4, 10, 0, tzinfo=timezone.utc),
        duration_ms=1_800_000,
        status=CallStatus.READY,
        outcome=CallOutcome.WON,
    )


class TestRoundTrip:
    async def test_org_and_rep(self, session):
        await repo.put_org(session, Org(id="o1", name="Meridian"))
        await repo.put_rep(
            session,
            Rep(id="r1", org_id="o1", name="Zara Iqbal", is_top_performer=True),
        )
        assert (await repo.get_org(session, "o1")).name == "Meridian"
        assert [r.name for r in await repo.top_performers(session, "o1")] == [
            "Zara Iqbal"
        ]

    async def test_call_upsert_is_idempotent(self, session):
        await repo.put_call(session, a_call())
        await repo.put_call(session, a_call())
        assert len(await repo.list_calls(session, "o1")) == 1

    async def test_call_update_overwrites(self, session):
        await repo.put_call(session, a_call())
        updated = a_call()
        updated.title = "Renamed"
        await repo.put_call(session, updated)
        assert (await repo.get_call(session, "c1")).title == "Renamed"

    async def test_status_transition_persists_in_both_places(self, session):
        await repo.put_call(session, a_call())
        await repo.set_call_status(session, "c1", CallStatus.FAILED, error="boom")
        call = await repo.get_call(session, "c1")
        assert call.status is CallStatus.FAILED
        assert call.error == "boom"

    async def test_artifact_typed_round_trip(self, session):
        await repo.put_call(session, a_call())
        transcript = Transcript(
            call_id="c1",
            segments=[
                Segment(
                    id="s0001",
                    index=0,
                    speaker_id=0,
                    role=SpeakerRole.REP,
                    start_ms=0,
                    end_ms=4000,
                    text="Thanks for the time today.",
                )
            ],
        )
        await repo.put_artifact(session, "c1", repo.TRANSCRIPT, transcript)
        loaded = await repo.get_artifact(session, "c1", repo.TRANSCRIPT, Transcript)
        assert loaded.segments[0].text == "Thanks for the time today."
        assert loaded.segments[0].role is SpeakerRole.REP

    async def test_missing_artifact_returns_none(self, session):
        assert await repo.get_artifact(session, "nope", repo.METRICS, CallMetrics) is None

    async def test_artifact_overwrite_keeps_one_row(self, session):
        await repo.put_call(session, a_call())
        for duration in (1000, 2000):
            await repo.put_artifact(
                session, "c1", repo.METRICS, CallMetrics(call_id="c1", duration_ms=duration)
            )
        loaded = await repo.get_artifact(session, "c1", repo.METRICS, CallMetrics)
        assert loaded.duration_ms == 2000

    async def test_bulk_artifact_fetch(self, session):
        for i in range(3):
            await repo.put_call(session, a_call(call_id=f"c{i}"))
            await repo.put_artifact(
                session, f"c{i}", repo.METRICS, CallMetrics(call_id=f"c{i}", duration_ms=i)
            )
        found = await repo.get_artifacts_for(session, ["c0", "c2"], repo.METRICS)
        assert set(found) == {"c0", "c2"}

    async def test_list_calls_filters_by_rep(self, session):
        await repo.put_call(session, a_call(call_id="c1", rep_id="r1"))
        await repo.put_call(session, a_call(call_id="c2", rep_id="r2"))
        assert len(await repo.list_calls(session, "o1", rep_id="r2")) == 1


class TestInterruptedAnalysis:
    """What happens to a call that was being analysed when the server stopped.

    The pipeline is a background task inside the API process. When that process
    goes away mid-run -- a redeploy, an OOM, a power cut -- nothing is left to
    finish the call and nothing will ever set its status again. It sat in
    `transcribing` forever and the page showed a spinner that never resolved.

    Shipping during working hours is a routine event, so this is not an edge
    case; it is what happened every time.
    """

    async def test_a_call_stuck_transcribing_is_closed(self, session):
        stuck = a_call(call_id="c1")
        stuck.status = CallStatus.TRANSCRIBING
        await repo.put_call(session, stuck)

        closed = await repo.fail_interrupted_calls(session)

        assert closed == ["c1"]
        assert (await repo.get_call(session, "c1")).status is CallStatus.FAILED

    async def test_a_call_stuck_analyzing_is_closed(self, session):
        stuck = a_call(call_id="c1")
        stuck.status = CallStatus.ANALYZING
        await repo.put_call(session, stuck)

        assert await repo.fail_interrupted_calls(session) == ["c1"]

    async def test_the_message_tells_the_reader_what_to_do(self, session):
        """They did nothing wrong, and the recording is not lost."""
        stuck = a_call(call_id="c1")
        stuck.status = CallStatus.TRANSCRIBING
        await repo.put_call(session, stuck)
        await repo.fail_interrupted_calls(session)

        error = (await repo.get_call(session, "c1")).error
        assert "interrupted" in error.lower()
        assert "upload it again" in error.lower()

    async def test_finished_calls_are_left_alone(self, session):
        await repo.put_call(session, a_call(call_id="done"))
        failed = a_call(call_id="failed")
        failed.status = CallStatus.FAILED
        await repo.put_call(session, failed)

        assert await repo.fail_interrupted_calls(session) == []
        assert (await repo.get_call(session, "done")).status is CallStatus.READY
        assert (await repo.get_call(session, "failed")).status is CallStatus.FAILED

    async def test_it_is_safe_to_run_on_an_empty_database(self, session):
        """It runs at every startup, including the very first one."""
        assert await repo.fail_interrupted_calls(session) == []

    async def test_running_it_twice_changes_nothing_the_second_time(self, session):
        stuck = a_call(call_id="c1")
        stuck.status = CallStatus.TRANSCRIBING
        await repo.put_call(session, stuck)

        assert await repo.fail_interrupted_calls(session) == ["c1"]
        assert await repo.fail_interrupted_calls(session) == []

    async def test_several_at_once(self, session):
        for i in range(3):
            stuck = a_call(call_id=f"c{i}")
            stuck.status = CallStatus.ANALYZING
            await repo.put_call(session, stuck)
        await repo.put_call(session, a_call(call_id="fine"))

        assert sorted(await repo.fail_interrupted_calls(session)) == ["c0", "c1", "c2"]


class TestMomentSearch:
    async def _seed(self, session):
        await repo.add_moments(
            session,
            [
                {
                    "id": "m1", "org_id": "o1", "call_id": "c1", "rep_id": "r1",
                    "kind": "objection", "outcome": "won",
                    "text": "handled pricing beautifully",
                    "embedding": unit(1, 0, 0), "data": {"account": "Northwind"},
                },
                {
                    "id": "m2", "org_id": "o1", "call_id": "c2", "rep_id": "r2",
                    "kind": "objection", "outcome": "lost",
                    "text": "fumbled pricing",
                    "embedding": unit(0.95, 0.1, 0), "data": {},
                },
                {
                    "id": "m3", "org_id": "o1", "call_id": "c3", "rep_id": "r1",
                    "kind": "story", "outcome": "won",
                    "text": "a completely different topic",
                    "embedding": unit(0, 0, 1), "data": {},
                },
            ],
        )

    async def test_finds_the_semantically_closest(self, session):
        await self._seed(session)
        results = await repo.search_moments(session, "o1", unit(1, 0, 0), k=1)
        assert results[0][0]["id"] == "m1"

    async def test_outcome_filter_applies_before_scoring(self, session):
        await self._seed(session)
        results = await repo.search_moments(
            session, "o1", unit(1, 0, 0), outcome="won", k=5
        )
        assert {r[0]["id"] for r in results} == {"m1", "m3"}

    async def test_kind_filter(self, session):
        await self._seed(session)
        results = await repo.search_moments(
            session, "o1", unit(1, 0, 0), kind="story", k=5
        )
        assert [r[0]["id"] for r in results] == ["m3"]

    async def test_excluding_a_rep_removes_their_moments(self, session):
        await self._seed(session)
        results = await repo.search_moments(
            session, "o1", unit(1, 0, 0), exclude_rep_id="r1", k=5
        )
        assert all(r[0]["rep_id"] != "r1" for r in results)

    async def test_denormalised_context_survives(self, session):
        await self._seed(session)
        results = await repo.search_moments(session, "o1", unit(1, 0, 0), k=1)
        assert results[0][0]["account"] == "Northwind"

    async def test_empty_index_returns_empty(self, session):
        assert await repo.search_moments(session, "o1", unit(1, 0, 0)) == []


class TestPlayDedup:
    async def test_near_duplicate_is_matched(self, session):
        play = Play(
            id="p1", org_id="o1", name="The Compounding Cost",
            kind=PlayKind.STORY_ARC, thesis="Makes delay expensive.",
            when_to_use="On a timing objection.",
        )
        await repo.put_play(session, play, embedding=unit(1, 0, 0))
        found = await repo.nearest_play(session, "o1", unit(0.98, 0.02, 0), 0.9)
        assert found is not None and found[0].id == "p1"

    async def test_distinct_candidate_is_not_matched(self, session):
        play = Play(
            id="p1", org_id="o1", name="The Compounding Cost",
            kind=PlayKind.STORY_ARC, thesis="Makes delay expensive.",
            when_to_use="On a timing objection.",
        )
        await repo.put_play(session, play, embedding=unit(1, 0, 0))
        assert await repo.nearest_play(session, "o1", unit(0, 1, 0), 0.9) is None

    async def test_empty_library(self, session):
        assert await repo.nearest_play(session, "o1", unit(1, 0, 0), 0.9) is None

    async def test_win_rate_lift_computes(self, session):
        play = Play(
            id="p1", org_id="o1", name="X", kind=PlayKind.ANALOGY,
            thesis="t", when_to_use="w",
            win_rate_with=0.62, win_rate_without=0.31,
        )
        assert play.win_rate_lift == 0.31

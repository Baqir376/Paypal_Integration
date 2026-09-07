"""Adversarial tests for the parts most likely to break in the field.

Written to try to break things rather than to confirm they work. Categories:
degenerate input, boundary arithmetic, malformed upstream data, hostile text,
concurrency, and the invariants that must hold no matter what arrives.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from salix.agents.evidence import hydrate, prune_invalid, walk_evidence
from salix.dojo.engine import DojoEngine
from salix.metrics import analytics
from salix.metrics.engine import compute_metrics, is_question, split_sentences
from salix.metrics.scorecard import build_scorecard
from salix.providers.base import Providers
from salix.providers.mock import MockASR, MockEmbeddings, MockLLM, MockTTS
from salix.schemas.analysis import CallAnalysis, MeddicCoverage, MeddicItem
from salix.schemas.call import Call, CallStatus, Segment, Transcript
from salix.schemas.common import CallOutcome, DealStage, EvidenceRef, SkillAxis, SpeakerRole
from salix.schemas.deal import Deal
from salix.schemas.dojo import BuyerPersona, PersonaObjection
from salix.schemas.org import Org, Rep
from salix.store import repo
from salix.store.models import Base


def seg(idx, role, start, end, text="word word word"):
    return Segment(
        id=f"s{idx:04d}",
        index=idx,
        speaker_id=0 if role is SpeakerRole.REP else 1,
        role=role,
        start_ms=start,
        end_ms=end,
        text=text,
    )


REP = SpeakerRole.REP
BUYER = SpeakerRole.BUYER


@pytest_asyncio.fixture
async def session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as s:
        yield s
    await engine.dispose()


@pytest.fixture
def providers():
    return Providers(
        llm=MockLLM(), asr=MockASR(), tts=MockTTS(),
        embeddings=MockEmbeddings(), mode="mock",
    )


# ==========================================================================
# Degenerate transcripts
# ==========================================================================


class TestDegenerateTranscripts:
    """The metrics engine is fed whatever the ASR produces. It must never
    raise, and its invariants must hold for any input."""

    def test_single_segment(self):
        t = Transcript(call_id="c", segments=[seg(0, REP, 0, 5000)])
        m = compute_metrics(t)
        assert m.talk_ratio_rep == 1.0
        assert m.timeline

    def test_only_buyer_speaks(self):
        t = Transcript(call_id="c", segments=[seg(0, BUYER, 0, 9000)])
        m = compute_metrics(t)
        assert m.talk_ratio_rep == 0.0
        assert m.rep_wpm == 0.0
        assert build_scorecard(m).overall >= 0

    def test_zero_length_segments(self):
        """A zero-duration segment is malformed but must not divide by zero."""
        t = Transcript(
            call_id="c",
            segments=[seg(0, REP, 1000, 1000), seg(1, BUYER, 2000, 2000)],
        )
        m = compute_metrics(t)
        assert m.rep_talk_ms == 0
        assert m.rep_wpm == 0.0
        assert 0.0 <= m.talk_ratio_rep <= 1.0

    def test_inverted_segment_times(self):
        """end < start should not produce negative durations downstream."""
        t = Transcript(
            call_id="c",
            segments=[seg(0, REP, 5000, 1000), seg(1, BUYER, 6000, 9000)],
        )
        m = compute_metrics(t)
        assert m.rep_talk_ms >= 0
        assert m.buyer_talk_ms >= 0
        assert m.duration_ms >= 0
        assert 0.0 <= m.talk_ratio_rep <= 1.0

    def test_all_segments_identical_timestamps(self):
        t = Transcript(
            call_id="c", segments=[seg(i, REP if i % 2 else BUYER, 0, 0) for i in range(6)]
        )
        m = compute_metrics(t)
        assert m.duration_ms >= 0
        assert build_scorecard(m)

    def test_unknown_roles_only(self):
        """Diarization can fail to assign roles. Nothing should explode."""
        segments = [seg(0, REP, 0, 1000), seg(1, REP, 2000, 3000)]
        for s in segments:
            s.role = SpeakerRole.UNKNOWN
        m = compute_metrics(Transcript(call_id="c", segments=segments))
        assert m.talk_ratio_rep == 0.0
        assert m.rep_talk_ms == 0 and m.buyer_talk_ms == 0

    def test_massive_transcript_is_linear_enough(self):
        """5000 segments is a 12-hour call. Must complete quickly and stay
        bounded -- the timeline is capped regardless of input size."""
        import time

        segments = [
            seg(i, REP if i % 2 == 0 else BUYER, i * 2000, i * 2000 + 1800)
            for i in range(5000)
        ]
        started = time.monotonic()
        m = compute_metrics(Transcript(call_id="c", segments=segments))
        elapsed = time.monotonic() - started

        assert elapsed < 10.0, f"metrics took {elapsed:.1f}s on 5000 segments"
        assert len(m.timeline) <= 140, "timeline must stay bounded"
        assert len(m.monologues) <= 10
        assert len(m.interruptions) <= 25

    def test_empty_text_segments(self):
        t = Transcript(
            call_id="c",
            segments=[seg(0, REP, 0, 3000, ""), seg(1, BUYER, 4000, 7000, "   ")],
        )
        m = compute_metrics(t)
        assert m.rep_wpm == 0.0
        assert m.filler_rate_rep == 0.0

    def test_out_of_order_segments_are_sorted(self):
        t = Transcript(
            call_id="c",
            segments=[seg(1, BUYER, 10_000, 15_000), seg(0, REP, 0, 5000)],
        )
        m = compute_metrics(t)
        assert m.duration_ms == 15_000
        assert m.timeline[0].start_ms == 0


class TestInvariants:
    """Properties that must hold for every possible input."""

    @pytest.mark.parametrize("seed", range(12))
    def test_metrics_invariants_hold_for_random_input(self, seed):
        import random

        rng = random.Random(seed)
        segments = []
        cursor = 0
        for i in range(rng.randint(1, 40)):
            start = cursor + rng.randint(-500, 3000)  # allow overlaps
            end = start + rng.randint(0, 8000)
            segments.append(
                seg(
                    i,
                    REP if rng.random() < 0.5 else BUYER,
                    max(0, start),
                    max(0, end),
                    " ".join(["word"] * rng.randint(0, 30)),
                )
            )
            cursor = max(cursor, end)

        m = compute_metrics(Transcript(call_id="c", segments=segments))

        assert 0.0 <= m.talk_ratio_rep <= 1.0
        assert 0.0 <= m.open_question_ratio <= 1.0
        assert m.rep_talk_ms >= 0 and m.buyer_talk_ms >= 0
        assert m.silence_ms >= 0
        assert m.longest_monologue_ms >= 0
        assert m.patience_ms >= 0
        assert m.longest_dead_air_ms >= 0
        # Speech and silence cannot exceed the call.
        assert m.silence_ms <= m.duration_ms + 1
        for slice_ in m.timeline:
            assert 0.0 <= slice_.rep_share <= 1.0
            assert 0.0 <= slice_.energy <= 1.0
            assert slice_.end_ms >= slice_.start_ms

        card = build_scorecard(m)
        assert 0.0 <= card.overall <= 100.0
        assert all(0.0 <= a.score <= 100.0 for a in card.axes)
        assert {a.axis for a in card.axes} == set(SkillAxis)


# ==========================================================================
# Hostile text
# ==========================================================================


class TestHostileText:
    HOSTILE = [
        "<script>alert('xss')</script>",
        "'; DROP TABLE calls; --",
        "🎉" * 200,
        "a" * 20_000,
        "\x00\x01\x02 control chars",
        "\n\n\n\r\r\t\t",
        "أهلا وسهلا مرحبا",
        "{{7*7}} ${jndi:ldap://x}",
    ]

    @pytest.mark.parametrize("text", HOSTILE)
    def test_metrics_survive_hostile_text(self, text):
        t = Transcript(call_id="c", segments=[seg(0, REP, 0, 5000, text)])
        m = compute_metrics(t)
        assert m.rep_wpm >= 0
        assert build_scorecard(m)

    @pytest.mark.parametrize("text", HOSTILE)
    def test_sentence_splitting_survives(self, text):
        assert isinstance(split_sentences(text), list)

    @pytest.mark.parametrize("text", HOSTILE)
    def test_question_detection_survives(self, text):
        assert isinstance(is_question(text), bool)

    async def test_hostile_text_round_trips_through_storage(self, session):
        """Injection strings must persist and reload byte-identical."""
        await repo.put_org(session, Org(id="o1", name="<b>Org</b>"))
        call = Call(
            id="c1", org_id="o1", rep_id="r1",
            title="'; DROP TABLE calls; --",
            account="<script>alert(1)</script>",
            occurred_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        )
        await repo.put_call(session, call)
        loaded = await repo.get_call(session, "c1")
        assert loaded.title == "'; DROP TABLE calls; --"
        assert loaded.account == "<script>alert(1)</script>"

    async def test_injection_string_does_not_break_search(self, session):
        await repo.add_moments(
            session,
            [{
                "id": "m1", "org_id": "o1", "call_id": "c1", "rep_id": "r1",
                "kind": "play", "outcome": "won",
                "text": "'; DROP TABLE moments; --",
                "embedding": [0.1] * 8, "data": {},
            }],
        )
        results = await repo.search_moments(session, "o1", [0.1] * 8, k=3)
        assert len(results) == 1


# ==========================================================================
# Empty and single-item collections
# ==========================================================================


class TestEmptyStates:
    async def test_analytics_on_empty_org(self, session):
        await repo.put_org(session, Org(id="o1", name="Empty"))
        assert await analytics.load_bundles(session, "o1") == []
        assert await analytics.rep_snapshots(session, "o1") == []
        team = analytics.team_metrics([], [])
        assert team.calls_analyzed == 0
        assert team.win_rate == 0.0
        assert team.avg_talk_ratio == 0.0

    async def test_rep_with_no_calls(self, session):
        await repo.put_org(session, Org(id="o1", name="Org"))
        await repo.put_rep(session, Rep(id="r1", org_id="o1", name="Nobody"))
        snapshots = await analytics.rep_snapshots(session, "o1")
        assert len(snapshots) == 1
        assert snapshots[0].calls == 0
        assert snapshots[0].win_rate == 0.0
        assert snapshots[0].trend == []

    async def test_deal_with_no_calls_has_a_verdict(self, session, providers):
        from salix.agents.analyst import Analyst

        deal = Deal(
            id="d1", org_id="o1", name="Empty deal", account="Nobody",
            owner_id="r1", opened_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        )
        trajectory = await Analyst(providers).trajectory(session, deal)
        assert trajectory.points == []
        assert trajectory.verdict
        assert 0.0 <= trajectory.health <= 100.0

    def test_team_ceiling_with_no_data_falls_back(self):
        ceiling = analytics.team_ceiling({}, [])
        assert set(ceiling) == set(SkillAxis)
        assert all(v > 0 for v in ceiling.values())

    def test_biggest_gaps_when_rep_leads_everywhere(self):
        rep = {axis: 90.0 for axis in SkillAxis}
        ceiling = {axis: 70.0 for axis in SkillAxis}
        assert analytics.biggest_gaps(rep, ceiling) == []

    def test_axis_averages_with_no_scorecards(self):
        result = analytics.axis_averages([])
        assert set(result) == set(SkillAxis)
        assert all(v == 0.0 for v in result.values())


# ==========================================================================
# Evidence handling
# ==========================================================================


class TestEvidenceEdges:
    def _analysis(self, segment_id: str) -> CallAnalysis:
        item = MeddicItem(covered=False)
        return CallAnalysis(
            call_id="c",
            summary="s",
            headline="h",
            meddic=MeddicCoverage(
                metrics=item, economic_buyer=item, decision_criteria=item,
                decision_process=item, identify_pain=item, champion=item,
            ),
            buyer_signals=[],
            issues=[],
            strengths=[],
            commitments=[],
            objections=[],
            stages=[],
            next_step=None,
        )

    def test_hydrate_on_empty_transcript(self):
        analysis = self._analysis("s0001")
        invalid = hydrate(analysis, Transcript(call_id="c", segments=[]), "c")
        assert invalid == []

    def test_fabricated_id_is_reported_then_pruned(self):
        from salix.schemas.analysis import TalkTrackIssue
        from salix.schemas.common import Severity

        analysis = self._analysis("s0001")
        analysis.issues = [
            TalkTrackIssue(
                title="t", severity=Severity.LOW, explanation="e",
                evidence=[EvidenceRef(segment_id="s9999")], better_move="b",
            )
        ]
        transcript = Transcript(call_id="c", segments=[seg(0, REP, 0, 1000)])

        invalid = hydrate(analysis, transcript, "c")
        assert invalid == ["s9999"]

        pruned = prune_invalid(analysis, transcript)
        assert pruned == 1
        assert analysis.issues[0].evidence[0].segment_id == ""

    def test_walk_handles_deeply_nested_and_none(self):
        analysis = self._analysis("s0001")
        refs = list(walk_evidence(analysis))
        assert isinstance(refs, list)
        assert list(walk_evidence(None)) == []
        assert list(walk_evidence({"a": [None, {"b": []}]})) == []


# ==========================================================================
# Vector search
# ==========================================================================


class TestVectorEdges:
    async def test_dimension_mismatch_is_a_clear_error(self, session):
        await repo.add_moments(
            session,
            [{
                "id": "m1", "org_id": "o1", "call_id": "c1", "rep_id": "r1",
                "kind": "play", "outcome": "won", "text": "x",
                "embedding": [0.1] * 16, "data": {},
            }],
        )
        with pytest.raises(ValueError, match="does not match"):
            await repo.search_moments(session, "o1", [0.1] * 8)

    async def test_zero_vector_does_not_produce_nan(self, session):
        await repo.add_moments(
            session,
            [{
                "id": "m1", "org_id": "o1", "call_id": "c1", "rep_id": "r1",
                "kind": "play", "outcome": "won", "text": "x",
                "embedding": [0.0] * 8, "data": {},
            }],
        )
        results = await repo.search_moments(session, "o1", [0.0] * 8, k=1)
        for _, score in results:
            assert score == score, "NaN score"

    async def test_k_larger_than_corpus(self, session):
        await repo.add_moments(
            session,
            [{
                "id": "m1", "org_id": "o1", "call_id": "c1", "rep_id": "r1",
                "kind": "play", "outcome": "won", "text": "x",
                "embedding": [1.0, 0.0], "data": {},
            }],
        )
        assert len(await repo.search_moments(session, "o1", [1.0, 0.0], k=99)) == 1

    async def test_filters_that_match_nothing(self, session):
        await repo.add_moments(
            session,
            [{
                "id": "m1", "org_id": "o1", "call_id": "c1", "rep_id": "r1",
                "kind": "play", "outcome": "won", "text": "x",
                "embedding": [1.0, 0.0], "data": {},
            }],
        )
        assert await repo.search_moments(session, "o1", [1.0, 0.0], kind="nope") == []
        assert await repo.search_moments(session, "other_org", [1.0, 0.0]) == []


# ==========================================================================
# Dojo
# ==========================================================================


class TestDojoEdges:
    def _persona(self, objections=1) -> BuyerPersona:
        return BuyerPersona(
            id="p", name="A", title="T", company="C",
            disposition="d", context="c",
            objections=[
                PersonaObjection(category="price", text="too much")
                for _ in range(objections)
            ],
        )

    def test_scoring_an_empty_session(self, providers):
        engine = DojoEngine(providers)
        dojo = engine.start("r1", self._persona())
        score = engine.score(dojo)
        assert score.overall == 0.0
        assert score.verdict

    def test_scoring_a_session_with_only_rep_turns(self, providers):
        engine = DojoEngine(providers)
        dojo = engine.start("r1", self._persona())
        engine.record_turn(dojo, "rep", "Hello there", 0, 3000)
        score = engine.score(dojo)
        assert 0.0 <= score.overall <= 100.0
        assert score.talk_ratio_rep == 1.0

    def test_persona_with_no_objections_does_not_divide_by_zero(self, providers):
        engine = DojoEngine(providers)
        dojo = engine.start("r1", self._persona(objections=0))
        engine.record_turn(dojo, "rep", "What does that look like?", 0, 3000)
        engine.record_turn(dojo, "buyer", "Spreadsheets.", 3500, 6000)
        score = engine.score(dojo)
        assert score.objections_faced == 0
        assert 0.0 <= score.overall <= 100.0

    def test_turn_timings_are_monotonic_without_client_values(self, providers):
        engine = DojoEngine(providers)
        dojo = engine.start("r1", self._persona())
        for i in range(5):
            engine.record_turn(dojo, "rep" if i % 2 == 0 else "buyer", f"line {i}")
        for a, b in zip(dojo.turns, dojo.turns[1:]):
            assert b.start_ms >= a.end_ms
            assert a.end_ms > a.start_ms

    def test_bad_client_timings_are_corrected(self, providers):
        """A browser can report end before start. The transcript must stay
        coherent or the metrics engine will produce nonsense."""
        engine = DojoEngine(providers)
        dojo = engine.start("r1", self._persona())
        engine.record_turn(dojo, "rep", "hello", start_ms=5000, end_ms=1000)
        turn = dojo.turns[0]
        assert turn.end_ms > turn.start_ms

    def test_transcript_conversion_is_scorable(self, providers):
        engine = DojoEngine(providers)
        dojo = engine.start("r1", self._persona())
        engine.record_turn(dojo, "rep", "What does that look like today?", 0, 4000)
        engine.record_turn(dojo, "buyer", "It is a mess.", 4600, 8000)
        transcript = engine.to_transcript(dojo)
        metrics = compute_metrics(transcript)
        assert 0.0 <= metrics.talk_ratio_rep <= 1.0

    def test_nudges_do_not_duplicate(self, providers):
        engine = DojoEngine(providers)
        dojo = engine.start("r1", self._persona())
        engine.record_turn(dojo, "rep", "A" * 10, 0, 200_000)
        first = engine.nudges_for(dojo)
        second = engine.nudges_for(dojo)
        titles = [n.title for n in first]
        assert not (set(titles) & {n.title for n in second}), "nudge repeated on same turn"


# ==========================================================================
# Concurrency
# ==========================================================================


class TestConcurrency:
    async def test_parallel_writes_to_the_same_call(self, session):
        """Upserts must be idempotent under concurrent pipeline stages."""
        await repo.put_org(session, Org(id="o1", name="Org"))
        call = Call(
            id="c1", org_id="o1", rep_id="r1", title="T", account="A",
            occurred_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        )
        for _ in range(20):
            await repo.put_call(session, call)
        assert len(await repo.list_calls(session, "o1")) == 1

    async def test_many_bus_subscribers_all_receive(self):
        from salix.pipeline.bus import bus
        from salix.schemas.pipeline import StageKey, StageStatus

        bus.clear("multi")

        async def collect():
            return [e async for e in bus.subscribe("multi")]

        tasks = [asyncio.create_task(collect()) for _ in range(8)]
        await asyncio.sleep(0.05)
        await bus.emit("multi", StageKey.TRANSCRIBE, StageStatus.OK)
        await bus.emit("multi", StageKey.DONE, StageStatus.OK)

        results = await asyncio.gather(*tasks)
        assert all(len(r) == 2 for r in results), [len(r) for r in results]

    async def test_bus_does_not_leak_subscribers(self):
        from salix.pipeline.bus import bus
        from salix.schemas.pipeline import StageKey, StageStatus

        bus.clear("leak")
        for _ in range(5):
            await bus.emit("leak", StageKey.DONE, StageStatus.OK)
            _ = [e async for e in bus.subscribe("leak")]
        assert "leak" not in bus._subscribers or not bus._subscribers["leak"]

    async def test_bounded_history(self):
        from salix.pipeline.bus import bus
        from salix.schemas.pipeline import StageKey, StageStatus

        bus.clear("hist")
        for _ in range(400):
            await bus.emit("hist", StageKey.METRICS, StageStatus.OK)
        assert len(bus.history("hist")) <= 128


# ==========================================================================
# Providers under stress
# ==========================================================================


class TestProviderEdges:
    async def test_embedding_batching_beyond_the_limit(self):
        vectors = await MockEmbeddings().embed([f"text {i}" for i in range(57)])
        assert len(vectors) == 57

    async def test_embedding_of_empty_and_whitespace(self):
        vectors = await MockEmbeddings().embed(["", "   ", "\n"])
        assert len(vectors) == 3
        assert all(len(v) == 1024 for v in vectors)

    def test_asr_script_with_colons_in_the_text(self):
        """A line like `REP: The ratio is 43:57` must not lose its content."""
        result = MockASR.from_script("REP: The ratio is 43:57 and that matters.\n")
        assert "43:57" in result.sentences[0].text

    def test_asr_script_with_windows_line_endings(self):
        result = MockASR.from_script("REP: One.\r\nBUYER: Two.\r\n")
        assert len(result.sentences) == 2
        assert not result.sentences[0].text.endswith("\r")

    def test_asr_script_with_blank_and_comment_lines(self):
        result = MockASR.from_script("\n# comment\n\nREP: Only line.\n\n")
        assert len(result.sentences) == 1

    async def test_structured_output_never_returns_none(self):
        from salix.schemas.report import CycleReport

        result = await MockLLM().structured(system="s", user="", schema=CycleReport)
        assert result is not None

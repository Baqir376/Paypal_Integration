"""End-to-end pipeline tests.

These run the real DAG -- transcriptionist, prosodist, anatomist, playwright,
analyst -- against the offline providers and a real (in-memory) database. They
are the tests that would catch a wiring mistake between agents, which unit
tests by construction cannot.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from salix.agents.evidence import citation_coverage, walk_evidence
from salix.pipeline.bus import bus
from salix.pipeline.orchestrator import Pipeline
from salix.providers import build_providers
from salix.providers.base import Providers
from salix.providers.mock import MockASR, MockEmbeddings, MockLLM, MockTTS
from salix.schemas.analysis import CallAnalysis
from salix.schemas.call import Call, CallStatus
from salix.schemas.common import CallOutcome, DealStage, SpeakerRole
from salix.schemas.deal import Deal
from salix.schemas.org import Org, Rep
from salix.schemas.pipeline import StageKey, StageStatus
from salix.store import repo
from salix.store.models import Base

SCRIPT = """\
REP: Morning Ayesha, thanks for making the time today. Before I show you anything, what does your renewal process actually look like right now?
BUYER: Honestly it is spread across three spreadsheets and a shared inbox. Every quarter we lose a couple of renewals just because nobody noticed they were coming up.
REP: How many renewals are we talking about in a quarter?
BUYER: Around forty. Maybe two or three slip.
REP: And what is a slipped renewal worth to you?
BUYER: Call it eighteen thousand each. So we are losing maybe fifty thousand a quarter to a spreadsheet.
REP: That is the part I want to come back to. One of our customers, a logistics firm about your size, had the same shape of problem. They were not losing deals to competitors, they were losing them to nobody at all. Six months after they moved off spreadsheets their renewal rate went from eighty one percent to ninety four, and none of that came from selling harder.
BUYER: That is a good story but your pricing looks expensive for a team our size.
REP: Compared to what, though? You just told me you lose fifty thousand a quarter to missed renewals. What would you need to see to know this pays for itself?
BUYER: If it caught even one slipped renewal a quarter I would not argue about the price.
REP: Then that is the number we should test against. Who else would need to agree before you could move on something like this?
BUYER: My boss controls the budget, and our head of ops would have to actually use it.
REP: Makes sense. Can we get the three of us on a call Thursday and I will bring the model built on your forty renewals?
BUYER: Thursday works. Send an invite.
REP: I will send it this afternoon.
"""

LOSING_SCRIPT = """\
REP: Hi, thanks for taking the time. Let me walk you through our platform.
BUYER: Sure.
REP: So we have a unified dashboard, real time alerting, a full audit trail, custom reporting, role based permissions, an open API, native integrations with about forty tools, and everything is configurable per team. Our customers tell us the dashboard alone saves them hours. We also have mobile apps for both platforms, and the alerting can be routed by team, by severity, or by schedule. On top of that there is a full analytics layer with cohort analysis and retention curves, and we are shipping a forecasting module next quarter that will let you project renewals out four quarters.
BUYER: Right. We already use something for most of that.
REP: Ours is more modern though. The interface is much cleaner and the setup is faster.
BUYER: Maybe. It is probably too expensive for us anyway.
REP: I can look at discounts. Anyway, I will send over some materials.
BUYER: Okay.
"""


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
def providers() -> Providers:
    return Providers(
        llm=MockLLM(), asr=MockASR(), tts=MockTTS(),
        embeddings=MockEmbeddings(), mode="mock",
    )


class ScriptASR(MockASR):
    """Feeds a literal script into the pipeline without touching disk."""

    def __init__(self, script: str):
        super().__init__()
        self.script = script

    async def transcribe(self, audio_url, *, diarize=True, language_hints=("en",)):
        return self.from_script(self.script)


def a_call(call_id="c1", deal_id="d1", outcome=CallOutcome.WON) -> Call:
    return Call(
        id=call_id,
        org_id="o1",
        deal_id=deal_id,
        rep_id="r1",
        title="Discovery with Northwind",
        account="Northwind Logistics",
        occurred_at=datetime(2026, 3, 4, 10, 0, tzinfo=timezone.utc),
        outcome=outcome,
    )


async def seed_org(session):
    await repo.put_org(session, Org(id="o1", name="Meridian", product="Renewal ops"))
    await repo.put_rep(
        session, Rep(id="r1", org_id="o1", name="Zara Iqbal", is_top_performer=True)
    )
    await repo.put_rep(session, Rep(id="r2", org_id="o1", name="Bilal Khan"))
    await repo.put_deal(
        session,
        Deal(
            id="d1", org_id="o1", name="Northwind renewal ops",
            account="Northwind Logistics", owner_id="r1", value=64_000,
            stage=DealStage.DISCOVERY, outcome=CallOutcome.OPEN,
            opened_at=datetime(2026, 2, 1, tzinfo=timezone.utc),
            contacts=["Ayesha Rahman"],
        ),
    )


class TestFullRun:
    @pytest_asyncio.fixture
    async def result(self, session, providers):
        await seed_org(session)
        providers.asr = ScriptASR(SCRIPT)
        call = a_call()
        await repo.put_call(session, call)
        bus.clear(call.id)
        pipeline = Pipeline(providers)
        return await pipeline.run(session, call, rep_name="Zara Iqbal")

    async def test_completes(self, result):
        assert result.ok
        assert result.transcript is not None
        assert result.metrics is not None
        assert result.scorecard is not None

    async def test_roles_assigned_correctly(self, result):
        """The rep opens and asks the questions; a flipped assignment would
        invert every downstream number."""
        first = result.transcript.segments[0]
        assert first.role is SpeakerRole.REP
        assert len(result.transcript.rep_segments()) > 0
        assert len(result.transcript.buyer_segments()) > 0

    async def test_no_unknown_roles_remain(self, result):
        assert all(s.role is not SpeakerRole.UNKNOWN for s in result.transcript.segments)

    async def test_segment_ids_are_unique_and_ordered(self, result):
        ids = [s.id for s in result.transcript.segments]
        assert len(ids) == len(set(ids))
        assert ids == sorted(ids)

    async def test_metrics_are_coherent(self, result):
        m = result.metrics
        assert 0.0 < m.talk_ratio_rep < 1.0
        assert m.rep_talk_ms > 0 and m.buyer_talk_ms > 0
        assert m.rep_talk_ms + m.buyer_talk_ms + m.silence_ms <= m.duration_ms + 1
        assert m.rep_question_count > 0

    async def test_timeline_is_built(self, result):
        assert result.metrics.timeline
        assert result.metrics.timeline[-1].end_ms == result.metrics.duration_ms

    async def test_scorecard_covers_every_axis(self, result):
        from salix.schemas.common import SkillAxis

        assert {a.axis for a in result.scorecard.axes} == set(SkillAxis)

    async def test_artifacts_persisted(self, session, result):
        from salix.schemas.call import Transcript
        from salix.schemas.metrics import CallMetrics, Scorecard

        assert await repo.get_artifact(session, "c1", repo.TRANSCRIPT, Transcript)
        assert await repo.get_artifact(session, "c1", repo.METRICS, CallMetrics)
        assert await repo.get_artifact(session, "c1", repo.SCORECARD, Scorecard)

    async def test_call_marked_ready(self, session, result):
        call = await repo.get_call(session, "c1")
        assert call.status is CallStatus.READY
        assert call.duration_ms > 0

    async def test_pipeline_emitted_a_done_event(self, result):
        events = bus.history("c1")
        assert events
        assert events[-1].stage is StageKey.DONE
        assert events[-1].progress == 1.0

    async def test_stage_progress_is_monotonic(self, result):
        progress = [e.progress for e in bus.history("c1") if e.progress > 0]
        assert progress == sorted(progress)

    async def test_every_analysis_citation_resolves(self, result):
        """The core guarantee: no finding points at a segment that does not
        exist. Offline the analysis is heuristic, but the contract still holds."""
        if result.analysis is None:
            pytest.skip("anatomy unavailable")
        valid = {s.id for s in result.transcript.segments}
        for ref in walk_evidence(result.analysis):
            if ref.segment_id:
                assert ref.segment_id in valid
                assert ref.quote, "a resolved citation must carry its quote"

    async def test_citation_coverage_reported(self, result):
        if result.analysis is None:
            pytest.skip("anatomy unavailable")
        assert 0.0 <= citation_coverage(result.analysis) <= 1.0


class TestDegradation:
    """One broken agent must not take down the call."""

    async def test_transcription_failure_is_fatal_but_clean(self, session, providers):
        await seed_org(session)

        class BrokenASR(MockASR):
            async def transcribe(self, *a, **kw):
                raise RuntimeError("upstream ASR exploded")

        providers.asr = BrokenASR()
        call = a_call(call_id="c_bad")
        await repo.put_call(session, call)
        bus.clear(call.id)

        result = await Pipeline(providers).run(session, call)

        assert not result.ok
        assert "transcribe" in result.failed_stages
        stored = await repo.get_call(session, "c_bad")
        assert stored.status is CallStatus.FAILED
        assert "exploded" in stored.error

    async def test_anatomy_failure_still_yields_transcript_and_metrics(
        self, session, providers
    ):
        await seed_org(session)

        class BrokenLLM(MockLLM):
            async def structured(self, **kw):
                if kw["schema"] is CallAnalysis:
                    raise RuntimeError("model unavailable")
                return await super().structured(**kw)

        providers.asr = ScriptASR(SCRIPT)
        providers.llm = BrokenLLM()
        call = a_call(call_id="c_partial")
        await repo.put_call(session, call)
        bus.clear(call.id)

        result = await Pipeline(providers).run(session, call)

        assert result.ok
        assert result.metrics is not None
        assert result.analysis is None
        assert "anatomy" in result.failed_stages
        # The call is still usable, not failed.
        assert (await repo.get_call(session, "c_partial")).status is CallStatus.READY

    async def test_failed_stage_is_reported_on_the_bus(self, session, providers):
        await seed_org(session)

        class BrokenLLM(MockLLM):
            async def structured(self, **kw):
                if kw["schema"] is CallAnalysis:
                    raise RuntimeError("model unavailable")
                return await super().structured(**kw)

        providers.asr = ScriptASR(SCRIPT)
        providers.llm = BrokenLLM()
        call = a_call(call_id="c_evt")
        await repo.put_call(session, call)
        bus.clear(call.id)
        await Pipeline(providers).run(session, call)

        failures = [
            e for e in bus.history("c_evt") if e.status is StageStatus.FAILED
        ]
        assert any(e.stage is StageKey.ANATOMY for e in failures)


class TestContrastingCalls:
    """The measurements must actually distinguish a good call from a bad one.
    If they do not, nothing built on top of them means anything."""

    async def _run(self, session, providers, script, call_id, outcome):
        providers.asr = ScriptASR(script)
        call = a_call(call_id=call_id, outcome=outcome)
        await repo.put_call(session, call)
        bus.clear(call_id)
        return await Pipeline(providers).run(session, call, rep_name="Zara Iqbal")

    async def test_monologue_call_scores_worse_on_listening(self, session, providers):
        from salix.schemas.common import SkillAxis

        await seed_org(session)
        good = await self._run(session, providers, SCRIPT, "c_good", CallOutcome.WON)
        bad = await self._run(
            session, providers, LOSING_SCRIPT, "c_bad2", CallOutcome.LOST
        )

        assert bad.metrics.talk_ratio_rep > good.metrics.talk_ratio_rep
        assert bad.metrics.longest_monologue_ms > good.metrics.longest_monologue_ms
        assert bad.scorecard.axis(SkillAxis.LISTENING) < good.scorecard.axis(
            SkillAxis.LISTENING
        )

    async def test_discovery_call_asks_more_questions(self, session, providers):
        await seed_org(session)
        good = await self._run(session, providers, SCRIPT, "c_g2", CallOutcome.WON)
        bad = await self._run(
            session, providers, LOSING_SCRIPT, "c_b3", CallOutcome.LOST
        )
        assert good.metrics.rep_question_count > bad.metrics.rep_question_count


class TestBus:
    async def test_late_subscriber_receives_history(self):
        bus.clear("late")
        await bus.emit("late", StageKey.TRANSCRIBE, StageStatus.OK)
        await bus.emit("late", StageKey.DONE, StageStatus.OK)

        received = [e async for e in bus.subscribe("late")]
        assert [e.stage for e in received] == [StageKey.TRANSCRIBE, StageKey.DONE]

    async def test_subscription_ends_at_done(self):
        bus.clear("ends")
        await bus.emit("ends", StageKey.DONE, StageStatus.OK)
        received = [e async for e in bus.subscribe("ends")]
        assert len(received) == 1

    async def test_events_carry_agent_and_label(self):
        bus.clear("labels")
        await bus.emit("labels", StageKey.METRICS, StageStatus.RUNNING)
        event = bus.history("labels")[0]
        assert event.agent == "Prosodist"
        assert event.label == "Measuring conversation"


class TestProviderSelection:
    def test_defaults_to_mock_without_a_key(self, monkeypatch):
        monkeypatch.delenv("DASHSCOPE_API_KEY", raising=False)
        monkeypatch.delenv("SALIX_DASHSCOPE_API_KEY", raising=False)
        from salix.config import ProviderMode, Settings

        settings = Settings(provider_mode=ProviderMode.AUTO, dashscope_api_key=None)
        assert settings.resolved_mode is ProviderMode.MOCK
        assert build_providers(settings).mode == "mock"

    def test_key_switches_to_live(self):
        from salix.config import ProviderMode, Settings

        settings = Settings(provider_mode=ProviderMode.AUTO, dashscope_api_key="sk-x")
        assert settings.resolved_mode is ProviderMode.LIVE

    def test_explicit_mock_wins_over_a_present_key(self):
        from salix.config import ProviderMode, Settings

        settings = Settings(provider_mode=ProviderMode.MOCK, dashscope_api_key="sk-x")
        assert settings.resolved_mode is ProviderMode.MOCK

    def test_base_url_uses_workspace_when_set(self):
        from salix.config import Settings

        scoped = Settings(dashscope_workspace_id="llm-abc", dashscope_region="ap-southeast-1")
        assert "llm-abc.ap-southeast-1.maas.aliyuncs.com" in scoped.compatible_base_url

        shared = Settings(dashscope_workspace_id=None)
        assert "dashscope-intl.aliyuncs.com" in shared.compatible_base_url

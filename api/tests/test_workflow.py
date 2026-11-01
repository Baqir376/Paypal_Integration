# -*- coding: utf-8 -*-
"""Upload, analysis, deal score, threshold check, plan, closing test."""

from __future__ import annotations

import pytest
import pytest_asyncio

MP3 = b"\xff\xfb" + b"\x00" * 512

STRONG_CALL = """\
REP: Thanks for making the time today. What made you take this call now?
BUYER: Our renewal process is costing us about forty thousand dollars a quarter in missed renewals.
REP: How does that get decided, and who signs off on fixing it?
BUYER: I run operations, and the CFO Hina signs off. We compare on accuracy and time to value.
REP: What would good look like for you in ninety days?
BUYER: Half the missed renewals. We are very interested if this does that.
REP: A customer like you cut missed renewals by half in a quarter. Can we book a pilot review next Tuesday at ten with Hina?
BUYER: Yes, that works. I will bring Hina and send you the contract list by Friday.
"""

WEAK_CALL = """\
REP: Hi, let me tell you all about our product. It has many features and our platform is the best on the market and we help everybody do everything faster with dashboards and reports and integrations and much more.
BUYER: That is too expensive for us, honestly.
REP: It is very good value though, and our customers love it, and there are lots of features you would really like.
BUYER: We already use another tool and my boss controls the budget. I am not sure.
REP: Okay, well, thanks for your time, I will send you some information about the product at some point.
"""


@pytest_asyncio.fixture
async def world(tmp_path, monkeypatch):
    monkeypatch.setenv("SALIX_DATABASE_URL", f"sqlite+aiosqlite:///{(tmp_path / 't.db').as_posix()}")
    monkeypatch.setenv("SALIX_STORAGE_DIR", str(tmp_path / "storage"))
    monkeypatch.setenv("SALIX_PROVIDER_MODE", "mock")

    from httpx import ASGITransport, AsyncClient

    from salix.app import create_app
    from salix.config import get_settings
    from salix.providers import build_providers
    from salix.providers.mock import MockASR
    from salix.routers.deps import reset_org_cache
    from salix.schemas.org import Org
    from salix.store import db, repo, session_scope

    get_settings.cache_clear()
    await db.dispose()
    await db.init_db()
    reset_org_cache()
    async with session_scope() as session:
        await repo.put_org(session, Org(id="org_t", name="T"))

    app = create_app()
    app.state.providers = build_providers(get_settings())

    class Scripted(MockASR):
        script = STRONG_CALL

        async def transcribe(self, *args, **kwargs):
            return self.from_script(type(self).script)

    app.state.providers.asr = Scripted()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        client.asr = Scripted
        yield client

    reset_org_cache()
    await db.dispose()
    get_settings.cache_clear()


async def upload(client, script, name="Bilal"):
    client.asr.script = script
    response = await client.post(
        "/api/calls/upload",
        files={"file": ("a.mp3", MP3, "audio/mpeg")},
        data={"salesperson": name},
    )
    assert response.status_code == 202, response.text
    return response.json()


async def detail(client, body):
    return (await client.get(f"/api/calls/{body['call_id']}")).json()


def stage(body, key):
    from salix.pipeline.bus import bus

    return next(
        (e for e in reversed(bus.history(body["call_id"])) if e.stage.value == key), None
    )


class TestDealScore:
    async def test_the_strong_call_outscores_the_weak_one(self, world):
        strong = await detail(world, await upload(world, STRONG_CALL))
        weak = await detail(world, await upload(world, WEAK_CALL))
        assert strong["scorecard"]["deal"]["score"] > weak["scorecard"]["deal"]["score"] + 15
        assert strong["scorecard"]["overall"] > weak["scorecard"]["overall"]

    async def test_every_weak_score_says_why(self, world):
        weak = await detail(world, await upload(world, WEAK_CALL))
        assert weak["scorecard"]["deal"]["drivers"]
        assert weak["scorecard"]["deal"]["band"] in ("weak", "at risk")

    def _analysis(self, **overrides):
        from salix.schemas.analysis import CallAnalysis, MeddicCoverage, MeddicItem

        item = MeddicItem(covered=False)
        meddic = MeddicCoverage(
            metrics=item, economic_buyer=item, decision_criteria=item,
            decision_process=item, identify_pain=item, champion=item,
        )
        return CallAnalysis(call_id="c", summary="s", headline="h", meddic=meddic, **overrides)

    def test_no_reading_of_the_call_means_no_score(self):
        from salix.metrics.deal import score_deal

        assert score_deal(None) is None

    def test_a_dated_mutual_next_step_is_worth_most(self):
        from salix.metrics.deal import score_deal
        from salix.schemas.analysis import NextStep

        none = score_deal(self._analysis())
        vague = score_deal(self._analysis(next_step=NextStep(text="talk soon")))
        firm = score_deal(self._analysis(next_step=NextStep(text="Tue 10am", has_date=True, is_mutual=True)))
        assert none.score < vague.score < firm.score
        assert firm.score - none.score == 35
        assert any("No next step" in d for d in none.drivers)

    def test_an_open_objection_costs_more_than_a_resolved_one(self):
        from salix.metrics.deal import score_deal
        from salix.schemas.analysis import Objection
        from salix.schemas.common import EvidenceRef, ObjectionCategory

        ref = EvidenceRef(segment_id="s0", quote="q")

        def objection(handled, quality):
            return Objection(id="o", category=ObjectionCategory.PRICE, text="t", raised=ref, handled=handled, handling_quality=quality)

        resolved = score_deal(self._analysis(objections=[objection(True, 5)]))
        unresolved = score_deal(self._analysis(objections=[objection(False, 1)]))
        assert resolved.score > unresolved.score

    def test_it_stays_in_range(self):
        from salix.metrics.deal import score_deal
        from salix.schemas.analysis import BuyerSignal, NextStep
        from salix.schemas.common import EvidenceRef

        ref = EvidenceRef(segment_id="s0", quote="q")
        many = [BuyerSignal(kind="blocker", text="t", evidence=ref, weight=1.0) for _ in range(40)]
        assert 0 <= score_deal(self._analysis(buyer_signals=many)).score <= 100
        many = [BuyerSignal(kind="buying_signal", text="t", evidence=ref, weight=1.0) for _ in range(40)]
        result = score_deal(self._analysis(buyer_signals=many, next_step=NextStep(text="x", has_date=True, is_mutual=True)))
        assert 0 <= result.score <= 100


class TestThreshold:
    async def test_below_the_threshold_gets_a_plan(self, world):
        body = await upload(world, WEAK_CALL)
        assert stage(body, "coach").status.value == "ok"
        plan = (await world.get(f"/api/reps/{body['rep_id']}")).json()["coaching_plan"]
        assert plan["source_call_id"] == body["call_id"]

    async def test_above_the_threshold_gets_none(self, world, monkeypatch):
        from salix.config import get_settings

        monkeypatch.setattr(get_settings(), "coaching_threshold", 1.0)
        body = await upload(world, WEAK_CALL)
        event = stage(body, "coach")
        assert event.status.value == "skipped"
        assert "clears" in event.detail
        assert (await world.get(f"/api/reps/{body['rep_id']}")).json()["coaching_plan"] is None

    async def test_the_threshold_is_the_setting(self, world, monkeypatch):
        from salix.config import get_settings

        monkeypatch.setattr(get_settings(), "coaching_threshold", 100.0)
        body = await upload(world, STRONG_CALL)
        assert stage(body, "coach").status.value == "ok"

    async def test_a_plan_can_still_be_asked_for_after_a_good_call(self, world, monkeypatch):
        from salix.config import get_settings

        monkeypatch.setattr(get_settings(), "coaching_threshold", 1.0)
        body = await upload(world, STRONG_CALL)
        assert (await world.post(f"/api/reps/{body['rep_id']}/coach")).status_code == 200


class TestPlanIsAboutThisCall:
    async def test_it_targets_this_calls_weakest_skills(self, world):
        body = await upload(world, WEAK_CALL)
        call = await detail(world, body)
        plan = (await world.get(f"/api/reps/{body['rep_id']}")).json()["coaching_plan"]

        axes = {a["axis"]: a["score"] for a in call["scorecard"]["axes"]}
        for gap in plan["gaps"]:
            assert gap["rep_value"] == axes[gap["axis"]], "gap must quote this call's own number"
        weakest = min(axes, key=axes.get)
        assert weakest in [g["axis"] for g in plan["gaps"]]

    async def test_a_good_history_does_not_hide_a_bad_call(self, world):
        """Averaging the rep's history would let a strong record bury this call."""
        await upload(world, STRONG_CALL)
        await upload(world, STRONG_CALL)
        body = await upload(world, WEAK_CALL)
        call = await detail(world, body)
        plan = (await world.get(f"/api/reps/{body['rep_id']}")).json()["coaching_plan"]
        axes = {a["axis"]: a["score"] for a in call["scorecard"]["axes"]}
        assert all(g["rep_value"] == axes[g["axis"]] for g in plan["gaps"])

    async def test_the_model_is_told_what_happened_and_what_not_to_criticise(self, world, monkeypatch):
        from salix.agents.coach import Coach

        seen = {}
        providers = world._transport.app.state.providers
        original = providers.llm.structured

        async def spy(*, system, user, schema, **kwargs):
            if schema.__name__ == "CoachingPlan":
                seen["user"], seen["system"] = user, system
            return await original(system=system, user=user, schema=schema, **kwargs)

        monkeypatch.setattr(providers.llm, "structured", spy)
        await upload(world, WEAK_CALL)
        assert "THE CALL THIS PLAN IS FOR" in seen["user"]
        assert "Never criticise anything listed under STRONG SKILLS" in seen["system"]

    async def test_no_drill_on_a_skill_that_is_not_a_gap(self, world, monkeypatch):
        """Seen from the real model: a discovery drill for a rep scoring 80 on it."""
        from salix.schemas.coaching import Drill
        from salix.schemas.common import SkillAxis

        providers = world._transport.app.state.providers
        original = providers.llm.structured

        async def spy(*, system, user, schema, **kwargs):
            result = await original(system=system, user=user, schema=schema, **kwargs)
            if schema.__name__ == "CoachingPlan":
                # Every axis, so whichever are not gaps have to be dropped.
                result.drills = [
                    Drill(title=a.value, axis=a, instruction="i", success_criteria="s") for a in SkillAxis
                ]
            return result

        monkeypatch.setattr(providers.llm, "structured", spy)
        body = await upload(world, WEAK_CALL)
        plan = (await world.get(f"/api/reps/{body['rep_id']}")).json()["coaching_plan"]
        gaps = {g["axis"] for g in plan["gaps"]}
        assert plan["drills"] and all(d["axis"] in gaps for d in plan["drills"])

    def test_a_placeholder_score_does_not_become_the_teams_target(self):
        from salix.metrics.analytics import CallBundle, axis_averages
        from salix.schemas.common import SkillAxis as A
        from salix.schemas.metrics import AxisScore, Scorecard

        axes = [AxisScore(axis=a, score=50.0, benchmark=80.0) for a in A]
        card = Scorecard(call_id="c", overall=50.0, axes=axes)
        averages = axis_averages([CallBundle(call=None, metrics=None, scorecard=card, analysis=None)])
        assert averages[A.STORYTELLING] == 0.0 and averages[A.CLOSING] == 0.0
        assert averages[A.LISTENING] == 50.0

    def test_strong_skills_are_named_for_the_model(self):
        from salix.agents.coach import Coach
        from salix.schemas.common import SkillAxis as A

        block = Coach._strengths_block(
            [(A.CLOSING, 20.0, 80.0, 60.0)], {A.CLOSING: 20.0, A.LISTENING: 90.0, A.DISCOVERY: 40.0}
        )
        assert "listening" in block and "closing" not in block and "discovery" not in block


async def roleplay(world, script=WEAK_CALL):
    body = await upload(world, script)
    started = await world.post("/api/roleplay/start", json={"rep_id": body["rep_id"]})
    assert started.status_code == 200, started.text
    return body, started.json()


async def say(world, session, text):
    """One turn, returning the session the server hands back."""
    import json

    response = await world.post("/api/dojo/turn", json={"session": session, "text": text})
    assert response.status_code == 200, response.text
    for frame in response.text.split("\n\n"):
        if frame.startswith("event: session"):
            return json.loads(frame.split("data: ", 1)[1])
    raise AssertionError(f"no session in {response.text[:200]}")


CLOSING_LINES = [
    "What does the missed renewal problem cost you each quarter, and who decides on fixing it?",
    "That is a real number. A customer like you cut that in half, so what would you need to see?",
    "On the price objection, what are you comparing us against today, and what would make it worth it?",
    "Can we book a pilot review next Tuesday at ten with your finance lead?",
]


class TestClosingTest:
    async def test_needs_a_plan(self, world):
        await world.post("/api/reps", json={"name": "Nobody"})
        rep = (await world.get("/api/reps")).json()[0]["rep"]["id"]
        response = await world.post("/api/roleplay/start", json={"rep_id": rep})
        assert response.status_code == 409

    async def test_the_buyer_is_told_what_it_takes(self, world):
        _, started = await roleplay(world)
        session = started["session"]
        assert session["mode"] == "closing_test"
        assert session["plan_id"] == started["plan"]["id"]
        assert "WHAT IT TAKES TO WIN YOU OVER" in session["brief"]
        assert session["persona"]["difficulty"] == 3

    async def test_the_brief_reaches_the_model(self, world, monkeypatch):
        providers = world._transport.app.state.providers
        seen = {}
        original = providers.llm.stream

        async def spy(*, system, user, **kwargs):
            seen["system"] = system
            async for token in original(system=system, user=user, **kwargs):
                yield token

        monkeypatch.setattr(providers.llm, "stream", spy)
        _, started = await roleplay(world)
        await say(world, started["session"], "Hello there, what made you take this call?")
        assert "WHAT IT TAKES TO WIN YOU OVER" in seen["system"]

    async def test_a_rep_who_does_the_work_closes(self, world):
        _, started = await roleplay(world)
        session = started["session"]
        for line in CLOSING_LINES:
            session = await say(world, session, line)
        ended = (await world.post("/api/dojo/end", json={"session": session})).json()
        verdict = ended["assessment"]
        assert verdict["judged_by"] == "model"
        assert verdict["deal_closed"] is True
        assert verdict["close_evidence"]
        assert ended["score"] is not None

    async def test_a_rep_who_never_asks_does_not_close(self, world):
        _, started = await roleplay(world)
        session = started["session"]
        for line in ["Our product is great.", "It has many features you will love.", "Everyone likes it a lot."]:
            session = await say(world, session, line)
        verdict = (await world.post("/api/dojo/end", json={"session": session})).json()["assessment"]
        assert verdict["deal_closed"] is False
        assert verdict["ready"] is False

    async def test_ending_early_cannot_pass(self, world):
        _, started = await roleplay(world)
        session = await say(world, started["session"], "Can we book a call next Tuesday?")
        verdict = (await world.post("/api/dojo/end", json={"session": session})).json()["assessment"]
        assert verdict["ready"] is False and verdict["deal_closed"] is False
        assert verdict["judged_by"] == "measurements"
        assert "too short" in verdict["summary"]

    async def test_every_gap_gets_a_result(self, world):
        _, started = await roleplay(world)
        session = started["session"]
        for line in CLOSING_LINES:
            session = await say(world, session, line)
        verdict = (await world.post("/api/dojo/end", json={"session": session})).json()["assessment"]
        assert [g["axis"] for g in verdict["gaps"]] == [g["axis"] for g in started["plan"]["gaps"]]

    async def test_the_result_is_kept(self, world):
        body, started = await roleplay(world)
        session = started["session"]
        for line in CLOSING_LINES:
            session = await say(world, session, line)
        await world.post("/api/dojo/end", json={"session": session})
        profile = (await world.get(f"/api/reps/{body['rep_id']}")).json()
        assert profile["dojo_sessions"][0]["assessment"]["deal_closed"] is True

    async def test_a_practice_session_gets_no_verdict(self, world):
        body = await upload(world, WEAK_CALL)
        started = (await world.post("/api/dojo/start", json={"rep_id": body["rep_id"]})).json()
        session = await say(world, started["session"], "What made you take this call today?")
        ended = (await world.post("/api/dojo/end", json={"session": session})).json()
        assert ended["assessment"] is None and ended["mode"] == "practice"

    async def test_the_model_being_down_never_reports_a_close(self, world, monkeypatch):
        _, started = await roleplay(world)
        session = started["session"]
        for line in CLOSING_LINES:
            session = await say(world, session, line)

        providers = world._transport.app.state.providers

        async def boom(**kwargs):
            raise RuntimeError("model down")

        monkeypatch.setattr(providers.llm, "structured", boom)
        verdict = (await world.post("/api/dojo/end", json={"session": session})).json()["assessment"]
        assert verdict["judged_by"] == "measurements"
        assert verdict["deal_closed"] is False and verdict["ready"] is False


class TestTheJudgeHasToShowItsWorking:
    def _session(self):
        from salix.schemas.dojo import BuyerPersona, DojoSession, DojoTurn

        persona = BuyerPersona(id="p", name="N", title="T", company="C", disposition="d", context="c")
        lines = [
            ("rep", "What does this problem cost you every quarter?"),
            ("buyer", "About forty thousand."),
            ("rep", "Who signs off on fixing that?"),
            ("buyer", "Our CFO does."),
            ("rep", "Can we book next Tuesday at ten?"),
            ("buyer", "Yes, Tuesday at ten works for me."),
        ]
        return DojoSession(
            id="d", rep_id="r", persona=persona, mode="closing_test",
            turns=[DojoTurn(index=i, speaker=s, text=t) for i, (s, t) in enumerate(lines)],
        )

    def _plan(self):
        from salix.schemas.coaching import CoachingPlan, SkillGap
        from salix.schemas.common import SkillAxis as A

        return CoachingPlan(
            id="pl", rep_id="r", generated_at="now", diagnosis="d",
            gaps=[SkillGap(axis=A.DISCOVERY, rep_value=10, top_value=80, delta=70, explanation="e")],
        )

    async def _judge(self, verdict):
        from types import SimpleNamespace

        from salix.dojo.closing import ClosingJudge

        class LLM:
            async def structured(self, **kwargs):
                return verdict

        return await ClosingJudge(SimpleNamespace(llm=LLM(), embeddings=None, asr=None, tts=None)).assess(
            self._session(), self._plan(), {}
        )

    async def test_real_quotes_pass(self):
        from salix.schemas.common import SkillAxis as A
        from salix.schemas.dojo import ClosingVerdict, GapVerdict

        result = await self._judge(
            ClosingVerdict(
                deal_closed=True,
                close_evidence="Yes, Tuesday at ten works for me.",
                gaps=[GapVerdict(axis=A.DISCOVERY, passed=True, evidence="What does this problem cost you every quarter?")],
            )
        )
        assert result.ready and result.deal_closed

    async def test_a_quote_nobody_said_is_not_a_pass(self):
        from salix.schemas.common import SkillAxis as A
        from salix.schemas.dojo import ClosingVerdict, GapVerdict

        result = await self._judge(
            ClosingVerdict(
                deal_closed=True,
                close_evidence="Yes, Tuesday at ten works for me.",
                gaps=[GapVerdict(axis=A.DISCOVERY, passed=True, evidence="You asked brilliant questions")],
            )
        )
        assert result.gaps[0].passed is False and result.ready is False

    async def test_praise_for_an_unproven_pass_does_not_survive(self):
        """Measured on the real model: "not shown", beside "you asked three great
        questions", is a contradiction the rep cannot do anything with."""
        from salix.dojo.closing import UNPROVEN
        from salix.schemas.common import SkillAxis as A
        from salix.schemas.dojo import ClosingVerdict, GapVerdict

        result = await self._judge(
            ClosingVerdict(
                deal_closed=False,
                gaps=[GapVerdict(axis=A.DISCOVERY, passed=True, evidence="made up", feedback="Great questions!")],
            )
        )
        assert result.gaps[0].passed is False and result.gaps[0].feedback == UNPROVEN

    async def test_a_quote_from_two_lines_is_still_a_real_quote(self):
        from salix.schemas.common import SkillAxis as A
        from salix.schemas.dojo import ClosingVerdict, GapVerdict

        result = await self._judge(
            ClosingVerdict(
                deal_closed=True,
                close_evidence="Yes, Tuesday at ten works for me.",
                gaps=[
                    GapVerdict(
                        axis=A.DISCOVERY,
                        passed=True,
                        evidence="What does this problem cost you every quarter? ... Who signs off on fixing that?",
                    )
                ],
            )
        )
        assert result.gaps[0].passed is True

    async def test_a_real_line_cannot_carry_an_invented_one(self):
        from salix.dojo.closing import _said

        assert _said("Who signs off on fixing that? ... and I invented this part", ["Who signs off on fixing that?"]) is False

    async def test_an_invented_agreement_is_not_a_close(self):
        from salix.schemas.dojo import ClosingVerdict

        result = await self._judge(ClosingVerdict(deal_closed=True, close_evidence="I will sign today."))
        assert result.deal_closed is False and result.ready is False

    async def test_the_buyer_cannot_be_quoted_as_proof_of_the_reps_skill(self):
        from salix.schemas.common import SkillAxis as A
        from salix.schemas.dojo import ClosingVerdict, GapVerdict

        result = await self._judge(
            ClosingVerdict(
                deal_closed=False,
                gaps=[GapVerdict(axis=A.DISCOVERY, passed=True, evidence="Yes, Tuesday at ten works for me.")],
            )
        )
        assert result.gaps[0].passed is False

    async def test_a_skill_the_model_skipped_is_not_a_pass(self):
        from salix.schemas.dojo import ClosingVerdict

        result = await self._judge(ClosingVerdict(deal_closed=True, close_evidence="Yes, Tuesday at ten works for me.", gaps=[]))
        assert result.gaps[0].passed is False and result.ready is False

    async def test_a_trivial_quote_is_not_evidence(self):
        from salix.dojo.closing import _said

        assert _said("Who", ["Who signs off on fixing that?"]) is False
        assert _said("who signs off", ["Who signs off on fixing that?"]) is True


async def test_a_refused_voice_is_a_clean_502_not_a_crash(world, monkeypatch):
    """Microsoft's endpoint really does refuse sometimes. A malformed error here used
    to turn that into an unhandled 500 instead of the fallback the browser expects."""
    from salix.providers import edge_voice

    class Refusing:
        def __init__(self, *args, **kwargs):
            raise RuntimeError("403 from the voice service")

    monkeypatch.setattr("edge_tts.Communicate", Refusing)
    response = await world.get("/api/dojo/voice", params={"text": "hello there", "lang": "en"})
    assert response.status_code == 502
    assert "edge tts unavailable" in response.json()["detail"]
    assert edge_voice.ProviderError is not None

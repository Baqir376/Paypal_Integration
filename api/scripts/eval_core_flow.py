# -*- coding: utf-8 -*-
"""Does the real model produce scores and plans that make sense?

    python api/scripts/eval_core_flow.py [--audio path.mp3]

Runs the whole workflow on a throwaway database with the configured keys: a strong
scripted call, a weak one, optionally a real recording, then a closing test played
well and played badly. Uses real credit, so it is a script and not a test.

The output is for reading. It prints what a person needs to judge whether a plan is
about the right thing: each call's measured skills beside the plan written for it.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import pathlib
import shutil
import sys
import tempfile
from datetime import datetime, timezone

_tmp = pathlib.Path(tempfile.mkdtemp())
os.environ["SALIX_DATABASE_URL"] = f"sqlite+aiosqlite:///{(_tmp / 't.db').as_posix()}"
os.environ["SALIX_STORAGE_DIR"] = str(_tmp / "storage")

API_DIR = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(API_DIR))

from salix.config import get_settings  # noqa: E402
from salix.dojo.closing import MODE, ClosingJudge, buyer_brief  # noqa: E402
from salix.dojo.engine import DojoEngine  # noqa: E402
from salix.dojo.persona import build_persona  # noqa: E402
from salix.pipeline.orchestrator import run_in_background  # noqa: E402
from salix.providers import build_providers  # noqa: E402
from salix.providers.base import ProviderError  # noqa: E402
from salix.providers.mock import MockASR  # noqa: E402
from salix.schemas.call import Call, CallStatus  # noqa: E402
from salix.schemas.metrics import Scorecard  # noqa: E402
from salix.schemas.org import Org, Rep  # noqa: E402
from salix.store import db, repo, session_scope  # noqa: E402

STRONG = """\
REP: Thanks for making the time today. Before anything else, what made you take this call now?
BUYER: Our renewals are a mess. We missed about forty thousand dollars of renewals last quarter.
REP: Forty thousand in one quarter. How did you find out they were missed, and what did that cost your team beyond the money?
BUYER: Finance caught it a month later. My team spent two weeks reconciling spreadsheets by hand.
REP: Who else feels this, and who decides whether to fix it this year?
BUYER: I run operations, so it is my problem, but our CFO Hina signs anything over twenty thousand. She cares about audit risk.
REP: What would you judge a fix on, if you had three options in front of you?
BUYER: Accuracy first, then how fast we are live. We tried a tool last year and it took five months.
REP: That is fair. A logistics customer of ours your size was live in three weeks and cut missed renewals by half in the first quarter. Price will come up, so what are you comparing this with?
BUYER: It does look expensive next to the spreadsheet, which is free, honestly.
REP: The spreadsheet cost you forty thousand last quarter. If we only stopped half of that, does the price still feel high to you?
BUYER: No, put that way it pays for itself quickly. I would want Hina to see that number.
REP: Can we book thirty minutes next Tuesday at ten with you and Hina, and I will bring that calculation using your figures?
BUYER: Yes, Tuesday at ten works. I will invite Hina and send you last quarter's renewal list by Friday.
"""

WEAK = """\
REP: Hi, thanks for your time. So let me tell you about our platform. We are the leading renewal management solution and we have so many features, dashboards, reports, integrations, reminders, and our customers really love it. We have been in the market for years and our product is very easy to use and it can do basically everything you need it to do for your whole company.
BUYER: Okay. It sounds expensive though.
REP: No no, it is very good value for what you get, honestly, and we have lots of customers who say that, and we also have a mobile app and a really great support team who are always there for you.
BUYER: We already use spreadsheets and they mostly work. And my boss controls the budget anyway.
REP: Sure, sure, but spreadsheets are old, everyone is moving away from those, you really should look at our product because it is much better and it has all of these features I mentioned.
BUYER: I am not sure this is a priority right now.
REP: Okay, no problem at all. I will send you some information about the product and maybe we can talk sometime.
BUYER: Fine. Send it over.
"""

GOOD_ROLEPLAY = [
    "Thanks for seeing me. Before I say anything about us, what is the renewal problem actually costing you each quarter?",
    "That is a lot. Who else is affected by it, and who would sign off on fixing it this year?",
    "You mentioned price. What are you comparing this with today, and what would make the cost feel justified to you?",
    "A logistics company your size was live in three weeks and cut missed renewals in half in one quarter. If we only stopped half of yours, would the price still feel high?",
    "Can we book thirty minutes next Tuesday at ten with you and your finance lead, and I will bring that calculation using your own numbers?",
]

BAD_ROLEPLAY = [
    "Hi, our platform is the leading solution and it has so many features you will love.",
    "It is great value, honestly, everyone says so, and we have a mobile app too.",
    "Trust me, you really should buy it, it is much better than what you have.",
    "Okay, I will send you some information and maybe we can talk sometime.",
]


def show(label: str, card: Scorecard, plan) -> None:
    print(f"\n=== {label}")
    print(f"skill {card.overall} | deal {card.deal.score if card.deal else None} ({card.deal.band if card.deal else '-'})")
    print("axes  ", {a.axis.value: a.score for a in card.axes})
    print("why   ", ascii(card.deal.drivers if card.deal else card.caveats))
    if plan is None:
        print("plan   none")
        return
    print("gaps  ", [(g.axis.value, g.rep_value, g.top_value) for g in plan.gaps])
    print("plan  ", ascii(plan.diagnosis))
    print("script", len(plan.script.sections) if plan.script else None, "sections | drills", len(plan.drills))
    for drill in plan.drills[:3]:
        print("  drill", drill.axis.value, ascii(drill.title))


async def run_call(providers, org: str, rep: Rep, name: str, audio: pathlib.Path, script: str | None):
    if script is not None:
        audio.with_suffix(".txt").write_text(script, encoding="utf-8")
    call = Call(
        id=name, org_id=org, rep_id=rep.id, title=name, account="Northwind",
        occurred_at=datetime.now(timezone.utc), status=CallStatus.TRANSCRIBING,
    )
    async with session_scope() as session:
        await repo.put_call(session, call)
    await run_in_background(providers, call, audio_url=str(audio), rep_name=rep.name)
    async with session_scope() as session:
        card = await repo.get_artifact(session, name, repo.SCORECARD, Scorecard)
        plan = await repo.get_coaching_plan(session, rep.id)
    return card, plan


async def play(providers, org: str, rep: Rep, plan, lines: list[str], label: str) -> None:
    engine = DojoEngine(providers)
    async with session_scope() as session:
        persona = await build_persona(session, org, rep.id, difficulty=3)
    dojo = engine.start(rep.id, persona, "", "en")
    dojo.mode, dojo.plan_id, dojo.brief = MODE, plan.id, buyer_brief(plan)

    print(f"\n--- closing test, {label}")
    for line in lines:
        engine.record_turn(dojo, "rep", line)
        reply = "".join([t async for t in engine.buyer_reply(dojo, line)]).strip()
        engine.record_turn(dojo, "buyer", reply)
        print("  rep  :", ascii(line[:90]))
        print("  buyer:", ascii(reply[:170]))
    score = engine.score(dojo, [])
    verdict = await ClosingJudge(providers).assess(dojo, plan, dict(score.axes))
    print("  READY", verdict.ready, "| closed", verdict.deal_closed, "| by", verdict.judged_by)
    print("  close:", ascii(verdict.close_evidence[:140]))
    for gap in verdict.gaps:
        print(f"  {gap.axis.value}: {'PASS' if gap.passed else 'fail'}", ascii(gap.feedback[:120]))
    print("  next :", ascii(verdict.next_focus[:160]))


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--audio", help="a real recording to run as well")
    args = parser.parse_args()

    settings = get_settings()
    print("reasoning:", settings.llm_provider_name, settings.deep_model, "| transcription:", settings.asr_provider_name)
    await db.init_db()
    providers = build_providers(settings)
    real_asr = providers.asr
    providers.asr = MockASR()

    org = "org_eval"
    async with session_scope() as session:
        await repo.put_org(session, Org(id=org, name="Eval"))
        for rep_id, name in (("rep_a", "Asad"), ("rep_b", "Bushra"), ("rep_c", "Chand")):
            await repo.put_rep(session, Rep(id=rep_id, org_id=org, name=name))

    settings.audio_dir.mkdir(parents=True, exist_ok=True)
    asad = Rep(id="rep_a", org_id=org, name="Asad")
    bushra = Rep(id="rep_b", org_id=org, name="Bushra")

    card, plan = await run_call(providers, org, asad, "strong", settings.audio_dir / "strong.mp3", STRONG)
    show("STRONG scripted call", card, plan)
    card, weak_plan = await run_call(providers, org, bushra, "weak", settings.audio_dir / "weak.mp3", WEAK)
    show("WEAK scripted call", card, weak_plan)

    if weak_plan is not None and weak_plan.gaps:
        try:
            await play(providers, org, bushra, weak_plan, GOOD_ROLEPLAY, "played well")
            await play(providers, org, bushra, weak_plan, BAD_ROLEPLAY, "played badly")
        except ProviderError as exc:
            print("  stopped: the model refused:", str(exc)[:120])

    if args.audio:
        providers.asr = real_asr
        target = settings.audio_dir / f"real{pathlib.Path(args.audio).suffix}"
        shutil.copy(args.audio, target)
        chand = Rep(id="rep_c", org_id=org, name="Chand")
        card, plan = await run_call(providers, org, chand, "real", target, None)
        show(f"REAL recording {args.audio}", card, plan)

    await db.dispose()
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))

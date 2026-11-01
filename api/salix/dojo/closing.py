"""The closing test: can this rep now close the deal their plan was written for?

Practice and test are different things. The Dojo lets someone rehearse. This puts
them back in front of the buyer they lost ground with, armed with the coaching
plan, and answers one question at the end: would this deal have moved?

Two rules keep the answer honest.

**The buyer does not close easily.** The persona is told exactly what it needs to
hear before agreeing to anything, drawn from the rep's measured gaps, and told to
refuse until it has.

**The judge has to show its working.** Every verdict must quote what was actually
said, and each quote is checked against the session. A model's "you handled that
well" with nothing behind it does not count as a pass. If the model cannot be
reached, the measurements decide, and the result says that is what happened.
"""

from __future__ import annotations

import logging
import re

from ..agents.base import Agent
from ..metrics.scorecard import TOP_PERFORMER
from ..schemas.coaching import CoachingPlan
from ..schemas.common import SkillAxis
from ..schemas.dojo import (
    ClosingAssessment,
    ClosingVerdict,
    DojoSession,
    GapResult,
)

log = logging.getLogger("salix.dojo.closing")

#: Fewer rep turns than this is not a conversation, whatever the buyer said.
MIN_REP_TURNS = 3
MODE = "closing_test"

#: Said when the judge claimed a pass but what it quoted was not actually said.
UNPROVEN = "This could not be matched to anything you actually said, so it does not count yet."

#: What the buyer needs to hear on each weak skill before it will commit.
BUYER_NEEDS: dict[SkillAxis, str] = {
    SkillAxis.LISTENING: "the rep lets you talk, and reflects back what you actually said",
    SkillAxis.DISCOVERY: "the rep asks specific questions and learns what the problem costs you and who decides",
    SkillAxis.STORYTELLING: "the rep gives a concrete example of a similar customer and what changed for them",
    SkillAxis.OBJECTION_HANDLING: "the rep deals with the substance of your objection instead of reassuring you",
    SkillAxis.PACE_AND_PRESENCE: "the rep stays calm and does not rush or talk over you",
    SkillAxis.CLOSING: "the rep asks directly for a specific next step, with a date, that you also commit to",
}

SYSTEM = """\
You judge a sales roleplay. The salesperson was given a coaching plan and then
tried to win over a simulated buyer. Decide whether they can now close this deal.

You receive the skills the plan told them to fix, what success looks like, and the
full transcript.

`deal_closed`: true only if the BUYER explicitly agreed to a concrete next step.
A polite "sounds interesting" is not agreement. Put the buyer's exact words in
`close_evidence`, copied character for character. Empty if not closed.

`gaps`: one entry per listed skill.
- `passed`: did the salesperson actually demonstrate this skill in this session?
- `evidence`: the salesperson's exact words that prove it, copied character for
  character from one of their turns. Empty if they did not demonstrate it. Never
  paraphrase, and never quote the buyer here.
- `feedback`: one specific sentence on what they did or should have done.

`next_focus`: the single most useful thing to work on next.
`summary`: two sentences, addressed to the salesperson as "you".

Be strict. A pass means a sales manager listening in would agree.
"""


def buyer_brief(plan: CoachingPlan) -> str:
    """Added to the buyer's instructions for this session."""
    needs = [BUYER_NEEDS[g.axis] for g in plan.gaps if g.axis in BUYER_NEEDS]
    required = "\n".join(f"- {need}" for need in needs) or "- the rep earns it"
    return f"""\
WHAT IT TAKES TO WIN YOU OVER
You will only agree to a next step once you have seen all of this:
{required}

Until then, stay polite and non-committal, and if asked to commit, say what is
still missing for you, in your own words and without mentioning any list. Once
you have seen it and the rep asks for a next step, agree to it clearly and say what
you will do. If the rep never asks, do not offer.
"""


def transcript_of(session: DojoSession) -> str:
    who = {"rep": "SALESPERSON", "buyer": "BUYER"}
    return "\n".join(f"{who.get(t.speaker, t.speaker.upper())}: {t.text}" for t in session.turns)


def _normal(text: str) -> str:
    return re.sub(r"[^\w]+", " ", text.casefold(), flags=re.UNICODE).strip()


def _said(quote: str, turns: list[str]) -> bool:
    """Is this really in what was said? Punctuation and case aside.

    A model quoting more than one line joins them with an ellipsis or quote marks,
    so each piece is looked for on its own. Every piece has to be real, and a few
    words are not evidence of anything, so very short ones do not count.
    """
    pieces = [_normal(p) for p in re.split(r"\.{3}|\u2026|[\"\u201c\u201d\n]", quote)]
    pieces = [p for p in pieces if p]
    if not pieces or max(len(p) for p in pieces) < 8:
        return False
    spoken = [_normal(turn) for turn in turns]
    return all(any(p in turn for turn in spoken) for p in pieces if len(p) >= 8)


class ClosingJudge(Agent):
    name = "ClosingJudge"

    async def assess(
        self, session: DojoSession, plan: CoachingPlan, axes: dict[SkillAxis, float]
    ) -> ClosingAssessment:
        rep_turns = [t.text for t in session.turns if t.speaker == "rep"]
        buyer_turns = [t.text for t in session.turns if t.speaker == "buyer"]

        if len(rep_turns) < MIN_REP_TURNS:
            return self._measured(
                plan,
                axes,
                f"You ended after {len(rep_turns)} turn(s), which is too short to judge. "
                "Stay in the conversation and ask for a next step.",
            )

        gap_lines = "\n".join(
            f"- {g.axis.value}: {g.explanation}" for g in plan.gaps
        )
        criteria = "\n".join(
            f"- {d.axis.value}: {d.success_criteria}" for d in plan.drills
        )
        try:
            verdict = await self.llm.structured(
                system=SYSTEM,
                user=(
                    f"SKILLS TO FIX\n{gap_lines or '- none listed'}\n\n"
                    f"WHAT SUCCESS LOOKS LIKE\n{criteria or '- not specified'}\n\n"
                    f"TRANSCRIPT\n{transcript_of(session)}"
                ),
                schema=ClosingVerdict,
                temperature=0.0,
                max_tokens=2048,
            )
        except Exception as exc:  # noqa: BLE001
            log.warning("closing judge unavailable (%s); using measurements", exc)
            return self._measured(
                plan, axes, "The judge could not be reached, so this reflects the measurements only."
            )

        wanted = {g.axis for g in plan.gaps}
        results: dict[SkillAxis, GapResult] = {}
        for item in verdict.gaps:
            if item.axis not in wanted or item.axis in results:
                continue
            proven = item.passed and _said(item.evidence, rep_turns)
            results[item.axis] = GapResult(
                axis=item.axis,
                passed=proven,
                evidence=item.evidence if proven else "",
                # Its praise cannot stand beside a "not shown": the reader sees a
                # contradiction, and stops believing either half.
                feedback=(
                    UNPROVEN if item.passed and not proven else item.feedback
                ),
            )
        for gap in plan.gaps:
            results.setdefault(
                gap.axis,
                GapResult(axis=gap.axis, passed=False, feedback="Not shown in this session."),
            )

        closed = verdict.deal_closed and _said(verdict.close_evidence, buyer_turns)
        gaps = [results[g.axis] for g in plan.gaps]
        return ClosingAssessment(
            ready=closed and all(g.passed for g in gaps),
            deal_closed=closed,
            close_evidence=verdict.close_evidence if closed else "",
            gaps=gaps,
            next_focus=verdict.next_focus,
            summary=verdict.summary,
            judged_by="model",
        )

    @staticmethod
    def _measured(
        plan: CoachingPlan, axes: dict[SkillAxis, float], summary: str
    ) -> ClosingAssessment:
        """No model verdict. Skills can be measured, but nobody can say whether the
        buyer agreed, so this can never report the deal as closed."""
        gaps = [
            GapResult(
                axis=g.axis,
                passed=axes.get(g.axis, 0.0) >= TOP_PERFORMER[g.axis],
                feedback=f"Measured {axes.get(g.axis, 0.0):.0f} against a target of {TOP_PERFORMER[g.axis]:.0f}.",
            )
            for g in plan.gaps
        ]
        failing = next((g.axis.value.replace("_", " ") for g in gaps if not g.passed), "")
        return ClosingAssessment(
            ready=False,
            deal_closed=False,
            gaps=gaps,
            next_focus=f"Work on {failing}." if failing else "Ask for a dated next step.",
            summary=summary,
            judged_by="measurements",
        )

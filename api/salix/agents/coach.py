"""Coach -- turns a rep's measured gaps into a script they can actually use.

The retrieval step is what makes this different from asking a chatbot for sales
advice. For each axis where the rep trails the team, we build a query out of
their *specific* failure and search the moment index for how a colleague who
won handled the same situation. Those real passages -- with the teammate's
name, the account, and the segment they can go listen to -- are what the script
is generated from.

The consequence is that every line in the output traces back to something that
actually happened in this company. A rep can click any line and hear the person
who said it. That is the difference between a script a rep trusts and a script
a rep ignores.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from ..metrics import analytics
from ..metrics.scorecard import TOP_PERFORMER
from ..schemas.coaching import CoachingPlan, Drill, SkillGap, SourceRef
from ..schemas.common import SkillAxis
from ..schemas.org import Rep
from ..store import repo
from .base import Agent
from .playwright import KIND_CLOSE, KIND_DISCOVERY, KIND_OBJECTION, KIND_PLAY

log = logging.getLogger("salix.coach")


# What to go looking for when a rep is weak on a given axis, and which slice of
# the index is likely to hold the answer.
RETRIEVAL_PLAN: dict[SkillAxis, tuple[str, str | None]] = {
    SkillAxis.LISTENING: (
        "asking a question and letting the buyer talk, handing back the floor, "
        "short deliberate turns that draw the buyer out",
        KIND_DISCOVERY,
    ),
    SkillAxis.DISCOVERY: (
        "questions that uncover quantified business pain, the economic buyer, "
        "the decision process and what they will judge options on",
        KIND_DISCOVERY,
    ),
    SkillAxis.STORYTELLING: (
        "a customer story, an analogy or a reframe that changed how the buyer "
        "saw their own problem",
        KIND_PLAY,
    ),
    SkillAxis.OBJECTION_HANDLING: (
        "turning an objection about price, timing, risk or the incumbent into a "
        "reason to move forward",
        KIND_OBJECTION,
    ),
    SkillAxis.PACE_AND_PRESENCE: (
        "calm, unhurried delivery that leaves silence after a hard question",
        None,
    ),
    SkillAxis.CLOSING: (
        "landing a mutual next step with a date and a commitment from the buyer",
        KIND_CLOSE,
    ),
}


ROLE = """\
You are writing a coaching plan for one salesperson, using evidence from calls
their own colleagues actually ran.

You are given:
- the rep's measured shortfalls against the team ceiling, per skill
- real passages from winning calls by teammates, each with an id, the
  colleague's name, and the account

WHAT TO PRODUCE

`diagnosis` -- one sentence a sales manager would say out loud. Name the single
pattern costing this rep the most, and it must be about the FIRST shortfall listed.
Not a list, not hedged. Never criticise anything listed under STRONG SKILLS: those
numbers are measured, and a rep told the opposite stops trusting the whole plan.

`gaps` -- for each measured shortfall, an `explanation` that says what the rep
does instead of the right thing, and what it costs them. Reference their actual
numbers. "Averages 71% talk time, so buyers stop volunteering the objections
that would tell him what to fix" is right. "Could improve listening" is not.

`script` -- a script for the exact situation this rep keeps losing.
- `scenario`: name the situation in one line.
- `sections`: the phases of the conversation, each with a `purpose`.
- lines alternate `rep` and `buyer_expected`. The buyer lines are what this rep
  should be ready for, drawn from the objections that actually beat them.
- On any rep line adapted from a retrieved passage, set `source` with the
  `play_id` / `call_id` / `segment_id` / `rep_name` of the passage you used.
  This is mandatory: it is how the rep verifies the line is real.
- Write words a person would say out loud. No stage directions, no corporate
  register, no phrases like "leverage" or "circle back".

`drills` -- two or three exercises, only on the listed shortfalls. Each names a
success criterion that can be checked, and a `persona_hint` describing the buyer to
practise against.

Ground everything in the retrieved passages. If the evidence does not support a
recommendation, leave it out.
"""


#: At or above this, a skill is told to the model as one not to criticise.
STRONG_SKILL = 70.0

#: When the model cannot be reached, a rep still gets something to practise.
FALLBACK_DRILLS: dict[SkillAxis, tuple[str, str, str]] = {
    SkillAxis.LISTENING: (
        "Hand back the floor",
        "Run a discovery call and stop talking after every question, however long the silence lasts.",
        "Talk ratio under 50%, and no unbroken stretch over 60 seconds.",
    ),
    SkillAxis.DISCOVERY: (
        "Quantify the pain",
        "Before any pitch, ask open questions until the buyer has put a number on the problem and named who decides.",
        "A figure for the cost of the problem and the name of the economic buyer.",
    ),
    SkillAxis.STORYTELLING: (
        "One customer story",
        "Answer 'why you?' with a two-minute story about a similar customer, ending on the result they got.",
        "The story names a situation, a change and a measurable result.",
    ),
    SkillAxis.OBJECTION_HANDLING: (
        "Stay with the objection",
        "When the buyer objects on price, ask what it is being compared to before answering it.",
        "The objection is answered and the buyer confirms it is resolved.",
    ),
    SkillAxis.PACE_AND_PRESENCE: (
        "Leave the silence",
        "After the buyer finishes, wait a full second before replying, and slow down on the numbers.",
        "No interruptions, and at least a second before each reply.",
    ),
    SkillAxis.CLOSING: (
        "Land a mutual next step",
        "End the call with a dated next step that the buyer has also committed something to.",
        "A calendar date, and one action owned by the buyer.",
    ),
}


class Coach(Agent):
    name = "Coach"

    async def run(
        self, session: AsyncSession, org_id: str, rep: Rep, *, focus_call_id: str | None = None
    ) -> CoachingPlan:
        """`focus_call_id` writes the plan about that call's weak skills rather than
        the rep's average: a rep is coached on the call they just had."""
        bundles = await analytics.load_bundles(session, org_id, rep_id=rep.id)
        scored = [b for b in bundles if b.scorecard is not None]

        if not scored:
            return self._empty_plan(rep, "No analyzed calls yet for this rep.")

        snapshots = await analytics.rep_snapshots(session, org_id)
        mine = next((s for s in snapshots if s.rep.id == rep.id), None)
        rep_axes = mine.axes if mine else analytics.axis_averages(scored)
        ceiling = mine.team_axes if mine else {}
        focus = next((b for b in scored if b.call.id == focus_call_id), None)
        if focus is not None:
            rep_axes = {a.axis: a.score for a in focus.scorecard.axes}

        gaps = analytics.biggest_gaps(rep_axes, ceiling, limit=3)
        if not gaps:
            # Leading the team is not the same as having nothing to learn, and
            # the first rep on a new team leads it by definition: without this,
            # their first plan is an empty page. The published benchmark is the
            # bar that does not depend on who else is on the floor.
            gaps = analytics.biggest_gaps(rep_axes, TOP_PERFORMER, limit=3)
        if not gaps:
            plan = self._empty_plan(
                rep, "This rep is at or above every benchmark. Nothing to correct."
            )
            await repo.put_coaching_plan(session, org_id, plan)
            return plan

        retrieved = await self._retrieve(session, org_id, rep, gaps)
        try:
            plan = await self._generate(session, rep, bundles, gaps, retrieved, focus, rep_axes)
        except Exception as exc:  # noqa: BLE001
            # The gaps are measured and the drills need no model, so an upstream
            # failure costs the script rather than the plan.
            log.warning("coach generation failed for %s (%s); using measurements", rep.name, exc)
            plan = self._measured_plan(rep, gaps)
        # A drill on a skill the rep is already good at is advice they can see is
        # wrong. Seen from the real model: discovery at 80, and a discovery drill.
        weak = {axis for axis, _, _, _ in gaps}
        plan.drills = [d for d in plan.drills if d.axis in weak]
        if not plan.drills:
            plan.drills = self._fallback_drills(gaps)

        plan.id = f"plan_{uuid.uuid4().hex[:10]}"
        plan.rep_id = rep.id
        plan.rep_name = rep.name
        plan.generated_at = datetime.now(timezone.utc).isoformat()
        plan.source_call_id = focus.call.id if focus else None
        await repo.put_coaching_plan(session, org_id, plan)
        return plan

    # -- retrieval -------------------------------------------------------

    async def _retrieve(
        self,
        session: AsyncSession,
        org_id: str,
        rep: Rep,
        gaps: list[tuple[SkillAxis, float, float, float]],
    ) -> list[tuple[dict, float, SkillAxis]]:
        """Search the moment index once per gap.

        Two filters carry the weight: `outcome="won"` so we only learn from
        calls that actually closed, and `exclude_rep_id` so a rep is never
        taught their own habits back. MMR keeps the results genuinely
        different from each other.
        """
        found: list[tuple[dict, float, SkillAxis]] = []
        seen: set[str] = set()

        for axis, rep_value, top_value, _ in gaps:
            query, kind = RETRIEVAL_PLAN[axis]
            embedding = (await self.embeddings.embed([query]))[0]

            # Won calls first. A team new to Salix has none yet, so colleagues'
            # open calls are next best. Lost calls never: that is how a rep
            # learns the thing that lost the deal.
            results: list[tuple[dict, float]] = []
            for outcome in ("won", "open"):
                results = await repo.search_moments(
                    session,
                    org_id,
                    embedding,
                    kind=kind,
                    outcome=outcome,
                    exclude_rep_id=rep.id,
                    k=4,
                    diversify=True,
                )
                if results:
                    break
            for moment, score in results:
                if moment["id"] in seen:
                    continue
                seen.add(moment["id"])
                found.append((moment, score, axis))

        log.info(
            "coach retrieved %d moment(s) across %d gap(s) for %s",
            len(found), len(gaps), rep.name,
        )
        return found

    # -- generation ------------------------------------------------------

    async def _generate(
        self,
        session: AsyncSession,
        rep: Rep,
        bundles: list[analytics.CallBundle],
        gaps: list[tuple[SkillAxis, float, float, float]],
        retrieved: list[tuple[dict, float, SkillAxis]],
        focus: analytics.CallBundle | None = None,
        rep_axes: dict[SkillAxis, float] | None = None,
    ) -> CoachingPlan:
        rep_names = {r.id: r.name for r in await repo.list_reps(session, rep.org_id)}

        sections = [
            self._gaps_block(gaps, bundles),
            self._strengths_block(gaps, rep_axes or {}),
            self._focus_block(focus),
            self._losses_block(bundles),
            self._evidence_block(retrieved, rep_names),
        ]

        plan = await self.llm.structured(
            system=self.system_prompt(ROLE, cite=False),
            user=f"REP: {rep.name}\n\n" + "\n\n".join(s for s in sections if s),
            schema=CoachingPlan,
            # The script lines are quoted from real retrieved calls, so
            # nothing here needs inventing. A rep who regenerates their plan
            # and is told something different has been given two plans and no
            # reason to trust either.
            temperature=0.0,
            max_tokens=10000,
        )

        self._repair_gaps(plan, gaps)
        self._verify_sources(plan, retrieved, rep_names)
        plan.prescribed_play_ids = sorted(
            {m["play_id"] for m, _, _ in retrieved if m.get("play_id")}
        )
        return plan

    def _gaps_block(
        self,
        gaps: list[tuple[SkillAxis, float, float, float]],
        bundles: list[analytics.CallBundle],
    ) -> str:
        lines = ["MEASURED SHORTFALLS (0-100 scale, against the team ceiling or benchmark)"]
        for axis, rep_value, top_value, delta in gaps:
            lines.append(
                f"- {axis.value}: this rep {rep_value}, team ceiling {top_value} "
                f"(behind by {delta})"
            )

        with_metrics = [b for b in bundles if b.metrics is not None]
        if with_metrics:
            import statistics

            lines.append("")
            lines.append("THEIR AVERAGES ACROSS ANALYZED CALLS")
            lines.append(
                f"- Talk ratio: {round(statistics.fmean([b.metrics.talk_ratio_rep for b in with_metrics]) * 100)}% "
                "(top performers sit near 43%)"
            )
            lines.append(
                f"- Longest monologue: "
                f"{round(statistics.fmean([b.metrics.longest_monologue_ms for b in with_metrics]) / 1000)}s"
            )
            lines.append(
                f"- Questions per minute: "
                f"{round(statistics.fmean([b.metrics.rep_question_rate_per_min for b in with_metrics]), 2)}"
            )
            lines.append(
                f"- Pause before replying: "
                f"{round(statistics.fmean([b.metrics.patience_ms for b in with_metrics]))}ms"
            )
        return "\n".join(lines)

    @staticmethod
    def _strengths_block(
        gaps: list[tuple[SkillAxis, float, float, float]],
        rep_axes: dict[SkillAxis, float],
    ) -> str:
        weak = {axis for axis, _, _, _ in gaps}
        strong = [
            f"- {axis.value}: {value}"
            for axis, value in rep_axes.items()
            if axis not in weak and value >= STRONG_SKILL
        ]
        return "STRONG SKILLS (measured; do not criticise these)\n" + "\n".join(strong) if strong else ""

    @staticmethod
    def _focus_block(focus: analytics.CallBundle | None) -> str:
        """What actually happened on the call this plan is for."""
        if focus is None or focus.analysis is None:
            return ""
        analysis = focus.analysis
        lines = [f"THE CALL THIS PLAN IS FOR: {focus.call.title}", f"What decided it: {analysis.headline}"]
        open_ones = [o for o in analysis.objections if not o.handled]
        lines += [f'- left unresolved ({o.category.value}): "{o.text}"' for o in open_ones[:4]]
        lines += [f"- went wrong: {i.title}. {i.explanation}" for i in analysis.issues[:4]]
        lines.append(
            f"- next step: {analysis.next_step.text}" if analysis.next_step else "- no next step was agreed"
        )
        return "\n".join(lines)

    def _losses_block(self, bundles: list[analytics.CallBundle]) -> str:
        """What actually beat this rep. The script should answer these, not a
        generic set of textbook objections."""
        lost = [
            b for b in bundles
            if b.analysis is not None and b.call.outcome.value == "lost"
        ]
        if not lost:
            return ""

        lines = ["WHAT BEAT THIS REP (from their own lost calls)"]
        for bundle in lost[:5]:
            lines.append(f"- {bundle.call.account}: {bundle.analysis.headline}")
            for objection in bundle.analysis.objections:
                if not objection.handled:
                    lines.append(
                        f"    unresolved {objection.category.value}: "
                        f'"{objection.text}"'
                    )
        return "\n".join(lines)

    def _evidence_block(
        self,
        retrieved: list[tuple[dict, float, SkillAxis]],
        rep_names: dict[str, str],
    ) -> str:
        if not retrieved:
            # Told outright. The role says to leave out whatever the evidence
            # does not support, which with no evidence at all means no script.
            return (
                "NO COLLEAGUE CALLS ARE INDEXED YET\n"
                "Write the script anyway, from this rep's own measurements and "
                "objections. Set no `source` on any line: there is nothing to cite."
            )

        lines = [
            "EVIDENCE FROM WINNING CALLS BY COLLEAGUES",
            "Use these. Cite the id of any passage you draw a line from.",
            "",
        ]
        for moment, score, axis in retrieved:
            colleague = rep_names.get(moment["rep_id"], "a colleague")
            header = (
                f'[{moment["id"]}] {colleague} | {moment.get("account", "")} | '
                f"for {axis.value} | similarity {score:.2f}"
            )
            lines.append(header)
            if moment.get("play_name"):
                lines.append(f'  play: {moment["play_name"]} (id {moment["play_id"]})')
            if moment.get("objection"):
                lines.append(f'  objection: {moment["objection"]}')
            lines.append(f'  call_id: {moment["call_id"]}')
            if moment.get("segment_id"):
                lines.append(f'  segment_id: {moment["segment_id"]}')
            lines.append(f'  text: {moment["text"][:900]}')
            lines.append("")
        return "\n".join(lines)

    # -- post-conditions -------------------------------------------------

    def _repair_gaps(
        self, plan: CoachingPlan, gaps: list[tuple[SkillAxis, float, float, float]]
    ) -> None:
        """Overwrite the model's numbers with the measured ones.

        The model is asked to explain the gaps, not to restate them, and it will
        occasionally round or invent a value. The narrative is its job; the
        arithmetic is ours.
        """
        measured = {axis: (rep_v, top_v, delta) for axis, rep_v, top_v, delta in gaps}
        kept: list[SkillGap] = []

        for gap in plan.gaps:
            if gap.axis not in measured:
                continue
            rep_value, top_value, delta = measured[gap.axis]
            gap.rep_value, gap.top_value, gap.delta = rep_value, top_value, delta
            gap.severity = (
                "high" if delta >= 20 else "medium" if delta >= 10 else "low"
            )
            kept.append(gap)

        # Anything the model skipped still needs to appear.
        covered = {g.axis for g in kept}
        for axis, rep_value, top_value, delta in gaps:
            if axis in covered:
                continue
            kept.append(
                SkillGap(
                    axis=axis,
                    rep_value=rep_value,
                    top_value=top_value,
                    delta=delta,
                    severity="high" if delta >= 20 else "medium",
                    explanation=(
                        f"Trails the team ceiling on {axis.value.replace('_', ' ')} "
                        f"by {delta} points."
                    ),
                )
            )
        plan.gaps = sorted(kept, key=lambda g: -g.delta)

    def _verify_sources(
        self,
        plan: CoachingPlan,
        retrieved: list[tuple[dict, float, SkillAxis]],
        rep_names: dict[str, str],
    ) -> None:
        """Drop any source reference that does not match a retrieved passage.

        A citation the rep cannot follow is worse than no citation, so an
        unverifiable reference is removed rather than displayed.
        """
        if plan.script is None:
            return

        by_call = {m["call_id"]: m for m, _, _ in retrieved}
        # A play_id maps to *many* moments -- the same move run by different
        # reps on different calls. Collapsing them into one entry silently
        # rewrites a quote's attribution to whichever call was indexed last,
        # so the index is kept as a list and disambiguated by call below.
        by_play: dict[str, list[dict]] = {}
        for moment, _, _ in retrieved:
            if moment.get("play_id"):
                by_play.setdefault(moment["play_id"], []).append(moment)

        grounded: list[SourceRef] = []

        for section in plan.script.sections:
            for line in section.lines:
                source = line.source
                if source is None:
                    continue
                moment = self._resolve_moment(source, by_play, by_call)
                if moment is None:
                    line.source = None
                    continue
                # The resolved moment is authoritative for every field,
                # including who said it. A model that names the wrong colleague
                # must not be able to put those words in their mouth.
                source.call_id = moment["call_id"]
                source.rep_name = rep_names.get(moment["rep_id"], source.rep_name)
                source.quote = moment.get("quote") or moment["text"][:400]
                if moment.get("play_name"):
                    source.play_id = moment["play_id"]
                    source.play_name = moment["play_name"]
                if moment.get("segment_id"):
                    source.segment_id = moment["segment_id"]
                grounded.append(source)

        plan.script.grounded_in = grounded

    @staticmethod
    def _resolve_moment(
        source: SourceRef,
        by_play: dict[str, list[dict]],
        by_call: dict[str, dict],
    ) -> dict | None:
        """Find the single moment a script line was drawn from.

        A play cited without a call is ambiguous whenever more than one rep has
        run it. Rather than guess -- and risk telling a rep that Zara said
        something Daniyal said -- an unresolvable citation is dropped.
        """
        if source.play_id and source.play_id in by_play:
            candidates = by_play[source.play_id]
            if source.call_id:
                exact = next(
                    (m for m in candidates if m["call_id"] == source.call_id), None
                )
                if exact is not None:
                    return exact
            return candidates[0] if len(candidates) == 1 else None
        if source.call_id:
            return by_call.get(source.call_id)
        return None

    @staticmethod
    def _fallback_drills(gaps: list[tuple[SkillAxis, float, float, float]]) -> list[Drill]:
        drills: list[Drill] = []
        for axis, _, _, _ in gaps:
            title, instruction, success = FALLBACK_DRILLS[axis]
            drills.append(
                Drill(title=title, axis=axis, instruction=instruction, success_criteria=success)
            )
        return drills

    def _measured_plan(
        self, rep: Rep, gaps: list[tuple[SkillAxis, float, float, float]]
    ) -> CoachingPlan:
        """A plan from the numbers alone: no script, and it says why."""
        axis, rep_value, top_value, _ = gaps[0]
        plan = self._empty_plan(
            rep,
            f"Biggest gap is {axis.value.replace('_', ' ')}, at {rep_value} against "
            f"{top_value}. The written script could not be generated this time; "
            "regenerate the plan to try again.",
        )
        self._repair_gaps(plan, gaps)
        return plan

    def _empty_plan(self, rep: Rep, reason: str) -> CoachingPlan:
        return CoachingPlan(
            id=f"plan_{uuid.uuid4().hex[:10]}",
            rep_id=rep.id,
            rep_name=rep.name,
            generated_at=datetime.now(timezone.utc).isoformat(),
            diagnosis=reason,
            gaps=[],
            prescribed_play_ids=[],
            script=None,
            drills=[],
        )

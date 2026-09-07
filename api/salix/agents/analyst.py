"""Analyst -- deal trajectory, risk radar, and the end-of-cycle report.

A single call tells you how a conversation went. A deal tells you whether the
*sequence* is going anywhere, and that is where the money is. This agent chains
a deal's calls into a trajectory, detects risk with named causes, and writes the
cycle report a VP would actually forward.

Risk detection is deliberately deterministic. "This deal is at risk" is a claim
that has to survive being questioned in a pipeline review, so every risk here is
derived by rule from stored analysis -- an objection raised on call two that no
later call addresses, a deal with one contact, engagement declining across three
conversations. The language model writes the cycle narrative around those facts;
it does not decide them.
"""

from __future__ import annotations

import logging
import statistics
import uuid
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from ..metrics import analytics
from ..metrics.analytics import CallBundle
from ..schemas.common import (
    CallOutcome,
    DealStage,
    EvidenceRef,
    RiskKind,
    Severity,
)
from ..schemas.deal import Deal, DealTrajectory, Risk, TrajectoryPoint
from ..schemas.report import CycleReport, Finding, Recommendation
from ..store import repo
from .base import Agent

log = logging.getLogger("salix.analyst")

# A rep holding more than this share of the conversation, averaged across a
# deal, is a structural problem rather than one bad call.
TALK_DOMINANCE_THRESHOLD = 0.62

# Engagement must fall by at least this much across the trend for the drop to
# be called decay rather than noise.
DECAY_THRESHOLD = 0.12


ROLE = """\
You are writing the end-of-cycle report for a sales team. Your reader is a VP
who has ten minutes and needs to know what to do differently next quarter.

You are given the team's measured numbers, per-rep results, the plays that
correlate with wins, and the deals currently at risk. All of it is already
computed. Your job is to explain it, not to recount it.

`headline` -- one line, the finding of the cycle. Something a VP would forward.

`narrative` -- four or five paragraphs. Open with what actually happened to the
number and why. Name the mechanism, not the metric: if win rate fell, say what
in the conversations caused it. Name individual reps where the data supports it,
positively and negatively. Close with what changes.

`findings` -- three to five things that are true and non-obvious. Each needs a
quantified `impact` where the data supports one. A finding that restates a
metric is not a finding; the reader can already see the metric. Look for
relationships: which behaviour separates the wins from the losses.

`recommendations` -- two to four changes, in priority order. Each names an owner
and an expected effect. Specific enough to start on Monday.

Do not congratulate anyone. Do not hedge. If the cycle went badly, say so.
"""


class Analyst(Agent):
    name = "Analyst"

    # ------------------------------------------------------------------
    # Deal trajectory
    # ------------------------------------------------------------------

    async def trajectory(
        self, session: AsyncSession, deal: Deal, owner_name: str = ""
    ) -> DealTrajectory:
        calls = await repo.list_calls(session, deal.org_id, deal_id=deal.id)
        bundles = await self._bundles_for(session, calls)
        bundles.sort(key=lambda b: b.call.occurred_at)

        points = [self._point(b) for b in bundles if b.is_analyzed]
        risks = self._detect_risks(deal, bundles)
        momentum = self._momentum(points)
        health = self._health(points, risks, momentum)

        return DealTrajectory(
            deal_id=deal.id,
            deal_name=deal.name,
            account=deal.account,
            owner_name=owner_name,
            value=deal.value,
            stage=deal.stage,
            points=points,
            risks=risks,
            momentum=momentum,
            health=health,
            verdict=self._verdict(deal, points, risks, momentum, health),
        )

    async def _bundles_for(self, session: AsyncSession, calls) -> list[CallBundle]:
        if not calls:
            return []
        ids = [c.id for c in calls]
        metrics = await repo.get_artifacts_for(session, ids, repo.METRICS)
        scorecards = await repo.get_artifacts_for(session, ids, repo.SCORECARD)
        analyses = await repo.get_artifacts_for(session, ids, repo.ANALYSIS)

        from ..schemas.analysis import CallAnalysis
        from ..schemas.metrics import CallMetrics, Scorecard

        def parse(table, call_id, model):
            raw = table.get(call_id)
            return model.model_validate(raw) if raw else None

        return [
            CallBundle(
                call=c,
                metrics=parse(metrics, c.id, CallMetrics),
                scorecard=parse(scorecards, c.id, Scorecard),
                analysis=parse(analyses, c.id, CallAnalysis),
            )
            for c in calls
        ]

    def _point(self, bundle: CallBundle) -> TrajectoryPoint:
        analysis = bundle.analysis
        return TrajectoryPoint(
            call_id=bundle.call.id,
            occurred_at=bundle.call.occurred_at,
            title=bundle.call.title,
            score=bundle.scorecard.overall if bundle.scorecard else 0.0,
            buyer_engagement=self._engagement(bundle),
            open_objections=sum(
                1 for o in analysis.objections if not o.handled
            ) if analysis else 0,
            had_next_step=bool(analysis and analysis.next_step),
            meddic_coverage=analysis.meddic.coverage_ratio() if analysis else 0.0,
        )

    def _engagement(self, bundle: CallBundle) -> float:
        """How invested the buyer was, on a 0-1 scale.

        Built from three independent signals so no single one can dominate: how
        much of the call the buyer held, how readily they took the floor back,
        and how many genuine interest or concern signals they gave. A quiet
        buyer is a disengaged buyer, and it is the earliest warning a deal has.
        """
        if bundle.metrics is None:
            return 0.0

        m = bundle.metrics
        # Buyer share, scaled so the 57% benchmark reads as a full score.
        share = min(1.0, (1.0 - m.talk_ratio_rep) / 0.57)
        # Reciprocity: a conversation, not a presentation.
        reciprocity = min(1.0, m.switches_per_min / 4.0)

        signals = 0.5
        if bundle.analysis is not None:
            weighted = [
                s.weight for s in bundle.analysis.buyer_signals
                if s.kind in ("interest", "buying_signal")
            ]
            blockers = sum(
                1 for s in bundle.analysis.buyer_signals if s.kind == "blocker"
            )
            signals = min(1.0, sum(weighted) / 2.0) if weighted else 0.35
            signals = max(0.0, signals - 0.15 * blockers)

        return round(0.4 * share + 0.25 * reciprocity + 0.35 * signals, 3)

    # -- risk rules ------------------------------------------------------

    def _detect_risks(self, deal: Deal, bundles: list[CallBundle]) -> list[Risk]:
        analyzed = [b for b in bundles if b.analysis is not None]
        if not analyzed:
            return []

        risks: list[Risk] = []
        risks.extend(self._unresolved_objections(analyzed))

        latest = analyzed[-1]
        if latest.analysis.next_step is None:
            risks.append(
                Risk(
                    kind=RiskKind.NO_NEXT_STEP,
                    severity=Severity.HIGH,
                    title="No next step from the most recent call",
                    explanation=(
                        f'"{latest.call.title}" ended without an agreed next '
                        "action. Deals without a scheduled next step stall by "
                        "default rather than by decision."
                    ),
                    first_seen_call_id=latest.call.id,
                )
            )
        elif not latest.analysis.next_step.is_mutual:
            risks.append(
                Risk(
                    kind=RiskKind.NO_NEXT_STEP,
                    severity=Severity.MEDIUM,
                    title="Next step is one-sided",
                    explanation=(
                        "The rep committed to an action but the buyer committed "
                        "to nothing, so there is no evidence of buyer intent to "
                        "keep this moving."
                    ),
                    evidence=(
                        [latest.analysis.next_step.evidence]
                        if latest.analysis.next_step.evidence
                        else []
                    ),
                    first_seen_call_id=latest.call.id,
                )
            )

        if len(deal.contacts) <= 1 and len(analyzed) >= 2:
            risks.append(
                Risk(
                    kind=RiskKind.SINGLE_THREADED,
                    severity=Severity.MEDIUM,
                    title="Single-threaded after multiple calls",
                    explanation=(
                        f"{len(analyzed)} calls in and the deal still runs "
                        "through one contact. If they go quiet or leave, the "
                        "deal goes with them."
                    ),
                    first_seen_call_id=analyzed[-1].call.id,
                )
            )

        if not analyzed[-1].analysis.meddic.economic_buyer.covered:
            risks.append(
                Risk(
                    kind=RiskKind.NO_ECONOMIC_BUYER,
                    severity=Severity.HIGH if deal.value > 50_000 else Severity.MEDIUM,
                    title="Economic buyer never identified",
                    explanation=(
                        "Across every call in this deal, nobody established who "
                        "controls the budget. The rep is selling to people who "
                        "cannot say yes."
                    ),
                    first_seen_call_id=analyzed[0].call.id,
                )
            )

        risks.extend(self._momentum_risk(analyzed))
        risks.extend(self._dominance_risk(analyzed))
        return risks

    def _unresolved_objections(self, analyzed: list[CallBundle]) -> list[Risk]:
        """An objection is only a risk if *no later call* addressed it.

        Categories are used rather than exact wording, because a buyer raising
        price on call two and price again on call four is one unresolved
        concern, not two.
        """
        open_by_category: dict[str, tuple[CallBundle, object]] = {}

        for bundle in analyzed:
            for objection in bundle.analysis.objections:
                key = objection.category.value
                if objection.handled and objection.handling_quality >= 3:
                    open_by_category.pop(key, None)
                elif key not in open_by_category:
                    open_by_category[key] = (bundle, objection)

        risks: list[Risk] = []
        for category, (bundle, objection) in open_by_category.items():
            age = (analyzed[-1].call.occurred_at - bundle.call.occurred_at).days
            risks.append(
                Risk(
                    kind=RiskKind.UNRESOLVED_OBJECTION,
                    severity=Severity.HIGH if age >= 7 else Severity.MEDIUM,
                    title=f"Unresolved {category} objection",
                    explanation=(
                        f'Raised on "{bundle.call.title}" and never resolved in '
                        f"any later call: \"{objection.text}\""
                    ),
                    evidence=[objection.raised],
                    first_seen_call_id=bundle.call.id,
                    age_days=max(0, age),
                )
            )
        return risks

    def _momentum_risk(self, analyzed: list[CallBundle]) -> list[Risk]:
        if len(analyzed) < 3:
            return []
        recent = [self._engagement(b) for b in analyzed[-3:]]
        drop = recent[0] - recent[-1]
        if drop < DECAY_THRESHOLD:
            return []
        return [
            Risk(
                kind=RiskKind.MOMENTUM_DECAY,
                severity=Severity.HIGH if drop > 0.25 else Severity.MEDIUM,
                title="Buyer engagement is falling",
                explanation=(
                    f"Buyer engagement dropped from {recent[0]:.2f} to "
                    f"{recent[-1]:.2f} across the last three calls. They are "
                    "talking less and volunteering less each time."
                ),
                first_seen_call_id=analyzed[-3].call.id,
            )
        ]

    def _dominance_risk(self, analyzed: list[CallBundle]) -> list[Risk]:
        ratios = [b.metrics.talk_ratio_rep for b in analyzed if b.metrics]
        if not ratios:
            return []
        average = statistics.fmean(ratios)
        if average <= TALK_DOMINANCE_THRESHOLD:
            return []
        return [
            Risk(
                kind=RiskKind.MONOLOGUE_DOMINANCE,
                severity=Severity.MEDIUM,
                title="The rep is doing most of the talking",
                explanation=(
                    f"Across {len(ratios)} calls the rep held {round(average * 100)}% "
                    "of the conversation. At that ratio buyers stop volunteering "
                    "the objections that would reveal what is actually blocking "
                    "this deal."
                ),
                first_seen_call_id=analyzed[0].call.id,
            )
        ]

    # -- scoring ---------------------------------------------------------

    def _momentum(self, points: list[TrajectoryPoint]) -> float:
        """Slope of engagement across the last three calls, clamped to -1..1."""
        if len(points) < 2:
            return 0.0
        recent = [p.buyer_engagement for p in points[-3:]]
        return round(max(-1.0, min(1.0, (recent[-1] - recent[0]) * 2.0)), 3)

    def _health(
        self, points: list[TrajectoryPoint], risks: list[Risk], momentum: float
    ) -> float:
        if not points:
            return 50.0

        base = statistics.fmean([p.score for p in points[-3:]])
        penalty = sum(
            {
                Severity.LOW: 3.0,
                Severity.MEDIUM: 8.0,
                Severity.HIGH: 15.0,
                Severity.CRITICAL: 25.0,
            }[r.severity]
            for r in risks
        )
        return round(max(0.0, min(100.0, base + momentum * 15.0 - penalty)), 1)

    def _verdict(
        self,
        deal: Deal,
        points: list[TrajectoryPoint],
        risks: list[Risk],
        momentum: float,
        health: float,
    ) -> str:
        if deal.outcome is CallOutcome.WON:
            return "Closed won."
        if deal.outcome is CallOutcome.LOST:
            return "Closed lost."
        if not points:
            return "No analyzed calls yet."

        worst = max(risks, key=lambda r: r.severity.value, default=None)
        if health < 40 and worst is not None:
            return f"At risk. {worst.title}."
        if momentum < -0.2:
            return "Slipping. Buyer engagement is trending down."
        if health >= 70 and momentum >= 0:
            return "Healthy. Engagement holding, next step in place."
        return "Stable, but nothing is pulling it forward."

    # ------------------------------------------------------------------
    # Cycle report
    # ------------------------------------------------------------------

    async def cycle_report(
        self, session: AsyncSession, org_id: str, cycle_label: str = ""
    ) -> CycleReport:
        org = await repo.get_org(session, org_id)
        deals = await repo.list_deals(session, org_id)
        bundles = await analytics.load_bundles(session, org_id)
        snapshots = await analytics.rep_snapshots(session, org_id)
        plays = await repo.list_plays(session, org_id)

        team = analytics.team_metrics(bundles, deals)
        rows = analytics.rep_rows(snapshots)
        self._attribute_play_lift(plays, bundles, session)

        risks = await self.portfolio_risks(session, deals, snapshots)
        label = cycle_label or (org.cycle_label if org else "Current cycle")

        dates = sorted(b.call.occurred_at for b in bundles) or [
            datetime.now(timezone.utc)
        ]

        report = await self._write(
            session, org_id, label, team, rows, plays, risks, bundles
        )
        report.id = f"rpt_{uuid.uuid4().hex[:10]}"
        report.org_id = org_id
        report.cycle_label = label
        report.period_start = dates[0].date().isoformat()
        report.period_end = dates[-1].date().isoformat()
        report.team = team
        report.reps = rows
        report.risks = risks[:10]
        report.top_play_ids = [
            p.id for p in sorted(plays, key=lambda p: -p.usage_count)[:5]
        ]
        report.generated_at = datetime.now(timezone.utc).isoformat()

        await repo.put_report(session, report)
        return report

    def _attribute_play_lift(self, plays, bundles, session) -> None:
        """Fill in each play's win rate against the baseline.

        `win_rate_without` is the org's win rate on decided calls where the play
        did not appear, so the lift is a comparison against this team's own
        baseline rather than an industry number.
        """
        decided = [b for b in bundles if b.call.outcome.value in ("won", "lost")]
        if not decided:
            return

        for play in plays:
            used_in = {i.call_id for i in play.instances}
            without = [b for b in decided if b.call.id not in used_in]
            if len(without) < 2:
                continue
            won = sum(1 for b in without if b.call.outcome is CallOutcome.WON)
            play.win_rate_without = round(won / len(without), 3)

    async def portfolio_risks(self, session, deals, snapshots) -> list[Risk]:
        """The risk radar: every open deal, worst first."""
        owner_names = {s.rep.id: s.rep.name for s in snapshots}
        collected: list[Risk] = []

        for deal in deals:
            if deal.outcome is not CallOutcome.OPEN:
                continue
            trajectory = await self.trajectory(
                session, deal, owner_names.get(deal.owner_id, "")
            )
            for risk in trajectory.risks:
                risk.title = f"{deal.account}: {risk.title}"
                collected.append(risk)

        order = {
            Severity.CRITICAL: 0, Severity.HIGH: 1,
            Severity.MEDIUM: 2, Severity.LOW: 3,
        }
        return sorted(collected, key=lambda r: (order[r.severity], -r.age_days))

    async def _write(
        self, session, org_id, label, team, rows, plays, risks, bundles
    ) -> CycleReport:
        blocks = [
            f"CYCLE: {label}",
            "",
            "TEAM NUMBERS",
            f"- {team.calls_analyzed} calls analyzed ({team.hours_analyzed} hours)",
            f"- Win rate {round(team.win_rate * 100)}% across {team.deals} deals",
            f"- Closed {team.closed_value:,.0f}; open pipeline {team.pipeline_value:,.0f}",
            f"- Average talk ratio {round(team.avg_talk_ratio * 100)}% (benchmark 43%)",
            f"- Average pause before replying {round(team.avg_patience_ms)}ms",
            f"- MEDDIC coverage {round(team.avg_meddic_coverage * 100)}%",
            f"- Objections resolved {round(team.objection_resolution_rate * 100)}%",
            f"- Calls ending with a next step {round(team.next_step_rate * 100)}%",
            "",
            "PER REP",
        ]
        for row in rows:
            blocks.append(
                f"- {row.name}: score {row.overall_score}, win rate "
                f"{round(row.win_rate * 100)}% ({row.won}W/{row.lost}L), "
                f"{row.calls} calls, strongest {row.standout}, "
                f"weakest {row.watch_item}, trend {row.trend:+.1f}"
            )

        if plays:
            blocks += ["", "PLAYBOOK"]
            for play in sorted(plays, key=lambda p: -p.usage_count)[:8]:
                lift = play.win_rate_lift
                lift_text = (
                    f", win rate {round(play.win_rate_with * 100)}% vs "
                    f"{round(play.win_rate_without * 100)}% without "
                    f"({lift:+.0%} lift)"
                    if lift is not None and play.win_rate_with is not None
                    else ""
                )
                blocks.append(
                    f"- {play.name} ({play.kind.value}), used {play.usage_count}x"
                    f"{lift_text}. {play.thesis}"
                )

        if risks:
            blocks += ["", "OPEN DEALS AT RISK"]
            for risk in risks[:10]:
                blocks.append(f"- [{risk.severity.value}] {risk.title}: {risk.explanation}")

        lost = [b for b in bundles if b.call.outcome is CallOutcome.LOST and b.analysis]
        if lost:
            blocks += ["", "WHAT DECIDED THE LOSSES"]
            for bundle in lost[:8]:
                blocks.append(f"- {bundle.call.account}: {bundle.analysis.headline}")

        try:
            return await self.llm.structured(
                system=self.system_prompt(ROLE, cite=False),
                user="\n".join(blocks),
                schema=CycleReport,
                # The cycle report is an argument about a quarter that
                # already happened. Its conclusions should not depend on when
                # the button was pressed.
                temperature=0.0,
                max_tokens=10000,
            )
        except Exception as exc:  # noqa: BLE001
            # The numbers are the report; the prose is commentary. If the model
            # is unavailable we still ship a usable document.
            log.warning("cycle narrative generation failed (%s); using facts only", exc)
            return self._fallback_report(org_id, label, team, rows, risks)

    def _fallback_report(self, org_id, label, team, rows, risks) -> CycleReport:
        best = rows[0].name if rows else "nobody"
        return CycleReport(
            id="pending",
            org_id=org_id,
            cycle_label=label,
            period_start="",
            period_end="",
            headline=(
                f"{team.calls_analyzed} calls analyzed, "
                f"{round(team.win_rate * 100)}% win rate."
            ),
            narrative=(
                "Narrative generation was unavailable, so this report contains "
                "the measured results only. Every number below is computed "
                "directly from the call transcripts."
            ),
            team=team,
            reps=rows,
            findings=[
                Finding(
                    title="Talk ratio against benchmark",
                    detail=(
                        f"The team averaged {round(team.avg_talk_ratio * 100)}% "
                        "of speaking time against a 43% benchmark."
                    ),
                    impact="",
                )
            ],
            risks=risks[:10],
            recommendations=[
                Recommendation(
                    title="Review the risk radar",
                    detail=f"{len(risks)} open deals carry at least one flagged risk.",
                    owner=best,
                    priority=1,
                )
            ],
        )

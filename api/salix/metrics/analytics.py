"""Cross-call aggregation.

Everything here rolls per-call artifacts up to the rep, the deal or the team.
It is shared by the Coach (which needs to know where a rep is weak), the
Analyst (which needs the whole cycle) and the read APIs behind the dashboard,
so the leaderboard and the coaching plan can never disagree about who is doing
well.

All of it is arithmetic over stored artifacts -- one bulk query per artifact
kind, then aggregation in memory. No language model, and no N+1.
"""

from __future__ import annotations

import statistics
from typing import Optional, Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from .scorecard import TOP_PERFORMER
from ..schemas.analysis import CallAnalysis
from ..schemas.call import Call
from ..schemas.common import CallOutcome, SkillAxis
from ..schemas.deal import Deal
from ..schemas.metrics import CallMetrics, Scorecard
from ..schemas.org import Rep, RepSnapshot
from ..schemas.report import RepRow, TeamMetrics
from ..store import repo


#: The axes scored from a reading of the call rather than from a measurement of it.
NEEDS_ANALYSIS = frozenset(
    {SkillAxis.STORYTELLING, SkillAxis.OBJECTION_HANDLING, SkillAxis.CLOSING}
)


class CallBundle:
    """A call with its artifacts, loaded once and passed around."""

    __slots__ = ("call", "metrics", "scorecard", "analysis")

    def __init__(
        self,
        call: Call,
        metrics: Optional[CallMetrics],
        scorecard: Optional[Scorecard],
        analysis: Optional[CallAnalysis],
    ):
        self.call = call
        self.metrics = metrics
        self.scorecard = scorecard
        self.analysis = analysis

    @property
    def is_analyzed(self) -> bool:
        return self.metrics is not None and self.scorecard is not None


async def load_bundles(
    session: AsyncSession, org_id: str, *, rep_id: Optional[str] = None
) -> list[CallBundle]:
    """Load calls and every artifact in four queries, whatever the call count."""
    calls = await repo.list_calls(session, org_id, rep_id=rep_id, limit=1000)
    if not calls:
        return []

    ids = [c.id for c in calls]
    metrics = await repo.get_artifacts_for(session, ids, repo.METRICS)
    scorecards = await repo.get_artifacts_for(session, ids, repo.SCORECARD)
    analyses = await repo.get_artifacts_for(session, ids, repo.ANALYSIS)

    def parse(table, call_id, model):
        raw = table.get(call_id)
        return model.model_validate(raw) if raw else None

    return [
        CallBundle(
            call=call,
            metrics=parse(metrics, call.id, CallMetrics),
            scorecard=parse(scorecards, call.id, Scorecard),
            analysis=parse(analyses, call.id, CallAnalysis),
        )
        for call in calls
    ]


# --------------------------------------------------------------------------
# Rep level
# --------------------------------------------------------------------------


def axis_averages(bundles: Sequence[CallBundle]) -> dict[SkillAxis, float]:
    """Mean score per axis across a rep's analyzed calls."""
    collected: dict[SkillAxis, list[float]] = {axis: [] for axis in SkillAxis}
    for bundle in bundles:
        if bundle.scorecard is None:
            continue
        for axis_score in bundle.scorecard.axes:
            # On a call the model could not read, these are a neutral placeholder.
            # Averaged in, they set the team's target at 50 and drag on the rep.
            if bundle.analysis is None and axis_score.axis in NEEDS_ANALYSIS:
                continue
            collected[axis_score.axis].append(axis_score.score)
    return {
        axis: round(statistics.fmean(values), 1) if values else 0.0
        for axis, values in collected.items()
    }


def team_ceiling(
    by_rep: dict[str, dict[SkillAxis, float]],
    top_performer_ids: Sequence[str],
) -> dict[SkillAxis, float]:
    """The bar a struggling rep is measured against.

    Where the org has designated top performers, that is their average -- a
    real, reachable number set by colleagues rather than an abstract ideal.
    Otherwise it falls back to the best observed value per axis, and finally to
    the published benchmark when there is no data at all.
    """
    if top_performer_ids:
        # Only those with calls. A top performer with none scores zero on every
        # axis, and averaging that in drags the bar down until nobody has a gap.
        pool = [
            by_rep[r]
            for r in top_performer_ids
            if r in by_rep and any(by_rep[r].values())
        ]
        if pool:
            return {
                axis: round(statistics.fmean([p.get(axis, 0.0) for p in pool]), 1)
                for axis in SkillAxis
            }

    if by_rep:
        return {
            axis: round(max(p.get(axis, 0.0) for p in by_rep.values()), 1)
            for axis in SkillAxis
        }

    return dict(TOP_PERFORMER)


def _deal_outcomes(deals: Sequence[Deal], rep_id: str) -> tuple[int, int, int, float]:
    owned = [d for d in deals if d.owner_id == rep_id]
    won = sum(1 for d in owned if d.outcome is CallOutcome.WON)
    lost = sum(1 for d in owned if d.outcome is CallOutcome.LOST)
    revenue = sum(d.value for d in owned if d.outcome is CallOutcome.WON)
    return len(owned), won, lost, revenue


async def rep_snapshots(
    session: AsyncSession, org_id: str, *, include_archived: bool = False
) -> list[RepSnapshot]:
    """The leaderboard. Ranked by overall score, with the team ceiling attached
    so every radar chart can draw its comparison ring without another call.

    Somebody removed from the team is off the board and out of the ceiling, but
    `include_archived` still finds them: their old calls link to their profile.
    """
    everyone = await repo.list_reps(session, org_id)
    reps = [r for r in everyone if not r.archived]
    deals = await repo.list_deals(session, org_id)
    bundles = await load_bundles(session, org_id)

    by_rep: dict[str, list[CallBundle]] = {r.id: [] for r in everyone}
    for bundle in bundles:
        by_rep.setdefault(bundle.call.rep_id, []).append(bundle)

    axes_by_rep = {rep_id: axis_averages(b) for rep_id, b in by_rep.items()}
    active = {r.id for r in reps}
    ceiling = team_ceiling(
        {rep_id: axes for rep_id, axes in axes_by_rep.items() if rep_id in active},
        [r.id for r in reps if r.is_top_performer],
    )

    snapshots: list[RepSnapshot] = []
    for rep in (everyone if include_archived else reps):
        owned = by_rep.get(rep.id, [])
        scored = [b for b in owned if b.scorecard is not None]
        with_metrics = [b for b in owned if b.metrics is not None]
        deal_count, won, lost, revenue = _deal_outcomes(deals, rep.id)
        decided = won + lost

        overall = (
            round(statistics.fmean([b.scorecard.overall for b in scored]), 1)
            if scored
            else 0.0
        )

        snapshots.append(
            RepSnapshot(
                rep=rep,
                calls=len(owned),
                deals=deal_count,
                won=won,
                lost=lost,
                win_rate=round(won / decided, 3) if decided else 0.0,
                overall_score=overall,
                axes=axes_by_rep.get(rep.id, {}),
                team_axes=ceiling,
                trend=_trend(scored),
                talk_ratio=round(
                    statistics.fmean([b.metrics.talk_ratio_rep for b in with_metrics]), 3
                )
                if with_metrics
                else 0.0,
                patience_ms=round(
                    statistics.fmean([b.metrics.patience_ms for b in with_metrics]), 1
                )
                if with_metrics
                else 0.0,
            )
        )

    snapshots.sort(key=lambda s: s.overall_score, reverse=True)
    for rank, snapshot in enumerate(snapshots, start=1):
        snapshot.rank = rank
    return snapshots


def _trend(bundles: Sequence[CallBundle]) -> list[float]:
    """Overall score over time, oldest first, for the sparkline."""
    ordered = sorted(
        (b for b in bundles if b.scorecard is not None),
        key=lambda b: b.call.occurred_at,
    )
    return [b.scorecard.overall for b in ordered][-12:]


def biggest_gaps(
    rep_axes: dict[SkillAxis, float],
    ceiling: dict[SkillAxis, float],
    limit: int = 3,
) -> list[tuple[SkillAxis, float, float, float]]:
    """The axes where this rep trails the team ceiling by the most.

    Returned as (axis, rep_value, top_value, delta), worst first. Only genuine
    shortfalls are included -- an axis where the rep is at or above the ceiling
    is not a coaching opportunity.
    """
    gaps = [
        (axis, rep_axes.get(axis, 0.0), ceiling.get(axis, 0.0),
         round(ceiling.get(axis, 0.0) - rep_axes.get(axis, 0.0), 1))
        for axis in SkillAxis
    ]
    return sorted([g for g in gaps if g[3] > 0], key=lambda g: -g[3])[:limit]


# --------------------------------------------------------------------------
# Team level
# --------------------------------------------------------------------------


def team_metrics(bundles: Sequence[CallBundle], deals: Sequence[Deal]) -> TeamMetrics:
    analyzed = [b for b in bundles if b.metrics is not None]
    with_analysis = [b for b in bundles if b.analysis is not None]

    decided = [d for d in deals if d.outcome in (CallOutcome.WON, CallOutcome.LOST)]
    won = [d for d in decided if d.outcome is CallOutcome.WON]

    objections = [o for b in with_analysis for o in b.analysis.objections]
    resolved = [o for o in objections if o.handled]
    with_next_step = [b for b in with_analysis if b.analysis.next_step is not None]

    return TeamMetrics(
        calls_analyzed=len(analyzed),
        hours_analyzed=round(
            sum(b.metrics.duration_ms for b in analyzed) / 3_600_000, 1
        ),
        deals=len(deals),
        win_rate=round(len(won) / len(decided), 3) if decided else 0.0,
        pipeline_value=round(
            sum(d.value for d in deals if d.outcome is CallOutcome.OPEN), 2
        ),
        closed_value=round(sum(d.value for d in won), 2),
        avg_talk_ratio=round(
            statistics.fmean([b.metrics.talk_ratio_rep for b in analyzed]), 3
        )
        if analyzed
        else 0.0,
        avg_patience_ms=round(
            statistics.fmean([b.metrics.patience_ms for b in analyzed]), 1
        )
        if analyzed
        else 0.0,
        avg_meddic_coverage=round(
            statistics.fmean(
                [b.analysis.meddic.coverage_ratio() for b in with_analysis]
            ),
            3,
        )
        if with_analysis
        else 0.0,
        objection_resolution_rate=round(len(resolved) / len(objections), 3)
        if objections
        else 0.0,
        next_step_rate=round(len(with_next_step) / len(with_analysis), 3)
        if with_analysis
        else 0.0,
    )


def rep_rows(snapshots: Sequence[RepSnapshot]) -> list[RepRow]:
    """Leaderboard rows for the cycle report."""
    rows: list[RepRow] = []
    for snapshot in snapshots:
        rep: Rep = snapshot.rep
        weakest = min(snapshot.axes.items(), key=lambda kv: kv[1], default=(None, 0.0))
        strongest = max(snapshot.axes.items(), key=lambda kv: kv[1], default=(None, 0.0))
        rows.append(
            RepRow(
                rep_id=rep.id,
                name=rep.name,
                calls=snapshot.calls,
                deals=snapshot.deals,
                won=snapshot.won,
                lost=snapshot.lost,
                win_rate=snapshot.win_rate,
                revenue=rep.attained,
                overall_score=snapshot.overall_score,
                axes=snapshot.axes,
                trend=round(snapshot.trend[-1] - snapshot.trend[0], 1)
                if len(snapshot.trend) > 1
                else 0.0,
                standout=strongest[0].value if strongest[0] else "",
                watch_item=weakest[0].value if weakest[0] else "",
            )
        )
    return rows

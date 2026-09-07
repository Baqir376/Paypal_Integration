"""Metrics translated into the six-axis rep radar.

Kept deliberately separate from `engine.py`: the engine produces facts, this
module produces opinions about them. Retuning a benchmark should never require
touching measurement code, and every score carries plain-language `drivers` so
a rep is never shown a number without being told what moved it.

Three axes (listening, discovery, pace) are fully deterministic. Three
(storytelling, objection handling, closing) need the Anatomist's reading of the
call; when no analysis is available they return a neutral 50 and say so rather
than inventing a number.
"""

from __future__ import annotations

from typing import Optional

from ..schemas.analysis import CallAnalysis
from ..schemas.common import SkillAxis
from ..schemas.metrics import AxisScore, CallMetrics, Scorecard
from . import benchmarks as B

# What a top performer looks like on each axis. Used as the comparison ring on
# the radar chart, not as a pass mark.
TOP_PERFORMER: dict[SkillAxis, float] = {
    SkillAxis.LISTENING: 88.0,
    SkillAxis.DISCOVERY: 85.0,
    SkillAxis.STORYTELLING: 82.0,
    SkillAxis.OBJECTION_HANDLING: 84.0,
    SkillAxis.PACE_AND_PRESENCE: 86.0,
    SkillAxis.CLOSING: 83.0,
}

AXIS_WEIGHTS: dict[SkillAxis, float] = {
    SkillAxis.LISTENING: 0.18,
    SkillAxis.DISCOVERY: 0.20,
    SkillAxis.STORYTELLING: 0.15,
    SkillAxis.OBJECTION_HANDLING: 0.18,
    SkillAxis.PACE_AND_PRESENCE: 0.12,
    SkillAxis.CLOSING: 0.17,
}


def _clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, value))


def _band(value: float, ideal: float, tolerance: float, falloff: float) -> float:
    """Score a value that has a sweet spot rather than a direction.

    Inside `ideal +/- tolerance` scores 100; beyond that it decays linearly,
    reaching 0 once the deviation exceeds `tolerance + falloff`.
    """
    deviation = abs(value - ideal)
    if deviation <= tolerance:
        return 100.0
    excess = deviation - tolerance
    return _clamp(100.0 * (1.0 - excess / falloff))


def _range_band(value: float, low: float, high: float, falloff: float) -> float:
    """Like `_band` but for an acceptable interval rather than a point."""
    if low <= value <= high:
        return 100.0
    excess = (low - value) if value < low else (value - high)
    return _clamp(100.0 * (1.0 - excess / falloff))


# --------------------------------------------------------------------------
# Deterministic axes
# --------------------------------------------------------------------------


def score_listening(m: CallMetrics) -> AxisScore:
    drivers: list[str] = []

    ratio = _band(m.talk_ratio_rep, B.TALK_RATIO_TARGET, B.TALK_RATIO_TOLERANCE, 0.30)
    pct = round(m.talk_ratio_rep * 100)
    if m.talk_ratio_rep > B.TALK_RATIO_TARGET + B.TALK_RATIO_TOLERANCE:
        drivers.append(f"Spoke {pct}% of the call; top performers sit near 43%")
    elif m.talk_ratio_rep < B.TALK_RATIO_TARGET - B.TALK_RATIO_TOLERANCE:
        drivers.append(f"Spoke only {pct}%; the buyer was left to drive")
    else:
        drivers.append(f"Talk ratio {pct}% is on benchmark")

    mono = _range_band(m.longest_monologue_ms, 0, B.MONOLOGUE_WARN_MS, 90_000)
    if m.longest_monologue_ms > B.MONOLOGUE_WARN_MS:
        drivers.append(
            f"Longest unbroken stretch ran {m.longest_monologue_ms // 1000}s"
        )

    interrupt_penalty = min(30.0, m.interruptions_by_rep * 7.5)
    if m.interruptions_by_rep:
        drivers.append(f"Talked over the buyer {m.interruptions_by_rep}x")

    score = _clamp(0.55 * ratio + 0.45 * mono - interrupt_penalty)
    return AxisScore(
        axis=SkillAxis.LISTENING,
        score=round(score, 1),
        benchmark=TOP_PERFORMER[SkillAxis.LISTENING],
        drivers=drivers,
    )


def score_discovery(m: CallMetrics, analysis: Optional[CallAnalysis]) -> AxisScore:
    drivers: list[str] = []

    rate = _range_band(
        m.rep_question_rate_per_min, B.QUESTION_RATE_FLOOR, 4.0, 2.0
    )
    drivers.append(
        f"{m.rep_question_count} questions ({m.rep_question_rate_per_min}/min)"
    )

    openness = _clamp(m.open_question_ratio / B.OPEN_QUESTION_TARGET * 100)
    if m.open_question_ratio < B.OPEN_QUESTION_TARGET:
        drivers.append(
            f"Only {round(m.open_question_ratio * 100)}% were open questions"
        )

    if analysis is not None:
        coverage = analysis.meddic.coverage_ratio()
        meddic = coverage * 100
        missing = [
            name
            for name, item in (
                ("metrics", analysis.meddic.metrics),
                ("economic buyer", analysis.meddic.economic_buyer),
                ("decision criteria", analysis.meddic.decision_criteria),
                ("decision process", analysis.meddic.decision_process),
                ("pain", analysis.meddic.identify_pain),
                ("champion", analysis.meddic.champion),
            )
            if not item.covered
        ]
        if missing:
            drivers.append("MEDDIC gaps: " + ", ".join(missing))
        score = 0.35 * rate + 0.25 * openness + 0.40 * meddic
    else:
        score = 0.6 * rate + 0.4 * openness

    return AxisScore(
        axis=SkillAxis.DISCOVERY,
        score=round(_clamp(score), 1),
        benchmark=TOP_PERFORMER[SkillAxis.DISCOVERY],
        drivers=drivers,
    )


#: How the pace driver names a language, when it is worth naming.
_LANGUAGE_LABEL = {"ur": "Urdu", "ur-roman": "Roman Urdu"}


def score_pace(m: CallMetrics) -> AxisScore:
    drivers: list[str] = []

    # Words per minute is not comparable across languages, and the correction
    # for that is only as good as the corpus behind it. Where there is no
    # calibrated band the rate is reported but not scored -- see
    # benchmarks.PACE_CALIBRATED for why.
    low, high = B.wpm_band(m.language)
    label = _LANGUAGE_LABEL.get(m.language)
    exact = B.pace_is_scored(m.language)
    if exact:
        wpm = _range_band(m.rep_wpm, low, high, 60.0)
    else:
        # No calibrated band for this language, so the term is credited in
        # full rather than guessed at -- 100 on the same 0-100 scale
        # `_range_band` returns. See benchmarks.PACE_RATIO_BOUNDS for why every
        # estimate was rejected.
        wpm = 100.0
    if not exact:
        drivers.append(
            f"Delivery at {m.rep_wpm} wpm, not scored — the pace benchmark is "
            f"not calibrated for {label or m.language}"
        )
    elif m.rep_wpm > high:
        drivers.append(f"Spoke fast at {m.rep_wpm} wpm")
    elif m.rep_wpm and m.rep_wpm < low:
        drivers.append(f"Spoke slowly at {m.rep_wpm} wpm")
    else:
        drivers.append(f"Delivery paced at {m.rep_wpm} wpm")

    patience = _range_band(
        m.patience_ms, B.PATIENCE_FLOOR_MS, B.PATIENCE_CEILING_MS, 700.0
    )
    if m.patience_ms < B.PATIENCE_FLOOR_MS:
        drivers.append(
            f"Jumped in {round(m.patience_ms)}ms after the buyer stopped"
        )

    filler = _range_band(m.filler_rate_rep, 0.0, B.FILLER_RATE_GOOD, 6.0)
    if m.filler_rate_rep > B.FILLER_RATE_GOOD:
        drivers.append(f"Filler words at {m.filler_rate_rep} per 100")

    score = 0.35 * wpm + 0.40 * patience + 0.25 * filler
    return AxisScore(
        axis=SkillAxis.PACE_AND_PRESENCE,
        score=round(_clamp(score), 1),
        benchmark=TOP_PERFORMER[SkillAxis.PACE_AND_PRESENCE],
        drivers=drivers,
    )


# --------------------------------------------------------------------------
# Analysis-dependent axes
# --------------------------------------------------------------------------


def _neutral(axis: SkillAxis, reason: str) -> AxisScore:
    return AxisScore(
        axis=axis,
        score=50.0,
        benchmark=TOP_PERFORMER[axis],
        drivers=[reason],
    )


def score_objection_handling(analysis: Optional[CallAnalysis]) -> AxisScore:
    axis = SkillAxis.OBJECTION_HANDLING
    if analysis is None:
        return _neutral(axis, "Awaiting call analysis")
    if not analysis.objections:
        return AxisScore(
            axis=axis,
            score=70.0,
            benchmark=TOP_PERFORMER[axis],
            drivers=["No objections surfaced -- either a clean fit or shallow probing"],
        )

    drivers: list[str] = []
    handled = [o for o in analysis.objections if o.handled]
    quality = sum(o.handling_quality for o in analysis.objections) / (
        5.0 * len(analysis.objections)
    )
    resolution = len(handled) / len(analysis.objections)

    drivers.append(
        f"{len(handled)} of {len(analysis.objections)} objections addressed"
    )
    unresolved = [o for o in analysis.objections if not o.handled]
    if unresolved:
        drivers.append("Left open: " + ", ".join(o.category.value for o in unresolved))

    score = 100.0 * (0.45 * resolution + 0.55 * quality)
    return AxisScore(
        axis=axis,
        score=round(_clamp(score), 1),
        benchmark=TOP_PERFORMER[axis],
        drivers=drivers,
    )


def score_storytelling(
    analysis: Optional[CallAnalysis], plays_landed: int
) -> AxisScore:
    axis = SkillAxis.STORYTELLING
    if analysis is None:
        return _neutral(axis, "Awaiting call analysis")

    drivers: list[str] = []
    # Landing narrative plays is the strongest available signal; three in a call
    # is what the top performers in the seed corpus manage.
    play_component = _clamp(plays_landed / 3.0 * 100)
    if plays_landed:
        drivers.append(f"Landed {plays_landed} narrative play(s)")
    else:
        drivers.append("No recognisable narrative move -- pitched features, not a story")

    strength_component = _clamp(len(analysis.strengths) / 3.0 * 100)
    issue_penalty = min(25.0, len(analysis.issues) * 6.0)

    score = 0.6 * play_component + 0.4 * strength_component - issue_penalty
    return AxisScore(
        axis=axis,
        score=round(_clamp(score), 1),
        benchmark=TOP_PERFORMER[axis],
        drivers=drivers,
    )


def score_closing(analysis: Optional[CallAnalysis]) -> AxisScore:
    axis = SkillAxis.CLOSING
    if analysis is None:
        return _neutral(axis, "Awaiting call analysis")

    drivers: list[str] = []
    score = 25.0
    step = analysis.next_step

    if step is None:
        drivers.append("No next step agreed -- the call ended without a forward path")
    else:
        score = 55.0
        drivers.append(f"Next step: {step.text}")
        if step.has_date:
            score += 22.0
        else:
            drivers.append("Next step has no date on it")
        if step.is_mutual:
            score += 18.0
        else:
            drivers.append("Only the rep committed; the buyer agreed to nothing")

    concrete = [c for c in analysis.commitments if c.is_concrete]
    if concrete:
        score += min(10.0, len(concrete) * 4.0)
        drivers.append(f"{len(concrete)} concrete commitment(s) captured")

    return AxisScore(
        axis=axis,
        score=round(_clamp(score), 1),
        benchmark=TOP_PERFORMER[axis],
        drivers=drivers,
    )


# --------------------------------------------------------------------------


def build_scorecard(
    metrics: CallMetrics,
    analysis: Optional[CallAnalysis] = None,
    plays_landed: int = 0,
) -> Scorecard:
    axes = [
        score_listening(metrics),
        score_discovery(metrics, analysis),
        score_storytelling(analysis, plays_landed),
        score_objection_handling(analysis),
        score_pace(metrics),
        score_closing(analysis),
    ]
    overall = sum(a.score * AXIS_WEIGHTS[a.axis] for a in axes)
    return Scorecard(
        call_id=metrics.call_id,
        overall=round(_clamp(overall), 1),
        axes=axes,
    )

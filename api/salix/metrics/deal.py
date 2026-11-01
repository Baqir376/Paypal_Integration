"""How much this call moved the deal.

Separate from the skill scorecard on purpose. A scorecard asks how well the rep
behaved; this asks where the deal stands now. A polite, well-paced call that ends
with no next step and an unanswered price objection scores well on one and badly
on the other, and it is the second that decides whether coaching is needed.

Deterministic, and every point is explained, so a rep can see exactly why:

    next step    35   agreed at all, has a date, and the buyer committed too
    objections   20   how many were resolved, and how well
    qualification 25  MEDDIC coverage
    buyer signals 20  buying signals and interest, against concerns and blockers
"""

from __future__ import annotations

from typing import Optional, Sequence

from ..schemas.analysis import CallAnalysis
from ..schemas.common import SalixModel
from ..schemas.metrics import DealScore

BANDS = ((75.0, "strong"), (50.0, "at risk"), (0.0, "weak"))

#: With no objections raised there is nothing to credit or to penalise, and it may
#: mean nobody probed. So: better than a mishandled one, short of a resolved one.
NO_OBJECTIONS = 12.0


def score_deal(analysis: Optional[CallAnalysis]) -> Optional[DealScore]:
    """None when the call could not be read: no score beats a made-up one."""
    if analysis is None:
        return None

    drivers: list[str] = []

    step = analysis.next_step
    if step is None:
        next_step = 0.0
        drivers.append("No next step agreed")
    else:
        next_step = 15.0 + (10.0 if step.has_date else 0.0) + (10.0 if step.is_mutual else 0.0)
        if not step.has_date:
            drivers.append("The next step has no date on it")
        if not step.is_mutual:
            drivers.append("The buyer committed to nothing")
        if step.has_date and step.is_mutual:
            drivers.append("A dated, mutual next step is agreed")

    if analysis.objections:
        handled = [o for o in analysis.objections if o.handled]
        resolution = len(handled) / len(analysis.objections)
        quality = sum(o.handling_quality for o in analysis.objections) / (
            5.0 * len(analysis.objections)
        )
        objections = 20.0 * (0.5 * resolution + 0.5 * quality)
        open_ones = len(analysis.objections) - len(handled)
        if open_ones:
            drivers.append(f"{open_ones} objection(s) left open")
    else:
        objections = NO_OBJECTIONS
        drivers.append("No objections surfaced")

    coverage = analysis.meddic.coverage_ratio()
    qualification = 25.0 * coverage
    if coverage < 0.5:
        drivers.append(f"Only {round(coverage * 100)}% of MEDDIC is covered")

    net = 0.0
    for signal in analysis.buyer_signals:
        if signal.kind in ("buying_signal", "interest"):
            net += signal.weight
        elif signal.kind in ("concern", "blocker"):
            net -= signal.weight * (1.5 if signal.kind == "blocker" else 1.0)
    signals = 20.0 * max(0.0, min(1.0, 0.5 + net / 4.0))
    if net < 0:
        drivers.append("The buyer's concerns outweigh their interest")

    score = round(next_step + objections + qualification + signals, 1)
    band = next(label for floor, label in BANDS if score >= floor)
    return DealScore(score=score, band=band, drivers=drivers)


# --------------------------------------------------------------------------
# Is the score any good?
# --------------------------------------------------------------------------

#: Below this many decided calls, per outcome, the numbers are reported and not
#: believed. Thirty is a rule of thumb, not a statistical guarantee.
MIN_PER_OUTCOME = 30


class BandResult(SalixModel):
    band: str
    calls: int
    won: int
    win_rate: Optional[float] = None


class Calibration(SalixModel):
    decided: int
    won: int
    lost: int
    #: The chance a won call outscores a lost one. 0.5 is a coin, 1.0 is perfect.
    separation: Optional[float] = None
    reliable: bool = False
    verdict: str = ""
    bands: list[BandResult] = []


def calibrate(calls: Sequence[tuple[float, bool]]) -> Calibration:
    """Check the score against what actually happened, from (score, won) pairs.

    The weights above were chosen by judgement. Only a team's own closed deals can
    say whether they were chosen well, so this is the question asked of its data
    rather than an answer assumed in advance.
    """
    won = [score for score, was_won in calls if was_won]
    lost = [score for score, was_won in calls if not was_won]

    bands = []
    for index, (floor, label) in enumerate(BANDS):
        ceiling = BANDS[index - 1][0] if index else float("inf")
        inside = [was_won for score, was_won in calls if floor <= score < ceiling]
        bands.append(
            BandResult(
                band=label,
                calls=len(inside),
                won=sum(inside),
                win_rate=round(sum(inside) / len(inside), 3) if inside else None,
            )
        )

    separation = None
    if won and lost:
        wins = sum((w > l) + 0.5 * (w == l) for w in won for l in lost)
        separation = round(wins / (len(won) * len(lost)), 3)

    reliable = len(won) >= MIN_PER_OUTCOME and len(lost) >= MIN_PER_OUTCOME
    if separation is None:
        verdict = "Mark calls as won or lost to test this score. It needs both."
    else:
        if separation >= 0.75:
            reading = "the score separates won calls from lost ones well"
        elif separation >= 0.6:
            reading = "the score has some signal, but it is weak"
        elif separation > 0.4:
            reading = "the score is no better than a coin toss here"
        else:
            reading = "the score is running backwards here"
        verdict = (
            reading.capitalize() + "."
            if reliable
            else f"Too few closed calls to trust this yet ({len(won)} won, {len(lost)} lost; "
            f"{MIN_PER_OUTCOME} of each is the minimum). So far, {reading}."
        )

    return Calibration(
        decided=len(calls),
        won=len(won),
        lost=len(lost),
        separation=separation,
        reliable=reliable,
        verdict=verdict,
        bands=bands,
    )

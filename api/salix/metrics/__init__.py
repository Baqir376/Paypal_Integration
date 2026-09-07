"""Deterministic conversation measurement.

`engine` computes facts from timestamps; `scorecard` turns those facts into the
six-axis rep radar; `benchmarks` holds every tunable constant in one auditable
place. No module in this package calls a language model.
"""

from .engine import build_timeline, compute_metrics, is_backchannel, is_question
from .scorecard import TOP_PERFORMER, build_scorecard

__all__ = [
    "TOP_PERFORMER",
    "build_scorecard",
    "build_timeline",
    "compute_metrics",
    "is_backchannel",
    "is_question",
]

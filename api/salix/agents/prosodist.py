"""Prosodist -- the deterministic measurement stage of the DAG.

It is an agent by position in the pipeline, not by mechanism: it calls no
language model at all. It exists as its own stage because the numbers it
produces are inputs to every agent downstream, and because keeping measurement
visibly separate from interpretation is the point.

The work lives in `salix.metrics`; this is the seam that puts it in the graph.
"""

from __future__ import annotations

import logging
from typing import Optional

from ..metrics.engine import compute_metrics
from ..metrics.scorecard import build_scorecard
from ..schemas.analysis import CallAnalysis
from ..schemas.call import Transcript
from ..schemas.metrics import CallMetrics, Scorecard
from .base import Agent

log = logging.getLogger("salix.prosodist")


class Prosodist(Agent):
    name = "Prosodist"

    def run(self, transcript: Transcript, duration_ms: int | None = None) -> CallMetrics:
        metrics = compute_metrics(transcript, duration_ms)
        log.info(
            "%s: talk ratio %.0f%%, longest monologue %ds, patience %dms",
            transcript.call_id,
            metrics.talk_ratio_rep * 100,
            metrics.longest_monologue_ms // 1000,
            round(metrics.patience_ms),
        )
        return metrics

    def score(
        self,
        metrics: CallMetrics,
        analysis: Optional[CallAnalysis] = None,
        plays_landed: int = 0,
    ) -> Scorecard:
        """Scored twice per call by design.

        Once immediately after measurement, so the call page has numbers while
        the language models are still working, and again once the Anatomist and
        Playwright have reported, which fills in the three axes that need a
        reading of the conversation rather than a measurement of it.
        """
        return build_scorecard(metrics, analysis, plays_landed)

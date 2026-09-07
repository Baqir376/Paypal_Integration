"""Anatomist -- reads the structure of a sales conversation.

This agent answers the questions a sales manager asks when they listen to a
recording: where did the call turn, what did the buyer actually object to, was
it handled, what did we learn about how they buy, and did anyone commit to
anything real at the end.

It does not score the call. Scoring belongs to the deterministic engine, and
keeping the two apart means a change of opinion about what "good" means never
contaminates the record of what happened.
"""

from __future__ import annotations

import logging

from ..metrics.benchmarks import MONOLOGUE_WARN_MS
from ..schemas.analysis import CallAnalysis
from ..schemas.call import Transcript
from ..schemas.metrics import CallMetrics
from .base import Agent

log = logging.getLogger("salix.anatomist")


ROLE = """\
Your job is to read one sales call transcript and describe its anatomy.

WHAT TO PRODUCE

1. `headline` -- the single thing that decided how this call went. One line.
   Not a summary; a verdict. "The rep answered the pricing objection with a
   feature list instead of a business case" is a headline. "A productive
   discovery call" is not.

2. `summary` -- three sentences. What the buyer needs, what the rep did about
   it, where it stands now.

3. `stages` -- segment the call into its phases using the transcript
   timestamps. Not every call has every stage; only report the ones that
   actually occurred, in the order they occurred.

4. `objections` -- every point of resistance the buyer raised, including the
   soft ones. "We are pretty happy with what we have" is a status-quo
   objection. For each:
   - quote it in the buyer's own words
   - mark `handled` true only if the rep actually addressed the substance;
     acknowledging an objection and moving on is NOT handling it
   - `handling_quality`: 0 ignored, 1 deflected, 2 acknowledged only,
     3 answered adequately, 4 answered well with evidence, 5 turned the
     objection into a reason to buy

5. `meddic` -- what the rep learned about how this deal gets bought.
   Mark `covered` true only when the transcript shows the information was
   actually obtained, not merely that the topic was mentioned.
   - metrics: quantified impact the buyer cares about
   - economic_buyer: who controls the money, identified by role or name
   - decision_criteria: what they will judge options on
   - decision_process: the steps and timeline to a signature
   - identify_pain: the concrete problem, with consequences
   - champion: someone inside who will argue for this when the rep is not there

6. `commitments` -- who agreed to do what. `is_concrete` is true only when
   there is both a specific action and a specific time.

7. `next_step` -- the agreed next action. `is_mutual` is true only if the buyer
   agreed to something too; a rep promising to send materials is not mutual.
   If the call ended without one, return null. Do not invent optimism.

8. `buyer_signals` -- moments revealing genuine interest, concern or a blocker.

9. `issues` -- specific execution mistakes by the rep. For each, `better_move`
   states what a strong performer would have said at that exact moment. Be
   concrete enough that the rep could say the words next time.

10. `strengths` -- moments the rep genuinely did well, same shape, with
    `better_move` holding why it worked. Report real ones only. If the call was
    weak, return an empty list rather than manufacturing encouragement.
"""


class Anatomist(Agent):
    name = "Anatomist"

    async def run(
        self,
        transcript: Transcript,
        call_id: str,
        *,
        metrics: CallMetrics | None = None,
        context: str = "",
    ) -> CallAnalysis:
        analysis = await self.grounded(
            system=self.system_prompt(ROLE),
            user=self._prompt(transcript, metrics, context),
            schema=CallAnalysis,
            transcript=transcript,
            call_id=call_id,
            # Zero. Reading a transcript for objections, stages and MEDDIC
            # coverage is extraction, not composition: the objections are
            # either in the call or they are not. Sampling meant the same
            # recording analysed twice gave two different answers -- 2
            # objections and a score of 61 on one run, 3 and a 65 on the next,
            # from a byte-identical transcript. A manager cannot argue with a
            # rep about a number that moves on its own.
            temperature=0.0,
            max_tokens=12000,
        )
        # The model is asked for the call id but has no reason to know it.
        analysis.call_id = call_id
        return analysis

    def _prompt(
        self, transcript: Transcript, metrics: CallMetrics | None, context: str
    ) -> str:
        parts: list[str] = []
        if context:
            parts.append(f"DEAL CONTEXT\n{context}")

        if metrics is not None:
            parts.append(f"MEASURED FACTS\n{self._measured(metrics)}")

        parts.append(f"TRANSCRIPT\n{transcript.render()}")
        return "\n\n".join(parts)

    def _measured(self, m: CallMetrics) -> str:
        """Hand the model the deterministic numbers.

        Two reasons. It stops the model estimating things we already know
        exactly, and it lets qualitative findings line up with the quantitative
        ones -- an eleven-minute monologue is a fact worth explaining, not a
        fact worth re-deriving.
        """
        lines = [
            f"Call duration: {m.duration_ms // 60000} min {(m.duration_ms // 1000) % 60} s",
            f"Rep spoke {round(m.talk_ratio_rep * 100)}% of the speaking time "
            f"(top performers sit near 43%)",
            f"Longest unbroken rep stretch: {m.longest_monologue_ms // 1000}s"
            + (
                f" starting at {m.longest_monologue_at_ms // 60000:02d}:"
                f"{(m.longest_monologue_at_ms // 1000) % 60:02d}"
                if m.longest_monologue_ms > MONOLOGUE_WARN_MS
                else ""
            ),
            f"Rep asked {m.rep_question_count} questions "
            f"({m.rep_question_rate_per_min}/min), "
            f"{round(m.open_question_ratio * 100)}% open-ended",
            f"Average pause before the rep replied: {round(m.patience_ms)}ms",
            f"Rep talked over the buyer {m.interruptions_by_rep} time(s)",
            f"Rep delivery: {m.rep_wpm} words per minute, "
            f"{m.filler_rate_rep} filler words per 100",
        ]
        return "\n".join(f"- {line}" for line in lines)

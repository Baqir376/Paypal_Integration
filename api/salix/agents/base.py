"""Agent foundations.

Each agent in Salix is a narrow specialist with a typed output contract. They
share three things, all of which live here:

* `Agent` -- the base, holding the provider bundle and a name for tracing.
* `grounded()` -- the structured call plus citation enforcement loop. An agent
  that cites a segment which does not exist gets one chance to correct itself
  against the real id list before its fabricated references are pruned.
* A shared voice. `HOUSE_STYLE` is prepended to every system prompt so the
  whole product speaks like one specific, unsentimental sales coach rather than
  like a chatbot.
"""

from __future__ import annotations

import logging
from typing import Optional, TypeVar

from pydantic import BaseModel

from . import evidence
from ..providers.base import ProviderError, Providers
from ..schemas.call import Transcript

log = logging.getLogger("salix.agents")

T = TypeVar("T", bound=BaseModel)


HOUSE_STYLE = """\
You are part of Salix, a sales conversation analyst used by working revenue teams.

How you write:
- Plain, specific, unsentimental. You are a sharp colleague, not a cheerleader.
- Never praise vaguely. "Good rapport" is worthless; "asked about their renewal
  date before pitching, which framed the whole call" is useful.
- Quantify when the transcript supports it and stay silent when it does not.
- Never invent a fact, a name, a number, or a quote that is not in the material
  you were given. An empty finding is always better than a fabricated one.
- No emoji. No exclamation marks. No filler openers like "Great question".
- Refer to the salesperson as "the rep" and the other party as "the buyer".
"""


CITATION_RULES = """\
EVIDENCE REQUIREMENTS
Every claim must be traceable. The transcript is given to you as numbered lines
in the form `[s0042] (12:31) REP: ...`.

- Wherever the schema asks for a `segment_id`, use one of those exact ids.
- Cite the line the thing actually happened on, not a nearby one.
- If you cannot find a line that supports a claim, drop the claim. Do not
  invent an id, do not guess, and do not cite a plausible-looking id you did
  not see in the transcript.
"""


class Agent:
    """Base class. Subclasses declare `name` and implement `run`."""

    name: str = "agent"

    def __init__(self, providers: Providers):
        self.providers = providers

    @property
    def llm(self):
        return self.providers.llm

    @property
    def embeddings(self):
        return self.providers.embeddings

    def system_prompt(self, role: str, *, cite: bool = True) -> str:
        parts = [HOUSE_STYLE, role]
        if cite:
            parts.append(CITATION_RULES)
        return "\n\n".join(p.strip() for p in parts)

    async def grounded(
        self,
        *,
        system: str,
        user: str,
        schema: type[T],
        transcript: Transcript,
        call_id: str,
        model: Optional[str] = None,
        temperature: float = 0.2,
        max_tokens: int = 8192,
    ) -> T:
        """Structured generation with citation verification and one repair pass.

        The repair prompt does not merely say "you were wrong" -- it hands back
        the specific fabricated ids alongside the ids that actually exist,
        which is what makes the second attempt reliably succeed.
        """
        result = await self.llm.structured(
            system=system,
            user=user,
            schema=schema,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
        )

        invalid = evidence.hydrate(result, transcript, call_id)
        if not invalid:
            return result

        log.warning(
            "%s cited %d nonexistent segment(s): %s",
            self.name, len(invalid), invalid[:8],
        )

        try:
            repaired = await self.llm.structured(
                system=system,
                user=(
                    f"{user}\n\n"
                    "--- CORRECTION REQUIRED ---\n"
                    "Your previous answer cited these segment ids, which do not "
                    f"exist in the transcript: {', '.join(sorted(set(invalid))[:20])}.\n\n"
                    "The only valid ids are:\n"
                    f"{evidence.valid_id_hint(transcript)}\n\n"
                    "Produce the analysis again. Every segment_id must come from "
                    "that list. Drop any finding you cannot support with a real "
                    "line rather than substituting a different id."
                ),
                schema=schema,
                model=model,
                temperature=0.0,
                max_tokens=max_tokens,
            )
        except ProviderError as exc:
            log.warning("%s citation repair failed (%s); pruning", self.name, exc)
            evidence.prune_invalid(result, transcript)
            return result

        still_invalid = evidence.hydrate(repaired, transcript, call_id)
        if still_invalid:
            pruned = evidence.prune_invalid(repaired, transcript)
            log.warning("%s pruned %d unresolvable citation(s)", self.name, pruned)
        return repaired

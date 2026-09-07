"""Evidence hydration and citation enforcement.

This is the mechanism that stops Salix from being a confident guesser. Every
claim an agent makes must name the transcript segments it came from. After the
model responds we walk the returned object, check each cited id against the
real transcript, and:

* hydrate valid citations with the verbatim quote and timestamp, so the UI can
  show a finding beside its proof without a second lookup;
* collect invalid ones -- a segment id that does not exist is a fabrication,
  and the agent is asked to try again with the list of ids it may actually use.

The walk is generic over Pydantic models, so a new schema with an `EvidenceRef`
anywhere inside it is covered automatically.
"""

from __future__ import annotations

import logging
from typing import Any, Iterator

from pydantic import BaseModel

from ..schemas.call import Transcript
from ..schemas.common import EvidenceRef

log = logging.getLogger("salix.evidence")


def walk_evidence(node: Any) -> Iterator[EvidenceRef]:
    """Yield every EvidenceRef nested anywhere inside `node`."""
    if isinstance(node, EvidenceRef):
        yield node
        return
    if isinstance(node, BaseModel):
        for name in type(node).model_fields:
            yield from walk_evidence(getattr(node, name, None))
        return
    if isinstance(node, (list, tuple, set)):
        for item in node:
            yield from walk_evidence(item)
        return
    if isinstance(node, dict):
        for item in node.values():
            yield from walk_evidence(item)


def hydrate(model: BaseModel, transcript: Transcript, call_id: str) -> list[str]:
    """Fill in quotes and timestamps; return the list of fabricated segment ids.

    Mutates in place, which is safe because agents hand us an object they just
    built and nobody else holds a reference to it yet.
    """
    index = {s.id: s for s in transcript.segments}
    invalid: list[str] = []

    for ref in walk_evidence(model):
        if not ref.segment_id:
            continue
        segment = index.get(ref.segment_id)
        if segment is None:
            invalid.append(ref.segment_id)
            continue
        ref.call_id = call_id
        ref.quote = segment.text
        ref.start_ms = segment.start_ms

    return invalid


def prune_invalid(model: BaseModel, transcript: Transcript) -> int:
    """Blank out citations that could not be resolved.

    Used as the last resort after retries are exhausted: a finding with no
    evidence is still worth showing, but it must not carry a fake reference.
    """
    index = {s.id for s in transcript.segments}
    pruned = 0
    for ref in walk_evidence(model):
        if ref.segment_id and ref.segment_id not in index:
            ref.segment_id = ""
            ref.quote = ""
            ref.start_ms = None
            pruned += 1
    return pruned


def citation_coverage(model: BaseModel) -> float:
    """Share of citations that resolved to a real segment. Surfaced on the call
    page so a reviewer can see how well grounded an analysis is."""
    refs = [r for r in walk_evidence(model) if r.segment_id]
    if not refs:
        return 0.0
    return round(sum(1 for r in refs if r.quote) / len(refs), 3)


def valid_id_hint(transcript: Transcript, limit: int = 400) -> str:
    """A compact list of legal segment ids for the repair prompt."""
    ids = [s.id for s in transcript.segments][:limit]
    return ", ".join(ids)

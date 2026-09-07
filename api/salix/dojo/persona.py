"""Building the buyer a rep actually has to beat.

The persona is not invented and it is not a generic "tough prospect". It is
assembled from the objections that appear in this rep's own lost and stalled
calls, weighted by how badly each was handled. A rep who keeps losing on price
gets a buyer who opens on price; a rep who never finds the economic buyer gets
one who will not reveal who signs.

That is what makes the practice transfer. Generic roleplay teaches a rep to
handle a buyer who does not exist.
"""

from __future__ import annotations

import logging
import uuid
from collections import Counter

from sqlalchemy.ext.asyncio import AsyncSession

from ..metrics import analytics
from ..schemas.common import CallOutcome, ObjectionCategory
from ..schemas.dojo import BuyerPersona, PersonaObjection
from ..store import repo

log = logging.getLogger("salix.dojo.persona")

# Buyer voices, chosen to be clearly distinct from the seed rep voices.
VOICES = ("Jennifer", "Elias", "Nofish", "Katerina")

DISPOSITIONS = {
    ObjectionCategory.PRICE: "cost-focused, will not move without a business case",
    ObjectionCategory.TIMING: "busy and non-committal, everything is next quarter",
    ObjectionCategory.AUTHORITY: "guarded about who actually signs",
    ObjectionCategory.COMPETITION: "loyal to the incumbent, needs a real reason to move",
    ObjectionCategory.STATUS_QUO: "content, sees no urgency, hard to unsettle",
    ObjectionCategory.TRUST: "sceptical of vendor claims, wants proof",
    ObjectionCategory.FIT: "unconvinced this is built for a company their size",
    ObjectionCategory.RISK: "worried about migration and disruption",
    ObjectionCategory.OTHER: "pragmatic and hard to read",
}

TITLES = (
    "VP Operations", "Head of Revenue Operations", "Commercial Director",
    "Chief Financial Officer", "Director of Customer Success",
)

# Names for the generated buyer. Deliberately varied; the persona is fictional
# and clearly labelled as such in the UI.
#: The buyer is always a woman, so every name here is one.
#:
#: The list used to be half men, and in English nothing showed: verbs there do
#: not agree with the speaker. In Urdu it was glaring -- "Tomas Lindqvist bol
#: RAHI hoon", "main nahi CHAHTI" -- a Scandinavian man's name attached to
#: feminine grammar and read aloud by a woman's voice, three ways of saying
#: something different about the same person in one sentence.
#:
#: Fixing the grammar instead would have been the wrong end: the voice is
#: female by product decision, so the persona has to be too.
NAMES = (
    "Ayesha Rahman", "Grace Mbeki", "Priya Nair", "Ines Oyelaran",
    "Sana Mahmood", "Elena Vasquez", "Nadia Haddad", "Claire Beaumont",
)


async def build_persona(
    session: AsyncSession,
    org_id: str,
    rep_id: str,
    *,
    difficulty: int = 2,
    scenario_hint: str = "",
) -> BuyerPersona:
    """Mine this rep's own failures into an opponent."""
    bundles = await analytics.load_bundles(session, org_id, rep_id=rep_id)
    rep = await repo.get_rep(session, rep_id)

    # Weight by how badly it went: an objection that lost a deal matters more
    # than one that merely came up.
    weighted: list[tuple[PersonaObjection, float]] = []
    categories: Counter[ObjectionCategory] = Counter()

    for bundle in bundles:
        if bundle.analysis is None:
            continue
        lost = bundle.call.outcome is CallOutcome.LOST
        for objection in bundle.analysis.objections:
            if objection.handled and objection.handling_quality >= 4:
                continue  # they can already beat this one
            weight = 1.0
            if lost:
                weight += 1.5
            if not objection.handled:
                weight += 1.0
            weight += (5 - objection.handling_quality) * 0.3

            categories[objection.category] += weight
            weighted.append(
                (
                    PersonaObjection(
                        category=objection.category,
                        text=objection.text,
                        from_call_id=bundle.call.id,
                        hardness=min(1.0, 0.35 + weight * 0.12),
                    ),
                    weight,
                )
            )

    weighted.sort(key=lambda pair: -pair[1])
    objections = [objection for objection, _ in weighted[:6]]
    derived_from = sorted({o.from_call_id for o in objections if o.from_call_id})

    if not objections:
        # A rep with no analysed failures still deserves a workout.
        objections = [
            PersonaObjection(
                category=ObjectionCategory.STATUS_QUO,
                text="Honestly, what we have works well enough for now.",
                hardness=0.5,
            ),
            PersonaObjection(
                category=ObjectionCategory.PRICE,
                text="That is more than we were expecting to spend.",
                hardness=0.6,
            ),
        ]
        log.info("no analysed objections for %s; using the default sparring buyer", rep_id)

    dominant = categories.most_common(1)[0][0] if categories else ObjectionCategory.STATUS_QUO

    # Difficulty raises how hard the buyer holds the line, not how rude they are.
    hardness_shift = {1: -0.15, 2: 0.0, 3: 0.2}.get(difficulty, 0.0)
    for objection in objections:
        objection.hardness = max(0.1, min(1.0, objection.hardness + hardness_shift))

    seed = abs(hash((rep_id, difficulty))) % len(NAMES)
    persona = BuyerPersona(
        id=f"persona_{uuid.uuid4().hex[:10]}",
        name=NAMES[seed],
        title=TITLES[seed % len(TITLES)],
        company=_company_for(bundles),
        disposition=DISPOSITIONS[dominant],
        context=(
            scenario_hint
            or (
                "Took the meeting because something is not working, but has been "
                "sold to before and is wary of it happening again."
            )
        ),
        objections=objections,
        voice=VOICES[seed % len(VOICES)],
        voice_instruction=(
            "Speak as a busy senior operations leader on a business call. "
            "Measured, a little guarded, not hostile."
        ),
        derived_from_call_ids=derived_from,
        difficulty=difficulty,
    )

    log.info(
        "persona for %s: %s, %d objection(s) from %d call(s), dominant %s",
        rep.name if rep else rep_id,
        persona.name,
        len(objections),
        len(derived_from),
        dominant.value,
    )
    return persona


def _company_for(bundles) -> str:
    """Reuse an account the rep actually lost, so the scenario feels theirs."""
    lost = [b.call.account for b in bundles if b.call.outcome is CallOutcome.LOST]
    if lost:
        return lost[0]
    return bundles[0].call.account if bundles else "A mid-market operations team"

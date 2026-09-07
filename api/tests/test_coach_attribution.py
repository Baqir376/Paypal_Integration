"""Regression tests for coaching-script source attribution.

Telling a rep that one colleague said something a different colleague actually
said is worse than offering no citation at all: it is the one error that would
destroy trust in the whole feature. These tests pin the resolution rules.
"""

from __future__ import annotations

from salix.agents.coach import Coach
from salix.schemas.coaching import SourceRef


def moment(moment_id, call_id, rep_id, play_id="play_cc", play_name="The Compounding Cost"):
    return {
        "id": moment_id,
        "call_id": call_id,
        "rep_id": rep_id,
        "kind": "play",
        "outcome": "won",
        "text": f"{play_name}. A story about a comparable customer.",
        "play_id": play_id,
        "play_name": play_name,
        "quote": f"quote from {call_id}",
    }


ZARA = moment("m1", "call_northwind_1", "rep_zara")
DANIYAL = moment("m2", "call_orbit_1", "rep_daniyal")


def index(*moments):
    by_play: dict[str, list[dict]] = {}
    for m in moments:
        by_play.setdefault(m["play_id"], []).append(m)
    return by_play, {m["call_id"]: m for m in moments}


class TestResolveMoment:
    def test_play_and_call_together_resolve_exactly(self):
        by_play, by_call = index(ZARA, DANIYAL)
        found = Coach._resolve_moment(
            SourceRef(play_id="play_cc", call_id="call_orbit_1"), by_play, by_call
        )
        assert found["rep_id"] == "rep_daniyal"

    def test_shared_play_without_a_call_is_dropped_not_guessed(self):
        """The bug this file exists for. Two reps ran the same play; citing the
        play alone cannot identify which one, so it must resolve to nothing."""
        by_play, by_call = index(ZARA, DANIYAL)
        assert Coach._resolve_moment(SourceRef(play_id="play_cc"), by_play, by_call) is None

    def test_unique_play_without_a_call_still_resolves(self):
        by_play, by_call = index(ZARA)
        found = Coach._resolve_moment(SourceRef(play_id="play_cc"), by_play, by_call)
        assert found["call_id"] == "call_northwind_1"

    def test_call_only_citation_resolves(self):
        by_play, by_call = index(ZARA, DANIYAL)
        found = Coach._resolve_moment(SourceRef(call_id="call_orbit_1"), by_play, by_call)
        assert found["rep_id"] == "rep_daniyal"

    def test_unknown_play_falls_back_to_the_call(self):
        by_play, by_call = index(ZARA)
        found = Coach._resolve_moment(
            SourceRef(play_id="play_nonexistent", call_id="call_northwind_1"),
            by_play,
            by_call,
        )
        assert found["call_id"] == "call_northwind_1"

    def test_wrong_call_for_a_shared_play_does_not_silently_substitute(self):
        by_play, by_call = index(ZARA, DANIYAL)
        assert (
            Coach._resolve_moment(
                SourceRef(play_id="play_cc", call_id="call_that_never_existed"),
                by_play,
                by_call,
            )
            is None
        )

    def test_empty_source_resolves_to_nothing(self):
        by_play, by_call = index(ZARA)
        assert Coach._resolve_moment(SourceRef(), by_play, by_call) is None

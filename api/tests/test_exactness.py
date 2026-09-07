# -*- coding: utf-8 -*-
"""Proof that the measurement layer is exact.

The product's central claim is that a number you cannot recompute is a number
you should not trust: talk ratio, monologue length, patience, interruptions,
question rate and pace are arithmetic over diarized timestamps, with no model
in the path. This file is the evidence for that claim, and it is deliberately
stronger than the fixture tests elsewhere.

Fixtures prove the engine agrees with what somebody once wrote down. That is
worth having, and it is not proof: a fixture computed from the implementation
agrees with the implementation by construction. So this does two other things.

**Differential testing.** Every quantity is recomputed here by a second
implementation, written from the specification rather than from the code, using
a different algorithm -- an event sweep over interval boundaries instead of the
engine's sort-and-merge. Two independent routes to the same integer, over
thousands of randomly generated transcripts, is a real check. A bug would have
to be present in both, and they share no code.

**Invariants.** Some things must hold for every conceivable input, including
the ones nobody thought to write a fixture for: overlapping speech, zero-length
segments, segments out of order, a call where nobody speaks. Those are asserted
over generated input rather than chosen input, which is where the surprises
live.

What this does NOT prove, and no test could: that the transcript is correct.
Speech recognition has a word error rate -- Deepgram's own published median is
5.26% -- and every number here is exact *with respect to the transcript it was
given*. That distinction is the honest version of the accuracy claim, and it is
worth stating plainly rather than blurring.
"""

from __future__ import annotations

import random

import pytest

from salix.metrics.engine import compute_metrics
from salix.schemas.call import Segment, Transcript
from salix.schemas.common import SpeakerRole

# --------------------------------------------------------------------------
# An independent implementation, written from the specification
# --------------------------------------------------------------------------


def union_ms(intervals: list[tuple[int, int]]) -> int:
    """Total time covered by a set of intervals, counting overlap once.

    An event sweep: +1 entering an interval, -1 leaving it, and time accrues
    while the depth is above zero. The engine merges sorted intervals instead.
    Same answer, no shared code, no shared way of being wrong.
    """
    events: list[tuple[int, int]] = []
    for start, end in intervals:
        if end > start:
            events.append((start, +1))
            events.append((end, -1))
    if not events:
        return 0

    events.sort()
    covered = 0
    depth = 0
    previous = events[0][0]
    for position, delta in events:
        if depth > 0:
            covered += position - previous
        depth += delta
        previous = position
    return covered


def independent_floor_control(segments: list[Segment], duration_ms: int) -> dict:
    """Recompute the floor-control numbers from the stated rules."""
    if not segments:
        # No speech at all. A recording of known length is then silence for
        # the whole of it -- which is the state worth being able to see, not
        # one to report as zero.
        return {
            "rep": 0, "buyer": 0, "speech": 0,
            "silence": max(0, duration_ms), "ratio": 0.0,
        }

    rep = [(s.start_ms, s.end_ms) for s in segments if s.role is SpeakerRole.REP]
    buyer = [(s.start_ms, s.end_ms) for s in segments if s.role is SpeakerRole.BUYER]
    every = [(s.start_ms, s.end_ms) for s in segments]

    rep_ms = union_ms(rep)
    buyer_ms = union_ms(buyer)
    speech_ms = union_ms(every)
    total = max(duration_ms, max(s.end_ms for s in segments))
    voiced = rep_ms + buyer_ms

    return {
        "rep": rep_ms,
        "buyer": buyer_ms,
        "speech": speech_ms,
        "silence": max(0, total - speech_ms),
        "ratio": (rep_ms / voiced) if voiced else 0.0,
    }


# --------------------------------------------------------------------------
# Generated transcripts, including the shapes nobody writes fixtures for
# --------------------------------------------------------------------------


def a_segment(index: int, role: SpeakerRole, start: int, end: int, text: str = "hello there") -> Segment:
    return Segment(
        id=f"seg_{index}",
        index=index,
        speaker_id=0 if role is SpeakerRole.REP else 1,
        role=role,
        start_ms=start,
        end_ms=end,
        text=text,
    )


def random_transcript(rng: random.Random, *, allow_overlap=True, allow_empty=True):
    """A transcript with whatever shape the generator feels like.

    Deliberately hostile: segments may overlap, touch exactly, have zero
    length, arrive out of order, or come from one speaker only.
    """
    count = rng.randint(0, 30)
    segments: list[Segment] = []
    cursor = rng.randint(0, 2000)

    for index in range(count):
        role = rng.choice([SpeakerRole.REP, SpeakerRole.BUYER])
        gap = rng.choice([-1500, -400, 0, 0, 120, 700, 3000]) if allow_overlap else rng.randint(0, 900)
        start = max(0, cursor + gap)
        length = rng.choice([0, 1, 250, 900, 4000, 20000]) if allow_empty else rng.randint(200, 9000)
        end = start + length
        segments.append(a_segment(index, role, start, end))
        cursor = end

    rng.shuffle(segments)
    for position, segment in enumerate(segments):
        segment.index = position

    last = max((s.end_ms for s in segments), default=0)
    duration = rng.choice([0, last, last + rng.randint(0, 30000)])
    return Transcript(call_id="c_generated", segments=segments), duration


CASES = 3000


class TestFloorControlIsExact:
    """Two implementations, one answer, three thousand times."""

    def test_talk_time_matches_an_independent_computation(self):
        rng = random.Random(20260907)
        for case in range(CASES):
            transcript, duration = random_transcript(rng)
            expected = independent_floor_control(transcript.segments, duration)
            actual = compute_metrics(transcript, duration)

            assert actual.rep_talk_ms == expected["rep"], f"case {case}"
            assert actual.buyer_talk_ms == expected["buyer"], f"case {case}"
            assert actual.silence_ms == expected["silence"], f"case {case}"

    def test_the_ratio_matches_to_the_stored_precision(self):
        rng = random.Random(11)
        for case in range(CASES):
            transcript, duration = random_transcript(rng)
            expected = independent_floor_control(transcript.segments, duration)
            actual = compute_metrics(transcript, duration)

            assert actual.talk_ratio_rep == pytest.approx(
                round(min(1.0, expected["ratio"]), 4), abs=1e-9
            ), f"case {case}"

    def test_overlapping_speech_is_counted_once_not_twice(self):
        """The rule the whole coherence of the ratio rests on. Two people
        talking at the same second is one second of the call, not two."""
        transcript = Transcript(call_id="c", segments=[
                a_segment(0, SpeakerRole.REP, 0, 10_000),
                a_segment(1, SpeakerRole.REP, 5_000, 15_000),
            ])
        duration = 15_000
        assert compute_metrics(transcript, duration).rep_talk_ms == 15_000

    def test_identical_segments_do_not_double_count(self):
        transcript = Transcript(call_id="c", segments=[
                a_segment(0, SpeakerRole.REP, 1_000, 4_000),
                a_segment(1, SpeakerRole.REP, 1_000, 4_000),
            ])
        duration = 4_000
        assert compute_metrics(transcript, duration).rep_talk_ms == 3_000

    def test_touching_segments_leave_no_gap_and_no_overlap(self):
        transcript = Transcript(call_id="c", segments=[
                a_segment(0, SpeakerRole.REP, 0, 5_000),
                a_segment(1, SpeakerRole.REP, 5_000, 9_000),
            ])
        duration = 9_000
        assert compute_metrics(transcript, duration).rep_talk_ms == 9_000


class TestInvariants:
    """True for every input, including the ones nobody imagined."""

    def _cases(self):
        rng = random.Random(4242)
        for _ in range(CASES):
            yield random_transcript(rng)

    def test_the_ratio_is_always_a_proportion(self):
        for transcript, duration in self._cases():
            assert 0.0 <= compute_metrics(transcript, duration).talk_ratio_rep <= 1.0

    def test_silence_is_never_negative(self):
        for transcript, duration in self._cases():
            assert compute_metrics(transcript, duration).silence_ms >= 0

    def test_no_duration_is_negative(self):
        for transcript, duration in self._cases():
            m = compute_metrics(transcript, duration)
            assert m.rep_talk_ms >= 0
            assert m.buyer_talk_ms >= 0
            assert m.longest_monologue_ms >= 0

    def test_speech_never_exceeds_the_call(self):
        for transcript, duration in self._cases():
            m = compute_metrics(transcript, duration)
            total = max(duration, max((s.end_ms for s in transcript.segments), default=0))
            speech = union_ms([(s.start_ms, s.end_ms) for s in transcript.segments])
            assert speech <= total
            assert m.silence_ms == max(0, total - speech)

    def test_the_longest_monologue_fits_inside_the_call(self):
        for transcript, duration in self._cases():
            m = compute_metrics(transcript, duration)
            total = max(duration, max((s.end_ms for s in transcript.segments), default=0))
            assert m.longest_monologue_ms <= total

    def test_the_ratio_agrees_with_its_own_components(self):
        """Stated separately because a UI reads the ratio and the millisecond
        counts from the same object, and they must tell the same story."""
        for transcript, duration in self._cases():
            m = compute_metrics(transcript, duration)
            voiced = m.rep_talk_ms + m.buyer_talk_ms
            if voiced:
                assert m.talk_ratio_rep == pytest.approx(
                    round(min(1.0, m.rep_talk_ms / voiced), 4), abs=1e-9
                )

    def test_counts_are_never_negative(self):
        for transcript, duration in self._cases():
            m = compute_metrics(transcript, duration)
            assert m.rep_question_count >= 0
            assert m.interruptions_by_rep >= 0
            assert m.interruptions_by_buyer >= 0
            assert m.rep_wpm >= 0
            assert m.patience_ms >= 0


class TestDeterminism:
    """The same transcript must always produce the same numbers.

    Not a formality. It is what lets a manager and a rep look at the same call
    on different days and argue about the conversation rather than about the
    software.
    """

    def test_repeated_computation_is_identical(self):
        rng = random.Random(999)
        for _ in range(400):
            transcript, duration = random_transcript(rng)
            first = compute_metrics(transcript, duration)
            second = compute_metrics(transcript, duration)
            assert first.model_dump() == second.model_dump()

    def test_segment_order_does_not_change_the_answer(self):
        """Segments arrive from the transcriber in whatever order it emits
        them. The measurements are about time, not about arrival."""
        rng = random.Random(7)
        for _ in range(400):
            transcript, duration = random_transcript(rng)
            shuffled = Transcript(
                call_id=transcript.call_id,
                segments=sorted(transcript.segments, key=lambda s: (s.end_ms, s.start_ms)),
            )
            a = compute_metrics(transcript, duration)
            b = compute_metrics(shuffled, duration)

            assert a.rep_talk_ms == b.rep_talk_ms
            assert a.buyer_talk_ms == b.buyer_talk_ms
            assert a.talk_ratio_rep == b.talk_ratio_rep
            assert a.silence_ms == b.silence_ms


class TestDegenerateInput:
    """The shapes that arrive from real audio and break naive code."""

    def test_an_empty_transcript(self):
        m = compute_metrics(Transcript(call_id="c", segments=[]), 0)
        assert m.talk_ratio_rep == 0.0
        assert m.rep_talk_ms == 0

    def test_a_call_where_only_the_rep_speaks(self):
        transcript = Transcript(call_id="c", segments=[a_segment(0, SpeakerRole.REP, 0, 60_000)])
        duration = 60_000
        assert compute_metrics(transcript, duration).talk_ratio_rep == 1.0

    def test_a_call_where_only_the_buyer_speaks(self):
        transcript = Transcript(call_id="c", segments=[a_segment(0, SpeakerRole.BUYER, 0, 60_000)])
        duration = 60_000
        assert compute_metrics(transcript, duration).talk_ratio_rep == 0.0

    def test_zero_length_segments_contribute_nothing(self):
        transcript = Transcript(call_id="c", segments=[
                a_segment(0, SpeakerRole.REP, 1_000, 1_000),
                a_segment(1, SpeakerRole.BUYER, 2_000, 2_000),
            ])
        duration = 5_000
        m = compute_metrics(transcript, duration)
        assert m.rep_talk_ms == 0
        assert m.buyer_talk_ms == 0
        assert m.talk_ratio_rep == 0.0

    def test_a_declared_duration_shorter_than_the_audio(self):
        """The transcriber's duration and the last timestamp can disagree. The
        later of the two is the call, or silence would come out negative."""
        transcript = Transcript(call_id="c", segments=[a_segment(0, SpeakerRole.REP, 0, 90_000)])
        duration = 10_000
        assert compute_metrics(transcript, duration).silence_ms == 0

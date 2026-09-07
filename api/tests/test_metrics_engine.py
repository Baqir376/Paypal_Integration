"""Unit tests for the deterministic metrics engine.

Every expectation here is computed by hand from the fixture timestamps written
in the test itself. If a test needs a comment explaining where the number came
from, the number is wrong.
"""

from __future__ import annotations

import pytest

from salix.metrics import benchmarks as B
from salix.metrics import intervals as iv
from salix.metrics.engine import (
    compute_metrics,
    count_fillers,
    is_backchannel,
    is_open_question,
    is_question,
    monologue_runs,
)
from salix.metrics.scorecard import build_scorecard
from salix.schemas.call import Segment, Transcript
from salix.schemas.common import SkillAxis, SpeakerRole


def seg(idx, role, start, end, text):
    return Segment(
        id=f"s{idx:04d}",
        index=idx,
        speaker_id=0 if role is SpeakerRole.REP else 1,
        role=role,
        start_ms=start,
        end_ms=end,
        text=text,
    )


REP = SpeakerRole.REP
BUYER = SpeakerRole.BUYER


# --------------------------------------------------------------------------
# Interval arithmetic
# --------------------------------------------------------------------------


class TestIntervals:
    def test_merge_collapses_overlap(self):
        assert iv.merge([(0, 100), (50, 200), (300, 400)]) == [(0, 200), (300, 400)]

    def test_merge_joins_touching(self):
        assert iv.merge([(0, 100), (100, 200)]) == [(0, 200)]

    def test_merge_drops_zero_length(self):
        assert iv.merge([(50, 50), (0, 10)]) == [(0, 10)]

    def test_total_counts_overlap_once(self):
        # Naive summation would give 250; the union is 0..200 = 200.
        assert iv.total([(0, 150), (100, 200)]) == 200

    def test_gaps_between_and_around(self):
        assert iv.gaps([(100, 200), (400, 500)], 0, 600) == [
            (0, 100),
            (200, 400),
            (500, 600),
        ]

    def test_overlap_disjoint_is_zero(self):
        assert iv.overlap_ms((0, 100), (200, 300)) == 0

    def test_overlap_partial(self):
        assert iv.overlap_ms((0, 100), (60, 300)) == 40


# --------------------------------------------------------------------------
# Text classification
# --------------------------------------------------------------------------


class TestTextHelpers:
    @pytest.mark.parametrize(
        "text",
        ["What does that process look like today?", "How are you handling it"],
    )
    def test_open_questions(self, text):
        assert is_question(text)
        assert is_open_question(text)

    def test_closed_question_without_punctuation(self):
        # ASR frequently drops the question mark; the auxiliary verb carries it.
        assert is_question("Do you have budget allocated for this")
        assert not is_open_question("Do you have budget allocated for this")

    def test_statement_is_not_a_question(self):
        assert not is_question("We integrate with your existing stack.")

    def test_filler_counting(self):
        text = "So, um, you know, it is basically the same thing, I mean."
        # um, you know, basically, i mean = 4
        assert count_fillers(text) == 4

    def test_backchannel_detection(self):
        assert is_backchannel(seg(1, BUYER, 0, 600, "Mm-hmm."))
        assert is_backchannel(seg(2, BUYER, 0, 900, "Right, yeah."))

    def test_long_utterance_is_not_backchannel(self):
        assert not is_backchannel(
            seg(3, BUYER, 0, 4000, "Yeah, that is exactly the problem we hit.")
        )

    def test_short_but_substantive_is_not_backchannel(self):
        assert not is_backchannel(seg(4, BUYER, 0, 900, "Too expensive."))


# --------------------------------------------------------------------------
# Floor control
# --------------------------------------------------------------------------


class TestTalkRatio:
    def test_even_split(self):
        t = Transcript(
            call_id="c1",
            segments=[
                seg(0, REP, 0, 10_000, "Hello there and welcome."),
                seg(1, BUYER, 10_000, 20_000, "Good to meet you as well."),
            ],
        )
        m = compute_metrics(t)
        assert m.rep_talk_ms == 10_000
        assert m.buyer_talk_ms == 10_000
        assert m.talk_ratio_rep == 0.5

    def test_ratio_uses_union_not_sum(self):
        # Rep 0..10s, buyer 8..18s. Overlap is 2s. Union totals 10s + 10s.
        t = Transcript(
            call_id="c2",
            segments=[
                seg(0, REP, 0, 10_000, "One two three."),
                seg(1, BUYER, 8_000, 18_000, "Four five six."),
            ],
        )
        m = compute_metrics(t)
        assert m.duration_ms == 18_000
        # Speech union is 0..18000, so silence is zero despite the overlap.
        assert m.silence_ms == 0

    def test_silence_is_duration_minus_speech(self):
        t = Transcript(
            call_id="c3",
            segments=[
                seg(0, REP, 0, 5_000, "Short opener."),
                seg(1, BUYER, 15_000, 20_000, "Delayed reply."),
            ],
        )
        m = compute_metrics(t, duration_ms=30_000)
        # Speech = 5000 + 5000 = 10000 of a 30000ms call.
        assert m.silence_ms == 20_000

    def test_duration_never_shorter_than_last_segment(self):
        t = Transcript(call_id="c4", segments=[seg(0, REP, 0, 40_000, "Long.")])
        m = compute_metrics(t, duration_ms=10_000)
        assert m.duration_ms == 40_000


class TestMonologue:
    def test_backchannel_does_not_break_the_run(self):
        # Rep speaks 0..60s and 61..120s with a "mm-hmm" wedged between.
        # A naive implementation reports 60s; the correct answer is 120s.
        t = Transcript(
            call_id="c5",
            segments=[
                seg(0, REP, 0, 60_000, "Let me walk you through the platform."),
                seg(1, BUYER, 60_100, 60_800, "Mm-hmm."),
                seg(2, REP, 61_000, 120_000, "And then the second piece is this."),
            ],
        )
        m = compute_metrics(t)
        assert m.longest_monologue_ms == 120_000
        assert m.longest_monologue_at_ms == 0

    def test_real_handoff_breaks_the_run(self):
        t = Transcript(
            call_id="c6",
            segments=[
                seg(0, REP, 0, 60_000, "Let me walk you through the platform."),
                seg(1, BUYER, 60_100, 75_000, "Before you go on, how does pricing work?"),
                seg(2, REP, 75_500, 120_000, "Good question, it is per seat."),
            ],
        )
        m = compute_metrics(t)
        assert m.longest_monologue_ms == 60_000

    def test_same_speaker_gap_within_tolerance_stays_one_run(self):
        t = Transcript(
            call_id="c7",
            segments=[
                seg(0, REP, 0, 50_000, "First half."),
                seg(1, REP, 51_000, 100_000, "Second half."),
            ],
        )
        m = compute_metrics(t)
        assert m.longest_monologue_ms == 100_000

    def test_same_speaker_long_gap_splits_the_run(self):
        gap = B.TURN_GAP_TOLERANCE_MS + 1_000
        t = Transcript(
            call_id="c8",
            segments=[
                seg(0, REP, 0, 50_000, "First half."),
                seg(1, REP, 50_000 + gap, 100_000 + gap, "Second half."),
            ],
        )
        m = compute_metrics(t)
        assert m.longest_monologue_ms == 50_000

    def test_counts_only_rep_monologues_over_threshold(self):
        t = Transcript(
            call_id="c9",
            segments=[
                seg(0, REP, 0, 100_000, "A very long rep stretch."),
                seg(1, BUYER, 101_000, 200_000, "A very long buyer stretch."),
            ],
        )
        m = compute_metrics(t)
        assert m.monologues_over_threshold == 1
        assert len(m.monologues) == 2

    def test_runs_helper_is_stable_on_empty(self):
        assert monologue_runs([]) == []


class TestReciprocity:
    def test_patience_averages_buyer_to_rep_gaps(self):
        # Gaps of 800ms and 1200ms -> mean 1000ms.
        t = Transcript(
            call_id="c10",
            segments=[
                seg(0, BUYER, 0, 5_000, "We looked at three vendors."),
                seg(1, REP, 5_800, 9_000, "What mattered most in that comparison?"),
                seg(2, BUYER, 9_000, 14_000, "Honestly, the support response times."),
                seg(3, REP, 15_200, 18_000, "That is where we tend to win."),
            ],
        )
        m = compute_metrics(t)
        assert m.patience_ms == 1000.0

    def test_interruption_is_excluded_from_patience(self):
        # The rep cuts in 500ms early. That is an interruption, not a fast
        # handoff, and must not drag the patience mean down.
        t = Transcript(
            call_id="c11",
            segments=[
                seg(0, BUYER, 0, 5_000, "We were thinking maybe next quarter."),
                seg(1, REP, 4_500, 8_000, "Right, but consider the cost of waiting."),
                seg(2, BUYER, 8_000, 12_000, "Sure."),
                seg(3, REP, 12_900, 15_000, "So what would unlock this quarter?"),
            ],
        )
        m = compute_metrics(t)
        assert m.interruptions_by_rep == 1
        assert m.patience_ms == 900.0

    def test_jitter_below_threshold_is_not_an_interruption(self):
        overlap = B.INTERRUPTION_MIN_OVERLAP_MS - 50
        t = Transcript(
            call_id="c12",
            segments=[
                seg(0, BUYER, 0, 5_000, "That sounds reasonable to me."),
                seg(1, REP, 5_000 - overlap, 8_000, "Great, then here is the plan."),
            ],
        )
        m = compute_metrics(t)
        assert m.interruptions_by_rep == 0


class TestDiscovery:
    def test_question_rate_per_minute(self):
        # Two questions across a 60s call.
        t = Transcript(
            call_id="c13",
            segments=[
                seg(0, REP, 0, 30_000, "What does that look like today? Do you have a budget?"),
                seg(1, BUYER, 30_000, 60_000, "We handle it in spreadsheets."),
            ],
        )
        m = compute_metrics(t)
        assert m.rep_question_count == 2
        assert m.rep_question_rate_per_min == 2.0
        assert m.open_question_ratio == 0.5

    def test_no_questions_gives_zero_not_error(self):
        t = Transcript(
            call_id="c14",
            segments=[seg(0, REP, 0, 10_000, "We are the market leader.")],
        )
        m = compute_metrics(t)
        assert m.rep_question_count == 0
        assert m.open_question_ratio == 0.0


class TestDelivery:
    def test_wpm_uses_speaking_time_only(self):
        # 20 words spoken across exactly 10 seconds -> 120 wpm.
        words = " ".join(["word"] * 20)
        t = Transcript(call_id="c15", segments=[seg(0, REP, 0, 10_000, words)])
        m = compute_metrics(t, duration_ms=60_000)
        assert m.rep_wpm == 120.0

    def test_filler_rate_per_hundred_words(self):
        # 4 fillers in the text below; 100 total words -> rate of 4.0.
        text = ("um " * 4) + ("word " * 96)
        t = Transcript(call_id="c16", segments=[seg(0, REP, 0, 40_000, text.strip())])
        m = compute_metrics(t)
        assert m.filler_rate_rep == 4.0

    def test_dead_air_excludes_leading_and_trailing(self):
        t = Transcript(
            call_id="c17",
            segments=[
                seg(0, REP, 10_000, 15_000, "Opening."),
                seg(1, BUYER, 25_000, 30_000, "Reply."),
            ],
        )
        m = compute_metrics(t, duration_ms=60_000)
        # Only the 10s internal gap counts, not the 10s lead-in or 30s tail.
        assert m.longest_dead_air_ms == 10_000


class TestTimeline:
    def test_buckets_cover_the_whole_call_without_gaps(self):
        t = Transcript(
            call_id="c18",
            segments=[
                seg(0, REP, 0, 60_000, "Rep half."),
                seg(1, BUYER, 60_000, 120_000, "Buyer half."),
            ],
        )
        m = compute_metrics(t)
        assert m.timeline[0].start_ms == 0
        assert m.timeline[-1].end_ms == m.duration_ms
        for a, b in zip(m.timeline, m.timeline[1:]):
            assert a.end_ms == b.start_ms

    def test_silent_bucket_is_neutral(self):
        t = Transcript(
            call_id="c19",
            segments=[
                seg(0, REP, 0, 5_000, "Hello."),
                seg(1, BUYER, 115_000, 120_000, "Goodbye."),
            ],
        )
        m = compute_metrics(t)
        middle = m.timeline[len(m.timeline) // 2]
        assert middle.rep_ms == 0 and middle.buyer_ms == 0
        assert middle.rep_share == 0.5
        assert middle.energy == 0.0

    def test_rep_share_reflects_who_held_the_floor(self):
        t = Transcript(
            call_id="c20",
            segments=[seg(0, REP, 0, 120_000, "All rep, all the time.")],
        )
        m = compute_metrics(t)
        assert m.timeline[0].rep_share == 1.0


class TestEmptyInput:
    def test_no_segments_returns_zeroed_metrics(self):
        m = compute_metrics(Transcript(call_id="empty", segments=[]), duration_ms=5_000)
        assert m.duration_ms == 5_000
        assert m.talk_ratio_rep == 0.0
        assert m.timeline == []


# --------------------------------------------------------------------------
# Scorecard
# --------------------------------------------------------------------------


class TestScorecard:
    def _metrics(self, **overrides):
        base = dict(
            call_id="c", duration_ms=600_000, rep_talk_ms=258_000,
            buyer_talk_ms=342_000, talk_ratio_rep=0.43, rep_question_rate_per_min=2.0,
            rep_question_count=20, open_question_ratio=0.65, rep_wpm=155.0,
            patience_ms=800.0, filler_rate_rep=1.0, longest_monologue_ms=60_000,
        )
        base.update(overrides)
        from salix.schemas.metrics import CallMetrics

        return CallMetrics(**base)

    def test_benchmark_call_scores_well_on_listening(self):
        card = build_scorecard(self._metrics())
        assert card.axis(SkillAxis.LISTENING) > 85

    def test_dominating_the_call_hurts_listening(self):
        card = build_scorecard(self._metrics(talk_ratio_rep=0.82))
        assert card.axis(SkillAxis.LISTENING) < 55

    def test_long_monologue_hurts_listening(self):
        good = build_scorecard(self._metrics()).axis(SkillAxis.LISTENING)
        bad = build_scorecard(
            self._metrics(longest_monologue_ms=210_000)
        ).axis(SkillAxis.LISTENING)
        assert bad < good

    def test_interruptions_penalise_listening(self):
        clean = build_scorecard(self._metrics()).axis(SkillAxis.LISTENING)
        talky = build_scorecard(
            self._metrics(interruptions_by_rep=4)
        ).axis(SkillAxis.LISTENING)
        # 4 interruptions hit the 30-point penalty cap.
        assert clean - talky == 30.0

    def test_interruption_penalty_is_capped(self):
        four = build_scorecard(self._metrics(interruptions_by_rep=4))
        twelve = build_scorecard(self._metrics(interruptions_by_rep=12))
        assert four.axis(SkillAxis.LISTENING) == twelve.axis(SkillAxis.LISTENING)

    def test_analysis_free_axes_return_neutral_and_say_so(self):
        card = build_scorecard(self._metrics())
        story = next(a for a in card.axes if a.axis is SkillAxis.STORYTELLING)
        assert story.score == 50.0
        assert "Awaiting" in story.drivers[0]

    def test_every_axis_present_and_in_range(self):
        card = build_scorecard(self._metrics())
        assert {a.axis for a in card.axes} == set(SkillAxis)
        assert all(0.0 <= a.score <= 100.0 for a in card.axes)
        assert 0.0 <= card.overall <= 100.0

    def test_drivers_are_always_populated(self):
        card = build_scorecard(self._metrics())
        assert all(a.drivers for a in card.axes)

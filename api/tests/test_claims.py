# -*- coding: utf-8 -*-
"""The landing page has to be true.

Salix's entire argument is that a number you cannot recompute is a number you
should not trust, and that nothing should be asserted without the evidence it
came from. The landing page then advertised "185 TESTS PASSING" from two
separate hard-coded literals, for a suite that had grown to several times
that, beside a badge reading QWEN LIVE on a deployment running Gemini with no
transcription at all.

Marketing copy rots silently because nothing executes it. This does.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

FACTS = Path(__file__).resolve().parents[2] / "web" / "lib" / "facts.ts"


def _claim(name: str) -> int:
    """Read a number out of web/lib/facts.ts without a JS runtime."""
    source = FACTS.read_text(encoding="utf-8")
    match = re.search(rf"export const {name} = (\d+);", source)
    assert match, f"{name} is not declared in {FACTS.name}"
    return int(match.group(1))


@pytest.mark.skipif(not FACTS.exists(), reason="frontend not present")
class TestAdvertisedNumbers:
    def test_the_test_count_on_the_landing_page_is_real(self):
        """The number the page prints is the number this suite collects.

        Counted in a subprocess rather than from the running session, because
        the session only knows what *this* invocation selected: running one
        file would make the claim look wrong, and `-k something` would make it
        look absurd. The question is what the whole suite holds, so ask that.

        Deliberately exact rather than a floor. "At least 185" would stay green
        forever while the page understated the work fourfold, which is the
        failure this exists to catch -- the claim being stale, not small.
        """
        import os
        import subprocess
        import sys

        # Collection is cheap and does not execute anything, but the guard
        # stops any chance of this recursing into itself.
        if os.environ.get("SALIX_COUNTING_TESTS"):
            pytest.skip("counting subprocess")

        result = subprocess.run(
            [sys.executable, "-m", "pytest", "--collect-only", "-q"],
            cwd=Path(__file__).resolve().parents[1],
            capture_output=True,
            text=True,
            env={**os.environ, "SALIX_COUNTING_TESTS": "1"},
            timeout=300,
        )
        match = re.search(r"(\d+)\s*/?\s*\d*\s*tests? collected", result.stdout)
        assert match, f"could not read a count from:\n{result.stdout[-600:]}"

        # Collection counts this test too -- the skip above happens at run
        # time, not at collection -- so this is the true total.
        collected = int(match.group(1))
        advertised = _claim("TEST_COUNT")

        assert advertised == collected, (
            f"web/lib/facts.ts advertises {advertised} tests, the suite "
            f"collects {collected}. Update TEST_COUNT."
        )

    def test_the_talk_ratio_benchmark_matches_the_engine(self):
        """The page names 43% and the scorecard has to agree."""
        from salix.metrics import benchmarks as B

        advertised = _claim("TALK_RATIO_BENCHMARK")
        assert abs(B.TALK_RATIO_TARGET * 100 - advertised) < 1.0

    def test_no_provider_is_named_in_the_frontend_facts(self):
        """Which model is running belongs to /api/health, not to a constant.

        A hard-coded "QWEN3.8-MAX" was correct until the reasoning layer could
        point at Gemini or Groq, and then it was a lie printed in the hero.
        """
        source = FACTS.read_text(encoding="utf-8").lower()
        for vendor in ("qwen3.8-max", "gemini-", "text-embedding-v4"):
            assert vendor not in source, f"{vendor} is hard-coded in facts.ts"


class TestAnalysisIsRepeatable:
    """The same call must not score differently on Tuesday.

    A recording was uploaded twice. Every measured number came back
    byte-identical -- 13 segments, 54% talk ratio, 267ms patience -- because
    that layer is arithmetic. The analysis did not: two objections and a score
    of 61 on the first run, three and a 65 on the second, from the same
    transcript.

    A sales manager cannot coach against a number that moves on its own, and
    the product's whole argument is that its numbers can be checked. So the
    agents that *read* a transcript sample nothing. The Dojo buyer still does,
    because a person who says the same sentence twice is not a person.

    Temperature zero reduces variation rather than abolishing it -- inference
    is not bit-reproducible -- but sampling was the part that was ours to fix.
    """

    EXTRACTION = {
        "anatomist": "objections, stages and MEDDIC coverage",
        "playwright": "which narrative plays a call contains",
        "coach": "a plan quoted from retrieved calls",
        "analyst": "an argument about a quarter that already happened",
    }

    @pytest.mark.parametrize("agent,what", sorted(EXTRACTION.items()))
    def test_the_reading_agents_do_not_sample(self, agent, what):
        import re
        from pathlib import Path

        source = (Path(__file__).resolve().parents[1] / "salix" / "agents"
                  / f"{agent}.py").read_text(encoding="utf-8")
        temperatures = [float(t) for t in re.findall(r"temperature=([0-9.]+)", source)]

        assert temperatures, f"{agent} sets no temperature"
        assert all(t == 0.0 for t in temperatures), (
            f"{agent} samples at {temperatures}, and it is extracting {what}"
        )

    def test_the_dojo_buyer_still_varies(self):
        """The one place sampling is right. A buyer who answers identically
        every time is a script, and the rep is practising against nothing."""
        import re
        from pathlib import Path

        source = (Path(__file__).resolve().parents[1] / "salix" / "dojo"
                  / "engine.py").read_text(encoding="utf-8")
        temperatures = [float(t) for t in re.findall(r"temperature=([0-9.]+)", source)]

        assert any(t > 0.5 for t in temperatures), (
            "the Dojo buyer should sample; only the reading agents should not"
        )

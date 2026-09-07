# -*- coding: utf-8 -*-
"""Put every transcript into Latin letters.

Salix offers two languages and both are written in Latin script: English, and
Roman Urdu -- Urdu vocabulary spelled the way a Pakistani colleague types it.
Speech recognition does not cooperate. Ask Deepgram for `ur` and it returns
Nastaliq; ask it for `multi` and Urdu speech comes back in Devanagari, which is
Hindi's script and which a Pakistani reader cannot read at all.

Neither is what the product shows anywhere else, and the Devanagari case is
worse than merely inconsistent: `detect_language` reads it as English, so an
Urdu call would be scored against English pace benchmarks with the Urdu
question detection never running -- wrong numbers, and no error to notice.

So the transcript is transliterated before anything measures it. Everything
downstream -- diarization, the metrics engine, the anatomy agent, the moment
index -- then sees one script, and it is the script the rest of the product
uses.

**Why a model rather than a table.** Urdu is an abjad: short vowels are mostly
not written. "کتاب" is k-t-a-b on the page and "kitaab" in speech, and no
character mapping recovers the missing vowel. A rule-based transliterator
produces something technically reversible and painful to read, which defeats
the point. The reasoning model is already configured, already good at Urdu, and
produces the spelling people actually use.

**What happens when it fails.** The original text, unchanged. A transcript in
Nastaliq is still measured correctly -- the engine handles Urdu script -- so
degrading to it costs consistency rather than correctness. Silently returning
half-transliterated text would cost both.
"""

from __future__ import annotations

import logging
import re
from typing import Sequence

from ..providers.base import ASRSentence, Providers

log = logging.getLogger("salix.pipeline.romanise")

#: Perso-Arabic (Urdu) and Devanagari (Hindi). The two scripts speech
#: recognition hands back for Urdu speech, and neither belongs on screen here.
NON_LATIN = re.compile(r"[؀-ۿݐ-ݿऀ-ॿﭐ-﷿ﹰ-﻿]")

#: Lines per request. Long enough that a whole call is usually one call to the
#: model, short enough that a mis-numbered reply loses a chunk rather than the
#: transcript.
BATCH = 40

SYSTEM = """\
You transliterate Urdu into Roman Urdu. You do not translate.

Roman Urdu is Urdu written in Latin letters, the way Pakistani colleagues
message each other: "Aap ki price bohat zyada hai, hamare paas budget nahi
hai."

RULES
- Transliterate the sound, not the meaning. "شکریہ" becomes "shukriya", never
  "thank you".
- Write the vowels that are spoken but not written. Urdu is an abjad; "کتاب"
  is "kitaab".
- English words already in the text stay exactly as they are: price, budget,
  team, system, renewal, process, reporting.
- Devanagari input is Urdu written in the wrong script. Transliterate it the
  same way.
- Spell phonetically and consistently.
- Output NOTHING in Urdu, Arabic or Devanagari script. Latin letters only.

FORMAT
- The input is numbered lines.
- Return exactly the same numbers, in the same order, one line each.
- Same count in, same count out. Never merge, split, reorder or drop a line.
- No commentary, no preamble, no code fences.
"""


def needs_romanising(sentences: Sequence[ASRSentence]) -> bool:
    return any(NON_LATIN.search(s.text or "") for s in sentences)


def _numbered(lines: Sequence[str]) -> str:
    return "\n".join(f"{i + 1}. {line}" for i, line in enumerate(lines))


def _parse(reply: str, expected: int) -> list[str] | None:
    """Read the numbered reply back, or refuse it.

    Returns None rather than a partial result on anything unexpected. These
    lines are about to be aligned with timestamps taken from the audio, so a
    transcript that is one line short is worse than one in the wrong script:
    every word after the gap would be attributed to the wrong moment, and to
    possibly the wrong speaker.
    """
    found: dict[int, str] = {}
    for raw in (reply or "").splitlines():
        match = re.match(r"\s*(\d+)\s*[.)]\s*(.*)$", raw)
        if not match:
            # Unnumbered text is commentary the model was asked not to add.
            # Ignoring it is safe; it carries no position.
            continue
        index = int(match.group(1))
        text = match.group(2).strip()

        # A number outside the range, or one seen twice, means the model
        # split or duplicated a line rather than transliterating it. Dropping
        # the surplus would quietly keep a truncated version of whatever was
        # split, so the whole batch is refused instead.
        if not 1 <= index <= expected or index in found:
            log.warning("romanise: line number %d is not one that was sent", index)
            return None
        if not text:
            log.warning("romanise: line %d came back empty", index)
            return None
        found[index] = text

    if len(found) != expected:
        log.warning("romanise: expected %d lines, parsed %d", expected, len(found))
        return None

    out = [found[i + 1] for i in range(expected)]
    if any(NON_LATIN.search(line) for line in out):
        log.warning("romanise: the reply still contains non-Latin script")
        return None
    return out


async def _batch(providers: Providers, lines: list[str]) -> list[str] | None:
    try:
        reply = await providers.llm.complete(
            system=SYSTEM,
            user=_numbered(lines),
            temperature=0.0,  # transliteration has a right answer
        )
    except Exception as exc:  # noqa: BLE001
        log.warning("romanise: model call failed (%s)", exc)
        return None
    return _parse(reply or "", len(lines))


async def romanise(
    providers: Providers, sentences: list[ASRSentence]
) -> tuple[list[ASRSentence], bool]:
    """Return the sentences in Latin script, and whether anything changed.

    Timestamps and speaker ids are carried across untouched: only the text is
    rewritten, and only when every line of a batch comes back clean.
    """
    if not sentences or not needs_romanising(sentences):
        return sentences, False

    texts = [s.text or "" for s in sentences]
    out = list(texts)
    converted = False

    for start in range(0, len(texts), BATCH):
        chunk = texts[start : start + BATCH]
        # A batch of pure English needs no round trip.
        if not any(NON_LATIN.search(line) for line in chunk):
            continue

        result = await _batch(providers, chunk)
        if result is None:
            log.warning(
                "romanise: keeping the original script for lines %d-%d",
                start + 1, start + len(chunk),
            )
            continue
        out[start : start + len(chunk)] = result
        converted = True

    if not converted:
        return sentences, False

    rewritten = [
        sentence.model_copy(update={"text": text})
        for sentence, text in zip(sentences, out)
    ]
    remaining = sum(1 for s in rewritten if NON_LATIN.search(s.text or ""))
    log.info(
        "romanise: %d/%d line(s) now in Latin script",
        len(rewritten) - remaining, len(rewritten),
    )
    return rewritten, True

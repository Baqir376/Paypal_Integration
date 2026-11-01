# -*- coding: utf-8 -*-
"""Work out what language a recording is in, without asking anybody.

Roman Urdu is a way of writing Urdu rather than a language anyone can hear, so
audio alone cannot separate it from Urdu. What can be told apart is how the call
was spoken, and that decides how it should be written:

    en        English throughout                     -> Latin script
    ur-roman  Urdu and English mixed, or Latin text  -> Latin script
              carrying Urdu vocabulary
    ur        Urdu throughout                        -> Nastaliq

The recogniser's first pass is `multi`, which copes with a call that switches
languages mid-sentence, and the script it answers in is the evidence. It writes
Urdu speech in Devanagari, so a transcript that is mostly Devanagari is an Urdu
call asked for in the wrong mode. That is worth a second pass as `ur`: the answer
comes back in the right script and is transcribed by the right model. If the
second pass fails, the first still stands and is transliterated instead.
"""

from __future__ import annotations

import logging
import re
from typing import Sequence

from ..metrics.engine import detect_language
from ..providers.base import ASRResult, ASRSentence, Providers

log = logging.getLogger("salix.pipeline.language")

_DEVANAGARI = re.compile(r"[ऀ-ॿ]")
_PERSO_ARABIC = re.compile(r"[؀-ۿݐ-ݿﭐ-﷿ﹰ-﻿]")
_LATIN = re.compile(r"[A-Za-z]")

#: At or above this share of letters not in Latin script, the call is Urdu. Set
#: from real recordings through Deepgram: a call in Urdu came back 100% Nastaliq,
#: and one switching between Urdu and English came back 82% once its English
#: stayed in Latin. Two samples, so treat the exact value as a starting point.
URDU_THROUGHOUT = 0.9
#: At or above this share it is code-switching. Below it, a stray word in another
#: script says nothing about the call.
CODE_SWITCHING = 0.1
#: This much Devanagari means Urdu speech heard in `multi` mode, and is worth
#: asking again as `ur` to find out how much of the call really was Urdu.
SECOND_PASS = 0.5

LABELS = {"en": "English", "ur": "Urdu", "ur-roman": "Roman Urdu"}


def _shares(sentences: Sequence[ASRSentence]) -> tuple[float, float]:
    """The share of letters in Devanagari and in Perso-Arabic script."""
    text = " ".join(s.text or "" for s in sentences)
    devanagari = len(_DEVANAGARI.findall(text))
    arabic = len(_PERSO_ARABIC.findall(text))
    total = devanagari + arabic + len(_LATIN.findall(text))
    if not total:
        return 0.0, 0.0
    return devanagari / total, arabic / total


def classify(sentences: Sequence[ASRSentence]) -> str:
    """'en', 'ur' or 'ur-roman', from the transcript alone."""
    devanagari, arabic = _shares(sentences)
    other_script = devanagari + arabic
    if other_script >= URDU_THROUGHOUT:
        return "ur"
    if other_script >= CODE_SWITCHING:
        return "ur-roman"
    return detect_language(" ".join(s.text or "" for s in sentences))


async def transcribe_detecting(
    providers: Providers, audio: str, *, requested: str = ""
) -> tuple[ASRResult, str]:
    """Transcribe, and say which language the result is in.

    `requested` is for API callers who know already. Nothing in the product sends
    it. `multi` is not a language, so it is still classified.
    """
    hints = (requested,) if requested else ()
    asr = await providers.asr.transcribe(audio, diarize=True, language_hints=hints)

    if requested and requested != "multi":
        return asr, requested

    language = classify(asr.sentences)
    if _shares(asr.sentences)[0] < SECOND_PASS:
        return asr, language

    try:
        second = await providers.asr.transcribe(audio, diarize=True, language_hints=("ur",))
    except Exception as exc:  # noqa: BLE001
        log.warning("second pass as Urdu failed (%s); keeping the first", exc)
        return asr, "ur-roman"

    # Code-switched calls keep the first pass: `multi` is the mode built for them.
    if classify(second.sentences) == "ur" and _shares(second.sentences)[0] < SECOND_PASS:
        return second, "ur"
    return asr, "ur-roman"

# -*- coding: utf-8 -*-
"""Neural speech for the languages nothing else here can say.

Windows ships no Urdu voice unless somebody installs the language pack, and no
sales floor is going to do that on twenty machines. Neither `qwen3-tts-flash`
nor `qwen-audio-3.0-tts` supports Urdu either -- they cover ten and sixteen
languages respectively and Urdu is in neither list -- so a DashScope key does
not solve it.

Microsoft's Edge read-aloud service does. It exposes the Azure neural voices,
including `ur-PK-UzmaNeural`, over a websocket that needs no key. That is what this provider talks to.

Two things are worth knowing before relying on it:

* It is an undocumented endpoint belonging to a browser feature. It is free and
  it works, but it can be rate-limited or withdrawn, so every failure returns
  cleanly rather than raising into a request handler.
* There is no `en-PK` voice. Roman Urdu is therefore read by an Indian English
  voice, because the phonetics land naturally that way -- an `ur-PK` voice
  handed Latin letters reads them as English spelled badly. Only Urdu *script*
  gets the native Urdu voice.

The buyer is always a woman. There used to be a male alternate per language and
a `male=` flag to select it, and nothing ever set it -- so it was an untested
branch whose only real effect was to make the voice table twice as easy to get
wrong. One voice per language, chosen because it reads that language well.
"""

from __future__ import annotations

import logging
import re
from typing import Optional

from .base import ProviderError

log = logging.getLogger("salix.providers.edge")

# Arabic / Urdu script, used to route a line to the right voice.
_URDU_RE = re.compile(r"[؀-ۿݐ-ݿﭐ-﷿ﹰ-﻿]")

#: One female voice per language. The names are Azure's.
VOICES: dict[str, str] = {
    "ur": "ur-PK-UzmaNeural",
    # Roman Urdu: Indian English, not Urdu, and not British. See the note above
    # -- Neerja reads Latin-script Urdu phonetically, which is what makes it
    # intelligible. A British voice reads the same letters as English and the
    # result is a Roman Urdu sentence delivered in an accent that cannot
    # pronounce it.
    "ur-roman": "en-IN-NeerjaNeural",
    "en": "en-GB-SoniaNeural",
}

#: What the rest of the app calls these languages.
#:
#: The frontend sends the tag it hands to *speech recognition*, which is a
#: different question from which voice should read the answer: Roman Urdu is
#: recognised as `en-PK` because Pakistani-accented English is the closest
#: acoustic model, but it must not be *spoken* as English. Without these
#: aliases `en-PK` fell through to the English voice, and every Roman Urdu
#: reply came back in a British accent.
ALIASES: dict[str, str] = {
    "roman": "ur-roman",
    "ur-pk": "ur",
    "ur-in": "ur",
    "en-pk": "ur-roman",
    "en-in": "ur-roman",
    "en-gb": "en",
    "en-us": "en",
}

MAX_CHARS = 1600

#: Roman Urdu read at conversational English pace sounds hesitant, because the
#: voice is sounding out syllables it does not recognise as words. A small
#: increase lands it closer to how the sentence is actually spoken.
RATE: dict[str, str] = {"ur-roman": "+5%"}


#: Markup a synthesiser would otherwise pronounce.
#:
#: The persona prompt forbids stage directions and asterisks, and a model
#: mostly obeys. "Mostly" is the problem: the one reply in fifty that arrives
#: as "**Dekhein**, baat yeh hai" is read aloud as "asterisk asterisk dekhein",
#: which breaks the illusion completely and in front of whoever is watching.
#: Cheaper to strip than to rely on instruction-following.
_MARKUP = (
    (re.compile(r"\*\*(.*?)\*\*", re.S), r"\1"),   # bold
    (re.compile(r"(?<!\w)\*(.*?)\*(?!\w)", re.S), r"\1"),  # italics, not a*b
    (re.compile(r"^\s*[-•*]\s+", re.M), ""),        # bullets
    (re.compile(r"^\s*#{1,6}\s+", re.M), ""),       # headings
    (re.compile(r"`{1,3}"), ""),                    # code ticks
    (re.compile(r"\((?:laughs|pauses|sighs)\)", re.I), ""),  # stage directions
)


def _speakable(text: str) -> str:
    """What is left once the things a voice should not say are removed."""
    line = (text or "").strip()
    for pattern, replacement in _MARKUP:
        line = pattern.sub(replacement, line)
    # Collapse the whitespace the substitutions leave behind.
    return re.sub(r"\s{2,}", " ", line).strip()


def language_key(text: str, language: str = "") -> str:
    """Which of the three voices should read this line.

    Urdu *script* in the text wins outright. That is not a guess: a line in
    Nastaliq has to be read by an Urdu voice whatever the session was opened
    in, and no other voice will make sense of it.

    Otherwise the declared language decides, through the alias table -- because
    what arrives is the recognition tag, not a voice key.
    """
    if _URDU_RE.search(text or ""):
        return "ur"

    declared = (language or "").strip().lower()
    if declared in VOICES:
        return declared
    if declared in ALIASES:
        return ALIASES[declared]
    return "en"


def voice_for(text: str, language: str = "") -> str:
    """The voice to read this line in. Always a woman's."""
    return VOICES[language_key(text, language)]


def rate_for(text: str, language: str = "") -> str:
    """Delivery speed, as edge-tts wants it."""
    return RATE.get(language_key(text, language), "+0%")


class EdgeTTS:
    """Free neural speech, including Urdu. No API key."""

    name = "edge"

    def __init__(self, settings=None):
        self.settings = settings

    def voices(self) -> list[str]:
        return list(VOICES.values())

    async def synthesize(
        self,
        text: str,
        *,
        voice: str = "",
        language: str = "",
        instruction: str = "",
        out_path: Optional[str] = None,
    ) -> bytes:
        line = _speakable(text)
        if not line:
            raise ProviderError("tts", "nothing to synthesise")

        # Imported here so the dependency is only paid for when speech is
        # actually asked for.
        try:
            import edge_tts
        except ImportError as exc:  # pragma: no cover - dependency is declared
            raise ProviderError("tts", "edge-tts is not installed") from exc

        chosen = voice if voice in self.voices() else voice_for(line, language)
        rate = rate_for(line, language)

        try:
            audio = bytearray()
            async for chunk in edge_tts.Communicate(
                line[:MAX_CHARS], chosen, rate=rate
            ).stream():
                if chunk["type"] == "audio":
                    audio.extend(chunk["data"])
        except Exception as exc:
            # Undocumented upstream. A clean failure lets the caller fall back
            # to saying nothing, which is the honest outcome.
            raise ProviderError("tts", f"edge tts unavailable: {exc}") from exc

        if not audio:
            raise ProviderError("tts", "edge tts returned no audio")

        if out_path:
            with open(out_path, "wb") as handle:
                handle.write(audio)

        log.debug("edge tts: %s at %s, %d bytes", chosen, rate, len(audio))
        return bytes(audio)

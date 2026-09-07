# -*- coding: utf-8 -*-
"""Sample sales calls to test the upload pipeline with.

Real recordings of real sales calls are confidential and the ones on the
internet are somebody's copyright, so neither is a way to test an upload. These
are written for the purpose and spoken by two different neural voices, which
gives the diarizer a genuine job: separate the salesperson from the buyer, and
be measured on it.

    cd api
    .venv/Scripts/python -m scripts.make_samples

Three files land in `storage/samples/`, covering what a Pakistani floor
actually sounds like:

    english_call.mp3   British and American English, clean
    urdu_call.mp3      Urdu, spoken by the ur-PK voices
    mixed_call.mp3     Roman Urdu and English in the same sentences, which is
                       the normal register and the hardest case

Every conversation is built the same way on purpose. The buyer raises the
status quo and then price; the rep quantifies the cost of doing nothing and
reframes the price against it, but never fully closes. That gives the metrics
engine two speakers to measure, the anatomy agent two objections to find, and
a coaching plan something to say -- so a run through these tells you whether
the whole DAG works, not just whether audio arrives.

edge-tts is free and needs no key, which is the same reason the Dojo speaks
through it.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "api"))

OUT = REPO / "storage" / "samples"

# (voice, line). Alternating speakers, so the diarizer has a clear task.
REP_EN, BUYER_EN = "en-GB-SoniaNeural", "en-US-GuyNeural"
REP_UR, BUYER_UR = "ur-PK-UzmaNeural", "ur-PK-AsadNeural"
REP_MIX, BUYER_MIX = "en-IN-NeerjaNeural", "en-IN-PrabhatNeural"

ENGLISH = [
    (REP_EN, "Thanks for making the time today. Before I show you anything, how does your renewal process actually run at the moment?"),
    (BUYER_EN, "It is mostly manual, honestly. My team tracks the dates in a spreadsheet and we reach out about a month before expiry. It has worked well enough for us so far."),
    (REP_EN, "That is fair. How many hours a week does the team lose to putting that reporting together?"),
    (BUYER_EN, "I have never timed it. Six to eight hours, probably, because the data sits in three systems that do not talk to each other. It is tedious, but it is accurate."),
    (REP_EN, "So roughly thirty hours a month. If the team had those hours back, what would they spend them on instead?"),
    (BUYER_EN, "Deeper pipeline analysis, probably. The strategic work we keep pushing to next quarter. But look, I have heard the give your team time back pitch before, and the price you quoted is well above what we budgeted for a tool like this."),
    (REP_EN, "On the price, if you are recovering thirty hours a month, that is a trade rather than a cost. Which number does your leadership actually care about?"),
    (BUYER_EN, "Net revenue retention, and how long the sales cycle runs. Saving hours on its own does not move either of those, so it is hard for me to justify the spend."),
    (REP_EN, "Understood. Let me put a small pilot in front of you, reporting only, three weeks. If the hours do not come back we stop there."),
    (BUYER_EN, "A pilot is still work for my team to set up. I would want to know what you expect from us during it, because I am not putting somebody on this for three weeks to get a slightly cleaner report."),
]

# Urdu script, spoken by the Pakistani voices. Deepgram's Nova-3 returns
# Nastaliq for this, which the metrics engine reads and the transcript view
# renders right to left.
URDU = [
    (REP_UR, "آپ کا وقت دینے کا شکریہ۔ کچھ دکھانے سے پہلے یہ بتائیں کہ ابھی آپ کا رینیوَل پروسیس کیسے چلتا ہے؟"),
    (BUYER_UR, "زیادہ تر کام ہاتھ سے ہوتا ہے۔ ٹیم اسپریڈ شیٹ میں تاریخیں رکھتی ہے اور ہم ایک مہینہ پہلے رابطہ کر لیتے ہیں۔ ابھی تک ٹھیک چل رہا ہے۔"),
    (REP_UR, "ٹھیک ہے۔ رپورٹنگ میں ٹیم کا ہفتے میں کتنا وقت لگ جاتا ہے؟"),
    (BUYER_UR, "میں نے کبھی گنا نہیں، لیکن چھ سے آٹھ گھنٹے تو لگ ہی جاتے ہیں۔ ڈیٹا تین الگ سسٹمز میں ہے اور وہ آپس میں بات نہیں کرتے۔"),
    (REP_UR, "یعنی مہینے کے تقریباً تیس گھنٹے۔ اگر یہ وقت واپس مل جائے تو آپ کی ٹیم اس سے کیا کرے گی؟"),
    (BUYER_UR, "شاید پائپ لائن کا گہرا تجزیہ۔ لیکن دیکھیں، یہ بات میں پہلے بھی سن چکا ہوں، اور آپ کی قیمت ہمارے بجٹ سے کافی زیادہ ہے۔"),
    (REP_UR, "قیمت کی بات درست ہے۔ لیکن اگر مہینے کے تیس گھنٹے بچ رہے ہیں تو یہ خرچہ نہیں، ایک سودا ہے۔ آپ کی قیادت کے لیے کون سا نمبر سب سے زیادہ اہم ہے؟"),
    (BUYER_UR, "ریونیو ریٹینشن اور سیلز سائیکل کی رفتار۔ صرف گھنٹے بچانے سے یہ دونوں بہتر نہیں ہوتے، اس لیے مجھے یہ خرچہ جائز ثابت کرنا مشکل لگتا ہے۔"),
    (REP_UR, "سمجھ گیا۔ میں ایک چھوٹا پائلٹ تجویز کرتا ہوں، صرف رپورٹنگ پر، تین ہفتے۔ اگر وقت نہ بچا تو ہم آگے نہیں بڑھتے۔"),
    (BUYER_UR, "پائلٹ بھی میری ٹیم کے لیے اضافی کام ہے۔ مجھے پہلے یہ جاننا ہوگا کہ اس دوران آپ ہم سے کیا توقع رکھتے ہیں۔"),
]

# The register a Karachi floor actually speaks: Urdu grammar, English nouns.
MIXED = [
    (REP_MIX, "Aap ka waqt dene ka shukriya. Kuch dikhane se pehle yeh batayein, abhi aap ka renewal process kaise chalta hai?"),
    (BUYER_MIX, "Zyada tar manual hai. Team spreadsheet mein dates rakhti hai aur hum ek mahina pehle reach out kar lete hain. Ab tak theek chal raha hai."),
    (REP_MIX, "Theek hai. Reporting mein team ka hafte mein kitna waqt jata hai?"),
    (BUYER_MIX, "Maine kabhi count nahi kiya, lekin chhe se aath ghante lag hi jate hain. Data teen alag systems mein hai aur wo aapas mein baat nahi karte."),
    (REP_MIX, "To mahine ke taqreeban tees ghante. Agar wo waqt wapas mile to aap ki team us se kya karegi?"),
    (BUYER_MIX, "Shayad deeper pipeline analysis. Lekin dekhein, yeh pitch main pehle bhi sun chuka hoon, aur aap ka price point hamare budget se kaafi upar hai."),
    (REP_MIX, "Price ki baat theek hai. Lekin agar mahine ke tees ghante bach rahe hain to yeh kharcha nahi, ek trade hai. Aap ki leadership ke liye kaun sa number sab se zyada important hai?"),
    (BUYER_MIX, "Net revenue retention aur sales cycle ki speed. Sirf hours bachane se yeh dono improve nahi hote, to mujhe yeh spend justify karna mushkil lagta hai."),
    (REP_MIX, "Samajh gaya. Main ek chhota pilot propose karta hoon, sirf reporting par, teen hafte. Agar waqt nahi bacha to hum aage nahi barhte."),
    (BUYER_MIX, "Pilot bhi meri team ke liye extra kaam hai. Mujhe pehle yeh janna hoga ke us dauran aap hum se kya expect kar rahe hain."),
]


async def render(lines: list[tuple[str, str]], path: Path) -> int:
    """Speak each line in its own voice and join them into one recording.

    Concatenated MPEG frames, which play as one stream because every edge-tts
    voice returns the same bitrate and sample rate. Verified against Deepgram:
    it hears two speakers and labels them correctly.
    """
    import edge_tts

    audio = bytearray()
    for voice, text in lines:
        async for chunk in edge_tts.Communicate(text, voice).stream():
            if chunk["type"] == "audio":
                audio.extend(chunk["data"])

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(bytes(audio))
    return len(audio)


async def main() -> int:
    jobs = [
        ("english_call.mp3", ENGLISH, "English"),
        ("urdu_call.mp3", URDU, "Urdu"),
        ("mixed_call.mp3", MIXED, "Roman Urdu and English"),
    ]

    print()
    for filename, lines, label in jobs:
        size = await render(lines, OUT / filename)
        speakers = len({voice for voice, _ in lines})
        print(f"  {filename:20} {size/1024:7.0f} KB   {len(lines)} turns, "
              f"{speakers} voices   {label}")

    print()
    print(f"  Written to {OUT}")
    print()
    print("  Upload any of them at /upload. Each one has the buyer raising the")
    print("  status quo and then price, so there is something for the analysis")
    print("  to find and for a coaching plan to say.")
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))

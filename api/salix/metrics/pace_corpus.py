# -*- coding: utf-8 -*-
"""Parallel sales speech, for calibrating pace across languages.

Words per minute is not comparable between languages, and treating it as
though it were is how an Urdu-speaking rep gets marked down for talking too
fast while saying exactly what their English-speaking colleague said.

The reason is structural rather than cultural. Urdu expresses with several
words what English expresses with one:

    "we can deploy"   ->  "ہم تعیناتی کر سکتے ہیں"    (3 words -> 5)
    "for you"         ->  "آپ کے لیے"                  (2 words -> 3)

Compound verbs, postpositions and light-verb constructions all split what
English fuses. So the same sentence, spoken in the same number of seconds,
produces a higher word count in Urdu — and a WPM benchmark set on English
reads that as rushing.

The correction rests on one published finding: languages converge on roughly
the same *information* rate (~39 bits/s) while their *speech* rates diverge
widely -- Coupé, Oh, Dediu & Pellegrino, "Different languages, similar
encoding efficiency", Science Advances 5(9), 2019. If information per second
is near-constant, then for identical content spoken in identical time, words
per minute scales with the number of words a language needs to carry that
content. That ratio is measurable from parallel text, which is what this file
is.

The study covers 17 languages and does not include Urdu, so the ratio is
derived here rather than cited. Published Urdu and Hindi figures were checked
and rejected: they disagree by a factor of two (one source reports 210 wpm,
another 100-110) and mostly describe read voiceover rather than conversation.
A number that decides how a rep is scored should come from evidence in this
repository that anyone can recompute, not from a blog post.

Every pair below is the same sales utterance, written naturally in each
language rather than translated word for word — a calque would inflate the
ratio and defeat the point.

Sentence length matters more than it looks. Urdu's overhead is largely fixed
per clause, so it shrinks as a share of a longer sentence: an earlier version
of this corpus averaged seven English words and produced a ratio of 1.19,
while the same sentences split by length gave 1.29 for six words or fewer and
1.08 for nine or more. Measured against a held-out call the true ratio was
1.12, so the short corpus over-corrected. These utterances are therefore
written at the length reps actually speak at — mostly fifteen to twenty words,
with a few short ones because real calls contain those too.

Replace them with transcripts of real Urdu calls the moment you have them;
`derive_ratios()` picks up the new numbers and the benchmarks move with it.
"""

from __future__ import annotations

import re

# (english, urdu, roman urdu)
PARALLEL: tuple[tuple[str, str, str], ...] = (
    (
        "Thanks for making the time today, I know the quarter end is busy for everyone.",
        "آج وقت دینے کا شکریہ، مجھے معلوم ہے کہ کوارٹر کے آخر میں سب مصروف ہوتے ہیں۔",
        "Aaj waqt dene ka shukriya, mujhe maloom hai ke quarter ke aakhir mein sab masroof hote hain.",
    ),
    (
        "Before we talk about pricing, I would like to understand how your team handles renewals today.",
        "قیمت پر بات کرنے سے پہلے میں سمجھنا چاہوں گا کہ آپ کی ٹیم آج رینیوَل کیسے سنبھالتی ہے۔",
        "Price par baat karne se pehle main samajhna chahoon ga ke aap ki team aaj renewals kaise sambhalti hai.",
    ),
    (
        "Where does most of the time actually go when a deal reaches the legal stage?",
        "جب کوئی ڈیل قانونی مرحلے پر پہنچتی ہے تو سب سے زیادہ وقت کہاں لگتا ہے؟",
        "Jab koi deal legal marhale par pahunchti hai to sab se zyada waqt kahan lagta hai?",
    ),
    (
        "It is spread across three account managers and a spreadsheet that nobody really owns.",
        "یہ تین اکاؤنٹ مینیجرز اور ایک ایسی شیٹ پر پھیلا ہوا ہے جس کا حقیقت میں کوئی مالک نہیں۔",
        "Ye teen account managers aur ek aisi sheet par phaila hua hai jis ka haqeeqat mein koi malik nahi.",
    ),
    (
        "If nothing changes for another quarter, what does that actually cost the business?",
        "اگر ایک اور کوارٹر کچھ نہ بدلا تو اس کی حقیقی قیمت کاروبار کو کیا پڑے گی؟",
        "Agar ek aur quarter kuch na badla to is ki haqeeqi cost business ko kya paregi?",
    ),
    (
        "Roughly two people worth of wasted effort every quarter, and probably more than that.",
        "ہر کوارٹر تقریباً دو افراد کی محنت ضائع ہوتی ہے، اور شاید اس سے بھی زیادہ۔",
        "Har quarter taqreeban do afraad ki mehnat zaaya hoti hai, aur shayad is se bhi zyada.",
    ),
    (
        "That number is well beyond what we were expecting and beyond the budget we approved.",
        "یہ رقم ہماری توقع سے کہیں زیادہ ہے اور اس بجٹ سے بھی زیادہ جو ہم نے منظور کیا تھا۔",
        "Ye raqam hamari tawaqqo se kahin zyada hai aur us budget se bhi zyada jo hum ne manzoor kiya tha.",
    ),
    (
        "I understand the concern about migration, and I would rather be straightforward than let this run on.",
        "منتقلی کے بارے میں آپ کی فکر مجھے سمجھ آتی ہے، اور میں اسے کھینچنے کے بجائے صاف بات کرنا چاہوں گا۔",
        "Migration ke baare mein aap ki fikr mujhe samajh aati hai, aur main ise khenchne ke bajaye saaf baat karna chahoon ga.",
    ),
    (
        "Let me show you where we are actually different, and you can judge whether that is worth a move.",
        "میں آپ کو دکھاتا ہوں کہ ہم واقعی کہاں مختلف ہیں، اور آپ خود فیصلہ کریں کہ یہ تبدیلی کے قابل ہے یا نہیں۔",
        "Main aap ko dikhata hoon ke hum waqai kahan mukhtalif hain, aur aap khud faisla karen ke ye tabdeeli ke qabil hai ya nahi.",
    ),
    (
        "Who else needs to be in the room before a decision like this can move forward?",
        "ایسا فیصلہ آگے بڑھنے سے پہلے اور کن لوگوں کا کمرے میں ہونا ضروری ہے؟",
        "Aisa faisla aage barhne se pehle aur kin logon ka kamre mein hona zaroori hai?",
    ),
    (
        "We can have this deployed in about two weeks, including training for the whole team.",
        "ہم اسے تقریباً دو ہفتوں میں نافذ کر سکتے ہیں، پوری ٹیم کی تربیت سمیت۔",
        "Hum ise taqreeban do hafton mein nafiz kar sakte hain, poori team ki training samet.",
    ),
    (
        "The northern team would resist anything new right now because they have had a genuinely rough quarter.",
        "شمالی ٹیم اس وقت کسی بھی نئی چیز کی مخالفت کرے گی کیونکہ ان کا کوارٹر واقعی مشکل گزرا ہے۔",
        "Northern team is waqt kisi bhi nai cheez ki mukhalifat kare gi kyunke un ka quarter waqai mushkil guzra hai.",
    ),
    (
        "What would you need to see from us before you would be comfortable moving ahead?",
        "آگے بڑھنے سے پہلے آپ کو ہماری طرف سے کیا دیکھنا ہوگا تاکہ آپ مطمئن ہوں؟",
        "Aage barhne se pehle aap ko hamari taraf se kya dekhna hoga taake aap mutmain hon?",
    ),
    (
        "I skimmed the pricing page and shared it with my finance director, and neither of us got far.",
        "میں نے قیمت کا صفحہ دیکھا اور اپنے فنانس ڈائریکٹر کو بھیجا، اور ہم دونوں زیادہ آگے نہیں بڑھ سکے۔",
        "Main ne price ka safha dekha aur apne finance director ko bheja, aur hum dono zyada aage nahi barh sake.",
    ),
    (
        "Can we put thirty minutes with your finance team in the calendar for next week?",
        "کیا ہم اگلے ہفتے آپ کی فنانس ٹیم کے ساتھ تیس منٹ کیلنڈر میں رکھ سکتے ہیں؟",
        "Kya hum agle hafte aap ki finance team ke saath tees minute calendar mein rakh sakte hain?",
    ),
    (
        "There is no central tracker and there never really has been, which is the honest answer.",
        "کوئی مرکزی ٹریکر نہیں ہے اور کبھی تھا بھی نہیں، یہی سچی بات ہے۔",
        "Koi markazi tracker nahi hai aur kabhi tha bhi nahi, yehi sachi baat hai.",
    ),
    (
        "We looked at something quite similar last year and it stalled, so why would this be different?",
        "ہم نے پچھلے سال ایسی ہی چیز دیکھی تھی اور وہ رک گئی، تو یہ مختلف کیوں ہوگی؟",
        "Hum ne pichle saal aisi hi cheez dekhi thi aur wo ruk gai, to ye mukhtalif kyun hogi?",
    ),
    (
        "I will send a short summary this evening with the three things we agreed to check.",
        "میں آج شام ایک مختصر خلاصہ بھیج دوں گا جس میں وہ تین چیزیں ہوں گی جن پر ہم متفق ہوئے۔",
        "Main aaj shaam ek mukhtasar khulasa bhej doon ga jis mein wo teen cheezen hon gi jin par hum muttafiq hue.",
    ),
    (
        "Tell me more about that, because it sounds like the real problem sits upstream of the tooling.",
        "اس کے بارے میں مزید بتائیے، کیونکہ لگتا ہے اصل مسئلہ ٹولنگ سے پہلے کہیں ہے۔",
        "Is ke baare mein mazeed bataiye, kyunke lagta hai asal masla tooling se pehle kahin hai.",
    ),
    (
        "How quickly do you need this working before it stops being useful to you this year?",
        "آپ کو یہ کتنی جلدی چاہیے اس سے پہلے کہ اس سال یہ آپ کے کام کا نہ رہے؟",
        "Aap ko ye kitni jaldi chahiye is se pehle ke is saal ye aap ke kaam ka na rahe?",
    ),
    (
        "That is a fair question, and I do not think a discount is the honest answer to it.",
        "یہ مناسب سوال ہے، اور میرے خیال میں رعایت اس کا ایماندارانہ جواب نہیں ہے۔",
        "Ye munasib sawal hai, aur mere khayal mein riayat is ka imandarana jawab nahi hai.",
    ),
    (
        "Thanks, that helps.",
        "شکریہ، اس سے مدد ملی۔",
        "Shukriya, is se madad mili.",
    ),
    (
        "Understood, I will follow up next week.",
        "سمجھ گیا، میں اگلے ہفتے رابطہ کروں گا۔",
        "Samajh gaya, main agle hafte raabta karoon ga.",
    ),
    (
        "Who signs this off on your side?",
        "آپ کی طرف سے اس کی منظوری کون دیتا ہے؟",
        "Aap ki taraf se is ki manzoori kaun deta hai?",
    ),
)


def _words(text: str) -> int:
    """Whitespace words, matching how the engine counts them everywhere else."""
    return len([w for w in text.split() if w.strip()])


def derive_ratios() -> dict[str, float]:
    """Words needed per language, relative to English, for the same content.

    Totals rather than a mean of per-sentence ratios: a two-word sentence and a
    twenty-word one should not carry equal weight in a rate calibration.
    """
    en = sum(_words(row[0]) for row in PARALLEL)
    ur = sum(_words(row[1]) for row in PARALLEL)
    ro = sum(_words(row[2]) for row in PARALLEL)
    return {
        "en": 1.0,
        "ur": round(ur / en, 4),
        "ur-roman": round(ro / en, 4),
    }

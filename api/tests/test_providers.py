"""Tests for the provider layer.

The contract that matters: offline mode must produce valid, correctly-shaped
output for *any* schema, because that is what keeps the system runnable without
an API key.
"""

from __future__ import annotations

import pytest

from salix.config import ProviderMode, Settings
from salix.providers.dashscope_llm import extract_json
from salix.providers.mock import MockASR, MockEmbeddings, MockLLM
from salix.schemas.analysis import CallAnalysis
from salix.schemas.coaching import CoachingPlan, GeneratedScript
from salix.schemas.deal import DealTrajectory
from salix.schemas.dojo import BuyerPersona
from salix.schemas.play import PlayCandidate
from salix.schemas.report import CycleReport


class TestExtractJson:
    def test_clean_object(self):
        assert extract_json('{"a": 1}') == '{"a": 1}'

    def test_markdown_fence(self):
        assert extract_json('```json\n{"a": 1}\n```') == '{"a": 1}'

    def test_bare_fence(self):
        assert extract_json('```\n{"a": 1}\n```') == '{"a": 1}'

    def test_surrounding_prose(self):
        raw = 'Here you go:\n{"a": 1}\nHope that helps!'
        assert extract_json(raw) == '{"a": 1}'

    def test_nested_braces_keep_outermost(self):
        raw = '{"a": {"b": 2}}'
        assert extract_json(raw) == raw

    def test_empty_raises(self):
        with pytest.raises(ValueError):
            extract_json("   ")

    def test_no_object_raises(self):
        with pytest.raises(ValueError):
            extract_json("no json at all here")


class TestMockLLMStructured:
    """Any schema, always valid. A new model must never break offline mode."""

    @pytest.mark.parametrize(
        "schema",
        [
            CallAnalysis, PlayCandidate, CoachingPlan, GeneratedScript,
            DealTrajectory, CycleReport, BuyerPersona,
        ],
    )
    async def test_returns_valid_instance(self, schema):
        llm = MockLLM()
        result = await llm.structured(system="s", user="u", schema=schema)
        assert isinstance(result, schema)
        # Round-trips cleanly, which is what the pipeline relies on.
        assert schema.model_validate_json(result.model_dump_json())

    async def test_deterministic_for_same_input(self):
        llm = MockLLM()
        a = await llm.structured(system="s", user="u", schema=PlayCandidate)
        b = await llm.structured(system="s", user="u", schema=PlayCandidate)
        assert a.model_dump_json() == b.model_dump_json()

    async def test_reads_the_transcript_for_call_analysis(self):
        transcript = (
            "[s0001] (00:00) REP: Thanks for making time today.\n"
            "[s0002] (00:12) BUYER: Honestly the pricing looks expensive for us.\n"
            "[s0003] (00:30) REP: I hear that. Let me send you the ROI model Monday.\n"
        )
        llm = MockLLM()
        result = await llm.structured(
            system="analyse", user=transcript, schema=CallAnalysis
        )
        assert result.objections, "keyword cue 'expensive' should surface an objection"
        assert result.objections[0].category.value == "price"
        assert result.objections[0].raised.segment_id == "s0002"
        assert result.next_step is not None
        assert result.next_step.has_date is True


class TestMockASR:
    SCRIPT = (
        "# a comment line that must be ignored\n"
        "REP: Good morning, thanks for making the time.\n"
        "BUYER: Of course. We have about thirty minutes.\n"
        "REP: Perfect. What does your current process look like?\n"
    )

    def test_parses_script_into_diarized_sentences(self):
        result = MockASR.from_script(self.SCRIPT)
        assert len(result.sentences) == 3
        assert [s.speaker_id for s in result.sentences] == [0, 1, 0]

    def test_timestamps_are_monotonic_and_non_overlapping(self):
        result = MockASR.from_script(self.SCRIPT)
        for a, b in zip(result.sentences, result.sentences[1:]):
            assert a.end_time > a.begin_time
            assert b.begin_time >= a.end_time

    def test_duration_covers_final_sentence(self):
        result = MockASR.from_script(self.SCRIPT)
        assert result.duration_ms >= result.sentences[-1].end_time

    def test_longer_lines_take_longer_to_say(self):
        short = MockASR.from_script("REP: Yes.\n").sentences[0]
        long = MockASR.from_script(
            "REP: " + " ".join(["word"] * 100) + "\n"
        ).sentences[0]
        assert (long.end_time - long.begin_time) > (short.end_time - short.begin_time)

    def test_deterministic(self):
        a = MockASR.from_script(self.SCRIPT)
        b = MockASR.from_script(self.SCRIPT)
        assert a.model_dump_json() == b.model_dump_json()

    def test_empty_script_raises(self):
        with pytest.raises(ValueError):
            MockASR.from_script("# nothing here\n")


class TestMockEmbeddings:
    async def test_shape_and_normalisation(self):
        provider = MockEmbeddings()
        vectors = await provider.embed(["alpha", "beta"])
        assert len(vectors) == 2
        assert all(len(v) == provider.dim for v in vectors)
        for v in vectors:
            norm = sum(x * x for x in v) ** 0.5
            assert abs(norm - 1.0) < 1e-6

    async def test_stable_for_identical_text(self):
        provider = MockEmbeddings()
        first = await provider.embed(["the compounding cost story"])
        second = await provider.embed(["The Compounding Cost Story"])
        assert first[0] == second[0], "case-insensitive and deterministic"

    async def test_different_text_differs(self):
        provider = MockEmbeddings()
        vectors = await provider.embed(["alpha", "completely different"])
        assert vectors[0] != vectors[1]

    async def test_empty_input(self):
        assert await MockEmbeddings().embed([]) == []


class TestPortableEmbeddings:
    """Semantic search without a payment card.

    Alibaba requires one for identity verification, which puts real embeddings
    out of reach for anybody who cannot give it -- and the offline twin hashes
    text into a stable vector, so the whole retrieval path runs and returns
    passages unrelated to the question. The playbook then cites an arbitrary
    colleague's call instead of the relevant one, which is worse than citing
    nothing.

    `embeddings.create` is part of the OpenAI protocol, so any compatible
    endpoint hosting an embedding model can serve them. Naming that model is
    enough.
    """

    def test_a_dashscope_key_alone_is_still_enough(self):
        s = Settings(provider_mode=ProviderMode.AUTO, dashscope_api_key="sk-x")
        assert s.embeddings_is_live is True
        assert s.embedding_model == "text-embedding-v4"

    def test_a_text_key_alone_is_not(self):
        """Groq has no embedding model; claiming otherwise would ship a
        provider that fails on the first search."""
        s = Settings(
            provider_mode=ProviderMode.AUTO,
            llm_api_key="gsk-x",
            llm_base_url="https://api.groq.com/openai/v1",
        )
        assert s.llm_is_live is True
        assert s.embeddings_is_live is False

    def test_naming_an_embedding_model_turns_them_on(self):
        s = Settings(
            provider_mode=ProviderMode.AUTO,
            llm_api_key="g-x",
            llm_base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
            llm_model_embedding="gemini-embedding-001",
        )
        assert s.embeddings_is_live is True
        assert s.embedding_model == "gemini-embedding-001"
        assert "googleapis" in s.embedding_endpoint
        assert s.embedding_key == "g-x"

    def test_dashscope_wins_when_both_are_configured(self):
        """It is the one that also does transcription, so keeping every vector
        on one provider avoids a re-seed when the other is removed."""
        s = Settings(
            provider_mode=ProviderMode.AUTO,
            dashscope_api_key="sk-x",
            llm_api_key="g-x",
            llm_base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
            llm_model_embedding="gemini-embedding-001",
        )
        assert s.embedding_model == "text-embedding-v4"
        assert s.embedding_key == "sk-x"
        assert "aliyuncs" in s.embedding_endpoint

    def test_transcription_stays_dashscope_only(self):
        """Diarization has no standard protocol; nothing else can stand in."""
        s = Settings(
            provider_mode=ProviderMode.AUTO,
            llm_api_key="g-x",
            llm_base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
            llm_model_embedding="gemini-embedding-001",
        )
        assert s.dashscope_is_live is False

    def test_the_provider_reports_who_is_answering(self):
        from salix.providers.dashscope_llm import DashScopeEmbeddings

        gemini = DashScopeEmbeddings(
            Settings(
                llm_api_key="g-x",
                llm_base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
                llm_model_embedding="gemini-embedding-001",
            )
        )
        assert gemini.name == "google gemini"
        assert DashScopeEmbeddings(Settings(dashscope_api_key="sk-x")).name == "dashscope"

    async def test_a_wrong_width_is_refused_rather_than_stored(self):
        """The index has a fixed width. A model returning another would corrupt
        every comparison against rows already written, and silently: cosine
        against a truncated vector still returns a number."""
        from salix.providers.base import ProviderError
        from salix.providers.dashscope_llm import DashScopeEmbeddings

        provider = DashScopeEmbeddings(Settings(dashscope_api_key="sk-x", embedding_dim=1024))

        class Item:
            embedding = [0.1] * 768

        class Response:
            data = [Item()]

        async def _create(batch):
            return Response()

        provider._create = _create

        with pytest.raises(ProviderError) as caught:
            await provider.embed(["anything"])
        assert "768" in str(caught.value)
        assert "SALIX_EMBEDDING_DIM" in str(caught.value)

    async def test_an_endpoint_that_rejects_dimensions_is_retried_without_it(self):
        """`dimensions` is optional in the protocol and not universally
        implemented. Sending it to a host that refuses it fails the whole call,
        and the only way to find out is to be told."""
        from salix.providers.dashscope_llm import DashScopeEmbeddings

        provider = DashScopeEmbeddings(Settings(dashscope_api_key="sk-x", embedding_dim=4))
        seen = []

        class Item:
            embedding = [0.5, 0.5, 0.5, 0.5]

        class Response:
            data = [Item()]

        class FakeEmbeddings:
            async def create(self, **kwargs):
                seen.append("dimensions" in kwargs)
                if "dimensions" in kwargs:
                    raise ValueError("Unsupported parameter: dimensions")
                return Response()

        provider._client = type("C", (), {"embeddings": FakeEmbeddings()})()

        assert await provider.embed(["a"]) == [[0.5, 0.5, 0.5, 0.5]]
        assert seen == [True, False]

        # And it does not ask again.
        seen.clear()
        await provider.embed(["b"])
        assert seen == [False]


class TestSessionLanguage:
    """Two languages, and the buyer has to actually answer in the chosen one.

    The persona prompt used to say nothing about language at all, so the model
    simply mirrored whatever it was handed. That is fine for English and wrong
    for Roman Urdu: a model given Latin-script Urdu recognises the language and
    replies in Nastaliq, which a rep who types in Latin letters cannot read
    back at a glance.
    """

    def _persona(self):
        from salix.schemas.dojo import BuyerPersona

        return BuyerPersona(
            id="persona_test",
            name="Priya Nair",
            title="COO",
            company="Northwind",
            context="Renewal season, stretched team.",
            disposition="Sceptical but fair.",
            objections=[],
        )

    def test_english_is_the_default(self):
        from salix.dojo.engine import persona_system_prompt

        prompt = persona_system_prompt(self._persona())
        assert "Reply in English" in prompt

    def test_roman_urdu_forbids_the_script_explicitly(self):
        """The instruction has to be blunt. A polite preference gets ignored."""
        from salix.dojo.engine import persona_system_prompt

        prompt = persona_system_prompt(self._persona(), "ur-roman")
        assert "ROMAN URDU" in prompt
        assert "NEVER use Urdu or Arabic script" in prompt
        assert "Nastaliq" in prompt

    def test_the_roman_urdu_rules_carry_an_example(self):
        """Naming a language is weaker than showing a sentence in it."""
        from salix.dojo.engine import persona_system_prompt

        prompt = persona_system_prompt(self._persona(), "ur-roman")
        assert "Dekhein" in prompt

    def test_the_instruction_itself_contains_no_urdu_script(self):
        """A prompt that says 'never use this script' while using it is a
        contradiction the model resolves in the wrong direction."""
        import re

        from salix.dojo.engine import LANGUAGE_RULES

        urdu = re.compile(r"[؀-ۿ]")
        for language, rules in LANGUAGE_RULES.items():
            assert not urdu.search(rules), language

    def test_an_unknown_language_falls_back_to_english(self):
        from salix.dojo.engine import persona_system_prompt

        prompt = persona_system_prompt(self._persona(), "klingon")
        assert "Reply in English" in prompt

    def test_the_session_records_what_it_was_opened_in(self):
        from salix.dojo.engine import DojoEngine

        engine = DojoEngine(providers=None)
        assert engine.start("r1", self._persona(), language="ur-roman").language == "ur-roman"
        assert engine.start("r1", self._persona()).language == "en"

    def test_a_junk_language_never_reaches_the_prompt(self):
        """Stored unvalidated it would silently select no rules at all."""
        from salix.dojo.engine import DojoEngine

        engine = DojoEngine(providers=None)
        assert engine.start("r1", self._persona(), language="ur-PK").language == "en"
        assert engine.start("r1", self._persona(), language="").language == "en"

    def test_every_persona_name_is_a_woman(self):
        """The voice is a woman and the Urdu grammar is feminine, so the name
        has to agree.

        Half the list used to be men. English hid it -- verbs there do not
        agree with the speaker -- but in Urdu it read as "Tomas Lindqvist bol
        rahi hoon": a Scandinavian man's name, feminine grammar, and a woman's
        voice, all describing the same person in one sentence.
        """
        from salix.dojo.persona import NAMES

        masculine = {
            "tomas", "henrik", "owen", "marcus", "daniyal", "bilal", "ahmed",
            "james", "david", "peter", "john", "michael", "carlos", "raj",
        }
        for name in NAMES:
            first = name.split()[0].lower()
            assert first not in masculine, name

    def test_the_buyer_speaks_of_herself_in_the_feminine(self):
        """Urdu verbs agree with the speaker's gender.

        The buyer is voiced by a woman in every language, so "bol raha hoon"
        under a female voice is a contradiction a Pakistani rep hears in the
        first second. The model has to be told; it will otherwise default to
        the masculine.
        """
        from salix.dojo.engine import persona_system_prompt

        prompt = persona_system_prompt(self._persona(), "ur-roman")
        assert "You are a woman" in prompt
        assert "rahi hoon" in prompt

    def test_the_roman_urdu_opening_uses_the_feminine(self):
        from salix.routers.dojo import _opening_line

        opening = _opening_line(self._persona(), "ur-roman")
        assert "bol rahi hoon" in opening
        assert "bol raha hoon" not in opening

    def test_the_english_opening_is_unchanged(self):
        from salix.routers.dojo import _opening_line

        assert "Hi," in _opening_line(self._persona(), "en")

    def test_only_two_languages_are_offered(self):
        """The product offers English and Roman Urdu. If a third is added, this
        test should be updated deliberately rather than pass by accident."""
        from salix.dojo.engine import LANGUAGE_RULES

        assert set(LANGUAGE_RULES) == {"en", "ur-roman"}


class TestVoice:
    """The buyer is always a woman, and always in the right accent.

    Two separate bugs live here. The first is gender: there used to be a male
    alternate per language behind a flag nothing ever set. The second is more
    subtle and was the audible one -- the frontend sent the tag it hands to
    *speech recognition*, and Roman Urdu is recognised as `en-PK` because
    Pakistani-accented English is the closest acoustic model. Asking a
    synthesiser that same question returned the British English voice, so every
    Roman Urdu reply came back in an accent that cannot pronounce it.
    """

    FEMALE = {"ur-PK-UzmaNeural", "en-IN-NeerjaNeural", "en-GB-SoniaNeural"}

    def test_every_voice_offered_is_female(self):
        from salix.providers.edge_voice import VOICES

        assert set(VOICES.values()) == self.FEMALE

    def test_no_male_voice_survives_anywhere(self):
        """The male names are gone from the table, not merely unreachable."""
        from salix.providers.edge_voice import VOICES

        for name in ("AsadNeural", "PrabhatNeural", "RyanNeural"):
            assert not any(name in v for v in VOICES.values()), name

    @pytest.mark.parametrize(
        "language,expected",
        [
            ("ur-roman", "en-IN-NeerjaNeural"),
            ("roman", "en-IN-NeerjaNeural"),
            # The bug: this is what the frontend actually sent.
            ("en-PK", "en-IN-NeerjaNeural"),
            ("en-IN", "en-IN-NeerjaNeural"),
            ("en", "en-GB-SoniaNeural"),
            ("en-GB", "en-GB-SoniaNeural"),
            ("en-US", "en-GB-SoniaNeural"),
            ("ur", "ur-PK-UzmaNeural"),
            ("ur-PK", "ur-PK-UzmaNeural"),
        ],
    )
    def test_the_tag_reaches_the_right_voice(self, language, expected):
        from salix.providers.edge_voice import voice_for

        assert voice_for("Dekhein, mujhe abhi zaroorat nahi.", language) == expected

    def test_roman_urdu_is_never_read_in_a_british_accent(self):
        """The regression, stated as itself."""
        from salix.providers.edge_voice import voice_for

        line = "Aap ki price bohat zyada hai, budget nahi hai."
        for tag in ("roman", "ur-roman", "en-PK", "en-IN"):
            assert voice_for(line, tag) == "en-IN-NeerjaNeural", tag

    def test_urdu_script_overrides_whatever_was_declared(self):
        """A Nastaliq line has to be read by the Urdu voice regardless of the
        session, because no other voice can make sense of it."""
        from salix.providers.edge_voice import voice_for

        assert voice_for("آپ کی قیمت زیادہ ہے", "en") == "ur-PK-UzmaNeural"

    def test_an_unknown_tag_falls_back_to_english(self):
        from salix.providers.edge_voice import voice_for

        assert voice_for("hello", "klingon") == "en-GB-SoniaNeural"
        assert voice_for("hello", "") == "en-GB-SoniaNeural"

    def test_roman_urdu_is_read_slightly_faster(self):
        """At English pace the voice sounds hesitant: it is sounding out
        syllables it does not recognise as words."""
        from salix.providers.edge_voice import rate_for

        assert rate_for("Dekhein", "ur-roman") == "+5%"
        assert rate_for("Look", "en") == "+0%"

    @pytest.mark.parametrize(
        "raw,spoken",
        [
            ("**Dekhein**, baat yeh hai", "Dekhein, baat yeh hai"),
            ("*really* not sure", "really not sure"),
            ("- first point", "first point"),
            ("## Heading", "Heading"),
            ("(laughs) no thanks", "no thanks"),
            ("`code`", "code"),
            ("plain sentence", "plain sentence"),
        ],
    )
    def test_markup_is_not_read_aloud(self, raw, spoken):
        """The prompt forbids asterisks and a model mostly obeys. The one reply
        in fifty that arrives bold is read as "asterisk asterisk dekhein"."""
        from salix.providers.edge_voice import _speakable

        assert _speakable(raw) == spoken

    def test_multiplication_is_not_mistaken_for_italics(self):
        from salix.providers.edge_voice import _speakable

        assert _speakable("2*3 is six") == "2*3 is six"


class TestObjectionsHandled:
    """Credit for engaging with an objection, from a real session.

    Every line below is verbatim from a Roman Urdu practice session run through
    the live model and scored 0/2 -- on a conversation where the rep quantified
    the cost of the status quo, reframed price as a trade against 25-30 hours a
    month, and closed on a pilot with a walk-away condition. That is textbook
    objection handling and the engine saw none of it.

    Two causes, hiding each other:

    1. It required a literal "?" in the rep's text. Dictation does not produce
       question marks, and speaking is the Dojo's primary mode -- so a spoken
       session could never be credited with handling anything at all.
    2. The category vocabulary was English-only, so "theek hai" and "aadat"
       -- how somebody actually declines to change -- matched nothing.
    """

    def _session(self, rep_lines, buyer_lines, categories):
        from salix.schemas.common import ObjectionCategory
        from salix.schemas.dojo import BuyerPersona, DojoSession, DojoTurn, PersonaObjection

        turns, clock = [], 0
        for index, (rep, buyer) in enumerate(zip(rep_lines, buyer_lines)):
            turns.append(DojoTurn(index=len(turns), speaker="rep", text=rep,
                                  start_ms=clock, end_ms=clock + 4000))
            clock += 4500
            turns.append(DojoTurn(index=len(turns), speaker="buyer", text=buyer,
                                  start_ms=clock, end_ms=clock + 5000))
            clock += 5500

        return DojoSession(
            id="dojo_test", rep_id="r1", language="ur-roman",
            persona=BuyerPersona(
                id="p1", name="Priya Nair", title="COO", company="Northwind",
                context="", disposition="",
                objections=[
                    PersonaObjection(category=ObjectionCategory(c), text="", hardness=0.6)
                    for c in categories
                ],
            ),
            turns=turns,
        )

    # The session as it actually happened, with dictation's missing punctuation.
    REP = [
        "as-salamu alaykum sirf yah sab ke abhi aapke renewal process Kaise chalta hai",
        "bilkul Agar kam to theek hai bus yah bataen reporting Mein team ke Hafte mein kitne Waqt jata hai",
        "to mahine mein agar vah Waqt Wapas Mile To aapki team usse kya karti",
        "price Ki Baat theek hai lekin Agar 25 se 30 ghante Bach rahe hain to yah kharcha Nahin Ek trade hai "
        "aapki leadership ke liye kaun sa number sabse Jyada Mane Rakhta hai",
    ]
    BUYER = [
        "Dekhein abhi humara jo system chal raha hai wo kaafi had tak manual hai lekin team ko iski aadat ho "
        "gayi hai. Aap batayein aapko kyun lagta hai ke mujhe isey change karne ki zaroorat hai",
        "Hafte mein taqreeban 6 se 8 ghante nikal jaate hain. Mujhe samajh nahi aa raha ke itna bara "
        "investment karne ka kya faida hoga jabke budget humara pehle hi tight hai",
        "Lekin baat wahi hai. Aapka solution humare existing budget se kaafi upar ja raha hai",
        "Meri leadership team tab impress hoti hai jab hum operational costs ko direct impact karte hain",
    ]

    def test_the_real_session_is_credited(self):
        from salix.dojo.engine import DojoEngine

        session = self._session(self.REP, self.BUYER, ["price", "status_quo"])
        assert DojoEngine(providers=None)._objections_handled(session) == (2, 2)

    def test_a_spoken_turn_needs_no_question_mark(self):
        """The bug on its own. Identical text, punctuation removed."""
        from salix.dojo.engine import DojoEngine

        engine = DojoEngine(providers=None)
        typed = self._session(
            ["What exactly is the price compared against?"],
            ["Your price is well above our budget."], ["price"])
        spoken = self._session(
            ["what exactly is the price compared against"],
            ["Your price is well above our budget."], ["price"])

        assert engine._objections_handled(typed) == (1, 1)
        assert engine._objections_handled(spoken) == (1, 1)

    def test_roman_urdu_status_quo_is_recognised(self):
        """"theek hai" and "aadat" are how somebody declines to change."""
        from salix.dojo.engine import DojoEngine

        session = self._session(
            ["agar sab theek chal raha hai to reporting mein kitna waqt jata hai"],
            ["humara system theek hai aur team ko iski aadat ho gayi hai"],
            ["status_quo"])
        assert DojoEngine(providers=None)._objections_handled(session) == (1, 1)

    def test_a_reassurance_is_not_engagement(self):
        """The distinction the whole measure exists to draw."""
        from salix.dojo.engine import DojoEngine

        session = self._session(
            ["fikar na karein, price ki value jaldi mil jati hai"],
            ["Aapka price hamare budget se upar hai"], ["price"])
        assert DojoEngine(providers=None)._objections_handled(session) == (1, 0)

    def test_a_question_about_something_else_does_not_count(self):
        """A question in one turn used to satisfy a category raised in another."""
        from salix.dojo.engine import DojoEngine

        session = self._session(
            ["how many people are on the team?", "our pricing is competitive"],
            ["Your price is above our budget.", "Still too expensive."], ["price"])
        assert DojoEngine(providers=None)._objections_handled(session) == (1, 0)

    def test_an_objection_the_buyer_never_raised_is_not_counted(self):
        from salix.dojo.engine import DojoEngine

        session = self._session(
            ["what is the price compared against?"],
            ["We are quite happy as we are."], ["price"])
        # Never raised, so never faced -- and therefore never held against them.
        assert DojoEngine(providers=None)._objections_handled(session) == (0, 0)

    # ---- the vocabulary failure, in the buyer's own words ----------------

    AYESHA = [
        "It's manual, mostly. My team tracks the dates in a spreadsheet and we reach out "
        "to clients a month before they expire. It's not flashy, but honestly, it's worked "
        "well enough for us so far.",
        "I'm not sure I'd call it lost time. We have a workflow, and the team knows how to "
        "navigate it. It takes a few hours each week, sure, but it's part of the job.",
        "They'd probably just get through their backlog faster. We're keeping our heads "
        "above water, and I'm not really looking to overhaul our process.",
        "A three-week pilot sounds like a lot of coordination for something that isn't "
        "really broken. We've already got a rhythm. What are we talking about in terms of cost?",
    ]

    def test_the_status_quo_objection_is_seen_at_all(self):
        """Four clear refusals to change, detected zero times.

        The term was "works" and she said "worked". Everything downstream --
        the score, the verdict, the coach nudge -- was then reasoning about an
        objection it believed had never been raised.
        """
        from salix.dojo.engine import _mentions_category

        buyer = " ".join(self.AYESHA)
        assert _mentions_category(buyer, "status_quo")
        assert _mentions_category(buyer, "price")

    def test_each_phrasing_on_its_own(self):
        """Any one of these alone should be enough."""
        from salix.dojo.engine import _mentions_category

        for line in (
            "it's worked well enough for us so far",
            "something that isn't really broken",
            "we've already got a rhythm",
            "I'm not really looking to overhaul our process",
            "we're keeping our heads above water",
        ):
            assert _mentions_category(line, "status_quo"), line

    def test_the_status_quo_is_credited_without_sharing_its_words(self):
        """The case keyword matching cannot see.

        The rep never says "works", "broken" or anything else from the status
        quo vocabulary. What they do is ask, immediately after she says it has
        worked well enough, how many hours a week the team loses -- which is
        the objection challenged on its own terms and shares none of its
        language. Adjacency is what makes that visible.

        Price is not credited in the same session, and correctly so: the rep
        never asked about it, and she only raised it in her final turn, with
        nothing after it.
        """
        from salix.dojo.engine import DojoEngine

        rep = [
            "Thanks for the time. How does your renewal process run today?",
            "Fair enough. How many hours a week does the team lose to reporting?",
            "If the team got that time back, what would they do with it?",
            "Let me show you a small pilot on reporting only, three weeks. Would that work?",
        ]
        session = self._session(rep, self.AYESHA, ["status_quo", "price"])
        faced, handled = DojoEngine(providers=None)._objections_handled(session)
        assert faced == 2
        assert handled == 1

    def test_an_objection_raised_in_the_last_turn_cannot_be_answered(self):
        """Nothing follows it, so there is nothing to credit."""
        from salix.dojo.engine import DojoEngine

        session = self._session(
            ["how does the process run today?"],
            ["It runs fine. What does this cost?"], ["price"])
        faced, handled = DojoEngine(providers=None)._objections_handled(session)
        assert (faced, handled) == (1, 0)

    def test_adding_the_price_question_earns_the_credit(self):
        """The one line that was missed, restored."""
        from salix.dojo.engine import DojoEngine

        rep = [
            "Thanks for the time. How does your renewal process run today?",
            "Fair enough. How many hours a week does the team lose to reporting?",
            "If the team got that time back, what would they do with it?",
            "On price, if you are getting those hours back that is a trade, not a cost. "
            "Which number does your leadership care about?",
        ]
        session = self._session(rep, self.AYESHA, ["status_quo", "price"])
        faced, handled = DojoEngine(providers=None)._objections_handled(session)
        assert faced == 2
        assert handled >= 1

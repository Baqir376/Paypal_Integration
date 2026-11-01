# -*- coding: utf-8 -*-
"""Recording in, score out, coaching plan out, with nobody clicking anything.

Each of these was broken before it was written: the plan was never generated,
the first rep on a team got an empty one, one failed stage told the browser the
analysis was finished, and nothing was visible until the whole graph ended.
"""

from __future__ import annotations

import asyncio

import pytest
import pytest_asyncio

MP3 = b"\xff\xfb" + b"\x00" * 512


@pytest_asyncio.fixture
async def world(tmp_path, monkeypatch):
    monkeypatch.setenv("SALIX_DATABASE_URL", f"sqlite+aiosqlite:///{(tmp_path / 't.db').as_posix()}")
    monkeypatch.setenv("SALIX_STORAGE_DIR", str(tmp_path / "storage"))
    monkeypatch.setenv("SALIX_PROVIDER_MODE", "mock")

    from httpx import ASGITransport, AsyncClient

    from salix.app import create_app
    from salix.config import get_settings
    from salix.providers import build_providers
    from salix.routers.deps import reset_org_cache
    from salix.schemas.org import Org
    from salix.store import db, repo, session_scope

    get_settings.cache_clear()
    await db.dispose()
    await db.init_db()
    reset_org_cache()
    async with session_scope() as session:
        await repo.put_org(session, Org(id="org_t", name="T"))

    app = create_app()
    app.state.providers = build_providers(get_settings())
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client

    reset_org_cache()
    await db.dispose()
    get_settings.cache_clear()


async def upload(client, name="Bilal's Call", **data):
    return await client.post(
        "/api/calls/upload",
        files={"file": ("a.mp3", MP3, "audio/mpeg")},
        data={"salesperson": name, **data},
    )


class TestRecordingToCoachingPlan:
    async def test_a_new_team_gets_a_real_plan_from_its_first_call(self, world):
        """A name and a file. This team has no history and no colleagues, which
        is every customer on their first day."""
        response = await upload(world)
        assert response.status_code == 202, response.text
        body = response.json()

        call = (await world.get(f"/api/calls/{body['call_id']}")).json()
        assert call["call"]["status"] == "ready"
        assert call["call"]["title"] == "Bilal's Call"
        assert call["rep_name"] == "Bilal"
        assert call["transcript"]["segments"]

        scorecard = call["scorecard"]
        assert 0 < scorecard["overall"] <= 100
        assert len(scorecard["axes"]) == 6
        assert scorecard["caveats"] == []

        plan = (await world.get(f"/api/reps/{body['rep_id']}")).json()["coaching_plan"]
        assert plan is not None
        assert plan["gaps"], "the first rep on a team must still get gaps"
        assert plan["drills"]
        assert plan["script"] is not None and plan["script"]["sections"]

    async def test_the_score_is_stored_where_the_lists_read_it(self, world):
        body = (await upload(world)).json()
        detail = (await world.get(f"/api/calls/{body['call_id']}")).json()
        listed = (await world.get("/api/calls")).json()[0]
        assert listed["score"] == detail["scorecard"]["overall"]
        board = (await world.get("/api/reps")).json()[0]
        assert board["overall_score"] == detail["scorecard"]["overall"]

    async def test_every_stage_reports_and_the_stream_ends_on_done(self, world):
        from salix.pipeline.bus import bus

        body = (await upload(world)).json()
        events = bus.history(body["call_id"])
        final = {e.stage.value: e.status.value for e in events}
        for stage in ("transcribe", "diarize", "metrics", "anatomy", "plays", "embed", "coach", "done"):
            assert final[stage] == "ok", f"{stage}: {final.get(stage)}"
        assert final["trajectory"] == "skipped"
        assert events[-1].stage.value == "done"

    async def test_a_plan_is_replaced_by_the_next_call(self, world):
        first = (await upload(world)).json()
        one = (await world.get(f"/api/reps/{first['rep_id']}")).json()["coaching_plan"]["id"]
        await upload(world)
        two = (await world.get(f"/api/reps/{first['rep_id']}")).json()["coaching_plan"]["id"]
        assert one != two


class TestDegradation:
    async def test_a_failed_stage_does_not_end_the_stream(self):
        from salix.pipeline.bus import EventBus
        from salix.schemas.pipeline import PipelineEvent, StageKey, StageStatus

        failed = PipelineEvent(call_id="c", stage=StageKey.ANATOMY, status=StageStatus.FAILED)
        assert EventBus._is_final(failed) is False
        done = PipelineEvent(call_id="c", stage=StageKey.DONE, status=StageStatus.OK)
        assert EventBus._is_final(done) is True

    async def test_a_failed_transcription_still_ends_the_stream(self, world):
        from salix.pipeline.bus import bus

        class Broken:
            name = "broken"

            async def transcribe(self, *args, **kwargs):
                raise RuntimeError("unreadable")

        world._transport.app.state.providers.asr = Broken()
        body = (await upload(world)).json()
        last = bus.history(body["call_id"])[-1]
        assert (last.stage.value, last.status.value) == ("done", "failed")

    async def test_failed_anatomy_is_flagged_on_the_score_and_skips_the_plan(self, world, monkeypatch):
        from salix.agents.anatomist import Anatomist
        from salix.pipeline.bus import bus

        async def boom(*args, **kwargs):
            raise RuntimeError("model down")

        monkeypatch.setattr(Anatomist, "run", boom)
        body = (await upload(world)).json()
        detail = (await world.get(f"/api/calls/{body['call_id']}")).json()
        assert detail["call"]["status"] == "ready"
        assert any("placeholders" in c for c in detail["scorecard"]["caveats"])
        final = {e.stage.value: e.status.value for e in bus.history(body["call_id"])}
        assert final["anatomy"] == "failed"
        assert final["coach"] == "skipped"

    async def test_one_voice_is_flagged_on_the_score(self, world):
        from salix.providers.base import ASRResult, ASRSentence

        class OneVoice:
            name = "one"

            async def transcribe(self, *args, **kwargs):
                return ASRResult(
                    sentences=[
                        ASRSentence(begin_time=i * 3000, end_time=i * 3000 + 2500, text="We help teams sell better today.")
                        for i in range(6)
                    ],
                    duration_ms=20000,
                )

        world._transport.app.state.providers.asr = OneVoice()
        body = (await upload(world)).json()
        detail = (await world.get(f"/api/calls/{body['call_id']}")).json()
        assert any("one voice" in c for c in detail["scorecard"]["caveats"])

    async def test_the_model_being_down_costs_the_script_not_the_plan(self, world, monkeypatch):
        from salix.agents.coach import Coach

        async def boom(*args, **kwargs):
            raise RuntimeError("model down")

        monkeypatch.setattr(Coach, "_generate", boom)
        body = (await upload(world)).json()
        plan = (await world.get(f"/api/reps/{body['rep_id']}")).json()["coaching_plan"]
        assert plan["gaps"] and plan["drills"]
        assert plan["script"] is None
        assert "could not be generated" in plan["diagnosis"]

    async def test_a_stage_commits_before_the_next_one_starts(self, world, monkeypatch):
        """Read from another connection, the way the call page does."""
        from salix.agents.anatomist import Anatomist
        from salix.schemas.call import Transcript
        from salix.store import repo, session_scope

        seen = {}
        original = Anatomist.run

        async def spy(self, transcript, call_id, **kwargs):
            async with session_scope() as other:
                seen["transcript"] = await repo.get_artifact(other, call_id, repo.TRANSCRIPT, Transcript)
                seen["call"] = await repo.get_call(other, call_id)
            return await original(self, transcript, call_id, **kwargs)

        monkeypatch.setattr(Anatomist, "run", spy)
        await upload(world)
        assert seen["transcript"] is not None
        assert seen["call"].status.value == "analyzing"

    async def test_an_upload_is_not_blocked_while_another_is_being_analysed(self, world, monkeypatch):
        """The graph used to hold SQLite's write lock through every model call."""
        from salix.agents.anatomist import Anatomist
        from salix.schemas.org import Rep
        from salix.store import repo, session_scope

        wrote = {}
        original = Anatomist.run

        async def spy(self, *args, **kwargs):
            async with session_scope() as other:
                await asyncio.wait_for(
                    repo.put_rep(other, Rep(id="rep_x", org_id="org_t", name="X")), timeout=5
                )
                await asyncio.wait_for(other.commit(), timeout=5)
            wrote["ok"] = True
            return await original(self, *args, **kwargs)

        monkeypatch.setattr(Anatomist, "run", spy)
        await upload(world)
        assert wrote.get("ok")


class TestCeiling:
    def test_a_top_performer_with_no_calls_does_not_lower_the_bar(self):
        from salix.metrics import analytics
        from salix.schemas.common import SkillAxis

        ceiling = analytics.team_ceiling(
            {"new": {a: 0.0 for a in SkillAxis}, "star": {a: 80.0 for a in SkillAxis}},
            ["new", "star"],
        )
        assert all(v == 80.0 for v in ceiling.values())

    async def test_the_team_leader_is_coached_against_the_benchmark(self, world):
        first = (await upload(world, "Sana")).json()
        plan = (await world.get(f"/api/reps/{first['rep_id']}")).json()["coaching_plan"]
        assert all(g["top_value"] > g["rep_value"] for g in plan["gaps"])

    async def test_colleagues_open_calls_are_used_when_nobody_has_won(self, world):
        await upload(world, "Sana")
        second = (await upload(world, "Hamza")).json()
        plan = (await world.get(f"/api/reps/{second['rep_id']}")).json()["coaching_plan"]
        assert plan["script"] is not None

    async def test_lost_calls_are_never_evidence(self, world, monkeypatch):
        from salix.store import repo

        asked = []
        original = repo.search_moments

        async def spy(session, org_id, embedding, **kwargs):
            asked.append(kwargs.get("outcome"))
            return await original(session, org_id, embedding, **kwargs)

        monkeypatch.setattr(repo, "search_moments", spy)
        await upload(world, "Sana", outcome="lost")
        await upload(world, "Hamza", outcome="lost")
        assert "lost" not in asked and None not in asked
        assert "won" in asked


class TestLanguageDetection:
    ENGLISH = "Thanks for taking the time today. What does your current process look like?"
    ROMAN = "Aap ka process kya hai aur aap ko kis cheez mein masla hai yeh batayein?"
    NASTALIQ = "آپ کا موجودہ طریقہ کار کیا ہے اور آپ کو کس چیز میں مسئلہ ہے؟"
    DEVANAGARI = "आप का मौजूदा तरीक़ा क्या है और आप को किस चीज़ में मसला है?"

    @staticmethod
    def sentences(*lines):
        from salix.providers.base import ASRSentence

        return [
            ASRSentence(begin_time=i * 3000, end_time=i * 3000 + 2500, text=t, speaker_id=i % 2)
            for i, t in enumerate(lines)
        ]

    def test_english(self):
        from salix.pipeline.language import classify

        assert classify(self.sentences(self.ENGLISH, self.ENGLISH)) == "en"

    def test_urdu_in_latin_letters(self):
        from salix.pipeline.language import classify

        assert classify(self.sentences(self.ROMAN, self.ROMAN)) == "ur-roman"

    def test_urdu_in_nastaliq(self):
        from salix.pipeline.language import classify

        assert classify(self.sentences(self.NASTALIQ, self.NASTALIQ)) == "ur"

    def test_mostly_devanagari_is_urdu_speech(self):
        from salix.pipeline.language import classify

        assert classify(self.sentences(self.DEVANAGARI, self.DEVANAGARI)) == "ur"

    def test_switching_mid_call_is_roman_urdu(self):
        from salix.pipeline.language import classify

        lines = [self.ENGLISH, self.ENGLISH, self.ENGLISH, self.DEVANAGARI]
        assert classify(self.sentences(*lines)) == "ur-roman"

    async def test_urdu_with_english_in_it_is_roman_urdu_after_the_second_pass(self):
        """Measured on real audio: the mixed sample is mostly Devanagari on the
        first pass, and only the second shows how much of it was English."""
        from salix.pipeline.language import transcribe_detecting

        mixed = self.NASTALIQ + " budget process renewal team pricing"
        asr = self._asr([[self.DEVANAGARI], [mixed]])
        result, language = await transcribe_detecting(self._providers(asr), "a.mp3")
        assert language == "ur-roman"
        assert result.sentences[0].text == self.DEVANAGARI

    def test_one_stray_word_does_not_change_the_language(self):
        from salix.pipeline.language import classify

        assert classify(self.sentences(self.ENGLISH * 6 + " شکریہ")) == "en"

    def test_nothing_at_all(self):
        from salix.pipeline.language import classify

        assert classify(self.sentences("")) == "en"

    def _asr(self, passes):
        from salix.providers.base import ASRResult

        outer = self

        class Scripted:
            name = "scripted"
            calls: list[tuple] = []

            async def transcribe(self, audio, *, diarize=True, language_hints=()):
                type(self).calls.append(tuple(language_hints))
                result = passes[len(type(self).calls) - 1]
                if isinstance(result, Exception):
                    raise result
                return ASRResult(sentences=outer.sentences(*result), duration_ms=9000)

        Scripted.calls = []
        return Scripted()

    def _providers(self, asr):
        from types import SimpleNamespace

        return SimpleNamespace(asr=asr)

    async def test_first_pass_is_asked_for_nothing(self):
        from salix.pipeline.language import transcribe_detecting

        asr = self._asr([[self.ENGLISH]])
        _, language = await transcribe_detecting(self._providers(asr), "a.mp3")
        assert language == "en"
        assert asr.calls == [()]

    async def test_devanagari_earns_a_second_pass_as_urdu(self):
        from salix.pipeline.language import transcribe_detecting

        asr = self._asr([[self.DEVANAGARI], [self.NASTALIQ]])
        result, language = await transcribe_detecting(self._providers(asr), "a.mp3")
        assert language == "ur"
        assert asr.calls == [(), ("ur",)]
        assert result.sentences[0].text == self.NASTALIQ

    async def test_nastaliq_first_time_needs_no_second_pass(self):
        from salix.pipeline.language import transcribe_detecting

        asr = self._asr([[self.NASTALIQ]])
        _, language = await transcribe_detecting(self._providers(asr), "a.mp3")
        assert language == "ur"
        assert len(asr.calls) == 1

    async def test_a_failed_second_pass_keeps_the_first(self):
        from salix.pipeline.language import transcribe_detecting

        asr = self._asr([[self.DEVANAGARI], RuntimeError("quota")])
        result, language = await transcribe_detecting(self._providers(asr), "a.mp3")
        assert language == "ur-roman"
        assert result.sentences[0].text == self.DEVANAGARI

    async def test_an_api_caller_who_knows_is_believed(self):
        from salix.pipeline.language import transcribe_detecting

        asr = self._asr([[self.ENGLISH]])
        _, language = await transcribe_detecting(self._providers(asr), "a.mp3", requested="ur")
        assert language == "ur"
        assert asr.calls == [("ur",)]

    @pytest.mark.parametrize(
        "language,script,expected",
        [("ur", "NASTALIQ", "ur"), ("ur-roman", "ROMAN", "ur-roman"), ("en", "ENGLISH", "en")],
    )
    async def test_the_result_reaches_the_call(self, world, language, script, expected):
        """Uploaded with nothing about language, through the real pipeline."""
        text = getattr(self, script)
        outer = self

        class Fixed:
            name = "fixed"

            async def transcribe(self, *args, **kwargs):
                from salix.providers.base import ASRResult

                return ASRResult(sentences=outer.sentences(text, text, text, text), duration_ms=12000)

        world._transport.app.state.providers.asr = Fixed()
        body = (await upload(world)).json()
        detail = (await world.get(f"/api/calls/{body['call_id']}")).json()
        assert detail["call"]["language"] == expected
        assert detail["transcript"]["language"] == expected
        assert detail["metrics"]["language"] == expected

    async def test_nastaliq_is_kept_and_devanagari_never_reaches_the_screen(self, world):
        outer = self

        class Mixed:
            name = "mixed"

            async def transcribe(self, *args, **kwargs):
                from salix.providers.base import ASRResult

                lines = [outer.ENGLISH, outer.ENGLISH, outer.ENGLISH, outer.DEVANAGARI]
                return ASRResult(sentences=outer.sentences(*lines), duration_ms=12000)

        calls = []

        async def complete(*args, **kwargs):
            calls.append(kwargs)
            return "\n".join(f"{i + 1}. latin line" for i in range(4))

        providers = world._transport.app.state.providers
        providers.asr = Mixed()
        original = providers.llm.complete
        providers.llm.complete = complete
        try:
            body = (await upload(world)).json()
        finally:
            providers.llm.complete = original
        assert calls, "a code-switched call must be transliterated"
        detail = (await world.get(f"/api/calls/{body['call_id']}")).json()
        text = " ".join(s["text"] for s in detail["transcript"]["segments"])
        assert not any("ऀ" <= c <= "ॿ" for c in text)


class TestUploadForm:
    @pytest.mark.parametrize(
        "typed,expected",
        [
            ("Bilal", "Bilal"),
            ("Bilal's Call", "Bilal"),
            ("Bilal’s call", "Bilal"),
            ("bilal CALL", "bilal"),
            ("  Bilal   Ahmed  ", "Bilal Ahmed"),
        ],
    )
    async def test_the_name_is_understood(self, world, typed, expected):
        body = (await upload(world, typed)).json()
        detail = (await world.get(f"/api/calls/{body['call_id']}")).json()
        assert detail["rep_name"] == expected

    async def test_no_name_at_all_is_refused(self, world):
        response = await world.post(
            "/api/calls/upload", files={"file": ("a.mp3", MP3, "audio/mpeg")}
        )
        assert response.status_code == 422

    @pytest.mark.parametrize("typed", ["   ", "x" * 200])
    async def test_a_name_that_is_not_one_is_refused(self, world, typed):
        response = await upload(world, typed)
        assert response.status_code == 422

    async def test_the_same_person_twice_is_one_person(self, world):
        await upload(world, "Bilal")
        await upload(world, "bilal's call")
        assert len((await world.get("/api/reps")).json()) == 1

    async def test_a_first_name_finds_the_full_name(self, world):
        await world.post("/api/reps", json={"name": "Bilal Ahmed"})
        body = (await upload(world, "Bilal's Call")).json()
        detail = (await world.get(f"/api/calls/{body['call_id']}")).json()
        assert detail["rep_name"] == "Bilal Ahmed"
        assert len((await world.get("/api/reps")).json()) == 1

    async def test_two_with_that_name_asks_rather_than_guesses(self, world):
        await world.post("/api/reps", json={"name": "Bilal Ahmed"})
        await world.post("/api/reps", json={"name": "Bilal Khan"})
        response = await upload(world, "Bilal")
        assert response.status_code == 409
        assert "Bilal Ahmed" in response.json()["detail"]
        assert "Bilal Khan" in response.json()["detail"]

    async def test_title_and_account_can_still_be_given(self, world):
        body = (await upload(world, "Bilal", title="Renewal", account="Northwind")).json()
        call = (await world.get(f"/api/calls/{body['call_id']}")).json()["call"]
        assert (call["title"], call["account"]) == ("Renewal", "Northwind")

    async def test_the_default_title_uses_their_first_name(self, world):
        body = (await upload(world, "Bilal Ahmed")).json()
        call = (await world.get(f"/api/calls/{body['call_id']}")).json()["call"]
        assert call["title"] == "Bilal's call"

    @pytest.mark.parametrize("name", ["../../secrets", "..", "a/b", "c:\\windows\\x"])
    async def test_a_sample_lookup_cannot_leave_the_samples_folder(self, world, tmp_path, name):
        (tmp_path / "secrets.txt").write_text("REP: stolen\nBUYER: stolen\n", encoding="utf-8")
        response = await world.post(
            "/api/calls/upload",
            files={"file": (f"{name}.mp3", MP3, "audio/mpeg")},
            data={"salesperson": "Bilal"},
        )
        assert response.status_code == 202
        detail = (await world.get(f"/api/calls/{response.json()['call_id']}")).json()
        assert "stolen" not in str(detail["transcript"])

    async def test_a_bundled_sample_keeps_its_script_offline(self, world, tmp_path):
        samples = tmp_path / "storage" / "samples"
        samples.mkdir(parents=True)
        (samples / "demo_urdu.txt").write_text(
            f"REP: {self.NASTALIQ_LINE}\nBUYER: {self.NASTALIQ_LINE}\n", encoding="utf-8"
        )
        response = await world.post(
            "/api/calls/upload",
            files={"file": ("demo_urdu.mp3", MP3, "audio/mpeg")},
            data={"salesperson": "Bilal"},
        )
        detail = (await world.get(f"/api/calls/{response.json()['call_id']}")).json()
        assert detail["call"]["language"] == "ur"

    NASTALIQ_LINE = "آپ کا موجودہ طریقہ کار کیا ہے؟"


class TestTeam:
    async def test_add_edit_remove(self, world):
        created = await world.post("/api/reps", json={"name": "  Zara   Sheikh ", "quota": 5000})
        assert created.status_code == 201
        rep = created.json()
        assert rep["name"] == "Zara Sheikh"
        assert rep["initials"] == "ZS"

        edited = await world.patch(f"/api/reps/{rep['id']}", json={"name": "Zara Khan", "quota": 9000})
        assert edited.json()["name"] == "Zara Khan"
        assert edited.json()["initials"] == "ZK"
        assert edited.json()["quota"] == 9000

        assert (await world.delete(f"/api/reps/{rep['id']}")).status_code == 204
        assert (await world.get("/api/reps")).json() == []

    async def test_a_duplicate_is_refused(self, world):
        await world.post("/api/reps", json={"name": "Zara"})
        assert (await world.post("/api/reps", json={"name": "zara"})).status_code == 409

    async def test_renaming_onto_someone_else_is_refused(self, world):
        await world.post("/api/reps", json={"name": "Zara"})
        other = (await world.post("/api/reps", json={"name": "Hamza"})).json()
        response = await world.patch(f"/api/reps/{other['id']}", json={"name": "ZARA"})
        assert response.status_code == 409

    async def test_changing_only_the_case_of_your_own_name_is_fine(self, world):
        rep = (await world.post("/api/reps", json={"name": "zara"})).json()
        response = await world.patch(f"/api/reps/{rep['id']}", json={"name": "Zara"})
        assert response.status_code == 200

    @pytest.mark.parametrize(
        "method,path,payload",
        [
            ("patch", "/api/reps/nobody", {"name": "x"}),
            ("delete", "/api/reps/nobody", None),
            ("post", "/api/reps/nobody/restore", None),
        ],
    )
    async def test_unknown_rep_is_404(self, world, method, path, payload):
        kwargs = {"json": payload} if payload else {}
        response = await getattr(world, method)(path, **kwargs)
        assert response.status_code == 404

    @pytest.mark.parametrize("name", ["", "   ", "x" * 81])
    async def test_a_bad_name_is_refused(self, world, name):
        assert (await world.post("/api/reps", json={"name": name})).status_code == 422

    async def test_a_negative_quota_is_refused(self, world):
        response = await world.post("/api/reps", json={"name": "Zara", "quota": -1})
        assert response.status_code == 422

    async def test_a_rename_reaches_their_calls(self, world):
        body = (await upload(world, "Zara")).json()
        await world.patch(f"/api/reps/{body['rep_id']}", json={"name": "Zara Khan"})
        detail = (await world.get(f"/api/calls/{body['call_id']}")).json()
        assert detail["rep_name"] == "Zara Khan"

    async def test_removing_someone_keeps_their_calls(self, world):
        body = (await upload(world, "Zara")).json()
        await world.delete(f"/api/reps/{body['rep_id']}")

        assert (await world.get("/api/reps")).json() == []
        detail = (await world.get(f"/api/calls/{body['call_id']}")).json()
        assert detail["rep_name"] == "Zara"
        assert (await world.get(f"/api/reps/{body['rep_id']}")).status_code == 200
        listed = (await world.get("/api/reps/archived")).json()
        assert [r["name"] for r in listed] == ["Zara"]

    async def test_a_removed_rep_cannot_be_uploaded_to_by_id(self, world):
        body = (await upload(world, "Zara")).json()
        await world.delete(f"/api/reps/{body['rep_id']}")
        response = await world.post(
            "/api/calls/upload",
            files={"file": ("a.mp3", MP3, "audio/mpeg")},
            data={"rep_id": body["rep_id"]},
        )
        assert response.status_code == 400

    async def test_restoring_brings_their_history_back(self, world):
        body = (await upload(world, "Zara")).json()
        await world.delete(f"/api/reps/{body['rep_id']}")
        assert (await world.post(f"/api/reps/{body['rep_id']}/restore")).status_code == 200
        board = (await world.get("/api/reps")).json()
        assert board[0]["calls"] == 1

    async def test_uploading_under_a_removed_name_brings_them_back(self, world):
        body = (await upload(world, "Zara")).json()
        await world.delete(f"/api/reps/{body['rep_id']}")
        again = (await upload(world, "Zara")).json()
        assert again["rep_id"] == body["rep_id"]
        assert (await world.get("/api/reps")).json()[0]["calls"] == 2

    async def test_adding_a_removed_name_brings_them_back(self, world):
        body = (await upload(world, "Zara")).json()
        await world.delete(f"/api/reps/{body['rep_id']}")
        created = await world.post("/api/reps", json={"name": "Zara"})
        assert created.status_code == 201
        assert created.json()["id"] == body["rep_id"]

    async def test_a_removed_rep_leaves_the_team_ceiling(self, world):
        star = (await world.post("/api/reps", json={"name": "Star"})).json()
        await upload(world, "Star")
        await upload(world, "Other")
        await world.delete(f"/api/reps/{star['id']}")
        board = (await world.get("/api/reps")).json()
        assert [r["rep"]["name"] for r in board] == ["Other"]
        assert board[0]["team_axes"] == board[0]["axes"]


class TestFreshDeployment:
    async def test_startup_creates_an_org_only_if_there_is_none(self, tmp_path, monkeypatch):
        monkeypatch.setenv("SALIX_DATABASE_URL", f"sqlite+aiosqlite:///{(tmp_path / 'f.db').as_posix()}")
        monkeypatch.setenv("SALIX_STORAGE_DIR", str(tmp_path / "s"))
        monkeypatch.setenv("SALIX_PROVIDER_MODE", "mock")

        from salix.app import create_app, lifespan
        from salix.config import get_settings
        from salix.store import db, repo, session_scope

        get_settings.cache_clear()
        await db.dispose()
        try:
            async with lifespan(create_app()):
                async with session_scope() as session:
                    org = await repo.first_org(session)
                    assert org.id == repo.DEFAULT_ORG_ID
        finally:
            await db.dispose()
            get_settings.cache_clear()

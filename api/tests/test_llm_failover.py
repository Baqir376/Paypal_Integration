"""A stuck or overloaded model must cost seconds, not most of a minute.

Comes from a real run: Gemini took 52 seconds to answer 503 "high demand" to a
one-line question, was retried twice, and the next model then answered in one second.
"""

from __future__ import annotations

import asyncio
import time

import pytest

from salix.config import Settings
from salix.providers import failover
from salix.providers.base import ProviderError
from salix.providers.dashscope_llm import DashScopeLLM
from salix.providers.failover import FailoverLLM, Route, build_routes
from salix.schemas.analysis import Objection


class Fake:
    name = "fake"

    def __init__(self, answer="ok", delay=0.0, error=None):
        self.answer, self.delay, self.error = answer, delay, error
        self.calls = 0

    async def complete(self, *, model=None, **kwargs):
        self.calls += 1
        await asyncio.sleep(self.delay)
        if self.error:
            raise self.error
        return self.answer

    async def stream(self, *, model=None, **kwargs):
        self.calls += 1
        await asyncio.sleep(self.delay)
        if self.error:
            raise self.error
        yield "first "
        await asyncio.sleep(self.delay and 0)
        yield self.answer


@pytest.fixture(autouse=True)
def short_patience(monkeypatch):
    monkeypatch.setattr(failover, "QUICK_PATIENCE_S", 0.05)
    monkeypatch.setattr(failover, "LONG_PATIENCE_S", 0.2)


def llm(*fakes):
    return FailoverLLM([Route(f"route{i}", fake) for i, fake in enumerate(fakes)])


async def test_a_stuck_model_loses_a_quick_question_to_the_next_one():
    stuck, healthy = Fake(delay=30), Fake(answer="from the backup")
    started = time.monotonic()
    assert await llm(stuck, healthy).complete(system="", user="", max_tokens=512) == "from the backup"
    assert time.monotonic() - started < 1


async def test_a_long_request_gets_longer_than_a_quick_one():
    # Slower than quick patience, faster than long patience: a long call may take this.
    thinker = Fake(answer="the whole analysis", delay=0.1)
    backup = Fake(answer="should not be used")
    assert await llm(thinker, backup).complete(system="", user="", max_tokens=12000) == "the whole analysis"
    assert backup.calls == 0


async def test_the_last_route_is_never_cut_off():
    # With nothing behind it, giving up early would turn a slow answer into no answer.
    failing, slow = Fake(error=RuntimeError("down")), Fake(answer="slow but here", delay=0.1)
    assert await llm(failing, slow).complete(system="", user="", max_tokens=512) == "slow but here"


async def test_a_model_that_failed_is_skipped_by_the_next_request():
    stuck, healthy = Fake(delay=30), Fake()
    chain = llm(stuck, healthy)
    await chain.complete(system="", user="", max_tokens=512)
    await chain.complete(system="", user="", max_tokens=512)
    assert stuck.calls == 1 and healthy.calls == 2


async def test_when_everything_fails_the_error_still_surfaces():
    with pytest.raises(ProviderError):
        await llm(Fake(error=ProviderError("a", "down")), Fake(error=ProviderError("b", "down"))).complete(system="", user="")


async def test_a_stream_that_never_starts_moves_to_the_next_route():
    stuck, healthy = Fake(delay=30), Fake(answer="reply")
    started = time.monotonic()
    tokens = [token async for token in llm(stuck, healthy).stream(system="", user="")]
    assert "".join(tokens) == "first reply"
    assert time.monotonic() - started < 1


def test_no_route_retries_when_another_is_waiting():
    settings = Settings(llm_base_url="http://x", llm_api_key="k", llm_fallback_models="a,b")
    routes = build_routes(settings)
    assert len(routes) == 3
    assert all(route.llm.settings.max_retries == 1 for route in routes)


async def test_a_single_failed_attempt_does_not_sleep_before_giving_up(monkeypatch):
    settings = Settings(llm_base_url="http://x", llm_api_key="k", max_retries=1)
    client = DashScopeLLM(settings)

    async def overloaded(**kwargs):
        raise RuntimeError("503 high demand")

    monkeypatch.setattr(client._client.chat.completions, "create", overloaded)
    started = time.monotonic()
    with pytest.raises(ProviderError):
        await client.complete(system="", user="")
    assert time.monotonic() - started < 0.2


def test_a_stray_key_on_an_objection_does_not_force_a_retry():
    objection = Objection.model_validate(
        {
            "id": "o1",
            "category": "risk",
            "text": "We tried this before.",
            "raised": {"segment_id": "s1", "quote": "We tried this before."},
            "handled": False,
            "handling_quality": 0,
            "stage": "risk",
        }
    )
    assert not hasattr(objection, "stage")

"""What the buyer says has to be words. A fallback model under load once answered "**: * *"."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from salix.dojo import engine as engine_module
from salix.dojo.engine import DojoEngine
from salix.providers.base import ProviderError


class Stream:
    name = "fake"

    def __init__(self, *tokens):
        self.tokens = tokens

    async def stream(self, **kwargs):
        for token in self.tokens:
            yield token


def buyer(*tokens):
    return DojoEngine(SimpleNamespace(llm=Stream(*tokens)))


@pytest.fixture(autouse=True)
def plain_prompt(monkeypatch):
    monkeypatch.setattr(engine_module, "persona_system_prompt", lambda *args: "be a buyer")


SESSION = SimpleNamespace(turns=[], persona=None, language="en", brief="")


async def said(engine):
    return "".join([token async for token in engine.buyer_reply(SESSION, "Hello")])


async def test_markdown_never_reaches_the_rep():
    assert await said(buyer("**Honestly", ",** it looks ", "*expensive*.")) == "Honestly, it looks expensive."


async def test_symbols_before_the_first_word_are_dropped():
    assert await said(buyer("**", ": ", "We need ", "a date.")) == "We need a date."


async def test_a_reply_with_no_words_counts_as_a_failure():
    with pytest.raises(ProviderError):
        await said(buyer("**: ", "* *"))


async def test_urdu_counts_as_words():
    assert await said(buyer("قیمت زیادہ ہے")) == "قیمت زیادہ ہے"

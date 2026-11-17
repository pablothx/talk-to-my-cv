"""Citations and the relevance gate against kb.example/, bge-m3 and the configured LLM."""

from pathlib import Path

import pytest

from talk_to_my_cv.chat_models import build_chat_model
from talk_to_my_cv.config import load_settings
from talk_to_my_cv.embeddings import build_embedder, relevance_threshold
from talk_to_my_cv.ingest import ingest
from talk_to_my_cv.language import detect_language
from talk_to_my_cv.rag import answer

pytestmark = pytest.mark.e2e

KB = Path(__file__).resolve().parents[1] / "kb.example"


class SpyChatModel:
    """Wraps the real model and counts calls, to prove the gate skipped it."""

    def __init__(self, inner):
        self.inner = inner
        self.calls = 0

    def complete(self, messages):
        self.calls += 1
        return self.inner.complete(messages)


@pytest.fixture(scope="module")
def rag():
    settings = load_settings()
    embedder = build_embedder(settings)
    from talk_to_my_cv.store import PgVectorStore

    store = PgVectorStore(settings.database_url, schema="test_citations")
    ingest(KB, embedder, store)
    chat = SpyChatModel(build_chat_model(settings))
    threshold = relevance_threshold(settings.embed_model)

    def ask(question: str):
        return answer(question, embedder, store, chat, threshold=threshold)

    ask.chat = chat
    return ask


def test_answer_cites_the_section_that_holds_the_fact(rag):
    result = rag("How much did Project Lumen speed up reconciliation?")

    assert "14 minutes" in result.text
    assert "experience/northwind-payments.md § Senior Backend Engineer > Project Lumen" in (
        result.citations
    )


def test_tech_stack_answer_cites_the_skills_file(rag):
    result = rag("What is her tech stack?")

    assert any(c.startswith("skills.md § ") for c in result.citations)


def test_off_topic_question_is_refused_without_calling_the_llm(rag):
    calls_before = rag.chat.calls

    result = rag("What is her favourite football team?")

    assert result.refused
    assert result.citations == []
    assert rag.chat.calls == calls_before


def test_spanish_question_gets_a_spanish_answer(rag):
    result = rag("¿Cuánto aceleró Project Lumen la conciliación?")

    assert not result.refused
    assert detect_language(result.text) == "es"

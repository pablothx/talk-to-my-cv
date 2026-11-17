import pytest
from fakes import FakeChatModel, FakeEmbedder

from talk_to_my_cv.chunking import chunk_document
from talk_to_my_cv.rag import answer, is_refusal
from talk_to_my_cv.store import EmbeddingModel, InMemoryStore

KB = {
    "experience/northwind.md": "---\ntitle: Northwind\n---\n## Lumen\n\nLed Project Lumen.\n",
    "skills.md": "---\ntitle: Skills\n---\n## Languages\n\nJava.\n\n## Cloud\n\nAWS.\n",
}


@pytest.fixture
def store():
    embedder, store = FakeEmbedder(), InMemoryStore()
    store.set_model(EmbeddingModel(embedder.model, embedder.dimension))
    chunks = [c for path, md in KB.items() for c in chunk_document(path, md)]
    store.upsert(chunks, embedder.embed([c.embed_text for c in chunks]))
    return store


def test_answer_retrieves_top_k_and_hands_them_to_the_chat_model(store):
    chat = FakeChatModel(reply="She led Project Lumen.")

    result = answer("What did she lead?", FakeEmbedder(), store, chat, k=2)

    assert result.text == "She led Project Lumen."
    assert len(result.retrieved) == 2
    [messages] = chat.calls
    assert messages[1]["content"] == "What did she lead?"
    for r in result.retrieved:
        assert r.chunk.text in messages[0]["content"]
    scores = [r.score for r in result.retrieved]
    assert scores == sorted(scores, reverse=True)


@pytest.mark.parametrize(
    "text",
    ["I don't have that information.", "No tengo esa información.", "  no tengo esa información "],
)
def test_refusals_are_recognised_in_both_languages(text):
    assert is_refusal(text)


def test_an_answer_that_mentions_missing_info_is_not_a_refusal():
    assert not is_refusal("No, she has never used Kubernetes in production.")

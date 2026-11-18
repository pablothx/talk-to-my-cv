"""Pick the answering engine and wire it to the configured models and store."""

from collections.abc import Callable

from talk_to_my_cv.chat_models import build_chat_model
from talk_to_my_cv.config import Settings
from talk_to_my_cv.embeddings import build_embedder, relevance_threshold
from talk_to_my_cv.graph import answer_with_graph
from talk_to_my_cv.rag import Answer, answer
from talk_to_my_cv.store import SearchMode, build_store

# Both take the same arguments and return an Answer: ENGINE picks one (step 7).
ENGINES = {"pipeline": answer, "graph": answer_with_graph}


def build_ask(settings: Settings) -> Callable[[str], Answer]:
    """question → Answer, with everything from configuration (used by the API, step 8)."""
    embedder, chat = build_embedder(settings), build_chat_model(settings)
    store = build_store(settings.vector_store, settings)
    threshold = relevance_threshold(settings.embed_model)
    mode = SearchMode(settings.search_mode)
    respond = ENGINES[settings.engine]

    def ask(question: str) -> Answer:
        return respond(question, embedder, store, chat, threshold=threshold, mode=mode)

    return ask

"""ChatModel implementations, selected by LLM_PROVIDER (ADR-0004)."""

from typing import Any

import groq
import ollama

from talk_to_my_cv.config import Settings

SEED = 42  # Same seed + temperature 0 = as reproducible as each provider allows.


class OllamaChatModel:
    """Local and free. Slow without a GPU (see lesson 03, "No GPU")."""

    def __init__(self, client: Any, model: str) -> None:
        self.client = client
        self.model = model

    def complete(self, messages: list[dict[str, str]]) -> str:
        response = self.client.chat(
            model=self.model, messages=messages, options={"temperature": 0, "seed": SEED}
        )
        return response["message"]["content"]


class GroqChatModel:
    """Hosted and fast. The retrieved CV chunks leave your machine."""

    def __init__(self, client: Any, model: str) -> None:
        self.client = client
        self.model = model

    def complete(self, messages: list[dict[str, str]]) -> str:
        response = self.client.chat.completions.create(
            model=self.model, messages=messages, temperature=0, seed=SEED
        )
        return response.choices[0].message.content


def build_chat_model(settings: Settings) -> OllamaChatModel | GroqChatModel:
    if settings.llm_provider == "groq":
        return GroqChatModel(groq.Groq(api_key=settings.groq_api_key), settings.chat_model)
    return OllamaChatModel(ollama.Client(host=settings.ollama_host), settings.chat_model)

"""Test doubles shared across unit tests."""

import hashlib
from collections.abc import Sequence


class FakeEmbedder:
    """Deterministic vectors derived from a hash of the text; records every embedded text."""

    def __init__(self, model: str = "fake-embed", dimension: int = 8):
        self.model = model
        self.dimension = dimension
        self.embedded: list[str] = []

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        self.embedded.extend(texts)
        return [self._vector(t) for t in texts]

    def _vector(self, text: str) -> list[float]:
        digest = hashlib.sha256(text.encode()).digest()
        return [b / 255 + 0.01 for b in digest[: self.dimension]]


class FakeChatModel:
    """Returns a canned reply and records every conversation it was given."""

    def __init__(self, reply: str = "She led Project Lumen."):
        self.reply = reply
        self.calls: list[list[dict[str, str]]] = []

    def complete(self, messages: list[dict[str, str]]) -> str:
        self.calls.append(messages)
        return self.reply


class ScriptedChatModel:
    """Replies in order, one per call; records every conversation it was given."""

    def __init__(self, *replies: str):
        self.replies = list(replies)
        self.calls: list[list[dict[str, str]]] = []

    def complete(self, messages: list[dict[str, str]]) -> str:
        self.calls.append(messages)
        return self.replies[len(self.calls) - 1]

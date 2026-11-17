"""Embeddings: turning text into vectors, and comparing them."""

import math
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Protocol

import ollama
import yaml

from talk_to_my_cv.config import Settings, read_env

Vector = Sequence[float]


def cosine_similarity(a: Vector, b: Vector) -> float:
    """Cosine of the angle between two vectors: 1 = same direction, 0 = unrelated."""
    if len(a) != len(b):
        raise ValueError(f"vectors differ in dimension: {len(a)} vs {len(b)}")
    norms = math.hypot(*a) * math.hypot(*b)
    if norms == 0:
        raise ValueError("cosine similarity is undefined for a zero vector")
    return sum(x * y for x, y in zip(a, b, strict=True)) / norms


class Embedder(Protocol):
    """Turns texts into vectors of a fixed `dimension` (ADR-0003)."""

    model: str
    dimension: int

    def embed(self, texts: Sequence[str]) -> list[list[float]]: ...


class OllamaClient(Protocol):
    def embed(self, model: str, input: list[str]) -> Mapping: ...


class OllamaEmbedder:
    def __init__(self, client: OllamaClient, model: str, dimension: int, batch_size: int = 32):
        self.client = client
        self.model = model
        self.dimension = dimension
        self.batch_size = batch_size

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        vectors: list[list[float]] = []
        for start in range(0, len(texts), self.batch_size):
            batch = list(texts[start : start + self.batch_size])
            vectors.extend(self.client.embed(model=self.model, input=batch)["embeddings"])
        for vector in vectors:
            if len(vector) != self.dimension:
                raise ValueError(
                    f"{self.model} should return {self.dimension} dimensions, got {len(vector)}"
                )
        return vectors


MODELS_FILE = Path(__file__).resolve().parents[2] / "config" / "models.yaml"


def _model_config(model: str, models_file: Path) -> dict:
    models = yaml.safe_load(models_file.read_text())["embedding_models"]
    if model not in models:
        raise ValueError(f"unknown embedding model {model!r}: add it to {models_file}")
    return models[model]


def embedding_dimension(model: str, models_file: Path = MODELS_FILE) -> int:
    return _model_config(model, models_file)["dimension"]


def relevance_threshold(
    model: str, env: Mapping[str, str] | None = None, models_file: Path = MODELS_FILE
) -> float:
    """Minimum top-1 similarity to answer at all (ADR-0006). RELEVANCE_THRESHOLD overrides."""
    env = read_env() if env is None else env
    if env.get("RELEVANCE_THRESHOLD"):
        return float(env["RELEVANCE_THRESHOLD"])
    config = _model_config(model, models_file)
    if "relevance_threshold" not in config:
        raise ValueError(
            f"{model} has no relevance_threshold in {models_file.name}: "
            "scores differ per model, so each one needs its own (step 5 calibrates it)"
        )
    return float(config["relevance_threshold"])


def build_embedder(settings: Settings) -> OllamaEmbedder:
    return OllamaEmbedder(
        ollama.Client(host=settings.ollama_host),
        model=settings.embed_model,
        dimension=embedding_dimension(settings.embed_model),
    )

import pytest

from talk_to_my_cv.embeddings import OllamaEmbedder


class FakeOllamaClient:
    """Mimics `ollama.Client.embed`: one vector per input, encoding the text length."""

    def __init__(self, dimension: int = 2):
        self.dimension = dimension
        self.calls: list[list[str]] = []

    def embed(self, model: str, input: list[str]) -> dict:
        self.calls.append(list(input))
        return {"embeddings": [[float(len(t))] + [0.0] * (self.dimension - 1) for t in input]}


def test_texts_are_sent_in_batches_and_vectors_keep_input_order():
    client = FakeOllamaClient()
    embedder = OllamaEmbedder(client, model="bge-m3", dimension=2, batch_size=2)

    vectors = embedder.embed(["a", "bb", "ccc", "dddd", "eeeee"])

    assert client.calls == [["a", "bb"], ["ccc", "dddd"], ["eeeee"]]
    assert [v[0] for v in vectors] == [1.0, 2.0, 3.0, 4.0, 5.0]


def test_unexpected_dimension_fails_loudly():
    embedder = OllamaEmbedder(FakeOllamaClient(dimension=3), model="bge-m3", dimension=1024)

    with pytest.raises(ValueError, match="1024.*3"):
        embedder.embed(["hello"])

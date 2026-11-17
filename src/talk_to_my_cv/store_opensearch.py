"""OpenSearch: k-NN vectors + BM25 text, and hybrid search combining both (step 6)."""

from collections.abc import Iterable, Sequence

from opensearchpy import NotFoundError, OpenSearch, helpers

from talk_to_my_cv.chunking import Chunk
from talk_to_my_cv.embeddings import Vector, cosine_similarity
from talk_to_my_cv.store import EmbeddingModel, SearchMode, SearchResult, UnsupportedSearchMode

HYBRID_PIPELINE = "talk-to-my-cv-hybrid"

# BM25 should match on content words, not on how people phrase questions. Lucene's
# English stopword list keeps "she", "has", "did"..., so we add the usual question
# words in both languages of the tutorial.
_QUESTION_WORDS = """
she her hers he him his they them their has have had did does do done what which who
whom how when where why worked work works used use uses ella él ellos su sus qué que
cuál cual cómo como cuándo cuando dónde donde quién quien tiene tuvo trabajó usó hizo
"""
QUESTION_WORDS = _QUESTION_WORDS.split()

INDEX_SETTINGS = {
    "index": {"knn": True},
    "analysis": {
        "filter": {
            "english_stop": {"type": "stop", "stopwords": "_english_"},
            "spanish_stop": {"type": "stop", "stopwords": "_spanish_"},
            "question_words": {"type": "stop", "stopwords": QUESTION_WORDS},
        },
        "analyzer": {
            "cv_text": {
                "tokenizer": "standard",
                "filter": [
                    "lowercase",
                    "asciifolding",
                    "english_stop",
                    "spanish_stop",
                    "question_words",
                    "kstem",
                ],
            }
        },
    },
}


def _mappings(model: EmbeddingModel) -> dict:
    return {
        "_meta": {"embedding_model": model.name, "dimension": model.dimension},
        "properties": {
            "content_hash": {"type": "keyword"},
            "file": {"type": "keyword"},
            "section": {"type": "keyword"},
            "text": {"type": "text", "index": False},
            "embed_text": {"type": "text", "analyzer": "cv_text"},
            "metadata": {"type": "object", "enabled": False},
            "embedding": {
                "type": "knn_vector",
                "dimension": model.dimension,
                "method": {"name": "hnsw", "engine": "lucene", "space_type": "cosinesimil"},
            },
        },
    }


class OpenSearchStore:
    """Scores are always the cosine similarity, computed here from the stored vector.

    OpenSearch's own scores can't feed the relevance gate: k-NN with cosinesimil returns
    (1 + cos) / 2, BM25 is unbounded, and hybrid min-max puts every top-1 at 1.0. So the
    search mode decides the *order*, and the score stays comparable across stores and modes.
    """

    supported_modes = frozenset(SearchMode)

    def __init__(self, url: str, index: str = "kb") -> None:
        self.client = OpenSearch(url, timeout=30)
        self.index = index
        self.client.transport.perform_request(
            "PUT",
            f"/_search/pipeline/{HYBRID_PIPELINE}",
            body={
                "description": "Min-max normalise BM25 and k-NN, then average them.",
                "phase_results_processors": [
                    {
                        "normalization-processor": {
                            "normalization": {"technique": "min_max"},
                            "combination": {
                                "technique": "arithmetic_mean",
                                "parameters": {"weights": [0.5, 0.5]},
                            },
                        }
                    }
                ],
            },
        )

    def get_model(self) -> EmbeddingModel | None:
        try:
            mapping = self.client.indices.get_mapping(index=self.index)
        except NotFoundError:
            return None
        meta = mapping[self.index]["mappings"].get("_meta", {})
        return EmbeddingModel(meta["embedding_model"], meta["dimension"]) if meta else None

    def set_model(self, model: EmbeddingModel) -> None:
        if self.client.indices.exists(index=self.index):
            self.client.indices.delete(index=self.index)
        self.client.indices.create(
            index=self.index, body={"settings": INDEX_SETTINGS, "mappings": _mappings(model)}
        )

    def fingerprints(self) -> dict[str, str]:
        if not self.client.indices.exists(index=self.index):
            return {}
        hits = helpers.scan(
            self.client, index=self.index, query={"_source": ["content_hash"]}, size=500
        )
        return {hit["_id"]: hit["_source"]["content_hash"] for hit in hits}

    def upsert(self, chunks: Sequence[Chunk], vectors: Sequence[Vector]) -> None:
        actions = [
            {
                "_index": self.index,
                "_id": c.id,
                "_source": {
                    "content_hash": c.content_hash,
                    "file": c.file,
                    "section": c.section,
                    "text": c.text,
                    "embed_text": c.embed_text,
                    "metadata": c.metadata,
                    "embedding": list(v),
                },
            }
            for c, v in zip(chunks, vectors, strict=True)
        ]
        helpers.bulk(self.client, actions, refresh="wait_for")

    def delete(self, ids: Iterable[str]) -> None:
        actions = [{"_op_type": "delete", "_index": self.index, "_id": id_} for id_ in ids]
        helpers.bulk(self.client, actions, refresh="wait_for", raise_on_error=False)

    def search(
        self, query: str, query_vector: Vector, mode: SearchMode, k: int
    ) -> list[SearchResult]:
        if mode not in self.supported_modes:
            raise UnsupportedSearchMode("OpenSearchStore", mode)
        knn = {"knn": {"embedding": {"vector": list(query_vector), "k": k}}}
        bm25 = {"match": {"embed_text": query}}
        body: dict = {"size": k}
        params: dict = {}
        if mode == SearchMode.VECTOR:
            body["query"] = knn
        elif mode == SearchMode.KEYWORD:
            body["query"] = bm25
        else:
            body["query"] = {"hybrid": {"queries": [bm25, knn]}}
            params["search_pipeline"] = HYBRID_PIPELINE
        hits = self.client.search(index=self.index, body=body, params=params)["hits"]["hits"]
        return [self._result(hit["_id"], hit["_source"], query_vector) for hit in hits]

    @staticmethod
    def _result(id_: str, source: dict, query_vector: Vector) -> SearchResult:
        chunk = Chunk(
            id=id_,
            content_hash=source["content_hash"],
            file=source["file"],
            section=source["section"],
            text=source["text"],
            embed_text=source["embed_text"],
            metadata=source["metadata"],
        )
        score = max(0.0, cosine_similarity(query_vector, source["embedding"]))
        return SearchResult(chunk, score)

    def reset(self) -> None:
        if self.client.indices.exists(index=self.index):
            self.client.indices.delete(index=self.index)

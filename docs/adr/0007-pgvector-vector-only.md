# pgvector implements only vector search; no Postgres full-text

`SearchMode` is `{vector, keyword, hybrid}`. The pgvector store implements only `vector` and raises `UnsupportedSearchMode` for the other two; the eval skips unsupported store/mode combinations and records the skip. We deliberately do not build keyword search on Postgres `tsvector`, even though it is possible: BM25 and hybrid search arrive with OpenSearch in step 6, and the vector-only baseline makes that contrast clear.

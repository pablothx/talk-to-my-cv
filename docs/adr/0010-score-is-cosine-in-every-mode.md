# The score is always cosine similarity; the search mode only decides the order

OpenSearch's native scores can't feed the relevance gate (ADR-0006):

- k-NN with `cosinesimil` returns `(1 + cos) / 2`;
- BM25 is unbounded and depends on the corpus;
- hybrid search with min-max normalisation puts every top-1 at exactly 1.0.

So every store returns `SearchResult.score` as the cosine similarity between the query and the chunk, computed client-side from the stored vector. `vector`, `keyword` and `hybrid` decide only which chunks come back and in what order. The threshold calibrated in step 5 keeps its meaning in every store and mode, and pgvector and OpenSearch give the same score for the same chunk.

## Consequences

- OpenSearch returns each chunk's vector with every hit (1024 floats each, k=5): a few KB per query, irrelevant at this scale.
- In `keyword` mode, a question whose content words never appear in the KB returns no chunks at all, so the gate refuses without the LLM. Step 6 found this is the only mode that fixes the JavaScript trap. Hybrid search loses that signal, because its vector half always returns something. Step 7 can use "no lexical match" as evidence.

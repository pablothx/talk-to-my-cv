# Relevance gate on top-1 similarity, before any LLM call

The relevance score is cosine similarity in [0, 1]; pgvector computes it as `1 - distance` with `vector_cosine_ops`.

- **Rejection:** if the top-1 chunk is below the threshold, the answer is the fixed "I don't have that information" and the LLM is never called.
- **Context:** otherwise, the context is the chunks in the top-k (k=5) that pass the threshold.

Thresholds are set per embedding model in `config/models.yaml`, because score distributions differ by model, and an env var can override them. The `bge-m3` value is provisional until step 5 calibrates it with the eval.

Gating before the LLM is deliberate: refusing to answer is deterministic, costs nothing, and cannot be talked around by a prompt.

Step 5 measured this gate: see ADR-0009 for its limits and how the threshold is now chosen.

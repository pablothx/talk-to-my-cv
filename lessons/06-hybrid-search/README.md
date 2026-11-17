# Step 6: Hybrid search with OpenSearch

🇪🇸 [Leer en español](README.es.md)

## What you'll learn

- What **BM25** (keyword search) is and how it differs from vector search.
- How to combine both into a **hybrid search** with OpenSearch.
- How to swap vector databases without changing anything else, thanks to a common interface.
- How to test a hypothesis with the eval, even when the result isn't what you expected.

## The concept

### Two ways to search

| | Vectors (k-NN) | Keywords (BM25) |
|---|---|---|
| Compares | meanings | exact words |
| "trabajé con AWS" vs "I worked with AWS" | very similar | no words in common... except "AWS" |
| "Java" vs "JavaScript" | almost the same (0.84, step 1) | different words |
| Question in Spanish, KB in English | works (`bge-m3` is multilingual) | almost always fails |

**Hybrid search** runs both, normalizes each one's scores between 0 and 1 (min-max) and averages them. The idea is to keep the best of each.

### Our hypothesis (step 1)

"Java" and "JavaScript" score 0.84 for the embedding. We expected BM25, which compares exact words, to fix step 2's JavaScript trap.

### A detail that matters: the score

Step 4's threshold compares **cosine similarity**. But OpenSearch doesn't return it:

- k-NN with `cosinesimil` returns `(1 + cosine) / 2`: an OpenSearch 0.769 is a cosine of 0.538;
- BM25 has no upper bound and depends on the whole corpus;
- hybrid with min-max **always** puts the top result at 1.0.

If we used those scores, the threshold calibrated in step 5 would stop making sense. So, in every store and every mode, **the score is the cosine**, computed from the stored vector, and the mode only decides **which chunks come back and in what order** ([ADR-0010](../../docs/adr/0010-score-is-cosine-in-every-mode.md)).

### Another detail: stopwords

With the standard analyzer, "Has she worked with JavaScript?" found chunks through "she" and "with". Lucene's English stopword list doesn't include "she" or "has". We use our own analyzer:

- it drops English and Spanish stopwords;
- it drops question words ("she", "did", "qué", "usó"...);
- it folds accents;
- it uses a light stemmer (`kstem`).

## The code

| File | What it does |
|------|--------------|
| `compose.yaml` | Adds OpenSearch 2.19 (single node, no security, 512 MB heap). |
| `src/talk_to_my_cv/store_opensearch.py` | `OpenSearchStore`: a k-NN index (HNSW, Lucene) + text with our analyzer, and the hybrid pipeline. |
| `src/talk_to_my_cv/store.py` | `supported_modes` per store, and `build_store()` to pick one from configuration. |

Switching stores is two lines in `.env`:

```bash
VECTOR_STORE=opensearch
SEARCH_MODE=hybrid      # vector | keyword | hybrid
```

pgvector only does vector search; if you ask it for `hybrid`, configuration fails at startup with a clear message ([ADR-0007](../../docs/adr/0007-pgvector-vector-only.md)).

Step 2's contract tests now run against **three** stores (in-memory, pgvector and OpenSearch) and require the same from all three, including that the score is exactly the cosine.

## Check that it works

```bash
docker compose up -d        # OpenSearch takes ~1 minute to start
make check-06
VECTOR_STORE=opensearch make ingest
VECTOR_STORE=opensearch SEARCH_MODE=hybrid make ask DEBUG=1 Q="How big is the team she leads?"
make eval-all               # every combination: ~9 min on a CPU
```

## The results

`make eval-all`, with the same 20 questions and the 0.42 threshold:

| Store · mode | hit@5 | MRR | refusal accuracy | answer accuracy |
|---|---:|---:|---:|---:|
| pgvector · vector | 1.00 | 0.82 | 0.88 | 0.82 |
| opensearch · vector | 1.00 | 0.82 | 0.88 | 0.82 |
| opensearch · keyword | 0.64 | 0.52 | 0.71 | 0.71 |
| **opensearch · hybrid** | 1.00 | **0.86** | 0.88 | 0.82 |
| pgvector · hybrid | *skipped* | | | |

The traps:

| Trap | vector | keyword | hybrid |
|---|:-:|:-:|:-:|
| JavaScript (must refuse) | ✗ says "No" | **✓ refuses** | ✗ says "No" |
| CRM / HubSpot (must answer) | ✗ | ✗ | ✗ |
| Kubernetes (must say "no") | ✓ | ✓ | ✓ |

Four things to look at:

1. **pgvector and OpenSearch give exactly the same results in vector mode.** That's the proof the cosine score is consistent across stores.
2. **Hybrid improves the order, not the hits.** MRR goes from 0.82 to 0.86. For example, for "How big is the team she leads?", vector search put `Contact` first; hybrid puts `Senior Backend Engineer` first, which contains "team" and "leads". The other metrics don't change.
3. **The JavaScript hypothesis was half right.** BM25 does help: since "JavaScript" doesn't appear in any chunk, **keyword search returns zero results** and the gate refuses without calling the LLM. But hybrid **loses that signal**, because its vector half always brings something back, and the threshold looks at the cosine. The useful information ("none of the question's keywords is in the KB") exists, but the fusion hides it. A good candidate for step 7.
4. **Keyword-only is much worse** (0.71), especially with the Spanish questions: "¿Qué idiomas habla?" ("What languages does she speak?") shares no words with "Spanish, English, Esperanto". BM25 doesn't translate. Multilingual embeddings do.

**Nobody fixes CRM:** the word "CRM" isn't in the KB, so neither vectors nor keywords find it. The fix is still writing "HubSpot (CRM)".

## Play with it

1. **Look at the lost signal.** Compare `SEARCH_MODE=keyword` and `SEARCH_MODE=hybrid` with `make ask DEBUG=1 Q="Has she worked with JavaScript?"` (with `VECTOR_STORE=opensearch`). How would you combine both without losing the "zero results"?
2. **Change the weights.** In `store_opensearch.py`, the pipeline averages with weights `[0.5, 0.5]`. Try `[0.3, 0.7]` (more vectors) and `[0.7, 0.3]` (more keywords), and run `make eval STORE=opensearch MODE=hybrid`. What happens to MRR and to the Spanish questions? Careful: picking the weights by looking at these 20 questions is overfitting (step 5).
3. **Remove the custom analyzer.** Change `embed_text` to `"analyzer": "standard"`, drop the index (`make ingest REBUILD=1` with `VECTOR_STORE=opensearch`) and see what `SEARCH_MODE=keyword` brings back for "Has she worked with JavaScript?".

## Known limitations

- **The analyzer mixes two languages** with an English stemmer. For a Spanish-only KB, OpenSearch's `spanish` analyzer is a better fit.
- **Some question words are in the stopword list**, like "worked" and "used": they add nothing when asking, but the rule is a heuristic, not a law.
- **OpenSearch runs without security.** Fine on your machine; for AWS, see [docs/produccion-en-aws.md](../../docs/produccion-en-aws.md).

# Step 6: Hybrid search with OpenSearch

🇪🇸 [Leer en español](README.es.md)

Until now we searched only by meaning. In this step we add the classic **exact-word** search and try combining the two. With step 5's eval we'll see, with numbers, whether it helps.

## What you'll learn

- What **BM25** (keyword search) is and how it differs from vector search.
- How to combine both into a **hybrid search** with OpenSearch.
- How to swap vector databases without touching the rest of the code, thanks to a common interface.
- How to test a hypothesis with the eval, even when the result isn't what you expected.

---

## Piece 1 of 8: two ways to search

| | Vectors | Keywords (BM25) |
|---|---|---|
| Compares | meanings | exact words |
| "trabajé con AWS" vs "I worked with AWS" | very similar | no words in common... except "AWS" |
| "Java" vs "JavaScript" | almost the same (0.84, step 1) | different words |
| Question in Spanish, CV in English | works (`bge-m3` is multilingual) | almost always fails |

Each one is good where the other is bad.

## Piece 2 of 8: what BM25 is

BM25 is classic text search, the kind search engines have used for decades. It gives a chunk more points when:

- it has **the question's words**;
- those words are **rare** in the collection ("Kubernetes" is worth more than "experience", which appears everywhere);
- the chunk is **short** (a word in a short text weighs more than in a long one).

It doesn't understand meaning: "cloud" and "AWS" are just different words. But it's exact: "Java" is never "JavaScript".

## Piece 3 of 8: hybrid search

**Hybrid search** runs both and combines the results:

1. Each search gives its scores, on different scales.
2. Both are normalized between 0 and 1 (*min-max*: the best in each list is worth 1 and the worst 0).
3. They're averaged, half and half.

The idea is to keep the best of each.

## Piece 4 of 8: our hypothesis

"Java" and "JavaScript" score 0.84 for the embedding. We expected BM25, which compares exact words, to fix the JavaScript trap.

We'll check it with the eval, not with an impression.

## Piece 5 of 8: OpenSearch

**OpenSearch** is a search engine (the open fork of Elasticsearch). It does both in one place: vectors and BM25. We add it to `compose.yaml`: a single node, no security (your machine only) and 512 MB of memory.

For vectors it uses an **HNSW** index: instead of comparing the question against every chunk, it hops through a graph of "near neighbors" and finds the best ones much faster. It's approximate, but with thousands of documents the speed difference is huge.

Switching stores is two lines in `.env`:

```bash
VECTOR_STORE=opensearch
SEARCH_MODE=hybrid      # vector | keyword | hybrid
```

The rest of the code doesn't notice, because `OpenSearchStore` implements the same `VectorStore` interface from step 2. pgvector only does vectors: if you ask it for `hybrid`, it fails at startup with a clear message ([ADR-0007](../../docs/adr/0007-pgvector-vector-only.md)).

## Piece 6 of 8: a detail that matters, the score

Step 4's threshold compares **cosine similarity**. But OpenSearch doesn't return it:

- for vectors it returns `(1 + cosine) / 2`: an OpenSearch 0.769 is a cosine of 0.538;
- BM25 has no upper bound and depends on every document;
- hybrid with min-max **always** puts the top result at 1.0.

If we used those numbers, the calibrated 0.42 would stop making sense. So, in every store and mode, **the score is the cosine**, computed from the stored vector. The mode only decides **which chunks come back and in what order** ([ADR-0010](../../docs/adr/0010-score-is-cosine-in-every-mode.md)).

## Piece 7 of 8: another detail, stopwords

With the standard analyzer, "Has she worked with JavaScript?" found chunks through "she" and "with". Lucene's English stopword list doesn't include "she" or "has".

An **analyzer** is what prepares text for BM25. We use our own, which:

- drops English and Spanish stopwords ("the", "de", "with"...);
- drops question words ("she", "did", "qué", "usó"...);
- strips accents ("tecnología" = "tecnologia");
- uses a light *stemmer* (`kstem`), which brings words to their root ("leads" → "lead").

## Piece 8 of 8: the contract tests, now with three stores

Step 2's contract tests now run against **three** stores (in-memory, pgvector and OpenSearch) and require the same from all three, including that the score is exactly the cosine.

| File | What it does |
|------|--------------|
| `compose.yaml` | Adds OpenSearch 2.19. |
| `src/talk_to_my_cv/store_opensearch.py` | `OpenSearchStore`: a vector index (HNSW) + text with our analyzer, and hybrid search. |
| `src/talk_to_my_cv/store.py` | `supported_modes` per store, and `build_store()` to pick one from configuration. |

---

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

Four things to notice:

1. **pgvector and OpenSearch give exactly the same results in vector mode.** That's the proof the cosine score is consistent across stores.
2. **Hybrid improves the order, not the hits.** MRR goes from 0.82 to 0.86. For "How big is the team she leads?", vectors put `Contact` first; hybrid puts `Senior Backend Engineer` first, which contains "team" and "leads".
3. **The JavaScript hypothesis was half right.** BM25 does help: since "JavaScript" isn't in any chunk, **keyword search returns zero results** and it refuses without calling the LLM. But hybrid **loses that signal**, because its vector half always brings something back. The useful information ("none of the question's keywords is in the CV") exists, but the mix hides it. A good candidate for step 7.
4. **Keyword-only is much worse** (0.71), especially in Spanish: "¿Qué idiomas habla?" shares no words with "Spanish, English, Esperanto". BM25 doesn't translate.

**Nobody fixes CRM:** the word "CRM" isn't in the CV. The fix is still writing "HubSpot (CRM)".

## Play with it

1. **Look at the lost signal.** With `VECTOR_STORE=opensearch`, compare `SEARCH_MODE=keyword` and `SEARCH_MODE=hybrid` on `make ask DEBUG=1 Q="Has she worked with JavaScript?"`. How would you combine both without losing the "zero results"?
2. **Change the weights.** In `store_opensearch.py`, hybrid averages with weights `[0.5, 0.5]`. Try `[0.3, 0.7]` and `[0.7, 0.3]`, and run `make eval STORE=opensearch MODE=hybrid`. Careful: picking the weights by looking at these 20 questions is overfitting (step 5).
3. **Remove the custom analyzer.** Change `embed_text` to `"analyzer": "standard"`, drop the index (`make ingest REBUILD=1` with `VECTOR_STORE=opensearch`) and see what `SEARCH_MODE=keyword` returns for "Has she worked with JavaScript?".

## Known limitations

- **The analyzer mixes two languages** with an English stemmer. For a Spanish-only CV, OpenSearch's `spanish` analyzer is a better fit.
- **Some question words are in the stopword list,** like "worked" and "used": they add nothing when asking, but it's a heuristic, not a law.
- **OpenSearch runs without security.** Fine on your machine; for AWS, see the [production guide](../../docs/production-on-aws.md).

---

## FAQ

<details>
<summary><b>Do I need OpenSearch for a CV?</b></summary>

No. For 20 chunks, pgvector is more than enough. OpenSearch makes sense with thousands of documents, when exact-word search matters (codes, product names), or to learn the architecture you'd use at a company.
</details>

---

## ✋ Review

**1. What is BM25 good at, and what is it bad at?**

<details><summary>Show answer</summary>

Good: exact words and rare names ("Java" is never "JavaScript"). Bad: synonyms and other languages ("cloud" doesn't find "AWS"; "idiomas" doesn't find "languages").
</details>

**2. Why is the score always the cosine, even though OpenSearch returns other numbers?**

<details><summary>Show answer</summary>

Because the threshold (0.42) was calibrated with cosines. With OpenSearch's numbers (`(1+cosine)/2`, unbounded BM25, min-max) the threshold would stop making sense. The mode decides which chunks come back; the score is always the same.
</details>

**3. Why doesn't hybrid fix JavaScript, when BM25 alone does?**

<details><summary>Show answer</summary>

Because the vector half always brings something back with a high cosine. BM25's "zero results" gets lost in the mix.
</details>

**4. 🧪 Try it:** with `VECTOR_STORE=opensearch SEARCH_MODE=keyword`, ask "¿Qué idiomas habla?". What do you expect?

<details><summary>Show answer</summary>

That it fails: "idiomas" and "habla" don't appear in the English CV. BM25 doesn't translate. Step 7 fixes it by rewriting the question in English.
</details>

**5. What does it prove that pgvector and OpenSearch give exactly the same results in vector mode?**

<details><summary>Show answer</summary>

That the common interface and the cosine score work: you can swap databases without the results changing. The contract tests require it.
</details>

---

[← Step 5](../05-evaluation/README.md) · [Index](../../README.md) · [Next: Step 7, LangGraph →](../07-langgraph/README.md)

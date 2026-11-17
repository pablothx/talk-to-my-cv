# Step 2: Chunking and ingestion

🇪🇸 [Leer en español](README.es.md)

## What you'll learn

- Why a RAG doesn't search whole documents, but **pieces** (chunks).
- How to cut Markdown so that every piece can be **cited**.
- How to make ingestion **idempotent**: running it ten times gives the same result as running it once.
- Why you must never mix vectors from two different models.

## The concept

If you embed a whole CV into a single vector, that vector is about "a bit of everything" and doesn't look much like any specific question. So we cut the document into small pieces, each with a clear topic, and embed each one.

We chose to cut **by Markdown headings**, which is how a person already organised their CV:

- each `##` (H2) is a chunk;
- if an H2 has `###` (H3) headings inside it, each H3 is its own chunk;
- a section over ~1500 characters is split by paragraph.

Each chunk stores **two texts**:

| Field | Example | What for |
|-------|---------|----------|
| `text` | `Led Project Lumen, a ledger…` | What the LLM sees, and what we cite. |
| `embed_text` | `Northwind Payments > Senior Backend Engineer > Project Lumen` + the text | What gets embedded. |

The heading path gives the embedding context. "Led Project Lumen…" alone doesn't say which company it happened at; with the path in front, it does. The section stored for citations stays clean.

### Idempotency

Each chunk has:

- an **ID** derived from the file, the section and the piece number, which is stable across runs;
- a **content hash**, which changes only when the text or the frontmatter changes.

With these, `make ingest` compares what is on disk with what is in the database:

- **New ID:** added.
- **Different hash:** only that chunk is re-embedded.
- **ID no longer on disk:** deleted.
- **Everything else:** left alone.

Embedding is the expensive part, so this matters as soon as your KB grows.

### The model lock

The database stores which model and dimension built the index, in the `kb_meta` table. If you change `EMBED_MODEL`, ingestion **fails** and asks you to run `make ingest REBUILD=1`. Vectors from two different models can't be compared: mixing them would give searches that look like they work but return garbage ([ADR-0005](../../docs/adr/0005-chunk-identity-and-embedding-model-lock.md)).

## The code

| File | What it does |
|------|--------------|
| `src/talk_to_my_cv/chunking.py` | `chunk_document(path, markdown)`: frontmatter, headings, splits, IDs and hashes. |
| `src/talk_to_my_cv/store.py` | The `VectorStore` interface, plus `InMemoryStore` (for tests) and `PgVectorStore`. |
| `src/talk_to_my_cv/ingest.py` | `ingest(kb_dir, embedder, store)`: compares, embeds what changed, deletes orphans. |
| `kb.example/` | Valentina Ríos, a fictional persona, with planted facts and traps for the eval. |
| `eval/questions.yaml` | First eval questions. Each trap is explained in a comment. |

One testing trick worth stealing: **the same contract tests run against the in-memory store and against pgvector.** So if the ingestion tests pass against the fake (fast, no Docker), we know they hold for Postgres too.

Files inside folders whose names start with `_` (for example `kb/_drafts/`) are ignored: they're drafts.

## Check that it works

```bash
make check-02
make ingest
```

```
kb.example: 19 added, 0 updated, 0 unchanged, 0 deleted
```

The second time:

```
kb.example: 0 added, 0 updated, 19 unchanged, 0 deleted
```

## Play with it

1. **Edit a section** of `kb.example/profile.md` and run `make ingest`: it should say `1 updated`. Delete a file: `N deleted`.
2. **See what search brings back for the traps.** These are our top-1 results with `bge-m3`:

   | Question | Top-1 | Score | Right chunk? |
   |----------|-------|------:|--------------|
   | How much did Project Lumen speed up reconciliation? | Project Lumen | 0.65 | ✓ |
   | ¿Usó Kubernetes? *(Did she use Kubernetes?)* | Infrastructure | 0.51 | ✓ |
   | Has she worked with JavaScript? | profile § Summary | 0.50 | there is no right chunk |
   | ¿Tiene experiencia en CRM? *(Does she have CRM experience?)* | skills § Data and messaging | 0.52 | ✗ (it was Integrations, with HubSpot) |
   | What is her favourite football team? | profile § Contact | 0.41 | there is no right chunk |

   Three things to notice:

   - **Scores are lower than in step 1.** A whole chunk has more words than a single sentence, and that dilutes the similarity.
   - **The CRM trap reproduces:** the HubSpot chunk doesn't even make the top 3. Change "HubSpot" to "HubSpot (CRM)" in `kb.example/experience/northwind-payments.md`, re-ingest, and look again.
   - **The JavaScript trap didn't behave as we expected, and that teaches more.** The Java chunk doesn't show up at the top, because inside a long chunk "Java" carries little weight. The problem is a different one: JavaScript's top-1 scores **0.50** and Kubernetes' scores **0.51**. Kubernetes has an answer ("not in production") and JavaScript doesn't. **A threshold on the top-1 score cannot separate them:** set it at 0.505 and it refuses a question that had an answer; lower it and it lets through one that doesn't.

     Step 5 will measure this across every eval question. If it holds, we revisit [ADR-0006](../../docs/adr/0006-relevance-gate-before-llm.md) and, in step 7, add a verification step with the LLM: it reads the retrieved chunks and decides whether they really answer the question.
3. **Change `EMBED_MODEL`** to another model (for example `nomic-embed-text`, after `ollama pull` and adding it to `config/models.yaml`) and run `make ingest`. Read the error.

## Known limitations

We leave these on purpose, because for this tutorial they don't change the outcome:

- **A single paragraph over 1500 characters stays one large chunk.** We split between paragraphs, never inside one. If your KB has huge paragraphs, break them up yourself.
- **The chunker doesn't tell a real heading from a `#` inside a code block.** A shell comment (`# install`) inside ```` ``` ```` would be taken as a heading. In a CV, that's rare.
- **There is no HNSW index in pgvector.** With 19 chunks, exact search compares against all of them and takes milliseconds. With thousands of chunks you need an approximate index; we cover that in step 6.

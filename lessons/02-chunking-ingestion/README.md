# Step 2: Chunking and ingestion

🇪🇸 [Leer en español](README.es.md)

In this step we turn the CV into database rows: each row is a piece with its text, its origin and its embedding. This is **ingestion**, and it runs once (and again whenever the CV changes).

## What you'll learn

- Why a RAG doesn't search whole documents, but **pieces** (chunks).
- How to cut a CV so every piece can be **cited**.
- What goes into each column of the table, and why.
- How to make ingestion **idempotent**: running it ten times gives the same result as running it once.
- Why you must never mix vectors from two models.

---

## Piece 1: why cut

If you embed a whole CV into a single vector, that vector is about "a bit of everything" and doesn't look much like any concrete question. So we cut the document into small pieces, each with a clear topic, and embed each one.

## Piece 2: the example CV

`kb.example/` is the CV of **Valentina Ríos**, a fictional person. It's 6 Markdown files:

```
kb.example/
├── profile.md                       summary, languages, contact
├── skills.md                        technologies
├── education.md
├── projects.md
└── experience/
    ├── northwind-payments.md        her current job
    └── brightcart.md                her previous job
```

It has **planted facts**: things impossible to guess, like Project Lumen cutting reconciliation "from 9 hours to 14 minutes". If the chat answers that, we know it read it from the document and didn't make it up. It also has **traps** for the evaluation (step 5).

## Piece 3: how we cut

We cut **by Markdown headings**, which is how a person already organized their CV:

- each `##` (H2) is a chunk;
- if the H2 has `###` (H3) inside, each H3 is its own chunk;
- if a section goes over ~1500 characters (half a page), it's split by paragraphs, **never mid-paragraph**.

Every line of the document lands in some chunk: nothing is lost. Valentina's CV becomes **19 chunks**.

## Piece 4: the frontmatter

Each file starts with a data block, the *frontmatter*:

```yaml
---
type: experience
title: Northwind Payments
company: Northwind Payments
role: Senior Backend Engineer
start: 2021-04
end: present
tags: [java, aws, kafka, payments]
---
```

It's copied as `metadata` into every chunk of the file. The `title` is used in the heading path (piece 6). The rest is stored but **not used for search today**: it's ready for future filtering (for example, "experience only" or "this person only") without re-ingesting.

## Piece 5: the table

Each chunk is a row in the `chunks` table in Postgres:

| Column | Example | What it's for |
|---|---|---|
| `id` | `7e9435d0b4dacd6f` | Identifies the chunk (piece 7). |
| `content_hash` | `d9d676b4151156a9` | Detects whether the chunk changed (piece 7). |
| `file` | `experience/northwind-payments.md` | Where it came from. |
| `section` | `Senior Backend Engineer > Project Lumen` | The heading path. With `file`, it forms the **citation**. |
| `text` | `Led Project Lumen, a ledger…` | The piece's text, clean. |
| `embed_text` | `Northwind Payments > Senior Backend Engineer > Project Lumen` + the text | What gets embedded and what the LLM reads (piece 6). |
| `metadata` | `{"company": "Northwind Payments", ...}` | The frontmatter. |
| `embedding` | `[-0.028, 0.012, ...]` | 1024 numbers, from `embed_text`. |

You can look at it yourself:

```bash
docker compose exec postgres psql -U postgres -d talk_to_my_cv
```

```sql
\d chunks
select file, section from chunks;
```

## Piece 6: why `embed_text` starts with the headings

The Project Lumen chunk says *"Led Project Lumen, a ledger reconciliation engine..."*. Nowhere does it say **Northwind Payments**: that's in the file's title.

If you ask "what did she do at Northwind?", without the headings that chunk wouldn't look like the question. So the embedded text is **the heading path + the text**:

```
Northwind Payments > Senior Backend Engineer > Project Lumen

Led Project Lumen, a ledger reconciliation engine...
```

And the LLM gets **the same**: if search found the chunk thanks to "Northwind", the LLM must be able to read "Northwind". We learned that the hard way in step 5.

## Piece 7: idempotent ingestion

Embedding is the expensive part. We don't want to re-embed everything when a comma changes. Each chunk has two fingerprints:

- an **`id`** built from the file, the section and the piece number. It doesn't change between runs.
- a **`content_hash`** built from the text and the metadata. It changes only when the content changes.

`make ingest` compares what's on disk with what's in the database:

| Situation | What it does |
|---|---|
| New `id` | Adds it (and embeds it). |
| Same `id`, different `content_hash` | Re-embeds it. |
| `id` no longer on disk | Deletes it. |
| Nothing changed | Leaves it alone. |

```
kb.example: 19 added, 0 updated, 0 unchanged, 0 deleted      ← the first time
kb.example: 0 added, 0 updated, 19 unchanged, 0 deleted      ← the second
```

## Piece 8: the model lock

The database records which model built it, in another table, `kb_meta`:

```
 model  | dimension
--------+-----------
 bge-m3 |      1024
```

If you change `EMBED_MODEL`, ingestion **fails** with this message:

```
The index was built with bge-m3 (1024 dims), but EMBED_MODEL is ... Vectors from
different models can't be compared: run `make ingest REBUILD=1` to start over.
```

Mixing vectors from two models would give searches that **look like they work but return junk**. A loud error beats a silent one ([ADR-0005](../../docs/adr/0005-chunk-identity-and-embedding-model-lock.md)).

## Piece 9: your CV as a PDF

If you put a PDF in `kb/`, ingestion converts it to Markdown **in memory**, with fixed rules and **no LLM** (so nothing can be made up):

- the first line is the title (your name);
- an ALL-CAPS line (`PROFESSIONAL EXPERIENCE`) opens a `##` section;
- a line ending in a year range (`Senior Engineer, Acme (2021 – Present)`) opens a `###` subsection: one chunk per job, with the company in the heading path.

Files inside folders starting with `_` (like `kb/_drafts/`) are skipped.

## Piece 10: the stores and the contract tests

The code doesn't talk to Postgres directly, but to an interface, `VectorStore` (`upsert`, `delete`, `search`...). There are two implementations:

- `InMemoryStore`: in memory, for tests. Fast and no Docker.
- `PgVectorStore`: Postgres with pgvector, for real life.

**The same contract tests run against both.** If ingestion works against the in-memory one, we know it works against Postgres. In step 6 a third one joins, OpenSearch, and the same tests check it.

| File | What it does |
|------|--------------|
| `src/talk_to_my_cv/chunking.py` | `chunk_document(path, markdown)`: frontmatter, headings, splits, IDs and hashes. |
| `src/talk_to_my_cv/store.py` | `VectorStore`, `InMemoryStore` and `PgVectorStore`. |
| `src/talk_to_my_cv/ingest.py` | `ingest()`: compares, embeds what changed and deletes orphans. |
| `src/talk_to_my_cv/pdf.py` | PDF → Markdown with fixed rules. |

---

## Check that it works

```bash
make check-02
make ingest
```

## Play with it

1. **Edit a section** of `kb.example/profile.md` and run `make ingest`: it should say `1 updated`. Delete a file: `N deleted`.
2. **Look at what search returns for the traps.** These are our top-1 results:

   | Question | Top-1 | Score | Right chunk? |
   |----------|-------|------:|--------------|
   | How much did Project Lumen speed up reconciliation? | Project Lumen | 0.65 | ✓ |
   | ¿Usó Kubernetes? | Infrastructure | 0.51 | ✓ |
   | Has she worked with JavaScript? | profile § Summary | 0.50 | there's no right chunk |
   | ¿Tiene experiencia en CRM? | skills § Data and messaging | 0.52 | ✗ (it was Integrations, with HubSpot) |
   | What is her favourite football team? | profile § Contact | 0.41 | there's no right chunk |

   - **Scores are lower than in step 1.** A chunk has more words than a single sentence, and that dilutes similarity.
   - **The CRM trap shows up:** the HubSpot chunk isn't even in the top 3. Change "HubSpot" to "HubSpot (CRM)" in `kb.example/experience/northwind-payments.md`, re-ingest and look again.
   - **JavaScript and Kubernetes are neck and neck:** 0.50 and 0.51. Kubernetes has an answer ("not in production") and JavaScript doesn't. **A threshold on the top-1 can't separate them.** Step 5 measures it and step 7 solves it.
3. **Change `EMBED_MODEL`** to another model (for example `nomic-embed-text`, after `ollama pull` and adding it to `config/models.yaml`) and run `make ingest`. Read the error.

## Known limitations

- **A paragraph over 1500 characters stays as one big chunk.** We never split mid-paragraph. It happens often with PDFs, because the extracted text has no blank lines between paragraphs.
- **The chunker can't tell a real heading from a `#` inside a code block.** Rare in a CV.
- **There's no index in pgvector.** With 19 chunks, comparing against all of them takes milliseconds. With thousands you need an approximate index (HNSW); we see it in step 6.
- **The `text` column isn't read today.** Since step 5's fix, the LLM gets `embed_text`. `text` is kept in case you want to show the clean piece.
- **Metadata is barely used.** Only the title. To separate people or filter by type, `search()` would need a filter.

---

## FAQ

<details>
<summary><b>If I give it a 20-page CV, does it cover all of it?</b></summary>

Yes: every line lands in some chunk. Long sections are split by paragraph, so 20 pages may give 60 or 80 chunks. But storing everything isn't using everything: for each question the LLM only sees the 5 most similar. A question whose answer is spread over many chunks ("how many years has she worked in total?") may go wrong.
</details>

<details>
<summary><b>Can I load 100 CVs and ask "give me the 20 with the most Java experience"?</b></summary>

Not as it is. There are two problems:

1. **People get mixed up:** the top 5 may bring chunks from 5 different people, and the LLM blends them. You'd need a `candidate_id` in the metadata and a per-person filter before searching.
2. **"The 20 with the most..." isn't a search, it's a ranking.** You have to look at all 100, compute years of Java for each and sort. A RAG brings what *looks* most similar, not what *has* the most. For that you use **structured extraction**: at ingestion, an LLM pulls a fixed record from each CV (skills, years per skill) into a table, and you answer with SQL (`ORDER BY java_years DESC LIMIT 20`).

Also watch out for third parties' personal data (you need a legal basis to process it) and for ranking people with AI: the EU AI Act treats it as high risk.
</details>

<details>
<summary><b>How do I get into the database to look at the chunks?</b></summary>

`docker compose exec postgres psql -U postgres -d talk_to_my_cv`, then `select file, section from chunks;`. With a GUI (DBeaver, TablePlus): host `localhost`, the port from `POSTGRES_PORT` (5432 by default), database `talk_to_my_cv`, user and password `postgres`.
</details>

---

## ✋ Review

**1. Why don't we embed the whole CV into a single vector?**

<details><summary>Show answer</summary>

Because a vector of the whole CV is about "a bit of everything" and doesn't look like any concrete question. Also, without pieces we couldn't cite which section the answer came from.
</details>

**2. 🧪 Try it:** run `make ingest` twice in a row. What do you expect the second run to say?

<details><summary>Show answer</summary>

`0 added, 0 updated, 19 unchanged, 0 deleted`. The `content_hash` values didn't change, so it re-embeds nothing.
</details>

**3. What's the difference between `id` and `content_hash`?**

<details><summary>Show answer</summary>

The `id` says **which** chunk it is (file + section + piece number) and doesn't change if you edit the text. The `content_hash` says **what it contains**, and changes if the text or metadata changes. With both, ingestion knows whether a chunk is new, changed or gone.
</details>

**4. Why does `embed_text` start with the heading path?**

<details><summary>Show answer</summary>

Because a chunk's text often doesn't name the company or the role: those are in the headings. With the path in front, the embedding "knows" which job that piece belongs to, and a question about the company finds it.
</details>

**5. You changed `EMBED_MODEL` and `make ingest` fails. Is it a bug?**

<details><summary>Show answer</summary>

No, it's the lock: the database was built with another model and its vectors can't be compared with the new ones. `make ingest REBUILD=1` wipes everything and re-embeds with the new model.
</details>

---

[← Step 1](../01-embeddings/README.md) · [Index](../../README.md) · [Next: Step 3, first RAG →](../03-first-rag/README.md)

# PRD: talk-to-my-cv, steps 0–5

## Problem

Engineers who want to learn RAG get stuck between toy notebooks and cloud-heavy tutorials that need API keys and a credit card. This project is a tutorial and template repo: in one day, the learner builds a chat that answers questions about a CV, cites its sources, refuses what it doesn't know, and is measured with an eval. Everything runs locally and for free.

## Users

- **Learner:** follows the lessons step by step, in English or Spanish.
- **Template user:** forks the repo, drops their own Markdown into `kb/`, and gets their own CV chat.
- **Author:** uses the project to learn and as a portfolio piece for AI Engineer roles.

## Non-negotiable requirements

1. `git clone` → `docker compose up -d` → `make ingest` → `make chat` works with no API keys, accounts or cost. The defaults are Ollama `qwen2.5:3b` and `bge-m3` (ADR-0004).
2. Each step runs on its own from its `step-NN` tag, and `make check-NN` passes there (ADR-0002).
3. The chat answers only from the KB, in the third person, in the language of the question. Every answer cites file and section; anything else gets a short refusal.
4. When nothing passes the relevance gate, the LLM is never called (ADR-0006).

## Out of scope (today)

OpenSearch and hybrid search (step 6), LangGraph (step 7), FastAPI and the web UI (step 8), the AWS production doc, and LLM-as-judge faithfulness.

## Shared conventions

These are stated once here and in `CLAUDE.md`; the steps below assume them.

- **Config:** settings come from env and `.env`, through `pydantic-settings` in `talk_to_my_cv/config.py`. Per-model data (embedding dimension, relevance threshold) lives in `config/models.yaml`.
- **Tests:** `make test` runs ruff and the unit tests. `make test-e2e` runs the tests marked `e2e`, which need Ollama, pgvector and the configured `LLM_PROVIDER`.
- **`make check-NN`** = `make test`, then the e2e tests for steps ≤ NN, then any step-specific smoke command. It exits non-zero on any failure.
- **Lessons:** each lesson ships `lessons/NN-name/README.es.md` (drafted first, then approved by the user) and `README.md` (generated after approval), cross-linked.

---

## Step 0: Setup

**Goal:** a clean, reproducible skeleton that a learner can bring up in 10 minutes.

**Scope**
- Python 3.12 project managed with `uv`: `pyproject.toml`, `src/talk_to_my_cv/`, `tests/`, and pytest with the `e2e` marker registered and excluded by default.
- `compose.yaml`:
  - `pgvector/pgvector` (pg16) with a healthcheck and a named volume.
  - An `ollama` service behind `profiles: [ollama]`.
- `.env.example`, which documents every setting: `OLLAMA_HOST`, `LLM_PROVIDER=ollama`, `LLM_MODEL`, `EMBED_MODEL`, `GROQ_API_KEY` (empty), `DATABASE_URL`, `KB_DIR=kb.example`.
- `talk_to_my_cv/config.py`, a typed settings object.
- `make doctor`, which checks each item below with a ✓/✗ line and an actionable hint:
  - `uv` installed
  - Docker running
  - Postgres reachable
  - Ollama reachable at `OLLAMA_HOST`
  - both models pulled
  - if `LLM_PROVIDER=groq`, `GROQ_API_KEY` set
- Repo hygiene:
  - MIT `LICENSE`.
  - `.pre-commit-config.yaml` with gitleaks and ruff (lint + format).
  - GitHub Actions CI running `make test`.
- `README.md` and `README.es.md` skeletons (quickstart plus a table of steps), and lesson `lessons/00-setup/`.

**`make check-00` passes when**
- [ ] `make test` is green: ruff is clean and the unit tests for config pass (defaults, env override, `LLM_PROVIDER` validation).
- [ ] `make doctor` exits 0 on a machine with the stack up.
- [ ] `make doctor` exits non-zero with a hint when Ollama is down or a model is missing. This is covered by unit tests with fake probes.
- [ ] `docker compose up -d` brings pgvector to `healthy`.
- [ ] `pre-commit run --all-files` passes.

## Step 1: Embeddings

**Goal:** understand what an embedding is and see why similarity works.

**Scope**
- The `Embedder` protocol and `OllamaEmbedder`, which batches requests (ADR-0003).
- `FakeEmbedder`, deterministic, for unit tests.
- A `cosine_similarity` helper.
- `make embed TEXT="..."` prints the dimension and the first values.
- `make similar`, a demo that ranks a few sentences against a query.
- Lesson `lessons/01-embeddings/`.

**`make check-01` passes when**
- [ ] The unit tests for `cosine_similarity` pass (identical texts, orthogonal texts, zero-vector guard), and so do the batching tests.
- [ ] An e2e test confirms that `bge-m3` returns 1024-dimensional vectors.
- [ ] An e2e test confirms that a paraphrase scores higher than an unrelated sentence.

## Step 2: Chunking and ingestion

**Goal:** turn the KB into cited, idempotently stored chunks.

**Scope**
- `kb.example/`: a fictional persona, written in English, with these files:
  - `profile.md`
  - `experience/<company>.md` × 2–3
  - `skills.md`
  - `projects.md`
  - `education.md`

  Frontmatter: `type`, `title`, `company?`, `role?`, `start?`, `end?`, `tags[]`. The KB includes ≥ 4 planted facts.
- Markdown chunker (CLAUDE.md conventions):
  - Split by H2, or by H3 when present.
  - Sections over ~1500 chars are split by paragraph.
  - The embedded text carries the heading breadcrumb.
  - Stored metadata: file, bare section path, frontmatter.
- The `VectorStore` interface and `PgVectorStore` (ADR-0005, ADR-0007):
  - Schema created on first use.
  - `kb_meta` stores the model and dimension.
  - Deterministic chunk ids and content hashes.
  - Orphan deletion.
  - `UnsupportedSearchMode` for `keyword`/`hybrid`.
- `make ingest`, which reports added, updated, unchanged and deleted chunks. `REBUILD=1` drops and recreates the index.
- Lesson `lessons/02-chunking-ingestion/`.

**`make check-02` passes when**
- [ ] The chunker's unit tests pass. They cover heading levels, long-section splitting, frontmatter-to-metadata, breadcrumb-in-embedded-text-only, and stable ids across runs.
- [ ] The ingestion's unit tests pass, using `FakeEmbedder` and an in-memory store. A second run gives 0 added and 0 updated. Editing one section re-embeds only that chunk. Deleting a file removes its chunks.
- [ ] An e2e test: `make ingest` on `kb.example/` into pgvector stores > 0 chunks, and a rerun reports everything unchanged.
- [ ] An e2e test: a model/dimension mismatch fails with a message that names `make ingest REBUILD=1`.

## Step 3: First RAG

**Goal:** retrieve, then generate; the first end-to-end answers.

**Scope**
- The `ChatModel` protocol with `OllamaChatModel` and `GroqChatModel`, selected by `LLM_PROVIDER` (ADR-0004). Both use `temperature=0` and a fixed seed where the provider supports it.
- `FakeChatModel` for unit tests.
- A `rag.answer(question)` pipeline: embed the question, `store.search(mode=vector, k=5)`, build the prompt, generate.
- The prompt rules:
  - Answer only from the context.
  - Third person.
  - Same language as the question.
  - Only about the persona's experience.
  - A short refusal for anything else.
  - No tools or secrets in the prompt.
- `make chat` (REPL) and `make ask Q="..."` (one shot).
- Lesson `lessons/03-first-rag/`, which includes the "No GPU" section with measured tok/s.

**`make check-03` passes when**
- [ ] The unit tests pass. Prompt assembly includes the retrieved chunks and the language and persona rules. The pipeline wires store → prompt → model, checked with fakes.
- [ ] An e2e test on `kb.example/`: a question about the persona's experience returns an answer containing the expected key fact.
- [ ] An e2e test: a technical-stack question returns an answer that names the expected technologies.
- [ ] An e2e test: an unanswerable question gets a refusal. In this step, the refusal comes from the prompt only.

## Step 4: Citations and the relevance gate

**Goal:** make answers checkable and make refusal deterministic.

**Scope**
- Answers cite `file § section` for every chunk used. The citations come from metadata, not invented by the LLM.
- The relevance gate (ADR-0006):
  - The top-1 cosine similarity is compared against the per-model threshold from `config/models.yaml`, which an env var can override.
  - Below the threshold, the pipeline returns the fixed refusal without calling `ChatModel`.
  - Above it, the context is the top-k chunks that pass.
- Both the CLI and `make ask` show the citations.
- Lesson `lessons/04-citations-threshold/`.

**`make check-04` passes when**
- [ ] The unit tests pass. Below the threshold, `FakeChatModel` is never called and the refusal is returned. Above it, only passing chunks reach the prompt. The citations match the chunk metadata. The threshold is looked up per embedding model, and the env override works.
- [ ] An e2e test: the answerable question cites the expected file and section.
- [ ] An e2e test: the stack question cites `skills.md` or the relevant experience file.
- [ ] An e2e test: the unanswerable question is refused, with a spy proving the LLM was not called.
- [ ] An e2e test: a Spanish question gets a Spanish answer.

## Step 5: Evaluation

**Goal:** measure retrieval and refusal, and calibrate the threshold with data.

**Scope**
- `eval/questions.yaml` with ~20 questions, mixing English and Spanish:
  - ≥ 8 answerable, each with `expected_sources` (file + section) and `expected_answer`.
  - ≥ 6 unanswerable (they must be refused).
  - ≥ 4 about planted facts.
- `make eval STORE=pgvector MODE=vector`:
  - Computes hit@k, MRR and refusal accuracy (correct refusals plus correct non-refusals).
  - Unsupported store/mode combinations are skipped and the skip is recorded.
  - Output: `eval/results/<YYYY-MM-DD>_<store>_<mode>_<embed-model>.md` plus `.json`. Raw per-question output goes to `eval/results/raw/`.
- `make eval-sweep` reports refusal accuracy across a range of thresholds. The calibrated `bge-m3` threshold is committed to `config/models.yaml`.
- Lesson `lessons/05-evaluation/`. Its "para jugar" is calibrating the threshold.

**`make check-05` passes when**
- [ ] The unit tests pass. hit@k and MRR are checked on hand-built rankings, refusal accuracy on hand-built outcomes, and the questions YAML is schema-validated (the type counts above are enforced).
- [ ] An e2e test: `make eval STORE=pgvector MODE=vector` writes both summary files with all three metrics.
- [ ] An e2e test: `MODE=hybrid` on pgvector is reported as skipped, not as a failure.
- [ ] The committed summary for the calibrated threshold shows refusal accuracy ≥ 0.9 and hit@5 ≥ 0.8 on `kb.example/`. The targets are set here and revised in the lesson if reality disagrees.

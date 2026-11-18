# talk-to-my-cv

A bilingual tutorial and template repo: learn RAG by building a chat with your CV. It must run 100% locally and for free: `git clone` → `docker compose up` → `make ingest` → `make chat`, with no API keys or accounts.

Before changing architecture, read `docs/adr/`. Terms (chunk, section path, relevance gate, refusal, planted fact) are defined in `GLOSSARY.md`.

## Language

- Code, identifiers, comments and commit messages are in English (Conventional Commits).
- `README.md` is in English and links to `README.es.md` at the top. Every lesson has both files, and each links to the other.

## Code layout

- One package, `src/talk_to_my_cv/`, grows step by step. `lessons/NN-name/` holds only READMEs (ADR-0002).
- Every model call goes through our own `Embedder` / `ChatModel` interfaces. LangChain and LangGraph enter only at step 7 (ADR-0003).
- Defaults always satisfy the no-keys requirement: `LLM_PROVIDER=ollama` in code and `.env.example`. Groq is opt-in (ADR-0004).
- `ENGINE=pipeline` (steps 3–6, `rag.answer`) or `ENGINE=graph` (step 7, `graph.answer_with_graph`): same arguments, same `Answer`. The pipeline stays as the lessons wrote it.
- The API (`api.py`, step 8) gets a `question → Answer` function injected (`create_app(ask)`). Every dynamic value in the page goes through `html.escape`, and the page has no JavaScript (CSP `script-src 'none'`).
- The vector stores implement `VectorStore` (`upsert`, `search(query, mode, k)`). An unsupported mode raises `UnsupportedSearchMode` (ADR-0007).
- The KB is Markdown with frontmatter (or a CV as PDF, `pdf.py`: fixed rules, no LLM) under `KB_DIR`: `kb.example/` is a fictional persona written in English, and `kb/` holds the user's real data and is gitignored. Path parts starting with `_` are skipped.
- Chunks are split by H2 (H3 when present). Sections over ~1500 chars are split by paragraph. The embedded text is prefixed with the heading breadcrumb; the stored section stays bare for citations.

## Testing

- Work test-first with `/tdd`.
- Unit tests use fakes and are the only tests in CI.
- E2E tests are marked `@pytest.mark.e2e` and assert citations, refusal and key facts, never exact wording (ADR-0008).

## Closing a step

A step closes only in this order:

1. `make check-NN` passes, and its code runs on its own.
2. Claude drafts `lessons/NN-name/README.es.md` from what was built and what was hard. The draft follows the lesson structure: what you'll learn, the concept (short), the code, how to verify it works, and "para jugar" (an experiment).
3. The user edits and approves the Spanish draft.
4. Only after that approval, Claude writes `README.md` in English.
5. Tag `step-NN`. Tags are never moved; fixes go forward.

## Eval

- `eval/questions.yaml` holds three kinds of questions: answerable, unanswerable (the bot must refuse) and planted facts.
- Each run writes `eval/results/<YYYY-MM-DD>_<store>_<mode>_<embed-model>.md` (with `_graph` before the model for `ENGINE=graph`) plus a `.json` with the same metrics, and both are committed. Raw runs go to `eval/results/raw/`, which is gitignored.

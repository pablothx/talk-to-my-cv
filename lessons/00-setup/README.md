# Step 0: Setup

🇪🇸 [Leer en español](README.es.md)

Before writing a single line of RAG, we get the machine ready and check with one command that everything is in place. If you haven't read the [fundamentals](../fundamentals/README.md), start there.

## What you'll learn

- What pieces a local RAG has and where each one runs.
- How to get a Python project ready in minutes with `uv`.
- How to check the environment with `make doctor` before you start.
- Two design ideas that repeat throughout the tutorial.

---

## Piece 1: the three pieces of a RAG

A RAG needs three things:

1. **An embedding model**, which turns text into vectors. We use `bge-m3`.
2. **A place to store and search those vectors.** We use Postgres with the **pgvector** extension, which teaches Postgres to store lists of numbers and compare them.
3. **An LLM that writes the answer.** We use `qwen2.5:3b`.

Both models run in **Ollama**, a program that serves models on your machine. The code talks to it over HTTP, like any other API.

## Piece 2: what runs where

```
your machine
├── uv / Python  ──►  Ollama (native, :11434)     embeddings + LLM
└── docker compose ─► Postgres + pgvector (:5432) vectors
```

- **Python runs on your machine**, not in Docker. That keeps the edit → run loop instant and the debugger working with no setup ([ADR-0001](../../docs/adr/0001-python-on-host-infra-in-compose.md)).
- **Docker only runs the infrastructure:** the database (and, in step 6, OpenSearch).
- **Ollama runs natively,** so it can use your GPU if you have one.

Everything is free and local: no API keys, no accounts.

## Piece 3: the tools

| Tool | What it is | What we use it for |
|---|---|---|
| **uv** | A very fast Python project manager | Installs Python and the dependencies, and runs commands |
| **Docker / compose** | Containers | Running Postgres without installing it |
| **make** | A command shortcut | `make chat` instead of a long command |
| **Ollama** | A model server | Local embeddings and LLM |

Every `make something` is a shortcut: to see what it does, open the `Makefile`. `make help` lists them all.

## Piece 4: the setup files

| File | What it's for |
|------|---------------|
| `pyproject.toml` | Dependencies, test settings (`e2e` tests are excluded by default) and ruff (the linter). |
| `uv.lock` | The exact versions of everything, so your install matches ours. |
| `compose.yaml` | Postgres with pgvector, with a *healthcheck* (Docker knows when it's ready). Ollama in a container is optional (`--profile ollama`). |
| `.env.example` | Every variable, with its default explained. You copy it to `.env`. |
| `src/talk_to_my_cv/config.py` | `load_settings()`: reads `.env` and validates each variable. |
| `src/talk_to_my_cv/doctor.py` | `make doctor`: checks the environment and tells you how to fix what fails. |
| `.pre-commit-config.yaml` | On every commit: **gitleaks** (stops you if a key slips in) and **ruff** (code style). |
| `.github/workflows/ci.yml` | On every push, GitHub runs the linter and the unit tests. |

## Piece 5: the `.env`

All configuration lives in a `.env` file, which **is never committed**. The most important ones:

```bash
LLM_PROVIDER=ollama      # who writes the answers
LLM_MODEL=qwen2.5:3b
EMBED_MODEL=bge-m3       # who makes the embeddings
DATABASE_URL=postgresql://postgres:postgres@localhost:5432/talk_to_my_cv
KB_DIR=kb.example        # where the CV comes from: the example, or `kb` for yours
```

If you set an invalid value (for example `LLM_PROVIDER=chatgpt`), `config.py` fails at startup with a message naming the wrong variable. Better to fail at the start than halfway through.

## Piece 6: `make doctor`

Before you start, `make doctor` checks everything and tells you what's missing:

```
✓ uv installed
✓ Docker running
✓ Postgres reachable
✓ Ollama reachable
✓ model bge-m3 pulled
✓ model qwen2.5:3b pulled
```

If something fails, it gives you **a concrete hint** ("run `ollama pull bge-m3`"). And if Ollama is down, it doesn't also say "the model is missing": it skips those checks and gives you one useful hint.

## Piece 7: two design ideas you'll see throughout the tutorial

**1. Configuration takes the environment as a parameter.** `load_settings(env={...})` in tests and `load_settings()` in real life. That way we test defaults and errors without touching global variables:

```python
def test_groq_without_api_key_fails_pointing_to_the_variable():
    with pytest.raises(ValueError, match="GROQ_API_KEY"):
        load_settings(env={"LLM_PROVIDER": "groq"})
```

**2. The doctor takes injectable *probes*.** A *probe* is the function that actually checks something (does Ollama answer?). The doctor's logic (what to check, what to skip, what to suggest) is separate from the probes. Tests pass fake probes ("Ollama is down") and check the report, without needing Ollama.

Both are the same idea: **inject what comes from outside**, so you can test the logic with fake pieces. You'll see it in every step.

## Piece 8: two levels of tests

- **Unit tests** (`make test`): use fake pieces, run in milliseconds and are the only ones that run on GitHub.
- **End-to-end tests** (`make test-e2e`): talk to the real Ollama and Postgres. They never compare an answer's exact text, because an LLM doesn't always say the same thing ([ADR-0008](../../docs/adr/0008-tests-against-nondeterministic-llms.md)).

And each step has its **`make check-NN`**: it runs the unit tests, the e2e tests of every step up to that one, and a final check. A step is done when its check passes.

---

## Check that it works

```bash
cp .env.example .env
ollama pull bge-m3 && ollama pull qwen2.5:3b
make install
make check-00
```

You should see the ✓ lines above and, at the end:

```
✓ step 00 OK
```

### Problems we hit (and you might too)

- **`Bind for 0.0.0.0:5432 failed: port is already allocated`.** You already have another Postgres on that port. In `.env`, set `POSTGRES_PORT=5433` and change the port in `DATABASE_URL` too.
- **`invalid go version` when installing the hooks.** The classic gitleaks hook builds with your system's Go, and fails if it's old. That's why we use `gitleaks-docker`: it only needs Docker.

### No GPU

On a Ryzen 7 4700U without a GPU, `qwen2.5:3b` generates 3 to 4 words (tokens) per second: an answer takes 11 to 25 seconds. It works, but it isn't a fluid conversation. If your machine is similar, you can set `LLM_PROVIDER=groq` with a free `GROQ_API_KEY`; embeddings stay local. Full numbers in [lesson 3](../03-first-rag/README.md#no-gpu).

## Play with it

1. Stop Ollama, run `make doctor` and see how the report changes. Also try `OLLAMA_HOST=http://localhost:1 make doctor`.
2. Set `LLM_PROVIDER=groq` in `.env` without `GROQ_API_KEY`. Where does it fail and what does it say?
3. Add a new probe to `doctor.py` (for example, that `.env` exists). Write the test first.

---

## ✋ Review

**1. Why does Python run on your machine and not in a container?**

<details><summary>Show answer</summary>

So editing and running is instant and the debugger works with no setup. Docker only runs the infrastructure (Postgres, OpenSearch). It's in ADR-0001.
</details>

**2. 🧪 Try it:** run `LLM_PROVIDER=chatgpt make doctor`. Before looking: does it fail in the doctor or earlier?

<details><summary>Show answer</summary>

Earlier: `load_settings()` validates `LLM_PROVIDER` at startup and the message names the variable. Invalid configuration never gets used.
</details>

**3. Why doesn't the doctor say "model bge-m3 missing" when Ollama is down?**

<details><summary>Show answer</summary>

Because it would be a false diagnosis: if Ollama doesn't answer, it can't know whether the model is there. It skips those checks and gives one useful hint: start Ollama.
</details>

**4. Which tests run on GitHub, and why not the others?**

<details><summary>Show answer</summary>

Only the unit tests, which use fake pieces. The e2e tests need Ollama, Postgres and multi-GB models, which GitHub doesn't have. Also, an LLM's output varies, so e2e tests only check behavior, never exact text.
</details>

**5. What does gitleaks prevent?**

<details><summary>Show answer</summary>

Committing a key by accident (for example, your `GROQ_API_KEY`). It scans every commit and stops it if it finds something that looks like a secret.
</details>

---

[← Fundamentals](../fundamentals/README.md) · [Index](../../README.md) · [Next: Step 1, embeddings →](../01-embeddings/README.md)

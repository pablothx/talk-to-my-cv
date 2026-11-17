# Step 0: Setup

🇪🇸 [Leer en español](README.es.md)

## What you'll learn

- Which pieces a local RAG is made of, and where each one runs.
- How to get a Python project ready in minutes with `uv`.
- How to check, with a single command (`make doctor`), that everything is in place before writing a line of RAG.

## The concept

A RAG needs three things:

1. **An embedding model**, which turns text into vectors. We use `bge-m3`.
2. **A place to store and search those vectors.** We use Postgres with the pgvector extension.
3. **An LLM that writes the answer.** We use `qwen2.5:3b`, or Groq if your machine has no GPU (see below).

In this project, **Python runs on your machine** with `uv` and **Docker only starts the database**. Ollama runs natively. That keeps the edit → run loop instant, and the debugger works without any extra setup ([ADR-0001](../../docs/adr/0001-python-on-host-infra-in-compose.md)).

```
your machine
├── uv / Python  ──►  Ollama (native, :11434)    embeddings + LLM
└── docker compose ─► pgvector (:5432)           vectors
```

Everything is free and local by default: no API keys, no accounts.

## The code

| File | What it's for |
|------|---------------|
| `pyproject.toml` | Dependencies, pytest config (`e2e` tests excluded by default) and ruff. |
| `compose.yaml` | pgvector with a healthcheck. Containerised Ollama is optional (`--profile ollama`). |
| `.env.example` | Every setting, with its default explained. |
| `src/talk_to_my_cv/config.py` | `load_settings(env)`: typed, validated settings. |
| `src/talk_to_my_cv/doctor.py` | `make doctor`: checks your environment and tells you how to fix what fails. |
| `.pre-commit-config.yaml` | gitleaks (so a key never slips into a commit) and ruff on every commit. |

You'll see two design choices repeated throughout the tutorial.

**1. Settings take the environment as a parameter.** Tests call `load_settings(env={})`, and real runs call `load_settings()`, which reads `.env` and the process environment. That way we test defaults and validation without touching global state:

```python
def test_groq_without_api_key_fails_pointing_to_the_variable():
    with pytest.raises(ValueError, match="GROQ_API_KEY"):
        load_settings(env={"LLM_PROVIDER": "groq"})
```

**2. The doctor takes injectable *probes*.** The logic (what to check, what to skip, what to suggest) is separate from how each thing is actually checked. Tests use fake probes; `make doctor` uses the real ones. For example, if Ollama is down, there's no point also saying "model missing": the doctor skips those checks and gives you one useful hint.

## Check that it works

```bash
cp .env.example .env
ollama pull bge-m3 && ollama pull qwen2.5:3b
make install
make check-00
```

You should see:

```
✓ uv installed
✓ Docker running
✓ Postgres reachable
✓ Ollama reachable
✓ model bge-m3 pulled
✓ model qwen2.5:3b pulled
...
✓ step 00 OK
```

### Problems we hit (and you might too)

- **`Bind for 0.0.0.0:5432 failed: port is already allocated`.** Another Postgres is already using that port. Set `POSTGRES_PORT=5433` in `.env`, and change the port in `DATABASE_URL` too.
- **`invalid go version` when installing the hooks.** The standard gitleaks hook compiles with your system's Go, which fails if that Go is old. That's why we use `gitleaks-docker`: it only needs Docker, which you already have.

### No GPU

> TODO (step 3): real tokens-per-second numbers on a machine without a GPU, and why `LLM_PROVIDER=groq` makes sense there.

## Play with it

1. Stop Ollama, run `make doctor`, and see how the report changes. Also try `OLLAMA_HOST=http://localhost:1 make doctor`.
2. Set `LLM_PROVIDER=groq` in `.env` without a `GROQ_API_KEY`. Where does it fail, and what does it tell you?
3. Add a new probe to `doctor.py` (for example, one that checks `.env` exists). Write the test first.

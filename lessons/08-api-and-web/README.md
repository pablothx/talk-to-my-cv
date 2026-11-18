# Step 8: API and web page

🇪🇸 [Leer en español](README.es.md)

## What you'll learn

- How to expose the RAG as an **HTTP API** with FastAPI, and test it without real models.
- Why an LLM's answer is **untrusted input** for your page, and how to show it safely.
- How to run the API in a **container** that uses the Ollama on your machine, and the Linux detail that breaks it.

## The concept

### Inject the function, not the models

The API knows nothing about embeddings, stores or LLMs. It gets a single function:

```python
create_app(ask)  # ask: question → Answer
```

In production, `ask` is the pipeline or step 7's graph, built from `.env` (`ENGINE` still picks). In the tests, it's a three-line fake. So the API tests run in milliseconds and in CI, without Ollama.

### The LLM's answer is untrusted input

In step 3 we saw prompt injection: someone writes instructions for the model in the question. Now there's a new risk. If the page rendered the answer as HTML, convincing the model to write `<script>...</script>` would be enough to run code in the browser of whoever reads the page. That's **XSS** (*cross-site scripting*).

On top of that, the page shows the question again, so you don't even need to fool the model: writing the `<script>` in the question is enough.

Two defenses, and each one is enough on its own:

1. **Everything dynamic goes through `html.escape`**: the question, the answer and the citations. `<script>` is shown as text: `&lt;script&gt;`.
2. **The page has no JavaScript**, and tells the browser so with a `Content-Security-Policy: script-src 'none'` header. Even if escaping failed, the browser wouldn't run the script.

Without JavaScript, the form does a plain POST and the server returns the page with the answer. It's less pretty than a chat that types word by word, but there's nothing to inject.

### The container and your machine's Ollama

Until now, all the Python ran on your machine ([ADR-0001](../../docs/adr/0001-python-on-host-infra-in-compose.md)). The API is the app's first container. It talks to the stores by service name (`postgres`, `opensearch`) and to Ollama, which runs natively, through `host.docker.internal`.

On macOS and Windows (Docker Desktop) that just works. **On Linux, it doesn't:** `host.docker.internal` points to the `docker0` IP (172.17.0.1), and Ollama only listens on `127.0.0.1`. The connection is refused.

| Option | Problem |
|---|---|
| `OLLAMA_HOST=0.0.0.0` in the Ollama service (what its FAQ says) | Needs sudo, and Ollama, which has no authentication, is left open to your local network. |
| `network_mode: host` for the API | Changes every address, and behaves differently on Docker Desktop. |
| **A socat bridge** | A tiny container listens on `172.17.0.1:11434` and forwards to `127.0.0.1:11434`. No sudo, and only containers can reach it. |

We chose the bridge ([ADR-0012](../../docs/adr/0012-api-container-reaches-native-ollama-through-a-bridge.md)). `make api-up` adds it on Linux only.

## The code

| File | What it does |
|------|--------------|
| `src/talk_to_my_cv/api.py` | `create_app(ask)`: `POST /api/ask` (JSON), `GET /` and `POST /` (the page), `GET /health`. If it can't reach Ollama, it returns a 503 that says what to check. |
| `src/talk_to_my_cv/engines.py` | `build_ask(settings)`: builds `ask` with the models, store and engine from `.env`. |
| `Dockerfile`, `.dockerignore` | The API image. `.dockerignore` is an allowlist: `.env` and `kb/` (your real data) never get into the image. |
| `compose.yaml` | The `api` (profile `api`) and `ollama-bridge` (profile `bridge`) services. |

The API validates the question before calling any model: empty or longer than 500 characters returns 422. A refusal is a normal answer (200, `"refused": true`), not an error.

```bash
curl -s localhost:8000/api/ask -H 'content-type: application/json' \
  -d '{"question": "How much did Project Lumen speed up reconciliation?"}'
```

```json
{"answer": "Project Lumen sped up reconciliation from 9 hours to 14 minutes.",
 "refused": false,
 "citations": ["experience/northwind-payments.md § Senior Backend Engineer > Project Lumen"]}
```

## Check that it works

```bash
make check-08        # steps 0 to 8; starts the container
make serve           # or without Docker: the API on your machine, http://localhost:8000
make api-up          # the API in a container, http://localhost:8000
make api-down
```

Open http://localhost:8000 and ask. Then try `<script>alert(1)</script>` as a question: it must show up as text.

### What was hard

**The container started healthy and answered 500.** `/health` said `ok`, but every question failed with `Failed to connect to Ollama`: the Linux problem above. `/health` only says the process is alive, not that its dependencies work. Now that error is a 503 with a hint (`OLLAMA_HOST`), in the API and in the page.

## Play with it

1. **Break one defense at a time.** In `render_page()` (`api.py`), remove the question's `escape()` and ask `</textarea><h1>hello</h1>`: the heading shows up on the page. Now ask `</textarea><script>alert(1)</script>`: does it run? It shouldn't, because the CSP stops it. Remove the CSP header too and try again. When you're done, put both defenses back.
2. **Use the API from another program.** Write a script that reads questions from a file, calls `/api/ask` and saves the answers. It's the starting point for a Slack bot or a widget on your personal site.
3. **Switch the engine.** Set `ENGINE=graph` in `.env`, run `make api-up` again and ask "Has she worked with JavaScript?". Compare the answer and the time with `ENGINE=pipeline`.

## Known limitations

- **No streaming:** the page waits for the whole answer (10 to 30 seconds on a CPU), with no progress indicator, because it has no JavaScript.
- **No authentication or rate limiting.** Fine on your machine; publishing it like this lets anyone use your CPU (or your Groq account). For AWS, see [docs/production-on-aws.md](../../docs/production-on-aws.md).
- **One answer at a time:** FastAPI takes several questions at once, but Ollama on a CPU generates one answer at a time, so the rest wait.

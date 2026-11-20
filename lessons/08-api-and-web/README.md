# Step 8: API and web page

🇪🇸 [Leer en español](README.es.md)

Until now the chat lived in the terminal. In this step we turn it into an **HTTP API** and a **web page**, and put it in a container. With that, any other program (a Slack bot, your personal site) can use it.

## What you'll learn

- How to expose the RAG as an **API** with FastAPI, and test it without real models.
- Why an LLM's answer is **untrusted input** for your page, and how to show it safely.
- How to run the API in a **container** that uses your machine's Ollama, and the Linux detail that breaks it.

---

## Piece 1 of 7: the API in one line

```bash
make serve
```

It starts the API on http://localhost:8000. From another terminal:

```bash
curl -s localhost:8000/api/ask -H 'content-type: application/json' \
  -d '{"question": "How much did Project Lumen speed up reconciliation?"}'
```

```json
{"answer": "Project Lumen sped up reconciliation from 9 hours to 14 minutes.",
 "refused": false,
 "citations": ["experience/northwind-payments.md § Senior Backend Engineer > Project Lumen"]}
```

And if you open http://localhost:8000 in the browser, there's a page with a form.

## Piece 2 of 7: the endpoints

| Route | What it does |
|---|---|
| `POST /api/ask` | JSON in, JSON out. For other programs. |
| `GET /` | The page with the form. |
| `POST /` | The page with the answer. |
| `GET /health` | Says `ok` if the process is alive. |

The API validates the question **before** calling any model: empty or over 500 characters returns **422** (validation error). A refusal is a normal answer (**200**, `"refused": true`), not an error.

## Piece 3 of 7: inject the function, not the models

The API knows nothing about embeddings, stores or LLMs. It gets **a single function**:

```python
create_app(ask)  # ask: question → Answer
```

- In production, `ask` is the pipeline or the graph, built from `.env` (`ENGINE` still picks).
- In the tests, it's a three-line fake.

So the API tests run in milliseconds and on GitHub, without Ollama. It's the same idea as step 0: **inject what comes from outside**.

## Piece 4 of 7: a new risk, XSS

In step 3 we saw prompt injection: someone writes instructions for the model in the question. Now there's a new risk.

If the page rendered the answer as HTML, convincing the model to write `<script>...</script>` would be enough to **run code in the browser of whoever reads the page**. That's **XSS** (*cross-site scripting*).

And it's worse: the page shows the question again, so you don't even need to fool the model. Writing the `<script>` in the question is enough.

> **An LLM's answer is untrusted input**, just like what a user types.

## Piece 5 of 7: two defenses

Each one is enough on its own, and we have both:

1. **Everything dynamic goes through `html.escape`:** the question, the answer and the citations. `<script>` is shown as text: `&lt;script&gt;`.
2. **The page has no JavaScript**, and tells the browser so with a `Content-Security-Policy: script-src 'none'` header. Even if escaping failed, the browser wouldn't run any script.

Without JavaScript, the form does a plain POST and the server returns the page with the answer. It's less pretty than a chat that types word by word, but there's nothing to inject.

## Piece 6 of 7: the API in a container

Until now all the Python ran on your machine. The API is the app's first container:

```bash
make api-up      # builds the image and starts it on http://localhost:8000
make api-down
```

- The image (`Dockerfile`) uses Python 3.12 *slim*, installs the exact dependencies from `uv.lock` and runs as an unprivileged user.
- `.dockerignore` is an **allowlist**: only the code, the config and the dependencies get in. **`.env` and `kb/` (your real data) never get into the image.**
- Inside Docker, the API talks to Postgres and OpenSearch by service name (`postgres`, `opensearch`), and to Ollama, which runs on your machine, through `host.docker.internal`.

## Piece 7 of 7: the Linux problem

On macOS and Windows (Docker Desktop), `host.docker.internal` just works. **On Linux, it doesn't:** it points to the Docker network's IP (172.17.0.1), and Ollama only listens on `127.0.0.1`. The connection is refused.

| Option | Problem |
|---|---|
| Make Ollama listen on every IP (`OLLAMA_HOST=0.0.0.0`) | Needs sudo, and Ollama, which has no password, is left open to your local network. |
| `network_mode: host` for the API | Changes every address, and behaves differently on Docker Desktop. |
| **A socat bridge** | A tiny container listens on `172.17.0.1:11434` and forwards to `127.0.0.1:11434`. No sudo, and only containers can reach it. |

We chose the bridge ([ADR-0012](../../docs/adr/0012-api-container-reaches-native-ollama-through-a-bridge.md)). `make api-up` adds it on Linux only.

| File | What it does |
|------|--------------|
| `src/talk_to_my_cv/api.py` | `create_app(ask)`: the endpoints, the page and error handling. |
| `src/talk_to_my_cv/engines.py` | `build_ask(settings)`: builds `ask` with the models, store and engine from `.env`. |
| `Dockerfile`, `.dockerignore` | The API image. |
| `compose.yaml` | The `api` (profile `api`) and `ollama-bridge` (profile `bridge`) services. |

---

## Check that it works

```bash
make check-08        # steps 0 to 8; starts the container
make serve           # or without Docker: the API on your machine
make api-up          # the API in a container
```

Open http://localhost:8000 and ask. Then try `<script>alert(1)</script>` as a question: it must show up as text.

### What was hard

**The container started healthy and answered 500.** `/health` said `ok`, but every question failed with `Failed to connect to Ollama`: the Linux problem above. `/health` only says the process is alive, not that its dependencies work. Now that error is a **503** with a hint (`OLLAMA_HOST`), in the API and in the page.

## Play with it

1. **Break one defense at a time.** In `render_page()` (`api.py`), remove the question's `escape()` and ask `</textarea><h1>hello</h1>`: the heading shows up on the page. Now ask `</textarea><script>alert(1)</script>`: does it run? It shouldn't, because the CSP stops it. Remove the CSP header too and try again. When you're done, put both defenses back.
2. **Use the API from another program.** Write a script that reads questions from a file, calls `/api/ask` and saves the answers. It's the starting point for a Slack bot or a widget on your site.
3. **Switch the engine.** Set `ENGINE=graph` in `.env`, run `make api-up` again and ask "Has she worked with JavaScript?". Compare the answer and the time with `ENGINE=pipeline`.

## Known limitations

- **No streaming:** the page waits for the whole answer (10 to 30 seconds on a CPU), with no progress indicator, because it has no JavaScript.
- **No authentication or rate limiting.** Fine on your machine; publishing it like this lets anyone use your CPU (or your Groq account). To publish it, see the [production on AWS guide](../../docs/production-on-aws.md).
- **One answer at a time:** FastAPI takes several questions at once, but Ollama on a CPU generates one at a time, so the rest wait.

---

## ✋ Review

**1. Why does `create_app` take a function and not the models?**

<details><summary>Show answer</summary>

So the API doesn't depend on Ollama or the database: in tests you pass a fake and they run in milliseconds, on GitHub. In production you pass the pipeline or the graph.
</details>

**2. Why is the LLM's answer treated as untrusted input?**

<details><summary>Show answer</summary>

Because someone can convince the model to write HTML or `<script>`. If the page showed it as is, it would run code in the browser of whoever reads it (XSS).
</details>

**3. 🧪 Try it:** with `make serve`, ask `<script>alert(1)</script>` on the page. What do you expect to see?

<details><summary>Show answer</summary>

The text `<script>alert(1)</script>` as is, with no alert. Escaping turns it into text, and even if it failed, the CSP `script-src 'none'` would block running it.
</details>

**4. `/health` says `ok` but every question fails. How can that be?**

<details><summary>Show answer</summary>

`/health` only says the API process is alive, not that Ollama or the database answer. On Linux, the container couldn't reach Ollama. Now that case returns a 503 with a hint.
</details>

**5. Why is `.dockerignore` an allowlist and not a denylist?**

<details><summary>Show answer</summary>

Because if someone adds a sensitive file tomorrow (another `.env`, a CV), with a denylist it would get into the image without anyone noticing. With an allowlist, only what was named on purpose gets in.
</details>

---

[← Step 7](../07-langgraph/README.md) · [Index](../../README.md) · [Bonus: production on AWS →](../../docs/production-on-aws.md)

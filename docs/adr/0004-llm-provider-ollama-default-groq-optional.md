# LLM provider: Ollama by default, Groq optional; embeddings always local

`ChatModel` has two implementations, chosen with `LLM_PROVIDER`: `ollama` (default `qwen2.5:3b`) and `groq` (needs `GROQ_API_KEY`). Embeddings always use Ollama `bge-m3`, whatever the provider.

- The repo default (code and `.env.example`) stays `ollama`, because the central requirement is to run with no keys, accounts or cost.
- The author's own `.env` uses `groq`: the author's machine is CPU-only, and local generation there runs at about 5 tok/s.
- The local default is `qwen2.5:3b`, not `7b`, for the same reason. Both models are configurable.
- The tutorial has a "No GPU" section with the real measured numbers.

## Consequences

- With `groq`, the retrieved CV chunks leave the machine. The docs must say so wherever `kb/` (real data) is used with Groq.
- Changing the embedding model invalidates the index (see ADR-0005). Changing the LLM provider does not.

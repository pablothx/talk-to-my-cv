# LLM provider: Ollama by default, Groq optional; embeddings always local

`ChatModel` has two implementations, chosen with `LLM_PROVIDER`: `ollama` (default `qwen2.5:3b`) and `groq` (needs `GROQ_API_KEY`). Embeddings always use Ollama `bge-m3`, whatever the provider.

- The repo default (code and `.env.example`) stays `ollama`, because the central requirement is to run with no keys, accounts or cost.
- Groq exists for CPU-only machines, where local generation runs at about 4 tok/s. The author's machine is one of them, and the author still runs the project 100% locally with Ollama.
- The local default is `qwen2.5:3b`, not `7b`, for the same reason. Both models are configurable.
- The tutorial has a "No GPU" section with the real measured numbers.

## Consequences

- With `groq`, the retrieved CV chunks leave the machine. The docs must say so wherever `kb/` (real data) is used with Groq.
- Changing the embedding model invalidates the index (see ADR-0005). Changing the LLM provider does not.

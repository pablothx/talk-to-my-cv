# Unit tests use fakes; e2e tests assert behaviour, not wording

- **Unit tests** (`make test`) use a fake `Embedder` and a fake `ChatModel`, and are the only tests that run in CI (GitHub Actions: ruff + unit tests, with no Ollama and no Groq).
- **End-to-end tests** are marked `@pytest.mark.e2e` and are excluded by default. They run with `make test-e2e` and inside `check-03` and `check-04`, against `kb.example/` and the configured `LLM_PROVIDER`, with `temperature=0` and a fixed seed.
- **What e2e tests assert:** the cited file and section, refusal or not, and the presence of a key fact. They never compare exact text, because LLM output is not reproducible across providers and models.

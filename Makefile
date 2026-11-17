.DEFAULT_GOAL := help
UV := uv run

.PHONY: help install up down doctor lint test test-e2e embed similarity ingest check-00 check-01 check-02

help: ## Show available targets
	@grep -E '^[a-zA-Z0-9_-]+:.*## ' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "  %-12s %s\n", $$1, $$2}'

install: ## Install dependencies and git hooks
	uv sync
	$(UV) pre-commit install

up: ## Start infrastructure (pgvector) and wait until healthy
	docker compose up -d --wait

down: ## Stop infrastructure
	docker compose down

doctor: ## Check that the local stack is ready
	@$(UV) python -m talk_to_my_cv.doctor

lint: ## Ruff lint + format check
	$(UV) ruff check .
	$(UV) ruff format --check .

test: lint ## Lint + unit tests (what CI runs)
	$(UV) pytest

test-e2e: ## End-to-end tests (need Ollama, pgvector and the LLM provider)
	$(UV) pytest -m e2e

embed: ## Embed TEXT="..." and print dimension and first values
	@$(UV) python -m talk_to_my_cv.cli embed "$(TEXT)"

similarity: ## Cosine similarity between A="..." and B="..."
	@$(UV) python -m talk_to_my_cv.cli similarity "$(A)" "$(B)"

ingest: ## Ingest KB_DIR into pgvector (REBUILD=1 drops the index first)
	@$(UV) python -m talk_to_my_cv.cli ingest $(if $(filter 1,$(REBUILD)),--rebuild)

check-00: test up doctor ## Step 0: skeleton, config and doctor
	$(UV) pre-commit run --all-files
	@echo "✓ step 00 OK"

check-01: check-00 ## Step 1: embeddings
	$(UV) pytest -m e2e tests/test_embeddings_e2e.py
	@echo "✓ step 01 OK"

check-02: check-01 ## Step 2: chunking and ingestion
	$(UV) pytest -m e2e tests/test_store_contract.py tests/test_ingest_e2e.py
	@$(MAKE) -s ingest
	@echo "✓ step 02 OK"

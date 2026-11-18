.DEFAULT_GOAL := help
UV := uv run

.PHONY: help install up down doctor lint test test-e2e embed similarity ingest chat ask check-00 check-01 check-02 check-03 check-04 eval eval-sweep eval-all check-05 check-06 check-07

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

DEBUG_FLAG = $(if $(filter 1,$(DEBUG)),--debug)

chat: ## Chat with the KB (DEBUG=1 shows retrieved chunks and scores)
	@$(UV) python -m talk_to_my_cv.cli chat $(DEBUG_FLAG)

ask: ## Ask one question Q="..." (DEBUG=1 shows retrieved chunks and scores)
	@$(UV) python -m talk_to_my_cv.cli chat $(DEBUG_FLAG) "$(Q)"

STORE ?= pgvector
MODE ?= vector

eval: ## Run eval/questions.yaml (STORE=pgvector MODE=vector THRESHOLD=... ENGINE=pipeline|graph)
	@$(UV) python -m talk_to_my_cv.cli eval --store $(STORE) --mode $(MODE) $(if $(THRESHOLD),--threshold $(THRESHOLD)) $(if $(ENGINE),--engine $(ENGINE))

eval-sweep: ## Sweep relevance thresholds (no LLM) and plot eval/results/threshold-sweep_*.png
	@$(UV) python -m talk_to_my_cv.cli eval-sweep --store $(STORE)

eval-all: ## Eval every store × mode combination (unsupported ones are reported as skipped)
	@for combo in pgvector:vector pgvector:hybrid opensearch:vector opensearch:keyword opensearch:hybrid; do \
		$(MAKE) -s eval STORE=$${combo%%:*} MODE=$${combo##*:} | grep -E "^- |^\| (refusal|answer)_accuracy|^\| (hit@5|mrr)|Skipped"; \
	done

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

check-03: check-02 ## Step 3: first RAG (uses the configured LLM_PROVIDER)
	$(UV) pytest -m e2e tests/test_rag_e2e.py
	@echo "✓ step 03 OK"

check-04: check-03 ## Step 4: citations and relevance gate
	$(UV) pytest -m e2e tests/test_citations_e2e.py
	@echo "✓ step 04 OK"

check-05: check-04 ## Step 5: evaluation
	$(UV) pytest -m e2e tests/test_eval_e2e.py
	@echo "✓ step 05 OK"

check-06: check-05 ## Step 6: OpenSearch and hybrid search
	$(UV) pytest -m e2e tests/test_hybrid_e2e.py
	@echo "✓ step 06 OK"

check-07: check-06 ## Step 7: LangGraph flow with LLM verification
	$(UV) pytest -m e2e tests/test_graph_e2e.py
	@echo "✓ step 07 OK"

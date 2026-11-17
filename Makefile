.DEFAULT_GOAL := help
UV := uv run

.PHONY: help install up down doctor lint test test-e2e check-00

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

check-00: test up doctor ## Step 0: skeleton, config and doctor
	$(UV) pre-commit run --all-files
	@echo "✓ step 00 OK"

# The step 8 API. Everything else still runs on the host (ADR-0001, ADR-0012).
FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:0.12.23 /uv /usr/local/bin/uv

WORKDIR /app
ENV UV_LINK_MODE=copy UV_COMPILE_BYTECODE=1 PATH="/app/.venv/bin:$PATH"

# Dependencies first, so editing the code doesn't reinstall them.
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --locked --no-dev --no-install-project

COPY src ./src
COPY config ./config
RUN uv sync --locked --no-dev

RUN useradd --create-home app
USER app

EXPOSE 8000
HEALTHCHECK --interval=10s --timeout=3s --retries=10 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"
CMD ["uvicorn", "--factory", "talk_to_my_cv.api:app_from_settings", "--host", "0.0.0.0", "--port", "8000"]

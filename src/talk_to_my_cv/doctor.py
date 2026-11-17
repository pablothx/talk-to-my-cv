"""`make doctor`: checks that the local stack is ready, with a fix hint for each failure."""

import json
import shutil
import subprocess
import sys
import urllib.request
from dataclasses import dataclass
from typing import Protocol

import psycopg

from talk_to_my_cv.config import Settings, load_settings


class Probes(Protocol):
    def uv_installed(self) -> bool: ...
    def docker_running(self) -> bool: ...
    def postgres_reachable(self, url: str) -> bool: ...
    def ollama_reachable(self, host: str) -> bool: ...
    def ollama_models(self, host: str) -> set[str]: ...
    def groq_reachable(self, api_key: str) -> bool: ...


@dataclass(frozen=True)
class Check:
    name: str
    ok: bool
    hint: str = ""
    skipped_because: str = ""


@dataclass(frozen=True)
class DoctorReport:
    checks: list[Check]

    @property
    def exit_code(self) -> int:
        return 0 if all(check.ok for check in self.checks) else 1

    def render(self) -> str:
        lines = []
        for c in self.checks:
            if c.skipped_because:
                lines.append(f"- {c.name} (skipped: {c.skipped_because})")
                continue
            lines.append(f"{'✓' if c.ok else '✗'} {c.name}")
            if not c.ok and c.hint:
                lines.append(f"    → {c.hint}")
        return "\n".join(lines)


def _has_model(available: set[str], wanted: str) -> bool:
    """Ollama lists untagged models as `name:latest`."""
    return wanted in available or f"{wanted}:latest" in available


def run_doctor(probes: Probes, settings: Settings) -> DoctorReport:
    ollama_up = probes.ollama_reachable(settings.ollama_host)
    checks = [
        Check("uv installed", probes.uv_installed(), "install uv: https://docs.astral.sh/uv/"),
        Check(
            "Docker running", probes.docker_running(), "start Docker, then `docker compose up -d`"
        ),
        Check(
            "Postgres reachable",
            probes.postgres_reachable(settings.database_url),
            "`docker compose up -d` and check DATABASE_URL",
        ),
        Check(
            "Ollama reachable",
            ollama_up,
            f"run `ollama serve` (or `docker compose --profile ollama up -d`); "
            f"OLLAMA_HOST={settings.ollama_host}",
        ),
    ]
    if settings.llm_provider == "groq":
        checks.append(
            Check(
                "Groq API reachable",
                probes.groq_reachable(settings.groq_api_key or ""),
                "check GROQ_API_KEY in .env (https://console.groq.com/keys)",
            )
        )
        models: tuple[str, ...] = (settings.embed_model,)
    else:
        models = (settings.embed_model, settings.llm_model)
    if not ollama_up:
        checks += [
            Check(f"model {m} pulled", ok=True, skipped_because="Ollama unreachable")
            for m in models
        ]
        return DoctorReport(checks)
    available = probes.ollama_models(settings.ollama_host)
    for model in models:
        checks.append(
            Check(f"model {model} pulled", _has_model(available, model), f"ollama pull {model}")
        )
    return DoctorReport(checks)


class SystemProbes:
    """Real probes against the local machine. Thin adapters: covered by `make doctor`."""

    def uv_installed(self) -> bool:
        return shutil.which("uv") is not None

    def docker_running(self) -> bool:
        try:
            return (
                subprocess.run(["docker", "info"], capture_output=True, timeout=10).returncode == 0
            )
        except (OSError, subprocess.TimeoutExpired):
            return False

    def postgres_reachable(self, url: str) -> bool:
        try:
            with psycopg.connect(url, connect_timeout=3):
                return True
        except psycopg.Error:
            return False

    def ollama_reachable(self, host: str) -> bool:
        try:
            self.ollama_models(host)
            return True
        except OSError:
            return False

    def ollama_models(self, host: str) -> set[str]:
        with urllib.request.urlopen(f"{host}/api/tags", timeout=3) as response:
            return {m["name"] for m in json.load(response)["models"]}

    def groq_reachable(self, api_key: str) -> bool:
        request = urllib.request.Request(
            "https://api.groq.com/openai/v1/models",
            headers={"Authorization": f"Bearer {api_key}", "User-Agent": "talk-to-my-cv"},
        )
        try:
            with urllib.request.urlopen(request, timeout=5) as response:
                return response.status == 200
        except OSError:
            return False


def main() -> int:
    try:
        settings = load_settings()
    except ValueError as error:
        print(f"✗ configuration invalid\n{error}")
        return 1
    report = run_doctor(SystemProbes(), settings)
    print(report.render())
    return report.exit_code


if __name__ == "__main__":
    sys.exit(main())

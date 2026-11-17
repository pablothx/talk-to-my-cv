from dataclasses import dataclass, field

from talk_to_my_cv.config import load_settings
from talk_to_my_cv.doctor import run_doctor


@dataclass
class FakeProbes:
    uv: bool = True
    docker: bool = True
    postgres: bool = True
    ollama: bool = True
    models: set[str] = field(default_factory=lambda: {"qwen2.5:3b", "bge-m3:latest"})
    groq: bool = True

    def uv_installed(self) -> bool:
        return self.uv

    def docker_running(self) -> bool:
        return self.docker

    def postgres_reachable(self, url: str) -> bool:
        return self.postgres

    def ollama_reachable(self, host: str) -> bool:
        return self.ollama

    def ollama_models(self, host: str) -> set[str]:
        return self.models

    def groq_reachable(self, api_key: str) -> bool:
        return self.groq


def test_healthy_stack_passes_with_exit_code_zero():
    report = run_doctor(FakeProbes(), load_settings(env={}))

    assert report.exit_code == 0
    assert all(check.ok for check in report.checks)
    assert "✓" in report.render()


def test_missing_model_fails_with_a_pull_hint():
    probes = FakeProbes(models={"qwen2.5:3b"})

    report = run_doctor(probes, load_settings(env={}))

    assert report.exit_code != 0
    assert "✗" in report.render()
    assert "ollama pull bge-m3" in report.render()


class OllamaDown(FakeProbes):
    def ollama_models(self, host: str) -> set[str]:
        raise ConnectionError("connection refused")


def test_ollama_down_reports_one_failure_and_skips_model_checks():
    report = run_doctor(OllamaDown(ollama=False), load_settings(env={}))

    failed = [check.name for check in report.checks if not check.ok]
    assert failed == ["Ollama reachable"]
    assert report.exit_code != 0
    assert "skipped" in report.render()
    assert "ollama serve" in report.render()


GROQ_ENV = {"LLM_PROVIDER": "groq", "GROQ_API_KEY": "gsk_test", "LLM_MODEL": "llama-3.3-70b"}


def test_groq_provider_checks_the_api_instead_of_the_local_llm_model():
    probes = FakeProbes(models={"bge-m3:latest"})

    report = run_doctor(probes, load_settings(env=GROQ_ENV))

    names = [check.name for check in report.checks]
    assert "Groq API reachable" in names
    assert not any("llama-3.3-70b" in name for name in names)
    assert report.exit_code == 0


def test_rejected_groq_key_fails_with_a_hint():
    report = run_doctor(FakeProbes(groq=False), load_settings(env=GROQ_ENV))

    assert report.exit_code != 0
    assert "GROQ_API_KEY" in report.render()


def test_ollama_provider_does_not_call_groq():
    names = [c.name for c in run_doctor(FakeProbes(), load_settings(env={})).checks]

    assert "Groq API reachable" not in names

import pytest

from talk_to_my_cv.config import load_settings


def test_defaults_need_no_api_keys_or_accounts():
    settings = load_settings(env={})

    assert settings.llm_provider == "ollama"
    assert settings.llm_model == "qwen2.5:3b"
    assert settings.embed_model == "bge-m3"
    assert settings.ollama_host == "http://localhost:11434"
    assert settings.kb_dir.as_posix() == "kb.example"
    assert settings.groq_api_key is None
    assert settings.database_url == "postgresql://postgres:postgres@localhost:5432/talk_to_my_cv"


def test_environment_overrides_defaults():
    settings = load_settings(env={"LLM_MODEL": "qwen2.5:7b", "KB_DIR": "kb"})

    assert settings.llm_model == "qwen2.5:7b"
    assert settings.kb_dir.as_posix() == "kb"


def test_unknown_llm_provider_is_rejected_with_the_valid_options():
    with pytest.raises(ValueError, match="ollama.*groq"):
        load_settings(env={"LLM_PROVIDER": "openai"})


def test_groq_without_api_key_fails_pointing_to_the_variable():
    with pytest.raises(ValueError, match="GROQ_API_KEY"):
        load_settings(env={"LLM_PROVIDER": "groq"})


def test_groq_with_api_key_is_accepted():
    settings = load_settings(env={"LLM_PROVIDER": "groq", "GROQ_API_KEY": "gsk_test"})

    assert settings.llm_provider == "groq"


def test_each_provider_has_its_own_model_so_switching_is_one_line():
    ollama = load_settings(env={})
    groq = load_settings(env={"LLM_PROVIDER": "groq", "GROQ_API_KEY": "gsk_test"})

    assert ollama.chat_model == "qwen2.5:3b"
    assert groq.chat_model == "llama-3.3-70b-versatile"


def test_store_and_search_mode_default_to_the_step_2_setup():
    settings = load_settings(env={})

    assert settings.vector_store == "pgvector"
    assert settings.search_mode == "vector"


def test_store_and_search_mode_are_validated():
    with pytest.raises(ValueError, match="pgvector.*opensearch"):
        load_settings(env={"VECTOR_STORE": "chroma"})
    with pytest.raises(ValueError, match="vector.*keyword.*hybrid"):
        load_settings(env={"SEARCH_MODE": "semantic"})


def test_a_mode_the_store_cannot_do_fails_at_startup():
    with pytest.raises(ValueError, match="pgvector.*hybrid.*opensearch"):
        load_settings(env={"VECTOR_STORE": "pgvector", "SEARCH_MODE": "hybrid"})

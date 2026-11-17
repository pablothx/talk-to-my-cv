from types import SimpleNamespace

from talk_to_my_cv.chat_models import GroqChatModel, OllamaChatModel, build_chat_model
from talk_to_my_cv.config import load_settings

MESSAGES = [{"role": "system", "content": "rules"}, {"role": "user", "content": "q"}]


class FakeOllama:
    def __init__(self):
        self.kwargs = {}

    def chat(self, **kwargs):
        self.kwargs = kwargs
        return {"message": {"content": "from ollama"}}


class FakeGroqCompletions:
    def __init__(self):
        self.kwargs = {}

    def create(self, **kwargs):
        self.kwargs = kwargs
        message = SimpleNamespace(content="from groq")
        return SimpleNamespace(choices=[SimpleNamespace(message=message)])


def test_ollama_gets_the_model_and_deterministic_options():
    client = FakeOllama()

    reply = OllamaChatModel(client, model="qwen2.5:3b").complete(MESSAGES)

    assert reply == "from ollama"
    assert client.kwargs["model"] == "qwen2.5:3b"
    assert client.kwargs["messages"] == MESSAGES
    assert client.kwargs["options"]["temperature"] == 0
    assert "seed" in client.kwargs["options"]


def test_groq_gets_the_model_and_deterministic_options():
    completions = FakeGroqCompletions()
    client = SimpleNamespace(chat=SimpleNamespace(completions=completions))

    reply = GroqChatModel(client, model="llama-3.3-70b-versatile").complete(MESSAGES)

    assert reply == "from groq"
    assert completions.kwargs["model"] == "llama-3.3-70b-versatile"
    assert completions.kwargs["messages"] == MESSAGES
    assert completions.kwargs["temperature"] == 0
    assert "seed" in completions.kwargs


def test_llm_provider_selects_the_implementation_and_its_model():
    ollama = build_chat_model(load_settings(env={}))
    groq = build_chat_model(load_settings(env={"LLM_PROVIDER": "groq", "GROQ_API_KEY": "gsk_x"}))

    assert isinstance(ollama, OllamaChatModel) and ollama.model == "qwen2.5:3b"
    assert isinstance(groq, GroqChatModel) and groq.model == "llama-3.3-70b-versatile"

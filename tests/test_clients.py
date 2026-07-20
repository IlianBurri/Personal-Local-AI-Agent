import types
from core.providers import OpenAIClient, AnthropicClient, OllamaClient
import requests


def test_openai_streaming_basic():
    client = OpenAIClient(api_key="fake", model="gpt-test")

    class FakeCompletions:
        @staticmethod
        def create(model, messages, stream=True, **kwargs):
            yield types.SimpleNamespace(
                choices=[
                    types.SimpleNamespace(
                        delta=types.SimpleNamespace(content="Hello ")
                    )
                ]
            )
            yield types.SimpleNamespace(
                choices=[
                    types.SimpleNamespace(
                        delta=types.SimpleNamespace(content="world")
                    )
                ]
            )

    client.client = types.SimpleNamespace(
        chat=types.SimpleNamespace(
            completions=FakeCompletions
        )
    )
    out = "".join([t for t in client.stream_chat([{"role":"user","content":"hi"}])])
    assert out == "Hello world"


def test_anthropic_streaming_messages_stream():
    ac = AnthropicClient(api_key="fake", model="claude-test")

    class FakeStream:
        text_stream = ["Part1 ", "Part2"]

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    class FakeClient:
        class messages:
            @staticmethod
            def stream(messages, model, **kwargs):
                return FakeStream()

    ac.client = FakeClient()
    out = "".join([t for t in ac.stream_chat([{"role":"user","content":"hi"}])])
    assert out == "Part1 Part2"


def test_ollama_streaming_and_list(monkeypatch):
    oc = OllamaClient(base_url="http://localhost:11434", model="test")

    # mock list_models
    def fake_get(url, timeout=5):
        class R:
            def raise_for_status(self):
                pass

            def json(self):
                return ["model-a", "model-b"]

        return R()

    monkeypatch.setattr(requests, "get", fake_get)
    tags = oc.list_models()
    assert isinstance(tags, list)

    # mock streaming post — response format matches /api/chat
    def fake_post(url, json=None, stream=True, timeout=60, headers=None):
        class R:
            def raise_for_status(self):
                pass

            def iter_lines(self, decode_unicode=True):
                yield '{"message": {"role": "assistant", "content": "Hello "}}'
                yield '{"message": {"role": "assistant", "content": "world"}}'

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

        return R()

    monkeypatch.setattr(requests, "post", fake_post)
    out = "".join([t for t in oc.stream_chat([{"role":"user","content":"hi"}])])
    assert out == "Hello world"

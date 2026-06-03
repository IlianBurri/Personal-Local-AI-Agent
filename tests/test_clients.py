import json
import types
from core.clients import OpenAIClient, AnthropicClient, OllamaClient
import requests


def test_openai_streaming_basic():
    client = OpenAIClient(api_key="fake", model="gpt-test")

    class FakeChatCompletion:
        @staticmethod
        def create(model, messages, stream=True, **kwargs):
            # simulate streaming chunks with deltas
            yield {"choices": [{"delta": {"content": "Hello "}}]}
            yield {"choices": [{"delta": {"content": "world"}}]}

    client._openai = types.SimpleNamespace(ChatCompletion=FakeChatCompletion)
    out = "".join([t for t in client.stream_chat([{"role":"user","content":"hi"}])])
    assert out == "Hello world"


def test_anthropic_streaming_messages_stream():
    ac = AnthropicClient(api_key="fake", model="claude-test")

    class FakeClient:
        class messages:
            @staticmethod
            def stream(messages, model, **kwargs):
                yield {"content": "Part1 "}
                yield {"content": "Part2"}

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

    # mock streaming post
    def fake_post(url, json=None, stream=True, timeout=60, headers=None):
        class R:
            def raise_for_status(self):
                pass

            def iter_lines(self, decode_unicode=True):
                yield '{"text":"stream1"}'
                yield '{"text":"stream2"}'

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

        return R()

    monkeypatch.setattr(requests, "post", fake_post)
    out = "".join([t for t in oc.stream_chat([{"role":"user","content":"hi"}])])
    assert "stream1" in out
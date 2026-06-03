from abc import ABC, abstractmethod
from typing import Iterator, AsyncIterator, Dict, Any
import requests
import json
import os


class BaseLLMClient(ABC):
    """Abstract LLM client that yields streaming tokens."""

    @abstractmethod
    def stream_chat(self, messages, **kwargs) -> Iterator[str]:
        """Yield text chunks for streaming UI."""
        raise NotImplementedError()


class OpenAIClient(BaseLLMClient):
    def __init__(self, api_key: str, model: str = "gpt-4o"):
        import openai

        self._openai = openai
        self._openai.api_key = api_key
        self.model = model

    def stream_chat(self, messages, **kwargs):
        # messages: list of {role, content}
        resp = self._openai.ChatCompletion.create(
            model=self.model, messages=messages, stream=True, **kwargs
        )
        for chunk in resp:
            if "choices" in chunk:
                for c in chunk["choices"]:
                    delta = c.get("delta", {})
                    text = delta.get("content")
                    if text:
                        yield text


class AnthropicClient(BaseLLMClient):
    def __init__(self, api_key: str, model: str = "claude-2"):
        import anthropic

        self._anthropic = anthropic
        self.client = anthropic.Client(api_key)
        self.model = model

    def stream_chat(self, messages, **kwargs):
        # Anthropic expects a single string prompt composed of system/user/assistant turns.
        prompt = "\n".join([f"{m['role']}: {m['content']}" for m in messages])
        for chunk in self.client.stream_completion(prompt=prompt, model=self.model, **kwargs):
            # chunk is a dict with 'completion' segments
            text = chunk.get("completion")
            if text:
                yield text


class OllamaClient(BaseLLMClient):
    def __init__(self, base_url: str = "http://localhost:11434", model: str = None):
        self.base_url = base_url.rstrip("/")
        self.model = model

    def list_models(self):
        url = f"{self.base_url}/models"
        r = requests.get(url, timeout=5)
        r.raise_for_status()
        return r.json()

    def stream_chat(self, messages, **kwargs):
        model = self.model or "ollama"
        url = f"{self.base_url}/api/generate"
        payload = {
            "model": model,
            "prompt": "\n".join([f"{m['role']}: {m['content']}" for m in messages]),
            "stream": True,
        }
        with requests.post(url, json=payload, stream=True, timeout=60) as r:
            r.raise_for_status()
            for line in r.iter_lines(decode_unicode=True):
                if not line:
                    continue
                try:
                    data = json.loads(line)
                except Exception:
                    data = {"text": line}
                text = data.get("text") or data.get("output") or data.get("content")
                if text:
                    yield text

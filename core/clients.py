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
        # Use streaming ChatCompletion interface
        resp = self._openai.ChatCompletion.create(
            model=self.model, messages=messages, stream=True, **kwargs
        )
        for chunk in resp:
            # chunk is a dict-like with choices and deltas
            try:
                if "choices" in chunk:
                    for c in chunk["choices"]:
                        delta = c.get("delta", {})
                        text = delta.get("content")
                        if text:
                            yield text
                else:
                    # older clients may yield text directly
                    text = chunk.get("text") if isinstance(chunk, dict) else str(chunk)
                    if text:
                        yield text
            except Exception:
                # fallback
                try:
                    yield str(chunk)
                except Exception:
                    continue


class AnthropicClient(BaseLLMClient):
    def __init__(self, api_key: str, model: str = "claude-2"):
        import anthropic

        self._anthropic = anthropic
        self.client = anthropic.Client(api_key)
        self.model = model

    def stream_chat(self, messages, **kwargs):
        # Anthropic streaming via messages.stream if available
        try:
            # If the SDK supports messages.stream
            stream = self.client.messages.stream(messages=messages, model=self.model, **kwargs)
            for part in stream:
                # part may be dict with 'content' or 'text'
                text = None
                if isinstance(part, dict):
                    text = part.get("content") or part.get("text") or part.get("completion")
                else:
                    text = str(part)
                if text:
                    yield text
            return
        except Exception:
            # Fallback to older completion API
            prompt = "\n".join([f"{m['role']}: {m['content']}" for m in messages])
            try:
                for chunk in self.client.stream_completion(prompt=prompt, model=self.model, **kwargs):
                    text = chunk.get("completion")
                    if text:
                        yield text
            except Exception:
                # final fallback: call non-streaming completion
                resp = self.client.completions.create(prompt=prompt, model=self.model, **kwargs)
                out = resp.get("completion") or resp.get("text") or ""
                if out:
                    yield out


class OllamaClient(BaseLLMClient):
    def __init__(self, base_url: str = "http://localhost:11434", model: str = None):
        self.base_url = base_url.rstrip("/")
        self.model = model

    def list_models(self):
        # Ollama tags endpoint
        url = f"{self.base_url}/api/tags"
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
            # Ollama may send JSON lines
            for line in r.iter_lines(decode_unicode=True):
                if not line:
                    continue
                try:
                    data = json.loads(line)
                except Exception:
                    data = {"text": line}
                # Ollama streams may include 'output' or 'response' fields
                text = None
                if isinstance(data, dict):
                    text = data.get("text") or data.get("output") or data.get("response") or data.get("content")
                else:
                    text = str(data)
                if text:
                    yield text

from abc import ABC, abstractmethod
from typing import Iterator, AsyncIterator, Dict, Any, Optional, Callable
import requests
import json
import os
import time
import random
from requests.exceptions import RequestException


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
        # Use streaming ChatCompletion interface. Wrap in retry loop for transient errors.
        max_retries = kwargs.pop("_retries", 3)
        backoff_base = kwargs.pop("_backoff_base", 0.6)

        attempt = 0
        while True:
            attempt += 1
            try:
                resp = self._openai.ChatCompletion.create(
                    model=self.model, messages=messages, stream=True, **kwargs
                )
                for chunk in resp:
                    # chunk is a dict-like with choices and deltas
                    try:
                        if isinstance(chunk, dict) and "choices" in chunk:
                            for c in chunk["choices"]:
                                delta = c.get("delta", {})
                                text = delta.get("content") or delta.get("message")
                                if text:
                                    yield text
                        else:
                            # older clients may yield text directly or a dict with 'text'
                            if isinstance(chunk, dict):
                                text = chunk.get("text") or chunk.get("content")
                                if text:
                                    yield text
                            else:
                                yield str(chunk)
                    except Exception:
                        # best-effort fallback
                        try:
                            yield str(chunk)
                        except Exception:
                            continue
                # finished successfully
                break
            except Exception as e:
                # Only retry on likely transient errors
                if attempt >= max_retries:
                    raise
                sleep = backoff_base * (2 ** (attempt - 1)) * (0.8 + random.random() * 0.4)
                time.sleep(sleep)
                continue


class AnthropicClient(BaseLLMClient):
    def __init__(self, api_key: str, model: str = "claude-2"):
        import anthropic

        self._anthropic = anthropic
        self.client = anthropic.Client(api_key)
        self.model = model

    def stream_chat(self, messages, **kwargs):
        # Anthropic streaming via messages.stream if available. Use retries for transient issues.
        max_retries = kwargs.pop("_retries", 3)
        backoff_base = kwargs.pop("_backoff_base", 0.6)

        prompt = "\n".join([f"{m['role']}: {m['content']}" for m in messages])

        attempt = 0
        while True:
            attempt += 1
            try:
                # Try modern messages.stream API
                try:
                    stream = self.client.messages.stream(messages=messages, model=self.model, **kwargs)
                    for part in stream:
                        text = None
                        if isinstance(part, dict):
                            text = part.get("content") or part.get("text") or part.get("completion")
                        else:
                            text = str(part)
                        if text:
                            yield text
                    return
                except AttributeError:
                    # older SDKs may not have messages.stream
                    pass

                # Try stream_completion API
                try:
                    for chunk in self.client.stream_completion(prompt=prompt, model=self.model, **kwargs):
                        if isinstance(chunk, dict):
                            text = chunk.get("completion") or chunk.get("text")
                        else:
                            text = str(chunk)
                        if text:
                            yield text
                    return
                except AttributeError:
                    pass

                # Final fallback: non-streaming completion
                if hasattr(self.client, "completions"):
                    resp = self.client.completions.create(prompt=prompt, model=self.model, **kwargs)
                    out = None
                    if isinstance(resp, dict):
                        out = resp.get("completion") or resp.get("text") or ""
                    else:
                        out = str(resp)
                    if out:
                        yield out
                    return
                # If none of the above worked, raise
                raise RuntimeError("No supported Anthropic streaming API available")
            except Exception as e:
                if attempt >= max_retries:
                    raise
                sleep = backoff_base * (2 ** (attempt - 1)) * (0.8 + random.random() * 0.4)
                time.sleep(sleep)
                continue


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
        headers = {"User-Agent": "Arca-Agent/1.0"}
        with requests.post(url, json=payload, stream=True, timeout=60, headers=headers) as r:
            r.raise_for_status()
            # Ollama may stream JSON lines or SSE-style 'data: ...' lines
            for line in r.iter_lines(decode_unicode=True):
                if not line:
                    continue
                text = None
                raw = line.strip()
                # handle server-sent events lines like 'data: {...}'
                if raw.startswith("data:"):
                    raw = raw[len("data:"):].strip()
                try:
                    data = json.loads(raw)
                    if isinstance(data, dict):
                        text = data.get("text") or data.get("output") or data.get("response") or data.get("content")
                    else:
                        text = str(data)
                except Exception:
                    # not json, use raw
                    text = raw
                if text:
                    yield text

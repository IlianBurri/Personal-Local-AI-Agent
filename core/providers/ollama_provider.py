import json

import requests

from core.providers.base import BaseLLMClient


class OllamaClient(BaseLLMClient):
    """Ollama provider. Uses `/api/chat` for structured messages.

    Streaming response lines are JSON of the form:
        {"model": "...", "message": {"role": "assistant", "content": "..."}}
    """

    def __init__(self, base_url: str = "http://localhost:11434", model: str | None = None):
        self.base_url = base_url.rstrip("/")
        self.model = model

    def list_models(self):
        response = requests.get(f"{self.base_url}/api/tags", timeout=5)
        response.raise_for_status()
        return response.json()

    def stream_chat(self, messages, **kwargs):
        model = self.model or "llama3"
        url = f"{self.base_url}/api/chat"
        payload = {"model": model, "messages": messages, "stream": True}

        # Include optional generation params if provided
        for key in ("temperature", "max_tokens"):
            if key in kwargs:
                val = kwargs[key]
                if val is not None:
                    if key == "max_tokens":
                        payload["num_predict"] = int(val)
                    else:
                        payload[key] = val

        with requests.post(url, json=payload, stream=True, timeout=60) as response:
            response.raise_for_status()
            for line in response.iter_lines(decode_unicode=True):
                if not line:
                    continue
                try:
                    data = json.loads(line)
                except Exception:
                    continue
                chunk = (data.get("message") or {}).get("content") or ""
                if chunk:
                    yield chunk

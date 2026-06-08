import json
import requests

from core.providers.base import BaseLLMClient


class OllamaClient(BaseLLMClient):

    def __init__(
        self,
        base_url="http://localhost:11434",
        model=None
    ):
        self.base_url = base_url.rstrip("/")
        self.model = model

    def list_models(self):

        url = f"{self.base_url}/api/tags"

        response = requests.get(
            url,
            timeout=5
        )

        response.raise_for_status()

        return response.json()

    def stream_chat(
        self,
        messages,
        **kwargs
    ):

        model = self.model or "llama3"

        url = f"{self.base_url}/api/generate"

        payload = {
            "model": model,
            "prompt": "\n".join(
                f"{m['role']}: {m['content']}"
                for m in messages
            ),
            "stream": True,
        }

        with requests.post(
            url,
            json=payload,
            stream=True,
            timeout=60
        ) as response:

            response.raise_for_status()

            for line in response.iter_lines(
                decode_unicode=True
            ):

                if not line:
                    continue

                try:

                    data = json.loads(line)

                    text = (
                        data.get("response")
                        or data.get("text")
                        or ""
                    )

                except Exception:

                    text = line

                if text:
                    yield text
import random
import time

from core.providers.base import BaseLLMClient


class AnthropicClient(BaseLLMClient):
    """Anthropic provider via `messages.stream` (anthropic>=0.25)."""

    def __init__(self, api_key: str, model: str = "claude-3-5-sonnet-latest"):
        from anthropic import Anthropic

        self.client = Anthropic(api_key=api_key)
        self.model = model

    def stream_chat(self, messages, **kwargs):
        max_retries = kwargs.pop("_retries", 3)
        backoff_base = kwargs.pop("_backoff_base", 0.6)
        kwargs.setdefault("max_tokens", 1024)

        attempt = 0
        while True:
            attempt += 1
            try:
                with self.client.messages.stream(
                    messages=messages,
                    model=self.model,
                    **kwargs,
                ) as stream:
                    for text in stream.text_stream:
                        if text:
                            yield text
                return
            except Exception:
                if attempt >= max_retries:
                    raise
                time.sleep(_backoff(backoff_base, attempt))


def _backoff(base: float, attempt: int) -> float:
    return base * (2 ** (attempt - 1)) * (0.8 + random.random() * 0.4)

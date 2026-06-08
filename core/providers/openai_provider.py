import time
import random

from core.providers.base import BaseLLMClient


class OpenAIClient(BaseLLMClient):

    def __init__(
        self,
        api_key: str,
        model: str = "gpt-4o",
        client=None
    ):
        if client is None:
            from openai import OpenAI
            client = OpenAI(api_key=api_key)

        self.client = client
        self.model = model

    def stream_chat(
        self,
        messages,
        **kwargs
    ):

        max_retries = kwargs.pop(
            "_retries",
            3
        )

        backoff_base = kwargs.pop(
            "_backoff_base",
            0.6
        )

        attempt = 0

        while True:

            attempt += 1

            try:

                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    stream=True,
                    **kwargs
                )

                for chunk in response:
                    for choice in getattr(chunk, "choices", []):
                        delta = getattr(choice, "delta", None)
                        text = getattr(delta, "content", None)
                        if text:
                            yield text

                break

            except Exception:

                if attempt >= max_retries:
                    raise

                sleep = (
                    backoff_base
                    * (2 ** (attempt - 1))
                    * (
                        0.8
                        + random.random()
                        * 0.4
                    )
                )

                time.sleep(sleep)

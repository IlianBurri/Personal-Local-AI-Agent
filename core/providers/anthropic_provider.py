import time
import random

from core.providers.base import BaseLLMClient


class AnthropicClient(BaseLLMClient):

    def __init__(
        self,
        api_key: str,
        model: str = "claude-2"
    ):
        from anthropic import Anthropic

        self.client = Anthropic(api_key=api_key)
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

        prompt = "\n".join(
            [
                f"{m['role']}: {m['content']}"
                for m in messages
            ]
        )

        kwargs.setdefault("max_tokens", 1024)

        attempt = 0

        while True:

            attempt += 1

            try:

                try:

                    with self.client.messages.stream(
                        messages=messages,
                        model=self.model,
                        **kwargs
                    ) as stream:

                        for text in stream.text_stream:
                            if text:
                                yield text

                    return

                except AttributeError:
                    pass

                try:

                    for chunk in self.client.stream_completion(
                        prompt=prompt,
                        model=self.model,
                        **kwargs
                    ):

                        if isinstance(
                            chunk,
                            dict
                        ):

                            text = (
                                chunk.get("completion")
                                or chunk.get("text")
                            )

                        else:

                            text = str(chunk)

                        if text:
                            yield text

                    return

                except AttributeError:
                    pass

                if hasattr(
                    self.client,
                    "completions"
                ):

                    response = (
                        self.client.completions.create(
                            prompt=prompt,
                            model=self.model,
                            **kwargs
                        )
                    )

                    output = None

                    if isinstance(
                        response,
                        dict
                    ):

                        output = (
                            response.get("completion")
                            or response.get("text")
                            or ""
                        )

                    else:

                        output = str(response)

                    if output:
                        yield output

                    return

                raise RuntimeError(
                    "No supported Anthropic API found"
                )

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

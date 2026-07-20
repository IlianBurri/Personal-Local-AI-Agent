from abc import ABC, abstractmethod
from typing import Iterator


class BaseLLMClient(ABC):

    @abstractmethod
    def stream_chat(self, messages, **kwargs) -> Iterator[str]:
        raise NotImplementedError()

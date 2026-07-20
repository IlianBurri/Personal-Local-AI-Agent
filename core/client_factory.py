"""Build the right BaseLLMClient for the chosen provider, and list available models.

This is the single entry point used by `MainWindow.send_message` to dispatch
traffic to Ollama / OpenAI / Anthropic based on the user's selection.
"""

from __future__ import annotations

from typing import Iterable

from core.config import get_api_key, get_model
from core.providers import AnthropicClient, BaseLLMClient, OllamaClient, OpenAIClient


class MissingAPIKey(Exception):
    def __init__(self, provider: str):
        self.provider = provider
        super().__init__(
            f"No API key configured for {provider}. Set it in Settings or "
            f"export the {provider.upper()}_API_KEY environment variable."
        )


# Curated fallback model lists used when the provider's listing API isn't
# available (no key configured, offline, or no `list_models` endpoint).
_FALLBACK_MODELS: dict[str, list[str]] = {
    "openai": [
        "gpt-4o",
        "gpt-4o-mini",
        "gpt-4-turbo",
        "gpt-3.5-turbo",
    ],
    "anthropic": [
        "claude-3-5-sonnet-latest",
        "claude-3-5-haiku-latest",
        "claude-3-opus-latest",
        "claude-3-haiku-20240307",
    ],
    "ollama": ["llama3"],
}


def build_client(
    provider: str, model: str | None, config: dict
) -> BaseLLMClient:
    """Instantiate the provider's client. `model` overrides config."""
    provider = (provider or "ollama").lower()

    if provider == "ollama":
        bucket = config.get("providers", {}).get("ollama", {}) or {}
        base_url = bucket.get("base_url", "http://localhost:11434")
        return OllamaClient(base_url=base_url, model=model or get_model(config, "ollama"))

    if provider == "openai":
        api_key = get_api_key(config, "openai")
        if not api_key:
            raise MissingAPIKey("openai")
        return OpenAIClient(
            api_key=api_key,
            model=model or get_model(config, "openai") or "gpt-4o",
        )

    if provider == "anthropic":
        api_key = get_api_key(config, "anthropic")
        if not api_key:
            raise MissingAPIKey("anthropic")
        return AnthropicClient(
            api_key=api_key,
            model=model
            or get_model(config, "anthropic")
            or "claude-3-5-sonnet-latest",
        )

    raise ValueError(f"Unknown provider: {provider!r}")


def list_models(provider: str, config: dict) -> list[str]:
    """Best-effort list of model identifiers for the given provider."""
    provider = (provider or "ollama").lower()
    if provider == "ollama":
        return _list_ollama_models(config)
    if provider == "openai":
        return _list_openai_models(config)
    if provider == "anthropic":
        return _list_anthropic_models(config)
    return []


# ----------------------------------------------------------------------
# Per-provider implementation
# ----------------------------------------------------------------------


def _list_ollama_models(config: dict) -> list[str]:
    bucket = config.get("providers", {}).get("ollama", {}) or {}
    base_url = bucket.get("base_url", "http://localhost:11434").rstrip("/")
    try:
        import requests  # local import so non-Ollama paths skip the dep

        response = requests.get(f"{base_url}/api/tags", timeout=5)
        response.raise_for_status()
        data = response.json()
        names = [
            m.get("name")
            for m in (data.get("models", []) if isinstance(data, dict) else [])
            if m.get("name")
        ]
        return names if names else list(_FALLBACK_MODELS["ollama"])
    except Exception:
        return list(_FALLBACK_MODELS["ollama"])


def _list_openai_models(config: dict) -> list[str]:
    api_key = get_api_key(config, "openai")
    if not api_key:
        return list(_FALLBACK_MODELS["openai"])
    try:
        from openai import OpenAI

        client = OpenAI(api_key=api_key)
        models = client.models.list()
        ids = sorted(
            m.id for m in models if _looks_like_openai_chat_model(m.id)
        )
        return ids or list(_FALLBACK_MODELS["openai"])
    except Exception:
        return list(_FALLBACK_MODELS["openai"])


def _list_anthropic_models(config: dict) -> list[str]:
    # Anthropic SDK does not expose a public list-models endpoint; always use
    # the curated set so the dropdown is meaningful without a network call.
    return list(_FALLBACK_MODELS["anthropic"])


def _looks_like_openai_chat_model(model_id: str) -> bool:
    """Heuristic: surface chat-capable models in the dropdown."""
    name = model_id.lower()
    return (
        name.startswith(("gpt-", "o1", "o3", "o4", "chatgpt-"))
        or "turbo" in name
        or "instruct" in name
    )


def providers() -> Iterable[str]:
    return ("ollama", "openai", "anthropic")

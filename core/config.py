"""Arca config persistence with provider-aware helpers.

Mutating helpers (`set_provider`, `set_api_key`, `set_model`) persist to disk
automatically. Read-only helpers (`load_config`, `get_provider`, `get_api_key`,
`get_model`) leave the on-disk file untouched.
"""

import json
import os
from pathlib import Path

CONFIG_PATH = Path.home() / ".config" / "arca" / "config.json"
DEFAULT_CONFIG = {
    "provider": None,
    "providers": {
        "ollama": {},
        "openai": {},
        "anthropic": {},
    },
    "generation": {
        "temperature": 0.7,
        "max_tokens": 1024,
    },
    "web": {
        "password_salt": None,
        "password_hash": None,
    },
}


def ensure_config_path() -> Path:
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    if not CONFIG_PATH.exists():
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(DEFAULT_CONFIG, f, indent=2)
    return CONFIG_PATH


def load_config() -> dict:
    path = ensure_config_path()
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        providers = data.setdefault("providers", {})
        for name in DEFAULT_CONFIG["providers"]:
            providers.setdefault(name, {})
        return data
    except Exception:
        return json.loads(json.dumps(DEFAULT_CONFIG))


def save_config(data: dict):
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


# ----------------------------------------------------------------------------
# Read helpers (do not mutate disk)
# ----------------------------------------------------------------------------


def get_provider(config: dict) -> str:
    """Return the chosen provider name, defaulting to 'ollama'."""
    name = config.get("provider")
    return name if name in DEFAULT_CONFIG["providers"] else "ollama"


def get_api_key(config: dict, provider: str) -> str | None:
    """Read API key from config, falling back to the matching env var."""
    explicit = (config.get("providers", {}).get(provider, {}) or {}).get("api_key")
    if explicit:
        return explicit
    return os.environ.get(f"{provider.upper()}_API_KEY") or None


def get_model(config: dict, provider: str) -> str | None:
    return (config.get("providers", {}).get(provider, {}) or {}).get("model")


# ----------------------------------------------------------------------------
# Write helpers (auto-persist)
# ----------------------------------------------------------------------------


def set_provider(config: dict, name: str) -> None:
    config["provider"] = name
    save_config(config)


def set_api_key(config: dict, provider: str, key: str) -> None:
    providers = config.setdefault("providers", {})
    bucket = providers.setdefault(provider, {})
    bucket["api_key"] = key
    save_config(config)


def set_model(config: dict, provider: str, model: str) -> None:
    providers = config.setdefault("providers", {})
    bucket = providers.setdefault(provider, {})
    bucket["model"] = model
    save_config(config)


def get_temperature(config: dict) -> float:
    gen = config.get("generation", {}) or {}
    return gen.get("temperature", 0.7)


def set_temperature(config: dict, value: float) -> None:
    gen = config.setdefault("generation", {})
    gen["temperature"] = round(value, 2)
    save_config(config)


def get_max_tokens(config: dict) -> int:
    gen = config.get("generation", {}) or {}
    return gen.get("max_tokens", 1024)


def set_max_tokens(config: dict, value: int) -> None:
    gen = config.setdefault("generation", {})
    gen["max_tokens"] = value
    save_config(config)


def get_ollama_base_url(config: dict) -> str:
    bucket = config.get("providers", {}).get("ollama", {}) or {}
    return bucket.get("base_url", "http://localhost:11434")


def set_ollama_base_url(config: dict, url: str) -> None:
    providers = config.setdefault("providers", {})
    bucket = providers.setdefault("ollama", {})
    bucket["base_url"] = url.rstrip("/")
    save_config(config)

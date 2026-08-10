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
        "enable_tools": True,
        "allow_shell": False,
        "system_prompt": "",
        "max_tool_rounds": 10,
    },
    "ui": {
        "dark": True,
        "accent": "mint",
        "font_size": 14,
        "chat_width": 740,
        "app_name": "Arca",
        "tagline": "Your models. Your machine. Your rules.",
        "suggestions": [
            "Explain a concept",
            "Write some code",
            "Summarize text",
            "Draft an email",
            "Translate this",
            "Plan a project",
            "Debug my code",
            "Write a poem",
        ],
    },
}

DEFAULT_SUGGESTIONS = list(DEFAULT_CONFIG["ui"]["suggestions"])
DEFAULT_TAGLINE = DEFAULT_CONFIG["ui"]["tagline"]
DEFAULT_APP_NAME = DEFAULT_CONFIG["ui"]["app_name"]


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
        gen = data.setdefault("generation", {})
        for key, value in DEFAULT_CONFIG["generation"].items():
            gen.setdefault(key, value)
        ui = data.setdefault("ui", {})
        for key, value in DEFAULT_CONFIG["ui"].items():
            ui.setdefault(key, value)
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


def get_enable_tools(config: dict) -> bool:
    gen = config.get("generation", {}) or {}
    return bool(gen.get("enable_tools", True))


def set_enable_tools(config: dict, value: bool) -> None:
    gen = config.setdefault("generation", {})
    gen["enable_tools"] = bool(value)
    save_config(config)


def get_allow_shell(config: dict) -> bool:
    gen = config.get("generation", {}) or {}
    return bool(gen.get("allow_shell", False))


def set_allow_shell(config: dict, value: bool) -> None:
    gen = config.setdefault("generation", {})
    gen["allow_shell"] = bool(value)
    save_config(config)


def get_system_prompt(config: dict) -> str:
    gen = config.get("generation", {}) or {}
    return str(gen.get("system_prompt", "") or "").strip()


def set_system_prompt(config: dict, value: str) -> None:
    gen = config.setdefault("generation", {})
    gen["system_prompt"] = (value or "").strip()[:4000]
    save_config(config)


def get_max_tool_rounds(config: dict) -> int:
    gen = config.get("generation", {}) or {}
    value = gen.get("max_tool_rounds")
    if value is None:
        return 10
    try:
        return max(1, min(50, int(value)))
    except (TypeError, ValueError):
        return 10


def set_max_tool_rounds(config: dict, value: int) -> None:
    gen = config.setdefault("generation", {})
    gen["max_tool_rounds"] = max(1, min(50, int(value)))
    save_config(config)


def get_ollama_base_url(config: dict) -> str:
    env_url = os.environ.get("ARCA_OLLAMA_URL")
    if env_url:
        return env_url.rstrip("/")
    bucket = config.get("providers", {}).get("ollama", {}) or {}
    return bucket.get("base_url", "http://localhost:11434")


def set_ollama_base_url(config: dict, url: str) -> None:
    providers = config.setdefault("providers", {})
    bucket = providers.setdefault("ollama", {})
    bucket["base_url"] = url.rstrip("/")
    save_config(config)

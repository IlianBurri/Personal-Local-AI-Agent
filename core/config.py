import json
import os
from pathlib import Path

CONFIG_PATH = Path.home() / ".config" / "arca" / "config.json"

DEFAULT_CONFIG = {
    "provider": None,
    "providers": {},
    "web": {
        "password_salt": None,
        "password_hash": None,
    },
}


def ensure_config_path() -> Path:
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    if not CONFIG_PATH.exists():
        # HIER GEÄNDERT: Wir schreiben die Datei direkt, statt save_config() aufzurufen.
        # Das bricht die Endlosschleife!
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(DEFAULT_CONFIG, f, indent=2)
    return CONFIG_PATH


def load_config() -> dict:
    path = ensure_config_path()
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return DEFAULT_CONFIG.copy()


def save_config(data: dict):
    # Da ensure_config_path() jetzt sicher ist, kannst du es hier bedenkenlos aufrufen
    path = ensure_config_path()
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
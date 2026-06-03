import json
from pathlib import Path
from typing import List, Dict, Any

CONV_PATH = Path.home() / ".config" / "arca" / "conversations.json"

DEFAULT: List[Dict[str, Any]] = []


def ensure_conv_path():
    CONV_PATH.parent.mkdir(parents=True, exist_ok=True)
    if not CONV_PATH.exists():
        save_conversations(DEFAULT)


def load_conversations() -> List[Dict[str, Any]]:
    ensure_conv_path()
    try:
        with open(CONV_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def save_conversations(data: List[Dict[str, Any]]):
    ensure_conv_path()
    with open(CONV_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

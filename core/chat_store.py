import json
import time
from pathlib import Path
from typing import Dict, List, Any, Optional


def ensure_conversations_dir() -> Path:
    path = Path.home() / ".config" / "arca" / "conversations"
    path.mkdir(parents=True, exist_ok=True)
    return path


def safe_filename(prefix: str = "conv") -> str:
    return f"{prefix}_{int(time.time())}.json"


def list_conversation_files() -> List[Path]:
    return sorted(ensure_conversations_dir().glob("*.json"))


def load_conversation(path: Path) -> Dict[str, Any]:
    try:
        with open(path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
            if isinstance(data, dict):
                return data
    except Exception:
        pass
    return {"title": path.stem, "messages": []}


def save_conversation(path: Path, data: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=2)


def create_conversation(title: Optional[str] = None) -> Path:
    path = ensure_conversations_dir() / safe_filename()
    save_conversation(path, {"title": title or f"Conversation {int(time.time())}", "messages": []})
    return path
from pathlib import Path


def read_file(path: str) -> str:
    p = Path(path)
    return p.read_text(encoding="utf-8")


def write_file(path: str, content: str):
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")


def list_dir(path: str):
    p = Path(path)
    if not p.exists():
        return []
    items = []
    for child in sorted(p.iterdir()):
        items.append({"name": child.name, "is_dir": child.is_dir()})
    return items

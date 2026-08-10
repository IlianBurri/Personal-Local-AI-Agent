from pathlib import Path

MAX_FILE_READ = 512 * 1024  # 512 KB of text per read_file call


def read_file(path: str, offset: int | None = None, limit: int | None = None) -> str:
    """Read a text file. Optional ``offset``/``limit`` select a line window.

    Returns the raw text, or a JSON-ish error string when the file is too
    large, missing, or not decodable as UTF-8 text.
    """
    p = Path(path)
    if not p.exists():
        return '{"error": "File not found: %s"}' % path
    if p.stat().st_size > MAX_FILE_READ:
        return (
            '{"error": "File too large to read whole (%d bytes, max %d); '
            'use offset/limit to read it in windows"}' % (p.stat().st_size, MAX_FILE_READ)
        )
    try:
        lines = p.read_text(encoding="utf-8").splitlines(keepends=True)
    except UnicodeDecodeError:
        return '{"error": "File is not UTF-8 text; use run_command for binary files"}'
    if offset is not None or limit is not None:
        start = max(0, (offset or 1) - 1)
        end = None if limit is None else start + limit
        window = lines[start:end]
        header = f"--- {path} lines {start + 1}-{start + len(window)} ---\n"
        return header + "".join(window)
    return "".join(lines)


def write_file(path: str, content: str):
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")


def edit_file(path: str, old: str, new: str, replace_all: bool = False) -> str:
    """Surgically replace ``old`` with ``new`` in a text file.

    Returns a short confirmation, or an error string when the file is
    missing/not UTF-8 or ``old`` is not found. This is preferred over
    write_file for targeted changes because it preserves the rest of the
    file exactly.
    """
    p = Path(path)
    if not p.exists():
        return '{"error": "File not found: %s"}' % path
    try:
        text = p.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return '{"error": "File is not UTF-8 text"}'
    if replace_all:
        if text.count(old) == 0:
            return '{"error": "Text to replace not found in file"}'
        count = text.count(old)
        new_text = text.replace(old, new)
    else:
        if text.count(old) == 0:
            return '{"error": "Text to replace not found in file"}'
        if text.count(old) > 1:
            return (
                '{"error": "Text occurs %d times; pass replace_all=true or '
                "include more surrounding context to disambiguate\"}" % text.count(old)
            )
        count = 1
        new_text = text.replace(old, new, 1)
    p.write_text(new_text, encoding="utf-8")
    return '{"ok": true, "replacements": %d}' % count


def list_dir(path: str):
    p = Path(path)
    if not p.exists():
        return []
    items = []
    for child in sorted(p.iterdir()):
        items.append({"name": child.name, "is_dir": child.is_dir()})
    return items

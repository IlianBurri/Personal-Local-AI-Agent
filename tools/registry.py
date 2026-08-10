"""Central registry for LLM tool use.

Each tool declares a name, description, JSON-Schema parameters and a
handler. The chat loop (``server/chat.py``) exposes these to the providers
and executes them when the model requests a call.
"""

from __future__ import annotations

import json

from tools.file_tool import edit_file, list_dir, read_file, write_file
from tools.git_tool import git_status
from tools.grep_tool import grep_code
from tools.search_tool import fetch_url, web_search
from tools.shell_tool import run_command

MAX_TOOL_OUTPUT = 8000  # characters a single tool result may carry


def _spec(name, description, parameters, handler):
    return {
        "name": name,
        "description": description,
        "parameters": parameters,
        "handler": handler,
    }


TOOL_SPECS = {
    "run_command": _spec(
        "run_command",
        "Run a shell command on the user's machine and return its stdout, "
        "stderr and exit code. Use with care.",
        {
            "type": "object",
            "properties": {
                "command": {"type": "string", "description": "Shell command to run"},
                "cwd": {"type": "string", "description": "Working directory (optional)"},
                "timeout": {"type": "integer", "description": "Timeout in seconds (optional)"},
            },
            "required": ["command"],
        },
        run_command,
    ),
    "read_file": _spec(
        "read_file",
        "Read a text file from disk and return its contents.",
        {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Absolute or relative path"}
            },
            "required": ["path"],
        },
        read_file,
    ),
    "write_file": _spec(
        "write_file",
        "Write text content to a file, creating parent directories as needed.",
        {
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "content": {"type": "string"},
            },
            "required": ["path", "content"],
        },
        write_file,
    ),
    "list_dir": _spec(
        "list_dir",
        "List the entries of a directory.",
        {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Directory path (default: current)"}
            },
            "required": [],
        },
        list_dir,
    ),
    "web_search": _spec(
        "web_search",
        "Search the web and return short text results.",
        {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "max_results": {"type": "integer"},
            },
            "required": ["query"],
        },
        web_search,
    ),
    "fetch_url": _spec(
        "fetch_url",
        "Fetch a web page (http/https) and return its readable text content. "
        "Use after web_search to read the full contents of a promising result.",
        {
            "type": "object",
            "properties": {"url": {"type": "string", "description": "http(s) URL to read"}},
            "required": ["url"],
        },
        fetch_url,
    ),
    "edit_file": _spec(
        "edit_file",
        "Replace a block of text in a file with new text (surgical edit). "
        "Preferred over write_file for targeted changes because it preserves "
        "the rest of the file exactly. Fails if the old text is not found or "
        "is ambiguous; include more surrounding context in that case.",
        {
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "old": {"type": "string", "description": "Exact text to replace"},
                "new": {"type": "string", "description": "Replacement text"},
                "replace_all": {
                    "type": "boolean",
                    "description": "Replace every occurrence (default: first only)",
                },
            },
            "required": ["path", "old", "new"],
        },
        edit_file,
    ),
    "grep_code": _spec(
        "grep_code",
        "Search file contents under a directory (default: current working "
        "directory) with a regular expression. Returns matching lines as "
        "file:line: text. Ideal for finding where a symbol is defined or "
        "used without reading whole files.",
        {
            "type": "object",
            "properties": {
                "pattern": {"type": "string", "description": "Regular expression to match"},
                "path": {"type": "string", "description": "Directory to search (optional)"},
                "max_results": {"type": "integer", "description": "Result cap (optional)"},
            },
            "required": ["pattern"],
        },
        grep_code,
    ),
    "git_status": _spec(
        "git_status",
        "Return the current git branch, working-tree changes, and recent "
        "commits for the workspace. Read-only. Use before editing files so "
        "you know the repository state.",
        {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Repo path (optional, default: current)"}
            },
            "required": [],
        },
        git_status,
    ),
}


def openai_tools_schema(allowed: set[str] | None = None) -> list[dict]:
    """OpenAI / Ollama function-calling format."""
    return [
        {
            "type": "function",
            "function": {
                "name": spec["name"],
                "description": spec["description"],
                "parameters": spec["parameters"],
            },
        }
        for spec in _filter_specs(allowed)
    ]


def anthropic_tools_schema(allowed: set[str] | None = None) -> list[dict]:
    """Anthropic tool format."""
    return [
        {
            "name": spec["name"],
            "description": spec["description"],
            "input_schema": spec["parameters"],
        }
        for spec in _filter_specs(allowed)
    ]


def _filter_specs(allowed: set[str] | None = None):
    for name, spec in TOOL_SPECS.items():
        if allowed is None or name in allowed:
            yield spec


def tool_names() -> list[str]:
    return list(TOOL_SPECS)


def execute_tool(name: str, args: dict) -> tuple[bool, str]:
    """Run a tool; returns ``(ok, result_text)`` for the model to read."""
    spec = TOOL_SPECS.get(name)
    if spec is None:
        return False, json.dumps({"error": f"Unknown tool: {name}"}, ensure_ascii=False)
    try:
        result = spec["handler"](**(args or {}))
    except TypeError as exc:
        return False, json.dumps({"error": f"Invalid arguments: {exc}"}, ensure_ascii=False)
    except Exception as exc:  # noqa: BLE001 - tool errors become model-visible results
        return False, json.dumps({"error": str(exc)}, ensure_ascii=False)

    if isinstance(result, str):
        result = {"content": result}
    elif result is None:
        result = {"ok": True}
    text = json.dumps(result, ensure_ascii=False, default=str)
    if len(text) > MAX_TOOL_OUTPUT:
        text = text[:MAX_TOOL_OUTPUT]
        text += (
            f"\n...[truncated: output exceeded {MAX_TOOL_OUTPUT} chars; "
            "ask for a narrower slice if you need more]"
        )
    return True, text

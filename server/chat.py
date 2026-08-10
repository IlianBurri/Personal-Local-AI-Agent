"""Server-side chat orchestration.

Streams provider responses as ``(event, payload)`` tuples suitable for SSE
and transparently runs the tool loop: when the model requests tool calls
they are executed and the conversation continues until a plain text answer
is produced.

Events emitted: ``token`` (``{"text": ...}``) and
``tool`` (``{"name", "status": "start"|"done", "index", "ok"}``).
"""

from __future__ import annotations

import json
import os
import threading
import uuid

from core.client_factory import build_client
from core.config import (
    get_allow_shell,
    get_enable_tools,
    get_max_tokens,
    get_max_tool_rounds,
    get_system_prompt,
    get_temperature,
)
from tools.registry import (
    anthropic_tools_schema,
    execute_tool,
    openai_tools_schema,
)

# Cap on tool-call rounds per turn; overridable via ARCA_MAX_TOOL_ROUNDS.
# When the cap is hit the loop forces one final plain-text answer instead of
# stopping mid-tool-call, and emits a ``notice`` event so the UI can say why.
MAX_TOOL_ROUNDS = int(os.environ.get("ARCA_MAX_TOOL_ROUNDS", "10"))

# ---------------------------------------------------------------------------
# Generation registry — used by POST /api/stop
# ---------------------------------------------------------------------------

_stop_flags: dict[str, bool] = {}
_stop_lock = threading.Lock()


def register_generation() -> str:
    gen_id = uuid.uuid4().hex
    with _stop_lock:
        _stop_flags[gen_id] = False
    return gen_id


def request_stop(gen_id: str) -> bool:
    with _stop_lock:
        if gen_id in _stop_flags:
            _stop_flags[gen_id] = True
            return True
    return False


def unregister_generation(gen_id: str) -> None:
    with _stop_lock:
        _stop_flags.pop(gen_id, None)


def _should_stop(gen_id: str) -> bool:
    with _stop_lock:
        return _stop_flags.get(gen_id, False)


# ---------------------------------------------------------------------------
# Public entry
# ---------------------------------------------------------------------------


def stream(messages, provider, model, config, gen_id: str | None = None):
    """Yield ``(event, payload)`` tuples for one assistant turn.

    Stops early (cleanly) once ``request_stop(gen_id)`` has been called.
    """
    gen_id = gen_id or register_generation()
    # Defensive: even an explicitly passed gen_id must support stopping.
    with _stop_lock:
        _stop_flags.setdefault(gen_id, False)
    try:
        gen_kwargs = {
            "temperature": get_temperature(config),
            "max_tokens": get_max_tokens(config),
            "system_prompt": get_system_prompt(config) or None,
            "max_tool_rounds": get_max_tool_rounds(config),
        }
        # Tool policy: safe tools are enabled by default; shell execution
        # stays opt-in because the model may be prompted to run anything.
        allowed: set[str] | None = None
        if get_enable_tools(config):
            allowed = {
                "read_file",
                "write_file",
                "edit_file",
                "list_dir",
                "grep_code",
                "web_search",
                "fetch_url",
                "git_status",
            }
            if get_allow_shell(config):
                allowed.add("run_command")
        client = build_client(provider, model, config)
        provider = (provider or "ollama").lower()
        yield from _tool_loop(
            client, provider, list(messages), gen_id, gen_kwargs, allowed=allowed
        )
    finally:
        unregister_generation(gen_id)


# ---------------------------------------------------------------------------
# Tool loop
# ---------------------------------------------------------------------------


def _tool_loop(client, provider, messages, gen_id, gen_kwargs, allowed=None):
    """Run tool-aware streaming rounds until a plain answer is produced.

    ``allowed`` is the set of tool names the model may call (None = no
    tools at all). If a provider/model rejects the ``tools`` parameter,
    retry the first round without tools before giving up.
    """
    rounds = 0
    tools_enabled = allowed is not None
    max_rounds = int(gen_kwargs.get("max_tool_rounds") or MAX_TOOL_ROUNDS)

    while True:
        rounds += 1
        if rounds > max_rounds:
            # The model keeps calling tools; force one final plain-text round
            # so the user gets a real answer rather than a silent cut.
            tools_enabled = False
            yield (
                "notice",
                {
                    "message": (
                        f"Reached the tool-call limit ({max_rounds} rounds); "
                        "stopping tool use and wrapping up."
                    )
                },
            )
            messages.append(
                {
                    "role": "user",
                    "content": (
                        "You have reached the tool-call limit for this turn. "
                        "Do NOT call any more tools. Answer now with a concise "
                        "summary of what you have accomplished and any "
                        "suggested next steps."
                    ),
                }
            )

        if provider == "openai":
            round_gen = _openai_round(
                client, messages, gen_kwargs, tools_enabled, allowed
            )
        elif provider == "anthropic":
            round_gen = _anthropic_round(
                client, messages, gen_kwargs, tools_enabled, allowed
            )
        else:
            round_gen = _ollama_round(
                client, messages, gen_kwargs, tools_enabled, allowed
            )

        text_yielded = False
        text = ""
        tool_calls = None
        try:
            while True:
                try:
                    event = next(round_gen)
                except StopIteration as stop:
                    tool_calls, text = stop.value
                    break
                if _should_stop(gen_id):
                    return
                if event[0] == "token":
                    text_yielded = True
                yield event
        except Exception:
            # Only fall back when nothing has been streamed yet.
            if tools_enabled and not text_yielded:
                tools_enabled = False
                continue
            raise

        if not tool_calls or not tools_enabled:
            return

        # Model requested tools → execute them and continue the conversation.
        messages.append(_assistant_tool_message(provider, text, tool_calls))
        for index, call in enumerate(tool_calls):
            name = call.get("name", "")
            args = call.get("arguments", {})
            if isinstance(args, str):
                try:
                    args = json.loads(args)
                except Exception:
                    args = {"raw": args}
            yield ("tool", {"name": name, "status": "start", "index": index})
            ok, result = execute_tool(name, args)
            yield ("tool", {"name": name, "status": "done", "index": index, "ok": ok})
            messages.append(_tool_result_message(provider, call, result, index))


def _assistant_tool_message(provider: str, text: str, tool_calls: list[dict]) -> dict:
    if provider == "anthropic":
        content: list[dict] = []
        if text:
            content.append({"type": "text", "text": text})
        for index, call in enumerate(tool_calls):
            content.append(
                {
                    "type": "tool_use",
                    "id": call.get("id") or f"toolu_{index}",
                    "name": call["name"],
                    "input": _parse_args(call.get("arguments", {})),
                }
            )
        return {"role": "assistant", "content": content}
    # OpenAI expects `arguments` as a JSON string, Ollama as an object.
    if provider == "ollama":
        return {
            "role": "assistant",
            "content": text or None,
            "tool_calls": [
                {
                    "id": call.get("id") or f"call_{call['name']}_{index}",
                    "type": "function",
                    "function": {
                        "name": call["name"],
                        "arguments": _parse_args(call.get("arguments", {})),
                    },
                }
                for index, call in enumerate(tool_calls)
            ],
        }
    return {
        "role": "assistant",
        "content": text or None,
        "tool_calls": [
            {
                "id": call.get("id") or f"call_{call['name']}_{index}",
                "type": "function",
                "function": {
                    "name": call["name"],
                    "arguments": json.dumps(_parse_args(call.get("arguments", {}))),
                },
            }
            for index, call in enumerate(tool_calls)
        ],
    }


def _parse_args(args):
    if isinstance(args, dict):
        return args
    try:
        return json.loads(args or "{}")
    except Exception:
        return {"raw": args}


def _tool_result_message(provider: str, call: dict, result: str, index: int) -> dict:
    call_id = call.get("id") or f"call_{call['name']}_{index}"
    if provider == "anthropic":
        return {
            "role": "user",
            "content": [{"type": "tool_result", "tool_use_id": call_id, "content": result}],
        }
    if provider == "ollama":
        return {"role": "tool", "content": result}
    return {"role": "tool", "tool_call_id": call_id, "content": result}


# ---------------------------------------------------------------------------
# Per-provider streaming rounds
# ---------------------------------------------------------------------------


def _with_system(messages: list[dict], system_prompt: str | None) -> list[dict]:
    """Prepend a system message for providers that take it inline."""
    if not system_prompt:
        return messages
    return [{"role": "system", "content": system_prompt}] + list(messages)


def _openai_round(client, messages, gen_kwargs, tools_enabled, allowed=None):
    call_kwargs = dict(gen_kwargs)
    # Internal loop knobs — never forwarded to the provider SDK.
    call_kwargs.pop("system_prompt", None)
    call_kwargs.pop("max_tool_rounds", None)
    if tools_enabled:
        call_kwargs["tools"] = openai_tools_schema(allowed)
    msgs = _with_system(messages, gen_kwargs.get("system_prompt"))
    response = client.chat.completions.create(
        model=client.model, messages=msgs, stream=True, **call_kwargs
    )
    acc: dict[int, dict] = {}
    text = ""
    for chunk in response:
        for choice in getattr(chunk, "choices", []):
            delta = getattr(choice, "delta", None)
            if delta is None:
                continue
            content = getattr(delta, "content", None)
            if content:
                text += content
                yield ("token", {"text": content})
            for tc in getattr(delta, "tool_calls", None) or []:
                entry = acc.setdefault(tc.index, {"id": "", "name": "", "arguments": ""})
                if getattr(tc, "id", None):
                    entry["id"] = tc.id
                fn = getattr(tc, "function", None)
                if fn is not None:
                    if getattr(fn, "name", None):
                        entry["name"] += fn.name
                    if getattr(fn, "arguments", None):
                        entry["arguments"] += fn.arguments
    calls = []
    for idx in sorted(acc):
        entry = acc[idx]
        if entry["name"]:
            calls.append(
                {
                    "id": entry["id"] or f"call_{entry['name']}_{idx}",
                    "name": entry["name"],
                    "arguments": entry["arguments"],
                }
            )
    return calls, text


def _anthropic_round(client, messages, gen_kwargs, tools_enabled, allowed=None):
    call_kwargs = dict(gen_kwargs)
    # Internal loop knobs — never forwarded to the provider SDK.
    call_kwargs.pop("system_prompt", None)
    call_kwargs.pop("max_tool_rounds", None)
    if tools_enabled:
        call_kwargs["tools"] = anthropic_tools_schema(allowed)
    system = gen_kwargs.get("system_prompt")
    if system:
        call_kwargs["system"] = system
    text = ""
    tool_uses: dict[int, dict] = {}
    with client.messages.stream(messages=messages, model=client.model, **call_kwargs) as stream:
        for event in stream:
            if event.type == "content_block_start":
                block = getattr(event, "content_block", None)
                if block is not None and getattr(block, "type", None) == "tool_use":
                    tool_uses[event.index] = {
                        "id": block.id,
                        "name": block.name,
                        "input": "",
                    }
            elif event.type == "content_block_delta":
                delta = getattr(event, "delta", None)
                if delta is None:
                    continue
                d_type = getattr(delta, "type", None)
                if d_type == "text_delta":
                    if getattr(delta, "text", None):
                        text += delta.text
                        yield ("token", {"text": delta.text})
                elif d_type == "input_json_delta" and event.index in tool_uses:
                    tool_uses[event.index]["input"] += getattr(delta, "partial_json", "")
    calls = []
    for idx in sorted(tool_uses):
        entry = tool_uses[idx]
        try:
            parsed = json.loads(entry["input"] or "{}")
        except Exception:
            parsed = {"raw": entry["input"]}
        calls.append({"id": entry["id"], "name": entry["name"], "arguments": parsed})
    return calls, text


def _ollama_round(client, messages, gen_kwargs, tools_enabled, allowed=None):
    import requests

    payload = {
        "model": client.model or "llama3",
        "messages": _with_system(messages, gen_kwargs.get("system_prompt")),
        "stream": True,
    }
    if tools_enabled:
        payload["tools"] = openai_tools_schema(allowed)
    if gen_kwargs.get("temperature") is not None:
        payload["temperature"] = gen_kwargs["temperature"]
    if gen_kwargs.get("max_tokens"):
        payload["num_predict"] = int(gen_kwargs["max_tokens"])

    text = ""
    calls = []
    with requests.post(
        f"{client.base_url}/api/chat", json=payload, stream=True, timeout=120
    ) as response:
        response.raise_for_status()
        for line in response.iter_lines(decode_unicode=True):
            if not line:
                continue
            try:
                data = json.loads(line)
            except Exception:
                continue
            if data.get("done"):
                break
            msg = data.get("message") or {}
            chunk = msg.get("content") or ""
            if chunk:
                text += chunk
                yield ("token", {"text": chunk})
            for tc in msg.get("tool_calls") or []:
                fn = tc.get("function") or {}
                name = fn.get("name") or ""
                if not name:
                    continue
                args = fn.get("arguments") or {}
                if isinstance(args, str):
                    try:
                        args = json.loads(args)
                    except Exception:
                        args = {"raw": args}
                calls.append(
                    {"id": f"call_{name}_{len(calls)}", "name": name, "arguments": args}
                )
    return calls, text

"""Unit tests for the server-side tool-use loop."""

from types import SimpleNamespace

from server import chat as chat_mod

_CONFIG = {"providers": {}, "generation": {"temperature": 0.7, "max_tokens": 128}}


class _FakeStream:
    def __init__(self, events):
        self._events = iter(events)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def __iter__(self):
        return self._events


def _chunk(delta):
    return SimpleNamespace(choices=[SimpleNamespace(delta=delta)])


def _delta(content=None, tool_calls=None):
    return SimpleNamespace(content=content, tool_calls=tool_calls)


def test_openai_tool_loop(monkeypatch):
    round_no = {"n": 0}

    def fake_create(model, messages, stream=True, **kwargs):
        round_no["n"] += 1
        if round_no["n"] == 1:
            tc = SimpleNamespace(
                index=0,
                id="call_1",
                function=SimpleNamespace(
                    name="read_file", arguments='{"path": "a.txt"}'
                ),
            )
            return iter([_chunk(_delta(tool_calls=[tc]))])
        return iter([_chunk(_delta(content="The answer."))])

    class FakeCompletions:
        @staticmethod
        def create(model, messages, stream=True, **kwargs):
            return fake_create(model, messages, stream, **kwargs)

    class FakeClient:
        model = "gpt-test"
        chat = SimpleNamespace(completions=FakeCompletions)

    monkeypatch.setattr(chat_mod, "build_client", lambda *a, **k: FakeClient())
    monkeypatch.setattr(
        chat_mod,
        "execute_tool",
        lambda name, args: (True, '{"content": "file text"}'),
    )

    events = list(
        chat_mod.stream(
            [{"role": "user", "content": "read a.txt"}],
            "openai",
            "gpt-test",
            _CONFIG,
        )
    )
    tokens = [p["text"] for e, p in events if e == "token"]
    assert tokens == ["The answer."]

    tools = [p for e, p in events if e == "tool"]
    assert tools[0]["name"] == "read_file"
    assert tools[0]["status"] == "start"
    assert tools[1]["status"] == "done"
    assert tools[1]["ok"] is True


def test_anthropic_tool_loop(monkeypatch):
    round_no = {"n": 0}

    def fake_events(messages, model, **kwargs):
        round_no["n"] += 1
        if round_no["n"] == 1:
            return [
                SimpleNamespace(
                    type="content_block_start",
                    index=0,
                    content_block=SimpleNamespace(
                        type="tool_use", id="toolu_1", name="list_dir"
                    ),
                ),
                SimpleNamespace(
                    type="content_block_delta",
                    index=0,
                    delta=SimpleNamespace(
                        type="input_json_delta", partial_json='{"path": "."}'
                    ),
                ),
            ]
        return [
            SimpleNamespace(
                type="content_block_delta",
                index=0,
                delta=SimpleNamespace(type="text_delta", text="Done."),
            )
        ]

    class FakeMessages:
        @staticmethod
        def stream(messages, model, **kwargs):
            return _FakeStream(fake_events(messages, model, **kwargs))

    class FakeClient:
        model = "claude-test"
        messages = FakeMessages

    monkeypatch.setattr(chat_mod, "build_client", lambda *a, **k: FakeClient())
    monkeypatch.setattr(
        chat_mod, "execute_tool", lambda name, args: (True, "[]")
    )

    events = list(
        chat_mod.stream(
            [{"role": "user", "content": "list dir"}],
            "anthropic",
            "claude-test",
            _CONFIG,
        )
    )
    tokens = [p["text"] for e, p in events if e == "token"]
    assert tokens == ["Done."]

    tools = [p for e, p in events if e == "tool"]
    assert tools[0]["name"] == "list_dir"
    assert tools[-1]["status"] == "done"


def test_stop_halts_stream(monkeypatch):
    def fake_create(model, messages, stream=True, **kwargs):
        return iter([_chunk(_delta(content=f"tok{i} ")) for i in range(100)])

    class FakeCompletions:
        @staticmethod
        def create(model, messages, stream=True, **kwargs):
            return fake_create(model, messages, stream, **kwargs)

    class FakeClient:
        model = "gpt-test"
        chat = SimpleNamespace(completions=FakeCompletions)

    monkeypatch.setattr(chat_mod, "build_client", lambda *a, **k: FakeClient())

    gen = chat_mod.stream(
        [{"role": "user", "content": "hi"}],
        "openai",
        "gpt-test",
        _CONFIG,
        gen_id="stop-test",
    )
    assert next(gen) == ("token", {"text": "tok0 "})

    assert chat_mod.request_stop("stop-test") is True
    assert list(gen) == []  # loop returns at the next checkpoint


def test_tools_disabled_by_policy(monkeypatch):
    """When tool use is disabled, no tools are offered to the model."""
    sent = {}

    def fake_create(model, messages, stream=True, **kwargs):
        sent["tools"] = kwargs.get("tools")
        return iter([_chunk(_delta(content="ok"))])

    class FakeCompletions:
        @staticmethod
        def create(model, messages, stream=True, **kwargs):
            return fake_create(model, messages, stream, **kwargs)

    class FakeClient:
        model = "gpt-test"
        chat = SimpleNamespace(completions=FakeCompletions)

    monkeypatch.setattr(chat_mod, "build_client", lambda *a, **k: FakeClient())

    config = {
        "providers": {},
        "generation": {"temperature": 0.7, "max_tokens": 128, "enable_tools": False},
    }
    list(chat_mod.stream([{"role": "user", "content": "hi"}], "openai", "gpt-test", config))
    assert sent["tools"] is None


def test_openai_system_prompt_prepended(monkeypatch):
    seen = {}

    def fake_create(model, messages, stream=True, **kwargs):
        seen["messages"] = list(messages)
        return iter([_chunk(_delta(content="ok"))])

    class FakeCompletions:
        @staticmethod
        def create(model, messages, stream=True, **kwargs):
            return fake_create(model, messages, stream, **kwargs)

    class FakeClient:
        model = "gpt-test"
        chat = SimpleNamespace(completions=FakeCompletions)

    monkeypatch.setattr(chat_mod, "build_client", lambda *a, **k: FakeClient())
    config = {
        **_CONFIG,
        "generation": {
            **_CONFIG["generation"],
            "system_prompt": "You are a terse assistant.",
        },
    }
    list(
        chat_mod.stream(
            [{"role": "user", "content": "hi"}], "openai", "gpt-test", config
        )
    )
    assert seen["messages"][0] == {
        "role": "system",
        "content": "You are a terse assistant.",
    }


def test_anthropic_system_prompt_param(monkeypatch):
    seen = {}

    def fake_events(messages, model, **kwargs):
        seen["system"] = kwargs.get("system")
        return [
            SimpleNamespace(
                type="content_block_delta",
                index=0,
                delta=SimpleNamespace(type="text_delta", text="ok"),
            )
        ]

    class FakeMessages:
        @staticmethod
        def stream(messages, model, **kwargs):
            return _FakeStream(fake_events(messages, model, **kwargs))

    class FakeClient:
        model = "claude-test"
        messages = FakeMessages

    monkeypatch.setattr(chat_mod, "build_client", lambda *a, **k: FakeClient())
    config = {
        **_CONFIG,
        "generation": {
            **_CONFIG["generation"],
            "system_prompt": "You are a terse assistant.",
        },
    }
    list(
        chat_mod.stream(
            [{"role": "user", "content": "hi"}], "anthropic", "claude-test", config
        )
    )
    assert seen["system"] == "You are a terse assistant."


def test_max_tool_rounds_from_config(monkeypatch):
    round_no = {"n": 0}

    def fake_create(model, messages, stream=True, **kwargs):
        round_no["n"] += 1
        if kwargs.get("tools") is not None:
            tc = SimpleNamespace(
                index=0,
                id="call_x",
                function=SimpleNamespace(name="list_dir", arguments="{}"),
            )
            return iter([_chunk(_delta(tool_calls=[tc]))])
        return iter([_chunk(_delta(content="done"))])

    class FakeCompletions:
        @staticmethod
        def create(model, messages, stream=True, **kwargs):
            return fake_create(model, messages, stream, **kwargs)

    class FakeClient:
        model = "gpt-test"
        chat = SimpleNamespace(completions=FakeCompletions)

    monkeypatch.setattr(chat_mod, "build_client", lambda *a, **k: FakeClient())
    config = {
        **_CONFIG,
        "generation": {**_CONFIG["generation"], "max_tool_rounds": 2},
    }
    events = list(
        chat_mod.stream(
            [{"role": "user", "content": "do it"}], "openai", "gpt-test", config
        )
    )
    # 2 tool rounds, then 1 forced wrap-up round.
    assert round_no["n"] == 3
    notices = [p["message"] for e, p in events if e == "notice"]
    assert len(notices) == 1


def test_tool_round_cap_forces_wrapup(monkeypatch):
    """After MAX_TOOL_ROUNDS tool rounds, the loop emits a notice and a
    final plain-text answer instead of silently stopping."""
    round_no = {"n": 0}

    def fake_create(model, messages, stream=True, **kwargs):
        round_no["n"] += 1
        if kwargs.get("tools") is not None:
            # Keep requesting a tool call every round.
            tc = SimpleNamespace(
                index=0,
                id="call_x",
                function=SimpleNamespace(name="list_dir", arguments="{}"),
            )
            return iter([_chunk(_delta(tool_calls=[tc]))])
        # Tools disabled → forced final answer.
        return iter([_chunk(_delta(content="Wrapped up."))])

    class FakeCompletions:
        @staticmethod
        def create(model, messages, stream=True, **kwargs):
            return fake_create(model, messages, stream, **kwargs)

    class FakeClient:
        model = "gpt-test"
        chat = SimpleNamespace(completions=FakeCompletions)

    monkeypatch.setattr(chat_mod, "MAX_TOOL_ROUNDS", 3)
    monkeypatch.setattr(chat_mod, "build_client", lambda *a, **k: FakeClient())
    monkeypatch.setattr(
        chat_mod, "execute_tool", lambda name, args: (True, "[]")
    )

    events = list(
        chat_mod.stream(
            [{"role": "user", "content": "do agent work"}],
            "openai",
            "gpt-test",
            _CONFIG,
        )
    )
    notices = [p["message"] for e, p in events if e == "notice"]
    assert len(notices) == 1
    assert "tool-call limit" in notices[0]

    tokens = [p["text"] for e, p in events if e == "token"]
    assert tokens[-1] == "Wrapped up."


def test_plain_streaming_without_tools(monkeypatch):
    """Providers that reject the tools param fall back to plain streaming."""
    round_no = {"n": 0}

    def fake_create(model, messages, stream=True, **kwargs):
        round_no["n"] += 1
        if "tools" in kwargs:
            raise RuntimeError("tools not supported")
        return iter([_chunk(_delta(content="plain"))])

    class FakeCompletions:
        @staticmethod
        def create(model, messages, stream=True, **kwargs):
            return fake_create(model, messages, stream, **kwargs)

    class FakeClient:
        model = "gpt-test"
        chat = SimpleNamespace(completions=FakeCompletions)

    monkeypatch.setattr(chat_mod, "build_client", lambda *a, **k: FakeClient())

    events = list(
        chat_mod.stream(
            [{"role": "user", "content": "hi"}],
            "openai",
            "gpt-test",
            _CONFIG,
        )
    )
    tokens = [p["text"] for e, p in events if e == "token"]
    assert tokens == ["plain"]
    assert round_no["n"] == 2  # one attempt with tools, one without

"""API-level tests for the Arca web server."""

import pytest

import core.config as cfg_mod
import server.app as sa
from core.database import ChatRepository, SQLiteManager


@pytest.fixture
def client(tmp_path, monkeypatch):
    # Isolate the on-disk config so tests never touch ~/.config/arca.
    monkeypatch.setattr(cfg_mod, "CONFIG_PATH", tmp_path / "config.json")

    db = SQLiteManager(db_path=str(tmp_path / "test.db"))
    monkeypatch.setattr(sa, "_db", db)
    monkeypatch.setattr(sa, "_repo", ChatRepository(db))

    flask_app = sa.create_app()
    monkeypatch.setattr(
        sa,
        "_config",
        {
            "provider": "ollama",
            "providers": {
                "ollama": {"base_url": "http://localhost:11434"},
                "openai": {},
                "anthropic": {},
            },
            "generation": {"temperature": 0.7, "max_tokens": 1024},
            "ui": {"dark": True, "accent": "mint"},
        },
    )
    flask_app.config["TESTING"] = True
    yield flask_app.test_client()


# ---------------------------------------------------------------------------
# Chats CRUD
# ---------------------------------------------------------------------------


def test_chat_crud(client):
    resp = client.post("/api/chats", json={})
    assert resp.status_code == 201
    chat_id = resp.get_json()["id"]

    chats = client.get("/api/chats").get_json()
    assert len(chats) == 1 and chats[0]["id"] == chat_id

    resp = client.patch(f"/api/chats/{chat_id}", json={"title": "Hello"})
    assert resp.status_code == 200
    assert client.get("/api/chats").get_json()[0]["title"] == "Hello"

    assert client.delete(f"/api/chats/{chat_id}").status_code == 204
    assert client.get("/api/chats").get_json() == []


# ---------------------------------------------------------------------------
# Chat streaming (SSE)
# ---------------------------------------------------------------------------


def test_streaming_chat_flow(client, monkeypatch):
    def fake_stream(messages, provider, model, config, gen_id=None):
        yield ("token", {"text": "Hello "})
        yield ("token", {"text": "world"})

    monkeypatch.setattr(sa.chat_service, "stream", fake_stream)

    resp = client.post("/api/chat", json={"text": "hi"})
    assert resp.status_code == 200
    assert "text/event-stream" in resp.content_type
    body = resp.get_data(as_text=True)

    assert "event: meta" in body
    assert '"gen_id"' in body
    assert "event: token" in body
    assert '"Hello "' in body and '"world"' in body
    assert "event: done" in body

    chats = sa._repo.get_all_chats()
    assert len(chats) == 1
    assert chats[0]["title"] == "hi"  # auto-titled from first user message

    msgs = sa._repo.get_chat_messages(chats[0]["id"])
    assert [m["role"] for m in msgs] == ["user", "assistant"]
    assert msgs[1]["content"] == "Hello world"


def test_streaming_error_event(client, monkeypatch):
    def boom(messages, provider, model, config, gen_id=None):
        raise RuntimeError("provider down")

    monkeypatch.setattr(sa.chat_service, "stream", boom)
    resp = client.post("/api/chat", json={"text": "hi"})
    body = resp.get_data(as_text=True)
    assert "event: error" in body
    assert "provider down" in body


def test_regenerate(client, monkeypatch):
    seen = []

    def fake_stream(messages, provider, model, config, gen_id=None):
        seen.append([m["role"] for m in messages])
        yield ("token", {"text": "answer"})

    monkeypatch.setattr(sa.chat_service, "stream", fake_stream)

    resp = client.post("/api/chat", json={"text": "question"})
    resp.get_data(as_text=True)  # consume the SSE stream
    chat_id = sa._repo.get_all_chats()[0]["id"]

    resp = client.post("/api/chat", json={"chat_id": chat_id, "regenerate": True})
    assert resp.status_code == 200
    resp.get_data(as_text=True)
    # The deleted assistant turn is gone, so the history is user-only again.
    assert seen[-1] == ["user"]

    msgs = sa._repo.get_chat_messages(chat_id)
    assert [m["role"] for m in msgs] == ["user", "assistant"]


def test_stop_endpoint(client):
    resp = client.post("/api/stop", json={"gen_id": "does-not-exist"})
    assert resp.get_json() == {"ok": False}


# ---------------------------------------------------------------------------
# Config / models / status
# ---------------------------------------------------------------------------


def test_config_roundtrip(client):
    cfg = client.get("/api/config").get_json()
    assert cfg["provider"] == "ollama"
    assert cfg["providers"]["ollama"]["has_key"] is False
    assert cfg["providers"]["openai"]["has_key"] is False

    resp = client.post(
        "/api/config",
        json={
            "provider": "openai",
            "api_keys": {"openai": "sk-test"},
            "generation": {"temperature": 0.2, "max_tokens": 512},
            "ui": {"dark": False, "accent": "azure"},
        },
    )
    assert resp.status_code == 200

    cfg = client.get("/api/config").get_json()
    assert cfg["provider"] == "openai"
    assert cfg["providers"]["openai"]["has_key"] is True
    assert cfg["providers"]["anthropic"]["has_key"] is False
    assert cfg["generation"]["temperature"] == 0.2
    assert cfg["generation"]["max_tokens"] == 512
    assert cfg["ui"]["accent"] == "azure"


def test_config_customization_roundtrip(client):
    """New customization fields persist and come back through /api/config."""
    resp = client.post(
        "/api/config",
        json={
            "generation": {
                "system_prompt": "You are a terse senior engineer.",
                "max_tool_rounds": 25,
            },
            "ui": {
                "accent": "#ff8800",
                "font_size": 17,
                "chat_width": 900,
                "app_name": "MyAgent",
                "tagline": "Built by me.",
                "suggestions": ["Fix a bug", "Write tests"],
            },
        },
    )
    assert resp.status_code == 200

    cfg = client.get("/api/config").get_json()
    assert cfg["generation"]["system_prompt"] == "You are a terse senior engineer."
    assert cfg["generation"]["max_tool_rounds"] == 25
    assert cfg["ui"]["accent"] == "#ff8800"
    assert cfg["ui"]["font_size"] == 17
    assert cfg["ui"]["chat_width"] == 900
    assert cfg["ui"]["app_name"] == "MyAgent"
    assert cfg["ui"]["tagline"] == "Built by me."
    assert cfg["ui"]["suggestions"] == ["Fix a bug", "Write tests"]

    # Clamping: out-of-range values are normalized.
    resp = client.post(
        "/api/config",
        json={"ui": {"font_size": 999, "chat_width": 2}},
    )
    assert resp.status_code == 200
    cfg = client.get("/api/config").get_json()
    assert cfg["ui"]["font_size"] == 20
    assert cfg["ui"]["chat_width"] == 560


def test_models_endpoint(client, monkeypatch):
    monkeypatch.setattr(sa, "list_models", lambda provider, config: ["a", "b"])
    resp = client.get("/api/models?provider=openai")
    assert resp.get_json() == {"models": ["a", "b"]}


def test_status_endpoint(client, monkeypatch):
    import requests

    class FakeResp:
        status_code = 200

    monkeypatch.setattr(requests, "get", lambda *a, **k: FakeResp())
    data = client.get("/api/status").get_json()
    assert data["ollama_reachable"] is True
    assert data["provider"] == "ollama"

"""Arca web server — Flask backend for the React frontend.

Serves the built SPA from ``ui/web/dist`` and exposes a small JSON/SSE API:

* ``GET  /api/chats`` / ``POST /api/chats`` / ``DELETE /api/chats/<id>``
* ``PATCH /api/chats/<id>`` (rename) / ``GET /api/chats/<id>/messages``
* ``POST /api/chat``  — SSE stream (send or regenerate an assistant turn)
* ``POST /api/stop``  — stop a running generation
* ``GET  /api/models?provider=...`` / ``GET /api/config`` / ``POST /api/config``
* ``GET  /api/status`` — provider, model, Ollama reachability
"""

from __future__ import annotations

import json
import os
import threading
from pathlib import Path

import requests
from flask import Flask, Response, jsonify, request, send_from_directory

from core.client_factory import MissingAPIKey, list_models, providers
from core.config import (
    DEFAULT_APP_NAME,
    DEFAULT_SUGGESTIONS,
    DEFAULT_TAGLINE,
    get_allow_shell,
    get_api_key,
    get_enable_tools,
    get_max_tokens,
    get_max_tool_rounds,
    get_model,
    get_ollama_base_url,
    get_provider,
    get_system_prompt,
    get_temperature,
    load_config,
    save_config,
    set_allow_shell,
    set_api_key,
    set_enable_tools,
    set_max_tokens,
    set_max_tool_rounds,
    set_model,
    set_ollama_base_url,
    set_provider,
    set_system_prompt,
    set_temperature,
)
from core.database import ChatRepository, SQLiteManager

from . import chat as chat_service

FRONTEND_DIR = Path(__file__).resolve().parent.parent / "ui" / "web" / "dist"

_db = SQLiteManager()
_repo = ChatRepository(_db)
_db_lock = threading.Lock()
_config = load_config()


def _make_title(text: str, limit: int = 40) -> str:
    title = " ".join(text.strip().split())
    if len(title) > limit:
        title = title[:limit].rstrip() + "\u2026"
    return title or "New chat"


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def create_app(frontend_dir: Path | None = None) -> Flask:
    global _config
    _config = load_config()
    assets_dir = frontend_dir or FRONTEND_DIR

    app = Flask(__name__)
    app.config["JSON_SORT_KEYS"] = False

    # ------------------------------------------------------------------
    # Static frontend
    # ------------------------------------------------------------------
    @app.route("/")
    def index():
        if not (assets_dir / "index.html").exists():
            return (
                "<h1>Frontend not built</h1>"
                "<p>Run <code>cd ui/web &amp;&amp; npm install &amp;&amp; "
                "npm run build</code> and restart Arca.</p>",
                200,
            )
        return send_from_directory(assets_dir, "index.html")

    @app.route("/assets/<path:filename>")
    def assets(filename):
        return send_from_directory(assets_dir / "assets", filename)

    # ------------------------------------------------------------------
    # Config
    # ------------------------------------------------------------------
    @app.get("/api/config")
    def api_config_get():
        ui = dict(_config.get("ui", {}) or {})
        ui.setdefault("dark", True)
        ui.setdefault("accent", "mint")
        ui.setdefault("font_size", 14)
        ui.setdefault("chat_width", 740)
        ui.setdefault("app_name", DEFAULT_APP_NAME)
        ui.setdefault("tagline", DEFAULT_TAGLINE)
        ui.setdefault("suggestions", DEFAULT_SUGGESTIONS)
        data = {
            "provider": get_provider(_config),
            "providers": {},
            "generation": {
                "temperature": get_temperature(_config),
                "max_tokens": get_max_tokens(_config),
                "enable_tools": get_enable_tools(_config),
                "allow_shell": get_allow_shell(_config),
                "system_prompt": get_system_prompt(_config),
                "max_tool_rounds": get_max_tool_rounds(_config),
            },
            "ui": ui,
        }
        for name in providers():
            bucket = {
                "model": get_model(_config, name),
                "has_key": bool(get_api_key(_config, name)),
            }
            if name == "ollama":
                bucket["base_url"] = get_ollama_base_url(_config)
            data["providers"][name] = bucket
        return jsonify(data)

    @app.post("/api/config")
    def api_config_set():
        body = request.get_json(silent=True) or {}
        if body.get("provider"):
            set_provider(_config, body["provider"])
        for prov, key in (body.get("api_keys") or {}).items():
            if prov in providers() and key and str(key).strip():
                set_api_key(_config, prov, str(key).strip())
        for prov, model in (body.get("models") or {}).items():
            if prov in providers() and model and str(model).strip():
                set_model(_config, prov, str(model).strip())
        ollama = body.get("ollama") or {}
        if ollama.get("base_url"):
            set_ollama_base_url(_config, str(ollama["base_url"]))
        gen = body.get("generation") or {}
        if gen.get("temperature") is not None:
            set_temperature(_config, float(gen["temperature"]))
        if gen.get("max_tokens"):
            set_max_tokens(_config, int(gen["max_tokens"]))
        if gen.get("enable_tools") is not None:
            set_enable_tools(_config, bool(gen["enable_tools"]))
        if gen.get("allow_shell") is not None:
            set_allow_shell(_config, bool(gen["allow_shell"]))
        if "system_prompt" in gen:
            set_system_prompt(_config, gen["system_prompt"])
        if gen.get("max_tool_rounds") is not None:
            set_max_tool_rounds(_config, int(gen["max_tool_rounds"]))
        ui = body.get("ui")
        if isinstance(ui, dict):
            prefs = _config.setdefault("ui", {"dark": True, "accent": "mint"})
            if "dark" in ui:
                prefs["dark"] = bool(ui["dark"])
            if ui.get("accent") is not None:
                prefs["accent"] = str(ui["accent"]).strip()[:20] or "mint"
            if ui.get("font_size") is not None:
                prefs["font_size"] = max(12, min(20, int(ui["font_size"])))
            if ui.get("chat_width") is not None:
                prefs["chat_width"] = max(560, min(1000, int(ui["chat_width"])))
            if ui.get("app_name") is not None:
                prefs["app_name"] = str(ui["app_name"]).strip()[:40] or DEFAULT_APP_NAME
            if ui.get("tagline") is not None:
                prefs["tagline"] = str(ui["tagline"]).strip()[:120]
            if ui.get("suggestions") is not None and isinstance(ui["suggestions"], list):
                prefs["suggestions"] = [
                    str(s).strip()[:60]
                    for s in ui["suggestions"]
                    if str(s).strip()
                ][:12]
            save_config(_config)
        return jsonify({"ok": True})

    # ------------------------------------------------------------------
    # Status / models
    # ------------------------------------------------------------------
    @app.get("/api/status")
    def api_status():
        provider = get_provider(_config)
        reachable = False
        try:
            resp = requests.get(f"{get_ollama_base_url(_config)}/api/tags", timeout=2)
            reachable = resp.status_code < 400
        except Exception:
            reachable = False
        return jsonify(
            {
                "provider": provider,
                "model": get_model(_config, provider),
                "has_key": bool(get_api_key(_config, provider)),
                "ollama_reachable": reachable,
            }
        )

    @app.get("/api/models")
    def api_models():
        provider = request.args.get("provider") or "ollama"
        return jsonify({"models": list_models(provider, _config)})

    # ------------------------------------------------------------------
    # Chats
    # ------------------------------------------------------------------
    @app.get("/api/chats")
    def api_chats():
        with _db_lock:
            return jsonify(_repo.get_all_chats())

    @app.post("/api/chats")
    def api_create_chat():
        with _db_lock:
            chat_id = _repo.create_chat("New chat")
            return jsonify({"id": chat_id}), 201

    @app.patch("/api/chats/<int:chat_id>")
    def api_rename_chat(chat_id):
        body = request.get_json(silent=True) or {}
        title = (body.get("title") or "").strip()
        if not title:
            return jsonify({"error": "title required"}), 400
        with _db_lock:
            _repo.rename_chat(chat_id, title)
        return jsonify({"ok": True})

    @app.delete("/api/chats/<int:chat_id>")
    def api_delete_chat(chat_id):
        with _db_lock:
            _repo.delete_chat(chat_id)
        return "", 204

    @app.get("/api/chats/<int:chat_id>/messages")
    def api_chat_messages(chat_id):
        with _db_lock:
            return jsonify(_repo.get_chat_messages(chat_id))

    # ------------------------------------------------------------------
    # Chat streaming (SSE)
    # ------------------------------------------------------------------
    @app.post("/api/chat")
    def api_chat():
        body = request.get_json(silent=True) or {}
        provider = (body.get("provider") or "").strip() or None
        model = (body.get("model") or "").strip() or None
        text = (body.get("text") or "").strip()
        regenerate = bool(body.get("regenerate"))
        chat_id = body.get("chat_id")
        gen_id = chat_service.register_generation()

        with _db_lock:
            if not chat_id:
                chat_id = _repo.create_chat("New chat")
            if regenerate:
                _repo.delete_last_assistant_message(chat_id)
            elif text:
                _repo.add_user_message(chat_id, text)
            title = None
            try:
                chats = {c["id"]: c for c in _repo.get_all_chats()}
                if chats.get(chat_id, {}).get("title") == "New chat" and text:
                    title = _make_title(text)
                    _repo.rename_chat(chat_id, title)
            except Exception:
                title = None
            history = _repo.get_chat_messages(chat_id)

        messages = [{"role": m["role"], "content": m["content"]} for m in history]

        def generate():
            assistant_text = ""
            try:
                yield _sse(
                    "meta",
                    {"gen_id": gen_id, "chat_id": chat_id, "title": title},
                )
                for event, payload in chat_service.stream(
                    messages, provider, model, _config, gen_id=gen_id
                ):
                    yield _sse(event, payload)
                    if event == "token":
                        assistant_text += payload["text"]
                if assistant_text:
                    with _db_lock:
                        _repo.add_assistant_message(chat_id, assistant_text)
                yield _sse("done", {"text": assistant_text})
            except MissingAPIKey as exc:
                yield _sse(
                    "error",
                    {
                        "message": (
                            f"No API key configured for {exc.provider.title()}. "
                            f"Set it in Settings or export the "
                            f"{exc.provider.upper()}_API_KEY environment variable."
                        )
                    },
                )
            except Exception as exc:  # noqa: BLE001 - surfaced to the UI
                yield _sse("error", {"message": str(exc)})
            finally:
                chat_service.unregister_generation(gen_id)

        return Response(
            generate(),
            mimetype="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    @app.post("/api/stop")
    def api_stop():
        body = request.get_json(silent=True) or {}
        ok = False
        if body.get("gen_id"):
            ok = chat_service.request_stop(body["gen_id"])
        return jsonify({"ok": ok})

    return app


def run(host: str | None = None, port: int | None = None) -> None:
    host = host or os.environ.get("ARCA_HOST", "127.0.0.1")
    port = port or int(os.environ.get("ARCA_PORT", "8765"))
    create_app().run(
        host=host, port=port, threaded=True, use_reloader=False, debug=False
    )

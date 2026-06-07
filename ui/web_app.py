import base64
import hashlib
import html
import json
import secrets
import threading
import urllib.parse
import webbrowser
from http import HTTPStatus
from http.cookies import SimpleCookie
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from typing import Any, Dict, List, Optional

from core.chat_store import (
    create_conversation,
    ensure_conversations_dir,
    list_conversation_files,
    load_conversation,
    save_conversation,
)
from core.clients import OpenAIClient, AnthropicClient, OllamaClient
from core.config import load_config, save_config


DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8765
SESSION_COOKIE = "arca_session"


def _json_response(handler: BaseHTTPRequestHandler, payload: Dict[str, Any], status: int = 200) -> None:
    body = json.dumps(payload).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def _html_response(handler: BaseHTTPRequestHandler, body: str, status: int = 200) -> None:
    encoded = body.encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "text/html; charset=utf-8")
    handler.send_header("Content-Length", str(len(encoded)))
    handler.end_headers()
    handler.wfile.write(encoded)


def _redirect(handler: BaseHTTPRequestHandler, location: str) -> None:
    handler.send_response(302)
    handler.send_header("Location", location)
    handler.end_headers()


def _parse_cookies(handler: BaseHTTPRequestHandler) -> SimpleCookie:
    cookie = SimpleCookie()
    raw = handler.headers.get("Cookie", "")
    if raw:
        cookie.load(raw)
    return cookie


def _read_request_body(handler: BaseHTTPRequestHandler) -> bytes:
    length = int(handler.headers.get("Content-Length", "0") or 0)
    if length <= 0:
        return b""
    return handler.rfile.read(length)


def _parse_json_body(handler: BaseHTTPRequestHandler) -> Dict[str, Any]:
    raw = _read_request_body(handler)
    if not raw:
        return {}
    return json.loads(raw.decode("utf-8"))


def _parse_form_body(handler: BaseHTTPRequestHandler) -> Dict[str, str]:
    raw = _read_request_body(handler).decode("utf-8")
    parsed = urllib.parse.parse_qs(raw, keep_blank_values=True)
    return {key: values[0] if values else "" for key, values in parsed.items()}


def hash_password(password: str, salt: Optional[str] = None) -> Dict[str, str]:
    salt_bytes = base64.urlsafe_b64decode(salt.encode("utf-8")) if salt else secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt_bytes, 100_000)
    return {
        "password_salt": base64.urlsafe_b64encode(salt_bytes).decode("utf-8"),
        "password_hash": digest.hex(),
    }


def verify_password(stored_salt: Optional[str], stored_hash: Optional[str], password: str) -> bool:
    if not stored_salt or not stored_hash:
        return False
    candidate = hash_password(password, stored_salt)
    return secrets.compare_digest(candidate["password_hash"], stored_hash)


def _ensure_web_config(config: Dict[str, Any]) -> Dict[str, Any]:
    config.setdefault("web", {})
    config["web"].setdefault("password_salt", None)
    config["web"].setdefault("password_hash", None)
    return config


def _available_provider_names(config: Dict[str, Any]) -> List[str]:
    providers = config.get("providers", {}) or {}
    names = [name for name in ["openai", "anthropic", "ollama"] if name in providers or name in ("openai", "anthropic", "ollama")]
    return names if names else ["openai", "anthropic", "ollama"]


def _build_client(config: Dict[str, Any], provider: str, model: Optional[str]) -> Any:
    providers = config.get("providers", {}) or {}
    if provider == "openai":
        api_key = providers.get("openai", {}).get("api_key")
        if not api_key:
            raise RuntimeError("OpenAI API key is not configured")
        return OpenAIClient(api_key, model=model or "gpt-4o")

    if provider == "anthropic":
        api_key = providers.get("anthropic", {}).get("api_key")
        if not api_key:
            raise RuntimeError("Anthropic API key is not configured")
        return AnthropicClient(api_key, model=model or "claude-3-5-sonnet")

    base_url = providers.get("ollama", {}).get("base_url", "http://localhost:11434")
    return OllamaClient(base_url=base_url, model=model)


def _build_messages(conversation: Dict[str, Any], system_prompt: str, user_message: Optional[str] = None) -> List[Dict[str, str]]:
    messages: List[Dict[str, str]] = []
    if system_prompt.strip():
        messages.append({"role": "system", "content": system_prompt.strip()})
    for message in conversation.get("messages", []):
        role = message.get("role") or "user"
        content = message.get("content") or ""
        messages.append({"role": role, "content": content})
    if user_message:
        messages.append({"role": "user", "content": user_message})
    return messages


def _session_token(handler: BaseHTTPRequestHandler) -> Optional[str]:
    cookie = _parse_cookies(handler)
    if SESSION_COOKIE in cookie:
        return cookie[SESSION_COOKIE].value
    return None


class ArcaWebServer(ThreadingHTTPServer):
    def __init__(self, server_address, handler_class):
        super().__init__(server_address, handler_class)
        self.config = _ensure_web_config(load_config())
        self.sessions: Dict[str, str] = {}
        self.lock = threading.Lock()


class ArcaWebHandler(BaseHTTPRequestHandler):
    server: ArcaWebServer

    def log_message(self, format: str, *args: Any) -> None:
        return

    def _is_authenticated(self) -> bool:
        token = _session_token(self)
        return bool(token and token in self.server.sessions)

    def _set_session_cookie(self, token: str) -> None:
        self.send_header("Set-Cookie", f"{SESSION_COOKIE}={token}; HttpOnly; Path=/; SameSite=Lax")

    def _clear_session_cookie(self) -> None:
        self.send_header("Set-Cookie", f"{SESSION_COOKIE}=; HttpOnly; Path=/; Max-Age=0; SameSite=Lax")

    def do_GET(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        if path == "/":
            if not self.server.config["web"].get("password_hash"):
                return _html_response(self, render_setup_page())
            if self._is_authenticated():
                return _html_response(self, render_app_page())
            return _html_response(self, render_login_page())

        if path == "/logout":
            token = _session_token(self)
            if token:
                self.server.sessions.pop(token, None)
            self.send_response(302)
            self._clear_session_cookie()
            self.send_header("Location", "/")
            self.end_headers()
            return

        if path == "/app":
            if self._is_authenticated():
                return _html_response(self, render_app_page())
            return _redirect(self, "/")

        if path == "/api/bootstrap":
            if not self._is_authenticated():
                return _json_response(self, {"ok": False, "error": "unauthorized"}, 401)

            ollama_models: List[str] = []
            try:
                base_url = self.server.config.get("providers", {}).get("ollama", {}).get("base_url", "http://localhost:11434")
                ollama_models = _build_client(self.server.config, "ollama", None).list_models()
                if isinstance(ollama_models, dict):
                    items = ollama_models.get("models", []) or ollama_models.get("tags", [])
                    ollama_models = [item.get("name") or item.get("model") or item.get("tag") for item in items if isinstance(item, dict)]
                elif isinstance(ollama_models, list):
                    ollama_models = [item for item in ollama_models if isinstance(item, str)]
            except Exception:
                ollama_models = []

            conversation_items = []
            for file_path in list_conversation_files():
                data = load_conversation(file_path)
                conversation_items.append(
                    {
                        "id": file_path.name,
                        "title": data.get("title") or file_path.stem,
                        "path": file_path.name,
                        "message_count": len(data.get("messages", [])),
                    }
                )

            return _json_response(
                self,
                {
                    "ok": True,
                    "provider": self.server.config.get("provider") or "openai",
                    "providers": _available_provider_names(self.server.config),
                    "ollama_models": ollama_models,
                    "conversations": conversation_items,
                },
            )

        if path == "/api/conversations":
            if not self._is_authenticated():
                return _json_response(self, {"ok": False, "error": "unauthorized"}, 401)
            items = []
            for file_path in list_conversation_files():
                data = load_conversation(file_path)
                items.append({"id": file_path.name, "title": data.get("title") or file_path.stem})
            return _json_response(self, {"ok": True, "conversations": items})

        if path.startswith("/api/conversations/"):
            if not self._is_authenticated():
                return _json_response(self, {"ok": False, "error": "unauthorized"}, 401)
            name = Path(path.split("/api/conversations/", 1)[1]).name
            file_path = ensure_conversations_dir() / name
            if not file_path.exists():
                return _json_response(self, {"ok": False, "error": "not_found"}, 404)
            return _json_response(self, {"ok": True, "conversation": load_conversation(file_path)})

        self.send_error(HTTPStatus.NOT_FOUND)

    def do_POST(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        if path == "/setup":
            form = _parse_form_body(self)
            password = form.get("password", "").strip()
            if len(password) < 6:
                return _html_response(self, render_setup_page("Password must be at least 6 characters."), 400)
            hashed = hash_password(password)
            self.server.config["web"].update(hashed)
            save_config(self.server.config)
            token = secrets.token_urlsafe(32)
            self.server.sessions[token] = "local"
            self.send_response(302)
            self._set_session_cookie(token)
            self.send_header("Location", "/app")
            self.end_headers()
            return

        if path == "/login":
            form = _parse_form_body(self)
            password = form.get("password", "")
            web_settings = self.server.config.get("web", {})
            if not verify_password(web_settings.get("password_salt"), web_settings.get("password_hash"), password):
                return _html_response(self, render_login_page("Invalid password."), 401)
            token = secrets.token_urlsafe(32)
            self.server.sessions[token] = "local"
            self.send_response(302)
            self._set_session_cookie(token)
            self.send_header("Location", "/app")
            self.end_headers()
            return

        if path == "/logout":
            token = _session_token(self)
            if token:
                self.server.sessions.pop(token, None)
            self.send_response(302)
            self._clear_session_cookie()
            self.send_header("Location", "/")
            self.end_headers()
            return

        if not self._is_authenticated():
            return _json_response(self, {"ok": False, "error": "unauthorized"}, 401)

        if path == "/api/conversations/new":
            file_path = create_conversation()
            return _json_response(self, {"ok": True, "conversation": {"id": file_path.name, "title": file_path.stem}})

        if path == "/api/chat":
            payload = _parse_json_body(self)
            provider = payload.get("provider") or self.server.config.get("provider") or "openai"
            model = payload.get("model") or None
            message = (payload.get("message") or "").strip()
            conversation_id = (payload.get("conversation_id") or "").strip()
            system_prompt = payload.get("system_prompt") or ""
            temperature = float(payload.get("temperature") or 0.7)
            max_tokens = int(payload.get("max_tokens") or 1024)

            if not message:
                return _json_response(self, {"ok": False, "error": "empty_message"}, 400)

            if conversation_id:
                conversation_path = ensure_conversations_dir() / Path(conversation_id).name
            else:
                conversation_path = create_conversation()

            if not conversation_path.exists():
                save_conversation(conversation_path, {"title": conversation_path.stem, "messages": []})

            conversation = load_conversation(conversation_path)
            conversation.setdefault("messages", []).append({"role": "user", "content": message})

            try:
                client = _build_client(self.server.config, provider, model)
                messages = _build_messages(conversation, system_prompt)
                
                # Hier schalten wir auf HTTP-Streaming um (Server-Sent Events)
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream; charset=utf-8")
                self.send_header("Cache-Control", "no-cache")
                self.send_header("Connection", "keep-alive")
                self.end_headers()

                full_response = []
                for token in client.stream_chat(messages, temperature=temperature, max_tokens=max_tokens):
                    if token:
                        full_response.append(token)
                        # Sende das Token im SSE-Format (data: ...)
                        self.wfile.write(f"data: {json.dumps({'token': token})}\n\n".encode("utf-8"))
                        self.wfile.flush()

                response_text = "".join(full_response).strip()
                conversation["messages"].append({"role": "assistant", "content": response_text})
                
                if not conversation.get("title") or conversation["title"].startswith("Conversation "):
                    conversation["title"] = message[:48] or conversation_path.stem
                save_conversation(conversation_path, conversation)

                # Sende das finale Signal mit den aktualisierten Metadaten
                final_meta = {
                    "done": True, 
                    "conversation": {"id": conversation_path.name, "title": conversation.get("title")}
                }
                self.wfile.write(f"data: {json.dumps(final_meta)}\n\n".encode("utf-8"))
                self.wfile.flush()
                return

            except Exception as exc:
                # Da Header möglicherweise schon gesendet wurden, senden wir den Fehler im Stream
                try:
                    self.wfile.write(f"data: {json.dumps({'error': str(exc)})}\n\n".encode("utf-8"))
                    self.wfile.flush()
                except Exception:
                    pass
                return

        self.send_error(HTTPStatus.NOT_FOUND)


def start_web_ui(host: str = DEFAULT_HOST, port: int = DEFAULT_PORT, open_browser: bool = True) -> ArcaWebServer:
    server = ArcaWebServer((host, port), ArcaWebHandler)
    if open_browser:
        webbrowser.open(f"http://{host}:{port}/")
    return server


def render_setup_page(error_message: str = "") -> str:
    return _render_auth_document("Set up Arca", "Create a local password to unlock the web UI.", error_message, setup=True)


def render_login_page(error_message: str = "") -> str:
    return _render_auth_document("Sign in to Arca", "Use your local password to open the agent web UI.", error_message, setup=False)


def _render_auth_document(title: str, subtitle: str, error_message: str, setup: bool) -> str:
    action = "/setup" if setup else "/login"
    button_label = "Create password" if setup else "Sign in"
    prompt = "Create a local password" if setup else "Password"
    error_html = f'<div class="error">{html.escape(error_message)}</div>' if error_message else ""
    return f"""<!doctype html>
<html lang="en" data-theme="dark">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width,initial-scale=1" />
  <title>{html.escape(title)}</title>
  <style>
    :root {{
      --bg: #0b0c0e;
      --panel: #111317;
      --panel-soft: #181b22;
      --text: #f3f4f1;
      --muted: #8e95a5;
      --border: #1f242e;
      --accent: #5e94e8;
      --accent-strong: #8bb2f3;
      --shadow: 0 20px 50px rgba(0, 0, 0, 0.5);
    }}
    * {{ box-sizing: border-box; }}
    body {{ margin: 0; min-height: 100vh; display: grid; place-items: center; background: var(--bg); color: var(--text); font-family: system-ui, -apple-system, sans-serif; }}
    .card {{ width: min(420px, calc(100vw - 32px)); background: var(--panel); border: 1px solid var(--border); border-radius: 16px; padding: 32px; box-shadow: var(--shadow); }}
    .wordmark {{ font-size: 12px; letter-spacing: 0.2em; text-transform: uppercase; color: var(--accent); font-weight: 700; margin-bottom: 24px; }}
    h1 {{ margin: 0 0 8px; font-size: 24px; font-weight: 600; letter-spacing: -0.02em; }}
    p {{ margin: 0 0 24px; color: var(--muted); font-size: 14px; line-height: 1.5; }}
    form {{ display: grid; gap: 16px; }}
    label {{ display: grid; gap: 8px; font-size: 13px; color: var(--muted); }}
    input {{ width: 100%; border: 1px solid var(--border); background: var(--panel-soft); color: var(--text); border-radius: 8px; padding: 12px 14px; font-size: 15px; outline: none; transition: border 0.2s; }}
    input:focus {{ border-color: var(--accent); }}
    button {{ border: 0; border-radius: 8px; background: var(--accent); color: #000; padding: 12px 18px; font-weight: 600; font-size: 15px; cursor: pointer; transition: background 0.2s; }}
    button:hover {{ background: var(--accent-strong); }}
    .error {{ background: rgba(220, 76, 76, 0.1); border: 1px solid rgba(220, 76, 76, 0.2); color: #ff8b8b; border-radius: 8px; padding: 12px; font-size: 14px; }}
    .hint {{ margin-top: 24px; font-size: 12px; color: var(--muted); text-align: center; }}
  </style>
</head>
<body>
  <div class="card">
    <div class="wordmark">Arca // Odysseus</div>
    <h1>{html.escape(title)}</h1>
    <p>{html.escape(subtitle)}</p>
    {error_html}
    <form method="post" action="{action}">
      <label>
        {html.escape(prompt)}
        <input type="password" name="password" autofocus required />
      </label>
      <button type="submit">{button_label}</button>
    </form>
    <div class="hint">Runs fully locally on your machine.</div>
  </div>
</body>
</html>"""


def render_app_page() -> str:
    return """<!doctype html>
<html lang="en" data-theme="dark">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width,initial-scale=1" />
  <title>Odysseus Workspace</title>
  <style>
    :root {
      --bg-main: #07080a;
      --bg-side: #0b0c10;
      --panel: #12141c;
      --panel-hover: #1c1f2b;
      --text: #f3f4f6;
      --muted: #858e9e;
      --border: #1b1e28;
      --accent: #4e8bf5;
      --accent-soft: rgba(78, 139, 245, 0.1);
      --font: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    }
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body { background: var(--bg-main); color: var(--text); font-family: var(--font); height: 100vh; overflow: hidden; }
    
    .workspace { display: grid; grid-template-columns: 260px 300px 1fr; height: 100vh; }
    
    /* Global Sidebar Navigation (Odysseus Hub) */
    .nav-bar { background: var(--bg-side); border-right: 1px solid var(--border); padding: 20px 14px; display: flex; flex-direction: column; gap: 24px; }
    .hub-title { font-size: 11px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.2em; color: var(--accent); padding-left: 8px; }
    .nav-group { display: flex; flex-direction: column; gap: 4px; }
    .nav-item { display: flex; align-items: center; gap: 10px; background: transparent; border: none; color: var(--muted); padding: 10px 12px; border-radius: 8px; cursor: pointer; text-align: left; font-size: 14px; font-weight: 500; transition: all 0.2s; }
    .nav-item:hover { background: var(--panel); color: var(--text); }
    .nav-item.active { background: var(--accent-soft); color: var(--accent); font-weight: 600; }
    .nav-footer { margin-top: auto; border-top: 1px solid var(--border); padding-top: 14px; }

    /* Secondary Sidebar (Conversations / Settings) */
    .sub-bar { background: #090a0e; border-right: 1px solid var(--border); display: flex; flex-direction: column; min-width: 0; }
    .sidebar-header { padding: 20px; border-bottom: 1px solid var(--border); display: flex; justify-content: space-between; align-items: center; }
    .sidebar-header h3 { font-size: 14px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.05em; color: var(--text); }
    .action-btn { background: var(--panel); border: 1px solid var(--border); color: var(--text); border-radius: 6px; padding: 6px 12px; font-size: 12px; cursor: pointer; font-weight: 500; }
    .action-btn:hover { background: var(--panel-hover); }
    .conv-list { flex: 1; overflow-y: auto; padding: 12px 8px; display: flex; flex-direction: column; gap: 4px; }
    .conv-item { background: transparent; border: none; padding: 12px; border-radius: 8px; cursor: pointer; text-align: left; display: flex; flex-direction: column; gap: 4px; transition: background 0.2s; }
    .conv-item:hover { background: rgba(255,255,255,0.02); }
    .conv-item.active { background: var(--panel); border-left: 3px solid var(--accent); border-radius: 0 8px 8px 0; }
    .conv-title { font-size: 13.5px; font-weight: 500; color: var(--text); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
    .conv-meta { font-size: 11px; color: var(--muted); }

    /* Main Content Area */
    .main-view { display: flex; flex-direction: column; background: var(--bg-main); min-width: 0; position: relative; }
    .top-nav { height: 60px; border-bottom: 1px solid var(--border); display: flex; align-items: center; justify-content: space-between; padding: 0 24px; background: rgba(7, 8, 10, 0.8); backdrop-filter: blur(12px); z-index: 10; }
    .current-meta { display: flex; flex-direction: column; }
    .current-title { font-size: 14px; font-weight: 600; }
    .current-status { font-size: 11px; color: var(--accent); font-weight: 500; letter-spacing: 0.05em; }
    
    /* View Switching Targets */
    .view-panel { display: none; flex: 1; flex-direction: column; min-height: 0; }
    .view-panel.active { display: flex; }

    /* Chat View Styles */
    .chat-scroll { flex: 1; overflow-y: auto; padding: 24px; display: flex; flex-direction: column; gap: 20px; }
    .msg-row { display: flex; width: 100%; }
    .msg-row.user { justify-content: flex-end; }
    .msg-bubble { max-width: 70%; padding: 14px 18px; border-radius: 12px; font-size: 14.5px; line-height: 1.6; word-wrap: break-word; }
    .msg-row.user .msg-bubble { background: var(--accent); color: #000; font-weight: 500; border-radius: 16px 16px 2px 16px; }
    .msg-row.assistant .msg-bubble { background: var(--panel); border: 1px solid var(--border); color: var(--text); border-radius: 16px 16px 16px 2px; }
    
    /* Empty & Alternative Placeholder Views */
    .placeholder-view { flex: 1; display: flex; flex-direction: column; align-items: center; justify-content: center; p: 24px; color: var(--muted); text-align: center; gap: 12px; }
    .placeholder-view h2 { color: var(--text); font-weight: 500; font-size: 20px; }

    /* Composer Block */
    .composer-area { padding: 20px 24px; border-top: 1px solid var(--border); background: var(--bg-main); }
    .input-box { background: var(--panel); border: 1px solid var(--border); border-radius: 12px; padding: 12px 16px; display: flex; flex-direction: column; gap: 8px; }
    .input-box textarea { width: 100%; background: transparent; border: none; color: var(--text); font-family: var(--font); font-size: 14.5px; outline: none; resize: none; min-height: 44px; max-height: 160px; line-height: 1.5; }
    .input-controls { display: flex; justify-content: space-between; align-items: center; border-top: 1px solid rgba(255,255,255,0.03); padding-top: 8px; }
    .config-selectors { display: flex; gap: 8px; }
    .selector { background: var(--bg-main); border: 1px solid var(--border); color: var(--muted); font-size: 12px; padding: 4px 8px; border-radius: 6px; outline: none; cursor: pointer; }
    .selector:focus { border-color: var(--accent); color: var(--text); }
    .send-trigger { background: var(--text); color: var(--bg-main); font-weight: 600; border: none; border-radius: 6px; padding: 6px 16px; font-size: 13px; cursor: pointer; }
    .send-trigger:hover { background: #fff; }
    
    /* Parameter Config Panel */
    .parameter-row { display: grid; grid-template-columns: repeat(2, 1fr); gap: 12px; margin-top: 12px; }
    .param-field { display: flex; flex-direction: column; gap: 4px; }
    .param-field label { font-size: 11px; color: var(--muted); text-transform: uppercase; font-weight: 600; }
    .param-field input { background: var(--panel); border: 1px solid var(--border); color: var(--text); padding: 6px 10px; border-radius: 6px; font-size: 12px; outline: none; }
    .sys-field { grid-column: 1 / -1; }
    .sys-field textarea { background: var(--panel); border: 1px solid var(--border); color: var(--text); padding: 8px; border-radius: 6px; font-size: 12px; outline: none; resize: none; height: 50px; font-family: var(--font); }

    .error-banner { color: #ff6b6b; font-size: 12px; margin-top: 8px; display: none; }
  </style>
</head>
<body>

  <div class="workspace">
    <nav class="nav-bar">
      <div class="hub-title">Odysseus AI</div>
      <div class="nav-group">
        <button class="nav-item active" onclick="switchView('chat')">
          <span>💬</span> Workspace Chat
        </button>
        <button class="nav-item" onclick="switchView('compare')">
          <span>⚖️</span> Blind Compare
        </button>
        <button class="nav-item" onclick="switchView('research')">
          <span>🔍</span> Deep Research
        </button>
      </div>
      <div class="nav-footer">
        <button class="nav-item" style="width:100%" onclick="location.href='/logout'">
          <span>🚪</span> Exit Session
        </button>
      </div>
    </nav>

    <aside class="sub-bar">
      <div class="sidebar-header">
        <h3 id="sidebarContextTitle">Conversations</h3>
        <button class="action-btn" id="newChatBtn">New Chat</button>
      </div>
      <div id="conversationList" class="conv-list"></div>
    </aside>

    <main class="main-view">
      <header class="top-nav">
        <div class="current-meta">
          <span class="current-title" id="pageTitle">Select or create a room</span>
          <span class="current-status" id="statusText">System Idle</span>
        </div>
      </header>

      <section id="view-chat" class="view-panel active">
        <div id="chatLog" class="chat-scroll">
          <div class="placeholder-view">
            <h2>Welcome to your Local Node</h2>
            <p>Select a conversation from the left pane or spawn a new instance.</p>
          </div>
        </div>
        
        <div class="composer-area">
          <div class="input-box">
            <textarea id="messageInput" placeholder="Type your instruction or inquiry here... (Press Enter to transmit, Shift+Enter for newline)"></textarea>
            <div class="input-controls">
              <div class="config-selectors">
                <select id="providerSelect" class="selector"></select>
                <select id="modelSelect" class="selector"></select>
              </div>
              <button class="send-trigger" id="sendBtn">Transmit</button>
            </div>
          </div>
          
          <div class="parameter-row">
            <div class="param-field"><label>Temperature</label><input id="temperatureInput" type="number" min="0" max="2" step="0.1" value="0.7" /></div>
            <div class="param-field"><label>Max Tokens</label><input id="maxTokensInput" type="number" min="16" max="4096" value="2048" /></div>
            <div class="param-field sys-field"><label>System Context Directive</label><textarea id="systemPromptInput" placeholder="Inject overarching operational parameters..."></textarea></div>
          </div>
          <div class="error-banner" id="errorText"></div>
        </div>
      </section>

      <section id="view-compare" class="view-panel">
        <div class="placeholder-view">
          <h2>⚖️ Model Blind Comparison Mode</h2>
          <p>Evaluate engine performances side-by-side without interface bias. Feature initialization upcoming.</p>
        </div>
      </section>

      <section id="view-research" class="view-panel">
        <div class="placeholder-view">
          <h2>🔍 Agentic Deep Research Engine</h2>
          <p>Automated recursive crawling and localized information aggregation pipeline. Feature initialization upcoming.</p>
        </div>
      </section>
    </main>
  </div>

  <script>
    const chatLog = document.getElementById('chatLog');
    const conversationList = document.getElementById('conversationList');
    const providerSelect = document.getElementById('providerSelect');
    const modelSelect = document.getElementById('modelSelect');
    const temperatureInput = document.getElementById('temperatureInput');
    const maxTokensInput = document.getElementById('maxTokensInput');
    const systemPromptInput = document.getElementById('systemPromptInput');
    const messageInput = document.getElementById('messageInput');
    const statusText = document.getElementById('statusText');
    const errorText = document.getElementById('errorText');
    const pageTitle = document.getElementById('pageTitle');
    const newChatBtn = document.getElementById('newChatBtn');
    
    let bootstrap = null;
    let activeConversationId = localStorage.getItem('arca-active-conversation') || '';

    // View Routing
    function switchView(viewName) {
      document.querySelectorAll('.nav-item').forEach(btn => btn.classList.remove('active'));
      document.querySelectorAll('.view-panel').forEach(panel => panel.classList.remove('active'));
      
      const targetBtn = Array.from(document.querySelectorAll('.nav-item')).find(btn => btn.getAttribute('onclick').includes(viewName));
      if(targetBtn) targetBtn.classList.add('active');
      
      document.getElementById(`view-${viewName}`).classList.add('active');
      
      const subBar = document.querySelector('.sub-bar');
      if (viewName !== 'chat') {
        subBar.style.display = 'none';
        document.querySelector('.workspace').style.gridTemplateColumns = "260px 1fr";
      } else {
        subBar.style.display = 'flex';
        document.querySelector('.workspace').style.gridTemplateColumns = "260px 300px 1fr";
      }
    }

    function escapeHtml(text) {
      return String(text).replace(/[&<>'"]/g, ch => ({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[ch]));
    }

    function setStatus(text) { statusText.textContent = text; }
    function setError(text) { 
      if(text) { errorText.textContent = text; errorText.style.display = 'block'; }
      else { errorText.style.display = 'none'; }
    }

    function renderConversations(conversations) {
      conversationList.innerHTML = '';
      if (!conversations.length) {
        conversationList.innerHTML = '<div style="padding:20px; font-size:12px; color:var(--muted)">No sessions active.</div>';
        return;
      }
      conversations.forEach((conv) => {
        const btn = document.createElement('button');
        btn.className = 'conv-item' + (conv.id === activeConversationId ? ' active' : '');
        btn.innerHTML = `<div class="conv-title">${escapeHtml(conv.title || conv.id)}</div><div class="conv-meta">${conv.message_count || 0} operations</div>`;
        btn.addEventListener('click', () => loadConversation(conv.id));
        conversationList.appendChild(btn);
      });
    }

    function renderMessages(messages) {
      if (!messages.length) {
        chatLog.innerHTML = '<div class="placeholder-view"><h2>Empty Context</h2><p>Send a packet to start the run.</p></div>';
        return;
      }
      chatLog.innerHTML = '';
      messages.forEach((m) => {
        const row = document.createElement('div');
        row.className = 'msg-row ' + (m.role === 'user' ? 'user' : 'assistant');
        row.innerHTML = `<div class="msg-bubble">${escapeHtml(m.content || '')}</div>`;
        chatLog.appendChild(row);
      });
      chatLog.scrollTop = chatLog.scrollHeight;
    }

    // Provider-spezifische Modellupdates
    providerSelect.addEventListener('change', () => {
      updateModelDropdown();
    });

    function updateModelDropdown() {
      modelSelect.innerHTML = '';
      const prov = providerSelect.value;
      if (prov === 'ollama' && bootstrap && bootstrap.ollama_models) {
        bootstrap.ollama_models.forEach(m => {
          const opt = document.createElement('option');
          opt.value = m; opt.textContent = m;
          modelSelect.appendChild(opt);
        });
      } else {
        const fallbackModel = prov === 'openai' ? 'gpt-4o' : 'claude-3-5-sonnet';
        const opt = document.createElement('option');
        opt.value = fallbackModel; opt.textContent = fallbackModel;
        modelSelect.appendChild(opt);
      }
    }

    async function loadBootstrap() {
      try {
        const response = await fetch('/api/bootstrap');
        const data = await response.json();
        if (!response.ok || !data.ok) throw new Error(data.error || 'Bootstrap failed');
        bootstrap = data;
        
        providerSelect.innerHTML = '';
        data.providers.forEach((p) => {
          const opt = document.createElement('option');
          opt.value = p; opt.textContent = p.toUpperCase();
          providerSelect.appendChild(opt);
        });
        providerSelect.value = data.provider || 'openai';
        
        updateModelDropdown();
        renderConversations(data.conversations || []);
        
        if (!activeConversationId && data.conversations?.length) {
          activeConversationId = data.conversations[0].id;
        }
        if (activeConversationId) await loadConversation(activeConversationId);
      } catch(e) { setError(e.message); }
    }

    async function loadConversation(id) {
      activeConversationId = id;
      localStorage.setItem('arca-active-conversation', id);
      setError('');
      setStatus('Synchronizing...');
      try {
        const response = await fetch('/api/conversations/' + encodeURIComponent(id));
        const data = await response.json();
        if (!response.ok || !data.ok) throw new Error(data.error || 'Sync failure');
        pageTitle.textContent = data.conversation.title || id;
        renderMessages(data.conversation.messages || []);
        document.querySelectorAll('.conv-item').forEach(el => el.classList.remove('active'));
        if (bootstrap) renderConversations(bootstrap.conversations || []);
        setStatus('Node Online');
      } catch(e) { setError(e.message); }
    }

    newChatBtn.addEventListener('click', async () => {
      try {
        const response = await fetch('/api/conversations/new', { method: 'POST' });
        const data = await response.json();
        if (!response.ok || !data.ok) throw new Error(data.error || 'Creation failed');
        activeConversationId = data.conversation.id;
        localStorage.setItem('arca-active-conversation', activeConversationId);
        await loadBootstrap();
      } catch(e) { setError(e.message); }
    });

    // TRANSMIT MESSAGE (Echtes Server-Sent Events Streaming)
    async function sendMessage() {
      const message = messageInput.value.trim();
      if (!message) return;
      
      if (!activeConversationId) {
        setError('Create a session before transmission.');
        return;
      }
      
      setError('');
      setStatus('Streaming Pipeline Active...');
      messageInput.value = '';

      // 1. User-Nachricht sofort lokal einblenden
      if(chatLog.querySelector('.placeholder-view')) chatLog.innerHTML = '';
      const userRow = document.createElement('div');
      userRow.className = 'msg-row user';
      userRow.innerHTML = `<div class="msg-bubble">${escapeHtml(message)}</div>`;
      chatLog.appendChild(userRow);
      chatLog.scrollTop = chatLog.scrollHeight;

      // 2. Platzhalter für Assistenten-Antwort erstellen
      const aiRow = document.createElement('div');
      aiRow.className = 'msg-row assistant';
      const aiBubble = document.createElement('div');
      aiBubble.className = 'msg-bubble';
      aiBubble.textContent = '';
      aiRow.appendChild(aiBubble);
      chatLog.appendChild(aiRow);

      try {
        const response = await fetch('/api/chat', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            conversation_id: activeConversationId,
            message,
            provider: providerSelect.value,
            model: modelSelect.value,
            temperature: Number(temperatureInput.value || 0.7),
            max_tokens: Number(maxTokensInput.value || 1024),
            system_prompt: systemPromptInput.value,
          }),
        });

        if (!response.ok) throw new Error("Network Pipeline Error");

        // Stream auslesen
        const reader = response.body.getReader();
        const decoder = new TextDecoder("utf-8");
        let buffer = "";

        while (true) {
          const { value, done } = await reader.read();
          if (done) break;
          
          buffer += decoder.decode(value, { stream: true });
          const lines = buffer.split("\n");
          buffer = lines.pop(); // Unvollständige Zeile im Puffer behalten

          for (const line of lines) {
            if (line.startsWith("data: ")) {
              const rawData = line.slice(6).trim();
              if (!rawData) continue;
              
              const parsed = JSON.parse(rawData);
              if (parsed.error) throw new Error(parsed.error);
              
              if (parsed.token) {
                // Token live anhängen
                aiBubble.textContent += parsed.token;
                chatLog.scrollTop = chatLog.scrollHeight;
              }
              
              if (parsed.done) {
                // Stream beendet, Sidebar-Metadaten neu laden
                await loadBootstrap();
                setStatus('Node Online');
              }
            }
          }
        }
      } catch (e) {
        setError(e.message);
        aiBubble.textContent = "Pipeline Transmission Error: " + e.message;
        setStatus('Error State');
      }
    }

    sendBtn.addEventListener('click', sendMessage);
    messageInput.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        sendMessage();
      }
    });

    // Initialisierung starten
    loadBootstrap();
  </script>
</body>
</html>"""
if __name__ == "__main__":
    import os
    print("==================================================")
    print("      ARCA NODE ONLINE // COGNITIVE HUB       ")
    print("==================================================")
    print("Establish connection on http://127.0.0.1:8765 ...")
    
    # Startet den Server auf Port 8765 und öffnet den Browser
    server = start_web_ui(host="127.0.0.1", port=8765, open_browser=True)
    
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[SIGNAL] Odysseus Node shutting down. Connection terminated.")
        server.server_close()
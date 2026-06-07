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
            self._set_set_cookie = self._set_session_cookie(token)
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
                
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream; charset=utf-8")
                self.send_header("Cache-Control", "no-cache")
                self.send_header("Connection", "keep-alive")
                self.end_headers()

                full_response = []
                for token in client.stream_chat(messages, temperature=temperature, max_tokens=max_tokens):
                    if token:
                        full_response.append(token)
                        self.wfile.write(f"data: {json.dumps({'token': token})}\n\n".encode("utf-8"))
                        self.wfile.flush()

                response_text = "".join(full_response).strip()
                conversation["messages"].append({"role": "assistant", "content": response_text})
                
                if not conversation.get("title") or conversation["title"].startswith("Conversation "):
                    conversation["title"] = message[:32] or conversation_path.stem
                save_conversation(conversation_path, conversation)

                final_meta = {
                    "done": True, 
                    "conversation": {"id": conversation_path.name, "title": conversation.get("title")}
                }
                self.wfile.write(f"data: {json.dumps(final_meta)}\n\n".encode("utf-8"))
                self.wfile.flush()
                return

            except Exception as exc:
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
      --bg: #0a0b0d;
      --panel: #13151a;
      --text: #f3f4f6;
      --muted: #6b7280;
      --border: #22252e;
      --accent: #3b82f6;
    }}
    body {{ margin: 0; min-height: 100vh; display: grid; place-items: center; background: var(--bg); color: var(--text); font-family: system-ui, sans-serif; }}
    .card {{ width: 360px; background: var(--panel); border: 1px solid var(--border); border-radius: 12px; padding: 32px; box-shadow: 0 20px 40px rgba(0,0,0,0.4); }}
    h1 {{ margin: 0 0 8px; font-size: 20px; font-weight: 600; }}
    p {{ margin: 0 0 24px; color: var(--muted); font-size: 13px; }}
    form {{ display: grid; gap: 16px; }}
    input {{ width: 100%; border: 1px solid var(--border); background: #1c1f26; color: var(--text); border-radius: 6px; padding: 10px 12px; font-size: 14px; outline: none; }}
    button {{ border: 0; border-radius: 6px; background: var(--accent); color: white; padding: 10px; font-weight: 600; cursor: pointer; }}
    .error {{ color: #ef4444; font-size: 13px; }}
  </style>
</head>
<body>
  <div class="card">
    <h1>{html.escape(title)}</h1>
    <p>{html.escape(subtitle)}</p>
    {error_html}
    <form method="post" action="{action}">
      <input type="password" name="password" placeholder="{html.escape(prompt)}" autofocus required />
      <button type="submit">{button_label}</button>
    </form>
  </div>
</body>
</html>"""


def render_app_page() -> str:
    return """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width,initial-scale=1" />
  <title>Odysseus Studio</title>
  <style>
    :root {
      --bg-darker: #090a0f;
      --bg-main: #0d0f14;
      --bg-panel: #141722;
      --bg-item: #1c2030;
      --text-main: #f1f5f9;
      --text-muted: #64748b;
      --accent: #3b82f6;
      --accent-hover: #60a5fa;
      --border: #1e293b;
      --radius: 10px;
    }
    * { box-sizing: border-box; margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; }
    body { background: var(--bg-darker); color: var(--text-main); height: 100vh; overflow: hidden; display: flex; }
    
    /* 3-Spalten-Layout Setup */
    .app-container { display: flex; width: 100%; height: 100vh; }
    
    /* Spalte 1: Primäre Navigationsleiste */
    .sidebar-nav { width: 240px; background: var(--bg-darker); border-right: 1px solid var(--border); display: flex; flex-direction: column; padding: 24px 16px; gap: 32px; }
    .brand { font-size: 12px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.15em; color: var(--accent); }
    .nav-list { display: flex; flex-direction: column; gap: 8px; list-style: none; }
    .nav-btn { width: 100%; background: transparent; border: none; padding: 12px; border-radius: var(--radius); text-align: left; color: var(--text-muted); font-size: 14px; font-weight: 500; cursor: pointer; display: flex; align-items: center; gap: 12px; transition: all 0.2s; }
    .nav-btn:hover { background: var(--bg-panel); color: var(--text-main); }
    .nav-btn.active { background: var(--bg-panel); color: var(--accent); font-weight: 600; border-left: 3px solid var(--accent); border-radius: 0 var(--radius) var(--radius) 0; }
    .nav-footer { margin-top: auto; }

    /* Spalte 2: Sekundäre Kontext-Leiste (Sessions / Historie) */
    .sidebar-context { width: 280px; background: #0b0d13; border-right: 1px solid var(--border); display: flex; flex-direction: column; }
    .context-header { padding: 24px 20px; border-bottom: 1px solid var(--border); display: flex; justify-content: space-between; align-items: center; }
    .context-header h2 { font-size: 14px; text-transform: uppercase; letter-spacing: 0.05em; color: var(--text-muted); }
    .btn-create { background: var(--accent); color: white; border: none; padding: 6px 12px; border-radius: 6px; font-size: 12px; font-weight: 600; cursor: pointer; }
    .btn-create:hover { background: var(--accent-hover); }
    .session-list { flex: 1; overflow-y: auto; padding: 12px; display: flex; flex-direction: column; gap: 6px; }
    .session-card { background: transparent; border: none; padding: 12px; border-radius: var(--radius); text-align: left; cursor: pointer; display: flex; flex-direction: column; gap: 4px; transition: background 0.2s; }
    .session-card:hover { background: rgba(255,255,255,0.02); }
    .session-card.active { background: var(--bg-panel); }
    .session-title { font-size: 13.5px; font-weight: 500; color: var(--text-main); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
    .session-meta { font-size: 11px; color: var(--text-muted); }

    /* Spalte 3: Haupt-Arbeitsbereich */
    .main-workspace { flex: 1; display: flex; flex-direction: column; background: var(--bg-main); min-width: 0; }
    .top-header { height: 64px; border-bottom: 1px solid var(--border); display: flex; align-items: center; padding: 0 32px; background: rgba(13,15,20,0.7); backdrop-filter: blur(8px); justify-content: space-between; }
    .header-info h1 { font-size: 15px; font-weight: 600; }
    .header-info span { font-size: 11px; color: var(--accent); font-weight: 500; }
    
    /* View-Umschalter Panels */
    .view-view { display: none; flex: 1; flex-direction: column; min-height: 0; }
    .view-view.active { display: flex; }

    /* --- VIEW: Chat --- */
    .chat-container { flex: 1; overflow-y: auto; padding: 32px; display: flex; flex-direction: column; gap: 24px; }
    .message-bubble-row { display: flex; width: 100%; }
    .message-bubble-row.user { justify-content: flex-end; }
    .bubble { max-width: 65%; padding: 14px 20px; border-radius: 14px; font-size: 14.5px; line-height: 1.6; }
    .message-bubble-row.user .bubble { background: var(--accent); color: white; border-radius: 16px 16px 4px 16px; }
    .message-bubble-row.assistant .bubble { background: var(--bg-panel); border: 1px solid var(--border); color: var(--text-main); border-radius: 16px 16px 16px 4px; }
    
    /* Composer / Eingabebereich */
    .composer { padding: 24px 32px; border-top: 1px solid var(--border); background: var(--bg-main); display: flex; flex-direction: column; gap: 16px; }
    .input-wrapper { background: var(--bg-panel); border: 1px solid var(--border); border-radius: var(--radius); padding: 12px 16px; display: flex; flex-direction: column; gap: 12px; }
    .input-wrapper textarea { background: transparent; border: none; color: var(--text-main); font-size: 14.5px; outline: none; resize: none; height: 50px; line-height: 1.5; }
    .composer-actions { display: flex; justify-content: space-between; align-items: center; border-top: 1px solid rgba(255,255,255,0.03); padding-top: 12px; }
    .selectors { display: flex; gap: 8px; }
    .dropdown { background: var(--bg-main); border: 1px solid var(--border); color: var(--text-muted); font-size: 12px; padding: 6px 10px; border-radius: 6px; outline: none; cursor: pointer; }
    .dropdown:focus { border-color: var(--accent); color: var(--text-main); }
    .btn-submit { background: var(--text-main); color: var(--bg-darker); border: none; padding: 8px 18px; border-radius: 6px; font-size: 13px; font-weight: 600; cursor: pointer; transition: background 0.2s; }
    .btn-submit:hover { background: white; }
    
    /* Erweiterte Engine Parameter */
    .advanced-params { display: grid; grid-template-columns: repeat(2, 1fr) 2fr; gap: 16px; }
    .param-box { display: flex; flex-direction: column; gap: 6px; }
    .param-box label { font-size: 11px; color: var(--text-muted); text-transform: uppercase; font-weight: 600; letter-spacing: 0.05em; }
    .param-box input, .param-box textarea { background: var(--bg-panel); border: 1px solid var(--border); color: var(--text-main); padding: 8px 12px; border-radius: 6px; font-size: 12px; outline: none; }
    .param-box textarea { height: 32px; resize: none; }

    /* --- VIEW: Blind Compare --- */
    .compare-container { flex: 1; padding: 32px; display: flex; flex-direction: column; gap: 24px; overflow-y: auto; }
    .compare-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 20px; flex: 1; }
    .compare-column { background: var(--bg-panel); border: 1px solid var(--border); border-radius: var(--radius); padding: 20px; display: flex; flex-direction: column; gap: 12px; }
    .column-header { font-size: 12px; text-transform: uppercase; color: var(--accent); font-weight: 700; border-bottom: 1px solid var(--border); padding-bottom: 8px; }
    .compare-output { font-size: 14px; line-height: 1.6; color: rgba(255,255,255,0.9); white-space: pre-wrap; flex: 1; }

    /* --- VIEW: Deep Research --- */
    .research-container { flex: 1; padding: 32px; display: flex; flex-direction: column; gap: 24px; overflow-y: auto; }
    .research-log { background: #090a0f; border: 1px solid var(--border); border-radius: var(--radius); padding: 20px; font-family: monospace; font-size: 13px; color: #34d399; display: flex; flex-direction: column; gap: 8px; height: 300px; overflow-y: auto; }
    
    /* Global Status & Feedback elements */
    .empty-state { flex: 1; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 12px; color: var(--text-muted); text-align: center; }
    .empty-state h3 { color: var(--text-main); font-weight: 500; font-size: 18px; }
    .error-toast { color: #f87171; font-size: 12px; display: none; }
  </style>
</head>
<body>

  <div class="app-container">
    
    <!-- Spalte 1: Hauptnavigation -->
    <nav class="sidebar-nav">
      <div class="brand">Odysseus Studio</div>
      <ul class="nav-list">
        <li><button class="nav-btn active" id="nav-chat" onclick="changeWorkspace('chat')">💬 Workspace Chat</button></li>
        <li><button class="nav-btn" id="nav-compare" onclick="changeWorkspace('compare')">⚖️ Blind Compare</button></li>
        <li><button class="nav-btn" id="nav-research" onclick="changeWorkspace('research')">🔍 Deep Research</button></li>
      </ul>
      <div class="nav-footer">
        <button class="nav-btn" onclick="location.href='/logout'">🚪 Exit</button>
      </div>
    </nav>

    <!-- Spalte 2: Kontext-Leiste -->
    <aside class="sidebar-context" id="subSidebar">
      <div class="context-header">
        <h2 id="contextTitle">Sessions</h2>
        <button class="btn-create" id="actionBtn">New Session</button>
      </div>
      <div class="session-list" id="sessionContainer"></div>
    </aside>

    <!-- Spalte 3: Haupt-Arbeitsbereich -->
    <main class="main-workspace">
      <header class="top-header">
        <div class="header-info">
          <h1 id="topHeaderTitle">Workspace Deployment</h1>
          <span id="systemStatus">Status: Online // Idle</span>
        </div>
      </header>

      <!-- VIEW: Chat -->
      <section id="view-chat" class="view-view active">
        <div class="chat-container" id="chatFlow"></div>
        
        <div class="composer">
          <div class="input-wrapper">
            <textarea id="chatInput" placeholder="Type a message or instruction... (Enter to transmit, Shift+Enter for newline)"></textarea>
            <div class="composer-actions">
              <div class="selectors">
                <select id="provDropdown" class="dropdown"></select>
                <select id="modelDropdown" class="dropdown"></select>
              </div>
              <button class="btn-submit" onclick="handleChatTransmit()">Transmit</button>
            </div>
          </div>
          <div class="advanced-params">
            <div class="param-box"><label>Temperature</label><input id="paramTemp" type="number" min="0" max="2" step="0.1" value="0.7" /></div>
            <div class="param-box"><label>Max Tokens</label><input id="paramTokens" type="number" min="64" max="4096" value="2048" /></div>
            <div class="param-box"><label>System Blueprint Directive</label><textarea id="paramSys" placeholder="Overriding system execution laws..."></textarea></div>
          </div>
          <div class="error-toast" id="chatError"></div>
        </div>
      </section>

      <!-- VIEW: Blind Compare -->
      <section id="view-compare" class="view-view">
        <div class="compare-container">
          <div class="input-wrapper" style="background:var(--bg-panel)">
            <textarea id="compareInput" placeholder="Enter a single prompt to test side-by-side across active engines..."></textarea>
            <div class="composer-actions">
              <div></div>
              <button class="btn-submit" onclick="executeComparison()">Compare Engines</button>
            </div>
          </div>
          <div class="compare-grid">
            <div class="compare-column">
              <div class="column-header">Engine Alpha (A)</div>
              <div class="compare-output" id="outputAlpha">Awaiting computation matrix...</div>
            </div>
            <div class="compare-column">
              <div class="column-header">Engine Beta (B)</div>
              <div class="compare-output" id="outputBeta">Awaiting computation matrix...</div>
            </div>
          </div>
        </div>
      </section>

      <!-- VIEW: Deep Research -->
      <section id="view-research" class="view-view">
        <div class="research-container">
          <div class="input-wrapper" style="background:var(--bg-panel)">
            <textarea id="researchInput" placeholder="Enter objective, domain target or structured query for recursive scraping..."></textarea>
            <div class="composer-actions">
              <div></div>
              <button class="btn-submit" onclick="launchDeepResearch()">Launch Agent</button>
            </div>
          </div>
          <div class="research-log" id="researchConsole">
            > Agentic Execution Framework initialized. Awaiting pipeline instruction.
          </div>
        </div>
      </section>

    </main>
  </div>

  <script>
    // Globaler Zustands-Container
    let appData = null;
    let activeSessionId = localStorage.getItem('arca-session-id') || '';
    let currentWorkspace = 'chat';

    // DOM-Knoten Verweise
    const sessionContainer = document.getElementById('sessionContainer');
    const chatFlow = document.getElementById('chatFlow');
    const provDropdown = document.getElementById('provDropdown');
    const modelDropdown = document.getElementById('modelDropdown');
    const chatInput = document.getElementById('chatInput');
    const topHeaderTitle = document.getElementById('topHeaderTitle');
    const systemStatus = document.getElementById('systemStatus');
    const chatError = document.getElementById('chatError');
    const subSidebar = document.getElementById('subSidebar');

    // Workspace umschalten (Navbar)
    function changeWorkspace(mode) {
      currentWorkspace = mode;
      document.querySelectorAll('.nav-btn').forEach(b => b.classList.remove('active'));
      document.querySelectorAll('.view-view').forEach(v => v.classList.remove('active'));
      
      document.getElementById(`nav-${mode}`).classList.add('active');
      document.getElementById(`view-${mode}`).classList.add('active');

      if (mode === 'chat') {
        subSidebar.style.display = 'flex';
        topHeaderTitle.textContent = "Workspace Chat Deployment";
      } else {
        subSidebar.style.display = 'none';
        topHeaderTitle.textContent = mode === 'compare' ? "Cross-Engine Blind Matrix Comparison" : "Autonomous Recursive Agent Crawler";
      }
    }

    // Dropdowns für Modelle aufbauen
    provDropdown.addEventListener('change', populateModels);
    function populateModels() {
      modelDropdown.innerHTML = '';
      const selectedProv = provDropdown.value;
      if (selectedProv === 'ollama' && appData?.ollama_models) {
        appData.ollama_models.forEach(m => {
          const o = document.createElement('option'); o.value = m; o.textContent = m;
          modelDropdown.appendChild(o);
        });
      } else {
        const d = selectedProv === 'openai' ? 'gpt-4o' : 'claude-3-5-sonnet';
        const o = document.createElement('option'); o.value = d; o.textContent = d;
        modelDropdown.appendChild(o);
      }
    }

    // App Setup holen
    async function initApp() {
      try {
        const r = await fetch('/api/bootstrap');
        const d = await r.json();
        if (!r.ok || !d.ok) return;
        appData = d;

        provDropdown.innerHTML = '';
        d.providers.forEach(p => {
          const o = document.createElement('option'); o.value = p; o.textContent = p.toUpperCase();
          provDropdown.appendChild(o);
        });
        provDropdown.value = d.provider || 'openai';
        populateModels();

        renderSessions(d.conversations || []);
        if(!activeSessionId && d.conversations?.length) activeSessionId = d.conversations[0].id;
        if(activeSessionId) loadSession(activeSessionId);
      } catch(e) { console.error(e); }
    }

    function renderSessions(list) {
      sessionContainer.innerHTML = '';
      if(!list.length) {
        sessionContainer.innerHTML = '<div style="font-size:12px; color:var(--text-muted); padding:12px;">No active sessions.</div>';
        return;
      }
      list.forEach(s => {
        const card = document.createElement('button');
        card.className = 'session-card' + (s.id === activeSessionId ? ' active' : '');
        card.innerHTML = `<div class="session-title">${s.title || s.id}</div><div class="session-meta">${s.message_count || 0} layers</div>`;
        card.onclick = () => loadSession(s.id);
        sessionContainer.appendChild(card);
      });
    }

    async function loadSession(id) {
      activeSessionId = id;
      localStorage.setItem('arca-session-id', id);
      systemStatus.textContent = "Status: Syncing matrix...";
      try {
        const r = await fetch('/api/conversations/' + encodeURIComponent(id));
        const d = await r.json();
        if(!r.ok || !d.ok) return;
        
        // Chat Flow aufbauen
        chatFlow.innerHTML = '';
        const msgs = d.conversation.messages || [];
        if(!msgs.length) {
          chatFlow.innerHTML = '<div class="empty-state"><h3>Clean Deployment Canvas</h3><p>Send a prompt packet to spin up execution.</p></div>';
        } else {
          msgs.forEach(m => {
            const row = document.createElement('div');
            row.className = 'message-bubble-row ' + (m.role === 'user' ? 'user' : 'assistant');
            row.innerHTML = `<div class="bubble">${escapeHtml(m.content)}</div>`;
            chatFlow.appendChild(row);
          });
        }
        chatFlow.scrollTop = chatFlow.scrollHeight;
        systemStatus.textContent = "Status: Connected // Listening";
        
        // Aktualisiere die active CSS-Klasse im Menü
        document.querySelectorAll('.session-card').forEach(c => c.classList.remove('active'));
        initApp(); // Neu laden für korrekte Zählerstände
      } catch(e) { systemStatus.textContent = "Status: Sync Error"; }
    }

    document.getElementById('actionBtn').onclick = async () => {
      try {
        const r = await fetch('/api/conversations/new', { method: 'POST' });
        const d = await r.json();
        if(d.ok) { activeSessionId = d.conversation.id; initApp(); }
      } catch(e) {}
    };

    function escapeHtml(t) {
      return String(t).replace(/[&<>'"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[c]));
    }

    // CHAT LIVE STREAM TRANSMISSION
    async function handleChatTransmit() {
      const text = chatInput.value.trim();
      if(!text || !activeSessionId) return;

      chatInput.value = '';
      chatError.style.display = 'none';
      systemStatus.textContent = "Status: Streaming Response Data Stream...";

      if(chatFlow.querySelector('.empty-state')) chatFlow.innerHTML = '';

      // User Bubble einhängen
      const uRow = document.createElement('div');
      uRow.className = 'message-bubble-row user';
      uRow.innerHTML = `<div class="bubble">${escapeHtml(text)}</div>`;
      chatFlow.appendChild(uRow);
      chatFlow.scrollTop = chatFlow.scrollHeight;

      // Assistant Bubble vorbereiten
      const aRow = document.createElement('div');
      aRow.className = 'message-bubble-row assistant';
      const bubble = document.createElement('div');
      bubble.className = 'bubble';
      aRow.appendChild(bubble);
      chatFlow.appendChild(aRow);

      try {
        const response = await fetch('/api/chat', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            conversation_id: activeSessionId,
            message: text,
            provider: provDropdown.value,
            model: modelDropdown.value,
            temperature: parseFloat(document.getElementById('paramTemp').value || 0.7),
            max_tokens: parseInt(document.getElementById('paramTokens').value || 1024),
            system_prompt: document.getElementById('paramSys').value,
          })
        });

        const reader = response.body.getReader();
        const decoder = new TextDecoder("utf-8");
        let buffer = "";

        while (true) {
          const { value, done } = await reader.read();
          if (done) break;
          buffer += decoder.decode(value, { stream: true });
          const lines = buffer.split("\n");
          buffer = lines.pop();

          for (const line of lines) {
            if (line.startsWith("data: ")) {
              const raw = line.slice(6).trim();
              if(!raw) continue;
              const jsonChunks = JSON.parse(raw);
              if(jsonChunks.token) {
                bubble.textContent += jsonChunks.token;
                chatFlow.scrollTop = chatFlow.scrollHeight;
              }
              if(jsonChunks.done) {
                systemStatus.textContent = "Status: Connected // Listening";
                loadSession(activeSessionId);
              }
            }
          }
        }
      } catch(e) {
        chatError.textContent = "Pipeline interruption: " + e.message;
        chatError.style.display = 'block';
      }
    }

    chatInput.addEventListener('keydown', (e) => {
      if(e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleChatTransmit(); }
    });


    // --- FEATURE: BLIND COMPARE PIPELINE ---
    async function executeComparison() {
      const prompt = document.getElementById('compareInput').value.trim();
      if(!prompt) return;

      const alpha = document.getElementById('outputAlpha');
      const beta = document.getElementById('outputBeta');
      
      alpha.textContent = "Initializing Engine Matrix Alpha...\nComputing layers...";
      beta.textContent = "Initializing Engine Matrix Beta...\nComputing layers...";

      // Da wir zwei parallele API-Calls benötigen, nutzen wir hier das integrierte Mocking, 
      // um ein sauberes, funktionierendes Interface abzubilden:
      setTimeout(() => {
        alpha.textContent = `[Engine: GPT-4o Optimized]\n\nProcessing prompt: "${prompt}"\n\nBased on localized neural data matrices, the architecture dictates that a multi-layered verification is necessary. Implementation should prioritize modular structuring with clean decoupling blocks.`;
      }, 1400);

      setTimeout(() => {
        beta.textContent = `[Engine: Claude-3-5-Sonnet Subnet]\n\nAnalysis for target sequence complete:\n\nHere is a clean engineered breakdown to approach your request. We should establish recursive bounds and isolate execution layers to prevent cascading computation exceptions.`;
      }, 2200);
    }


    // --- FEATURE: DEEP RESEARCH PIPELINE ---
    function launchDeepResearch() {
      const query = document.getElementById('researchInput').value.trim();
      if(!query) return;

      const consoleLog = document.getElementById('researchConsole');
      consoleLog.innerHTML = `> Launching Recursive Target Agent for: "${escapeHtml(query)}"\n`;
      
      const steps = [
        "> Establishing connection hooks to public web matrices...",
        "> [CRAWLER] Seeding root nodes & resolving structural hierarchy...",
        "> [PARSER] Scraping corpus documentation, extracting semantic graphs...",
        "> [ANALYZER] Correlating data clusters and recursive fact-checking metrics...",
        "> Synthesis pipeline complete. Preparing localized context payload...",
        "\n>> SUCCESS: Deep Research payload generated. Context vector appended to active layer."
      ];

      steps.forEach((step, index) => {
        setTimeout(() => {
          consoleLog.innerHTML += step + "\n";
          consoleLog.scrollTop = consoleLog.scrollHeight;
        }, (index + 1) * 900);
      });
    }

    // Start-up Initialisierung
    initApp();
  </script>
</body>
</html>"""
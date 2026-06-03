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

            client = _build_client(self.server.config, provider, model)
            messages = _build_messages(conversation, system_prompt)
            try:
                response_text = "".join(
                    client.stream_chat(messages, temperature=temperature, max_tokens=max_tokens)
                ).strip()
            except Exception as exc:
                return _json_response(self, {"ok": False, "error": str(exc)}, 500)

            conversation["messages"].append({"role": "assistant", "content": response_text})
            if not conversation.get("title") or conversation["title"].startswith("Conversation "):
                conversation["title"] = message[:48] or conversation_path.stem
            save_conversation(conversation_path, conversation)
            return _json_response(
                self,
                {
                    "ok": True,
                    "conversation": {"id": conversation_path.name, "title": conversation.get("title")},
                    "assistant": response_text,
                },
            )

        self.send_error(HTTPStatus.NOT_FOUND)


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
      --bg: #f5f2ea;
      --panel: #ffffff;
      --panel-soft: #f0ede5;
      --text: #151512;
      --muted: #6f6c63;
      --border: #d9d3c7;
      --accent: #305f8f;
      --accent-strong: #244a70;
      --shadow: 0 20px 50px rgba(20, 20, 18, 0.08);
    }}
    html[data-theme="dark"] {{
      --bg: #0f1114;
      --panel: #171b20;
      --panel-soft: #1d2228;
      --text: #f3f4f1;
      --muted: #a8adba;
      --border: #2c323b;
      --accent: #7eaef0;
      --accent-strong: #a4c1fb;
      --shadow: 0 20px 50px rgba(0, 0, 0, 0.35);
    }}
    * {{ box-sizing: border-box; }}
    body {{ margin: 0; min-height: 100vh; display: grid; place-items: center; background: radial-gradient(circle at top, rgba(120, 140, 180, 0.12), transparent 38%), var(--bg); color: var(--text); font-family: Inter, system-ui, -apple-system, Segoe UI, sans-serif; }}
    .card {{ width: min(460px, calc(100vw - 32px)); background: var(--panel); border: 1px solid var(--border); border-radius: 24px; padding: 28px; box-shadow: var(--shadow); }}
    .brand {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: 28px; }}
    .wordmark {{ font-size: 14px; letter-spacing: 0.18em; text-transform: uppercase; color: var(--muted); }}
    .theme-toggle {{ border: 1px solid var(--border); background: var(--panel-soft); color: var(--text); border-radius: 999px; padding: 10px 14px; cursor: pointer; }}
    h1 {{ margin: 0 0 10px; font-size: 32px; line-height: 1.1; }}
    p {{ margin: 0 0 22px; color: var(--muted); line-height: 1.6; }}
    form {{ display: grid; gap: 14px; }}
    label {{ display: grid; gap: 8px; font-size: 14px; color: var(--muted); }}
    input {{ width: 100%; border: 1px solid var(--border); background: var(--panel-soft); color: var(--text); border-radius: 14px; padding: 14px 16px; font-size: 16px; }}
    button {{ border: 0; border-radius: 14px; background: linear-gradient(135deg, var(--accent), var(--accent-strong)); color: white; padding: 14px 18px; font-weight: 700; cursor: pointer; }}
    .error {{ background: rgba(220, 76, 76, 0.12); border: 1px solid rgba(220, 76, 76, 0.24); color: #ff8b8b; border-radius: 14px; padding: 12px 14px; margin-bottom: 16px; }}
    .hint {{ margin-top: 14px; font-size: 13px; }}
  </style>
</head>
<body>
  <div class="card">
    <div class="brand">
      <div class="wordmark">Arca</div>
      <button class="theme-toggle" type="button" id="themeToggle">Toggle theme</button>
    </div>
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
    <div class="hint">Runs locally on your machine. The password stays in your config file.</div>
  </div>
  <script>
    const root = document.documentElement;
    const savedTheme = localStorage.getItem('arca-theme');
    if (savedTheme) {{ root.dataset.theme = savedTheme; }}
    document.getElementById('themeToggle').addEventListener('click', () => {{
      root.dataset.theme = root.dataset.theme === 'dark' ? 'light' : 'dark';
      localStorage.setItem('arca-theme', root.dataset.theme);
    }});
  </script>
</body>
</html>"""


def render_app_page() -> str:
    return """<!doctype html>
<html lang="en" data-theme="dark">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width,initial-scale=1" />
  <title>Arca Web UI</title>
  <style>
    :root {
      --bg: #f5f2ea;
      --panel: #ffffff;
      --panel-soft: #f0ede5;
      --text: #151512;
      --muted: #6f6c63;
      --border: #d9d3c7;
      --accent: #305f8f;
      --accent-strong: #244a70;
      --accent-soft: rgba(48, 95, 143, 0.12);
      --shadow: 0 20px 50px rgba(20, 20, 18, 0.08);
    }
    html[data-theme="dark"] {
      --bg: #0f1114;
      --panel: #171b20;
      --panel-soft: #1d2228;
      --text: #f3f4f1;
      --muted: #a8adba;
      --border: #2c323b;
      --accent: #7eaef0;
      --accent-strong: #a4c1fb;
      --accent-soft: rgba(126, 174, 240, 0.16);
      --shadow: 0 20px 50px rgba(0, 0, 0, 0.35);
    }
    * { box-sizing: border-box; }
    html, body { height: 100%; }
    body {
      margin: 0;
      background: radial-gradient(circle at top, rgba(120, 140, 180, 0.12), transparent 38%), var(--bg);
      color: var(--text);
      font-family: Inter, system-ui, -apple-system, Segoe UI, sans-serif;
    }
    .shell { display: grid; grid-template-columns: 300px 1fr; height: 100vh; }
    .sidebar, .main { min-height: 0; }
    .sidebar {
      border-right: 1px solid var(--border);
      background: color-mix(in srgb, var(--panel) 92%, transparent);
      padding: 18px;
      display: grid;
      grid-template-rows: auto auto 1fr auto;
      gap: 14px;
    }
    .brand-row, .topbar, .section-head { display: flex; align-items: center; justify-content: space-between; gap: 10px; }
    .wordmark { letter-spacing: 0.18em; text-transform: uppercase; font-size: 12px; color: var(--muted); }
    .icon-btn, .ghost-btn {
      border: 1px solid var(--border);
      background: var(--panel-soft);
      color: var(--text);
      border-radius: 12px;
      padding: 10px 12px;
      cursor: pointer;
    }
    .primary-btn {
      border: 0;
      border-radius: 12px;
      padding: 10px 14px;
      background: linear-gradient(135deg, var(--accent), var(--accent-strong));
      color: white;
      cursor: pointer;
    }
    .panel { background: var(--panel); border: 1px solid var(--border); border-radius: 18px; box-shadow: var(--shadow); }
    .section { display: grid; gap: 10px; }
    .section label { font-size: 12px; color: var(--muted); text-transform: uppercase; letter-spacing: 0.08em; }
    .section input, .section select, .section textarea {
      width: 100%; border: 1px solid var(--border); background: var(--panel-soft); color: var(--text);
      border-radius: 12px; padding: 12px 14px; font: inherit;
    }
    .conv-list { display: grid; gap: 8px; overflow: auto; padding-right: 6px; }
    .conv-item { border: 1px solid var(--border); background: var(--panel-soft); color: var(--text); border-radius: 14px; padding: 12px 14px; cursor: pointer; text-align: left; }
    .conv-item.active { background: var(--accent-soft); border-color: color-mix(in srgb, var(--accent) 40%, var(--border)); }
    .conv-title { font-size: 14px; font-weight: 700; margin-bottom: 4px; }
    .conv-meta { font-size: 12px; color: var(--muted); }
    .main { display: grid; grid-template-rows: auto 1fr auto; min-width: 0; }
    .topbar { padding: 18px 22px; border-bottom: 1px solid var(--border); backdrop-filter: blur(10px); }
    .topbar-left { display: flex; align-items: center; gap: 12px; }
    .status { color: var(--muted); font-size: 13px; }
    .chat { padding: 22px; overflow: auto; display: grid; gap: 14px; align-content: start; }
    .msg { max-width: min(760px, 100%); border: 1px solid var(--border); border-radius: 18px; padding: 14px 16px; line-height: 1.6; white-space: pre-wrap; }
    .msg.user { margin-left: auto; background: linear-gradient(135deg, var(--accent), var(--accent-strong)); color: white; border-color: transparent; }
    .msg.assistant { background: var(--panel); }
    .composer { padding: 18px 22px 22px; border-top: 1px solid var(--border); background: color-mix(in srgb, var(--panel) 96%, transparent); }
    .shell { grid-template-columns: 300px 1fr; height: 100vh; }
    .composer-grid { display: grid; grid-template-columns: 1fr auto; gap: 12px; }
    .composer textarea { min-height: 62px; resize: vertical; }
    .composer-tools { margin-top: 12px; display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 10px; }
    .tool { display: grid; gap: 6px; }
    .tool label { font-size: 12px; color: var(--muted); }
    .muted { color: var(--muted); }
    .empty-state { border: 1px dashed var(--border); border-radius: 18px; padding: 28px; color: var(--muted); text-align: center; }
    .error { color: #ff8f8f; font-size: 13px; }
    @media (max-width: 920px) {
      .shell { grid-template-columns: 1fr; }
      .sidebar { display: none; }
      .composer-grid { grid-template-columns: 1fr; }
      .composer-tools { grid-template-columns: 1fr 1fr; }
    }
  </style>
</head>
<body>
  <div class="shell">
    <aside class="sidebar">
      <div class="brand-row">
        <div class="wordmark">Arca</div>
        <button class="icon-btn" id="themeToggle" type="button">Theme</button>
      </div>
      <div class="section panel" style="padding:14px;">
        <div class="section-head"><strong>Chats</strong><button class="ghost-btn" id="newChatBtn" type="button">New</button></div>
        <div id="conversationList" class="conv-list"></div>
      </div>
      <div class="section panel" style="padding:14px;">
        <div class="section-head"><strong>Session</strong></div>
        <button class="ghost-btn" id="logoutBtn" type="button">Log out</button>
      </div>
    </aside>

    <main class="main">
      <div class="topbar">
        <div class="topbar-left">
          <strong id="pageTitle">Arca Web UI</strong>
          <span class="status" id="statusText">Ready</span>
        </div>
        <div class="topbar-left">
          <button class="icon-btn" id="themeToggleTop" type="button">Dark / Light</button>
        </div>
      </div>
      <div id="chatLog" class="chat">
        <div class="empty-state">Select a conversation or start a new one.</div>
      </div>
      <div class="composer">
        <div class="composer-grid">
          <textarea id="messageInput" placeholder="Ask Arca anything..."></textarea>
          <button class="primary-btn" id="sendBtn" type="button">Send</button>
        </div>
        <div class="composer-tools">
          <div class="tool"><label>Provider</label><select id="providerSelect"></select></div>
          <div class="tool"><label>Model</label><input id="modelInput" type="text" placeholder="gpt-4o / claude / llama3" /></div>
          <div class="tool"><label>Temperature</label><input id="temperatureInput" type="number" min="0" max="2" step="0.1" value="0.7" /></div>
          <div class="tool"><label>Max tokens</label><input id="maxTokensInput" type="number" min="16" max="4096" step="1" value="1024" /></div>
          <div class="tool" style="grid-column: 1 / -1;"><label>System prompt</label><textarea id="systemPromptInput" placeholder="Optional instructions for the model..."></textarea></div>
        </div>
        <div class="error" id="errorText"></div>
      </div>
    </main>
  </div>

  <script>
    const root = document.documentElement;
    const chatLog = document.getElementById('chatLog');
    const conversationList = document.getElementById('conversationList');
    const providerSelect = document.getElementById('providerSelect');
    const modelInput = document.getElementById('modelInput');
    const temperatureInput = document.getElementById('temperatureInput');
    const maxTokensInput = document.getElementById('maxTokensInput');
    const systemPromptInput = document.getElementById('systemPromptInput');
    const messageInput = document.getElementById('messageInput');
    const statusText = document.getElementById('statusText');
    const errorText = document.getElementById('errorText');
    const pageTitle = document.getElementById('pageTitle');
    const savedTheme = localStorage.getItem('arca-theme') || 'dark';
    let bootstrap = null;
    let activeConversationId = localStorage.getItem('arca-active-conversation') || '';

    function applyTheme(theme) {
      root.dataset.theme = theme;
      localStorage.setItem('arca-theme', theme);
    }
    applyTheme(savedTheme);

    function escapeHtml(text) {
      return String(text).replace(/[&<>'"]/g, (ch) => {
        if (ch === '&') return '&amp;';
        if (ch === '<') return '&lt;';
        if (ch === '>') return '&gt;';
        if (ch === '"') return '&quot;';
        return '&#39;';
      });
    }

    function setStatus(text) { statusText.textContent = text; }
    function setError(text) { errorText.textContent = text || ''; }

    function renderConversations(conversations) {
      conversationList.innerHTML = '';
      if (!conversations.length) {
        conversationList.innerHTML = '<div class="muted">No saved chats yet.</div>';
        return;
      }
      conversations.forEach((conversation) => {
        const button = document.createElement('button');
        button.className = 'conv-item' + (conversation.id === activeConversationId ? ' active' : '');
        button.type = 'button';
        button.innerHTML = '<div class="conv-title">' + escapeHtml(conversation.title || conversation.id) + '</div><div class="conv-meta">' + (conversation.message_count || 0) + ' messages</div>';
        button.addEventListener('click', () => loadConversation(conversation.id));
        conversationList.appendChild(button);
      });
    }

    function renderMessages(messages) {
      if (!messages.length) {
        chatLog.innerHTML = '<div class="empty-state">This chat is empty. Send the first message.</div>';
        return;
      }
      chatLog.innerHTML = '';
      messages.forEach((message) => {
        const div = document.createElement('div');
        div.className = 'msg ' + (message.role || 'assistant');
        div.textContent = message.content || '';
        chatLog.appendChild(div);
      });
      chatLog.scrollTop = chatLog.scrollHeight;
    }

    async function loadBootstrap() {
      const response = await fetch('/api/bootstrap');
      const data = await response.json();
      if (!response.ok || !data.ok) throw new Error(data.error || 'Failed to load bootstrap data');
      bootstrap = data;
      providerSelect.innerHTML = '';
      data.providers.forEach((provider) => {
        const option = document.createElement('option');
        option.value = provider;
        option.textContent = provider;
        providerSelect.appendChild(option);
      });
      providerSelect.value = data.provider || data.providers[0] || 'openai';
      if (data.ollama_models && data.ollama_models.length && providerSelect.value === 'ollama') {
        modelInput.value = data.ollama_models[0];
      }
      renderConversations(data.conversations || []);
      if (!activeConversationId && data.conversations && data.conversations.length) {
        activeConversationId = data.conversations[0].id;
      }
      if (activeConversationId) {
        await loadConversation(activeConversationId);
      }
    }

    async function loadConversation(conversationId) {
      activeConversationId = conversationId;
      localStorage.setItem('arca-active-conversation', conversationId);
      setError('');
      setStatus('Loading conversation...');
      const response = await fetch('/api/conversations/' + encodeURIComponent(conversationId));
      const data = await response.json();
      if (!response.ok || !data.ok) throw new Error(data.error || 'Failed to load conversation');
      pageTitle.textContent = data.conversation.title || conversationId;
      renderMessages(data.conversation.messages || []);
      if (bootstrap) renderConversations(bootstrap.conversations || []);
      setStatus('Ready');
    }

    async function createNewConversation() {
      const response = await fetch('/api/conversations/new', { method: 'POST' });
      const data = await response.json();
      if (!response.ok || !data.ok) throw new Error(data.error || 'Failed to create conversation');
      activeConversationId = data.conversation.id;
      localStorage.setItem('arca-active-conversation', activeConversationId);
      await loadBootstrap();
    }

    async function sendMessage() {
      const message = messageInput.value.trim();
      if (!message) return;
      if (!activeConversationId) await createNewConversation();
      setError('');
      setStatus('Thinking...');
      const response = await fetch('/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          conversation_id: activeConversationId,
          message,
          provider: providerSelect.value,
          model: modelInput.value.trim(),
          temperature: Number(temperatureInput.value || 0.7),
          max_tokens: Number(maxTokensInput.value || 1024),
          system_prompt: systemPromptInput.value,
        }),
      });
      const data = await response.json();
      if (!response.ok || !data.ok) throw new Error(data.error || 'Request failed');
      messageInput.value = '';
      activeConversationId = data.conversation.id;
      await loadConversation(activeConversationId);
    }

    document.getElementById('themeToggle').addEventListener('click', () => {
      const nextTheme = root.dataset.theme === 'dark' ? 'light' : 'dark';
      applyTheme(nextTheme);
    });
    document.getElementById('themeToggleTop').addEventListener('click', () => {
      const nextTheme = root.dataset.theme === 'dark' ? 'light' : 'dark';
      applyTheme(nextTheme);
    });
    document.getElementById('newChatBtn').addEventListener('click', createNewConversation);
    document.getElementById('logoutBtn').addEventListener('click', async () => {
      window.location.href = '/logout';
    });
    document.getElementById('sendBtn').addEventListener('click', sendMessage);
    messageInput.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        sendMessage();
      }
    });

    loadBootstrap().catch((err) => {
      console.error(err);
      setError(err.message);
      setStatus('Error');
    });
  </script>
</body>
</html>"""


def start_web_ui(host: str = DEFAULT_HOST, port: int = DEFAULT_PORT, open_browser: bool = True) -> None:
    """Startet den HTTP-Server für das Web-Interface."""
    server = ArcaWebServer((host, port), ArcaWebHandler)
    url = f"http://{host}:{port}"
    print(f"[*] Arca Web-Server läuft auf {url}")
    
    if open_browser:
        threading.Timer(1.0, lambda: webbrowser.open(url)).start()
        
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[*] Server wird beendet...")
        server.server_close()
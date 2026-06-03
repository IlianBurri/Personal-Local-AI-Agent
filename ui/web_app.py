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
      await loadBootstrap();
      setStatus('Ready');
    }

    document.getElementById('themeToggle').addEventListener('click', () => {
      applyTheme(root.dataset.theme === 'dark' ? 'light' : 'dark');
    });
    document.getElementById('themeToggleTop').addEventListener('click', () => {
      applyTheme(root.dataset.theme === 'dark' ? 'light' : 'dark');
    });
    document.getElementById('logoutBtn').addEventListener('click', () => { window.location.href = '/logout'; });
    document.getElementById('newChatBtn').addEventListener('click', () => createNewConversation().catch((error) => setError(error.message)));
    document.getElementById('sendBtn').addEventListener('click', () => sendMessage().catch((error) => setError(error.message)));
    messageInput.addEventListener('keydown', (event) => {
      if (event.key === 'Enter' && !event.shiftKey) {
        event.preventDefault();
        sendMessage().catch((error) => setError(error.message));
      }
    });
    providerSelect.addEventListener('change', () => {
      if (bootstrap && providerSelect.value === 'ollama' && bootstrap.ollama_models && bootstrap.ollama_models.length) {
        modelInput.value = bootstrap.ollama_models[0];
      }
    });

    loadBootstrap().catch((error) => {
      setError(error.message);
      setStatus('Offline');
    });
  </script>
</body>
</html>"""


def start_web_ui(host: str = DEFAULT_HOST, port: int = DEFAULT_PORT, open_browser: bool = True) -> ArcaWebServer:
    server = ArcaWebServer((host, port), ArcaWebHandler)
    actual_host, actual_port = server.server_address
    if open_browser:
        webbrowser.open(f"http://{actual_host}:{actual_port}")
    return server
import argparse
import base64
import hashlib
import hmac
import json
import secrets
import threading
import webbrowser
from http import HTTPStatus
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import parse_qs, quote, unquote, urlparse

from core.chat_store import (
    create_conversation,
    ensure_conversations_dir,
    list_conversation_files,
    load_conversation,
    save_conversation,
)
from core.clients import OpenAIClient, AnthropicClient, OllamaClient
from core.config import load_config, save_config

HOST = "127.0.0.1"
DEFAULT_PORT = 8765
SESSION_COOKIE = "arca_session"
SESSION_TTL_SECONDS = 60 * 60 * 8


WEB_LOGIN_PAGE = """<!doctype html>
<html lang="de" data-theme="{theme}">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Arca Login</title>
  <style>
    :root {{
      color-scheme: light;
      --bg: #f4f1ea;
      --panel: rgba(255,255,255,0.78);
      --panel-strong: #ffffff;
      --text: #161410;
      --muted: #6d665c;
      --border: rgba(22,20,16,0.12);
      --accent: #315a86;
      --accent-strong: #234165;
      --shadow: 0 28px 80px rgba(22, 20, 16, 0.12);
    }}
    html[data-theme="dark"] {{
      color-scheme: dark;
      --bg: #0f1217;
      --panel: rgba(18, 23, 31, 0.82);
      --panel-strong: #151b24;
      --text: #f0f3f8;
      --muted: #9ca6b4;
      --border: rgba(240,243,248,0.10);
      --accent: #7aa7e6;
      --accent-strong: #a8c2f0;
      --shadow: 0 28px 80px rgba(0, 0, 0, 0.45);
    }}
    * {{ box-sizing: border-box; }}
    body {{ margin: 0; min-height: 100vh; font-family: Inter, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; background: radial-gradient(circle at top, rgba(122,167,230,0.18), transparent 30%), var(--bg); color: var(--text); }}
    .shell {{ min-height: 100vh; display: grid; place-items: center; padding: 24px; }}
    .card {{ width: min(980px, 100%); display: grid; grid-template-columns: 1.15fr 0.85fr; gap: 0; border: 1px solid var(--border); border-radius: 28px; overflow: hidden; background: var(--panel); backdrop-filter: blur(18px); box-shadow: var(--shadow); }}
    .hero {{ padding: 40px; border-right: 1px solid var(--border); background: linear-gradient(160deg, rgba(122,167,230,0.12), transparent 70%); }}
    .badge {{ display: inline-flex; align-items: center; gap: 8px; border: 1px solid var(--border); border-radius: 999px; padding: 8px 12px; color: var(--muted); font-size: 12px; letter-spacing: 0.08em; text-transform: uppercase; }}
    h1 {{ margin: 22px 0 14px; font-size: clamp(42px, 6vw, 68px); line-height: 0.94; letter-spacing: -0.05em; }}
    p {{ margin: 0; color: var(--muted); font-size: 15px; line-height: 1.7; max-width: 52ch; }}
    .notes {{ margin-top: 32px; display: grid; gap: 10px; }}
    .note {{ border: 1px solid var(--border); border-radius: 16px; padding: 14px 16px; background: rgba(255,255,255,0.08); }}
    .note strong {{ display: block; margin-bottom: 4px; }}
    .form {{ padding: 36px; display: grid; gap: 18px; background: var(--panel-strong); }}
    .mode-row {{ display: flex; justify-content: flex-end; }}
    .theme-btn {{ border: 1px solid var(--border); background: transparent; color: var(--text); border-radius: 999px; padding: 10px 14px; cursor: pointer; font: inherit; }}
    .field {{ display: grid; gap: 8px; }}
    label {{ font-size: 13px; color: var(--muted); }}
    input {{ width: 100%; border: 1px solid var(--border); background: rgba(255,255,255,0.06); color: var(--text); border-radius: 14px; padding: 14px 16px; font: inherit; }}
    input:focus {{ outline: 2px solid rgba(122,167,230,0.35); border-color: rgba(122,167,230,0.35); }}
    .submit {{ margin-top: 6px; border: 0; border-radius: 14px; padding: 14px 18px; background: var(--accent); color: #fff; font-weight: 600; cursor: pointer; }}
    .submit:hover {{ background: var(--accent-strong); }}
    .help {{ font-size: 12px; color: var(--muted); line-height: 1.6; }}
    .error {{ border: 1px solid rgba(220, 74, 74, 0.35); background: rgba(220, 74, 74, 0.1); color: #ffb0b0; border-radius: 14px; padding: 12px 14px; font-size: 13px; }}
    @media (max-width: 860px) {{ .card {{ grid-template-columns: 1fr; }} .hero {{ border-right: 0; border-bottom: 1px solid var(--border); }} }}
  </style>
</head>
<body>
  <div class="shell">
    <div class="card">
      <section class="hero">
        <div class="badge">Arca · Lokale Web UI</div>
        <h1>{headline}</h1>
        <p>{description}</p>
        <div class="notes">
          <div class="note"><strong>Browser-Start</strong> Beim Start öffnet sich die Oberfläche im Standardbrowser auf `localhost`.</div>
          <div class="note"><strong>Lokaler Login</strong> Das Passwort bleibt nur auf deinem Rechner gespeichert und schützt den Zugang zur Web-UI.</div>
          <div class="note"><strong>Theme</strong> Du kannst jederzeit zwischen Light und Dark wechseln. Die Auswahl bleibt im Browser erhalten.</div>
        </div>
      </section>
      <section class="form">
        <div class="mode-row"><button class="theme-btn" id="themeToggle" type="button">Theme wechseln</button></div>
        {message_block}
        <form method="post" action="{action}">
          <div class="field">
            <label for="password">{label}</label>
            <input id="password" name="password" type="password" autocomplete="current-password" autofocus required>
          </div>
          <button class="submit" type="submit">{button}</button>
        </form>
        <div class="help">{help_text}</div>
      </section>
    </div>
  </div>
  <script>
    const root = document.documentElement;
    const stored = localStorage.getItem('arca-theme');
    if (stored) {{ root.dataset.theme = stored; }}
    document.getElementById('themeToggle').addEventListener('click', () => {{
      root.dataset.theme = root.dataset.theme === 'dark' ? 'light' : 'dark';
      localStorage.setItem('arca-theme', root.dataset.theme);
    }});
  </script>
</body>
</html>
"""

WEB_APP_PAGE = """<!doctype html>
<html lang="de" data-theme="light">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Arca Web UI</title>
  <style>
    :root {{
      color-scheme: light;
      --bg: #f5f1ea;
      --panel: rgba(255,255,255,0.82);
      --panel-strong: #ffffff;
      --surface: #fcfaf6;
      --surface-soft: #f4efe6;
      --text: #181510;
      --muted: #6f665b;
      --border: rgba(24,21,16,0.12);
      --accent: #315a86;
      --accent-strong: #264768;
      --accent-soft: rgba(49,90,134,0.12);
      --shadow: 0 30px 90px rgba(24, 21, 16, 0.12);
      --user-bg: #315a86;
      --user-text: #ffffff;
      --assistant-bg: #f0ebe1;
    }}
    html[data-theme="dark"] {{
      color-scheme: dark;
      --bg: #0f1319;
      --panel: rgba(18,24,32,0.84);
      --panel-strong: #151b24;
      --surface: #121821;
      --surface-soft: #18202b;
      --text: #edf1f7;
      --muted: #9da8b7;
      --border: rgba(237,241,247,0.12);
      --accent: #7aa7e6;
      --accent-strong: #abc7f3;
      --accent-soft: rgba(122,167,230,0.14);
      --shadow: 0 30px 90px rgba(0, 0, 0, 0.45);
      --user-bg: #7aa7e6;
      --user-text: #0f1319;
      --assistant-bg: #18202b;
    }}
    * {{ box-sizing: border-box; }}
    html, body {{ margin: 0; min-height: 100%; }}
    body {{ min-height: 100vh; font-family: Inter, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; background: radial-gradient(circle at top, rgba(122,167,230,0.14), transparent 32%), var(--bg); color: var(--text); }}
    button, input, textarea, select {{ font: inherit; }}
    a {{ color: inherit; text-decoration: none; }}
    .app {{ min-height: 100vh; display: grid; grid-template-rows: auto 1fr; }}
    .topbar {{ display: flex; align-items: center; justify-content: space-between; gap: 16px; padding: 18px 24px; border-bottom: 1px solid var(--border); background: rgba(255,255,255,0.36); backdrop-filter: blur(18px); position: sticky; top: 0; z-index: 20; }}
    html[data-theme="dark"] .topbar {{ background: rgba(15,19,25,0.6); }}
    .brand {{ display: flex; align-items: center; gap: 14px; }}
    .brand-mark {{ width: 38px; height: 38px; border-radius: 12px; background: linear-gradient(145deg, var(--accent), var(--accent-strong)); box-shadow: 0 16px 40px rgba(49,90,134,0.24); }}
    .brand-title {{ font-size: 18px; font-weight: 700; letter-spacing: -0.03em; }}
    .brand-sub {{ font-size: 12px; color: var(--muted); }}
    .top-actions {{ display: flex; gap: 10px; align-items: center; flex-wrap: wrap; }}
    .ghost-btn, .danger-btn, .primary-btn {{ border: 1px solid var(--border); border-radius: 999px; padding: 10px 14px; cursor: pointer; background: transparent; color: var(--text); }}
    .primary-btn {{ background: var(--accent); border-color: transparent; color: #fff; }}
    .danger-btn {{ color: #d96d6d; }}
    .ghost-btn:hover, .danger-btn:hover {{ background: var(--accent-soft); }}
    .layout {{ display: grid; grid-template-columns: 300px minmax(0, 1fr) 320px; gap: 16px; padding: 18px; min-height: 0; }}
    .panel {{ min-height: 0; background: var(--panel); backdrop-filter: blur(18px); border: 1px solid var(--border); border-radius: 24px; box-shadow: var(--shadow); overflow: hidden; }}
    .sidebar {{ display: grid; grid-template-rows: auto auto auto 1fr; gap: 14px; padding: 18px; }}
    .section-title {{ font-size: 12px; letter-spacing: 0.12em; text-transform: uppercase; color: var(--muted); margin-bottom: 10px; }}
    .stack {{ display: grid; gap: 10px; }}
    .conv-list {{ display: grid; gap: 8px; max-height: 36vh; overflow: auto; padding-right: 4px; }}
    .conv-item {{ border: 1px solid var(--border); border-radius: 16px; padding: 12px 14px; background: var(--surface); text-align: left; cursor: pointer; }}
    .conv-item.active {{ outline: 2px solid rgba(122,167,230,0.25); border-color: rgba(122,167,230,0.35); }}
    .conv-item-title {{ font-size: 14px; font-weight: 600; margin-bottom: 3px; }}
    .conv-item-meta {{ font-size: 12px; color: var(--muted); }}
    .field {{ display: grid; gap: 7px; }}
    .field label {{ font-size: 12px; color: var(--muted); }}
    .field input, .field textarea, .field select {{ width: 100%; border: 1px solid var(--border); background: var(--surface); color: var(--text); border-radius: 14px; padding: 12px 14px; }}
    .field textarea {{ min-height: 106px; resize: vertical; }}
    .field input:focus, .field textarea:focus, .field select:focus {{ outline: 2px solid rgba(122,167,230,0.25); border-color: rgba(122,167,230,0.35); }}
    .middle {{ display: grid; grid-template-rows: auto 1fr auto; min-height: 0; }}
    .middle-head {{ padding: 18px 18px 0; }}
    .middle-card {{ margin: 0 18px 18px; border-radius: 22px; border: 1px solid var(--border); background: var(--panel-strong); min-height: 0; display: grid; grid-template-rows: 1fr auto; overflow: hidden; }}
    .messages {{ padding: 18px; overflow: auto; display: grid; gap: 14px; align-content: start; background: linear-gradient(180deg, rgba(122,167,230,0.04), transparent 30%); }}
    .msg {{ max-width: min(760px, 92%); border-radius: 20px; padding: 14px 16px; line-height: 1.65; white-space: pre-wrap; word-break: break-word; }}
    .msg.user {{ margin-left: auto; background: var(--user-bg); color: var(--user-text); border-bottom-right-radius: 6px; }}
    .msg.assistant {{ margin-right: auto; background: var(--assistant-bg); border-bottom-left-radius: 6px; }}
    .composer {{ border-top: 1px solid var(--border); padding: 16px; display: grid; gap: 12px; background: rgba(255,255,255,0.28); }}
    html[data-theme="dark"] .composer {{ background: rgba(10,12,16,0.22); }}
    .composer-row {{ display: grid; grid-template-columns: 1fr auto; gap: 10px; align-items: end; }}
    .composer textarea {{ min-height: 74px; resize: none; }}
    .status {{ font-size: 12px; color: var(--muted); min-height: 18px; }}
    .right {{ display: grid; grid-template-rows: auto 1fr; gap: 14px; padding: 18px; }}
    .config-grid {{ display: grid; gap: 12px; }}
    .mini-note {{ font-size: 13px; color: var(--muted); line-height: 1.6; }}
    .empty {{ display: grid; place-items: center; min-height: 38vh; color: var(--muted); text-align: center; padding: 20px; }}
    .pill {{ display: inline-flex; align-items: center; gap: 8px; padding: 8px 12px; border-radius: 999px; border: 1px solid var(--border); background: var(--surface); color: var(--muted); font-size: 12px; }}
    .dot {{ width: 9px; height: 9px; border-radius: 50%; background: #5db075; }}
    .split {{ display: flex; gap: 10px; flex-wrap: wrap; }}
    .small {{ font-size: 12px; }}
    .file-list {{ font-size: 13px; color: var(--muted); line-height: 1.6; }}
    @media (max-width: 1180px) {{ .layout {{ grid-template-columns: 1fr; }} .right {{ order: 3; }} .sidebar {{ order: 1; }} .middle {{ order: 2; }} }}
  </style>
</head>
<body>
  <div class="app">
    <header class="topbar">
      <div class="brand">
        <div class="brand-mark"></div>
        <div>
          <div class="brand-title">Arca</div>
          <div class="brand-sub">Local browser workspace</div>
        </div>
      </div>
      <div class="top-actions">
        <button class="ghost-btn" id="themeToggle" type="button">Theme</button>
        <button class="ghost-btn" id="newChatBtn" type="button">New chat</button>
        <button class="danger-btn" id="logoutBtn" type="button">Logout</button>
      </div>
    </header>

    <main class="layout">
      <aside class="panel sidebar">
        <div>
          <div class="section-title">Conversations</div>
          <div class="split">
            <span class="pill"><span class="dot"></span> Local login active</span>
            <span class="pill" id="providerBadge">Provider ready</span>
          </div>
        </div>
        <div class="conv-list" id="conversationList"></div>
        <div>
          <div class="section-title">Session</div>
          <div class="mini-note" id="sessionSummary">Loading session…</div>
        </div>
        <div>
          <div class="section-title">Files</div>
          <div class="file-list">Chats are stored locally in <span class="small">~/.config/arca/conversations</span>.</div>
        </div>
      </aside>

      <section class="panel middle">
        <div class="middle-head">
          <div class="section-title">Chat</div>
          <div class="pill" id="activeConversationPill">No conversation selected</div>
        </div>
        <div class="middle-card">
          <div id="messages" class="messages"></div>
          <div class="composer">
            <div class="composer-row">
              <div class="field" style="margin: 0;">
                <label for="promptInput">Message</label>
                <textarea id="promptInput" placeholder="Frag etwas oder starte mit einem Code-Snippet…"></textarea>
              </div>
              <button class="primary-btn" id="sendBtn" type="button">Send</button>
            </div>
            <div class="status" id="chatStatus"></div>
          </div>
        </div>
      </section>

      <aside class="panel right">
        <div>
          <div class="section-title">Provider</div>
          <div class="config-grid">
            <div class="field">
              <label for="providerSelect">Backend</label>
              <select id="providerSelect">
                <option value="openai">OpenAI</option>
                <option value="anthropic">Anthropic</option>
                <option value="ollama">Ollama</option>
              </select>
            </div>
            <div class="field">
              <label for="modelInput">Model</label>
              <input id="modelInput" type="text" placeholder="gpt-4o / claude-3-5-sonnet / llama3">
            </div>
            <div class="field">
              <label for="systemPrompt">System prompt</label>
              <textarea id="systemPrompt" placeholder="Setze Verhalten, Stil oder Kontext für diesen Chat…"></textarea>
            </div>
            <div class="field">
              <label for="temperatureInput">Temperature</label>
              <input id="temperatureInput" type="number" min="0" max="2" step="0.1" value="0.7">
            </div>
            <div class="field">
              <label for="maxTokensInput">Max tokens</label>
              <input id="maxTokensInput" type="number" min="16" max="8192" step="1" value="1024">
            </div>
          </div>
        </div>
        <div>
          <div class="section-title">Ollama</div>
          <div class="mini-note" id="ollamaStatus">Loading models…</div>
        </div>
      </aside>
    </main>
  </div>

  <script>
    const appState = {{
      bootstrap: null,
      activeConversationId: null,
      conversations: [],
      currentMessages: [],
      sending: false,
    }};

    const elements = {{
      conversationList: document.getElementById('conversationList'),
      sessionSummary: document.getElementById('sessionSummary'),
      activeConversationPill: document.getElementById('activeConversationPill'),
      messages: document.getElementById('messages'),
      promptInput: document.getElementById('promptInput'),
      sendBtn: document.getElementById('sendBtn'),
      newChatBtn: document.getElementById('newChatBtn'),
      logoutBtn: document.getElementById('logoutBtn'),
      themeToggle: document.getElementById('themeToggle'),
      providerSelect: document.getElementById('providerSelect'),
      modelInput: document.getElementById('modelInput'),
      systemPrompt: document.getElementById('systemPrompt'),
      temperatureInput: document.getElementById('temperatureInput'),
      maxTokensInput: document.getElementById('maxTokensInput'),
      chatStatus: document.getElementById('chatStatus'),
      ollamaStatus: document.getElementById('ollamaStatus'),
      providerBadge: document.getElementById('providerBadge'),
    }};

    function escapeHtml(value) {{
      return String(value)
        .replaceAll('&', '&amp;')
        .replaceAll('<', '&lt;')
        .replaceAll('>', '&gt;')
        .replaceAll('"', '&quot;')
        .replaceAll("'", '&#39;');
    }}

    function setTheme(theme) {{
      document.documentElement.dataset.theme = theme;
      localStorage.setItem('arca-theme', theme);
    }}

    function applyStoredTheme() {{
      const stored = localStorage.getItem('arca-theme');
      if (stored) {{
        setTheme(stored);
      }}
    }}

    function formatConversationMeta(conversation) {{
      const updated = conversation.updated_at ? new Date(conversation.updated_at * 1000) : null;
      return updated ? updated.toLocaleString() : '';
    }}

    function renderConversationList() {{
      elements.conversationList.innerHTML = '';
      if (!appState.conversations.length) {{
        elements.conversationList.innerHTML = '<div class="empty">No conversations yet.</div>';
        return;
      }}
      for (const conversation of appState.conversations) {{
        const button = document.createElement('button');
        button.type = 'button';
        button.className = 'conv-item' + (conversation.id === appState.activeConversationId ? ' active' : '');
        button.innerHTML = '<div class="conv-item-title">' + escapeHtml(conversation.title) + '</div><div class="conv-item-meta">' + escapeHtml(formatConversationMeta(conversation)) + '</div>';
        button.addEventListener('click', () => loadConversation(conversation.id));
        elements.conversationList.appendChild(button);
      }}
    }}

    function renderMessages() {{
      elements.messages.innerHTML = '';
      if (!appState.currentMessages.length) {{
        elements.messages.innerHTML = '<div class="empty">Start a conversation to see the chat here.</div>';
        return;
      }}
      for (const message of appState.currentMessages) {{
        const bubble = document.createElement('div');
        bubble.className = 'msg ' + (message.role === 'user' ? 'user' : 'assistant');
        bubble.innerHTML = escapeHtml(message.content || '');
        elements.messages.appendChild(bubble);
      }}
      elements.messages.scrollTop = elements.messages.scrollHeight;
    }}

    function updateSessionSummary() {{
      const provider = appState.bootstrap?.provider || 'openai';
      const model = appState.bootstrap?.model || 'custom';
      elements.sessionSummary.textContent = 'Logged in locally. Provider default: ' + provider + ' / ' + model + '.';
      elements.providerBadge.textContent = provider;
    }}

    function syncConfigToForm() {{
      const cfg = appState.bootstrap || {{}};
      elements.providerSelect.value = cfg.provider || 'openai';
      elements.modelInput.value = cfg.model || '';
      elements.systemPrompt.value = cfg.system_prompt || '';
      elements.temperatureInput.value = String(cfg.temperature ?? 0.7);
      elements.maxTokensInput.value = String(cfg.max_tokens ?? 1024);
      elements.ollamaStatus.textContent = cfg.ollama_status || 'Ollama models available locally when configured.';
      updateSessionSummary();
    }}

    async function api(path, options = {{}}) {{
      const response = await fetch(path, {{
        headers: Object.assign({{'Content-Type': 'application/json'}}, options.headers || {{}}),
        credentials: 'same-origin',
        ...options,
      }});
      if (!response.ok) {{
        const text = await response.text();
        throw new Error(text || ('HTTP ' + response.status));
      }}
      const contentType = response.headers.get('content-type') || '';
      if (contentType.includes('application/json')) {{
        return response.json();
      }}
      return response.text();
    }}

    async function loadBootstrap() {{
      const data = await api('/api/bootstrap');
      appState.bootstrap = data;
      appState.conversations = data.conversations || [];
      appState.activeConversationId = data.active_conversation_id || null;
      syncConfigToForm();
      renderConversationList();
      if (appState.activeConversationId) {{
        await loadConversation(appState.activeConversationId, false);
      }} else {{
        renderMessages();
      }}
      if (data.ollama_models && data.ollama_models.length) {{
        elements.ollamaStatus.textContent = 'Ollama models: ' + data.ollama_models.join(', ');
      }}
    }}

    async function loadConversation(conversationId, fetchRemote = true) {{
      appState.activeConversationId = conversationId;
      renderConversationList();
      elements.activeConversationPill.textContent = 'Conversation: ' + conversationId;
      if (fetchRemote) {{
        const data = await api('/api/conversations/' + encodeURIComponent(conversationId));
        appState.currentMessages = data.messages || [];
      }}
      renderMessages();
    }}

    async function createConversation() {{
      const data = await api('/api/conversations/new', {{ method: 'POST', body: JSON.stringify({{}}) }});
      await loadBootstrap();
      if (data.id) {{
        await loadConversation(data.id);
      }}
    }}

    async function sendMessage() {{
      if (appState.sending) return;
      const text = elements.promptInput.value.trim();
      if (!text) return;
      appState.sending = true;
      elements.sendBtn.disabled = true;
      elements.chatStatus.textContent = 'Generating response…';
      try {{
        if (!appState.activeConversationId) {{
          const created = await api('/api/conversations/new', {{ method: 'POST', body: JSON.stringify({{ title: text.slice(0, 42) }}) }});
          appState.activeConversationId = created.id;
          await loadBootstrap();
        }}
        const payload = {{
          conversation_id: appState.activeConversationId,
          message: text,
          provider: elements.providerSelect.value,
          model: elements.modelInput.value.trim(),
          system_prompt: elements.systemPrompt.value,
          temperature: parseFloat(elements.temperatureInput.value || '0.7'),
          max_tokens: parseInt(elements.maxTokensInput.value || '1024', 10),
        }};
        const data = await api('/api/chat', {{ method: 'POST', body: JSON.stringify(payload) }});
        elements.promptInput.value = '';
        appState.currentMessages = data.messages || [];
        appState.conversations = data.conversations || appState.conversations;
        await loadConversation(data.conversation_id || appState.activeConversationId, false);
        appState.currentMessages = data.messages || appState.currentMessages;
        renderMessages();
        renderConversationList();
        elements.chatStatus.textContent = 'Last reply received.';
      }} catch (error) {{
        elements.chatStatus.textContent = 'Error: ' + error.message;
      }} finally {{
        appState.sending = false;
        elements.sendBtn.disabled = false;
      }}
    }}

    async function logout() {{
      await api('/api/logout', {{ method: 'POST', body: JSON.stringify({{}}) }});
      window.location.href = '/';
    }}

    elements.sendBtn.addEventListener('click', sendMessage);
    elements.newChatBtn.addEventListener('click', createConversation);
    elements.logoutBtn.addEventListener('click', logout);
    elements.themeToggle.addEventListener('click', () => {{
      const next = document.documentElement.dataset.theme === 'dark' ? 'light' : 'dark';
      setTheme(next);
    }});
    elements.promptInput.addEventListener('keydown', (event) => {{
      if ((event.ctrlKey || event.metaKey) && event.key === 'Enter') {{
        sendMessage();
      }}
    }});

    applyStoredTheme();
    loadBootstrap().catch(error => {{
      elements.chatStatus.textContent = 'Unable to load session: ' + error.message;
    }});
  </script>
</body>
</html>
"""


def _now_ts() -> float:
    return float(__import__("time").time())


class WebAuthError(RuntimeError):
    pass


class WebAgentState:
    def __init__(self):
        self.config = load_config()
        self.sessions: Dict[str, float] = {}
        self.lock = threading.Lock()

    def refresh_config(self) -> dict:
        self.config = load_config()
        return self.config

    def save_config(self, config: dict) -> None:
        self.config = config
        save_config(config)

    def ensure_web_settings(self) -> dict:
        config = self.refresh_config()
        config.setdefault("web", {})
        config["web"].setdefault("password_salt", None)
        config["web"].setdefault("password_hash", None)
        return config

    def has_password(self) -> bool:
        config = self.ensure_web_settings()
        web_cfg = config.get("web", {})
        return bool(web_cfg.get("password_salt") and web_cfg.get("password_hash"))

    def set_password(self, password: str) -> None:
        salt = secrets.token_bytes(16)
        digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 220_000)
        config = self.ensure_web_settings()
        config["web"]["password_salt"] = base64.urlsafe_b64encode(salt).decode("ascii").rstrip("=")
        config["web"]["password_hash"] = base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")
        self.save_config(config)

    def verify_password(self, password: str) -> bool:
        config = self.ensure_web_settings()
        web_cfg = config.get("web", {})
        salt_text = web_cfg.get("password_salt")
        hash_text = web_cfg.get("password_hash")
        if not salt_text or not hash_text:
            return False
        salt = base64.urlsafe_b64decode(_pad_base64(salt_text))
        expected = base64.urlsafe_b64decode(_pad_base64(hash_text))
        actual = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 220_000)
        return hmac.compare_digest(expected, actual)

    def create_session(self) -> str:
        token = secrets.token_urlsafe(32)
        with self.lock:
            self.sessions[token] = _now_ts() + SESSION_TTL_SECONDS
        return token

    def validate_session(self, token: str) -> bool:
        if not token:
            return False
        with self.lock:
            expiry = self.sessions.get(token)
            if not expiry:
                return False
            if expiry < _now_ts():
                self.sessions.pop(token, None)
                return False
            return True

    def revoke_session(self, token: str) -> None:
        with self.lock:
            self.sessions.pop(token, None)

    def list_conversations(self) -> List[dict]:
        items = []
        for path in list_conversation_files():
            data = load_conversation(path)
            stat = path.stat()
            items.append({
                "id": path.name,
                "title": data.get("title") or path.stem,
                "message_count": len(data.get("messages", [])),
                "updated_at": stat.st_mtime,
            })
        return sorted(items, key=lambda item: item["updated_at"], reverse=True)

    def get_conversation_path(self, conversation_id: str) -> Path:
        return ensure_conversations_dir() / Path(conversation_id).name

    def get_conversation(self, conversation_id: str) -> dict:
        return load_conversation(self.get_conversation_path(conversation_id))

    def create_conversation(self, title: Optional[str] = None) -> dict:
        path = create_conversation(title=title)
        data = load_conversation(path)
        return {"id": path.name, "title": data.get("title") or path.stem, "messages": data.get("messages", [])}

    def save_conversation(self, conversation_id: str, data: dict) -> dict:
        path = self.get_conversation_path(conversation_id)
        save_conversation(path, data)
        return self.get_conversation(conversation_id)

    def resolve_client(self, provider: str, model: str | None) -> Any:
        config = self.refresh_config()
        providers = config.get("providers", {})
        if provider == "openai":
            api_key = providers.get("openai", {}).get("api_key")
            if not api_key:
                raise WebAuthError("OpenAI API key not configured")
            return OpenAIClient(api_key, model=model or "gpt-4o")
        if provider == "anthropic":
            api_key = providers.get("anthropic", {}).get("api_key")
            if not api_key:
                raise WebAuthError("Anthropic API key not configured")
            return AnthropicClient(api_key, model=model or "claude-3-5-sonnet")
        base_url = providers.get("ollama", {}).get("base_url", "http://localhost:11434")
        return OllamaClient(base_url=base_url, model=model or None)

    def get_ollama_models(self) -> List[str]:
        config = self.refresh_config()
        base_url = config.get("providers", {}).get("ollama", {}).get("base_url", "http://localhost:11434")
        try:
            tags = OllamaClient(base_url=base_url).list_models()
        except Exception:
            return []
        models: List[str] = []
        if isinstance(tags, dict):
            for item in tags.get("models", []) or tags.get("tags", []):
                if isinstance(item, str):
                    models.append(item)
                elif isinstance(item, dict):
                    name = item.get("name") or item.get("model") or item.get("tag")
                    if name:
                        models.append(name)
        elif isinstance(tags, list):
            for item in tags:
                if isinstance(item, str):
                    models.append(item)
                elif isinstance(item, dict):
                    name = item.get("name") or item.get("model") or item.get("tag")
                    if name:
                        models.append(name)
        return models


class ArcaRequestHandler(BaseHTTPRequestHandler):
    server: "ArcaWebServer"

    def log_message(self, format: str, *args: Any) -> None:
        return

    def do_GET(self):
        if self.path.startswith("/api/"):
            if not self._require_auth():
                return
            if self.path == "/api/bootstrap":
                self._send_json(self.server.state_bootstrap())
                return
            if self.path.startswith("/api/conversations/"):
                conversation_id = unquote(self.path.split("/api/conversations/", 1)[1])
                self._send_json(self.server.state.get_conversation(conversation_id))
                return
            self._send_error(HTTPStatus.NOT_FOUND, "Unknown API endpoint")
            return

        if self._is_authenticated():
            self._send_html(WEB_APP_PAGE)
            return

        self._send_html(self.server.render_login_page())

    def do_POST(self):
        if self.path == "/setup":
            body = self._read_form_body()
            password = body.get("password", [""])[0].strip()
            if len(password) < 6:
                self._send_html(self.server.render_login_page(message="Passwort muss mindestens 6 Zeichen haben.", message_kind="error", setup_mode=True), status=HTTPStatus.BAD_REQUEST)
                return
            self.server.state.set_password(password)
            session_token = self.server.state.create_session()
            self._set_session_cookie(session_token)
            self._redirect("/")
            return

        if self.path == "/login":
            body = self._read_form_body()
            password = body.get("password", [""])[0].strip()
            if self.server.state.verify_password(password):
                session_token = self.server.state.create_session()
                self._set_session_cookie(session_token)
                self._redirect("/")
            else:
                self._send_html(self.server.render_login_page(message="Ungültiges Passwort.", message_kind="error"), status=HTTPStatus.UNAUTHORIZED)
            return

        if self.path == "/api/logout":
            token = self._get_session_token()
            if token:
                self.server.state.revoke_session(token)
            self._clear_cookie()
            self._send_json({"ok": True})
            return

        if not self._require_auth():
            return

        if self.path == "/api/conversations/new":
            payload = self._read_json_body()
            title = (payload.get("title") or "").strip() or None
            conversation = self.server.state.create_conversation(title=title)
            self._send_json(conversation)
            return

        if self.path == "/api/chat":
            payload = self._read_json_body()
            conversation_id = (payload.get("conversation_id") or "").strip()
            message = (payload.get("message") or "").strip()
            if not message:
                self._send_json({"error": "Empty message"}, status=HTTPStatus.BAD_REQUEST)
                return
            if not conversation_id:
                conversation_id = self.server.state.create_conversation(title=message[:42])
                conversation_id = conversation_id["id"]
            conversation = self.server.state.get_conversation(conversation_id)
            messages = list(conversation.get("messages", []))
            messages.append({"role": "user", "content": message})
            provider = (payload.get("provider") or self.server.state.refresh_config().get("provider") or "openai").strip()
            model = (payload.get("model") or "").strip() or None
            system_prompt = (payload.get("system_prompt") or "").strip()
            temperature = float(payload.get("temperature") or 0.7)
            max_tokens = int(payload.get("max_tokens") or 1024)
            request_messages = []
            if system_prompt:
                request_messages.append({"role": "system", "content": system_prompt})
            request_messages.extend(messages)

            client = self.server.state.resolve_client(provider, model)
            try:
                assistant_text = "".join(client.stream_chat(request_messages, temperature=temperature, max_tokens=max_tokens))
            except WebAuthError as exc:
                self._send_json({"error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
                return
            except Exception as exc:
                self._send_json({"error": str(exc)}, status=HTTPStatus.INTERNAL_SERVER_ERROR)
                return

            messages.append({"role": "assistant", "content": assistant_text})
            if not conversation.get("title") or conversation.get("title", "").startswith("Conversation "):
                conversation["title"] = (message[:42] + "…") if len(message) > 42 else message[:42]
            conversation["messages"] = messages
            self.server.state.save_conversation(conversation_id, conversation)
            self._send_json({
                "conversation_id": conversation_id,
                "title": conversation.get("title") or conversation_id,
                "assistant": assistant_text,
                "messages": messages,
                "conversations": self.server.state.list_conversations(),
            })
            return

        self._send_error(HTTPStatus.NOT_FOUND, "Unknown endpoint")

    def _require_auth(self) -> bool:
        if self._is_authenticated():
            return True
        self._redirect("/")
        return False

    def _is_authenticated(self) -> bool:
        if not self.server.state.has_password():
            return self.path not in {"/api/bootstrap", "/api/conversations/new", "/api/chat"} and True
        token = self._get_session_token()
        return self.server.state.validate_session(token)

    def _get_session_token(self) -> str:
        cookie_header = self.headers.get("Cookie", "")
        if not cookie_header:
            return ""
        cookie = SimpleCookie()
        try:
            cookie.load(cookie_header)
        except Exception:
            return ""
        morsel = cookie.get(SESSION_COOKIE)
        return morsel.value if morsel else ""

    def _read_body(self) -> bytes:
        length = int(self.headers.get("Content-Length", "0") or 0)
        return self.rfile.read(length) if length > 0 else b""

    def _read_form_body(self) -> Dict[str, List[str]]:
        return parse_qs(self._read_body().decode("utf-8"), keep_blank_values=True)

    def _read_json_body(self) -> Dict[str, Any]:
        raw = self._read_body().decode("utf-8") or "{}"
        try:
            payload = json.loads(raw)
            return payload if isinstance(payload, dict) else {}
        except Exception:
            return {}

    def _send_json(self, payload: Dict[str, Any], status: HTTPStatus = HTTPStatus.OK) -> None:
        encoded = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(encoded)

    def _send_html(self, html: str, status: HTTPStatus = HTTPStatus.OK) -> None:
        encoded = html.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(encoded)

    def _send_error(self, status: HTTPStatus, message: str) -> None:
        encoded = message.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def _redirect(self, location: str) -> None:
        self.send_response(HTTPStatus.SEE_OTHER)
        self.send_header("Location", location)
        self.end_headers()

    def _set_session_cookie(self, token: str) -> None:
        self.send_response(HTTPStatus.SEE_OTHER)
        cookie = SimpleCookie()
        cookie[SESSION_COOKIE] = token
        cookie[SESSION_COOKIE]["path"] = "/"
        cookie[SESSION_COOKIE]["httponly"] = True
        cookie[SESSION_COOKIE]["samesite"] = "Lax"
        self.send_header("Set-Cookie", cookie.output(header="").strip())
        self.send_header("Location", "/")
        self.end_headers()

    def _clear_cookie(self) -> None:
        cookie = SimpleCookie()
        cookie[SESSION_COOKIE] = ""
        cookie[SESSION_COOKIE]["path"] = "/"
        cookie[SESSION_COOKIE]["expires"] = "Thu, 01 Jan 1970 00:00:00 GMT"
        self.send_header("Set-Cookie", cookie.output(header="").strip())


class ArcaWebServer(ThreadingHTTPServer):
    def __init__(self, address: Tuple[str, int], handler, state: WebAgentState):
        super().__init__(address, handler)
        self.state = state

    def state_bootstrap(self) -> Dict[str, Any]:
        config = self.state.refresh_config()
        providers = config.get("providers", {})
        conversations = self.state.list_conversations()
        active_conversation_id = conversations[0]["id"] if conversations else None
        active_conversation = self.state.get_conversation(active_conversation_id) if active_conversation_id else {"messages": []}
        return {
            "provider": config.get("provider") or "openai",
            "model": "",
            "system_prompt": "",
            "temperature": 0.7,
            "max_tokens": 1024,
            "providers_configured": sorted([name for name, value in providers.items() if value]),
            "ollama_models": self.state.get_ollama_models(),
            "ollama_status": "Loaded locally" if self.state.get_ollama_models() else "Ollama not reachable or no models available.",
            "conversations": conversations,
            "active_conversation_id": active_conversation_id,
            "active_conversation": active_conversation,
        }

    def render_login_page(self, message: str = "", message_kind: str = "", setup_mode: bool = False) -> str:
        has_password = self.state.has_password()
        title = "Password einrichten" if setup_mode or not has_password else "Login"
        headline = "Create your local login" if setup_mode or not has_password else "Welcome back"
        description = "Set a password once, then use the browser UI with your local chats and provider keys." if setup_mode or not has_password else "Use your local password to unlock the browser interface for Arca."
        label = "New password" if setup_mode or not has_password else "Password"
        button = "Save password" if setup_mode or not has_password else "Login"
        action = "/setup" if setup_mode or not has_password else "/login"
        help_text = "The password is stored locally as a salted hash. If you forget it, delete the web entry from ~/.config/arca/config.json." if setup_mode or not has_password else "Your browser session stays local to this machine."
        if message:
            message_block = f'<div class="{"error" if message_kind == "error" else "note"}">{message}</div>'
        else:
            message_block = ""
        theme = "dark" if self.state.refresh_config().get("web", {}).get("theme") == "dark" else "light"
        return WEB_LOGIN_PAGE.format(
            headline=headline,
            description=description,
            label=label,
            button=button,
            action=action,
            help_text=help_text,
            message_block=message_block,
            theme=theme,
            title=title,
        )


def _pad_base64(value: str) -> str:
    return value + "=" * (-len(value) % 4)


def run_web_app(host: str = HOST, port: int = DEFAULT_PORT, open_browser: bool = True) -> None:
    state = WebAgentState()
    server = ArcaWebServer((host, port), ArcaRequestHandler, state)
    url = f"http://{host}:{port}/"
    if open_browser:
        webbrowser.open(url)
    print(f"Arca Web UI running at {url}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Arca browser web UI")
    parser.add_argument("--host", default=HOST)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--no-open-browser", action="store_true")
    return parser


if __name__ == "__main__":
    args = build_parser().parse_args()
    run_web_app(host=args.host, port=args.port, open_browser=not args.no_open_browser)

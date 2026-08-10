# arca

> Your models. Your machine. Your rules.

A lightweight AI chat app that runs entirely on your machine. It opens as a
native desktop window (PyWebView) with a modern, polished web UI — no
Electron, no bloated framework stack. Connect to Anthropic, OpenAI, or a
local Ollama instance.

![Python](https://img.shields.io/badge/python-3.10%2B-blue?style=flat-square)
![UI](https://img.shields.io/badge/UI-React%20%2B%20Vite-8b5cf6?style=flat-square)
![License](https://img.shields.io/badge/license-MIT-lightgrey?style=flat-square)

---

## Features

- **Multi-provider** — Anthropic, OpenAI, and local Ollama provider clients
- **Local-first** — run models entirely on your machine via Ollama
- **Native window** — PyWebView desktop window (falls back to your browser)
- **Streaming responses** — real-time token streaming over SSE
- **Markdown rendering** — syntax-highlighted code blocks with 1-click copy
- **Agentic tool use** — a multi-round tool loop (capped, with forced
  wrap-up) lets the model explore and change the codebase: read/write/edit
  files, regex-search the code, read web pages, check git state, and run
  shell commands (opt-in), all with live tool pills in the UI
- **Multi-turn memory** — full conversation context per session (SQLite)
- **Fully customizable** — dark/light themes, any accent color, font size,
  chat width, app name & tagline, custom suggestion chips, and a custom
  system prompt + tool-round cap for agent behavior; everything persists in
  `~/.config/arca/config.json`
- **Polished UI** — chat history grouped by day, suggestion chips,
  regenerate & stop controls

---

## Quick start (zero-setup)

**Requirements:** Python 3.10+ (Node.js only needed to rebuild the frontend).

```bash
git clone https://github.com/IlianBurri/arca.git
cd arca
./start.sh        # macOS / Linux
# or double-click start.bat  (Windows)
```

The launcher creates a `.venv`, installs dependencies, builds the frontend
if needed (and Node is available), and opens Arca in a native window. On
first launch Arca uses your local Ollama instance by default.

### Manual start

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cd ui/web && npm install && npm run build && cd ..
python run.py
```

Set `ARCA_BROWSER=1` to always open the UI in your browser instead of a
native window. Set `ARCA_PORT=9000` to change the local port (default 8765)
and `ARCA_HOST=0.0.0.0` to listen on all interfaces.

### Docker

Run Arca in a container (Flask server + built frontend — no desktop window):

```bash
docker compose up -d --build
# open http://localhost:8765
```

- Chat history and settings persist in named volumes (`arca-data`,
  `arca-config`), so they survive container rebuilds.
- To use an **Ollama running on the host**, uncomment
  `ARCA_OLLAMA_URL: http://host.docker.internal:11434` in
  `docker-compose.yml` (the `host.docker.internal` alias is wired up via
  `extra_hosts`).
- API keys: pass `OPENAI_API_KEY` / `ANTHROPIC_API_KEY` env vars, or set
  them in the Settings panel (they persist in the `arca-config` volume).

Or build and run manually:

```bash
docker build -t arca .
docker run --rm -p 8765:8765 arca
```

> **Linux native window:** needs the distro's GTK/WebKit bindings
> (`sudo apt install python3-gi gir1.2-webkit2-4.1 gir1.2-gtk-3.0` on
> Debian/Ubuntu). The launcher creates its venv with
> `--system-site-packages` so the native window works automatically; if the
> bindings are missing, Arca falls back to your browser. The same applies
> to the standalone PyInstaller build: on Linux it requires
> `libwebkit2gtk-4.1-0` + `libgtk-3-0` on the target machine (Windows and
> macOS builds are self-contained).

---

## Providers

| Provider  | Requires             |
|-----------|----------------------|
| Anthropic | API key              |
| OpenAI    | API key              |
| Ollama    | Local Ollama install |

Configure keys, default models and generation parameters in the Settings
panel (gear icon). Provider config is stored in `~/.config/arca/config.json`
(API keys fall back to `OPENAI_API_KEY` / `ANTHROPIC_API_KEY` env vars).

---

## Project structure

```text
arca/
run.py         # Entry: starts the local server + PyWebView window
server/        # Flask API + SSE chat streaming + tool-use loop
core/          # Config, provider clients, SQLite persistence
tools/         # Tool registry (shell, files, web search) for LLM tool use
ui/web/        # React + Vite frontend (Codex-inspired dark design)
tests/         # pytest — API, providers, tool loop
start.sh / start.bat   # zero-setup launchers
```

### Frontend development

```bash
cd ui/web
npm run dev        # Vite dev server on :5173 (proxies /api to :8765)
npm run build      # production bundle into ui/web/dist (served by Flask)
```

### Standalone binary (optional, PyInstaller)

```bash
pip install pyinstaller
pyinstaller arca.spec
# distributable in dist/arca/
```

---

## Tests

```bash
pip install -r requirements.txt
pytest -q
```

---

## Contributing

PRs and issues welcome. If you find a bug or want a feature, [open an issue](https://github.com/IlianBurri/arca/issues).

---

## Links

- **Website:** [ilianburri.github.io/arca](https://ilianburri.github.io/arca/)
- **Releases:** [github.com/IlianBurri/arca/releases](https://github.com/IlianBurri/arca/releases)

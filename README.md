# arca

> Your models. Your machine. Your rules.

A lightweight desktop AI agent built with Python + PyQt6. Connect to Anthropic, OpenAI, or a local Ollama instance.

![Python](https://img.shields.io/badge/python-3.10%2B-blue?style=flat-square)
![PyQt6](https://img.shields.io/badge/UI-PyQt6-green?style=flat-square)
![License](https://img.shields.io/badge/license-MIT-lightgrey?style=flat-square)
![Platform](https://img.shields.io/badge/platform-Linux%20%7C%20macOS%20%7C%20Windows-informational?style=flat-square)

---

## Features

- **Multi-provider** - Anthropic, OpenAI, and local Ollama provider clients
- **Local-first** - run models entirely on your machine via Ollama
- **Streaming responses** - real-time output as the model generates
- **Multi-turn memory** - full conversation context per session
- **Tool use** - extensible tool support via the `tools/` module
- **Clean UI** - distraction-free chat interface, no Electron, no bloat

---

## Quick start

**Requirements:** Python 3.10+

```bash
git clone https://github.com/IlianBurri/arca.git
cd arca
python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python run.py
```

On first launch, arca will use your local Ollama instance by default.

---

## Providers

| Provider  | Requires             |
|-----------|----------------------|
| Anthropic | API key              |
| OpenAI    | API key              |
| Ollama    | Local Ollama install |

Provider config is stored in `~/.config/arca/config.json`.

---

## Project structure

```text
arca/
core/        # Config, providers, persistence
ui/          # PyQt6 chat interface
tools/       # Tool definitions for LLM tool use
docs/        # GitHub Pages landing page
requirements.txt
```

---

## Contributing

PRs and issues welcome. If you find a bug or want a feature, [open an issue](https://github.com/IlianBurri/arca/issues).

---

## Links

- **Website:** [ilianburri.github.io/arca](https://ilianburri.github.io/arca/)
- **Releases:** [github.com/IlianBurri/arca/releases](https://github.com/IlianBurri/arca/releases)

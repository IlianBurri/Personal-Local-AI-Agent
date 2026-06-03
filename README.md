# AI Agent (desktop)

A lightweight desktop AI agent that supports Anthropic, OpenAI, and a local Ollama instance. This repository contains a Python + PyQt6 prototype with modular LLM clients and a minimal chat UI.

This is an initial scaffold. See `docs/` for a GitHub Pages landing page skeleton.

## Quick start (Linux/macOS)

Install dependencies (recommended in a venv):

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Run the UI:

```bash
python -m ui.main
```

## Config
Config is stored in `~/.config/aiagent/config.json`. On first run the app will prompt for provider configuration.

## Contributing
PRs welcome. Open issues for features or bugs.

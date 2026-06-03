# AI Agent (desktop)

AI Agent is a lightweight desktop application that lets you connect to multiple LLM providers (OpenAI, Anthropic, local Ollama) via a unified interface. Switch providers from the UI without editing code.

**This repository** contains a Python + PyQt6 prototype with modular LLM clients, a basic chat UI, and a GitHub Pages landing page.

**Config**: stored at `~/.config/aiagent/config.json`. The app prompts for provider configuration on first launch.

## Quick start (Linux/macOS)

Clone and setup:

```bash
git clone https://github.com/IlianBurri/Personal-Local-AI-Agent.git
cd Personal-Local-AI-Agent
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Run the UI:

```bash
python3 -m ui.main
```

## Provider setup

On first launch you'll be prompted to choose a provider and enter an API key (for OpenAI or Anthropic) or a base URL (for Ollama). Keys are stored locally in `~/.config/aiagent/config.json` — never hardcoded into the app.

## Packaging

We plan to publish binaries using `PyInstaller`. See `docs/` for download links once releases are created.

## Contributing

Contributions welcome. Please open issues or PRs. Follow standard GitHub flow: branch from `main`, create a descriptive commit message, and open a PR.

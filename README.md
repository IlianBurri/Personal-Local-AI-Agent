# Arca

*Your models. Your machine. Your rules.*

Arca is a lightweight desktop AI agent that connects to any LLM — OpenAI, Anthropic, or a local Ollama instance — through a single clean interface. Switch providers from the sidebar without touching code.

Arca now also starts in a local browser UI by default. The web UI includes a local login screen, saved conversations, and a dark/light theme toggle.

## Quick start

```bash
git clone https://github.com/IlianBurri/arca.git
cd arca
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m ui.main
```

To force the old desktop window instead of the browser UI, run:

```bash
python -m ui.main --mode desktop
```

## Provider setup

On first launch Arca asks for your provider and API key. Everything is saved locally at `~/.config/arca/config.json` — nothing leaves your machine.

The browser UI also asks you to create a local password the first time you open it.

| Provider  | What you need          |
|-----------|------------------------|
| Anthropic | API key                |
| OpenAI    | API key                |
| Ollama    | Local instance running at `localhost:11434` |

## Project structure
arca/
├── core/        # LLM clients (Anthropic, OpenAI, Ollama)
├── ui/          # PyQt6 chat interface
├── tools/       # Agent tools (file read/write, shell)
├── docs/        # GitHub Pages landing page
└── requirements.txt
## Roadmap

- [ ] Streaming responses
- [ ] Conversation history
- [ ] Tool use (file access, shell commands)
- [ ] PyInstaller binary releases

## Contributing

PRs and issues welcome. Branch from `main`, write a clear commit message, open a PR.

## License

MIT

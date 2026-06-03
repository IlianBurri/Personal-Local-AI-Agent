# Arca

*Your models. Your machine. Your rules.*

Arca is a lightweight desktop AI agent that connects to any LLM — OpenAI, Anthropic, or a local Ollama instance — through a single clean interface. Switch providers from the sidebar without touching code.

## Quick start

```bash
git clone https://github.com/IlianBurri/arca.git
cd arca
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m ui.main
```

## Provider setup

On first launch Arca asks for your provider and API key. Everything is saved locally at `~/.config/arca/config.json` — nothing leaves your machine.

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

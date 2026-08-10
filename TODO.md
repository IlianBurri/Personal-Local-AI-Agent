# TODO - arca

## Done — Web-UI migration (PyQt6 → React/Vite + PyWebView)
- [x] Replaced the PyQt6 UI with a React + Vite frontend (`ui/web/`), Codex-inspired dark design
- [x] Native window via PyWebView with automatic browser fallback
- [x] Zero-setup launchers: `start.sh` (macOS/Linux) and `start.bat` (Windows)
- [x] Flask server (`server/`) with SSE streaming, stop support, auto-titling
- [x] Provider & model switching in the header, Ollama reachability status dot
- [x] Markdown rendering with syntax highlighting + 1-click code copy
- [x] Tool use wired end-to-end (shell / files / web search) with live tool pills
- [x] Settings panel: API keys, default models, temperature, max tokens, theme
- [x] Chat history grouped by day, rename/delete, regenerate, typing indicator
- [x] Removed all PyQt6 code and Vercel leftovers (`api/`, `vercel.json`)
- [x] Tests: API endpoints, SSE flow, tool loop, providers — 14 passing

## Next
- [ ] Verify the PyInstaller build (`pyinstaller arca.spec`) on each OS
- [x] Harden the tool loop against hostile tool output / runaway rounds
      (output truncation markers, configurable round cap via `ARCA_MAX_TOOL_ROUNDS`,
      forced wrap-up answer + `notice` event instead of a silent cut)
- [x] Agentic toolset: `edit_file`, `grep_code`, `fetch_url`, `git_status`, line-ranged reads
- [ ] Add tool-use confirmation toggle per chat
- [ ] End-to-end test of the PyWebView window on Windows/macOS

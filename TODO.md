# TODO - arca

## Phase 0 — Code review & bug inventory (no edits)
- [ ] Read remaining core/UI/provider/tooling files to build a complete bug list.
- [ ] Identify any import/runtime errors and provider selection gaps.
- [ ] Identify any desktop→web leakage (web server/browser launch).

## Phase 1 — Fix highest-priority bugs (core functionality)
- [x] Fix `core/storage.py` (align/retire legacy JSON storage).
- [ ] Ensure streaming errors propagate to UI (`StreamWorker.error`).

- [ ] Fix provider selection/API key handling so OpenAI/Anthropic/Ollama actually route correctly.
- [ ] Verify thread safety: QThread + worker lifetime + UI updates.
- [ ] Verify persistence works: chat creation, message saving, chat reload.

## Phase 2 — Enforce desktop-only (no localhost web UI)
- [ ] Remove/disable embedded web chat widget in `indexforWebsite.html`.
- [ ] Ensure entrypoints only start PyQt desktop UI.
- [ ] Remove any unused web-starting code paths if present.

## Phase 3 — UI redesign (polished + functional)
- [ ] Add settings panel (provider + keys + generation params).
- [ ] Add controls: stop generation, regenerate last response, clear chat.
- [ ] Improve message rendering (markdown + code fences) and add copy-for-all.
- [ ] Add status bar (model/provider, token count, connection status).
- [ ] Add keyboard shortcuts (Enter send, Ctrl+N new chat, etc.).
- [ ] Improve auto-scroll / token batching for performance.

## Phase 4 — Tests / verification
- [ ] Add `unittest` based smoke tests for storage/provider routing.
- [ ] Manual run: `python3 run.py` and verify end-to-end chat.


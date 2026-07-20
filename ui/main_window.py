"""Arca main application window — wires sidebar, chat, composer, and status bar."""

from __future__ import annotations

from PyQt6 import QtCore, QtGui, QtWidgets

from core.client_factory import MissingAPIKey, build_client
from core.config import get_max_tokens, get_temperature, load_config
from core.database import ChatRepository, SQLiteManager
from core.workers.stream_worker import StreamWorker
from ui.theme import ACCENT_PRESETS, Theme
from ui.widgets.chat_area import ChatArea
from ui.widgets.chat_input import ChatInput
from ui.widgets.model_selector import ModelSelector
from ui.widgets.settings_dialog import SettingsDialog
from ui.widgets.sidebar import Sidebar


class MainWindow(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Arca")
        self.resize(1280, 800)

        self.config = load_config()
        self.db = SQLiteManager()
        self.repo = ChatRepository(self.db)
        self.current_chat_id: int | None = None
        self.current_response = ""
        self.assistant_widget = None
        self._word_count = 0
        self._generating = False
        self._thread = None
        self._worker = None

        # Default to dark + graphite accent.
        self.theme = Theme(dark=True, accent=ACCENT_PRESETS["graphite"])

        self._build_ui()
        self._connect_signals()
        self._setup_shortcuts()
        self._apply_theme_styles()
        self._init()

    # ------------------------------------------------------------------
    # Build
    # ------------------------------------------------------------------
    def _build_ui(self):
        self.root = QtWidgets.QWidget()
        self.setCentralWidget(self.root)

        self.splitter = QtWidgets.QSplitter(
            QtCore.Qt.Orientation.Horizontal
        )
        self.splitter.setChildrenCollapsible(False)
        self.splitter.setHandleWidth(1)

        root_layout = QtWidgets.QHBoxLayout(self.root)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)
        root_layout.addWidget(self.splitter)

        # Sidebar
        self.sidebar = Sidebar(self.theme)
        self.splitter.addWidget(self.sidebar)

        # Center column
        center = QtWidgets.QWidget()
        center_layout = QtWidgets.QVBoxLayout(center)
        center_layout.setContentsMargins(0, 0, 0, 0)
        center_layout.setSpacing(0)

        self.model_selector = ModelSelector(self.theme, self.config)
        center_layout.addWidget(self.model_selector)

        self.chat = ChatArea(
            self.theme, on_chip_clicked=self._handle_chip_clicked
        )
        self.chat.regenerate_requested.connect(self._regenerate_response)
        center_layout.addWidget(self.chat, 1)

        # Composer row — wrapped with stretches to keep card centered.
        composer_row = QtWidgets.QHBoxLayout()
        composer_row.setContentsMargins(0, 0, 0, 0)
        composer_row.setSpacing(0)
        composer_row.addStretch()
        self.chat_input = ChatInput(self.theme)
        composer_row.addWidget(self.chat_input)
        composer_row.addStretch()
        center_layout.addLayout(composer_row)

        self.splitter.addWidget(center)
        self.splitter.setSizes([260, 1020])

        # Status bar
        self.status_bar = self.statusBar()
        self.status_model_lbl = QtWidgets.QLabel()
        self.status_model_lbl.setObjectName("statusModel")
        self.status_indicator_lbl = QtWidgets.QLabel()
        self.status_indicator_lbl.setObjectName("statusIndicator")
        self.status_bar.addPermanentWidget(self.status_model_lbl)
        self.status_bar.addPermanentWidget(self.status_indicator_lbl)

    def _connect_signals(self):
        self.chat_input.submitted.connect(self.send_message)
        self.chat_input.stop_requested.connect(self.stop_generation)
        self.sidebar.new_chat_clicked.connect(self.create_new_chat)
        self.sidebar.chat_selected.connect(self.open_chat)
        self.sidebar.chat_deleted.connect(self.delete_chat)
        self.sidebar.chat_renamed.connect(self.rename_chat)
        self.model_selector.theme_changed.connect(self.on_theme_changed)
        self.model_selector.settings_requested.connect(self.open_settings)

    def _setup_shortcuts(self):
        # Ctrl+N → New chat
        shortcut_new = QtGui.QShortcut(
            QtGui.QKeySequence("Ctrl+N"), self
        )
        shortcut_new.activated.connect(self.create_new_chat)

        # Escape → Stop generation (only when generating)
        shortcut_stop = QtGui.QShortcut(
            QtGui.QKeySequence("Escape"), self
        )
        shortcut_stop.activated.connect(self._stop_shortcut)

        # Ctrl+Shift+Delete → Clear current chat messages
        shortcut_clear = QtGui.QShortcut(
            QtGui.QKeySequence("Ctrl+Shift+Delete"), self
        )
        shortcut_clear.activated.connect(self._clear_chat)

    def _stop_shortcut(self):
        if self._generating:
            self.stop_generation()

    def _clear_chat(self):
        if self.current_chat_id:
            self.chat.clear()
            self.repo.delete_chat(self.current_chat_id)
            self.create_new_chat()

    def _apply_theme_styles(self):
        t = self.theme
        self.setStyleSheet(t.main_window_css())
        self.root.setStyleSheet(f"background: {t.bg_app};")
        self.splitter.setStyleSheet(
            f"QSplitter::handle {{ background: {t.border_soft}; }}"
        )
        self.status_bar.setStyleSheet(t.status_bar_css())

    def on_theme_changed(self, new_theme: Theme):
        self.theme = new_theme
        self._apply_theme_styles()
        self.sidebar.apply_theme(self.theme)
        self.model_selector.apply_theme(self.theme)
        self.chat_input.apply_theme(self.theme)
        self.chat.apply_theme(self.theme)
        self._update_status()
        self.update()

    # ------------------------------------------------------------------
    # Init
    # ------------------------------------------------------------------
    def _init(self):
        self.model_selector.initialize_from_config()
        self.load_chats()
        if self.current_chat_id is None:
            self.create_new_chat()
        else:
            self.sidebar.set_active(self.current_chat_id)
            self.open_chat(self.current_chat_id)
        self._update_status()

    def load_chats(self):
        self.sidebar.clear()
        chats = self.repo.get_all_chats()
        for chat in chats:
            self.sidebar.add_chat(
                chat["id"], chat["title"], chat.get("created_at")
            )
        if chats:
            self.current_chat_id = chats[0]["id"]

    def create_new_chat(self):
        chat_id = self.repo.create_chat("New chat")
        self.current_chat_id = chat_id
        self.chat.clear()
        self.load_chats()
        self.sidebar.set_active(chat_id)

    def open_chat(self, chat_id: int):
        self.current_chat_id = chat_id
        self.chat.clear()
        messages = self.repo.get_chat_messages(chat_id)
        for msg in messages:
            self.chat.add_message(msg["role"], msg["content"])
        self.sidebar.set_active(chat_id)

    def delete_chat(self, chat_id: int):
        self.repo.delete_chat(chat_id)
        was_current = chat_id == self.current_chat_id
        self.load_chats()
        if was_current:
            chats = self.repo.get_all_chats()
            if chats:
                self.open_chat(chats[0]["id"])
            else:
                self.create_new_chat()

    def rename_chat(self, chat_id: int, new_title: str):
        self.repo.rename_chat(chat_id, new_title)

    # ------------------------------------------------------------------
    # Chips
    # ------------------------------------------------------------------
    def _handle_chip_clicked(self, label: str):
        """Fill the composer with the chip's text; user presses Enter to send."""
        self.chat_input.set_text(label)

    # ------------------------------------------------------------------
    # Messaging
    # ------------------------------------------------------------------
    def send_message(self, text: str):
        if not self.current_chat_id or self._generating:
            return

        self.chat.add_message("user", text)
        self.repo.add_user_message(self.current_chat_id, text)

        history = self.repo.get_chat_messages(self.current_chat_id)
        messages = [
            {"role": m["role"], "content": m["content"]}
            for m in history
        ]

        try:
            client = build_client(
                self.model_selector.current_provider(),
                self.model_selector.current_model(),
                self.config,
            )
        except MissingAPIKey as e:
            self.chat.add_message(
                "assistant",
                f"**API key required**\n\nNo API key configured for "
                f"{e.provider.title()}. Click \u201c+ Add key\u201d in the "
                f"top bar or set the `{e.provider.upper()}_API_KEY` "
                f"environment variable.",
            )
            return
        except Exception as e:
            self.chat.add_message(
                "assistant",
                f"**Connection error**\n\n{e}\n\nMake sure your provider "
                f"is running and accessible.",
            )
            return

        self.current_response = ""
        self._word_count = 0
        self._generating = True
        self.chat_input.set_generating(True)
        self.chat.show_typing(True)
        self._update_status()

        # Build generation kwargs from settings
        gen_kwargs = {
            "temperature": get_temperature(self.config),
            "max_tokens": get_max_tokens(self.config),
        }

        # Create an empty assistant message widget now so streaming tokens
        # have a place to land immediately.
        self.assistant_widget = self.chat.add_message("assistant", "")

        self._thread = QtCore.QThread()
        self._worker = StreamWorker(client, messages, kwargs=gen_kwargs)
        self._worker.moveToThread(self._thread)
        self._worker.token.connect(self._on_token)
        self._worker.error.connect(self._on_error)
        self._worker.finished.connect(self._on_finished)
        self._worker.finished.connect(self._thread.quit)
        self._thread.started.connect(self._worker.run)

        self._thread.finished.connect(self._thread.deleteLater)
        self._thread.start()

    def stop_generation(self):
        """Stop the current generation cleanly."""
        if not self._generating:
            return
        if self._worker:
            self._worker.stop()
        if self._thread and self._thread.isRunning():
            self._thread.quit()
        # Cleanup happens via on_finished → _cleanup_generation

    def _on_token(self, token: str):
        # Hide typing indicator on first token
        if self._generating:
            self.chat.show_typing(False)
        self.current_response += token
        self._word_count += len(token.split())

        if self.assistant_widget:
            self.assistant_widget.append_text(token)

        if self._word_count == 10:
            self._auto_title()

    def _on_finished(self):
        if self.current_response.strip():
            self.repo.add_assistant_message(
                self.current_chat_id, self.current_response
            )
        self._cleanup_generation()

    def _on_error(self, message: str):
        if not message:
            message = "Unknown error"
        # Don't add duplicate error if we already have partial content
        if not self.current_response.strip():
            self.chat.add_message(
                "assistant",
                f"**Error**\n\n{message}\n\nCheck your connection and "
                f"provider settings, then try again.",
            )
        self._cleanup_generation()

    def _cleanup_generation(self):
        self._generating = False
        self._worker = None
        self._thread = None
        self.assistant_widget = None
        self.chat_input.set_generating(False)
        self.chat.show_typing(False)
        self._update_status()

    def _auto_title(self):
        chats = {c["id"]: c for c in self.repo.get_all_chats()}
        if self.current_chat_id not in chats:
            return
        if chats[self.current_chat_id]["title"] != "New chat":
            return
        messages = self.repo.get_chat_messages(self.current_chat_id)
        for msg in messages:
            if msg["role"] == "user":
                content = msg["content"].strip()
                if not content:
                    return
                title = content[:40].strip()
                if len(content) > 40:
                    title += "\u2026"
                self.repo.rename_chat(self.current_chat_id, title)
                self.sidebar.update_title(self.current_chat_id, title)
                return

    # ------------------------------------------------------------------
    # Regenerate
    # ------------------------------------------------------------------
    def _regenerate_response(self, widget):
        """Remove the last assistant response and re-send the conversation."""
        if not self.current_chat_id or self._generating:
            return

        # Get current messages from DB
        all_msgs = self.repo.get_chat_messages(self.current_chat_id)
        if not all_msgs:
            return

        # Safety guard: only regenerate if the clicked widget is the last
        # assistant message. Non-last regenerate is a noop.
        count = self.chat.column_vbox.count()
        if count == 0:
            return
        last_item = self.chat.column_vbox.itemAt(count - 1)
        last_widget = last_item.widget() if last_item else None
        if widget is not last_widget:
            return

        # Find the last assistant message in the DB and delete it
        assistant_idx = None
        for i in range(len(all_msgs) - 1, -1, -1):
            if all_msgs[i]["role"] == "assistant":
                assistant_idx = i
                break

        if assistant_idx is None:
            return

        # Delete from DB
        self.repo.delete_last_assistant_message(self.current_chat_id)

        # Remove from UI
        self.chat.remove_widget(widget)

        # Rebuild conversation messages (everything before the removed assistant)
        remaining = all_msgs[:assistant_idx]
        messages = [
            {"role": m["role"], "content": m["content"]}
            for m in remaining
        ]

        if not messages:
            return

        # Send to LLM
        try:
            client = build_client(
                self.model_selector.current_provider(),
                self.model_selector.current_model(),
                self.config,
            )
        except MissingAPIKey as e:
            self.chat.add_message(
                "assistant",
                f"**API key required**\n\nNo API key configured for "
                f"{e.provider.title()}. Click \u201c+ Add key\u201d in the "
                f"top bar or set the `{e.provider.upper()}_API_KEY` "
                f"environment variable.",
            )
            return
        except Exception as e:
            self.chat.add_message(
                "assistant",
                f"**Connection error**\n\n{e}\n\nMake sure your provider "
                f"is running and accessible.",
            )
            return

        gen_kwargs = {
            "temperature": get_temperature(self.config),
            "max_tokens": get_max_tokens(self.config),
        }

        self.current_response = ""
        self._word_count = 0
        self._generating = True
        self.chat_input.set_generating(True)
        self.chat.show_typing(True)
        self._update_status()

        self.assistant_widget = self.chat.add_message("assistant", "")

        self._thread = QtCore.QThread()
        self._worker = StreamWorker(client, messages, kwargs=gen_kwargs)
        self._worker.moveToThread(self._thread)
        self._worker.token.connect(self._on_token)
        self._worker.error.connect(self._on_error)
        self._worker.finished.connect(self._on_finished)
        self._worker.finished.connect(self._thread.quit)
        self._thread.started.connect(self._worker.run)

        self._thread.finished.connect(self._thread.deleteLater)
        self._thread.start()

    # ------------------------------------------------------------------
    # Settings
    # ------------------------------------------------------------------
    def open_settings(self):
        dialog = SettingsDialog(self.config, self.theme, self)
        dialog.apply_theme(self.theme)
        if dialog.exec() == QtWidgets.QDialog.DialogCode.Accepted:
            # Reload config and refresh UI elements
            self.model_selector._refresh_provider_state(initial=False)
            self._update_status()

    # ------------------------------------------------------------------
    # Status bar
    # ------------------------------------------------------------------
    def _update_status(self):
        provider = self.model_selector.current_provider()
        model = self.model_selector.current_model()
        parts = []
        if provider:
            parts.append(provider.title())
        if model:
            parts.append(model)
        label = " \u00b7 ".join(parts) if parts else "No provider selected"
        self.status_model_lbl.setText(f"  {label}  ")

        if self._generating:
            self.status_indicator_lbl.setText("  Generating\u2026  ")
        else:
            self.status_indicator_lbl.setText("  Ready  ")

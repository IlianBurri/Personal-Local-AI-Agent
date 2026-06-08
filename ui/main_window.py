import os

from PyQt6 import QtWidgets, QtCore

from core.config import load_config, save_config
from core.providers import AnthropicClient, OllamaClient, OpenAIClient
from core.workers.stream_worker import StreamWorker
from core.database import SQLiteManager, ChatRepository

from ui.widgets.sidebar import Sidebar
from ui.widgets.chat_area import ChatArea
from ui.widgets.chat_input import ChatInput
from ui.widgets.model_selector import ModelSelector


class MainWindow(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("Arca")
        self.resize(1440, 920)
        self.setMinimumSize(980, 680)
        self.setStyleSheet("background: #0f172a;")

        self.config = load_config()
        self.db = SQLiteManager()
        self.repo = ChatRepository(self.db)
        self.current_chat_id = None
        self.current_response = ""
        self.assistant_widget = None
        self.worker = None
        self.thread = None
        self._is_generating = False
        self._was_stopped = False

        self._build_ui()
        self._connect_signals()
        self._init()

    def _build_ui(self):
        root = QtWidgets.QWidget()
        root.setStyleSheet("background: #0f172a;")
        self.setCentralWidget(root)

        layout = QtWidgets.QHBoxLayout(root)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.sidebar = Sidebar()
        layout.addWidget(self.sidebar)

        divider = QtWidgets.QFrame()
        divider.setFixedWidth(1)
        divider.setStyleSheet("background: #263244;")
        layout.addWidget(divider)

        center = QtWidgets.QWidget()
        center.setStyleSheet("background: #0f172a;")
        center_layout = QtWidgets.QVBoxLayout(center)
        center_layout.setContentsMargins(0, 0, 0, 0)
        center_layout.setSpacing(0)

        self.model_selector = ModelSelector(self.config)
        center_layout.addWidget(self.model_selector)

        self.chat = ChatArea()
        center_layout.addWidget(self.chat, 1)

        self.chat_input = ChatInput()
        center_layout.addWidget(self.chat_input)

        layout.addWidget(center, 1)

    def _connect_signals(self):
        self.chat_input.submitted.connect(self.send_message)
        self.chat_input.stop_requested.connect(self.stop_generation)
        self.model_selector.settings_requested.connect(self.open_settings)
        self.sidebar.new_chat_clicked.connect(self.create_new_chat)
        self.sidebar.chat_selected.connect(self.open_chat)
        self.sidebar.chat_deleted.connect(self.delete_chat)
        self.sidebar.chat_renamed.connect(self.rename_chat)

    def _init(self):
        self.load_chats()
        if self.current_chat_id is None:
            self.create_new_chat()
        else:
            self.sidebar.set_active(self.current_chat_id)
            self.open_chat(self.current_chat_id)
        self.chat_input.focus_input()

    def load_chats(self):
        self.sidebar.clear()
        chats = self.repo.get_all_chats()
        for chat in chats:
            self.sidebar.add_chat(chat["id"], chat["title"])
        if chats:
            self.current_chat_id = chats[0]["id"]

    def create_new_chat(self):
        if self._is_generating:
            self.chat.add_system_notice("Finish or stop the current response before starting a new chat.")
            return
        chat_id = self.repo.create_chat("New Chat")
        self.current_chat_id = chat_id
        self.chat.clear()
        self.load_chats()
        self.sidebar.set_active(chat_id)
        self.chat_input.focus_input()

    def open_chat(self, chat_id: int):
        if self._is_generating:
            self.chat.add_system_notice("Finish or stop the current response before switching chats.")
            return
        self.current_chat_id = chat_id
        self.chat.clear()
        messages = self.repo.get_chat_messages(chat_id)
        for msg in messages:
            self.chat.add_message(msg["role"], msg["content"])
        self.sidebar.set_active(chat_id)
        self.chat_input.focus_input()

    def delete_chat(self, chat_id: int):
        if self._is_generating and chat_id == self.current_chat_id:
            self.stop_generation()
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
        title = new_title.strip() or "New Chat"
        self.repo.rename_chat(chat_id, title)
        self.sidebar.update_title(chat_id, title)

    def send_message(self, text: str):
        if not self.current_chat_id or self._is_generating:
            return

        try:
            client, kwargs = self._make_client()
        except ValueError as exc:
            self.chat.add_system_notice(str(exc))
            self.open_settings()
            return
        except Exception as exc:
            self.chat.add_system_notice(f"Provider setup failed: {exc}")
            return

        self.chat.add_message("user", text)
        self.repo.add_user_message(self.current_chat_id, text)

        history = self.repo.get_chat_messages(self.current_chat_id)
        messages = [{"role": m["role"], "content": m["content"]} for m in history]

        self.current_response = ""
        self._was_stopped = False
        self.assistant_widget = self.chat.add_message("assistant", "")
        self.chat_input.set_busy(True)
        self._is_generating = True

        self.thread = QtCore.QThread()
        self.worker = StreamWorker(client, messages, kwargs)
        self.worker.moveToThread(self.thread)
        self.worker.token.connect(self.on_token)
        self.worker.error.connect(self.on_error)
        self.worker.finished.connect(self.on_finished)
        self.worker.finished.connect(self.thread.quit)
        self.worker.finished.connect(self.worker.deleteLater)
        self.thread.finished.connect(self.thread.deleteLater)
        self.thread.started.connect(self.worker.run)
        self.thread.start()

        self._auto_title()

    def _make_client(self):
        provider = self.model_selector.current_provider()
        model = self.model_selector.current_model()
        self.config["provider"] = provider
        self.config.setdefault("providers", {}).setdefault(provider, {})["model"] = model
        save_config(self.config)

        if provider == "ollama":
            base_url = self.config.get("providers", {}).get("ollama", {}).get(
                "base_url",
                "http://localhost:11434",
            )
            return OllamaClient(base_url=base_url, model=model), {}

        if provider == "openai":
            api_key = (
                self.config.get("providers", {}).get("openai", {}).get("api_key")
                or os.environ.get("OPENAI_API_KEY")
            )
            if not api_key:
                raise ValueError("OpenAI needs an API key. Add it in Settings.")
            return OpenAIClient(api_key=api_key, model=model), {}

        if provider == "anthropic":
            api_key = (
                self.config.get("providers", {}).get("anthropic", {}).get("api_key")
                or os.environ.get("ANTHROPIC_API_KEY")
            )
            if not api_key:
                raise ValueError("Anthropic needs an API key. Add it in Settings.")
            return AnthropicClient(api_key=api_key, model=model), {"max_tokens": 2048}

        raise ValueError(f"Unknown provider: {provider}")

    def on_token(self, token: str):
        if self._was_stopped:
            return
        self.current_response += token
        if self.assistant_widget:
            self.assistant_widget.append_text(token)
        self.chat.scroll_to_bottom()

    def on_error(self, message: str):
        if not self._was_stopped:
            self.chat.add_system_notice(f"Generation failed: {message}")

    def on_finished(self):
        if self.current_response.strip() and not self._was_stopped:
            self.repo.add_assistant_message(
                self.current_chat_id,
                self.current_response.strip(),
            )
        elif self._was_stopped:
            self.chat.add_system_notice("Generation stopped.")

        self._finish_active_generation(notice=False)

    def stop_generation(self):
        if not self._is_generating:
            return
        self._was_stopped = True
        if self.worker:
            self.worker.cancel()
        self.chat_input.set_busy(False)

    def _finish_active_generation(self, notice=True):
        self._is_generating = False
        self.chat_input.set_busy(False)
        self.worker = None
        self.thread = None
        if notice:
            self.chat_input.focus_input()

    def _auto_title(self):
        messages = self.repo.get_chat_messages(self.current_chat_id)
        first_user = next((m for m in messages if m["role"] == "user"), None)
        if not first_user:
            return
        title = first_user["content"].replace("\n", " ").strip()
        if len(title) > 46:
            title = title[:43].rstrip() + "..."
        if title:
            self.repo.rename_chat(self.current_chat_id, title)
            self.sidebar.update_title(self.current_chat_id, title)

    def open_settings(self):
        dialog = SettingsDialog(self.config, self)
        if dialog.exec() == QtWidgets.QDialog.DialogCode.Accepted:
            self.config = dialog.updated_config()
            save_config(self.config)
            self.model_selector.update_config(self.config)

    def closeEvent(self, event):
        self.stop_generation()
        self.db.close()
        super().closeEvent(event)


class SettingsDialog(QtWidgets.QDialog):
    def __init__(self, config, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Arca settings")
        self.setModal(True)
        self.resize(520, 360)
        self.config = {
            **(config or {}),
            "providers": dict((config or {}).get("providers", {})),
        }

        self.setStyleSheet("""
            QDialog {
                background: #0f172a;
                color: #f8fafc;
            }
            QLabel {
                color: #cbd5e1;
                font-size: 13px;
            }
            QLineEdit, QComboBox {
                background: #151f31;
                color: #f8fafc;
                border: 1px solid #334155;
                border-radius: 7px;
                padding: 8px;
                font-size: 13px;
            }
            QPushButton {
                background: #1d4ed8;
                color: #f8fafc;
                border: none;
                border-radius: 7px;
                padding: 8px 12px;
                font-weight: 800;
            }
            QPushButton:hover {
                background: #2563eb;
            }
        """)

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(14)

        form = QtWidgets.QFormLayout()
        form.setSpacing(12)

        self.provider = QtWidgets.QComboBox()
        self.provider.addItems(["ollama", "openai", "anthropic"])
        self.provider.setCurrentText(self.config.get("provider") or "ollama")
        form.addRow("Default provider", self.provider)

        providers = self.config.setdefault("providers", {})
        ollama = providers.setdefault("ollama", {})
        openai = providers.setdefault("openai", {})
        anthropic = providers.setdefault("anthropic", {})

        self.ollama_url = QtWidgets.QLineEdit(ollama.get("base_url", "http://localhost:11434"))
        form.addRow("Ollama URL", self.ollama_url)

        self.openai_key = QtWidgets.QLineEdit(openai.get("api_key", ""))
        self.openai_key.setEchoMode(QtWidgets.QLineEdit.EchoMode.Password)
        form.addRow("OpenAI key", self.openai_key)

        self.anthropic_key = QtWidgets.QLineEdit(anthropic.get("api_key", ""))
        self.anthropic_key.setEchoMode(QtWidgets.QLineEdit.EchoMode.Password)
        form.addRow("Anthropic key", self.anthropic_key)

        layout.addLayout(form)
        layout.addStretch()

        buttons = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.StandardButton.Save
            | QtWidgets.QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def updated_config(self):
        self.config["provider"] = self.provider.currentText()
        self.config.setdefault("providers", {}).setdefault("ollama", {})[
            "base_url"
        ] = self.ollama_url.text().strip() or "http://localhost:11434"
        self.config.setdefault("providers", {}).setdefault("openai", {})[
            "api_key"
        ] = self.openai_key.text().strip()
        self.config.setdefault("providers", {}).setdefault("anthropic", {})[
            "api_key"
        ] = self.anthropic_key.text().strip()
        return self.config

from PyQt6 import QtWidgets, QtCore

from core.config import load_config
from core.providers import OllamaClient
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
        self.resize(1400, 900)
        self.setStyleSheet("background: #0d1117;")

        self.config = load_config()
        self.db = SQLiteManager()
        self.repo = ChatRepository(self.db)
        self.current_chat_id = None
        self.current_response = ""
        self.assistant_widget = None
        self._word_count = 0

        self._build_ui()
        self._connect_signals()
        self._init()

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------

    def _build_ui(self):
        root = QtWidgets.QWidget()
        root.setStyleSheet("background: #0d1117;")
        self.setCentralWidget(root)

        layout = QtWidgets.QHBoxLayout(root)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Sidebar
        self.sidebar = Sidebar()
        layout.addWidget(self.sidebar)

        # Divider
        div = QtWidgets.QFrame()
        div.setFixedWidth(1)
        div.setStyleSheet("background: #1e293b;")
        layout.addWidget(div)

        # Center
        center = QtWidgets.QWidget()
        center.setStyleSheet("background: #0d1117;")
        center_layout = QtWidgets.QVBoxLayout(center)
        center_layout.setContentsMargins(0, 0, 0, 0)
        center_layout.setSpacing(0)

        self.model_selector = ModelSelector()
        center_layout.addWidget(self.model_selector)

        self.chat = ChatArea()
        center_layout.addWidget(self.chat, 1)

        self.chat_input = ChatInput()
        center_layout.addWidget(self.chat_input)

        layout.addWidget(center, 1)

    def _connect_signals(self):
        self.chat_input.submitted.connect(self.send_message)
        self.sidebar.new_chat_clicked.connect(self.create_new_chat)
        self.sidebar.chat_selected.connect(self.open_chat)
        self.sidebar.chat_deleted.connect(self.delete_chat)
        self.sidebar.chat_renamed.connect(self.rename_chat)

    # ------------------------------------------------------------------
    # Init
    # ------------------------------------------------------------------

    def _init(self):
        self.load_chats()
        if self.current_chat_id is None:
            self.create_new_chat()
        else:
            self.sidebar.set_active(self.current_chat_id)
            self.open_chat(self.current_chat_id)

    # ------------------------------------------------------------------
    # Chat Management
    # ------------------------------------------------------------------

    def load_chats(self):
        self.sidebar.clear()
        chats = self.repo.get_all_chats()
        for chat in chats:
            self.sidebar.add_chat(chat["id"], chat["title"])
        if chats:
            self.current_chat_id = chats[0]["id"]

    def create_new_chat(self):
        chat_id = self.repo.create_chat("New Chat")
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
    # Messaging
    # ------------------------------------------------------------------

    def send_message(self, text: str):
        if not self.current_chat_id:
            return

        self.chat.add_message("user", text)
        self.repo.add_user_message(self.current_chat_id, text)

        history = self.repo.get_chat_messages(self.current_chat_id)
        messages = [{"role": m["role"], "content": m["content"]} for m in history]

        model = self.model_selector.current_model()
        client = OllamaClient(model=model)

        self.current_response = ""
        self._word_count = 0

        self.thread = QtCore.QThread()
        self.worker = StreamWorker(client, messages)
        self.worker.moveToThread(self.thread)
        self.worker.token.connect(self.on_token)
        self.worker.finished.connect(self.on_finished)
        self.worker.finished.connect(self.thread.quit)
        self.thread.started.connect(self.worker.run)

        self.assistant_widget = self.chat.add_message("assistant", "")
        self.thread.start()

    def on_token(self, token: str):
        self.current_response += token
        self._word_count += len(token.split())

        if self.assistant_widget:
            self.assistant_widget.append_text(token)

        # Auto-title after ~10 words
        if self._word_count == 10:
            self._auto_title()

    def on_finished(self):
        if self.current_response.strip():
            self.repo.add_assistant_message(
                self.current_chat_id,
                self.current_response
            )

    def _auto_title(self):
        """Generate title from first user message."""
        messages = self.repo.get_chat_messages(self.current_chat_id)
        for msg in messages:
            if msg["role"] == "user":
                title = msg["content"][:40].strip()
                if len(msg["content"]) > 40:
                    title += "…"
                self.repo.rename_chat(self.current_chat_id, title)
                self.sidebar.update_title(self.current_chat_id, title)
                break

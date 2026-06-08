import sys
import os
import json
import time
import threading
from pathlib import Path

from PyQt6 import QtWidgets, QtCore, QtGui

try:
    from pygments import highlight
    from pygments.lexers import get_lexer_by_name, guess_lexer, TextLexer
    from pygments.formatters import HtmlFormatter
    PYGMENTS_AVAILABLE = True
except Exception:
    PYGMENTS_AVAILABLE = False

from core.config import load_config, save_config
from core.clients import OpenAIClient, AnthropicClient, OllamaClient


APP_BG = "#F5F4F0"
TEXT_COLOR = "#1A1A18"


def ensure_conversations_dir() -> Path:
    p = Path.home() / ".config" / "arca" / "conversations"
    p.mkdir(parents=True, exist_ok=True)
    return p


def safe_filename() -> str:
    return f"conv_{int(time.time())}.json"


class StreamWorker(QtCore.QObject):
    token = QtCore.pyqtSignal(str)
    finished = QtCore.pyqtSignal()
    error = QtCore.pyqtSignal(str)

    def __init__(self, client, messages, kwargs=None):
        super().__init__()
        self.client = client
        self.messages = messages
        self.kwargs = kwargs or {}

    @QtCore.pyqtSlot()
    def run(self):
        try:
            for tok in self.client.stream_chat(self.messages, **self.kwargs):
                if tok:
                    self.token.emit(str(tok))
        except Exception as e:
            self.error.emit(str(e))
        finally:
            self.finished.emit()


class MessageWidget(QtWidgets.QWidget):
    def __init__(self, role: str, content: str):
        super().__init__()
        self.role = role
        self.content = content
        self._setup()

    def _setup(self):
        layout = QtWidgets.QVBoxLayout(self)

        if "```" not in self.content:
            self.lbl = QtWidgets.QLabel(self.content)
            self.lbl.setWordWrap(True)
            layout.addWidget(self.lbl)
            return

        parts = self.content.split("```")

        for i, part in enumerate(parts):
            if i % 2 == 0:
                if part.strip():
                    lbl = QtWidgets.QLabel(part.strip())
                    lbl.setWordWrap(True)
                    layout.addWidget(lbl)
            else:
                code_text = part

                if "\n" in part:
                    _, code_text = part.split("\n", 1)

                code = QtWidgets.QPlainTextEdit()
                code.setPlainText(code_text)
                code.setReadOnly(True)

                font = QtGui.QFontDatabase.systemFont(
                    QtGui.QFontDatabase.SystemFont.FixedFont
                )
                font.setPointSize(11)
                code.setFont(font)
                code.setMaximumHeight(200)

                copy_btn = QtWidgets.QPushButton("Copy")

                def make_copy(widget=code):
                    def _():
                        QtWidgets.QApplication.clipboard().setText(widget.toPlainText())
                    return _

                copy_btn.clicked.connect(make_copy())

                row = QtWidgets.QHBoxLayout()
                row.addWidget(code)
                row.addWidget(copy_btn)
                layout.addLayout(row)

    def append_text(self, tok: str):
        if hasattr(self, "lbl"):
            self.lbl.setText(self.lbl.text() + tok)


class ChatArea(QtWidgets.QScrollArea):
    def __init__(self):
        super().__init__()
        self.setWidgetResizable(True)
        self.container = QtWidgets.QWidget()
        self.layout = QtWidgets.QVBoxLayout(self.container)
        self.layout.addStretch()
        self.setWidget(self.container)

    def add_message(self, role, text):
        w = MessageWidget(role, text)
        self.layout.insertWidget(self.layout.count() - 1, w)
        return w

    def clear(self):
        while self.layout.count() > 1:
            item = self.layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()


class MainWindow(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Arca")
        self.resize(1000, 700)

        self.config = load_config()
        self.current_file = None

        root = QtWidgets.QWidget()
        self.setCentralWidget(root)
        layout = QtWidgets.QHBoxLayout(root)

        # LEFT
        self.chat_list = QtWidgets.QListWidget()
        layout.addWidget(self.chat_list, 1)

        # CENTER
        center = QtWidgets.QVBoxLayout()
        layout.addLayout(center, 4)

        self.chat = ChatArea()
        center.addWidget(self.chat)

        self.input = QtWidgets.QLineEdit()
        self.send = QtWidgets.QPushButton("Send")
        row = QtWidgets.QHBoxLayout()
        row.addWidget(self.input)
        row.addWidget(self.send)
        center.addLayout(row)

        self.send.clicked.connect(self.send_message)

    def send_message(self):
        text = self.input.text().strip()
        if not text:
            return

        self.input.clear()
        self.chat.add_message("user", text)

        client = OllamaClient()

        self.thread = QtCore.QThread()
        self.worker = StreamWorker(client, [{"role": "user", "content": text}])

        self.worker.moveToThread(self.thread)
        self.worker.token.connect(self.on_token)
        self.worker.finished.connect(self.thread.quit)
        self.thread.started.connect(self.worker.run)

        self.assistant_widget = self.chat.add_message("assistant", "")
        self.thread.start()

    def on_token(self, tok):
        if hasattr(self, "assistant_widget"):
            self.assistant_widget.append_text(tok)


def main():
    app = QtWidgets.QApplication(sys.argv)
    w = MainWindow()
    w.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
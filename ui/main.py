import sys
import threading
from PyQt6 import QtWidgets, QtCore, QtGui

from core.config import load_config, save_config
from core.clients import OpenAIClient, AnthropicClient, OllamaClient


class StreamWorker(QtCore.QObject):
    chunk = QtCore.pyqtSignal(str)
    finished = QtCore.pyqtSignal()

    def __init__(self, client, messages, kwargs=None):
        super().__init__()
        self.client = client
        self.messages = messages
        self.kwargs = kwargs or {}

    def run(self):
        try:
            for token in self.client.stream_chat(self.messages, **self.kwargs):
                self.chunk.emit(token)
        finally:
            self.finished.emit()


class MainWindow(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("AI Agent")
        self.resize(1000, 700)

        self.config = load_config()

        # Main layout
        central = QtWidgets.QWidget()
        self.setCentralWidget(central)
        h = QtWidgets.QHBoxLayout(central)

        # Left: conversation list
        self.left_list = QtWidgets.QListWidget()
        self.left_list.addItem("New Chat")
        self.left_list.setMaximumWidth(240)
        h.addWidget(self.left_list)

        # Center: chat area
        center_w = QtWidgets.QWidget()
        center_l = QtWidgets.QVBoxLayout(center_w)
        self.chat_view = QtWidgets.QTextEdit()
        self.chat_view.setReadOnly(True)
        center_l.addWidget(self.chat_view)

        input_row = QtWidgets.QHBoxLayout()
        self.input_edit = QtWidgets.QLineEdit()
        self.send_btn = QtWidgets.QPushButton("Send")
        input_row.addWidget(self.input_edit)
        input_row.addWidget(self.send_btn)
        center_l.addLayout(input_row)

        h.addWidget(center_w, 1)

        # Right: config panel
        self.right_panel = QtWidgets.QWidget()
        self.right_panel.setMaximumWidth(320)
        rp_l = QtWidgets.QFormLayout(self.right_panel)
        self.provider_combo = QtWidgets.QComboBox()
        self.provider_combo.addItems(["openai", "anthropic", "ollama"])
        self.model_edit = QtWidgets.QLineEdit()
        self.system_prompt = QtWidgets.QTextEdit()
        self.temp_spin = QtWidgets.QDoubleSpinBox()
        self.temp_spin.setRange(0.0, 1.5)
        self.temp_spin.setSingleStep(0.1)

        rp_l.addRow("Provider", self.provider_combo)
        rp_l.addRow("Model", self.model_edit)
        rp_l.addRow("System", self.system_prompt)
        rp_l.addRow("Temperature", self.temp_spin)

        h.addWidget(self.right_panel)

        # Signals
        self.send_btn.clicked.connect(self.handle_send)

    def handle_send(self):
        text = self.input_edit.text().strip()
        if not text:
            return
        self.append_message("user", text)
        self.input_edit.clear()

        # Build messages including system prompt
        messages = []
        sys_prompt = self.system_prompt.toPlainText().strip()
        if sys_prompt:
            messages.append({"role": "system", "content": sys_prompt})
        # For simplicity, send only the last user message as chat context for now
        messages.append({"role": "user", "content": text})

        provider = self.provider_combo.currentText()
        model = self.model_edit.text() or None

        client = None
        conf = self.config.get("providers", {})
        if provider == "openai":
            key = conf.get("openai", {}).get("api_key")
            client = OpenAIClient(key, model=model or "gpt-4o")
        elif provider == "anthropic":
            key = conf.get("anthropic", {}).get("api_key")
            client = AnthropicClient(key, model=model or "claude-2")
        else:
            base = conf.get("ollama", {}).get("base_url", "http://localhost:11434")
            client = OllamaClient(base_url=base, model=model)

        # Stream in background
        self.thread = QtCore.QThread()
        self.worker = StreamWorker(client, messages)
        self.worker.moveToThread(self.thread)
        self.worker.chunk.connect(self.append_stream)
        self.worker.finished.connect(self.thread.quit)
        self.thread.started.connect(self.worker.run)
        self.thread.start()

    def append_message(self, role, text):
        if role == "user":
            self.chat_view.append(f"You: {text}")
        else:
            self.chat_view.append(f"Assistant: {text}")

    def append_stream(self, token: str):
        # Append streaming token to the last assistant line or create a new one
        cursor = self.chat_view.textCursor()
        cursor.movePosition(QtGui.QTextCursor.End)
        # Simple append
        self.chat_view.moveCursor(QtGui.QTextCursor.End)
        self.chat_view.insertPlainText(token)


def main():
    app = QtWidgets.QApplication(sys.argv)
    win = MainWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()

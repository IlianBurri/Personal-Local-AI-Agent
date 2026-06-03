import sys
import threading
from PyQt6 import QtWidgets, QtCore, QtGui

from core.config import load_config, save_config
from core.clients import OpenAIClient, AnthropicClient, OllamaClient
from core.storage import load_conversations, save_conversations
from tools.file_tool import read_file, write_file
from tools.shell_tool import run_command
from tools.search_tool import web_search


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
        # Conversations: list of {title, messages}
        self.conversations = load_conversations()

        # If no provider configured, prompt user
        if not self.config.get("provider"):
            dlg = ProviderDialog(self)
            if dlg.exec() == QtWidgets.QDialog.Accepted:
                prov, data = dlg.result()
                self.config["provider"] = prov
                self.config.setdefault("providers", {})[prov] = data
                save_config(self.config)

        # Main layout
        central = QtWidgets.QWidget()
        self.setCentralWidget(central)
        h = QtWidgets.QHBoxLayout(central)

        # Left: conversation list with New Chat button
        left_col = QtWidgets.QWidget()
        left_l = QtWidgets.QVBoxLayout(left_col)
        self.new_chat_btn = QtWidgets.QPushButton("New Chat")
        left_l.addWidget(self.new_chat_btn)
        self.left_list = QtWidgets.QListWidget()
        self.left_list.setMaximumWidth(240)
        left_l.addWidget(self.left_list)
        h.addWidget(left_col)
        self.new_chat_btn.clicked.connect(self.new_chat)
        self.left_list.currentRowChanged.connect(self.select_conversation)
        self.refresh_conversation_list()

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

        # Tools group
        tools_box = QtWidgets.QGroupBox("Tools")
        tools_layout = QtWidgets.QVBoxLayout(tools_box)
        self.btn_read = QtWidgets.QPushButton("Read file")
        self.btn_write = QtWidgets.QPushButton("Write file")
        self.btn_shell = QtWidgets.QPushButton("Run shell command")
        self.btn_search = QtWidgets.QPushButton("Web search")
        tools_layout.addWidget(self.btn_read)
        tools_layout.addWidget(self.btn_write)
        tools_layout.addWidget(self.btn_shell)
        tools_layout.addWidget(self.btn_search)
        rp_l.addRow(tools_box)

        h.addWidget(self.right_panel)

        # Signals
        self.send_btn.clicked.connect(self.handle_send)
        self.btn_read.clicked.connect(self.handle_read_file)
        self.btn_write.clicked.connect(self.handle_write_file)
        self.btn_shell.clicked.connect(self.handle_shell_command)
        self.btn_search.clicked.connect(self.handle_web_search)

    def handle_send(self):
        text = self.input_edit.text().strip()
        if not text:
            return
        self.input_edit.clear()

        # Ensure a conversation exists
        if not self.conversations:
            self.new_chat()
        row = self.left_list.currentRow()
        if row < 0:
            row = len(self.conversations) - 1
        conv = self.conversations[row]
        # append user message
        conv.setdefault("messages", []).append({"role": "user", "content": text})
        save_conversations(self.conversations)
        self.render_conversation(conv)

        # Build full history for sending
        messages = []
        sys_prompt = self.system_prompt.toPlainText().strip()
        if sys_prompt:
            messages.append({"role": "system", "content": sys_prompt})
        messages.extend(conv.get("messages", []))

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

        # Reserve assistant message in conversation for streaming append
        conv.setdefault("messages", []).append({"role": "assistant", "content": ""})
        save_conversations(self.conversations)

    def append_message(self, role, text):
        if role == "user":
            self.chat_view.append(f"You: {text}")
        else:
            self.chat_view.append(f"Assistant: {text}")

    def append_stream(self, token: str):
        # Append streaming token to the document and update current conversation
        row = self.left_list.currentRow()
        if row < 0:
            return
        conv = self.conversations[row]
        msgs = conv.setdefault("messages", [])
        if not msgs or msgs[-1].get("role") != "assistant":
            msgs.append({"role": "assistant", "content": ""})
        msgs[-1]["content"] = (msgs[-1].get("content") or "") + token
        save_conversations(self.conversations)

        # Append token to chat view for streaming
        self.chat_view.moveCursor(QtGui.QTextCursor.End)
        self.chat_view.insertPlainText(token)

    # Conversation management
    def refresh_conversation_list(self):
        self.left_list.clear()
        for i, c in enumerate(self.conversations):
            title = c.get("title") or f"Conversation {i+1}"
            snippet = ""
            if c.get("messages"):
                last = c["messages"][-1]
                snippet = (last.get("content") or "")[:40].replace("\n", " ")
            self.left_list.addItem(f"{title} — {snippet}")
        if not self.conversations:
            self.left_list.addItem("(no conversations)")

    def new_chat(self):
        title = f"Conversation {len(self.conversations)+1}"
        conv = {"title": title, "messages": []}
        self.conversations.append(conv)
        save_conversations(self.conversations)
        self.refresh_conversation_list()
        self.left_list.setCurrentRow(len(self.conversations)-1)

    def select_conversation(self, row: int):
        if row < 0 or row >= len(self.conversations):
            self.chat_view.clear()
            return
        conv = self.conversations[row]
        self.render_conversation(conv)

    def render_conversation(self, conv: dict):
        html = [
            "<html><head><meta charset='utf-8'/><style>",
            "body{font-family: -apple-system,Segoe UI,Helvetica,Arial,monospace; background:#F5F4F0; color:#1A1A18}",
            ".msg{padding:8px 12px;margin:8px;border-radius:8px;max-width:80%;}",
            ".user{background:#fff;border:1px solid #D0CFC8;margin-left:auto}",
            ".assistant{background:#eef3fb;border:1px solid #D0CFC8;margin-right:auto}",
            ".system{background:#f7f7f5;border:1px dashed #D0CFC8;font-size:0.9em;color:#333}",
            "</style></head><body>",
        ]
        html.append(f"<h3>{conv.get('title','Conversation')}</h3>")
        for m in conv.get("messages", []):
            role = m.get("role")
            content = (m.get("content") or "").replace("\n", "<br/>")
            if role == "user":
                html.append(f"<div class='msg user'><strong>You:</strong><div>{content}</div></div>")
            elif role == "assistant":
                html.append(f"<div class='msg assistant'><strong>Assistant:</strong><div>{content}</div></div>")
            elif role == "system":
                html.append(f"<div class='msg system'><strong>System:</strong><div>{content}</div></div>")
            else:
                html.append(f"<div class='msg'><strong>{role}:</strong><div>{content}</div></div>")
        html.append("</body></html>")
        self.chat_view.setHtml(''.join(html))

    # Tool handlers (moved to MainWindow so they can access UI state)
    def handle_read_file(self):
        path, _ = QtWidgets.QFileDialog.getOpenFileName(self, "Select file to read")
        if not path:
            return
        try:
            text = read_file(path)
        except Exception as e:
            QtWidgets.QMessageBox.warning(self, "Read error", str(e))
            return
        dlg = QtWidgets.QDialog(self)
        dlg.setWindowTitle("File content")
        v = QtWidgets.QVBoxLayout(dlg)
        te = QtWidgets.QPlainTextEdit()
        te.setPlainText(text)
        te.setReadOnly(True)
        v.addWidget(te)
        btns = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Close | QtWidgets.QDialogButtonBox.Ok)
        btns.accepted.connect(dlg.accept)
        btns.rejected.connect(dlg.reject)
        v.addWidget(btns)
        if dlg.exec() == QtWidgets.QDialog.Accepted:
            self.input_edit.setText(text)

    def handle_write_file(self):
        path, _ = QtWidgets.QFileDialog.getSaveFileName(self, "Choose file to write")
        if not path:
            return
        text, ok = QtWidgets.QInputDialog.getMultiLineText(self, "File content", "Content to write:")
        if not ok:
            return
        try:
            write_file(path, text)
            QtWidgets.QMessageBox.information(self, "Saved", f"Wrote file: {path}")
        except Exception as e:
            QtWidgets.QMessageBox.warning(self, "Write error", str(e))

    def handle_shell_command(self):
        cmd, ok = QtWidgets.QInputDialog.getText(self, "Shell command", "Command to run:")
        if not ok or not cmd.strip():
            return
        ans = QtWidgets.QMessageBox.question(
            self,
            "Confirm shell command",
            f"Run the following command?\n\n{cmd}\n\nThis may be dangerous. Proceed?",
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
        )
        if ans != QtWidgets.QMessageBox.Yes:
            return
        result = run_command(cmd)
        out = result.get("stdout", "") or ""
        err = result.get("stderr", "") or ""
        rc = result.get("returncode")
        dlg = QtWidgets.QDialog(self)
        dlg.setWindowTitle("Command output")
        v = QtWidgets.QVBoxLayout(dlg)
        te = QtWidgets.QPlainTextEdit()
        te.setPlainText(f"Return code: {rc}\n\nSTDOUT:\n{out}\n\nSTDERR:\n{err}")
        te.setReadOnly(True)
        v.addWidget(te)
        btn = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Close)
        btn.rejected.connect(dlg.reject)
        v.addWidget(btn)
        dlg.exec()

    def handle_web_search(self):
        q, ok = QtWidgets.QInputDialog.getText(self, "Web search", "Query:")
        if not ok or not q.strip():
            return
        try:
            results = web_search(q)
        except Exception as e:
            QtWidgets.QMessageBox.warning(self, "Search error", str(e))
            return
        dlg = QtWidgets.QDialog(self)
        dlg.setWindowTitle("Search results")
        v = QtWidgets.QVBoxLayout(dlg)
        te = QtWidgets.QPlainTextEdit()
        te.setPlainText("\n\n---\n".join(results) if results else "No results")
        te.setReadOnly(True)
        v.addWidget(te)
        btns = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Close | QtWidgets.QDialogButtonBox.Ok)
        btns.accepted.connect(dlg.accept)
        btns.rejected.connect(dlg.reject)
        v.addWidget(btns)
        if dlg.exec() == QtWidgets.QDialog.Accepted:
            if results:
                self.input_edit.setText(results[0])


class ProviderDialog(QtWidgets.QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Configure provider")
        self.setModal(True)
        l = QtWidgets.QFormLayout(self)
        self.provider = QtWidgets.QComboBox()
        self.provider.addItems(["openai", "anthropic", "ollama"]) 
        self.api_key = QtWidgets.QLineEdit()
        self.base_url = QtWidgets.QLineEdit("http://localhost:11434")
        self.model = QtWidgets.QLineEdit()
        l.addRow("Provider", self.provider)
        l.addRow("API key", self.api_key)
        l.addRow("Base URL (ollama)", self.base_url)
        l.addRow("Model", self.model)
        btns = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        l.addRow(btns)

    def result(self):
        prov = self.provider.currentText()
        data = {"api_key": self.api_key.text().strip()}
        if prov == "ollama":
            data["base_url"] = self.base_url.text().strip() or "http://localhost:11434"
        if self.model.text().strip():
            data["model"] = self.model.text().strip()
        return prov, data
    


def main():
    app = QtWidgets.QApplication(sys.argv)
    win = MainWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()

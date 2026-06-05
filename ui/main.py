import argparse
import sys
import os
import json
import time
import threading
from pathlib import Path
from typing import List, Dict, Any, Optional

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
from ui.web_app import start_web_ui


APP_BG = "#F5F4F0"
TEXT_COLOR = "#1A1A18"
BORDER = "#D0CFC8"
ACCENT = "#4A6FA5"


def ensure_conversations_dir() -> Path:
    p = Path.home() / ".config" / "arca" / "conversations"
    p.mkdir(parents=True, exist_ok=True)
    return p


def safe_filename(name: str) -> str:
    return "conv_" + str(int(time.time())) + ".json"


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
                if tok is None:
                    continue
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
        self._setup_ui()

    def _setup_ui(self):
        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(8)

        bubble = QtWidgets.QFrame()
        bubble.setFrameShape(QtWidgets.QFrame.Shape.StyledPanel)
        bubble.setLineWidth(1)
        bubble_layout = QtWidgets.QVBoxLayout(bubble)
        bubble_layout.setContentsMargins(8, 8, 8, 8)

        # Determine if content contains code block (```)
        if "```" in self.content:
            parts = self.content.split("```")
            for i, part in enumerate(parts):
                if i % 2 == 0:
                    if part.strip():
                        lbl = QtWidgets.QLabel(part.strip())
                        lbl.setWordWrap(True)
                        bubble_layout.addWidget(lbl)
                else:
                    # part may start with a language hint like "python\n..."
                    lang = None
                    code_text = part
                    if "\n" in part:
                        first, rest = part.split("\n", 1)
                        if first.isalpha() and len(first) <= 20:
                            lang = first.strip()
                            code_text = rest

                    if PYGMENTS_AVAILABLE:
                        try:
                            lexer = None
                            if lang:
                                try:
                                    lexer = get_lexer_by_name(lang)
                                except Exception:
                                    lexer = None
                            if lexer is None:
                                try:
                                    lexer = guess_lexer(code_text)
                                except Exception:
                                    lexer = TextLexer()
                            formatter = HtmlFormatter(noclasses=True, style="default")
                            html = highlight(code_text, lexer, formatter)
                            textedit = QtWidgets.QTextEdit()
                            textedit.setReadOnly(True)
                            textedit.setHtml(html)
                            textedit.setMaximumHeight(300)
                            copy_btn = QtWidgets.QPushButton("Copy")
                            def make_copy(te=textedit):
                                def _():
                                    clipboard = QtWidgets.QApplication.clipboard()
                                    clipboard.setText(te.toPlainText())
                                return _
                            copy_btn.clicked.connect(make_copy())
                            hb = QtWidgets.QHBoxLayout()
                            hb.addWidget(textedit)
                            hb.addWidget(copy_btn)
                            bubble_layout.addLayout(hb)
                        except Exception:
                            # fallback to plain text viewer
                            code = QtWidgets.QPlainTextEdit()
                            code.setPlainText(code_text)
                            code.setReadOnly(True)
                            font = QtGui.QFontDatabase.systemFont(QtGui.QFontDatabase.SystemFont.FixedFont)
                            font.setPointSize(11)
                            code.setFont(font)
                            code.setMaximumHeight(200)
                            copy_btn = QtWidgets.QPushButton("Copy")
                            def make_copy2(txt_widget=code):
                                def _():
                                    clipboard = QtWidgets.QApplication.clipboard()
                                    clipboard.setText(txt_widget.toPlainText())
                                return _
                            copy_btn.clicked.connect(make_copy2())
                            hb = QtWidgets.QHBoxLayout()
                            hb.addWidget(code)
                            hb.addWidget(copy_btn)
                            bubble_layout.addLayout(hb)
                    else:
<<<<<<< HEAD
                        code = QtWidgets.QPlainTextEdit()
                        code.setPlainText(code_text)
=======
                        # code block
                        code = QtWidgets.QPlainTextEdit()
                        code.setPlainText(part)
>>>>>>> ef21443 (fix: config recursion bug and PyQt6 enum compatibility)
                        code.setReadOnly(True)
                        font = QtGui.QFontDatabase.systemFont(QtGui.QFontDatabase.SystemFont.FixedFont)
                        font.setPointSize(11)
                        code.setFont(font)
                        code.setMaximumHeight(200)
<<<<<<< HEAD
                        copy_btn = QtWidgets.QPushButton("Copy")
                        def make_copy3(txt_widget=code):
                            def _():
                                clipboard = QtWidgets.QApplication.clipboard()
                                clipboard.setText(txt_widget.toPlainText())
                            return _
                        copy_btn.clicked.connect(make_copy3())
                        hb = QtWidgets.QHBoxLayout()
                        hb.addWidget(code)
                        hb.addWidget(copy_btn)
                        bubble_layout.addLayout(hb)
=======
                        # copy button
                        copy_btn = QtWidgets.QPushButton("Copy")
                    def make_copy(txt_widget=code):
                        def _():
                            clipboard = QtWidgets.QApplication.clipboard()
                            clipboard.setText(txt_widget.toPlainText())
                        return _
                    copy_btn.clicked.connect(make_copy())
                    hb = QtWidgets.QHBoxLayout()
                    hb.addWidget(code)
                    hb.addWidget(copy_btn)
                    bubble_layout.addLayout(hb)
>>>>>>> ef21443 (fix: config recursion bug and PyQt6 enum compatibility)
        else:
            self.lbl = QtWidgets.QLabel(self.content)
            self.lbl.setWordWrap(True)
            bubble_layout.addWidget(self.lbl)

        # For code blocks there's no single lbl; store reference to last code widget if needed
        self._last_code_widget: Optional[QtWidgets.QPlainTextEdit] = None
        for i in range(bubble_layout.count()):
            w = bubble_layout.itemAt(i).widget()
            if isinstance(w, QtWidgets.QPlainTextEdit):
                self._last_code_widget = w

        # style
        if self.role == "user":
            bubble.setStyleSheet(f"background:{ACCENT};color:#fff;border:1px solid {BORDER}")
            layout.addStretch()
            layout.addWidget(bubble, 0)
        else:
            bubble.setStyleSheet(f"background:#ffffff;color:{TEXT_COLOR};border:1px solid {BORDER}")
            layout.addWidget(bubble, 0)
            layout.addStretch()

    def append_text(self, tok: str):
        """Append token to the last text area (label or code block)."""
        if hasattr(self, "lbl") and self.lbl is not None:
            # update label text
            new_text = (self.lbl.text() or "") + tok
            self.lbl.setText(new_text)
        elif self._last_code_widget is not None:
            txt = self._last_code_widget.toPlainText() + tok
            self._last_code_widget.setPlainText(txt)
        else:
            # fallback: add a small label
            lbl = QtWidgets.QLabel(tok)
            lbl.setWordWrap(True)
            self.layout().addWidget(lbl)


class ChatCenter(QtWidgets.QScrollArea):
    def __init__(self):
        super().__init__()
        self.setWidgetResizable(True)
        content = QtWidgets.QWidget()
        self.vbox = QtWidgets.QVBoxLayout(content)
        self.vbox.addStretch()
        self.setWidget(content)

    def add_message(self, role: str, text: str) -> MessageWidget:
        widget = MessageWidget(role, text)
        self.vbox.insertWidget(self.vbox.count()-1, widget)
        QtCore.QTimer.singleShot(50, lambda: self.verticalScrollBar().setValue(self.verticalScrollBar().maximum()))
        return widget

    def clear(self):
        while self.vbox.count() > 1:
            item = self.vbox.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()


class MainWindow(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Arca — Local AI Agent")
        self.resize(1100, 700)
        self.setStyleSheet(f"QWidget{{background:{APP_BG};color:{TEXT_COLOR};font-size:14px;font-family:system-ui, -apple-system, 'Segoe UI', Roboto, 'Helvetica Neue', Arial;}}")

        self.config = load_config()

        # conversations store
        self.conversations_dir = ensure_conversations_dir()
        self.current_conv_path: Path | None = None

        # Main layout
        central = QtWidgets.QWidget()
        self.setCentralWidget(central)
        h = QtWidgets.QHBoxLayout(central)
        h.setContentsMargins(0,0,0,0)

        # Left sidebar
        left = QtWidgets.QFrame()
        left.setFixedWidth(220)
        left.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
        left_layout = QtWidgets.QVBoxLayout(left)
        left_layout.setContentsMargins(10,10,10,10)
        self.new_btn = QtWidgets.QPushButton("New Chat")
        left_layout.addWidget(self.new_btn)
        self.conv_list = QtWidgets.QListWidget()
        self.conv_list.setSizePolicy(QtWidgets.QSizePolicy.Policy.Expanding, QtWidgets.QSizePolicy.Policy.Expanding)
        left_layout.addWidget(self.conv_list)
        # provider/model area
        left_layout.addSpacing(8)
        self.provider_combo = QtWidgets.QComboBox()
        self.provider_combo.addItems(["openai","anthropic","ollama"])
        self.model_combo = QtWidgets.QComboBox()
        left_layout.addWidget(self.provider_combo)
        left_layout.addWidget(self.model_combo)
        self.ollama_status = QtWidgets.QLabel("")
        self.ollama_status.setStyleSheet("color:#666;font-size:12px")
        left_layout.addWidget(self.ollama_status)
        h.addWidget(left)

        # Center chat
        center_frame = QtWidgets.QFrame()
        center_layout = QtWidgets.QVBoxLayout(center_frame)
        center_layout.setContentsMargins(12,12,12,12)
        self.chat_area = ChatCenter()
        center_layout.addWidget(self.chat_area)
        # input row
        input_row = QtWidgets.QHBoxLayout()
        self.input_edit = QtWidgets.QLineEdit()
        self.send_btn = QtWidgets.QPushButton("Send")
        input_row.addWidget(self.input_edit)
        input_row.addWidget(self.send_btn)
        center_layout.addLayout(input_row)
        h.addWidget(center_frame, 1)

        # Right panel
        right = QtWidgets.QFrame()
        right.setFixedWidth(260)
        right_layout = QtWidgets.QVBoxLayout(right)
        right_layout.setContentsMargins(10,10,10,10)
        # collapse toggle
        self.collapse_btn = QtWidgets.QPushButton("Hide Config")
        right_layout.addWidget(self.collapse_btn)
        right_layout.addWidget(QtWidgets.QLabel("System prompt"))
        self.system_edit = QtWidgets.QPlainTextEdit()
        self.system_edit.setFixedHeight(120)
        right_layout.addWidget(self.system_edit)
        right_layout.addWidget(QtWidgets.QLabel("Temperature"))
        self.temp_spin = QtWidgets.QDoubleSpinBox()
        self.temp_spin.setRange(0.0, 2.0)
        self.temp_spin.setSingleStep(0.1)
        self.temp_spin.setValue(0.7)
        right_layout.addWidget(self.temp_spin)
        right_layout.addWidget(QtWidgets.QLabel("Max tokens"))
        self.max_tokens = QtWidgets.QSpinBox()
        self.max_tokens.setRange(16, 4096)
        self.max_tokens.setValue(1024)
        right_layout.addWidget(self.max_tokens)
        right_layout.addWidget(QtWidgets.QLabel("Tools"))
        self.tool_read = QtWidgets.QCheckBox("File read")
        self.tool_write = QtWidgets.QCheckBox("File write")
        self.tool_shell = QtWidgets.QCheckBox("Shell")
        right_layout.addWidget(self.tool_read)
        right_layout.addWidget(self.tool_write)
        right_layout.addWidget(self.tool_shell)
        right_layout.addStretch()
        h.addWidget(right)

        # Signals
        self.new_btn.clicked.connect(self.new_chat)
        self.send_btn.clicked.connect(self.send_message)
        self.conv_list.itemSelectionChanged.connect(self.load_selected_conversation)
        self.collapse_btn.clicked.connect(self.toggle_right)

        # initial populate
        self.load_conversations_list()

        # start Ollama autodiscovery in background
        threading.Thread(target=self._discover_ollama, daemon=True).start()

        # First-run prompt if no providers configured
        if not self.config.get("providers"):
            self.first_run_dialog()

    def toggle_right(self):
        right = self.centralWidget().layout().itemAt(2).widget()
        if right.isVisible():
            right.hide()
            self.collapse_btn.setText("Show Config")
        else:
            right.show()
            self.collapse_btn.setText("Hide Config")

    def first_run_dialog(self):
        dlg = QtWidgets.QDialog(self)
        dlg.setWindowTitle("First run setup")
        form = QtWidgets.QFormLayout(dlg)
        prov = QtWidgets.QComboBox()
        prov.addItems(["openai","anthropic","ollama"])
        key = QtWidgets.QLineEdit()
        key.setEchoMode(QtWidgets.QLineEdit.EchoMode.Password)
        form.addRow("Provider", prov)
        form.addRow("API Key", key)
<<<<<<< HEAD
        btns = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.StandardButton.Ok | QtWidgets.QDialogButtonBox.StandardButton.Cancel)
=======
        btns = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.StandardButton.Ok|QtWidgets.QDialogButtonBox.StandardButton.Cancel)
>>>>>>> ef21443 (fix: config recursion bug and PyQt6 enum compatibility)
        form.addWidget(btns)
        btns.accepted.connect(dlg.accept)
        btns.rejected.connect(dlg.reject)
        if dlg.exec() == QtWidgets.QDialog.DialogCode.Accepted:
            provider = prov.currentText()
            cfg = self.config
            cfg.setdefault("providers", {})[provider] = {"api_key": key.text().strip()}
            cfg["provider"] = provider
            save_config(cfg)

    def load_conversations_list(self):
        self.conv_list.clear()
        p = ensure_conversations_dir()
        for f in sorted(p.glob("*.json")):
            try:
                with open(f, "r", encoding="utf-8") as fh:
                    data = json.load(fh)
                    title = data.get("title") or f.stem
            except Exception:
                title = f.stem
            item = QtWidgets.QListWidgetItem(title)
            item.setData(QtCore.Qt.ItemDataRole.UserRole, str(f))
            self.conv_list.addItem(item)
        # ensure Ollama status cleared until checked
        self.ollama_status.setText("")

    def _discover_ollama(self):
        # determine base URL from config
        conf = self.config.get("providers", {})
        base = conf.get("ollama", {}).get("base_url", "http://localhost:11434")
        client = OllamaClient(base_url=base)
        try:
            tags = client.list_models()
            # normalize into list of model names
            models = []
            if isinstance(tags, dict):
                # maybe {'models': [...]}
                for v in tags.get("models", []) or tags.get("tags", []):
                    if isinstance(v, str):
                        models.append(v)
                    elif isinstance(v, dict):
                        name = v.get("name") or v.get("model")
                        if name:
                            models.append(name)
            elif isinstance(tags, list):
                for item in tags:
                    if isinstance(item, str):
                        models.append(item)
                    elif isinstance(item, dict):
                        name = item.get("name") or item.get("model") or item.get("tag")
                        if name:
                            models.append(name)
            # update UI on main thread
            def apply_models():
                self.model_combo.clear()
                if models:
                    self.model_combo.addItems(models)
                    self.ollama_status.setText(f"Ollama: {len(models)} models")
                else:
                    self.ollama_status.setText("Ollama: no models")
            QtCore.QTimer.singleShot(0, apply_models)
        except Exception:
            # offline - set label
            QtCore.QTimer.singleShot(0, lambda: self.ollama_status.setText("Ollama offline"))

    def load_selected_conversation(self):
        items = self.conv_list.selectedItems()
        if not items:
            return
        path = Path(items[0].data(QtCore.Qt.ItemDataRole.UserRole))
        self.current_conv_path = path
        try:
            with open(path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
        except Exception:
            data = {"messages": []}
        self.chat_area.clear()
        for m in data.get("messages", []):
            self.chat_area.add_message(m.get("role"), m.get("content"))

    def new_chat(self):
        fname = safe_filename("conv")
        p = ensure_conversations_dir() / fname
        obj = {"title": f"Conversation {int(time.time())}", "messages": []}
        with open(p, "w", encoding="utf-8") as fh:
            json.dump(obj, fh)
        self.load_conversations_list()
        # select last
        self.conv_list.setCurrentRow(self.conv_list.count()-1)

    def append_and_save(self, role: str, content: str):
        # append to UI and save to current conv
        widget = self.chat_area.add_message(role, content)
        if not self.current_conv_path:
            # create new
            fname = safe_filename("conv")
            self.current_conv_path = ensure_conversations_dir() / fname
            data = {"title": f"Conversation {int(time.time())}", "messages": []}
        else:
            try:
                with open(self.current_conv_path, "r", encoding="utf-8") as fh:
                    data = json.load(fh)
            except Exception:
                data = {"title": f"Conversation {int(time.time())}", "messages": []}
        data.setdefault("messages", []).append({"role": role, "content": content})
        with open(self.current_conv_path, "w", encoding="utf-8") as fh:
            json.dump(data, fh)
        # refresh list title
        self.load_conversations_list()
        return widget

    def send_message(self):
        text = self.input_edit.text().strip()
        if not text:
            return
        self.input_edit.clear()
        # append user
        self.append_and_save("user", text)

        # prepare messages for client: include system prompt then conversation history
        messages = []
        sys_prompt = self.system_edit.toPlainText().strip()
        if sys_prompt:
            messages.append({"role": "system", "content": sys_prompt})
        # load current conv messages
        convo = []
        if self.current_conv_path and self.current_conv_path.exists():
            try:
                with open(self.current_conv_path, "r", encoding="utf-8") as fh:
                    data = json.load(fh)
                    convo = data.get("messages", [])
            except Exception:
                convo = []
        messages.extend(convo)

        # choose provider
        provider = self.provider_combo.currentText()
        model = self.model_combo.currentText() or None
        conf = self.config.get("providers", {})
        client = None
        if provider == "openai":
            key = conf.get("openai", {}).get("api_key")
            if not key:
                QtWidgets.QMessageBox.warning(self, "Missing API key", "OpenAI API key not configured")
                return
            client = OpenAIClient(key, model=model or "gpt-4o")
        elif provider == "anthropic":
            key = conf.get("anthropic", {}).get("api_key")
            if not key:
                QtWidgets.QMessageBox.warning(self, "Missing API key", "Anthropic API key not configured")
                return
            client = AnthropicClient(key, model=model or "claude-2")
        else:
            base = conf.get("ollama", {}).get("base_url", "http://localhost:11434")
            client = OllamaClient(base_url=base, model=model)

        # Start worker thread for streaming
        self.thread = QtCore.QThread()
        self.worker = StreamWorker(client, messages, kwargs={"temperature": float(self.temp_spin.value()), "max_tokens": int(self.max_tokens.value())})
        self.worker.moveToThread(self.thread)
        self.worker.token.connect(self.on_token)
        self.worker.error.connect(self.on_error)
        self.worker.finished.connect(self.thread.quit)
        self.thread.started.connect(self.worker.run)
        # reserve assistant message in UI and storage and keep reference to widget
        self.current_assistant_widget = self.append_and_save("assistant", "")
        self.thread.start()

    def on_token(self, tok: str):
        # append token to last assistant message visually and in storage
        # add to UI: update last widget by adding plain text
        # For simplicity, append as a new user-type widget of assistant
        # Get last assistant widget by adding plain text to chat_area last widget
        # We will simply append a plain QLabel at end for streaming
        # Find last widget and append text
        # Naive approach: add a small label for streaming text
        # update in-place the reserved assistant widget
        if hasattr(self, "current_assistant_widget") and self.current_assistant_widget is not None:
            try:
                self.current_assistant_widget.append_text(tok)
            except Exception:
                # fallback to adding a message
                self.chat_area.add_message("assistant", tok)
        else:
            w = self.chat_area.add_message("assistant", tok)
        # Also append to current_conv file last message
        if not self.current_conv_path:
            return
        try:
            with open(self.current_conv_path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
        except Exception:
            data = {"messages": []}
        # Append token to last assistant message
        if data.get("messages") and data["messages"][-1]["role"] == "assistant":
            data["messages"][-1]["content"] = (data["messages"][-1].get("content") or "") + tok
        else:
            data.setdefault("messages", []).append({"role": "assistant", "content": tok})
        with open(self.current_conv_path, "w", encoding="utf-8") as fh:
            json.dump(data, fh)

    def on_error(self, err: str):
        QtWidgets.QMessageBox.warning(self, "Stream error", err)


def run_desktop_app():
    app = QtWidgets.QApplication(sys.argv)
    win = MainWindow()
    win.show()
    sys.exit(app.exec())


def run_web_app(host: str = "127.0.0.1", port: int = 8765, open_browser: bool = True):
    server = start_web_ui(host=host, port=port, open_browser=open_browser)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


def main():
    parser = argparse.ArgumentParser(description="Arca agent launcher")
    parser.add_argument("--mode", choices=["web", "desktop"], default="web")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--no-open-browser", action="store_true")
    args = parser.parse_args()

    if args.mode == "desktop":
        run_desktop_app()
        return

    run_web_app(host=args.host, port=args.port, open_browser=not args.no_open_browser)


if __name__ == "__main__":
    main()

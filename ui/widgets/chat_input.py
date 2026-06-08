from PyQt6 import QtWidgets, QtCore, QtGui


class ChatInput(QtWidgets.QWidget):

    submitted = QtCore.pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self.setStyleSheet("background: #0d1117;")

        outer = QtWidgets.QVBoxLayout(self)
        outer.setContentsMargins(24, 0, 24, 20)
        outer.setSpacing(0)

        # Container
        container = QtWidgets.QFrame()
        container.setStyleSheet("""
            QFrame {
                background: #1e293b;
                border: 1px solid #334155;
                border-radius: 12px;
            }
        """)

        inner = QtWidgets.QVBoxLayout(container)
        inner.setContentsMargins(16, 12, 16, 12)
        inner.setSpacing(8)

        self.input = _TextEdit(self)
        self.input.setMaximumHeight(120)
        self.input.setMinimumHeight(44)
        self.input.setPlaceholderText("Message Arca... (Enter to send, Shift+Enter for newline)")
        self.input.setStyleSheet("""
            QTextEdit {
                background: transparent;
                border: none;
                color: #f1f5f9;
                font-size: 14px;
                line-height: 1.5;
            }
        """)
        inner.addWidget(self.input)

        row = QtWidgets.QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)

        hint = QtWidgets.QLabel("Shift+Enter for newline")
        hint.setStyleSheet("color: #475569; font-size: 11px;")
        row.addWidget(hint)
        row.addStretch()

        self.send_btn = QtWidgets.QPushButton("Send ↑")
        self.send_btn.setFixedSize(80, 32)
        self.send_btn.setStyleSheet("""
            QPushButton {
                background: #1d4ed8;
                color: white;
                border: none;
                border-radius: 8px;
                font-size: 13px;
                font-weight: 600;
            }
            QPushButton:hover {
                background: #2563eb;
            }
            QPushButton:pressed {
                background: #1e40af;
            }
            QPushButton:disabled {
                background: #1e293b;
                color: #475569;
            }
        """)
        row.addWidget(self.send_btn)
        inner.addLayout(row)

        outer.addWidget(container)

        self.send_btn.clicked.connect(self._send)
        self.input.submit_requested.connect(self._send)

    def _send(self):
        text = self.input.toPlainText().strip()
        if not text:
            return
        self.submitted.emit(text)
        self.input.clear()


class _TextEdit(QtWidgets.QTextEdit):
    """QTextEdit that emits submit_requested on plain Enter."""
    submit_requested = QtCore.pyqtSignal()

    def keyPressEvent(self, event: QtGui.QKeyEvent):
        if (
            event.key() in (QtCore.Qt.Key.Key_Return, QtCore.Qt.Key.Key_Enter)
            and not (event.modifiers() & QtCore.Qt.KeyboardModifier.ShiftModifier)
        ):
            self.submit_requested.emit()
        else:
            super().keyPressEvent(event)

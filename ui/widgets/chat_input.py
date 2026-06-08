from PyQt6 import QtWidgets, QtCore, QtGui


class ChatInput(QtWidgets.QWidget):
    submitted = QtCore.pyqtSignal(str)
    stop_requested = QtCore.pyqtSignal()

    def __init__(self):
        super().__init__()
        self._busy = False
        self.setStyleSheet("background: #0f172a;")

        outer = QtWidgets.QVBoxLayout(self)
        outer.setContentsMargins(34, 0, 34, 26)
        outer.setSpacing(0)

        container = QtWidgets.QFrame()
        container.setStyleSheet("""
            QFrame {
                background: #151f31;
                border: 1px solid #334155;
                border-radius: 12px;
            }
            QFrame:focus-within {
                border-color: #22c55e;
            }
        """)

        inner = QtWidgets.QVBoxLayout(container)
        inner.setContentsMargins(15, 12, 15, 12)
        inner.setSpacing(10)

        self.input = _TextEdit(self)
        self.input.setMaximumHeight(140)
        self.input.setMinimumHeight(48)
        self.input.setPlaceholderText("Message Arca...")
        self.input.setStyleSheet("""
            QTextEdit {
                background: transparent;
                border: none;
                color: #f8fafc;
                font-size: 15px;
                line-height: 1.5;
            }
            QTextEdit:disabled {
                color: #64748b;
            }
        """)
        inner.addWidget(self.input)

        row = QtWidgets.QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(10)

        self.status = QtWidgets.QLabel("Enter to send. Shift+Enter for a new line.")
        self.status.setStyleSheet("color: #64748b; font-size: 12px; border: none;")
        row.addWidget(self.status)
        row.addStretch()

        self.stop_btn = QtWidgets.QPushButton("Stop")
        self.stop_btn.setFixedSize(72, 34)
        self.stop_btn.setStyleSheet(self._button_style("#7f1d1d", "#991b1b"))
        self.stop_btn.clicked.connect(self.stop_requested.emit)
        self.stop_btn.hide()
        row.addWidget(self.stop_btn)

        self.send_btn = QtWidgets.QPushButton("Send")
        self.send_btn.setFixedSize(78, 34)
        self.send_btn.setDefault(True)
        self.send_btn.setStyleSheet(self._button_style("#16a34a", "#22c55e", dark_text=True))
        self.send_btn.clicked.connect(self._send)
        row.addWidget(self.send_btn)

        inner.addLayout(row)
        outer.addWidget(container)

        self.input.submit_requested.connect(self._send)

    def _button_style(self, bg, hover, dark_text=False):
        color = "#052e16" if dark_text else "#f8fafc"
        return f"""
            QPushButton {{
                background: {bg};
                color: {color};
                border: none;
                border-radius: 8px;
                font-size: 13px;
                font-weight: 900;
            }}
            QPushButton:hover {{
                background: {hover};
            }}
            QPushButton:disabled {{
                background: #223049;
                color: #64748b;
            }}
        """

    def _send(self):
        if self._busy:
            return
        text = self.input.toPlainText().strip()
        if not text:
            return
        self.submitted.emit(text)
        self.input.clear()

    def set_busy(self, busy: bool):
        self._busy = busy
        self.input.setDisabled(busy)
        self.send_btn.setDisabled(busy)
        self.stop_btn.setVisible(busy)
        self.status.setText("Generating response..." if busy else "Enter to send. Shift+Enter for a new line.")

    def focus_input(self):
        self.input.setFocus()


class _TextEdit(QtWidgets.QTextEdit):
    submit_requested = QtCore.pyqtSignal()

    def keyPressEvent(self, event: QtGui.QKeyEvent):
        if (
            event.key() in (QtCore.Qt.Key.Key_Return, QtCore.Qt.Key.Key_Enter)
            and not (event.modifiers() & QtCore.Qt.KeyboardModifier.ShiftModifier)
        ):
            self.submit_requested.emit()
            return
        super().keyPressEvent(event)

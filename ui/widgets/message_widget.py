from PyQt6 import QtWidgets, QtGui, QtCore


class MessageWidget(QtWidgets.QWidget):
    def __init__(self, role: str, content: str):
        super().__init__()
        self.role = role
        self.content = content
        self.parts_layout = None
        self._setup()
        self._render()

    def _setup(self):
        outer = QtWidgets.QHBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(12)

        self.bubble = QtWidgets.QFrame()
        self.bubble.setMaximumWidth(860)
        self.bubble.setMinimumWidth(90)

        bubble_layout = QtWidgets.QVBoxLayout(self.bubble)
        bubble_layout.setContentsMargins(15, 12, 15, 12)
        bubble_layout.setSpacing(9)

        header = QtWidgets.QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)

        name = "You" if self.role == "user" else "Arca"
        self.name_lbl = QtWidgets.QLabel(name)
        self.name_lbl.setStyleSheet("font-size: 11px; font-weight: 900;")
        header.addWidget(self.name_lbl)
        header.addStretch()

        self.copy_btn = QtWidgets.QPushButton("Copy")
        self.copy_btn.setFixedSize(48, 24)
        self.copy_btn.setToolTip("Copy message")
        self.copy_btn.clicked.connect(self.copy_message)
        self.copy_btn.setStyleSheet("""
            QPushButton {
                background: transparent;
                color: #94a3b8;
                border: 1px solid #334155;
                border-radius: 5px;
                font-size: 11px;
                font-weight: 700;
            }
            QPushButton:hover {
                background: #223049;
                color: #f8fafc;
            }
        """)
        header.addWidget(self.copy_btn)
        bubble_layout.addLayout(header)

        self.parts_layout = QtWidgets.QVBoxLayout()
        self.parts_layout.setContentsMargins(0, 0, 0, 0)
        self.parts_layout.setSpacing(8)
        bubble_layout.addLayout(self.parts_layout)

        if self.role == "user":
            self.bubble.setStyleSheet("""
                QFrame {
                    background: #1d4ed8;
                    border-radius: 13px;
                    border: 1px solid #3b82f6;
                }
                QLabel {
                    color: #eff6ff;
                }
            """)
            self.name_lbl.setStyleSheet("color:#bfdbfe; font-size:11px; font-weight:900;")
            outer.addStretch(1)
            outer.addWidget(self.bubble)
        else:
            self.bubble.setStyleSheet("""
                QFrame {
                    background: #151f31;
                    border-radius: 13px;
                    border: 1px solid #2f3b52;
                }
                QLabel {
                    color: #e5e7eb;
                }
            """)
            self.name_lbl.setStyleSheet("color:#86efac; font-size:11px; font-weight:900;")
            outer.addWidget(self.bubble)
            outer.addStretch(1)

    def _clear_parts(self):
        while self.parts_layout.count():
            item = self.parts_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()

    def _render(self):
        self._clear_parts()
        if not self.content:
            label = self._text_label("Thinking...")
            label.setStyleSheet("color:#94a3b8; font-size:14px; font-style:italic;")
            self.parts_layout.addWidget(label)
            return

        parts = self.content.split("```")
        for index, part in enumerate(parts):
            if index % 2 == 0:
                if part.strip():
                    self.parts_layout.addWidget(self._text_label(part.strip()))
            else:
                code_text = part
                language = ""
                if "\n" in part:
                    first, rest = part.split("\n", 1)
                    if first.strip() and len(first.strip()) <= 24:
                        language = first.strip()
                        code_text = rest
                self.parts_layout.addWidget(self._code_block(code_text.rstrip(), language))

    def _text_label(self, text):
        label = QtWidgets.QLabel(text)
        label.setWordWrap(True)
        label.setTextInteractionFlags(QtCore.Qt.TextInteractionFlag.TextSelectableByMouse)
        label.setStyleSheet("font-size: 14px; line-height: 1.5;")
        return label

    def _code_block(self, code_text, language):
        frame = QtWidgets.QFrame()
        frame.setStyleSheet("""
            QFrame {
                background: #070b12;
                border: 1px solid #263244;
                border-radius: 8px;
            }
        """)
        layout = QtWidgets.QVBoxLayout(frame)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        header = QtWidgets.QHBoxLayout()
        header.setContentsMargins(10, 6, 8, 4)
        lang = QtWidgets.QLabel(language or "code")
        lang.setStyleSheet("color:#64748b; font-size:11px; font-weight:800;")
        header.addWidget(lang)
        header.addStretch()

        copy = QtWidgets.QPushButton("Copy")
        copy.setFixedSize(48, 22)
        copy.setStyleSheet(self.copy_btn.styleSheet())
        copy.clicked.connect(lambda: QtWidgets.QApplication.clipboard().setText(code_text))
        header.addWidget(copy)
        layout.addLayout(header)

        editor = QtWidgets.QPlainTextEdit()
        editor.setPlainText(code_text)
        editor.setReadOnly(True)
        editor.setMaximumHeight(260)
        font = QtGui.QFontDatabase.systemFont(QtGui.QFontDatabase.SystemFont.FixedFont)
        font.setPointSize(11)
        editor.setFont(font)
        editor.setStyleSheet("""
            QPlainTextEdit {
                background: #070b12;
                color: #d1fae5;
                border: none;
                padding: 10px;
                font-size: 12px;
            }
        """)
        layout.addWidget(editor)
        return frame

    def append_text(self, token: str):
        self.content += token
        self._render()

    def copy_message(self):
        QtWidgets.QApplication.clipboard().setText(self.content)

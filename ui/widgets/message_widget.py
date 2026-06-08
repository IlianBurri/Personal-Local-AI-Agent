from PyQt6 import QtWidgets, QtGui, QtCore


class MessageWidget(QtWidgets.QWidget):

    def __init__(self, role: str, content: str):
        super().__init__()
        self.role = role
        self.content = content
        self._setup()

    def _setup(self):
        outer = QtWidgets.QHBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        bubble = QtWidgets.QFrame()
        bubble.setMaximumWidth(720)

        bubble_layout = QtWidgets.QVBoxLayout(bubble)
        bubble_layout.setContentsMargins(14, 10, 14, 10)
        bubble_layout.setSpacing(6)

        if "```" not in self.content:
            self.lbl = QtWidgets.QLabel(self.content)
            self.lbl.setWordWrap(True)
            self.lbl.setTextInteractionFlags(
                QtCore.Qt.TextInteractionFlag.TextSelectableByMouse
            )
            self.lbl.setStyleSheet("font-size: 14px; line-height: 1.6;")
            bubble_layout.addWidget(self.lbl)
        else:
            self.lbl = None
            parts = self.content.split("```")
            for i, part in enumerate(parts):
                if i % 2 == 0:
                    if part.strip():
                        lbl = QtWidgets.QLabel(part.strip())
                        lbl.setWordWrap(True)
                        lbl.setTextInteractionFlags(
                            QtCore.Qt.TextInteractionFlag.TextSelectableByMouse
                        )
                        lbl.setStyleSheet("font-size: 14px;")
                        bubble_layout.addWidget(lbl)
                else:
                    code_text = part
                    if "\n" in part:
                        _, code_text = part.split("\n", 1)

                    code = QtWidgets.QPlainTextEdit()
                    code.setPlainText(code_text.rstrip())
                    code.setReadOnly(True)
                    font = QtGui.QFontDatabase.systemFont(
                        QtGui.QFontDatabase.SystemFont.FixedFont
                    )
                    font.setPointSize(12)
                    code.setFont(font)
                    code.setMaximumHeight(220)
                    code.setStyleSheet("""
                        QPlainTextEdit {
                            background: #0a0e14;
                            color: #a5f3fc;
                            border: 1px solid #1e293b;
                            border-radius: 6px;
                            padding: 10px;
                            font-size: 12px;
                        }
                    """)

                    copy_btn = QtWidgets.QPushButton("Copy")
                    copy_btn.setFixedSize(56, 26)
                    copy_btn.setStyleSheet("""
                        QPushButton {
                            background: #1e293b;
                            color: #94a3b8;
                            border: none;
                            border-radius: 4px;
                            font-size: 11px;
                            font-weight: 600;
                        }
                        QPushButton:hover {
                            background: #334155;
                            color: #f1f5f9;
                        }
                    """)

                    def make_copy(w=code):
                        def _():
                            QtWidgets.QApplication.clipboard().setText(
                                w.toPlainText()
                            )
                        return _

                    copy_btn.clicked.connect(make_copy())

                    header = QtWidgets.QHBoxLayout()
                    header.addStretch()
                    header.addWidget(copy_btn)
                    bubble_layout.addLayout(header)
                    bubble_layout.addWidget(code)

        if self.role == "user":
            bubble.setStyleSheet("""
                QFrame {
                    background: #1d4ed8;
                    border-radius: 16px 16px 4px 16px;
                }
                QLabel { color: #eff6ff; }
            """)
            outer.addStretch()
            outer.addWidget(bubble)
        else:
            bubble.setStyleSheet("""
                QFrame {
                    background: #1e293b;
                    border-radius: 16px 16px 16px 4px;
                    border: 1px solid #334155;
                }
                QLabel { color: #e2e8f0; }
            """)
            outer.addWidget(bubble)
            outer.addStretch()

    def append_text(self, tok: str):
        if self.lbl is not None:
            self.lbl.setText(self.lbl.text() + tok)

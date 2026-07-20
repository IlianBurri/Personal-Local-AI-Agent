"""Composer widget with send button, stop button, and auto-resize text input."""

from PyQt6 import QtCore, QtGui, QtWidgets

from ui.theme import Theme


class ChatInput(QtWidgets.QWidget):
    submitted = QtCore.pyqtSignal(str)
    stop_requested = QtCore.pyqtSignal()

    def __init__(self, theme: Theme):
        super().__init__()
        self._t = theme
        self._generating = False
        self._build()
        self.apply_theme(self._t)

    def _build(self):
        wrapper = QtWidgets.QVBoxLayout(self)
        wrapper.setContentsMargins(0, 12, 0, 24)
        wrapper.setSpacing(0)

        row = QtWidgets.QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(0)
        row.addStretch()
        wrapper.addLayout(row)

        self.composer = QtWidgets.QFrame()
        self.composer.setObjectName("composer")
        self.composer.setMinimumWidth(360)
        self.composer.setMaximumWidth(720)

        comp_layout = QtWidgets.QHBoxLayout(self.composer)
        comp_layout.setContentsMargins(16, 4, 8, 4)
        comp_layout.setSpacing(8)

        self.input = _TextEdit()
        self.input.setPlaceholderText("Message Arca\u2026")
        self.input.setAcceptRichText(False)
        self.input.setVerticalScrollBarPolicy(
            QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self.input.textChanged.connect(self._adjust_height)
        self.input.submit_requested.connect(self._send)
        self.input.installEventFilter(self)
        comp_layout.addWidget(self.input, 1)

        # Send button (visible when idle)
        self.send_btn = QtWidgets.QPushButton("\u2191")  # ↑
        self.send_btn.setFixedSize(32, 32)
        self.send_btn.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
        self.send_btn.setToolTip("Send")
        self.send_btn.clicked.connect(self._send)
        comp_layout.addWidget(self.send_btn)

        # Stop button (visible during generation)
        self.stop_btn = QtWidgets.QPushButton("\u25a0")  # ■
        self.stop_btn.setFixedSize(32, 32)
        self.stop_btn.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
        self.stop_btn.setToolTip("Stop generation")
        self.stop_btn.clicked.connect(self.stop_requested.emit)
        self.stop_btn.hide()
        comp_layout.addWidget(self.stop_btn)

        row.addWidget(self.composer)
        row.addStretch()

    # -- public API --
    def set_generating(self, generating: bool):
        self._generating = generating
        self.send_btn.setVisible(not generating)
        self.stop_btn.setVisible(generating)
        self.input.setReadOnly(generating)
        self.input.setPlaceholderText(
            "Message Arca\u2026" if not generating else "Arca is generating\u2026"
        )
        if not generating:
            self.input.setFocus()

    def set_text(self, text: str):
        self.input.setPlainText(text)
        self.input.setFocus()

    # -- theming --
    def apply_theme(self, theme: Theme):
        self._t = theme
        self._refresh_composer_style()
        self.send_btn.setStyleSheet(self._t.send_btn_css())
        self.stop_btn.setStyleSheet(self._t.stop_btn_css())

    def _refresh_composer_style(self):
        if self.input.hasFocus():
            self.composer.setStyleSheet(self._t.composer_focused_css())
        else:
            self.composer.setStyleSheet(self._t.composer_css())

    # -- events --
    def eventFilter(self, obj, event):
        if obj is self.input and event.type() in (
            QtCore.QEvent.Type.FocusIn,
            QtCore.QEvent.Type.FocusOut,
        ):
            self._refresh_composer_style()
        return super().eventFilter(obj, event)

    # -- internals --
    def _adjust_height(self):
        h = int(self.input.document().size().height()) + 12
        h = max(self.input.minimumHeight(), min(h, self.input.maximumHeight()))
        if self.input.height() != h:
            self.input.setFixedHeight(h)

    def _send(self):
        if self._generating:
            return
        text = self.input.toPlainText().strip()
        if not text:
            return
        self.input.clear()
        self.submitted.emit(text)


class _TextEdit(QtWidgets.QTextEdit):
    submit_requested = QtCore.pyqtSignal()

    def __init__(self):
        super().__init__()
        self.setMinimumHeight(28)
        self.setMaximumHeight(200)
        font = QtGui.QFont()
        font.setPointSize(11)
        self.setFont(font)

    def keyPressEvent(self, event: QtGui.QKeyEvent):
        if (
            event.key() in (QtCore.Qt.Key.Key_Return, QtCore.Qt.Key.Key_Enter)
            and not (event.modifiers() & QtCore.Qt.KeyboardModifier.ShiftModifier)
        ):
            self.submit_requested.emit()
            return
        super().keyPressEvent(event)

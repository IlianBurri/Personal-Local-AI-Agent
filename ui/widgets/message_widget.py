from PyQt6 import QtCore, QtGui, QtWidgets

from ui.theme import Theme


class MessageWidget(QtWidgets.QWidget):
    """Plain-text message row. No bubble on either side.

    User message: right-aligned plain text.
    Assistant message: left-aligned plain text.
    Code blocks render as separate bordered widgets with a language header
    and a copy button. Streaming tokens are appended to the *last* plain-text
    label, which works correctly when only plain text is streaming.

    Assistant messages show a "↻ Regenerate" button on hover.
    """

    regenerate_requested = QtCore.pyqtSignal(object)  # emits self

    def __init__(self, role: str, content: str, theme: Theme):
        super().__init__()
        self.role = role
        self.content = content
        self._t = theme
        self._text_lbls: list[QtWidgets.QLabel] = []
        self._regenerate_btn = None
        self._can_regenerate = False
        self._build()

    def _build(self):
        outer = QtWidgets.QVBoxLayout(self)
        outer.setContentsMargins(0, 16, 0, 16)
        outer.setSpacing(0)

        parts = self.content.split("```")
        # Streaming always needs somewhere to land. If the message is empty
        # or has no plain-text leading segment, allocate one label now so
        # append_text has a target.
        if len(parts) == 1 or parts[0] == "":
            self._append_text_segment(outer, "")

        for i, part in enumerate(parts):
            if i % 2 == 0:
                if i == 0 and self._text_lbls:
                    # The leading label was created as the streaming target above.
                    if part:
                        self._text_lbls[-1].setText(part)
                    continue
                text = part.strip() if part else ""
                if not text:
                    continue
                self._append_text_segment(outer, text)
            else:
                block = CodeBlock(part, self._t)
                row = QtWidgets.QHBoxLayout()
                row.setContentsMargins(0, 4, 0, 4)
                row.setSpacing(0)
                if self.role == "user":
                    row.addStretch()
                    row.addWidget(block)
                else:
                    row.addWidget(block)
                    row.addStretch()
                outer.addLayout(row)

        # Regenerate button — only for assistant messages, hidden by default
        if self.role == "assistant":
            btn_row = QtWidgets.QHBoxLayout()
            btn_row.setContentsMargins(0, 4, 0, 0)
            btn_row.setSpacing(0)
            btn_row.addStretch()
            self._regenerate_btn = QtWidgets.QPushButton("\u21bb Regenerate")
            self._regenerate_btn.setCursor(
                QtCore.Qt.CursorShape.PointingHandCursor
            )
            self._regenerate_btn.setToolTip("Regenerate this response")
            self._regenerate_btn.clicked.connect(
                lambda: self.regenerate_requested.emit(self)
            )
            self._regenerate_btn.hide()
            btn_row.addWidget(self._regenerate_btn)
            btn_row.addStretch()
            outer.addLayout(btn_row)

        self.apply_theme(self._t)

    def _append_text_segment(self, outer, text: str):
        row = QtWidgets.QHBoxLayout()
        row.setContentsMargins(0, 4, 0, 4)
        row.setSpacing(0)
        lbl = QtWidgets.QLabel(text)
        lbl.setWordWrap(True)
        lbl.setTextInteractionFlags(
            QtCore.Qt.TextInteractionFlag.TextSelectableByMouse
            | QtCore.Qt.TextInteractionFlag.LinksAccessibleByMouse,
        )
        lbl.setOpenExternalLinks(True)
        if self.role == "user":
            row.addStretch()
            row.addWidget(lbl)
        else:
            row.addWidget(lbl)
            row.addStretch()
        outer.addLayout(row)
        self._text_lbls.append(lbl)

    def apply_theme(self, theme: Theme):
        self._t = theme
        for lbl in self._text_lbls:
            lbl.setStyleSheet(self._t.message_text_css(self.role))
        if self._regenerate_btn:
            self._regenerate_btn.setStyleSheet(self._t.regenerate_btn_css())
        # Code blocks live inside row sub-layouts.
        layout_item = self.layout()
        if layout_item is not None:
            for i in range(layout_item.count()):
                item = layout_item.itemAt(i)
                sub = item.layout() if item else None
                if sub is None:
                    continue
                for j in range(sub.count()):
                    inner = sub.itemAt(j)
                    w = inner.widget() if inner else None
                    if isinstance(w, CodeBlock):
                        w.apply_theme(self._t)

    def append_text(self, token: str):
        """Append a streaming token to the trailing plain-text label."""
        self.content += token
        if not self._text_lbls:
            return
        last = self._text_lbls[-1]
        last.setText(last.text() + token)

    def set_can_regenerate(self, enabled: bool):
        """Enable or disable the regenerate button for this message.
        Only the last assistant message should have it.
        """
        self._can_regenerate = enabled
        if self._regenerate_btn:
            self._regenerate_btn.setVisible(enabled and bool(self.content.strip()))
            self.setAttribute(
                QtCore.Qt.WidgetAttribute.WA_Hover, enabled and bool(self.content.strip())
            )

    # -- hover events to show/hide regenerate button --
    def enterEvent(self, event):
        if self._regenerate_btn and self._can_regenerate and self.content.strip():
            self._regenerate_btn.show()
        super().enterEvent(event)

    def leaveEvent(self, event):
        if self._regenerate_btn:
            self._regenerate_btn.hide()
        super().leaveEvent(event)


class CodeBlock(QtWidgets.QWidget):
    def __init__(self, raw: str, theme: Theme):
        super().__init__()
        self._t = theme
        self.setObjectName("codeBlock")

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Header row: language label + copy button
        header = QtWidgets.QHBoxLayout()
        header.setContentsMargins(12, 6, 6, 6)
        header.setSpacing(0)

        lang = raw.split("\n", 1)[0].strip()
        lang_lbl = QtWidgets.QLabel(lang or "code")
        lang_lbl.setObjectName("codeLang")
        header.addWidget(lang_lbl)
        header.addStretch()

        copy_btn = QtWidgets.QPushButton("Copy")
        copy_btn.setObjectName("codeCopy")
        copy_btn.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
        copy_btn.clicked.connect(self._copy)
        header.addWidget(copy_btn)
        layout.addLayout(header)

        # Body
        body = raw
        if "\n" in raw:
            body = "\n".join(raw.split("\n")[1:])
        body = body.strip("\n")

        self.code = QtWidgets.QPlainTextEdit(body)
        self.code.setReadOnly(True)
        self.code.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
        self.code.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.code.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.code.setMaximumHeight(300)
        font = QtGui.QFont("Courier New" if QtCore.QSysInfo.productType() == "windows" else "Monospace")
        font.setPointSize(11)
        self.code.setFont(font)
        layout.addWidget(self.code)

        self.apply_theme(self._t)

    def _copy(self):
        QtWidgets.QApplication.clipboard().setText(self.code.toPlainText())

    def apply_theme(self, theme: Theme):
        self._t = theme
        self.setStyleSheet(self._t.code_block_css())

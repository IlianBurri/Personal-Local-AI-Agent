"""Center-constrained chat column with empty state, typing indicator, and chips."""

from PyQt6 import QtCore, QtWidgets

from ui.theme import Theme
from ui.widgets.message_widget import MessageWidget


class ChatArea(QtWidgets.QScrollArea):
    """Scrollable chat column with centered messages, empty state, and typing indicator."""

    regenerate_requested = QtCore.pyqtSignal(object)  # forwards MessageWidget

    def __init__(self, theme: Theme, on_chip_clicked=None):
        super().__init__()
        self._t = theme
        self._on_chip_clicked = on_chip_clicked
        self._empty_visible = True
        self._typing_widget = None

        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(
            QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )

        self.container = QtWidgets.QWidget()
        self.vbox = QtWidgets.QVBoxLayout(self.container)
        self.vbox.setContentsMargins(0, 0, 0, 0)
        self.vbox.setSpacing(0)

        # Empty state — visible until first message arrives.
        self._empty = ChatEmptyState(theme, on_chip_clicked)
        self.vbox.addWidget(self._empty, 0, QtCore.Qt.AlignmentFlag.AlignHCenter)

        # Centered message column.
        self._col_holder = QtWidgets.QHBoxLayout()
        self._col_holder.setContentsMargins(0, 32, 0, 0)
        self._col_holder.setSpacing(0)

        self.column = QtWidgets.QWidget()
        self.column.setMaximumWidth(720)
        self.column_vbox = QtWidgets.QVBoxLayout(self.column)
        self.column_vbox.setContentsMargins(0, 0, 0, 0)
        self.column_vbox.setSpacing(0)

        self._col_holder.addStretch()
        self._col_holder.addWidget(
            self.column, 0, QtCore.Qt.AlignmentFlag.AlignTop
        )
        self._col_holder.addStretch()

        self.vbox.addLayout(self._col_holder)
        self.vbox.addStretch(1)

        self.setWidget(self.container)
        self.apply_theme(self._t)

    # -- theming --
    def apply_theme(self, theme: Theme):
        self._t = theme
        self.setStyleSheet(self._t.chat_scroll_css() + self._t.scrollbar_css())
        self.container.setStyleSheet(f"background: {self._t.bg_app};")
        self.column.setAttribute(
            QtCore.Qt.WidgetAttribute.WA_StyledBackground, False
        )
        self._empty.apply_theme(self._t)
        if self._typing_widget:
            self._typing_widget.apply_theme(self._t)
        for i in range(self.column_vbox.count()):
            item = self.column_vbox.itemAt(i)
            w = item.widget() if item else None
            if isinstance(w, MessageWidget):
                w.apply_theme(self._t)

    # -- public API --
    def add_message(self, role: str, text: str) -> MessageWidget:
        if self._empty_visible:
            self._empty.hide()
            self._empty_visible = False

        widget = MessageWidget(role, text, self._t)
        widget.regenerate_requested.connect(self._on_regenerate_requested)
        self.column_vbox.addWidget(widget)
        self._refresh_regenerate_visibility()
        self._scroll_to_bottom()
        return widget

    def remove_widget(self, widget: MessageWidget):
        """Remove a specific message widget from the layout."""
        widget.regenerate_requested.disconnect()
        self.column_vbox.removeWidget(widget)
        widget.deleteLater()
        self._refresh_regenerate_visibility()
        # Show empty state if no messages left
        if self.column_vbox.count() == 0:
            self._empty.show()
            self._empty_visible = True

    def clear(self):
        for i in reversed(range(self.column_vbox.count())):
            item = self.column_vbox.itemAt(i)
            w = item.widget() if item else None
            if isinstance(w, MessageWidget):
                w.regenerate_requested.disconnect()
            if w is not None:
                w.deleteLater()
        if self._typing_widget:
            self._typing_widget = None
        self._empty.show()
        self._empty_visible = True

    def _refresh_regenerate_visibility(self):
        """Only the last assistant message should show the regenerate button."""
        last_assistant = None
        for i in range(self.column_vbox.count()):
            item = self.column_vbox.itemAt(i)
            w = item.widget() if item else None
            if isinstance(w, MessageWidget) and w.role == "assistant":
                last_assistant = w
        for i in range(self.column_vbox.count()):
            item = self.column_vbox.itemAt(i)
            w = item.widget() if item else None
            if isinstance(w, MessageWidget) and w.role == "assistant":
                w.set_can_regenerate(w is last_assistant)

    def show_typing(self, visible: bool):
        """Show or hide a compact 'typing' indicator at the bottom of messages."""
        if visible and not self._typing_widget:
            self._typing_widget = _TypingIndicator(self._t)
            self.column_vbox.addWidget(self._typing_widget)
            self._scroll_to_bottom()
        elif not visible and self._typing_widget:
            self._typing_widget.deleteLater()
            self._typing_widget = None

    def _on_regenerate_requested(self, widget: MessageWidget):
        self.regenerate_requested.emit(widget)

    def show_chips(self, on_chip_clicked):
        """Re-target chip click handler at runtime if needed."""
        self._on_chip_clicked = on_chip_clicked
        for chip in self._empty.chips:
            chip.clicked.disconnect()
            chip.clicked.connect(
                lambda _checked=False, t=chip.text(): on_chip_clicked(t)
            )

    # -- helpers --
    def _scroll_to_bottom(self):
        QtCore.QTimer.singleShot(
            40,
            lambda: self.verticalScrollBar().setValue(
                self.verticalScrollBar().maximum()
            ),
        )


class _TypingIndicator(QtWidgets.QWidget):
    """Animated three-dot typing indicator for assistant responses."""

    def __init__(self, theme: Theme):
        super().__init__()
        self._t = theme
        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(0, 8, 0, 8)
        layout.setSpacing(0)

        self.dots = QtWidgets.QLabel("\u25cf  \u25cf  \u25cf")  # ●  ●  ●
        self.dots.setStyleSheet(f"color: {theme.text_quiet}; font-size: 12px; background: transparent;")
        layout.addWidget(self.dots)
        layout.addStretch()
        self.apply_theme(theme)

        # Simple pulse timer
        self._timer = QtCore.QTimer(self)
        self._timer.setInterval(600)
        self._timer.timeout.connect(self._pulse)
        self._opacity = 0.4
        self._dir = 0.1
        self._timer.start()

    def apply_theme(self, theme: Theme):
        self._t = theme
        self.dots.setStyleSheet(f"color: {theme.text_quiet}; font-size: 12px; background: transparent;")

    def _pulse(self):
        self._opacity += self._dir
        if self._opacity >= 1.0 or self._opacity <= 0.3:
            self._dir *= -1
        alpha = int(self._opacity * 255)
        color = self._t.accent.base
        self.dots.setStyleSheet(
            f"color: rgba({int(color[1:3], 16)}, {int(color[3:5], 16)}, {int(color[5:7], 16)}, {self._opacity}); "
            f"font-size: 12px; background: transparent;"
        )

    def deleteLater(self):
        self._timer.stop()
        super().deleteLater()


class ChatEmptyState(QtWidgets.QWidget):
    """Welcome screen with branding, subtitle, and starter suggestion chips."""

    SUGGESTIONS = [
        "Explain a concept",
        "Write some code",
        "Summarize text",
        "Draft an email",
        "Translate this",
        "Plan a project",
        "Debug my code",
        "Write a poem",
    ]

    def __init__(self, theme: Theme, on_chip_clicked=None):
        super().__init__()
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 96, 0, 0)
        layout.setSpacing(6)
        layout.setAlignment(
            QtCore.Qt.AlignmentFlag.AlignHCenter
            | QtCore.Qt.AlignmentFlag.AlignTop
        )
        layout.addStretch(0)

        self.title = QtWidgets.QLabel("Arca")
        self.title.setObjectName("emptyTitle")
        self.title.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.title)

        self.sub = QtWidgets.QLabel(
            "Your models. Your machine. Your rules."
        )
        self.sub.setObjectName("emptySub")
        self.sub.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.sub)

        layout.addSpacing(32)

        # Suggestion chips in two centered rows
        self.chips: list[QtWidgets.QPushButton] = []
        mid = len(self.SUGGESTIONS) // 2
        for row_labels in (self.SUGGESTIONS[:mid], self.SUGGESTIONS[mid:]):
            chips_row = QtWidgets.QHBoxLayout()
            chips_row.setSpacing(8)
            for label in row_labels:
                btn = _Chip(label, theme, on_chip_clicked)
                self.chips.append(btn)
                chips_row.addWidget(btn)
            holder = QtWidgets.QHBoxLayout()
            holder.setContentsMargins(0, 0, 0, 0)
            holder.addStretch()
            holder.addLayout(chips_row)
            holder.addStretch()
            layout.addLayout(holder)

        self._t = theme
        self.apply_theme(theme)

    def apply_theme(self, theme: Theme):
        self._t = theme
        self.setStyleSheet(self._t.empty_state_css())
        for chip in self.chips:
            chip.apply_theme(self._t)


class _Chip(QtWidgets.QPushButton):
    """Stylized clickable suggestion chip."""

    def __init__(self, label: str, theme: Theme, on_clicked=None):
        super().__init__(label)
        self._t = theme
        self.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
        if on_clicked:
            self.clicked.connect(lambda: on_clicked(label))
        self.apply_theme(theme)

    def apply_theme(self, theme: Theme):
        self._t = theme
        self.setStyleSheet(self._t.chip_css())

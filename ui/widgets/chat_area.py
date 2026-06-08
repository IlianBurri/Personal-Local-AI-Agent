from PyQt6 import QtWidgets, QtCore

from ui.widgets.message_widget import MessageWidget


class ChatArea(QtWidgets.QScrollArea):
    def __init__(self):
        super().__init__()
        self.setWidgetResizable(True)
        self.setStyleSheet("""
            QScrollArea {
                background: #0f172a;
                border: none;
            }
            QScrollBar:vertical {
                background: transparent;
                width: 8px;
            }
            QScrollBar::handle:vertical {
                background: #334155;
                border-radius: 4px;
                min-height: 28px;
            }
            QScrollBar::add-line:vertical,
            QScrollBar::sub-line:vertical {
                height: 0;
            }
        """)

        self.container = QtWidgets.QWidget()
        self.container.setStyleSheet("background: #0f172a;")
        self.vbox = QtWidgets.QVBoxLayout(self.container)
        self.vbox.setContentsMargins(34, 28, 34, 28)
        self.vbox.setSpacing(14)
        self.vbox.addStretch()
        self.setWidget(self.container)

        self._empty = QtWidgets.QWidget()
        empty_layout = QtWidgets.QVBoxLayout(self._empty)
        empty_layout.setContentsMargins(0, 90, 0, 0)
        empty_layout.setSpacing(8)

        title = QtWidgets.QLabel("Ready when you are.")
        title.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet("color:#e5e7eb; font-size:26px; font-weight:900;")
        empty_layout.addWidget(title)

        subtitle = QtWidgets.QLabel("Pick a model, ask naturally, and keep the thread in one place.")
        subtitle.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        subtitle.setStyleSheet("color:#64748b; font-size:14px;")
        empty_layout.addWidget(subtitle)

        self.vbox.insertWidget(0, self._empty)

    def add_message(self, role: str, text: str) -> MessageWidget:
        self._empty.hide()
        widget = MessageWidget(role, text)
        self.vbox.insertWidget(self.vbox.count() - 1, widget)
        self.scroll_to_bottom()
        return widget

    def add_system_notice(self, text: str):
        self._empty.hide()
        notice = QtWidgets.QLabel(text)
        notice.setWordWrap(True)
        notice.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        notice.setStyleSheet("""
            QLabel {
                color: #fbbf24;
                background: #1f2937;
                border: 1px solid #374151;
                border-radius: 8px;
                padding: 10px 12px;
                font-size: 13px;
            }
        """)
        self.vbox.insertWidget(self.vbox.count() - 1, notice)
        self.scroll_to_bottom()

    def scroll_to_bottom(self):
        QtCore.QTimer.singleShot(
            20,
            lambda: self.verticalScrollBar().setValue(
                self.verticalScrollBar().maximum()
            )
        )

    def clear(self):
        while self.vbox.count() > 1:
            item = self.vbox.takeAt(0)
            widget = item.widget()
            if widget and widget is not self._empty:
                widget.deleteLater()

        self.vbox.insertWidget(0, self._empty)
        self._empty.show()

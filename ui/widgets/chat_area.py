from PyQt6 import QtWidgets, QtCore
from ui.widgets.message_widget import MessageWidget


class ChatArea(QtWidgets.QScrollArea):

    def __init__(self):
        super().__init__()
        self.setWidgetResizable(True)
        self.setStyleSheet("""
            QScrollArea {
                background: #0d1117;
                border: none;
            }
            QScrollBar:vertical {
                background: #0d1117;
                width: 6px;
                border-radius: 3px;
            }
            QScrollBar::handle:vertical {
                background: #334155;
                border-radius: 3px;
                min-height: 20px;
            }
            QScrollBar::add-line:vertical,
            QScrollBar::sub-line:vertical {
                height: 0;
            }
        """)

        self.container = QtWidgets.QWidget()
        self.container.setStyleSheet("background: #0d1117;")

        self.vbox = QtWidgets.QVBoxLayout(self.container)
        self.vbox.setContentsMargins(24, 24, 24, 24)
        self.vbox.setSpacing(8)
        self.vbox.addStretch()

        self.setWidget(self.container)

        self._empty_label = QtWidgets.QLabel("Start a conversation")
        self._empty_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self._empty_label.setStyleSheet("""
            color: #334155;
            font-size: 15px;
            font-weight: 500;
        """)
        self.vbox.insertWidget(0, self._empty_label)

    def add_message(self, role: str, text: str) -> MessageWidget:
        if self._empty_label.isVisible():
            self._empty_label.hide()

        widget = MessageWidget(role, text)
        self.vbox.insertWidget(self.vbox.count() - 1, widget)

        QtCore.QTimer.singleShot(
            30,
            lambda: self.verticalScrollBar().setValue(
                self.verticalScrollBar().maximum()
            )
        )
        return widget

    def clear(self):
        while self.vbox.count() > 1:
            item = self.vbox.takeAt(0)
            if item.widget() and item.widget() is not self._empty_label:
                item.widget().deleteLater()

        self._empty_label.show()

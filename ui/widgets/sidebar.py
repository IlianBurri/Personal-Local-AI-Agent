from PyQt6 import QtWidgets, QtCore


class ChatItem(QtWidgets.QWidget):
    delete_requested = QtCore.pyqtSignal()
    rename_requested = QtCore.pyqtSignal()

    def __init__(self, title: str):
        super().__init__()
        self.setFixedHeight(42)

        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(10, 0, 6, 0)
        layout.setSpacing(8)

        self.marker = QtWidgets.QFrame()
        self.marker.setFixedSize(3, 18)
        self.marker.setStyleSheet("background: transparent; border-radius: 1px;")
        layout.addWidget(self.marker)

        self.title_lbl = QtWidgets.QLabel(title)
        self.title_lbl.setWordWrap(False)
        self.title_lbl.setMinimumWidth(0)
        self.title_lbl.setStyleSheet("color:#9ca3af; font-size:13px;")
        layout.addWidget(self.title_lbl, 1)

        self.rename_btn = QtWidgets.QPushButton("Edit")
        self.rename_btn.setFixedSize(38, 24)
        self.rename_btn.setToolTip("Rename chat")
        self.rename_btn.setStyleSheet(self._action_style())
        self.rename_btn.clicked.connect(self.rename_requested.emit)
        layout.addWidget(self.rename_btn)

        self.delete_btn = QtWidgets.QPushButton("Del")
        self.delete_btn.setFixedSize(34, 24)
        self.delete_btn.setToolTip("Delete chat")
        self.delete_btn.setStyleSheet(self._action_style(danger=True))
        self.delete_btn.clicked.connect(self.delete_requested.emit)
        layout.addWidget(self.delete_btn)

        self.rename_btn.hide()
        self.delete_btn.hide()

    def _action_style(self, danger=False):
        hover = "#7f1d1d" if danger else "#223049"
        color = "#fecaca" if danger else "#cbd5e1"
        return f"""
            QPushButton {{
                background: transparent;
                color: {color};
                border: none;
                border-radius: 5px;
                font-size: 11px;
                font-weight: 700;
            }}
            QPushButton:hover {{
                background: {hover};
            }}
        """

    def set_title(self, title: str):
        self.title_lbl.setText(title)

    def set_active(self, active: bool):
        if active:
            self.setStyleSheet("background: #172033; border-radius: 8px;")
            self.marker.setStyleSheet("background: #22c55e; border-radius: 1px;")
            self.title_lbl.setStyleSheet("color:#f8fafc; font-size:13px; font-weight:700;")
        else:
            self.setStyleSheet("background: transparent;")
            self.marker.setStyleSheet("background: transparent; border-radius: 1px;")
            self.title_lbl.setStyleSheet("color:#9ca3af; font-size:13px;")

    def enterEvent(self, event):
        self.rename_btn.show()
        self.delete_btn.show()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self.rename_btn.hide()
        self.delete_btn.hide()
        super().leaveEvent(event)


class Sidebar(QtWidgets.QWidget):
    new_chat_clicked = QtCore.pyqtSignal()
    chat_selected = QtCore.pyqtSignal(int)
    chat_deleted = QtCore.pyqtSignal(int)
    chat_renamed = QtCore.pyqtSignal(int, str)

    def __init__(self):
        super().__init__()
        self.setFixedWidth(282)
        self._items: dict[int, tuple[QtWidgets.QListWidgetItem, ChatItem]] = {}
        self._active_id: int | None = None

        self.setStyleSheet("""
            QWidget {
                background: #0b1020;
                border: none;
            }
        """)

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(14, 18, 14, 16)
        layout.setSpacing(10)

        brand = QtWidgets.QLabel("ARCA")
        brand.setStyleSheet("""
            color: #f8fafc;
            font-size: 20px;
            font-weight: 900;
            letter-spacing: 2px;
            padding: 0 4px;
        """)
        layout.addWidget(brand)

        tag = QtWidgets.QLabel("Private AI workspace")
        tag.setStyleSheet("color:#64748b; font-size:12px; padding: 0 4px 6px 4px;")
        layout.addWidget(tag)

        self.new_chat_btn = QtWidgets.QPushButton("New chat")
        self.new_chat_btn.setFixedHeight(40)
        self.new_chat_btn.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
        self.new_chat_btn.setStyleSheet("""
            QPushButton {
                background: #16a34a;
                color: #052e16;
                border: none;
                border-radius: 8px;
                font-size: 13px;
                font-weight: 900;
            }
            QPushButton:hover {
                background: #22c55e;
            }
            QPushButton:pressed {
                background: #15803d;
            }
        """)
        layout.addWidget(self.new_chat_btn)

        section = QtWidgets.QLabel("CHATS")
        section.setStyleSheet("""
            color:#475569;
            font-size:10px;
            font-weight:900;
            letter-spacing:1.4px;
            padding: 8px 4px 0 4px;
        """)
        layout.addWidget(section)

        self.chat_list = QtWidgets.QListWidget()
        self.chat_list.setStyleSheet("""
            QListWidget {
                background: transparent;
                border: none;
                outline: none;
            }
            QListWidget::item {
                background: transparent;
                border: none;
                padding: 0;
                margin: 2px 0;
            }
            QListWidget::item:selected {
                background: transparent;
            }
        """)
        self.chat_list.setSpacing(2)
        self.chat_list.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        layout.addWidget(self.chat_list, 1)

        self.new_chat_btn.clicked.connect(self.new_chat_clicked.emit)
        self.chat_list.itemClicked.connect(self._on_item_clicked)

    def add_chat(self, chat_id: int, title: str):
        item = QtWidgets.QListWidgetItem()
        item.setData(QtCore.Qt.ItemDataRole.UserRole, chat_id)
        item.setSizeHint(QtCore.QSize(0, 42))

        widget = ChatItem(title)
        widget.delete_requested.connect(lambda: self._on_delete(chat_id))
        widget.rename_requested.connect(lambda: self._on_rename(chat_id, widget))

        self.chat_list.addItem(item)
        self.chat_list.setItemWidget(item, widget)
        self._items[chat_id] = (item, widget)

    def set_active(self, chat_id: int):
        if self._active_id is not None and self._active_id in self._items:
            _, old_widget = self._items[self._active_id]
            old_widget.set_active(False)
        self._active_id = chat_id
        if chat_id in self._items:
            _, widget = self._items[chat_id]
            widget.set_active(True)

    def update_title(self, chat_id: int, title: str):
        if chat_id in self._items:
            _, widget = self._items[chat_id]
            widget.set_title(title)

    def clear(self):
        self.chat_list.clear()
        self._items.clear()
        self._active_id = None

    def _on_item_clicked(self, item: QtWidgets.QListWidgetItem):
        chat_id = item.data(QtCore.Qt.ItemDataRole.UserRole)
        self.set_active(chat_id)
        self.chat_selected.emit(chat_id)

    def _on_delete(self, chat_id: int):
        reply = QtWidgets.QMessageBox.question(
            self,
            "Delete chat",
            "Delete this chat and its messages?",
            QtWidgets.QMessageBox.StandardButton.Yes | QtWidgets.QMessageBox.StandardButton.No,
        )
        if reply == QtWidgets.QMessageBox.StandardButton.Yes:
            self.chat_deleted.emit(chat_id)

    def _on_rename(self, chat_id: int, widget: ChatItem):
        new_title, ok = QtWidgets.QInputDialog.getText(
            self,
            "Rename chat",
            "Name",
            text=widget.title_lbl.text(),
        )
        if ok and new_title.strip():
            title = new_title.strip()
            widget.set_title(title)
            self.chat_renamed.emit(chat_id, title)

from PyQt6 import QtWidgets, QtCore, QtGui


class ChatItem(QtWidgets.QWidget):
    """Single chat item with hover actions."""

    delete_requested = QtCore.pyqtSignal()
    rename_requested = QtCore.pyqtSignal()

    def __init__(self, title: str):
        super().__init__()
        self.setFixedHeight(44)

        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(12, 0, 8, 0)
        layout.setSpacing(6)

        self.icon = QtWidgets.QLabel("💬")
        self.icon.setFixedWidth(18)
        layout.addWidget(self.icon)

        self.title_lbl = QtWidgets.QLabel(title)
        self.title_lbl.setStyleSheet("color:#CBD5E1; font-size:13px;")
        self.title_lbl.setMaximumWidth(160)
        self.title_lbl.setWordWrap(False)
        self.title_lbl.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Expanding,
            QtWidgets.QSizePolicy.Policy.Preferred
        )
        layout.addWidget(self.title_lbl, 1)

        self.action_container = QtWidgets.QWidget()
        action_row = QtWidgets.QHBoxLayout(self.action_container)
        action_row.setContentsMargins(0, 0, 0, 0)
        action_row.setSpacing(2)

        self.rename_btn = QtWidgets.QPushButton("✏")
        self.rename_btn.setFixedSize(24, 24)
        self.rename_btn.setToolTip("Rename")
        self.rename_btn.setStyleSheet(self._icon_btn_style())
        self.rename_btn.clicked.connect(self.rename_requested.emit)
        action_row.addWidget(self.rename_btn)

        self.delete_btn = QtWidgets.QPushButton("🗑")
        self.delete_btn.setFixedSize(24, 24)
        self.delete_btn.setToolTip("Delete")
        self.delete_btn.setStyleSheet(self._icon_btn_style("#ef4444"))
        self.delete_btn.clicked.connect(self.delete_requested.emit)
        action_row.addWidget(self.delete_btn)

        layout.addWidget(self.action_container)
        self.action_container.hide()

    def _icon_btn_style(self, hover_color="#64748b"):
        return f"""
            QPushButton {{
                background: transparent;
                border: none;
                border-radius: 4px;
                font-size: 13px;
                padding: 2px;
            }}
            QPushButton:hover {{
                background: rgba(255,255,255,0.08);
            }}
        """

    def set_title(self, title: str):
        self.title_lbl.setText(title)

    def set_active(self, active: bool):
        if active:
            self.setStyleSheet("background: #1e293b; border-radius: 8px;")
            self.title_lbl.setStyleSheet("color:#f1f5f9; font-size:13px; font-weight:600;")
        else:
            self.setStyleSheet("background: transparent;")
            self.title_lbl.setStyleSheet("color:#94a3b8; font-size:13px;")

    def enterEvent(self, event):
        self.action_container.show()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self.action_container.hide()
        super().leaveEvent(event)


class Sidebar(QtWidgets.QWidget):
    new_chat_clicked = QtCore.pyqtSignal()
    chat_selected = QtCore.pyqtSignal(int)
    chat_deleted = QtCore.pyqtSignal(int)
    chat_renamed = QtCore.pyqtSignal(int, str)

    def __init__(self):
        super().__init__()
        self.setFixedWidth(260)
        self._items: dict[int, tuple[QtWidgets.QListWidgetItem, ChatItem]] = {}
        self._active_id: int | None = None

        self.setStyleSheet("""
            QWidget {
                background: #0f1117;
                border: none;
            }
        """)

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(12, 16, 12, 16)
        layout.setSpacing(0)

        # Brand
        brand = QtWidgets.QLabel("✦ arca")
        brand.setStyleSheet("""
            color: #3b82f6;
            font-size: 16px;
            font-weight: 700;
            letter-spacing: 2px;
            padding: 0 4px 16px 4px;
        """)
        layout.addWidget(brand)

        # New Chat Button
        self.new_chat_btn = QtWidgets.QPushButton("+ New Chat")
        self.new_chat_btn.setFixedHeight(38)
        self.new_chat_btn.setStyleSheet("""
            QPushButton {
                background: #1d4ed8;
                color: #fff;
                border: none;
                border-radius: 8px;
                font-size: 13px;
                font-weight: 600;
                padding: 0 16px;
                margin-bottom: 12px;
            }
            QPushButton:hover {
                background: #2563eb;
            }
            QPushButton:pressed {
                background: #1e40af;
            }
        """)
        layout.addWidget(self.new_chat_btn)

        # Section label
        section = QtWidgets.QLabel("CHATS")
        section.setStyleSheet("color:#475569; font-size:10px; font-weight:700; letter-spacing:1.5px; padding: 8px 4px 6px 4px;")
        layout.addWidget(section)

        # Chat list
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
                margin: 1px 0;
                border-radius: 8px;
            }
            QListWidget::item:selected {
                background: transparent;
            }
        """)
        self.chat_list.setSpacing(1)
        self.chat_list.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        layout.addWidget(self.chat_list, 1)

        # Signals
        self.new_chat_btn.clicked.connect(self.new_chat_clicked.emit)
        self.chat_list.itemClicked.connect(self._on_item_clicked)

    def add_chat(self, chat_id: int, title: str):
        item = QtWidgets.QListWidgetItem()
        item.setData(QtCore.Qt.ItemDataRole.UserRole, chat_id)
        item.setSizeHint(QtCore.QSize(0, 44))

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
            self, "Delete Chat",
            "Delete this chat?",
            QtWidgets.QMessageBox.StandardButton.Yes | QtWidgets.QMessageBox.StandardButton.No
        )
        if reply == QtWidgets.QMessageBox.StandardButton.Yes:
            self.chat_deleted.emit(chat_id)

    def _on_rename(self, chat_id: int, widget: ChatItem):
        current = widget.title_lbl.text()
        new_title, ok = QtWidgets.QInputDialog.getText(
            self, "Rename Chat", "New name:", text=current
        )
        if ok and new_title.strip():
            widget.set_title(new_title.strip())
            self.chat_renamed.emit(chat_id, new_title.strip())

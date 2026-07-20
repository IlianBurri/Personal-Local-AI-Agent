from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Optional

from PyQt6 import QtCore, QtGui, QtWidgets

from ui.theme import Theme


class _SectionHeader(QtWidgets.QLabel):
    def __init__(self, text: str, theme: Theme):
        super().__init__(text)
        self._t = theme
        self.apply_theme(theme)

    def apply_theme(self, theme: Theme):
        self._t = theme
        self.setStyleSheet(theme.section_header_css())


class Sidebar(QtWidgets.QWidget):
    new_chat_clicked = QtCore.pyqtSignal()
    chat_selected = QtCore.pyqtSignal(int)
    chat_deleted = QtCore.pyqtSignal(int)
    chat_renamed = QtCore.pyqtSignal(int, str)

    def __init__(self, theme: Theme):
        super().__init__()
        self.setObjectName("sidebarRoot")
        self._t = theme
        self._chats: dict[int, tuple[str, Optional[str]]] = {}
        self._items: dict[int, ChatRow] = {}
        self._section_headers: list[_SectionHeader] = []
        self._active_id: Optional[int] = None
        self._build()
        self.apply_theme(self._t)

    def _build(self):
        root = QtWidgets.QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Brand header
        brand = QtWidgets.QHBoxLayout()
        brand.setContentsMargins(20, 16, 16, 8)
        brand.setSpacing(0)
        self.brand_lbl = QtWidgets.QLabel("Arca")
        brand.addWidget(self.brand_lbl)
        brand.addStretch()
        root.addLayout(brand)

        # New chat row
        new_row = QtWidgets.QHBoxLayout()
        new_row.setContentsMargins(12, 4, 12, 8)
        self.new_btn = QtWidgets.QPushButton("New chat")
        self.new_btn.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
        self.new_btn.setToolTip("Start a new chat")
        self.new_btn.clicked.connect(self.new_chat_clicked.emit)
        new_row.addWidget(self.new_btn)
        new_row.addStretch()
        root.addLayout(new_row)

        # Scrollable list of chats
        self.scroll = QtWidgets.QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
        self.scroll.setStyleSheet("background: transparent; border: none;")

        self.list_container = QtWidgets.QWidget()
        self.list_layout = QtWidgets.QVBoxLayout(self.list_container)
        self.list_layout.setContentsMargins(0, 4, 0, 12)
        self.list_layout.setSpacing(0)
        self.list_layout.addStretch(1)

        self.scroll.setWidget(self.list_container)
        root.addWidget(self.scroll, 1)

    # -- public API --
    def apply_theme(self, theme: Theme):
        self._t = theme
        self.setStyleSheet(self._t.sidebar_css())
        scroll_qss = self._t.scrollbar_css() + "QScrollArea { background: transparent; border: none; }"
        self.scroll.setStyleSheet(scroll_qss)
        self.list_container.setStyleSheet("background: transparent;")
        self.brand_lbl.setStyleSheet(self._t.wordmark_css())
        self.new_btn.setStyleSheet(self._t.ghost_btn_css())
        # Restyle existing rows and section headers; do NOT rebuild the list
        # on every theme switch.
        for chat_id, row in self._items.items():
            row.apply_theme(self._t, active=chat_id == self._active_id)
        for header in self._section_headers:
            header.apply_theme(self._t)

    def add_chat(self, chat_id: int, title: str, created_at: Optional[str] = None):
        self._chats[chat_id] = (title, created_at)
        self._rebuild()

    def update_title(self, chat_id: int, title: str):
        if chat_id in self._chats:
            self._chats[chat_id] = (title, self._chats[chat_id][1])
        if chat_id in self._items:
            self._items[chat_id].set_title(title)

    def clear(self):
        self._chats.clear()
        self._items.clear()
        self._active_id = None
        self._rebuild()

    def set_active(self, chat_id: int):
        if self._active_id in self._items:
            self._items[self._active_id].set_active(False)
        self._active_id = chat_id
        if chat_id in self._items:
            self._items[chat_id].set_active(True)

    # -- internals --
    def _delete(self, chat_id: int):
        reply = QtWidgets.QMessageBox.question(
            self, "Delete chat", "Delete this chat?",
            QtWidgets.QMessageBox.StandardButton.Yes
            | QtWidgets.QMessageBox.StandardButton.No,
        )
        if reply == QtWidgets.QMessageBox.StandardButton.Yes:
            if chat_id in self._items:
                del self._items[chat_id]
            if chat_id in self._chats:
                del self._chats[chat_id]
            if self._active_id == chat_id:
                self._active_id = None
            self._rebuild()
            self.chat_deleted.emit(chat_id)

    def _rename(self, chat_id: int, row: "ChatRow"):
        new_title, ok = QtWidgets.QInputDialog.getText(
            self, "Rename chat", "Enter new title:", text=row.title_lbl.text()
        )
        if ok and new_title.strip():
            title = new_title.strip()
            self._chats[chat_id] = (title, self._chats[chat_id][1])
            row.set_title(title)
            self.chat_renamed.emit(chat_id, title)

    def _select(self, chat_id: int):
        if chat_id == self._active_id:
            return
        self.set_active(chat_id)
        self.chat_selected.emit(chat_id)

    def _rebuild(self):
        # Clear layout (keep stretch at end)
        while self.list_layout.count() > 1:
            item = self.list_layout.takeAt(0)
            w = item.widget() if item else None
            if w is not None:
                w.setParent(None)
                w.deleteLater()
        self._items.clear()
        self._section_headers.clear()

        # Group chats by date bucket (most recent first within each bucket)
        buckets = _bucketize(self._chats)
        for label, items in buckets:
            if not items:
                continue
            header = _SectionHeader(label, self._t)
            self._section_headers.append(header)
            self.list_layout.addWidget(header)
            for chat_id, title in items:
                row = ChatRow(chat_id, title, self._t, self._active_id == chat_id)
                row.clicked.connect(self._select)
                row.delete_requested.connect(self._delete)
                row.rename_requested.connect(self._rename)
                self.list_layout.addWidget(row)
                self._items[chat_id] = row


class ChatRow(QtWidgets.QWidget):
    clicked = QtCore.pyqtSignal(int)
    delete_requested = QtCore.pyqtSignal(int)
    rename_requested = QtCore.pyqtSignal(int)

    def __init__(self, chat_id: int, title: str, theme: Theme, active: bool):
        super().__init__()
        self.chat_id = chat_id
        self._t = theme
        self._active = active
        self.setFixedHeight(30)
        self.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)

        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(12, 0, 8, 0)
        layout.setSpacing(0)

        self.title_lbl = QtWidgets.QLabel(title)
        self.title_lbl.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Expanding,
            QtWidgets.QSizePolicy.Policy.Preferred,
        )
        layout.addWidget(self.title_lbl, 1)

        self.apply_theme(self._t, self._active)

    # -- public API --
    def set_active(self, active: bool):
        self._active = active
        self.apply_theme(self._t, active)

    def set_title(self, title: str):
        self.title_lbl.setText(title)

    def apply_theme(self, theme: Theme, active: bool):
        self._t = theme
        self._active = active
        bg = self._t.bg_active if active else "transparent"
        color = self._t.text_main if active else self._t.text_sub
        weight = "500" if active else "400"
        self.setStyleSheet(
            f"background: {bg}; border-radius: 6px;"
        )
        self.title_lbl.setStyleSheet(
            f"color: {color}; font-family: {self._t.font_stack}; "
            f"font-size: 13px; font-weight: {weight}; background: transparent;"
        )

    # -- events --
    def enterEvent(self, event):
        if not self._active:
            self.setStyleSheet(f"background: {self._t.bg_hover}; border-radius: 6px;")

    def leaveEvent(self, event):
        if not self._active:
            self.setStyleSheet("background: transparent; border-radius: 6px;")

    def mousePressEvent(self, event: QtGui.QMouseEvent):
        if event.button() == QtCore.Qt.MouseButton.LeftButton:
            self.clicked.emit(self.chat_id)
        super().mousePressEvent(event)

    def contextMenuEvent(self, event: QtGui.QContextMenuEvent):
        menu = QtWidgets.QMenu(self)
        menu.setStyleSheet(self._t.menu_css())
        rename = menu.addAction("Rename")
        menu.addSeparator()
        delete = menu.addAction("Delete")
        action = menu.exec(event.globalPos())
        if action == rename:
            self.rename_requested.emit(self.chat_id)
        elif action == delete:
            self.delete_requested.emit(self.chat_id)


def _bucketize(
    chats: dict[int, tuple[str, Optional[str]]],
) -> list[tuple[str, list[tuple[int, str]]]]:
    """Group chats into Today / Yesterday / Previous 7 days / Older."""
    today = date.today()
    yesterday = today - timedelta(days=1)
    week_ago = today - timedelta(days=7)

    today_list: list[tuple[int, str]] = []
    yesterday_list: list[tuple[int, str]] = []
    week_list: list[tuple[int, str]] = []
    older_list: list[tuple[int, str]] = []

    for chat_id, (title, c_at) in chats.items():
        d = _parse_date(c_at)
        if d == today:
            today_list.append((chat_id, title))
        elif d == yesterday:
            yesterday_list.append((chat_id, title))
        elif d is not None and d > week_ago:
            week_list.append((chat_id, title))
        else:
            older_list.append((chat_id, title))

    return [
        ("Today", _sort_by_recent(today_list)),
        ("Yesterday", _sort_by_recent(yesterday_list)),
        ("Previous 7 days", _sort_by_recent(week_list)),
        ("Older", _sort_by_recent(older_list)),
    ]


def _sort_by_recent(items: list[tuple[int, str]]) -> list[tuple[int, str]]:
    # chats_id DESC already approximates recency (since ids are auto-increment).
    return sorted(items, key=lambda x: x[0], reverse=True)


def _parse_date(value: Optional[str]) -> Optional[date]:
    if not value:
        return None
    try:
        # SQLite CURRENT_TIMESTAMP: "YYYY-MM-DD HH:MM:SS"
        return datetime.fromisoformat(value).date()
    except Exception:
        return None

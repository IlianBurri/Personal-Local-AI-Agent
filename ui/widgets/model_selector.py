from PyQt6 import QtWidgets, QtCore
from core.providers import OllamaClient


class ModelSelector(QtWidgets.QWidget):

    def __init__(self):
        super().__init__()
        self.setFixedHeight(48)
        self.setStyleSheet("background: #0d1117; border-bottom: 1px solid #1e293b;")

        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(24, 0, 24, 0)
        layout.setSpacing(10)

        label = QtWidgets.QLabel("Model")
        label.setStyleSheet("color: #64748b; font-size: 12px; font-weight: 600; letter-spacing: 0.5px;")
        layout.addWidget(label)

        self.combo = QtWidgets.QComboBox()
        self.combo.setFixedHeight(32)
        self.combo.setMinimumWidth(200)
        self.combo.setStyleSheet("""
            QComboBox {
                background: #1e293b;
                color: #f1f5f9;
                border: 1px solid #334155;
                border-radius: 8px;
                padding: 0 12px;
                font-size: 13px;
            }
            QComboBox:hover {
                border-color: #3b82f6;
            }
            QComboBox::drop-down {
                border: none;
                padding-right: 8px;
            }
            QComboBox QAbstractItemView {
                background: #1e293b;
                color: #f1f5f9;
                border: 1px solid #334155;
                selection-background-color: #3b82f6;
                outline: none;
            }
        """)
        layout.addWidget(self.combo)

        self.refresh_btn = QtWidgets.QPushButton("⟳")
        self.refresh_btn.setFixedSize(32, 32)
        self.refresh_btn.setToolTip("Refresh models")
        self.refresh_btn.setStyleSheet("""
            QPushButton {
                background: #1e293b;
                color: #94a3b8;
                border: 1px solid #334155;
                border-radius: 8px;
                font-size: 15px;
            }
            QPushButton:hover {
                background: #334155;
                color: #f1f5f9;
            }
        """)
        self.refresh_btn.clicked.connect(self.load_models)
        layout.addWidget(self.refresh_btn)

        layout.addStretch()

        self.status = QtWidgets.QLabel("")
        self.status.setStyleSheet("color: #475569; font-size: 11px;")
        layout.addWidget(self.status)

        self.load_models()

    def load_models(self):
        self.status.setText("Loading…")
        try:
            client = OllamaClient()
            models = client.list_models()
            self.combo.clear()
            names = []
            for m in models.get("models", []):
                name = m.get("name")
                if name:
                    names.append(name)
            if names:
                self.combo.addItems(names)
                self.status.setText(f"{len(names)} models")
            else:
                self.combo.addItem("llama3")
                self.status.setText("No models found")
        except Exception:
            self.combo.clear()
            self.combo.addItem("llama3")
            self.status.setText("Ollama offline")

    def current_model(self) -> str:
        return self.combo.currentText()

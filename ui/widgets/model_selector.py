from PyQt6 import QtWidgets, QtCore

from core.providers import OllamaClient


DEFAULT_MODELS = {
    "ollama": ["llama3", "mistral", "codellama"],
    "openai": ["gpt-4o", "gpt-4o-mini"],
    "anthropic": ["claude-3-5-sonnet-latest", "claude-3-haiku-20240307"],
}


class ModelSelector(QtWidgets.QWidget):
    settings_requested = QtCore.pyqtSignal()

    def __init__(self, config=None):
        super().__init__()
        self.config = config or {}
        self.setFixedHeight(58)
        self.setStyleSheet("""
            QWidget {
                background: #10151f;
                border-bottom: 1px solid #263244;
            }
        """)

        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(22, 0, 22, 0)
        layout.setSpacing(10)

        title = QtWidgets.QLabel("Arca")
        title.setStyleSheet("""
            color: #f8fafc;
            font-size: 16px;
            font-weight: 800;
            letter-spacing: 0.8px;
            border: none;
        """)
        layout.addWidget(title)

        subtitle = QtWidgets.QLabel("local-first chat")
        subtitle.setStyleSheet("color: #64748b; font-size: 12px; border: none;")
        layout.addWidget(subtitle)
        layout.addSpacing(14)

        self.provider_combo = QtWidgets.QComboBox()
        self.provider_combo.addItems(["ollama", "openai", "anthropic"])
        self.provider_combo.setFixedHeight(34)
        self.provider_combo.setMinimumWidth(120)
        self.provider_combo.setStyleSheet(self._combo_style())
        provider = self.config.get("provider") or "ollama"
        self.provider_combo.setCurrentText(provider)
        layout.addWidget(self.provider_combo)

        self.model_combo = QtWidgets.QComboBox()
        self.model_combo.setEditable(True)
        self.model_combo.setFixedHeight(34)
        self.model_combo.setMinimumWidth(260)
        self.model_combo.setStyleSheet(self._combo_style())
        layout.addWidget(self.model_combo)

        self.refresh_btn = QtWidgets.QPushButton("Refresh")
        self.refresh_btn.setFixedHeight(34)
        self.refresh_btn.setToolTip("Refresh local Ollama models")
        self.refresh_btn.setStyleSheet(self._button_style())
        layout.addWidget(self.refresh_btn)

        self.settings_btn = QtWidgets.QPushButton("Settings")
        self.settings_btn.setFixedHeight(34)
        self.settings_btn.setStyleSheet(self._button_style(accent=True))
        layout.addWidget(self.settings_btn)

        layout.addStretch()

        self.status = QtWidgets.QLabel("")
        self.status.setStyleSheet("color: #94a3b8; font-size: 12px; border: none;")
        layout.addWidget(self.status)

        self.provider_combo.currentTextChanged.connect(self.load_models)
        self.refresh_btn.clicked.connect(self.load_models)
        self.settings_btn.clicked.connect(self.settings_requested.emit)

        self.load_models()

    def _combo_style(self):
        return """
            QComboBox {
                background: #182233;
                color: #f8fafc;
                border: 1px solid #334155;
                border-radius: 7px;
                padding: 0 10px;
                font-size: 13px;
            }
            QComboBox:hover {
                border-color: #22c55e;
            }
            QComboBox QAbstractItemView {
                background: #182233;
                color: #f8fafc;
                border: 1px solid #334155;
                selection-background-color: #2563eb;
                outline: none;
            }
        """

    def _button_style(self, accent=False):
        bg = "#1d4ed8" if accent else "#182233"
        hover = "#2563eb" if accent else "#223049"
        border = "transparent" if accent else "#334155"
        return f"""
            QPushButton {{
                background: {bg};
                color: #f8fafc;
                border: 1px solid {border};
                border-radius: 7px;
                padding: 0 12px;
                font-size: 13px;
                font-weight: 700;
            }}
            QPushButton:hover {{
                background: {hover};
            }}
        """

    def load_models(self):
        provider = self.current_provider()
        self.combo_block(True)
        self.model_combo.clear()

        if provider == "ollama":
            self.refresh_btn.setEnabled(True)
            self.status.setText("Checking Ollama...")
            try:
                base_url = self.current_base_url()
                models = OllamaClient(base_url=base_url).list_models()
                names = [
                    model.get("name")
                    for model in models.get("models", [])
                    if model.get("name")
                ]
            except Exception:
                names = []
                self.status.setText("Ollama offline")
            else:
                self.status.setText(f"{len(names)} local models" if names else "No local models")
            self.model_combo.addItems(names or DEFAULT_MODELS["ollama"])
        else:
            self.refresh_btn.setEnabled(False)
            self.model_combo.addItems(DEFAULT_MODELS[provider])
            key = self._provider_config(provider).get("api_key", "")
            self.status.setText("API key ready" if key else "Add API key in Settings")

        configured_model = self._provider_config(provider).get("model")
        if configured_model:
            self.model_combo.setCurrentText(configured_model)

        self.combo_block(False)

    def combo_block(self, blocked):
        self.provider_combo.blockSignals(blocked)
        self.model_combo.blockSignals(blocked)

    def _provider_config(self, provider):
        return self.config.get("providers", {}).get(provider, {})

    def current_provider(self) -> str:
        return self.provider_combo.currentText()

    def current_model(self) -> str:
        return self.model_combo.currentText().strip()

    def current_base_url(self) -> str:
        return self._provider_config("ollama").get("base_url", "http://localhost:11434")

    def update_config(self, config):
        self.config = config or {}
        provider = self.config.get("provider") or self.current_provider()
        self.provider_combo.setCurrentText(provider)
        self.load_models()

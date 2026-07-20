"""Settings dialog — API keys, default models, and generation parameters."""

from __future__ import annotations

from PyQt6 import QtCore, QtWidgets

from core.client_factory import list_models, providers
from core.config import (
    get_api_key,
    get_max_tokens,
    get_model,
    get_ollama_base_url,
    get_temperature,
    save_config,
    set_api_key,
    set_max_tokens,
    set_model,
    set_ollama_base_url,
    set_temperature,
)
from ui.theme import Theme


class SettingsDialog(QtWidgets.QDialog):
    """Modal settings panel with three sections.

    * API Keys — OpenAI key, Anthropic key, Ollama base URL
    * Default Models — pick preferred model per provider
    * Generation — temperature slider + max tokens spinner
    """

    def __init__(self, config: dict, theme: Theme, parent=None):
        super().__init__(parent)
        self._config = config
        self._t = theme
        self.setWindowTitle("Settings")
        self.setFixedSize(480, 520)
        self.setModal(True)

        self._build()
        self.apply_theme(self._t)

    def _build(self):
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(0)

        # Title
        title = QtWidgets.QLabel("Settings")
        title.setObjectName("dialogTitle")
        layout.addWidget(title)
        layout.addSpacing(20)

        # Scrollable content
        scroll = QtWidgets.QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(
            QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        scroll.setStyleSheet("background: transparent; border: none;")

        content = QtWidgets.QWidget()
        content.setStyleSheet("background: transparent;")
        form = QtWidgets.QVBoxLayout(content)
        form.setContentsMargins(0, 0, 0, 0)
        form.setSpacing(0)

        # ── API Keys ──────────────────────────────────────────────
        self._add_section(form, "API Keys")
        self.openai_key = self._add_password_field(
            form, "OpenAI API Key",
            get_api_key(self._config, "openai") or "",
        )
        self.anthropic_key = self._add_password_field(
            form, "Anthropic API Key",
            get_api_key(self._config, "anthropic") or "",
        )
        self.ollama_url = self._add_text_field(
            form, "Ollama Base URL",
            get_ollama_base_url(self._config),
        )

        form.addSpacing(20)

        # ── Default Models ─────────────────────────────────────────
        self._add_section(form, "Default Models")
        self.model_combos: dict[str, QtWidgets.QComboBox] = {}
        for prov in providers():
            combo = self._add_combo_field(form, prov.title(), prov)
            self.model_combos[prov] = combo

        form.addSpacing(20)

        # ── Generation ─────────────────────────────────────────────
        self._add_section(form, "Generation")

        # Temperature
        temp_row = QtWidgets.QHBoxLayout()
        temp_row.setContentsMargins(0, 0, 0, 0)
        lbl = QtWidgets.QLabel("Temperature")
        lbl.setObjectName("dialogField")
        temp_row.addWidget(lbl)
        temp_row.addStretch()
        self.temp_value = QtWidgets.QLabel()
        self.temp_value.setObjectName("dialogField")
        temp_row.addWidget(self.temp_value)
        form.addLayout(temp_row)

        self.temp_slider = QtWidgets.QSlider(
            QtCore.Qt.Orientation.Horizontal
        )
        self.temp_slider.setRange(0, 100)
        self.temp_slider.setValue(
            int(get_temperature(self._config) * 100)
        )
        self.temp_slider.valueChanged.connect(self._update_temp_label)
        form.addWidget(self.temp_slider)
        self._update_temp_label(self.temp_slider.value())

        form.addSpacing(12)

        # Max tokens
        tokens_row = QtWidgets.QHBoxLayout()
        tokens_row.setContentsMargins(0, 0, 0, 0)
        tokens_lbl = QtWidgets.QLabel("Max tokens")
        tokens_lbl.setObjectName("dialogField")
        tokens_row.addWidget(tokens_lbl)
        tokens_row.addStretch()
        self.max_tokens_spin = QtWidgets.QSpinBox()
        self.max_tokens_spin.setRange(64, 128000)
        self.max_tokens_spin.setSingleStep(256)
        self.max_tokens_spin.setValue(get_max_tokens(self._config))
        self.max_tokens_spin.setFixedWidth(120)
        tokens_row.addWidget(self.max_tokens_spin)
        form.addLayout(tokens_row)

        form.addStretch()
        scroll.setWidget(content)
        layout.addWidget(scroll, 1)

        # ── Buttons ───────────────────────────────────────────────
        layout.addSpacing(16)
        btn_row = QtWidgets.QHBoxLayout()
        btn_row.setSpacing(8)
        btn_row.addStretch()

        cancel_btn = QtWidgets.QPushButton("Cancel")
        cancel_btn.setObjectName("dialogCancel")
        cancel_btn.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(cancel_btn)

        save_btn = QtWidgets.QPushButton("Save")
        save_btn.setObjectName("dialogSave")
        save_btn.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
        save_btn.clicked.connect(self._save)
        btn_row.addWidget(save_btn)

        layout.addLayout(btn_row)

    # ── helpers ────────────────────────────────────────────────────
    def _add_section(self, parent, text: str):
        lbl = QtWidgets.QLabel(text)
        lbl.setObjectName("dialogSection")
        parent.addWidget(lbl)

    def _add_password_field(self, parent, label: str, value: str):
        row = QtWidgets.QHBoxLayout()
        row.setContentsMargins(0, 6, 0, 6)
        row.setSpacing(8)
        lbl = QtWidgets.QLabel(label)
        lbl.setObjectName("dialogField")
        lbl.setFixedWidth(140)
        edit = QtWidgets.QLineEdit(value)
        edit.setEchoMode(QtWidgets.QLineEdit.EchoMode.Password)
        edit.setPlaceholderText("Not set")
        row.addWidget(lbl)
        row.addWidget(edit, 1)
        parent.addLayout(row)
        return edit

    def _add_text_field(self, parent, label: str, value: str):
        row = QtWidgets.QHBoxLayout()
        row.setContentsMargins(0, 6, 0, 6)
        row.setSpacing(8)
        lbl = QtWidgets.QLabel(label)
        lbl.setObjectName("dialogField")
        lbl.setFixedWidth(140)
        edit = QtWidgets.QLineEdit(value)
        row.addWidget(lbl)
        row.addWidget(edit, 1)
        parent.addLayout(row)
        return edit

    def _add_combo_field(
        self, parent, label: str, provider: str
    ) -> QtWidgets.QComboBox:
        row = QtWidgets.QHBoxLayout()
        row.setContentsMargins(0, 6, 0, 6)
        row.setSpacing(8)
        lbl = QtWidgets.QLabel(label)
        lbl.setObjectName("dialogField")
        lbl.setFixedWidth(140)
        combo = QtWidgets.QComboBox()
        combo.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)

        # Populate models for this provider
        models = list_models(provider, self._config)
        combo.addItems(models)
        preferred = get_model(self._config, provider)
        if preferred and preferred in models:
            combo.setCurrentText(preferred)
        elif models:
            combo.setCurrentIndex(0)

        row.addWidget(lbl)
        row.addWidget(combo, 1)
        parent.addLayout(row)
        return combo

    def _update_temp_label(self, value: int):
        self.temp_value.setText(f"{value / 100:.2f}")

    # ── theming ────────────────────────────────────────────────────
    def apply_theme(self, theme: Theme):
        self._t = theme
        self.setStyleSheet(self._t.dialog_css())

    # ── save ───────────────────────────────────────────────────────
    def _save(self):
        # API keys
        key = self.openai_key.text().strip()
        if key:
            set_api_key(self._config, "openai", key)
        key = self.anthropic_key.text().strip()
        if key:
            set_api_key(self._config, "anthropic", key)

        # Ollama base URL
        url = self.ollama_url.text().strip()
        if url:
            set_ollama_base_url(self._config, url)

        # Default models
        for prov, combo in self.model_combos.items():
            model = combo.currentText().strip()
            if model:
                set_model(self._config, prov, model)

        # Generation params
        set_temperature(self._config, self.temp_slider.value() / 100)
        set_max_tokens(self._config, self.max_tokens_spin.value())

        save_config(self._config)
        self.accept()

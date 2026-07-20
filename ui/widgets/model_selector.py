from PyQt6 import QtCore, QtGui, QtWidgets

from core.client_factory import list_models, providers
from core.config import (
    get_api_key,
    get_model,
    get_provider,
    save_config,
    set_api_key,
    set_model,
    set_provider,
)
from ui.theme import ACCENT_PRESETS, Theme


class ModelSelector(QtWidgets.QWidget):
    """Two dropdowns (provider + model), persisted to config.

    Cloud providers show an inline '+ Add key' affordance when no API key
    is configured (and the env-var fallback isn't set either).
    """

    theme_changed = QtCore.pyqtSignal(object)
    settings_requested = QtCore.pyqtSignal()

    def __init__(self, theme: Theme, config: dict):
        super().__init__()
        self._t = theme
        self.config = config
        self.setObjectName("topbar")
        self.setFixedHeight(48)
        self._dots: list[_ColorDot] = []
        self._build()

    def _build(self):
        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(20, 0, 16, 0)
        layout.setSpacing(8)

        # Provider dropdown
        self.provider_combo = QtWidgets.QComboBox()
        self.provider_combo.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
        self.provider_combo.addItems(list(providers()))
        layout.addWidget(self.provider_combo)

        # Model dropdown
        self.model_combo = QtWidgets.QComboBox()
        self.model_combo.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
        self.model_combo.setMinimumWidth(180)
        layout.addWidget(self.model_combo)

        # Add-key affordance (only visible when cloud provider lacks key)
        self.add_key_btn = QtWidgets.QPushButton("+ Add key")
        self.add_key_btn.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
        self.add_key_btn.setToolTip("Set the API key for this provider")
        self.add_key_btn.clicked.connect(self._add_key)
        layout.addWidget(self.add_key_btn)

        layout.addStretch()

        # Dark / light toggle
        self.mode_btn = QtWidgets.QPushButton()
        self.mode_btn.setFixedSize(28, 28)
        self.mode_btn.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
        self.mode_btn.setToolTip("Toggle theme")
        self.mode_btn.clicked.connect(self._toggle_dark)
        layout.addWidget(self.mode_btn)

        spacer = QtWidgets.QSpacerItem(
            10, 0,
            QtWidgets.QSizePolicy.Policy.Fixed, QtWidgets.QSizePolicy.Policy.Minimum,
        )
        layout.addSpacer(spacer)

        # Settings gear button
        self.settings_btn = QtWidgets.QPushButton("\u2699")  # ⚙
        self.settings_btn.setFixedSize(28, 28)
        self.settings_btn.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
        self.settings_btn.setToolTip("Settings")
        self.settings_btn.clicked.connect(self.settings_requested.emit)
        layout.addWidget(self.settings_btn)

        # Color dots
        dots_container = QtWidgets.QWidget()
        self.dots_layout = QtWidgets.QHBoxLayout(dots_container)
        self.dots_layout.setContentsMargins(0, 0, 0, 0)
        self.dots_layout.setSpacing(8)
        for preset in ACCENT_PRESETS.values():
            dot = _ColorDot(preset, self._t)
            dot.selected.connect(self._on_accent_selected)
            self._dots.append(dot)
            self.dots_layout.addWidget(dot)
        layout.addWidget(dots_container)

        self.provider_combo.currentTextChanged.connect(self._on_provider_changed)
        self.model_combo.currentTextChanged.connect(self._on_model_changed)

        self.apply_theme(self._t)

    # -- theming --
    def apply_theme(self, theme: Theme):
        self._t = theme
        self.setStyleSheet(self._t.topbar_css())
        self.provider_combo.setStyleSheet(self._t.dropdown_css())
        self.model_combo.setStyleSheet(self._t.dropdown_css())
        # Add-key button styled as a subtle ghost button.
        self.add_key_btn.setStyleSheet(self._t.ghost_btn_css())
        self.settings_btn.setStyleSheet(self._t.icon_btn_css())
        self.mode_btn.setStyleSheet(self._t.icon_btn_css())
        self.mode_btn.setText("\u263e" if self._t.dark else "\u2600")

        for dot in self._dots:
            dot.apply_theme(self._t)
            dot.set_active(dot._preset.name.lower() == self._t.accent.name.lower())

    # -- public API --
    def initialize_from_config(self):
        provider = get_provider(self.config)
        idx = self.provider_combo.findText(provider)
        if idx < 0:
            idx = 0
            set_provider(self.config, self.provider_combo.itemText(0))
        self.provider_combo.blockSignals(True)
        self.provider_combo.setCurrentIndex(idx)
        self.provider_combo.blockSignals(False)
        self._refresh_provider_state(initial=True)

    def current_provider(self) -> str:
        return self.provider_combo.currentText().strip() or "ollama"

    def current_model(self) -> str:
        text = self.model_combo.currentText().strip()
        return text or "llama3"

    # -- internals --
    def _on_provider_changed(self, provider: str):
        if not provider:
            return
        set_provider(self.config, provider)
        self._refresh_provider_state(initial=False)

    def _refresh_provider_state(self, initial: bool):
        provider = self.current_provider()
        needs_key = provider in ("openai", "anthropic")
        has_key = bool(get_api_key(self.config, provider))
        self.add_key_btn.setVisible(needs_key and not has_key)
        self._load_models(initial=initial)

    def _load_models(self, initial: bool):
        provider = self.current_provider()
        models = list_models(provider, self.config)
        preferred = get_model(self.config, provider)

        self.model_combo.blockSignals(True)
        self.model_combo.clear()
        self.model_combo.addItems(models)

        if preferred and preferred in models:
            self.model_combo.setCurrentText(preferred)
        elif models:
            self.model_combo.setCurrentIndex(0)
            if not initial:
                set_model(self.config, provider, models[0])

        self.model_combo.blockSignals(False)

    def _on_model_changed(self, model: str):
        if not model:
            return
        set_model(self.config, self.current_provider(), model)
        save_config(self.config)

    def _add_key(self):
        provider = self.current_provider()
        text, ok = QtWidgets.QInputDialog.getText(
            self,
            f"{provider} API key",
            f"Paste your {provider} API key:",
            echo=QtWidgets.QLineEdit.EchoMode.Password,
        )
        if not ok or not text.strip():
            return
        set_api_key(self.config, provider, text.strip())
        save_config(self.config)
        self.add_key_btn.hide()
        self._load_models(initial=False)

    def _toggle_dark(self):
        self.theme_changed.emit(Theme(dark=not self._t.dark, accent=self._t.accent))

    def _on_accent_selected(self, preset: "AccentPreset"):
        self.theme_changed.emit(Theme(dark=self._t.dark, accent=preset))


class _ColorDot(QtWidgets.QAbstractButton):
    selected = QtCore.pyqtSignal(object)

    def __init__(self, preset, theme: Theme):
        super().__init__()
        self._preset = preset
        self._t = theme
        self._active = False
        self.setFixedSize(20, 20)
        self.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
        self.setToolTip(preset.name)
        self.clicked.connect(lambda: self.selected.emit(self._preset))

    def set_active(self, active: bool):
        self._active = active
        self.update()

    def apply_theme(self, theme: Theme):
        self._t = theme
        self.update()

    def paintEvent(self, event):
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)

        if self._active:
            p.setPen(QtGui.QPen(QtGui.QColor(self._t.text_main), 1.5))
            p.setBrush(QtCore.Qt.BrushStyle.NoBrush)
            p.drawEllipse(1, 1, 18, 18)
        else:
            p.setPen(QtGui.QPen(QtGui.QColor(self._t.border_main), 1))
            p.setBrush(QtCore.Qt.BrushStyle.NoBrush)
            p.drawEllipse(1, 1, 18, 18)

        p.setPen(QtCore.Qt.PenStyle.NoPen)
        p.setBrush(QtGui.QColor(self._preset.base))
        p.drawEllipse(5, 5, 10, 10)

"""
theme.py — Central design token system for Arca.

Usage:
    widget.setStyleSheet(t.dropdown_css())

Tokens are intentionally few. Change one → entire UI updates.
Light and dark variants are pure swaps; accent is a preset.
"""

from dataclasses import dataclass, field
from typing import NamedTuple


class AccentPreset(NamedTuple):
    name: str   # display label
    base: str   # primary accent
    tint: str   # hover/contrast variant
    soft: str   # ~15% alpha tint for active backgrounds (8-digit hex)


ACCENT_PRESETS: dict[str, AccentPreset] = {
    "graphite": AccentPreset("Graphite", "#64748b", "#94a3b8", "#64748b26"),
    "mint":     AccentPreset("Mint",     "#10b981", "#34d399", "#10b98126"),
    "azure":    AccentPreset("Azure",    "#3b82f6", "#60a5fa", "#3b82f626"),
    "amethyst": AccentPreset("Amethyst", "#8b5cf6", "#a78bfa", "#8b5cf626"),
    "amber":    AccentPreset("Amber",    "#f59e0b", "#fbbf24", "#f59e0b26"),
}


@dataclass
class Theme:
    dark: bool = False
    accent: AccentPreset = field(default_factory=lambda: ACCENT_PRESETS["graphite"])

    # -- Typography --
    font_stack: str = "system-ui, -apple-system, 'Segoe UI', Inter, sans-serif"
    mono_stack: str = "ui-monospace, 'SF Mono', 'JetBrains Mono', Menlo, monospace"

    # -- Radii --
    radius_sm: int = 6
    radius_md: int = 10
    radius_lg: int = 14

    # -- Backgrounds --
    @property
    def bg_app(self) -> str:
        return "#0e0e10" if self.dark else "#ffffff"

    @property
    def bg_sidebar(self) -> str:
        return "#18181b" if self.dark else "#f9f9f9"

    @property
    def bg_surface(self) -> str:
        return "#1f1f22" if self.dark else "#ffffff"

    @property
    def bg_hover(self) -> str:
        return "#27272a" if self.dark else "#f4f4f5"

    @property
    def bg_active(self) -> str:
        # Soft tinted active-item background; falls back to a hover tone if no accent.
        return self.accent.soft

    # -- Text --
    @property
    def text_main(self) -> str:
        return "#fafafa" if self.dark else "#0f0f0f"

    @property
    def text_sub(self) -> str:
        return "#a1a1aa" if self.dark else "#525252"

    @property
    def text_quiet(self) -> str:
        return "#52525b" if self.dark else "#a3a3a3"

    # -- Borders --
    @property
    def border_main(self) -> str:
        return "#27272a" if self.dark else "#e5e5e5"

    @property
    def border_soft(self) -> str:
        return "#1f1f22" if self.dark else "#f4f4f5"

    # ------------------------------------------------------------------------
    # CSS helpers — every widget should compose its style from these.
    # ------------------------------------------------------------------------

    def main_window_css(self) -> str:
        return f"QMainWindow {{ background: {self.bg_app}; }}"

    def scrollbar_css(self) -> str:
        return f"""
            QScrollBar:vertical {{
                background: transparent;
                width: 8px;
                margin: 0;
            }}
            QScrollBar::handle:vertical {{
                background: {self.border_main};
                border-radius: 4px;
                min-height: 24px;
                margin: 2px;
            }}
            QScrollBar::handle:vertical:hover {{
                background: {self.text_quiet};
            }}
            QScrollBar::add-line:vertical,
            QScrollBar::sub-line:vertical {{
                height: 0;
            }}
            QScrollBar::add-page:vertical,
            QScrollBar::sub-page:vertical {{
                background: transparent;
            }}
        """

    def sidebar_css(self) -> str:
        return f"""
            QWidget#sidebarRoot {{
                background: {self.bg_sidebar};
                border-right: 1px solid {self.border_soft};
            }}
        """

    def empty_state_css(self) -> str:
        return f"""
            QLabel#emptyTitle {{
                color: {self.text_main};
                font-family: {self.font_stack};
                font-size: 30px;
                font-weight: 600;
                letter-spacing: -0.5px;
                background: transparent;
            }}
            QLabel#emptySub {{
                color: {self.text_sub};
                font-family: {self.font_stack};
                font-size: 14px;
                background: transparent;
            }}
        """

    def wordmark_css(self) -> str:
        return f"""
            QLabel {{
                color: {self.text_main};
                font-family: {self.font_stack};
                font-size: 15px;
                font-weight: 600;
                letter-spacing: -0.2px;
                background: transparent;
            }}
        """

    def section_header_css(self) -> str:
        return f"""
            QLabel {{
                color: {self.text_quiet};
                font-family: {self.font_stack};
                font-size: 11px;
                font-weight: 600;
                background: transparent;
                padding: 14px 12px 4px 12px;
            }}
        """

    def ghost_btn_css(self) -> str:
        return f"""
            QPushButton {{
                background: transparent;
                color: {self.text_sub};
                border: none;
                border-radius: 6px;
                padding: 8px 12px;
                font-family: {self.font_stack};
                font-size: 13px;
                text-align: left;
            }}
            QPushButton:hover {{
                background: {self.bg_hover};
                color: {self.text_main};
            }}
        """

    def icon_btn_css(self) -> str:
        return f"""
            QPushButton {{
                background: transparent;
                color: {self.text_sub};
                border: none;
                border-radius: {self.radius_sm}px;
                font-family: {self.font_stack};
                font-size: 14px;
                padding: 0;
            }}
            QPushButton:hover {{
                background: {self.bg_hover};
                color: {self.text_main};
            }}
        """

    def topbar_css(self) -> str:
        return f"""
            QWidget#topbar {{
                background: {self.bg_app};
                border-bottom: 1px solid {self.border_soft};
            }}
        """

    def dropdown_css(self) -> str:
        return f"""
            QComboBox {{
                background: transparent;
                color: {self.text_main};
                border: 1px solid transparent;
                border-radius: {self.radius_sm}px;
                padding: 5px 10px;
                font-family: {self.font_stack};
                font-size: 13px;
                min-width: 160px;
            }}
            QComboBox:hover {{
                background: {self.bg_hover};
            }}
            QComboBox QAbstractItemView {{
                background: {self.bg_surface};
                color: {self.text_main};
                border: 1px solid {self.border_main};
                selection-background-color: {self.bg_active};
                outline: none;
                padding: 4px;
            }}
        """

    def chat_scroll_css(self) -> str:
        return f"""
            QScrollArea {{
                background: {self.bg_app};
                border: none;
            }}
        """

    def message_text_css(self, role: str) -> str:
        align = "right" if role == "user" else "left"
        return f"""
            QLabel {{
                background: transparent;
                color: {self.text_main};
                font-family: {self.font_stack};
                font-size: 14.5px;
                line-height: 1.6;
                text-align: {align};
            }}
        """

    def code_block_css(self) -> str:
        return f"""
            QWidget#codeBlock {{
                background: {self.bg_sidebar};
                border: 1px solid {self.border_main};
                border-radius: {self.radius_sm}px;
            }}
            QLabel#codeLang {{
                color: {self.text_quiet};
                font-family: {self.font_stack};
                font-size: 11px;
                font-weight: 600;
                letter-spacing: 0.4px;
                background: transparent;
                text-transform: uppercase;
            }}
            QPushButton#codeCopy {{
                background: transparent;
                color: {self.text_quiet};
                border: none;
                border-radius: 3px;
                padding: 2px 8px;
                font-family: {self.font_stack};
                font-size: 11px;
            }}
            QPushButton#codeCopy:hover {{
                background: {self.bg_hover};
                color: {self.text_sub};
            }}
            QPlainTextEdit {{
                background: transparent;
                color: {self.text_main};
                border: none;
                font-family: {self.mono_stack};
                font-size: 13px;
                padding: 4px 12px 12px 12px;
                selection-background-color: {self.bg_active};
                selection-color: {self.text_main};
            }}
        """

    def composer_css(self) -> str:
        return f"""
            QFrame#composer {{
                background: {self.bg_surface};
                border: 1px solid {self.border_main};
                border-radius: {self.radius_md}px;
            }}
            QTextEdit {{
                background: transparent;
                border: none;
                color: {self.text_main};
                font-family: {self.font_stack};
                font-size: 14px;
                line-height: 1.5;
                padding: 8px 4px;
                selection-background-color: {self.bg_active};
                selection-color: {self.text_main};
            }}
        """

    def composer_focused_css(self) -> str:
        return f"""
            QFrame#composer {{
                background: {self.bg_surface};
                border: 1px solid {self.text_quiet};
                border-radius: {self.radius_md}px;
            }}
            QTextEdit {{
                background: transparent;
                border: none;
                color: {self.text_main};
                font-family: {self.font_stack};
                font-size: 14px;
                line-height: 1.5;
                padding: 8px 4px;
                selection-background-color: {self.bg_active};
                selection-color: {self.text_main};
            }}
        """

    def send_btn_css(self) -> str:
        return f"""
            QPushButton {{
                background: {self.accent.base};
                color: #ffffff;
                border: none;
                border-radius: {self.radius_sm}px;
                font-family: {self.font_stack};
                font-size: 15px;
                font-weight: 600;
            }}
            QPushButton:hover {{
                background: {self.accent.tint};
            }}
            QPushButton:disabled {{
                background: {self.bg_hover};
                color: {self.text_quiet};
            }}
        """

    def chip_css(self) -> str:
        return f"""
            QPushButton {{
                background: transparent;
                color: {self.text_sub};
                border: 1px solid {self.border_main};
                border-radius: 14px;
                padding: 8px 16px;
                font-family: {self.font_stack};
                font-size: 13px;
            }}
            QPushButton:hover {{
                background: {self.bg_hover};
                color: {self.text_main};
                border-color: {self.text_quiet};
            }}
        """

    def regenerate_btn_css(self) -> str:
        return f"""
            QPushButton {{
                background: transparent;
                color: {self.text_quiet};
                border: 1px solid transparent;
                border-radius: {self.radius_sm}px;
                padding: 3px 10px;
                font-family: {self.font_stack};
                font-size: 11px;
                font-weight: 500;
            }}
            QPushButton:hover {{
                color: {self.accent.base};
                background: {self.accent.soft};
                border-color: {self.accent.soft};
            }}
        """

    def menu_css(self) -> str:
        return f"""
            QMenu {{
                background: {self.bg_surface};
                color: {self.text_main};
                border: 1px solid {self.border_main};
                border-radius: {self.radius_sm}px;
                padding: 4px;
            }}
            QMenu::item {{
                padding: 7px 18px;
                border-radius: 4px;
                font-family: {self.font_stack};
                font-size: 13px;
            }}
            QMenu::item:selected {{
                background: {self.bg_hover};
                color: {self.text_main};
            }}
            QMenu::separator {{
                height: 1px;
                background: {self.border_main};
                margin: 4px 8px;
            }}
        """

    def status_bar_css(self) -> str:
        return f"""
            QStatusBar {{
                background: {self.bg_app};
                border-top: 1px solid {self.border_soft};
                color: {self.text_quiet};
                font-family: {self.font_stack};
                font-size: 11px;
                padding: 2px 12px;
            }}
            QStatusBar::item {{
                border: none;
            }}
            QLabel#statusModel {{
                color: {self.text_sub};
                font-family: {self.font_stack};
                font-size: 11px;
                background: transparent;
            }}
            QLabel#statusIndicator {{
                color: {self.accent.base};
                font-family: {self.font_stack};
                font-size: 11px;
                background: transparent;
            }}
        """

    def stop_btn_css(self) -> str:
        return f"""
            QPushButton {{
                background: transparent;
                color: {self.text_sub};
                border: 1px solid {self.border_main};
                border-radius: {self.radius_sm}px;
                padding: 6px 14px;
                font-family: {self.font_stack};
                font-size: 12px;
                font-weight: 500;
            }}
            QPushButton:hover {{
                background: #ef444426;
                color: #ef4444;
                border-color: #ef4444;
            }}
        """

    def dialog_css(self) -> str:
        return f"""
            QDialog {{
                background: {self.bg_app};
                color: {self.text_main};
                font-family: {self.font_stack};
            }}
            QLabel#dialogTitle {{
                color: {self.text_main};
                font-size: 16px;
                font-weight: 600;
                font-family: {self.font_stack};
                background: transparent;
            }}
            QLabel#dialogSection {{
                color: {self.text_quiet};
                font-size: 11px;
                font-weight: 600;
                text-transform: uppercase;
                letter-spacing: 0.5px;
                font-family: {self.font_stack};
                background: transparent;
                padding: 12px 0 4px 0;
            }}
            QLabel#dialogField {{
                color: {self.text_sub};
                font-size: 13px;
                font-family: {self.font_stack};
                background: transparent;
            }}
            QLineEdit {{
                background: {self.bg_surface};
                color: {self.text_main};
                border: 1px solid {self.border_main};
                border-radius: {self.radius_sm}px;
                padding: 7px 10px;
                font-family: {self.font_stack};
                font-size: 13px;
                selection-background-color: {self.bg_active};
            }}
            QLineEdit:focus {{
                border-color: {self.accent.base};
            }}
            QDoubleSpinBox, QSpinBox {{
                background: {self.bg_surface};
                color: {self.text_main};
                border: 1px solid {self.border_main};
                border-radius: {self.radius_sm}px;
                padding: 5px 8px;
                font-family: {self.font_stack};
                font-size: 13px;
            }}
            QDoubleSpinBox:focus, QSpinBox:focus {{
                border-color: {self.accent.base};
            }}
            QSlider::groove:horizontal {{
                background: {self.border_main};
                height: 4px;
                border-radius: 2px;
            }}
            QSlider::handle:horizontal {{
                background: {self.accent.base};
                width: 16px;
                height: 16px;
                margin: -6px 0;
                border-radius: 8px;
            }}
            QSlider::handle:horizontal:hover {{
                background: {self.accent.tint};
            }}
            QSlider::sub-page:horizontal {{
                background: {self.accent.base};
                border-radius: 2px;
            }}
            QPushButton#dialogSave {{
                background: {self.accent.base};
                color: #ffffff;
                border: none;
                border-radius: {self.radius_sm}px;
                padding: 8px 24px;
                font-family: {self.font_stack};
                font-size: 13px;
                font-weight: 600;
            }}
            QPushButton#dialogSave:hover {{
                background: {self.accent.tint};
            }}
            QPushButton#dialogCancel {{
                background: transparent;
                color: {self.text_sub};
                border: 1px solid {self.border_main};
                border-radius: {self.radius_sm}px;
                padding: 8px 24px;
                font-family: {self.font_stack};
                font-size: 13px;
            }}
            QPushButton#dialogCancel:hover {{
                background: {self.bg_hover};
                color: {self.text_main};
            }}
        """

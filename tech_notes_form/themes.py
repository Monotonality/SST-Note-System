"""Theme palettes and Qt stylesheet generation.

Themes: Dark, Light, System (follows the OS), Ocean, Warm, Super Dark, and
Forest. "System" resolves to either the Dark or Light palette based on the
current Windows app theme (falls back to Light elsewhere).
"""

from __future__ import annotations

from dataclasses import dataclass

THEME_DARK = "dark"
THEME_LIGHT = "light"
THEME_SYSTEM = "system"
THEME_OCEAN = "ocean"
THEME_WARM = "warm"
THEME_SUPER_DARK = "super_dark"
THEME_FOREST = "forest"

THEME_CHOICES = [
    (THEME_DARK, "Dark"),
    (THEME_LIGHT, "Light"),
    (THEME_SYSTEM, "System"),
    (THEME_OCEAN, "Ocean"),
    (THEME_WARM, "Warm"),
    (THEME_SUPER_DARK, "Super Dark"),
    (THEME_FOREST, "Forest"),
]


@dataclass(frozen=True)
class Palette:
    window: str
    panel: str
    input_bg: str
    text: str
    muted: str
    border: str
    accent: str
    accent_text: str
    accent_hover: str
    danger: str


_PALETTES = {
    THEME_DARK: Palette(
        window="#1e1e1e", panel="#252526", input_bg="#2d2d30", text="#e6e6e6",
        muted="#9a9a9a", border="#3c3c3c", accent="#0e639c", accent_text="#ffffff",
        accent_hover="#1177bb", danger="#c94f4f",
    ),
    THEME_LIGHT: Palette(
        window="#f3f3f3", panel="#ffffff", input_bg="#ffffff", text="#1f1f1f",
        muted="#6b6b6b", border="#d0d0d0", accent="#0a66c2", accent_text="#ffffff",
        accent_hover="#0b76de", danger="#c0392b",
    ),
    THEME_OCEAN: Palette(
        window="#0b2530", panel="#103442", input_bg="#0f3a48", text="#dcf2f7",
        muted="#84b3c0", border="#1b4b5a", accent="#1ca3c4", accent_text="#012027",
        accent_hover="#27bcdf", danger="#e06b6b",
    ),
    THEME_WARM: Palette(
        window="#f6ece0", panel="#fff8ef", input_bg="#fffaf3", text="#3b2f25",
        muted="#8a7866", border="#e3d4c0", accent="#c2722e", accent_text="#ffffff",
        accent_hover="#d6822f", danger="#b23a2e",
    ),
    THEME_SUPER_DARK: Palette(
        window="#060608", panel="#0c0c10", input_bg="#121218", text="#a8d8ff",
        muted="#6a9ec4", border="#1e2a38", accent="#3d9ee5", accent_text="#060608",
        accent_hover="#5cb0f0", danger="#ff7070",
    ),
    THEME_FOREST: Palette(
        window="#0f1a14", panel="#142019", input_bg="#1a2820", text="#d4e8dc",
        muted="#7a9a88", border="#2a4034", accent="#3d9a6a", accent_text="#ffffff",
        accent_hover="#4db87d", danger="#d96a5c",
    ),
}


def detect_system_dark() -> bool:
    """Return True if the OS reports a dark app theme (Windows only)."""
    try:
        import winreg

        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize",
        )
        value, _ = winreg.QueryValueEx(key, "AppsUseLightTheme")
        return value == 0
    except Exception:
        return False


def resolve_palette(theme: str) -> Palette:
    if theme == THEME_SYSTEM:
        return _PALETTES[THEME_DARK] if detect_system_dark() else _PALETTES[THEME_LIGHT]
    return _PALETTES.get(theme, _PALETTES[THEME_LIGHT])


def build_stylesheet(theme: str, compact: bool = False) -> str:
    p = resolve_palette(theme)
    base_font = 12 if compact else 14
    title_font = 13 if compact else 15
    field_font = 13 if compact else 15
    field_pad = "3px 6px" if compact else "6px 8px"
    btn_pad = "4px 9px" if compact else "7px 14px"
    return f"""
    QWidget {{
        background-color: {p.window};
        color: {p.text};
        font-size: {base_font}px;
    }}
    QMainWindow, QDialog {{ background-color: {p.window}; }}

    #VersionLabel {{
        color: {p.muted};
        font-weight: 600;
        padding-left: 8px;
        padding-right: 10px;
    }}

    QPushButton#Rail {{
        background-color: {p.panel};
        color: {p.text};
        border: 1px solid {p.border};
        border-radius: 6px;
        font-weight: 700;
        padding: 0;
    }}
    QPushButton#Rail:hover {{
        background-color: {p.accent};
        color: {p.accent_text};
        border-color: {p.accent};
    }}

    #Panel {{
        background-color: {p.panel};
        border: 1px solid {p.border};
        border-radius: 8px;
    }}
    #PanelTitle {{ font-size: {title_font}px; font-weight: 600; }}
    #StatusLabel {{ color: {p.muted}; }}
    #EmptyState {{ color: {p.muted}; font-style: italic; }}

    #FieldCard {{
        background-color: {p.window};
        border: 1px solid {p.border};
        border-radius: 8px;
    }}
    QLineEdit#FieldLabel {{
        font-size: {field_font}px;
        font-weight: 600;
        background-color: {p.input_bg};
    }}

    QLabel {{ background: transparent; }}

    QPlainTextEdit, QTextEdit, QLineEdit, QComboBox, QListWidget {{
        background-color: {p.input_bg};
        color: {p.text};
        border: 1px solid {p.border};
        border-radius: 6px;
        padding: {field_pad};
        selection-background-color: {p.accent};
        selection-color: {p.accent_text};
    }}
    QPlainTextEdit:focus, QTextEdit:focus, QLineEdit:focus, QComboBox:focus {{
        border: 1px solid {p.accent};
    }}

    QPushButton {{
        background-color: {p.panel};
        color: {p.text};
        border: 1px solid {p.border};
        border-radius: 6px;
        padding: {btn_pad};
    }}
    QPushButton:hover {{ border: 1px solid {p.accent}; }}
    QPushButton:pressed {{ background-color: {p.input_bg}; }}

    QPushButton#Primary {{
        background-color: {p.accent};
        color: {p.accent_text};
        border: 1px solid {p.accent};
        font-weight: 600;
    }}
    QPushButton#Primary:hover {{ background-color: {p.accent_hover}; border-color: {p.accent_hover}; }}

    QPushButton#Remove, QPushButton#IconButton {{
        background-color: transparent;
        color: {p.muted};
        border: 1px solid {p.border};
        border-radius: 6px;
        padding: 2px;
        font-weight: 700;
        min-width: 28px;
        max-width: 28px;
        min-height: 28px;
        max-height: 28px;
    }}
    QPushButton#Remove:hover {{ color: {p.accent_text}; background-color: {p.danger}; border-color: {p.danger}; }}
    QPushButton#IconButton:hover {{ color: {p.accent_text}; background-color: {p.accent}; border-color: {p.accent}; }}

    QComboBox::drop-down {{ border: none; width: 22px; }}
    QComboBox QAbstractItemView {{
        background-color: {p.panel};
        color: {p.text};
        selection-background-color: {p.accent};
        selection-color: {p.accent_text};
        border: 1px solid {p.border};
    }}

    QCheckBox {{ background: transparent; spacing: 8px; }}
    QCheckBox::indicator {{
        width: 16px; height: 16px;
        border: 1px solid {p.border};
        border-radius: 4px;
        background: {p.input_bg};
    }}
    QCheckBox::indicator:checked {{ background: {p.accent}; border-color: {p.accent}; }}

    QMenuBar {{ background-color: {p.panel}; color: {p.text}; }}
    QMenuBar::item:selected {{ background-color: {p.accent}; color: {p.accent_text}; }}
    QMenu {{ background-color: {p.panel}; color: {p.text}; border: 1px solid {p.border}; padding: 4px; }}
    QMenu::item {{ padding: 5px 36px 5px 16px; }}
    QMenu::item:selected {{ background-color: {p.accent}; color: {p.accent_text}; }}
    QMenu::separator {{ height: 1px; background: {p.border}; margin: 4px 8px; }}

    QScrollArea {{ border: none; background: transparent; }}
    QScrollBar:vertical {{ background: transparent; width: 12px; margin: 0; }}
    QScrollBar::handle:vertical {{ background: {p.border}; border-radius: 6px; min-height: 30px; }}
    QScrollBar::handle:vertical:hover {{ background: {p.accent}; }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}

    QSplitter::handle {{ background: {p.border}; }}
    QSplitter::handle:horizontal {{ width: 4px; }}

    QToolTip {{ background-color: {p.panel}; color: {p.text}; border: 1px solid {p.border}; }}
    """

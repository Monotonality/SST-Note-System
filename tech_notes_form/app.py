"""Application bootstrap: single-instance guard, tray icon, entry point."""

from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import QSharedMemory, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QMenu,
    QMessageBox,
    QSystemTrayIcon,
)

from . import APP_NAME, ORG_NAME
from .main_window import MainWindow

LOGO_FILENAME = "AdamNote Logo.svg"


def _resource_path(name: str) -> Path:
    """Locate a bundled resource both when run from source and when frozen."""
    base = getattr(sys, "_MEIPASS", None)
    if base:
        candidate = Path(base) / name
        if candidate.exists():
            return candidate
    # Project root (one level above this package) when running from source.
    return Path(__file__).resolve().parent.parent / name


def app_icon() -> QIcon:
    """Return the AdamNote logo icon, falling back to a drawn icon if missing."""
    logo = _resource_path(LOGO_FILENAME)
    if logo.exists():
        icon = QIcon(str(logo))
        if not icon.isNull():
            return icon
    return _make_icon()


def _make_icon() -> QIcon:
    """Draw a simple app icon at runtime (fallback if the logo is unavailable)."""
    pixmap = QPixmap(256, 256)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)

    painter.setBrush(QColor("#0e639c"))
    painter.setPen(Qt.NoPen)
    painter.drawRoundedRect(16, 16, 224, 224, 40, 40)

    painter.setBrush(QColor("#ffffff"))
    painter.drawRoundedRect(60, 70, 136, 18, 6, 6)
    painter.drawRoundedRect(60, 118, 136, 18, 6, 6)
    painter.drawRoundedRect(60, 166, 90, 18, 6, 6)

    painter.setBrush(QColor("#9be3ff"))
    painter.drawRoundedRect(36, 70, 14, 18, 4, 4)
    painter.drawRoundedRect(36, 118, 14, 18, 4, 4)
    painter.drawRoundedRect(36, 166, 14, 18, 4, 4)

    painter.end()
    return QIcon(pixmap)


def _create_tray(window: MainWindow, icon: QIcon, app: QApplication):
    if not QSystemTrayIcon.isSystemTrayAvailable():
        return None

    tray = QSystemTrayIcon(icon, window)
    tray.setToolTip(APP_NAME)

    menu = QMenu()
    show_action = menu.addAction("Show / Hide")
    show_action.triggered.connect(lambda: _toggle_window(window))
    menu.addSeparator()
    quit_action = menu.addAction("Quit")
    quit_action.triggered.connect(app.quit)
    tray.setContextMenu(menu)

    def _on_activated(reason):
        if reason == QSystemTrayIcon.Trigger:
            _toggle_window(window)

    tray.activated.connect(_on_activated)
    tray.show()
    return tray


def _toggle_window(window: MainWindow):
    if window.isVisible() and not window.isMinimized():
        window.hide()
    else:
        window.showNormal()
        window.raise_()
        window.activateWindow()


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setOrganizationName(ORG_NAME)
    app.setApplicationDisplayName(APP_NAME)
    # Keep running in the tray when the window is closed via the tray quit only.
    app.setQuitOnLastWindowClosed(True)

    # Single-instance guard via shared memory.
    shared = QSharedMemory(f"{ORG_NAME}-single-instance")
    if not shared.create(1):
        QMessageBox.information(
            None, APP_NAME, f"{APP_NAME} is already running."
        )
        return 0

    icon = app_icon()
    app.setWindowIcon(icon)

    window = MainWindow()
    window.setWindowIcon(icon)
    window.show()

    # Tray is optional; the app works fine without it.
    tray = _create_tray(window, icon, app)
    if tray is not None:
        window._tray = tray  # keep a reference alive

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())

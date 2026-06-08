"""Build a standalone Windows executable with PyInstaller.

Usage:
    pip install pyinstaller
    python build_exe.py

The resulting double-clickable app is written to ``dist/AdamNote/``
(or ``dist/AdamNote.exe`` in onefile mode).
"""

import PyInstaller.__main__

PyInstaller.__main__.run(
    [
        "run.py",
        "--name=AdamNote",
        "--windowed",        # no console window
        "--noconfirm",
        "--clean",
        # Bundle the logo so it can be used as the app icon at runtime.
        # (On Windows PyInstaller uses ';' as the add-data separator.)
        "--add-data=AdamNote Logo.svg;.",
        # Use the logo as the executable's own icon (Windows accepts .ico best;
        # PyInstaller will convert where possible).
        "--icon=AdamNote Logo.svg",
        # Use --onefile for a single .exe; the default one-folder build starts
        # faster. Uncomment the next line for a single-file distributable.
        # "--onefile",
    ]
)

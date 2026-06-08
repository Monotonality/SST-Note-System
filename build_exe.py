"""Build a standalone single-file Windows executable with PyInstaller.

Usage:
    pip install pyinstaller PySide6
    python build_exe.py

The result is a single double-clickable file: ``dist/AdamNote.exe``.

PyInstaller's ``--icon`` needs a Windows ``.ico`` (an SVG is not accepted), so a
pre-made ``AdamNote Logo.ico`` is used for the executable's icon. The SVG is
also bundled so the app can use it as the in-app window/tray icon at runtime.
"""

from __future__ import annotations

import os

SVG_LOGO = "AdamNote Logo.svg"
ICO_LOGO = "AdamNote Logo.ico"


def main() -> None:
    import PyInstaller.__main__

    # Regenerate a crisp, tightly-cropped multi-size .ico from the SVG so the
    # taskbar icon looks large and sharp. Falls back to any existing .ico if the
    # optional deps (Pillow) aren't installed.
    if os.path.exists(SVG_LOGO):
        try:
            import make_icon

            make_icon.generate(SVG_LOGO, ICO_LOGO)
        except Exception as exc:
            print(f"[icon] Could not regenerate {ICO_LOGO} ({exc}); using existing file if present.")

    args = [
        "run.py",
        "--name=AdamNote",
        "--windowed",        # no console window
        "--onefile",         # single self-contained dist/AdamNote.exe
        "--noconfirm",
        "--clean",
    ]

    # Bundle the logo files so the app can use them as the in-app icon at runtime
    # (the .ico is preferred because it's tightly cropped and multi-size).
    # (On Windows PyInstaller uses ';' as the add-data separator.)
    if os.path.exists(ICO_LOGO):
        args.append(f"--add-data={ICO_LOGO};.")
    if os.path.exists(SVG_LOGO):
        args.append(f"--add-data={SVG_LOGO};.")

    # Use the .ico for the executable's own (taskbar/Explorer) icon.
    if os.path.exists(ICO_LOGO):
        args.append(f"--icon={ICO_LOGO}")
    else:
        print(f"[build] {ICO_LOGO} not found - building without a custom .exe icon.")

    print("[build] Running PyInstaller with:")
    for a in args:
        print(f"        {a}")
    PyInstaller.__main__.run(args)
    print("[build] Done. See dist/AdamNote.exe")


if __name__ == "__main__":
    main()

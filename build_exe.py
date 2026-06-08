"""Build a standalone Windows executable with PyInstaller.

Usage:
    pip install pyinstaller PySide6 pillow
    python build_exe.py              # single-file exe (portable, slower startup)
    python build_exe.py --onedir     # folder build (faster startup)

Outputs:
    onefile (default): ``dist/AdamNote.exe``
    onedir:            ``dist/AdamNote/AdamNote.exe`` (+ DLLs alongside it)

PyInstaller's ``--icon`` needs a Windows ``.ico`` (an SVG is not accepted), so a
pre-made ``AdamNote Logo.ico`` is used for the executable's icon. The SVG is
also bundled so the app can use it as the in-app window/tray icon at runtime.
"""

from __future__ import annotations

import argparse
import os

SVG_LOGO = "AdamNote Logo.svg"
ICO_LOGO = "AdamNote Logo.ico"


def _ensure_icon() -> None:
    """Regenerate a crisp multi-size .ico from the SVG when possible."""
    if not os.path.exists(SVG_LOGO):
        return
    try:
        import make_icon

        make_icon.generate(SVG_LOGO, ICO_LOGO)
    except Exception as exc:
        print(f"[icon] Could not regenerate {ICO_LOGO} ({exc}); using existing file if present.")


def build(*, onedir: bool = False) -> None:
    """Run PyInstaller in one-file or one-folder mode."""
    import PyInstaller.__main__

    _ensure_icon()

    args = [
        "run.py",
        "--name=AdamNote",
        "--windowed",        # no console window
        "--noconfirm",
        "--clean",
    ]
    if not onedir:
        args.append("--onefile")

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

    mode = "onedir (folder)" if onedir else "onefile (single exe)"
    print(f"[build] Mode: {mode}")
    print("[build] Running PyInstaller with:")
    for a in args:
        print(f"        {a}")
    PyInstaller.__main__.run(args)

    if onedir:
        print("[build] Done. Run dist/AdamNote/AdamNote.exe")
        print("[build] Distribute the entire dist/AdamNote/ folder.")
    else:
        print("[build] Done. Run dist/AdamNote.exe")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build AdamNote as a Windows executable with PyInstaller.",
    )
    parser.add_argument(
        "--onedir",
        "--folder",
        action="store_true",
        help=(
            "Build a folder (dist/AdamNote/) instead of a single exe. "
            "Starts faster because nothing is unpacked to a temp folder on launch."
        ),
    )
    parser.add_argument(
        "--onefile",
        action="store_true",
        help="Build a single portable exe (default). Slower startup, easiest to distribute.",
    )
    opts = parser.parse_args()

    if opts.onedir and opts.onefile:
        parser.error("Choose one mode: --onedir or --onefile (not both).")

    build(onedir=opts.onedir)


if __name__ == "__main__":
    main()

"""Generate a crisp, multi-resolution Windows ``.ico`` from the SVG logo.

Why this exists: a taskbar icon looks "small" when the ``.ico`` either lacks
large sizes or the artwork has wide transparent margins. This script renders the
SVG at high resolution, trims the transparent border so the logo fills the
canvas, then writes a multi-size ICO (16-256 px) so Windows always has a sharp,
appropriately sized image.

Usage:
    pip install PySide6 pillow
    python make_icon.py
"""

from __future__ import annotations

import io
import sys

SVG_LOGO = "AdamNote Logo.svg"
ICO_LOGO = "AdamNote Logo.ico"
RENDER_PX = 1024          # high-res render before trimming
MARGIN_RATIO = 0.06       # small breathing room around the trimmed logo
ICO_SIZES = [(256, 256), (128, 128), (96, 96), (64, 64), (48, 48), (32, 32), (24, 24), (16, 16)]


def _render_svg_to_pil(svg_path: str, render_px: int):
    """Render the SVG (aspect-ratio preserved, centered) to a PIL RGBA image."""
    from PySide6.QtCore import Qt, QBuffer, QByteArray, QRectF
    from PySide6.QtGui import QGuiApplication, QImage, QPainter
    from PySide6.QtSvg import QSvgRenderer
    from PIL import Image

    _ = QGuiApplication.instance() or QGuiApplication(sys.argv[:1])

    renderer = QSvgRenderer(svg_path)
    if not renderer.isValid():
        raise SystemExit(f"Invalid or missing SVG: {svg_path}")

    image = QImage(render_px, render_px, QImage.Format_ARGB32)
    image.fill(Qt.transparent)

    painter = QPainter(image)
    # Preserve aspect ratio and center within the square canvas.
    default = renderer.defaultSize()
    if default.width() > 0 and default.height() > 0:
        scale = min(render_px / default.width(), render_px / default.height())
        tw, th = default.width() * scale, default.height() * scale
        target = QRectF((render_px - tw) / 2.0, (render_px - th) / 2.0, tw, th)
    else:
        target = QRectF(0, 0, render_px, render_px)
    renderer.render(painter, target)
    painter.end()

    # Convert QImage -> PIL via PNG bytes (robust; avoids stride pitfalls).
    ba = QByteArray()
    buf = QBuffer(ba)
    buf.open(QBuffer.WriteOnly)
    image.save(buf, "PNG")
    return Image.open(io.BytesIO(bytes(ba))).convert("RGBA")


def generate(svg_path: str = SVG_LOGO, ico_path: str = ICO_LOGO) -> str:
    """Build ``ico_path`` from ``svg_path`` and return the ICO path."""
    from PIL import Image

    pil = _render_svg_to_pil(svg_path, RENDER_PX)

    # Trim transparent borders so the logo fills the icon (this is what makes the
    # taskbar icon look bigger), then re-pad to a square with a small margin.
    bbox = pil.getbbox()
    if bbox:
        pil = pil.crop(bbox)
    w, h = pil.size
    side = max(w, h)
    margin = int(round(side * MARGIN_RATIO))
    canvas = side + 2 * margin
    square = Image.new("RGBA", (canvas, canvas), (0, 0, 0, 0))
    square.paste(pil, ((canvas - w) // 2, (canvas - h) // 2), pil)

    square.save(ico_path, format="ICO", sizes=ICO_SIZES)
    print(f"[icon] Wrote multi-size ICO ({', '.join(f'{s[0]}' for s in ICO_SIZES)} px) -> {ico_path}")
    return ico_path


if __name__ == "__main__":
    generate()

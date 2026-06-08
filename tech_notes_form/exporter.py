"""Format parsed fields back into clean plain text."""

from __future__ import annotations

from typing import List

from .parser import Field, MODE_LABEL_BLOCK, MODE_SAME_LINE

EXPORT_MODES = [
    (MODE_SAME_LINE, "Label: value (same line)"),
    (MODE_LABEL_BLOCK, "Label on one line, value on next"),
]


def _format_field(f: Field, default_mode: str) -> str:
    """Render a single field using its own mode, or *default_mode* as fallback."""
    label = f.label.strip()
    value = f.value.strip()
    if not label and not value:
        return ""

    mode = f.export_mode or default_mode
    if mode == MODE_LABEL_BLOCK:
        return f"{label}:\n{value}" if value else f"{label}:"
    return f"{label}: {value}".rstrip()


def format_output(fields: List[Field], mode: str = MODE_SAME_LINE,
                  blank_between: bool = False) -> str:
    """Render *fields* to plain text.

    Each field may override *mode* with its own ``export_mode`` so rows can mix
    same-line and label-block layouts. *mode* is the default for fields without
    an override.

    ``blank_between`` inserts an empty line between fields for readability.
    """
    blocks: List[str] = []
    for f in fields:
        block = _format_field(f, mode)
        if block:
            blocks.append(block)

    separator = "\n\n" if blank_between else "\n"
    return separator.join(blocks)

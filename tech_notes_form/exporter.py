"""Format parsed fields back into clean plain text."""

from __future__ import annotations

from typing import List

from .parser import Field

# Export mode identifiers.
MODE_SAME_LINE = "same_line"
MODE_LABEL_BLOCK = "label_block"

EXPORT_MODES = [
    (MODE_SAME_LINE, "Label: value (same line)"),
    (MODE_LABEL_BLOCK, "Label on one line, value on next"),
]


def format_output(fields: List[Field], mode: str = MODE_SAME_LINE,
                  blank_between: bool = False) -> str:
    """Render *fields* to plain text using the chosen *mode*.

    ``blank_between`` inserts an empty line between fields for readability.
    """
    blocks: List[str] = []
    for f in fields:
        label = f.label.strip()
        value = f.value.strip()
        if not label and not value:
            continue
        if mode == MODE_LABEL_BLOCK:
            blocks.append(f"{label}:\n{value}" if value else f"{label}:")
        else:
            blocks.append(f"{label}: {value}".rstrip())

    separator = "\n\n" if blank_between else "\n"
    return separator.join(blocks)

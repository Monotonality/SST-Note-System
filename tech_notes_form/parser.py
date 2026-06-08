"""Forgiving parser for messy plain-text ticket notes.

Supported layouts (mixable within a single paste):

1. Same-line ............ ``Client Name: John Doe``
2. Label block .......... a label line ending in ``:`` followed (after an
   optional blank line) by the value on the next line::

       TICKET ID:
       INC12345

The parser tolerates inconsistent spacing and casing, and treats orphan
lines (text without a colon that is not part of a recognised block) as a
continuation of the previous value.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List

# A line is treated as a "label line" when it has a colon and the text before
# the first colon is a plausible label (not empty, not absurdly long).
_LABEL_RE = re.compile(r"^\s*(?P<label>[^:]+?)\s*:\s*(?P<value>.*?)\s*$")

# Maximum length of a label before we stop treating the line as a field.
_MAX_LABEL_LEN = 60

# Per-field export layout (also used by the exporter and form rows).
MODE_SAME_LINE = "same_line"
MODE_LABEL_BLOCK = "label_block"


@dataclass
class Field:
    """A single parsed label/value pair."""

    label: str = ""
    value: str = ""
    # ``same_line`` -> ``Label: value``; ``label_block`` -> label line then value.
    # Empty string means "use the export panel's default format".
    export_mode: str = ""

    def normalised_label(self) -> str:
        return self.label.strip().lower()


def _is_label_line(line: str):
    """Return an ``(label, value)`` tuple if *line* looks like a field, else None."""
    m = _LABEL_RE.match(line)
    if not m:
        return None
    label = m.group("label").strip()
    value = m.group("value").strip()
    if not label or len(label) > _MAX_LABEL_LEN:
        return None
    # Guard against URLs like ``http://example.com`` being read as a field
    # named "http" with the value "//example.com".
    if value.startswith("//"):
        return None
    return label, value


def _collect_block_value(lines: List[str], start: int) -> tuple[str, int]:
    """Read a multi-line value starting at *start*.

    Consumes lines until the next recognised label line. Blank lines between
    value lines are preserved; trailing blanks are dropped. Returns
    ``(value, next_index)`` where *next_index* is the first unconsumed line.
    """
    parts: List[str] = []
    j = start
    n = len(lines)
    while j < n:
        line = lines[j]
        if line.strip() and _is_label_line(line) is not None:
            break
        if not line.strip():
            k = j + 1
            while k < n and not lines[k].strip():
                k += 1
            if k < n and _is_label_line(lines[k]) is not None:
                break
            if parts:
                parts.append("")
        else:
            parts.append(line.rstrip())
        j += 1
    while parts and not parts[-1]:
        parts.pop()
    return "\n".join(parts), j


def _append_continuation(field: Field, line: str) -> None:
    """Append an orphan line to *field*'s value, preserving line breaks."""
    extra = line.rstrip()
    if not extra:
        return
    if field.value:
        field.value = f"{field.value}\n{extra}"
    else:
        field.value = extra


def parse_notes(text: str) -> List[Field]:
    """Parse raw note *text* into a list of :class:`Field` objects."""
    if not text:
        return []

    lines = text.splitlines()
    fields: List[Field] = []
    i = 0
    n = len(lines)

    while i < n:
        raw = lines[i]
        if not raw.strip():
            i += 1
            continue

        parsed = _is_label_line(raw)
        if parsed is not None:
            label, value = parsed
            if value == "":
                # Label block: collect every following line until the next field.
                j = i + 1
                while j < n and not lines[j].strip():
                    j += 1
                if j < n and _is_label_line(lines[j]) is None:
                    block_value, j = _collect_block_value(lines, j)
                    fields.append(Field(
                        label=label,
                        value=block_value,
                        export_mode=MODE_LABEL_BLOCK,
                    ))
                    i = j
                    continue
                fields.append(Field(label=label, value="", export_mode=MODE_LABEL_BLOCK))
                i += 1
                continue

            fields.append(Field(
                label=label,
                value=value,
                export_mode=MODE_SAME_LINE,
            ))
            i += 1
            continue

        # Orphan line (no colon) -> continuation of the previous value.
        if fields:
            _append_continuation(fields[-1], raw)
        i += 1

    return fields


def merge_fields(existing: List[Field], incoming: List[Field]):
    """Merge *incoming* fields into *existing* without clearing the form.

    Existing fields keep their position; a field is matched by its
    case-insensitive, trimmed label. Returns ``(merged, added, updated)`` where
    ``added``/``updated`` are counts for status reporting.
    """
    merged = [Field(f.label, f.value, f.export_mode) for f in existing]
    index = {f.normalised_label(): idx for idx, f in enumerate(merged)}

    added = 0
    updated = 0
    for item in incoming:
        key = item.normalised_label()
        if key in index:
            target = merged[index[key]]
            if item.value and item.value != target.value:
                target.value = item.value
                updated += 1
        else:
            index[key] = len(merged)
            merged.append(Field(item.label, item.value, item.export_mode))
            added += 1

    return merged, added, updated


if __name__ == "__main__":  # pragma: no cover - manual smoke test
    sample = """\
Client Name: John Doe
Customer Name: (empty)
TICKET ID:

INC12345
Reason:
Network outage in building B
Agency: Acme Corp
Notes: line one
line two
"""
    bullet_sample = """\
Steps taken:
- Remoted to another workstation
- Tried to access the URL at https://WG-Video.LittleFallsPD.local, but the page could not be found
- Opened a putty session and logged in with root The server IP is 10.0.0.7
"""
    for f in parse_notes(sample):
        print(repr(f.label), "=>", repr(f.value))
    print("--- bullets ---")
    for f in parse_notes(bullet_sample):
        print(repr(f.label), "=>", repr(f.value))
    print("--- n/a ---")
    for f in parse_notes("Backup taken: N/A\nStatus: n/a"):
        print(repr(f.label), "=>", repr(f.value))

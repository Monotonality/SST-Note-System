"""Forgiving parser for messy plain-text ticket notes.

Supported layouts (mixable within a single paste):

1. Same-line ............ ``Client Name: John Doe``
2. Empty markers ........ ``Customer Name: (empty)`` or a blank value
3. Label block .......... a label line ending in ``:`` followed (after an
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

# Values that should be normalised to an empty string.
_EMPTY_MARKERS = {
    "(empty)",
    "(none)",
    "(blank)",
    "(n/a)",
    "n/a",
    "na",
    "none",
    "-",
    "--",
    "—",
}


@dataclass
class Field:
    """A single parsed label/value pair."""

    label: str = ""
    value: str = ""

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


def _normalise_value(value: str) -> str:
    if value.strip().lower() in _EMPTY_MARKERS:
        return ""
    return value.strip()


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
                # Possible label block: look ahead past blank lines.
                j = i + 1
                while j < n and not lines[j].strip():
                    j += 1
                if j < n and _is_label_line(lines[j]) is None:
                    # Next non-blank line is a bare value for this label.
                    fields.append(Field(label=label, value=_normalise_value(lines[j])))
                    i = j + 1
                    continue
                # Either end of text or the next line is its own field.
                fields.append(Field(label=label, value=""))
                i += 1
                continue

            fields.append(Field(label=label, value=_normalise_value(value)))
            i += 1
            continue

        # Orphan line (no colon) -> treat as a continuation of the last value.
        if fields:
            extra = raw.strip()
            if fields[-1].value:
                fields[-1].value = f"{fields[-1].value} {extra}"
            else:
                fields[-1].value = extra
        i += 1

    return fields


def merge_fields(existing: List[Field], incoming: List[Field]):
    """Merge *incoming* fields into *existing* without clearing the form.

    Existing fields keep their position; a field is matched by its
    case-insensitive, trimmed label. Returns ``(merged, added, updated)`` where
    ``added``/``updated`` are counts for status reporting.
    """
    merged = [Field(f.label, f.value) for f in existing]
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
            merged.append(Field(item.label, item.value))
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
    for f in parse_notes(sample):
        print(repr(f.label), "=>", repr(f.value))

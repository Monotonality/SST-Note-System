"""Compile open notes into one editable document and split edits back out."""

from __future__ import annotations

import re
from typing import Dict, List, Tuple

from . import exporter
from .exporter import MODE_SAME_LINE
from .parser import Field, parse_notes
from .storage import NoteState

# One marker line per note. IDs are stable across edits so sections map back.
NOTE_MARKER_RE = re.compile(
    r"^<<<NOTE:(?P<id>[^\s>]+)>>>\s*$",
    re.MULTILINE,
)


def note_marker(note_id: str) -> str:
    return f"<<<NOTE:{note_id}>>>"


def note_body(note: NoteState, *, default_mode: str = MODE_SAME_LINE) -> str:
    """Plain-text body for one note (export format preferred, else raw import)."""
    mode = note.export_mode or default_mode
    if note.fields:
        return exporter.format_output(
            note.fields,
            mode=mode,
            blank_between=note.blank_between,
        )
    return note.raw_import.strip()


def compile_running_notes(
    notes: List[NoteState],
    *,
    default_mode: str = MODE_SAME_LINE,
) -> str:
    """Join all notes into one document with stable section markers."""
    blocks: List[str] = []
    for note in notes:
        title = (note.title or "").strip() or note.id
        header = f"{note_marker(note.id)}\n# {title}"
        body = note_body(note, default_mode=default_mode)
        blocks.append(f"{header}\n{body}" if body else header)
    return "\n\n".join(blocks)


def split_running_notes(text: str) -> Dict[str, str]:
    """Map note id → body text from a compiled running-notes document.

    The optional ``# title`` line immediately after a marker is stripped from the
    body so it does not become a parsed field.
    """
    matches = list(NOTE_MARKER_RE.finditer(text))
    if not matches:
        return {}

    sections: Dict[str, str] = {}
    for i, match in enumerate(matches):
        note_id = match.group("id")
        start = match.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        body = text[start:end].lstrip("\n")
        # Drop the human-readable title line we insert on compile.
        if body.startswith("# "):
            nl = body.find("\n")
            body = body[nl + 1 :] if nl >= 0 else ""
        sections[note_id] = body.strip("\n")
    return sections


def apply_sections_to_notes(
    notes: List[NoteState],
    sections: Dict[str, str],
    *,
    default_mode: str = MODE_SAME_LINE,
) -> Tuple[List[NoteState], int]:
    """Update notes whose ids appear in *sections*. Returns (notes, updated_count)."""
    updated = 0
    result: List[NoteState] = []
    for note in notes:
        if note.id not in sections:
            result.append(note)
            continue
        body = sections[note.id]
        fields: List[Field] = parse_notes(body) if body.strip() else []
        result.append(
            NoteState(
                id=note.id,
                title=note.title,
                fields=fields,
                raw_import=body,
                export_mode=note.export_mode or default_mode,
                blank_between=note.blank_between,
                source_path=note.source_path,
            )
        )
        updated += 1
    return result, updated

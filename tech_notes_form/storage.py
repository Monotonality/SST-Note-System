"""App-local persistence for the draft and user settings.

Data lives in the per-user application data folder (NOT browser storage):

* Windows: ``%AppData%/TechNotesForm``
* Other OSes: ``~/.config/TechNotesForm`` (handy for development)
"""

from __future__ import annotations

import json
import os
import re
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List

from . import ORG_NAME
from .parser import Field
from .templates import Template

DRAFT_FILE = "draft.json"
SETTINGS_FILE = "settings.json"
TEMPLATES_FILE = "templates.json"


@dataclass
class NoteState:
    id: str
    title: str = ""
    fields: List[Field] = field(default_factory=list)
    raw_import: str = ""
    export_mode: str = ""
    blank_between: bool = False


@dataclass
class WorkspaceState:
    active_index: int = 0
    notes: List[NoteState] = field(default_factory=list)


def app_data_dir() -> Path:
    base = os.environ.get("APPDATA")
    if base:
        path = Path(base) / ORG_NAME
    else:
        path = Path.home() / ".config" / ORG_NAME
    path.mkdir(parents=True, exist_ok=True)
    return path


def _read_json(path: Path) -> Dict[str, Any]:
    try:
        with path.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
            return data if isinstance(data, dict) else {}
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {}


def _write_json(path: Path, data: Dict[str, Any]) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    try:
        with tmp.open("w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2, ensure_ascii=False)
        os.replace(tmp, path)
    except OSError:
        # Persistence is best-effort; never crash the app over a failed save.
        pass


# --- Draft / workspace -----------------------------------------------------

def new_note_id() -> str:
    return f"note-{uuid.uuid4().hex[:8]}"


def _fields_from_json(items: Any) -> List[Field]:
    fields: List[Field] = []
    if not isinstance(items, list):
        return fields
    for item in items:
        if isinstance(item, dict):
            fields.append(Field(
                label=item.get("label", ""),
                value=item.get("value", ""),
                export_mode=item.get("export_mode", ""),
            ))
    return fields


def _note_from_dict(data: Dict[str, Any]) -> NoteState:
    return NoteState(
        id=data.get("id") or new_note_id(),
        title=data.get("title", ""),
        fields=_fields_from_json(data.get("fields", [])),
        raw_import=data.get("raw_import", ""),
        export_mode=data.get("export_mode", ""),
        blank_between=bool(data.get("blank_between", False)),
    )


def save_workspace(workspace: WorkspaceState) -> None:
    data = {
        "active_index": workspace.active_index,
        "notes": [
            {
                "id": note.id,
                "title": note.title,
                "fields": [
                    {
                        "label": f.label,
                        "value": f.value,
                        "export_mode": f.export_mode,
                    }
                    for f in note.fields
                ],
                "raw_import": note.raw_import,
                "export_mode": note.export_mode,
                "blank_between": note.blank_between,
            }
            for note in workspace.notes
        ],
    }
    _write_json(app_data_dir() / DRAFT_FILE, data)


def load_workspace() -> WorkspaceState:
    data = _read_json(app_data_dir() / DRAFT_FILE)
    if isinstance(data.get("notes"), list):
        notes = [_note_from_dict(item) for item in data["notes"] if isinstance(item, dict)]
        active_index = data.get("active_index", 0)
        if not isinstance(active_index, int):
            active_index = 0
        if not notes:
            notes = [NoteState(id=new_note_id())]
        active_index = max(0, min(active_index, len(notes) - 1))
        return WorkspaceState(active_index=active_index, notes=notes)

    # Migrate the legacy single-note draft.json format.
    note = NoteState(
        id=new_note_id(),
        fields=_fields_from_json(data.get("fields", [])),
        raw_import=data.get("raw_import", ""),
        export_mode=data.get("export_mode", "") or "",
        blank_between=bool(data.get("blank_between", False)),
    )
    return WorkspaceState(active_index=0, notes=[note])


def save_draft(fields: List[Field], raw_import: str, export_mode: str,
               blank_between: bool) -> None:
    """Backward-compatible single-note save (used only if callers still use it)."""
    save_workspace(WorkspaceState(
        active_index=0,
        notes=[NoteState(
            id=new_note_id(),
            fields=fields,
            raw_import=raw_import,
            export_mode=export_mode,
            blank_between=blank_between,
        )],
    ))


def load_draft() -> Dict[str, Any]:
    """Backward-compatible single-note load."""
    note = load_workspace().notes[0]
    return {
        "fields": note.fields,
        "raw_import": note.raw_import,
        "export_mode": note.export_mode or None,
        "blank_between": note.blank_between,
    }


def default_notes_dir() -> Path:
    """Exported note text files live in Documents/AdamNote (created if needed)."""
    for base in (Path.home() / "Documents", Path.home() / "Desktop", Path.home()):
        if base.is_dir():
            notes_dir = base / ORG_NAME
            notes_dir.mkdir(parents=True, exist_ok=True)
            return notes_dir
    notes_dir = Path.home() / ORG_NAME
    notes_dir.mkdir(parents=True, exist_ok=True)
    return notes_dir


def safe_filename(name: str, *, fallback: str = "notes") -> str:
    cleaned = re.sub(r'[<>:"/\\|?*]', "-", name.strip())
    cleaned = cleaned.strip(". ")
    return cleaned[:120] if cleaned else fallback


def resolve_notes_dir(settings: Dict[str, Any]) -> Path:
    stored = settings.get("last_notes_dir", "")
    if isinstance(stored, str) and stored:
        path = Path(stored)
        if path.is_dir():
            return path
    return default_notes_dir()


def remember_notes_dir(settings: Dict[str, Any], file_path: str) -> None:
    parent = Path(file_path).parent
    if parent.is_dir():
        settings["last_notes_dir"] = str(parent)


# --- Settings --------------------------------------------------------------

def save_settings(settings: Dict[str, Any]) -> None:
    _write_json(app_data_dir() / SETTINGS_FILE, settings)


def load_settings() -> Dict[str, Any]:
    return _read_json(app_data_dir() / SETTINGS_FILE)


# --- Custom templates ------------------------------------------------------

def load_custom_templates() -> List[Template]:
    data = _read_json(app_data_dir() / TEMPLATES_FILE)
    templates: List[Template] = []
    for item in data.get("templates", []):
        if not isinstance(item, dict):
            continue
        templates.append(
            Template(
                id=item.get("id", ""),
                name=item.get("name", "Untitled"),
                description=item.get("description", ""),
                sample=item.get("sample", ""),
                builtin=False,
            )
        )
    return templates


def save_custom_templates(templates: List[Template]) -> None:
    data = {
        "templates": [
            {
                "id": t.id,
                "name": t.name,
                "description": t.description,
                "sample": t.sample,
            }
            for t in templates
            if not t.builtin
        ]
    }
    _write_json(app_data_dir() / TEMPLATES_FILE, data)

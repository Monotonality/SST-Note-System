"""App-local persistence for the draft and user settings.

Data lives in the per-user application data folder (NOT browser storage):

* Windows: ``%AppData%/TechNotesForm``
* Other OSes: ``~/.config/TechNotesForm`` (handy for development)
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, List

from . import ORG_NAME
from .parser import Field
from .templates import Template

DRAFT_FILE = "draft.json"
SETTINGS_FILE = "settings.json"
TEMPLATES_FILE = "templates.json"


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


# --- Draft -----------------------------------------------------------------

def save_draft(fields: List[Field], raw_import: str, export_mode: str,
               blank_between: bool) -> None:
    data = {
        "fields": [
            {"label": f.label, "value": f.value, "export_mode": f.export_mode}
            for f in fields
        ],
        "raw_import": raw_import,
        "export_mode": export_mode,
        "blank_between": blank_between,
    }
    _write_json(app_data_dir() / DRAFT_FILE, data)


def load_draft() -> Dict[str, Any]:
    data = _read_json(app_data_dir() / DRAFT_FILE)
    fields = []
    for item in data.get("fields", []):
        if isinstance(item, dict):
            fields.append(Field(
                label=item.get("label", ""),
                value=item.get("value", ""),
                export_mode=item.get("export_mode", ""),
            ))
    return {
        "fields": fields,
        "raw_import": data.get("raw_import", ""),
        "export_mode": data.get("export_mode"),
        "blank_between": data.get("blank_between"),
    }


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

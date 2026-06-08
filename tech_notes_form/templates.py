"""Built-in note templates that technologists can copy, load, or load & parse."""

from __future__ import annotations

from dataclasses import dataclass
from typing import List


@dataclass
class Template:
    id: str
    name: str
    description: str
    sample: str
    builtin: bool = True

    def preview(self, lines: int = 6) -> str:
        """First *lines* lines of the sample, for a compact preview snippet."""
        rows = self.sample.strip().splitlines()
        snippet = "\n".join(rows[:lines])
        if len(rows) > lines:
            snippet += "\n..."
        return snippet


TEMPLATES: List[Template] = [
    Template(
        id="default_case",
        name="Standard Case (Default)",
        description="Default SST case note layout: triage, investigation, and close-out.",
        sample=(
            "Priority: \n"
            "Incident Number:\n"
            "Agency Name: \n"
            "Software Versions/Firmware Versions:\n"
            "\n"
            "When was the agency's EL solution deployed?: \n"
            "\n"
            "What was reported:\n"
            "\n"
            "Customer Ticket History:\n"
            "\n"
            "What occurred before the problem was reported:\n"
            "\n"
            "What KB's were used? (KB# - KB Article Title):\n"
            "\n"
            "What was found:\n"
            "\n"
            "Actions taken:\n"
            "\n"
            "Current status:\n"
            "\n"
            "Confirm Status:\n"
            "    Permission to Close: \n"
            "    Permission was given by: \n"
            "    Time/Date:\n"
        ),
    ),
]


def get_template(template_id: str) -> Template | None:
    for tpl in TEMPLATES:
        if tpl.id == template_id:
            return tpl
    return None


def all_templates() -> List[Template]:
    """Built-in plus user-saved custom templates."""
    from . import storage

    return list(TEMPLATES) + storage.load_custom_templates()


def resolve_template(template_id: str) -> Template | None:
    if not template_id:
        return None
    for tpl in all_templates():
        if tpl.id == template_id:
            return tpl
    return None


def template_choices() -> List[tuple[str, str]]:
    """``(id, label)`` pairs for preference / picker combos. ``""`` = none."""
    return [("", "None")] + [(t.id, t.name) for t in all_templates()]

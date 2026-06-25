"""Built-in note templates that technologists can copy, load, or load & parse."""

from __future__ import annotations

from dataclasses import dataclass
from typing import List


DEFAULT_TEMPLATE_ID = "default_case"


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
        id=DEFAULT_TEMPLATE_ID,
        name="Standard Case (Default)",
        description="Default SST case note layout: triage, investigation, and close-out.",
        sample=(
            "Priority: \n"
            "INC Number:\n"
            "Agency:\n"
            "Name:\n"
            "State:\n"
            "Software/Firmware Version:\n"
            "Deployment Date:\n"
            "\n"
            "Initial Issue Description:\n"
            "\n"
            "Customer Ticket History:\n"
            "\n"
            "Incident Context & Background:\n"
            "\n"
            "Diagnostic Findings:\n"
            "\n"
            "KB Utilization:\n"
            "\n"
            "Actions Taken:\n"
            "\n"
            "Next Steps:\n"
            "\n"
            "Closure Details:\n"
        ),
    ),
    Template(
        id="joseph_template",
        name="Joseph Template",
        description="Legacy SST case note layout with confirm-status close-out.",
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
    Template(
        id="jira_template",
        name="JIRA",
        description="JIRA ticket intake layout for agency, issue, and troubleshooting details.",
        sample=(
            "Description:\n"
            "\n"
            "Agency Name:\n"
            "Agency State:\n"
            "\n"
            "Customer Issue Description:\n"
            "\n"
            "Additional Information:\n"
            "\n"
            "Specific Dates:\n"
            "\n"
            "Specific Times:\n"
            "\n"
            "REIDS:\n"
            "\n"
            "Previous Troubleshooting Attempts:\n"
            "\n"
            "State Capture File Location:\n"
            "\n"
            "Requester First/Last Name:\n"
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

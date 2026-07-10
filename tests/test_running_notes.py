"""Running-notes compile / split regression tests."""

from __future__ import annotations

import unittest

from tech_notes_form.parser import Field
from tech_notes_form.running_notes import (
    apply_sections_to_notes,
    compile_running_notes,
    note_marker,
    split_running_notes,
)
from tech_notes_form.storage import NoteState


class RunningNotesTests(unittest.TestCase):
    def test_round_trip_preserves_fields(self):
        notes = [
            NoteState(
                id="note-aaa",
                title="Alpha",
                fields=[Field("INC Number", "INC001"), Field("Agency", "DoT")],
            ),
            NoteState(
                id="note-bbb",
                title="Beta",
                fields=[Field("Name", "Alex"), Field("State", "Active")],
            ),
        ]
        compiled = compile_running_notes(notes)
        self.assertIn(note_marker("note-aaa"), compiled)
        self.assertIn(note_marker("note-bbb"), compiled)
        self.assertIn("# Alpha", compiled)
        self.assertIn("INC Number: INC001", compiled)

        sections = split_running_notes(compiled)
        self.assertEqual(set(sections), {"note-aaa", "note-bbb"})
        updated, count = apply_sections_to_notes(notes, sections)
        self.assertEqual(count, 2)
        self.assertEqual(updated[0].fields[0].value, "INC001")
        self.assertEqual(updated[1].fields[0].label, "Name")

    def test_edit_one_section_updates_only_that_note(self):
        notes = [
            NoteState(
                id="note-aaa",
                title="Alpha",
                fields=[Field("INC Number", "INC001")],
            ),
            NoteState(
                id="note-bbb",
                title="Beta",
                fields=[Field("Name", "Alex")],
            ),
        ]
        compiled = compile_running_notes(notes)
        edited = compiled.replace("Alex", "Jordan")
        sections = split_running_notes(edited)
        updated, count = apply_sections_to_notes(notes, sections)
        self.assertEqual(count, 2)
        self.assertEqual(updated[0].fields[0].value, "INC001")
        self.assertEqual(updated[1].fields[0].value, "Jordan")

    def test_missing_marker_leaves_note_unchanged(self):
        notes = [
            NoteState(id="note-aaa", fields=[Field("A", "1")]),
            NoteState(id="note-bbb", fields=[Field("B", "2")]),
        ]
        # Only one section present.
        text = f"{note_marker('note-aaa')}\n# Alpha\nA: changed\n"
        sections = split_running_notes(text)
        updated, count = apply_sections_to_notes(notes, sections)
        self.assertEqual(count, 1)
        self.assertEqual(updated[0].fields[0].value, "changed")
        self.assertEqual(updated[1].fields[0].value, "2")

    def test_empty_body_clears_fields(self):
        notes = [NoteState(id="note-aaa", fields=[Field("A", "1")])]
        text = f"{note_marker('note-aaa')}\n# Alpha\n"
        sections = split_running_notes(text)
        updated, count = apply_sections_to_notes(notes, sections)
        self.assertEqual(count, 1)
        self.assertEqual(updated[0].fields, [])


if __name__ == "__main__":
    unittest.main()

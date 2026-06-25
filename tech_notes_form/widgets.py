"""Reusable widgets: an editable field row and the templates browser dialog."""

from __future__ import annotations

import uuid
from typing import List

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from . import storage
from .parser import Field, MODE_LABEL_BLOCK, MODE_SAME_LINE
from .templates import TEMPLATES, Template

PARSE_MODE_PARSE = "parse"
PARSE_MODE_MERGE = "merge"

PARSE_MODE_CHOICES = [
    (PARSE_MODE_PARSE, "Parse (replace form)"),
    (PARSE_MODE_MERGE, "Merge (add / update fields)"),
]


class ImportPasteEdit(QPlainTextEdit):
    """Import paste area that emits ``pasted`` when text is inserted from the clipboard."""

    pasted = Signal()

    def insertFromMimeData(self, source):
        super().insertFromMimeData(source)
        self.pasted.emit()


class PreferencesDialog(QDialog):
    """Application preferences (theme is under View ▸ Theme)."""

    def __init__(
        self,
        parent=None,
        *,
        persistent_sidebars: bool,
        compact: bool,
        confirm_clear_values: bool,
        import_panel_visible: bool,
        export_panel_visible: bool,
        remember_splitter_sizes: bool,
        default_template_id: str,
        template_choices: List[tuple[str, str]],
        auto_parse_on_paste: bool,
        default_parse_mode: str,
        default_export_mode: str,
        export_mode_choices: List[tuple[str, str]],
    ):
        super().__init__(parent)
        self.setWindowTitle("Preferences")
        self.setMinimumSize(560, 620)
        self.resize(600, 680)

        outer = QVBoxLayout(self)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)
        body = QWidget()
        form = QFormLayout(body)
        form.setSpacing(12)
        form.setContentsMargins(4, 4, 4, 4)

        def section(title: str):
            heading = QLabel(title)
            heading.setObjectName("PanelTitle")
            form.addRow(heading)

        section("Appearance")
        self.persistent_check = QCheckBox(
            "Keep a reopen button on the edge when a side panel is collapsed"
        )
        self.persistent_check.setChecked(persistent_sidebars)
        form.addRow("Sidebars", self.persistent_check)

        self.compact_check = QCheckBox(
            "Hide the form and edit in the live preview only (Import + Export)"
        )
        self.compact_check.setChecked(compact)
        form.addRow("Compact mode", self.compact_check)

        section("Form")
        self.confirm_clear_check = QCheckBox(
            "Ask for confirmation before clearing all field values"
        )
        self.confirm_clear_check.setChecked(confirm_clear_values)
        form.addRow("Clear values", self.confirm_clear_check)

        section("Layout")
        self.import_visible_check = QCheckBox("Show Import panel when the app opens")
        self.import_visible_check.setChecked(import_panel_visible)
        form.addRow("Import panel", self.import_visible_check)

        self.export_visible_check = QCheckBox("Show Export panel when the app opens")
        self.export_visible_check.setChecked(export_panel_visible)
        form.addRow("Export panel", self.export_visible_check)

        self.remember_splitter_check = QCheckBox(
            "Remember how wide the Import / Form / Export panels are"
        )
        self.remember_splitter_check.setChecked(remember_splitter_sizes)
        form.addRow("Panel widths", self.remember_splitter_check)

        section("Import & templates")
        self.template_combo = QComboBox()
        for tid, label in template_choices:
            self.template_combo.addItem(label, tid)
        idx = self.template_combo.findData(default_template_id or "")
        if idx >= 0:
            self.template_combo.setCurrentIndex(idx)
        form.addRow("Default template", self.template_combo)

        self.auto_parse_check = QCheckBox(
            "Parse or merge automatically when text is pasted into Import"
        )
        self.auto_parse_check.setChecked(auto_parse_on_paste)
        form.addRow("Auto-parse", self.auto_parse_check)

        self.parse_mode_combo = QComboBox()
        for mode_id, label in PARSE_MODE_CHOICES:
            self.parse_mode_combo.addItem(label, mode_id)
        pidx = self.parse_mode_combo.findData(default_parse_mode)
        if pidx >= 0:
            self.parse_mode_combo.setCurrentIndex(pidx)
        form.addRow("Default parse mode", self.parse_mode_combo)

        section("Export")
        self.export_mode_combo = QComboBox()
        for mode_id, label in export_mode_choices:
            self.export_mode_combo.addItem(label, mode_id)
        eidx = self.export_mode_combo.findData(default_export_mode)
        if eidx >= 0:
            self.export_mode_combo.setCurrentIndex(eidx)
        form.addRow("Export format", self.export_mode_combo)

        scroll.setWidget(body)
        outer.addWidget(scroll, 1)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        outer.addWidget(buttons)

    def values(self) -> dict:
        return {
            "persistent_sidebars": self.persistent_check.isChecked(),
            "compact": self.compact_check.isChecked(),
            "confirm_clear_values": self.confirm_clear_check.isChecked(),
            "import_panel_visible": self.import_visible_check.isChecked(),
            "export_panel_visible": self.export_visible_check.isChecked(),
            "remember_splitter_sizes": self.remember_splitter_check.isChecked(),
            "default_template_id": self.template_combo.currentData() or "",
            "auto_parse_on_paste": self.auto_parse_check.isChecked(),
            "default_parse_mode": self.parse_mode_combo.currentData() or PARSE_MODE_PARSE,
            "default_export_mode": self.export_mode_combo.currentData() or MODE_SAME_LINE,
        }


class GrowingTextEdit(QTextEdit):
    """A wrapping, multi-line value box that auto-sizes its height to fit the
    content. It starts at a single line, wraps at the right edge, and grows to
    show all of its text (it never scrolls internally); the surrounding Form
    scroll area handles overall scrolling.

    Uses ``QTextEdit`` because its document height is reported in pixels, which
    makes the fit-to-content calculation reliable (``QPlainTextEdit`` reports it
    in line counts).
    """

    MIN_HEIGHT = 34  # ~one line; grows as content wraps to new lines

    def __init__(self, text: str = "", parent=None):
        super().__init__(parent)
        self.setAcceptRichText(False)
        self.setPlainText(text)
        self.setLineWrapMode(QTextEdit.LineWrapMode.WidgetWidth)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setTabChangesFocus(True)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.textChanged.connect(self._fit)
        self.document().documentLayout().documentSizeChanged.connect(self._fit)
        self._fit()

    def _fit(self, *_):
        doc = self.document()
        doc.setTextWidth(self.viewport().width())
        doc_height = doc.size().height()  # pixels for QTextEdit
        target = max(self.MIN_HEIGHT, int(doc_height) + self.frameWidth() * 2 + 14)
        if target != self.height():
            self.setFixedHeight(target)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._fit()

    def showEvent(self, event):
        super().showEvent(event)
        self._fit()


class FieldRow(QWidget):
    """A single label/value pair laid out as a card: a full-width label on top
    with copy/remove actions, and an auto-growing value box beneath it."""

    changed = Signal()
    removeRequested = Signal(object)
    copied = Signal(str)

    def __init__(self, field: Field, parent=None, *, default_export_mode: str = MODE_SAME_LINE):
        super().__init__(parent)
        self.setObjectName("FieldCard")
        self._export_mode = field.export_mode or default_export_mode

        outer = QVBoxLayout(self)
        outer.setContentsMargins(10, 8, 10, 10)
        outer.setSpacing(6)

        header = QHBoxLayout()
        header.setSpacing(8)

        self.label_edit = QLineEdit(field.label)
        self.label_edit.setObjectName("FieldLabel")
        self.label_edit.setPlaceholderText("Label")
        self.label_edit.setAccessibleName("Field label")

        self.format_btn = QPushButton()
        self.format_btn.setObjectName("FormatToggle")
        self.format_btn.setCheckable(True)
        self.format_btn.setChecked(self._export_mode == MODE_LABEL_BLOCK)
        self.format_btn.setAccessibleName("Toggle export format for this field")
        self.format_btn.setCursor(Qt.PointingHandCursor)
        self._sync_format_btn()

        self.copy_btn = QPushButton("\u29c9")  # overlapping squares = copy glyph
        self.copy_btn.setObjectName("IconButton")
        self.copy_btn.setToolTip("Copy this field's value")
        self.copy_btn.setAccessibleName("Copy field value")
        self.copy_btn.setCursor(Qt.PointingHandCursor)

        self.remove_btn = QPushButton("\u00d7")  # multiplication sign
        self.remove_btn.setObjectName("Remove")
        self.remove_btn.setToolTip("Remove this field")
        self.remove_btn.setAccessibleName("Remove field")
        self.remove_btn.setCursor(Qt.PointingHandCursor)

        header.addWidget(self.label_edit, 1)
        header.addWidget(self.format_btn)
        header.addWidget(self.copy_btn)
        header.addWidget(self.remove_btn)

        # Wrapping, multi-line box (like the Import area) that grows as needed.
        self.value_edit = GrowingTextEdit(field.value)
        self.value_edit.setPlaceholderText("Value")
        self.value_edit.setAccessibleName("Field value")

        outer.addLayout(header)
        outer.addWidget(self.value_edit)

        self.label_edit.textChanged.connect(self.changed)
        self.value_edit.textChanged.connect(self.changed)
        self.format_btn.toggled.connect(self._on_format_toggled)
        self.copy_btn.clicked.connect(self._on_copy)
        self.remove_btn.clicked.connect(lambda: self.removeRequested.emit(self))

    def _sync_format_btn(self):
        if self._export_mode == MODE_LABEL_BLOCK:
            self.format_btn.setText("\u21b5")  # ↵ label block
            self.format_btn.setToolTip(
                "Export: label on one line, value on the next (click for Label: value)"
            )
        else:
            self.format_btn.setText(":")
            self.format_btn.setToolTip(
                "Export: Label: value on the same line (click for label block)"
            )

    def _on_format_toggled(self, checked: bool):
        self._export_mode = MODE_LABEL_BLOCK if checked else MODE_SAME_LINE
        self._sync_format_btn()
        self.changed.emit()

    def _on_copy(self):
        QApplication.clipboard().setText(self.value_edit.toPlainText())
        self.copied.emit(self.label_edit.text().strip() or "field")

    def to_field(self) -> Field:
        return Field(
            label=self.label_edit.text(),
            value=self.value_edit.toPlainText(),
            export_mode=self._export_mode,
        )

    def clear_value(self):
        """Empty this field's value box; the label is left unchanged."""
        self.value_edit.blockSignals(True)
        self.value_edit.setPlainText("")
        self.value_edit.blockSignals(False)

    def focus_label(self):
        self.label_edit.setFocus()


class TemplateEditDialog(QDialog):
    """Create or edit a custom template (name, description, sample text)."""

    def __init__(self, parent=None, template: Template | None = None,
                 title: str = "New Template"):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(560, 460)

        layout = QVBoxLayout(self)

        layout.addWidget(QLabel("Name"))
        self.name_edit = QLineEdit(template.name if template else "")
        self.name_edit.setPlaceholderText("e.g. Hardware Swap")
        self.name_edit.setAccessibleName("Template name")
        layout.addWidget(self.name_edit)

        layout.addWidget(QLabel("Description"))
        self.desc_edit = QLineEdit(template.description if template else "")
        self.desc_edit.setPlaceholderText("Short description shown in the list")
        self.desc_edit.setAccessibleName("Template description")
        layout.addWidget(self.desc_edit)

        layout.addWidget(QLabel("Sample text"))
        self.sample_edit = QPlainTextEdit(template.sample if template else "")
        self.sample_edit.setPlaceholderText(
            "Label: value\nAnother Label: (empty)\nTICKET ID:\nINC00000"
        )
        self.sample_edit.setAccessibleName("Template sample text")
        layout.addWidget(self.sample_edit, 1)

        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _on_accept(self):
        if not self.name_edit.text().strip():
            QMessageBox.warning(self, "Name required", "Please enter a template name.")
            self.name_edit.setFocus()
            return
        self.accept()

    def values(self):
        return (
            self.name_edit.text().strip(),
            self.desc_edit.text().strip(),
            self.sample_edit.toPlainText(),
        )


class TemplatesDialog(QDialog):
    """Browse built-in and custom templates; copy / load / load & parse,
    and create / edit / delete your own templates."""

    loadRequested = Signal(str)
    loadAndParseRequested = Signal(str)

    def __init__(self, parent=None, current_note_text: str = ""):
        super().__init__(parent)
        self.setWindowTitle("Note Templates")
        self.resize(760, 520)
        self._current_note_text = current_note_text
        self._templates: List[Template] = []

        root = QHBoxLayout(self)

        # Left: template list.
        self.list = QListWidget()
        self.list.setMaximumWidth(260)
        self.list.setAccessibleName("Template list")
        root.addWidget(self.list)

        # Right: details + actions.
        right = QVBoxLayout()
        self.name_label = QLabel()
        self.name_label.setObjectName("PanelTitle")
        self.desc_label = QLabel()
        self.desc_label.setObjectName("StatusLabel")
        self.desc_label.setWordWrap(True)

        self.preview = QPlainTextEdit()
        self.preview.setReadOnly(True)
        self.preview.setAccessibleName("Template preview")

        use_buttons = QHBoxLayout()
        self.copy_btn = QPushButton("Copy")
        self.load_btn = QPushButton("Load")
        self.load_parse_btn = QPushButton("Load && parse")
        self.load_parse_btn.setObjectName("Primary")
        use_buttons.addWidget(self.copy_btn)
        use_buttons.addWidget(self.load_btn)
        use_buttons.addStretch(1)
        use_buttons.addWidget(self.load_parse_btn)

        manage_buttons = QHBoxLayout()
        self.new_btn = QPushButton("New\u2026")
        self.save_current_btn = QPushButton("Save current note\u2026")
        self.edit_btn = QPushButton("Edit\u2026")
        self.delete_btn = QPushButton("Delete")
        manage_buttons.addWidget(self.new_btn)
        manage_buttons.addWidget(self.save_current_btn)
        manage_buttons.addStretch(1)
        manage_buttons.addWidget(self.edit_btn)
        manage_buttons.addWidget(self.delete_btn)

        right.addWidget(self.name_label)
        right.addWidget(self.desc_label)
        right.addWidget(self.preview, 1)
        right.addLayout(use_buttons)
        right.addLayout(manage_buttons)
        root.addLayout(right, 1)

        self.list.currentRowChanged.connect(self._on_select)
        self.copy_btn.clicked.connect(self._on_copy)
        self.load_btn.clicked.connect(self._on_load)
        self.load_parse_btn.clicked.connect(self._on_load_parse)
        self.new_btn.clicked.connect(self._on_new)
        self.save_current_btn.clicked.connect(self._on_save_current)
        self.edit_btn.clicked.connect(self._on_edit)
        self.delete_btn.clicked.connect(self._on_delete)

        self._reload_list()

    def _reload_list(self):
        self._templates = list(TEMPLATES) + storage.load_custom_templates()
        self.list.clear()
        for tpl in self._templates:
            tag = "" if tpl.builtin else " (custom)"
            self.list.addItem(QListWidgetItem(f"{tpl.name}{tag}"))
        if self._templates:
            self.list.setCurrentRow(0)

    def _current(self) -> Template | None:
        row = self.list.currentRow()
        if row < 0 or row >= len(self._templates):
            return None
        return self._templates[row]

    def _on_select(self, row: int):
        tpl = self._templates[row] if 0 <= row < len(self._templates) else None
        if tpl is None:
            self.name_label.clear()
            self.desc_label.clear()
            self.preview.clear()
            self.edit_btn.setEnabled(False)
            self.delete_btn.setEnabled(False)
            return
        self.name_label.setText(tpl.name)
        self.desc_label.setText(tpl.description)
        self.preview.setPlainText(tpl.preview())
        self.edit_btn.setEnabled(not tpl.builtin)
        self.delete_btn.setEnabled(not tpl.builtin)

    def _on_copy(self):
        tpl = self._current()
        if tpl:
            QApplication.clipboard().setText(tpl.sample)
            QMessageBox.information(self, "Copied", "Template text copied to the clipboard.")

    def _on_load(self):
        tpl = self._current()
        if tpl:
            self.loadRequested.emit(tpl.sample)
            self.accept()

    def _on_load_parse(self):
        tpl = self._current()
        if tpl:
            self.loadAndParseRequested.emit(tpl.sample)
            self.accept()

    def _on_new(self):
        dialog = TemplateEditDialog(self, title="New Template")
        if dialog.exec() != QDialog.Accepted:
            return
        name, desc, sample = dialog.values()
        custom = storage.load_custom_templates()
        custom.append(
            Template(
                id=str(uuid.uuid4()),
                name=name,
                description=desc,
                sample=sample,
                builtin=False,
            )
        )
        storage.save_custom_templates(custom)
        self._reload_list()

    def _on_save_current(self):
        if not self._current_note_text.strip():
            QMessageBox.information(
                self, "Nothing to save", "The current note is empty."
            )
            return
        dialog = TemplateEditDialog(self, title="Save Current Note as Template")
        dialog.sample_edit.setPlainText(self._current_note_text)
        if dialog.exec() != QDialog.Accepted:
            return
        name, desc, sample = dialog.values()
        custom = storage.load_custom_templates()
        custom.append(
            Template(
                id=str(uuid.uuid4()),
                name=name,
                description=desc,
                sample=sample,
                builtin=False,
            )
        )
        storage.save_custom_templates(custom)
        self._reload_list()

    def _on_edit(self):
        tpl = self._current()
        if tpl is None or tpl.builtin:
            return
        dialog = TemplateEditDialog(self, template=tpl, title="Edit Template")
        if dialog.exec() != QDialog.Accepted:
            return
        name, desc, sample = dialog.values()
        custom = storage.load_custom_templates()
        for i, t in enumerate(custom):
            if t.id == tpl.id:
                custom[i] = Template(
                    id=t.id, name=name, description=desc, sample=sample, builtin=False
                )
                break
        storage.save_custom_templates(custom)
        self._reload_list()

    def _on_delete(self):
        tpl = self._current()
        if tpl is None or tpl.builtin:
            return
        reply = QMessageBox.question(
            self,
            "Delete template",
            f"Delete the template \"{tpl.name}\"?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return
        custom = [t for t in storage.load_custom_templates() if t.id != tpl.id]
        storage.save_custom_templates(custom)
        self._reload_list()

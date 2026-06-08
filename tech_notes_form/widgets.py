"""Reusable widgets: an editable field row and the templates browser dialog."""

from __future__ import annotations

import uuid
from typing import List

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
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
    QSizePolicy,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from . import storage
from .parser import Field
from .templates import TEMPLATES, Template


class PreferencesDialog(QDialog):
    """App preferences: persistent sidebars and compact density.

    (Theme is chosen from the View ▸ Theme menu.)
    """

    def __init__(self, parent=None, *, persistent_sidebars: bool, compact: bool):
        super().__init__(parent)
        self.setWindowTitle("Preferences")
        self.setMinimumWidth(420)

        layout = QVBoxLayout(self)
        form = QFormLayout()
        form.setSpacing(10)

        self.persistent_check = QCheckBox(
            "Keep a reopen button on the edge when a side panel is collapsed"
        )
        self.persistent_check.setChecked(persistent_sidebars)
        form.addRow("Sidebars", self.persistent_check)

        self.compact_check = QCheckBox(
            "Compact mode (tighter spacing and fonts for small windows)"
        )
        self.compact_check.setChecked(compact)
        form.addRow("Density", self.compact_check)

        layout.addLayout(form)
        layout.addStretch(1)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def values(self) -> dict:
        return {
            "persistent_sidebars": self.persistent_check.isChecked(),
            "compact": self.compact_check.isChecked(),
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

    def __init__(self, field: Field, parent=None):
        super().__init__(parent)
        self.setObjectName("FieldCard")

        outer = QVBoxLayout(self)
        outer.setContentsMargins(10, 8, 10, 10)
        outer.setSpacing(6)

        header = QHBoxLayout()
        header.setSpacing(8)

        self.label_edit = QLineEdit(field.label)
        self.label_edit.setObjectName("FieldLabel")
        self.label_edit.setPlaceholderText("Label")
        self.label_edit.setAccessibleName("Field label")

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
        self.copy_btn.clicked.connect(self._on_copy)
        self.remove_btn.clicked.connect(lambda: self.removeRequested.emit(self))

    def _on_copy(self):
        QApplication.clipboard().setText(self.value_edit.toPlainText())
        self.copied.emit(self.label_edit.text().strip() or "field")

    def to_field(self) -> Field:
        return Field(label=self.label_edit.text(), value=self.value_edit.toPlainText())

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

        self.save_current_btn.setEnabled(bool(current_note_text.strip()))

        self._reload(select_id=None)

    # ------------------------------------------------------------- helpers

    def _reload(self, select_id: str | None):
        self._templates = list(TEMPLATES) + storage.load_custom_templates()
        self.list.blockSignals(True)
        self.list.clear()
        target_row = 0
        for idx, tpl in enumerate(self._templates):
            label = tpl.name if tpl.builtin else f"{tpl.name}  (custom)"
            item = QListWidgetItem(label)
            item.setData(Qt.UserRole, tpl.id)
            self.list.addItem(item)
            if select_id and tpl.id == select_id:
                target_row = idx
        self.list.blockSignals(False)
        if self._templates:
            self.list.setCurrentRow(target_row)
        else:
            self._on_select(-1)

    def _current_template(self) -> Template | None:
        row = self.list.currentRow()
        if 0 <= row < len(self._templates):
            return self._templates[row]
        return None

    def _custom_templates(self) -> List[Template]:
        return [t for t in self._templates if not t.builtin]

    def _persist_custom(self):
        storage.save_custom_templates(self._custom_templates())

    # ------------------------------------------------------------- selection

    def _on_select(self, _row: int):
        tpl = self._current_template()
        is_custom = bool(tpl and not tpl.builtin)
        self.edit_btn.setEnabled(is_custom)
        self.delete_btn.setEnabled(is_custom)
        if not tpl:
            self.name_label.setText("No templates")
            self.desc_label.setText("Create one with New or Save current note.")
            self.preview.setPlainText("")
            self.copy_btn.setEnabled(False)
            self.load_btn.setEnabled(False)
            self.load_parse_btn.setEnabled(False)
            return
        self.copy_btn.setEnabled(True)
        self.load_btn.setEnabled(True)
        self.load_parse_btn.setEnabled(True)
        self.name_label.setText(tpl.name)
        self.desc_label.setText(tpl.description or ("Custom template" if is_custom else ""))
        self.preview.setPlainText(tpl.sample.rstrip())

    # --------------------------------------------------------------- use ops

    def _on_copy(self):
        tpl = self._current_template()
        if tpl:
            QApplication.clipboard().setText(tpl.sample)

    def _on_load(self):
        tpl = self._current_template()
        if tpl:
            self.loadRequested.emit(tpl.sample)
            self.accept()

    def _on_load_parse(self):
        tpl = self._current_template()
        if tpl:
            self.loadAndParseRequested.emit(tpl.sample)
            self.accept()

    # ------------------------------------------------------------ manage ops

    def _create_from(self, name: str, description: str, sample: str):
        tpl = Template(
            id=f"custom_{uuid.uuid4().hex[:12]}",
            name=name,
            description=description,
            sample=sample,
            builtin=False,
        )
        self._templates.append(tpl)
        self._persist_custom()
        self._reload(select_id=tpl.id)

    def _on_new(self):
        dialog = TemplateEditDialog(self, title="New Template")
        if dialog.exec() == QDialog.Accepted:
            name, description, sample = dialog.values()
            self._create_from(name, description, sample)

    def _on_save_current(self):
        dialog = TemplateEditDialog(
            self,
            template=Template("", "", "", self._current_note_text, builtin=False),
            title="Save current note as template",
        )
        if dialog.exec() == QDialog.Accepted:
            name, description, sample = dialog.values()
            self._create_from(name, description, sample)

    def _on_edit(self):
        tpl = self._current_template()
        if not tpl or tpl.builtin:
            return
        dialog = TemplateEditDialog(self, template=tpl, title="Edit Template")
        if dialog.exec() == QDialog.Accepted:
            tpl.name, tpl.description, tpl.sample = dialog.values()
            self._persist_custom()
            self._reload(select_id=tpl.id)

    def _on_delete(self):
        tpl = self._current_template()
        if not tpl or tpl.builtin:
            return
        reply = QMessageBox.question(
            self,
            "Delete template",
            f"Delete the custom template \u201c{tpl.name}\u201d?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return
        self._templates = [t for t in self._templates if t.id != tpl.id]
        self._persist_custom()
        self._reload(select_id=None)

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

MIDDLE_PANEL_STACKED = "stacked"
MIDDLE_PANEL_WIDE = "wide"
MIDDLE_PANEL_MINIMALIST = "minimalist"

MIDDLE_PANEL_STYLE_CHOICES = [
    (MIDDLE_PANEL_STACKED, "Stacked — label above value"),
    (MIDDLE_PANEL_WIDE, "Wide — label left, value right"),
    (
        MIDDLE_PANEL_MINIMALIST,
        "Minimalist — form focus, wide layout, no side panels",
    ),
]


def middle_panel_style_from_flags(
    form_wide_layout: bool, minimalist_mode: bool
) -> str:
    if minimalist_mode:
        return MIDDLE_PANEL_MINIMALIST
    if form_wide_layout:
        return MIDDLE_PANEL_WIDE
    return MIDDLE_PANEL_STACKED


def flags_from_middle_panel_style(style: str) -> tuple[bool, bool]:
    """Return ``(form_wide_layout, minimalist_mode)``."""
    if style == MIDDLE_PANEL_MINIMALIST:
        return True, True
    if style == MIDDLE_PANEL_WIDE:
        return True, False
    return False, False


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
        confirm_dialogs: bool,
        middle_panel_style: str,
        import_panel_visible: bool,
        export_panel_visible: bool,
        remember_splitter_sizes: bool,
        editable_labels: bool,
        form_focus_on_open: bool,
        default_template_id: str,
        template_choices: List[tuple[str, str]],
        auto_parse_on_paste: bool,
        default_parse_mode: str,
        default_export_mode: str,
        export_mode_choices: List[tuple[str, str]],
    ):
        super().__init__(parent)
        self.setWindowTitle("Preferences")
        self.setMinimumSize(640, 720)
        self.resize(700, 820)

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
        self.confirm_dialogs_check = QCheckBox(
            "Show confirmation dialogs before closing tabs, clearing values, and similar actions"
        )
        self.confirm_dialogs_check.setChecked(confirm_dialogs)
        form.addRow("Confirmations", self.confirm_dialogs_check)

        self.editable_labels_check = QCheckBox(
            "Show editable label boxes (off = compact plain-text labels; Ctrl+E)"
        )
        self.editable_labels_check.setChecked(editable_labels)
        form.addRow("Editable labels", self.editable_labels_check)

        section("Layout")
        self.middle_panel_combo = QComboBox()
        for style_id, label in MIDDLE_PANEL_STYLE_CHOICES:
            self.middle_panel_combo.addItem(label, style_id)
        style_idx = self.middle_panel_combo.findData(middle_panel_style)
        if style_idx >= 0:
            self.middle_panel_combo.setCurrentIndex(style_idx)
        form.addRow("Middle panel style", self.middle_panel_combo)

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

        self.form_focus_on_open_check = QCheckBox(
            "Open in form focus mode (maximize the form; hide tabs and side panels)"
        )
        self.form_focus_on_open_check.setChecked(form_focus_on_open)
        form.addRow("Form focus", self.form_focus_on_open_check)

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

        self.middle_panel_combo.currentIndexChanged.connect(
            self._on_middle_panel_style_changed
        )
        self.import_visible_check.toggled.connect(self._on_panel_open_toggled)
        self.export_visible_check.toggled.connect(self._on_panel_open_toggled)
        self.compact_check.toggled.connect(self._update_form_focus_on_open_enabled)
        self._on_middle_panel_style_changed()

    def _update_form_focus_on_open_enabled(self) -> None:
        minimalist = self.middle_panel_combo.currentData() == MIDDLE_PANEL_MINIMALIST
        compact = self.compact_check.isChecked()
        self.form_focus_on_open_check.setEnabled(not minimalist and not compact)
        if compact:
            self.form_focus_on_open_check.setChecked(False)

    def _on_panel_open_toggled(self, checked: bool) -> None:
        if checked and self.middle_panel_combo.currentData() == MIDDLE_PANEL_MINIMALIST:
            wide_idx = self.middle_panel_combo.findData(MIDDLE_PANEL_WIDE)
            if wide_idx >= 0:
                self.middle_panel_combo.setCurrentIndex(wide_idx)

    def _on_middle_panel_style_changed(self, *_args) -> None:
        minimalist = self.middle_panel_combo.currentData() == MIDDLE_PANEL_MINIMALIST
        self.compact_check.setEnabled(not minimalist)
        if minimalist:
            self.import_visible_check.setChecked(False)
            self.export_visible_check.setChecked(False)
            self.compact_check.setChecked(False)
        self._update_form_focus_on_open_enabled()

    def values(self) -> dict:
        style = self.middle_panel_combo.currentData() or MIDDLE_PANEL_STACKED
        form_wide_layout, minimalist = flags_from_middle_panel_style(style)
        return {
            "persistent_sidebars": self.persistent_check.isChecked(),
            "compact": False if minimalist else self.compact_check.isChecked(),
            "middle_panel_style": style,
            "minimalist_mode": minimalist,
            "confirm_dialogs": self.confirm_dialogs_check.isChecked(),
            "import_panel_visible": (
                False if minimalist else self.import_visible_check.isChecked()
            ),
            "export_panel_visible": (
                False if minimalist else self.export_visible_check.isChecked()
            ),
            "remember_splitter_sizes": self.remember_splitter_check.isChecked(),
            "editable_labels": self.editable_labels_check.isChecked(),
            "form_focus_on_open": (
                self.form_focus_on_open_check.isChecked()
                and self.form_focus_on_open_check.isEnabled()
            ),
            "form_wide_layout": form_wide_layout,
            "default_template_id": self.template_combo.currentData() or "",
            "auto_parse_on_paste": self.auto_parse_check.isChecked(),
            "default_parse_mode": self.parse_mode_combo.currentData() or PARSE_MODE_PARSE,
            "default_export_mode": self.export_mode_combo.currentData() or MODE_SAME_LINE,
        }


KEYBOARD_SHORTCUT_SECTIONS: list[tuple[str, list[tuple[str, str]]]] = [
    (
        "File",
        [
            ("Ctrl+N", "Open a new note tab from the default template"),
            ("Ctrl+O", "Open a saved note file"),
            ("Ctrl+F", "Search open notes and saved .txt files (find in running notes while that view is open)"),
            ("Ctrl+S", "Save the export preview to a text file"),
            ("Ctrl+Shift+C", "Copy the export preview to the clipboard"),
            ("Ctrl+Shift+T", "Insert the current date and time at the cursor"),
            ("Ctrl+-", "Prefix \"\u2022 \" on each line of the selected text"),
            ("Ctrl+Shift+Delete", "Clear every field value (labels and rows kept)"),
            ("Ctrl+Shift+Backspace", "Clear the focused field's value only"),
            ("Ctrl+Q", "Exit the application"),
        ],
    ),
    (
        "Panels & layout",
        [
            ("Ctrl+1", "Show the Import panel (also exits form focus mode)"),
            ("Ctrl+2", "Toggle compact mode — hides the form panel (also exits form focus)"),
            ("Ctrl+3", "Show the Export panel (also exits form focus mode)"),
            ("Ctrl+Shift+2", "Toggle wide form layout (label left, value right)"),
            ("Ctrl+E", "Toggle editable field labels (plain text when off)"),
            ("Ctrl+Shift+F", "Toggle form focus mode (maximize the form editor)"),
            ("Ctrl+Shift+R", "Toggle running notes (all open notes in one document)"),
        ],
    ),
    (
        "Application",
        [
            ("Ctrl+,", "Open Preferences"),
            ("F1", "Open this keyboard shortcuts reference"),
        ],
    ),
]


class KeyboardShortcutsDialog(QDialog):
    """Scrollable reference of application keyboard shortcuts."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Keyboard Shortcuts")
        self.setMinimumSize(520, 460)
        self.resize(580, 560)

        outer = QVBoxLayout(self)

        intro = QLabel(
            "Shortcuts work from anywhere in the window, including form focus mode "
            "(when the menu bar is hidden)."
        )
        intro.setWordWrap(True)
        intro.setObjectName("StatusLabel")
        outer.addWidget(intro)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)
        body = QWidget()
        form = QVBoxLayout(body)
        form.setSpacing(16)
        form.setContentsMargins(4, 4, 4, 4)

        for section_title, entries in KEYBOARD_SHORTCUT_SECTIONS:
            heading = QLabel(section_title)
            heading.setObjectName("PanelTitle")
            form.addWidget(heading)

            rows = QFormLayout()
            rows.setSpacing(8)
            rows.setContentsMargins(0, 0, 0, 0)
            rows.setLabelAlignment(Qt.AlignLeft | Qt.AlignVCenter)
            rows.setFormAlignment(Qt.AlignLeft | Qt.AlignTop)
            for shortcut, description in entries:
                key_label = QLabel(shortcut)
                key_label.setObjectName("ShortcutKey")
                desc_label = QLabel(description)
                desc_label.setWordWrap(True)
                rows.addRow(key_label, desc_label)
            form.addLayout(rows)

        form.addStretch(1)
        scroll.setWidget(body)
        outer.addWidget(scroll, 1)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok)
        ok_btn = buttons.button(QDialogButtonBox.Ok)
        if ok_btn is not None:
            ok_btn.setText("Close")
        buttons.accepted.connect(self.accept)
        outer.addWidget(buttons)


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
    COMPACT_MIN_HEIGHT = 26
    COMPACT_HEIGHT_PAD = 4

    def __init__(self, text: str = "", parent=None):
        super().__init__(parent)
        self._compact = False
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

    def set_compact(self, compact: bool) -> None:
        if self._compact == compact:
            return
        self._compact = compact
        self._fit()

    def _fit(self, *_):
        doc = self.document()
        doc.setTextWidth(self.viewport().width())
        doc_height = doc.size().height()  # pixels for QTextEdit
        min_height = self.COMPACT_MIN_HEIGHT if self._compact else self.MIN_HEIGHT
        height_pad = self.COMPACT_HEIGHT_PAD if self._compact else 14
        target = max(min_height, int(doc_height) + self.frameWidth() * 2 + height_pad)
        if target != self.height():
            self.setFixedHeight(target)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._fit()

    def showEvent(self, event):
        super().showEvent(event)
        self._fit()


class FieldRow(QWidget):
    """A single label/value pair. Default: stacked card; wide mode: label left, value right."""

    WIDE_LABEL_STRETCH = 2
    WIDE_VALUE_STRETCH = 3
    WIDE_LABEL_MIN_WIDTH = 180
    WIDE_FOCUS_ACTIONS_WIDTH = 80

    changed = Signal()
    copied = Signal(str)

    def __init__(self, field: Field, parent=None, *, default_export_mode: str = MODE_SAME_LINE):
        super().__init__(parent)
        self.setObjectName("FieldCard")
        self._export_mode = field.export_mode or default_export_mode
        self._wide_layout = False
        self._wide_focus_actions = False
        self._labels_editable = False
        self._outer = QVBoxLayout(self)

        self.label_edit = QLineEdit(field.label)
        self.label_edit.setObjectName("FieldLabel")
        self.label_edit.setPlaceholderText("Label")
        self.label_edit.setAccessibleName("Field label")

        self.label_display = QLabel(field.label)
        self.label_display.setObjectName("FieldLabelText")
        self.label_display.setWordWrap(True)
        self.label_display.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self.label_display.setAccessibleName("Field label")

        self.format_btn = QPushButton()
        self.format_btn.setObjectName("FormatToggle")
        self.format_btn.setCheckable(True)
        self.format_btn.setChecked(self._export_mode == MODE_LABEL_BLOCK)
        self.format_btn.setAccessibleName("Toggle export format for this field")
        self.format_btn.setCursor(Qt.PointingHandCursor)
        self._sync_format_btn()

        self.copy_btn = QPushButton("\u29c9")
        self.copy_btn.setObjectName("IconButton")
        self.copy_btn.setToolTip("Copy this field's value")
        self.copy_btn.setAccessibleName("Copy field value")
        self.copy_btn.setCursor(Qt.PointingHandCursor)

        self.remove_btn = QPushButton("\u00d7")
        self.remove_btn.setObjectName("Remove")
        self.remove_btn.setToolTip("Clear this field's value")
        self.remove_btn.setAccessibleName("Clear field value")
        self.remove_btn.setCursor(Qt.PointingHandCursor)

        self.value_edit = GrowingTextEdit(field.value)
        self.value_edit.setAccessibleName("Field value")

        self.label_edit.textChanged.connect(self._on_label_changed)
        self.value_edit.textChanged.connect(self.changed)
        self.format_btn.toggled.connect(self._on_format_toggled)
        self.copy_btn.clicked.connect(self._on_copy)
        self.remove_btn.clicked.connect(self._on_clear_value)

        self._stacked_wrap = QWidget()
        self._stacked_header = QHBoxLayout()
        self._stacked_header.setSpacing(8)
        self._stacked_body = QVBoxLayout(self._stacked_wrap)
        self._stacked_body.setContentsMargins(0, 0, 0, 0)
        self._stacked_body.setSpacing(6)
        self._stacked_body.addLayout(self._stacked_header)

        self._wide_wrap = QWidget()
        self._wide_body = QHBoxLayout(self._wide_wrap)
        self._wide_body.setContentsMargins(0, 0, 0, 0)
        self._wide_body.setSpacing(8)
        self._wide_body.setAlignment(Qt.AlignTop)
        self._wide_left = QVBoxLayout()
        self._wide_left.setSpacing(4)
        self._wide_buttons = QHBoxLayout()
        self._wide_buttons.setSpacing(4)
        self._wide_left_wrap = QWidget()
        self._wide_left_wrap.setMinimumWidth(self.WIDE_LABEL_MIN_WIDTH)
        self._wide_left_wrap.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self._wide_left_wrap.setLayout(self._wide_left)

        self._wide_actions = QHBoxLayout()
        self._wide_actions.setSpacing(4)
        self._wide_actions.setContentsMargins(0, 0, 0, 0)
        self._wide_actions_wrap = QWidget()
        self._wide_actions_wrap.setFixedWidth(self.WIDE_FOCUS_ACTIONS_WIDTH)
        self._wide_actions_wrap.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Expanding)
        self._wide_actions_wrap.setLayout(self._wide_actions)

        self._outer.addWidget(self._stacked_wrap)
        self._outer.addWidget(self._wide_wrap)
        self._wide_wrap.hide()
        self._sync_value_placeholder()
        self._apply_layout_mode(False)

    def _value_placeholder(self) -> str:
        label = self.label_edit.text().strip()
        return label if label else "Value"

    def _sync_value_placeholder(self) -> None:
        self.value_edit.setPlaceholderText(self._value_placeholder())

    def _sync_label_display_alignment(self) -> None:
        if self._wide_layout and not self._labels_editable:
            self.label_display.setAlignment(Qt.AlignRight | Qt.AlignTop)
        else:
            self.label_display.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)

    def set_wide_layout(self, wide: bool) -> None:
        if self._wide_layout == wide:
            return
        self._wide_layout = wide
        self._apply_layout_mode(wide)
        self.value_edit._fit()

    def set_wide_focus_actions(self, enabled: bool) -> None:
        if self._wide_focus_actions == enabled:
            return
        self._wide_focus_actions = enabled
        if self._wide_layout:
            self._apply_layout_mode(True)

    def set_labels_editable(self, editable: bool) -> None:
        if self._labels_editable == editable:
            return
        self._labels_editable = editable
        self._apply_layout_mode(self._wide_layout)

    def _on_label_changed(self, text: str) -> None:
        if self.label_display.text() != text:
            self.label_display.setText(text)
        self._sync_value_placeholder()
        self.changed.emit()

    def _label_widget(self) -> QWidget:
        return self.label_edit if self._labels_editable else self.label_display

    def _show_field_widgets(self) -> None:
        self.value_edit.show()
        if self._wide_layout:
            self.format_btn.hide()
            if self._wide_focus_actions:
                self.copy_btn.show()
                self.remove_btn.show()
            else:
                self.copy_btn.hide()
                self.remove_btn.hide()
        else:
            self.format_btn.show()
            self.copy_btn.show()
            self.remove_btn.show()
        if self._labels_editable:
            self.label_edit.show()
            self.label_display.hide()
        else:
            self.label_display.show()
            self.label_edit.hide()

    def _apply_layout_mode(self, wide: bool) -> None:
        self._detach_field_widgets()

        if wide:
            self._outer.setContentsMargins(4, 1, 4, 1)
            self._outer.setSpacing(0)
            label_align = Qt.AlignRight if not self._labels_editable else Qt.AlignLeft
            self._wide_left.addWidget(self._label_widget(), 0, label_align)
            self._wide_body.addWidget(self._wide_left_wrap, self.WIDE_LABEL_STRETCH)
            self._wide_body.addWidget(self.value_edit, self.WIDE_VALUE_STRETCH)
            if self._wide_focus_actions:
                self._wide_actions.addStretch(1)
                self._wide_actions.addWidget(self.copy_btn)
                self._wide_actions.addWidget(self.remove_btn)
                self._wide_actions.addStretch(1)
                self._wide_body.addWidget(self._wide_actions_wrap, 0, Qt.AlignVCenter)
            self.label_display.setObjectName("FieldLabelTextWide")
            self._sync_label_display_alignment()
            self.value_edit.set_compact(True)
            self.value_edit.setObjectName("FieldValueWide")
            self._stacked_wrap.hide()
            self._wide_wrap.show()
            self._show_field_widgets()
            return

        self._outer.setContentsMargins(10, 8, 10, 10)
        self._outer.setSpacing(6)
        self._stacked_header.addWidget(self._label_widget(), 1)
        self._stacked_header.addWidget(self.format_btn)
        self._stacked_header.addWidget(self.copy_btn)
        self._stacked_header.addWidget(self.remove_btn)
        self._stacked_body.addWidget(self.value_edit)
        self.label_display.setObjectName("FieldLabelText")
        self._sync_label_display_alignment()
        self.value_edit.set_compact(False)
        self.value_edit.setObjectName("")
        self._wide_wrap.hide()
        self._stacked_wrap.show()
        self._show_field_widgets()

    def _detach_field_widgets(self) -> None:
        for widget in (
            self.label_edit,
            self.label_display,
            self.format_btn,
            self.copy_btn,
            self.remove_btn,
            self.value_edit,
        ):
            widget.setParent(self)

        while self._stacked_header.count():
            self._stacked_header.takeAt(0)
        while self._wide_buttons.count():
            self._wide_buttons.takeAt(0)
        while self._wide_left.count():
            self._wide_left.takeAt(0)
        while self._wide_actions.count():
            self._wide_actions.takeAt(0)
        if self._wide_body.indexOf(self._wide_left_wrap) >= 0:
            self._wide_body.removeWidget(self._wide_left_wrap)
        if self._wide_body.indexOf(self._wide_actions_wrap) >= 0:
            self._wide_body.removeWidget(self._wide_actions_wrap)

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

    def _on_clear_value(self):
        if not self.value_edit.toPlainText().strip():
            return
        self.clear_value()
        self.value_edit._fit()
        self.changed.emit()

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
        if self._labels_editable:
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

    def __init__(self, parent=None, current_note_text: str = "", *, confirm_dialogs: bool = True):
        super().__init__(parent)
        self._confirm_dialogs = confirm_dialogs
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
        if self._confirm_dialogs:
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

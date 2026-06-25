"""Main application window with the Import / Form / Export panels."""

from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QAction, QActionGroup, QKeySequence
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QTextEdit,
    QScrollArea,
    QSizePolicy,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from . import APP_NAME, __version__
from . import exporter, storage, themes
from .exporter import EXPORT_MODES, MODE_SAME_LINE
from .parser import Field, merge_fields, parse_notes
from .templates import DEFAULT_TEMPLATE_ID, resolve_template, template_choices
from .widgets import (
    FieldRow,
    ImportPasteEdit,
    PARSE_MODE_MERGE,
    PARSE_MODE_PARSE,
    PreferencesDialog,
    TemplatesDialog,
)

DEFAULT_SPLITTER_SIZES = [260, 760, 300]


def _panel(title: str, collapse_glyph: str | None = None):
    """Create a titled panel container.

    Returns ``(frame, content_layout, collapse_btn)``. When *collapse_glyph* is
    given, a small collapse button is added to the panel header and returned;
    otherwise the third item is ``None``.
    """
    frame = QWidget()
    frame.setObjectName("Panel")
    outer = QVBoxLayout(frame)
    outer.setContentsMargins(14, 14, 14, 14)
    outer.setSpacing(10)

    header = QHBoxLayout()
    heading = QLabel(title)
    heading.setObjectName("PanelTitle")
    header.addWidget(heading)
    header.addStretch(1)

    collapse_btn = None
    if collapse_glyph is not None:
        collapse_btn = QPushButton(collapse_glyph)
        collapse_btn.setObjectName("IconButton")
        collapse_btn.setToolTip("Collapse this panel (reopen it from the View menu)")
        collapse_btn.setCursor(Qt.PointingHandCursor)
        header.addWidget(collapse_btn)

    outer.addLayout(header)
    return frame, outer, collapse_btn


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(APP_NAME)
        self.resize(1180, 720)
        self.setMinimumSize(420, 360)  # usable in tight/narrow areas

        self.field_rows: List[FieldRow] = []
        self.current_theme = themes.THEME_SYSTEM
        self.settings: dict = {}
        self.persistent_sidebars = True
        self.compact = False
        self.confirm_clear_values = True
        self.import_panel_visible = True
        self.export_panel_visible = True
        self.remember_splitter_sizes = True
        self.default_template_id = ""
        self.auto_parse_on_paste = False
        self.default_parse_mode = PARSE_MODE_PARSE
        self.default_export_mode = MODE_SAME_LINE

        # Debounced auto-save timer.
        self._save_timer = QTimer(self)
        self._save_timer.setInterval(800)
        self._save_timer.setSingleShot(True)
        self._save_timer.timeout.connect(self._persist_draft)

        # Guards/timer for the editable live preview <-> form mirroring.
        self._updating_preview = False      # True while the form writes into the preview
        self._syncing_from_preview = False  # True while the preview rebuilds the form
        self._preview_sync_timer = QTimer(self)
        self._preview_sync_timer.setInterval(450)
        self._preview_sync_timer.setSingleShot(True)
        self._preview_sync_timer.timeout.connect(self._sync_form_from_preview)

        self._splitter_save_timer = QTimer(self)
        self._splitter_save_timer.setInterval(400)
        self._splitter_save_timer.setSingleShot(True)
        self._splitter_save_timer.timeout.connect(self._persist_splitter_sizes)

        self._last_text_focus: Optional[QWidget] = None

        self._build_ui()
        self._build_menu()
        app = QApplication.instance()
        if app is not None:
            app.focusChanged.connect(self._on_focus_changed)
        self._load_state()
        self._update_preview()
        self._update_empty_state()

    # ------------------------------------------------------------------ UI

    def _build_ui(self):
        self.import_panel = self._build_import_panel()
        self.form_panel = self._build_form_panel()
        self.export_panel = self._build_export_panel()

        self.splitter = QSplitter(Qt.Horizontal)
        self.splitter.setChildrenCollapsible(True)
        self.splitter.addWidget(self.import_panel)
        self.splitter.addWidget(self.form_panel)
        self.splitter.addWidget(self.export_panel)
        # The Form (middle) absorbs extra space; the side panels keep their size.
        self.splitter.setStretchFactor(0, 0)
        self.splitter.setStretchFactor(1, 1)
        self.splitter.setStretchFactor(2, 0)
        self.splitter.setSizes(DEFAULT_SPLITTER_SIZES)
        self.splitter.splitterMoved.connect(self._on_splitter_moved)
        for panel in (self.import_panel, self.form_panel, self.export_panel):
            panel.setMinimumWidth(0)

        # Thin "rails" on each edge that reopen a collapsed side panel. They are
        # only shown when the panel is collapsed and persistent sidebars is on.
        self.left_rail = self._make_rail("\u203a", "Reopen the Import panel")
        self.right_rail = self._make_rail("\u2039", "Reopen the Export panel")
        self.left_rail.clicked.connect(lambda: self.act_import.setChecked(True))
        self.right_rail.clicked.connect(lambda: self.act_export.setChecked(True))

        container = QWidget()
        self._central_layout = QHBoxLayout(container)
        self._central_layout.setContentsMargins(12, 12, 12, 12)
        self._central_layout.setSpacing(6)
        self._central_layout.addWidget(self.left_rail)
        self._central_layout.addWidget(self.splitter, 1)
        self._central_layout.addWidget(self.right_rail)
        self.setCentralWidget(container)

    def _make_rail(self, glyph: str, tooltip: str) -> QPushButton:
        rail = QPushButton(glyph)
        rail.setObjectName("Rail")
        rail.setToolTip(tooltip)
        rail.setCursor(Qt.PointingHandCursor)
        rail.setFixedWidth(20)
        rail.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Expanding)
        rail.setVisible(False)
        return rail

    def _build_import_panel(self) -> QWidget:
        frame, layout, self._import_collapse_btn = _panel("Import", "\u00ab")

        self.paste_box = ImportPasteEdit()
        self.paste_box.setPlaceholderText(
            "Paste raw ticket notes here, then click Parse.\n\n"
            "Examples:\n"
            "Client Name: John Doe\n"
            "Customer Name: (empty)\n"
            "TICKET ID:\nINC12345"
        )
        self.paste_box.setAccessibleName("Raw notes paste area")
        layout.addWidget(self.paste_box, 1)

        buttons = QHBoxLayout()
        self.parse_btn = QPushButton("Parse")
        self.parse_btn.setObjectName("Primary")
        self.parse_btn.setToolTip("Replace the form with fields parsed from the paste area")
        self.merge_btn = QPushButton("Merge")
        self.merge_btn.setToolTip("Add or update fields from the paste area without clearing the form")
        self.prefix_dash_btn = QPushButton("-")
        self.prefix_dash_btn.setObjectName("IconButton")
        self.prefix_dash_btn.setToolTip(
            "Prefix \"- \" on each line of the selected text"
        )
        self.prefix_dash_btn.setAccessibleName("Prefix dash on selected lines")
        self.prefix_dash_btn.setCursor(Qt.PointingHandCursor)
        self.new_btn = QPushButton("New note")
        self.new_btn.setToolTip("Clear the paste area and the form (Ctrl+N)")
        buttons.addWidget(self.parse_btn)
        buttons.addWidget(self.merge_btn)
        buttons.addWidget(self.prefix_dash_btn)
        buttons.addStretch(1)
        buttons.addWidget(self.new_btn)
        layout.addLayout(buttons)

        self.templates_btn = QPushButton("Templates\u2026")
        self.templates_btn.setToolTip("Browse built-in note templates")
        layout.addWidget(self.templates_btn)

        self.status_label = QLabel("Paste notes and click Parse to begin.")
        self.status_label.setObjectName("StatusLabel")
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)

        self.parse_btn.clicked.connect(self.on_parse)
        self.merge_btn.clicked.connect(self.on_merge)
        self.prefix_dash_btn.clicked.connect(self.on_prefix_dash_lines)
        self.new_btn.clicked.connect(self.on_new_note)
        self.templates_btn.clicked.connect(self.on_templates)
        self.paste_box.pasted.connect(self._on_import_pasted)

        return frame

    def _build_form_panel(self) -> QWidget:
        frame, layout, _ = _panel("Form")

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.rows_container = QWidget()
        self.rows_layout = QVBoxLayout(self.rows_container)
        self.rows_layout.setContentsMargins(0, 0, 0, 0)
        self.rows_layout.setSpacing(8)
        self.rows_layout.addStretch(1)
        self.scroll.setWidget(self.rows_container)

        self.empty_state = QLabel("No fields yet.\nParse a note or add a field to get started.")
        self.empty_state.setObjectName("EmptyState")
        self.empty_state.setAlignment(Qt.AlignCenter)

        layout.addWidget(self.empty_state)
        layout.addWidget(self.scroll, 1)

        form_buttons = QHBoxLayout()
        self.clear_form_btn = QPushButton("Clear values")
        self.clear_form_btn.setToolTip(
            "Empty every field's value while keeping all labels and rows"
        )
        self.clear_form_btn.clicked.connect(self.on_clear_form_values)
        self.datetime_btn = QPushButton("Date/time")
        self.datetime_btn.setToolTip(
            "Insert the current date, time, and timezone at the cursor (Ctrl+Shift+T)"
        )
        self.datetime_btn.setAccessibleName("Insert date and time")
        self.datetime_btn.clicked.connect(self.insert_datetime)
        self.add_field_btn = QPushButton("+ Add field")
        self.add_field_btn.setToolTip("Append a new empty field")
        self.add_field_btn.clicked.connect(self.on_add_field)
        form_buttons.addWidget(self.clear_form_btn)
        form_buttons.addWidget(self.datetime_btn)
        form_buttons.addStretch(1)
        form_buttons.addWidget(self.add_field_btn)
        layout.addLayout(form_buttons)

        return frame

    def _build_export_panel(self) -> QWidget:
        frame, layout, self._export_collapse_btn = _panel("Export", "\u00bb")

        controls = QHBoxLayout()
        controls.addWidget(QLabel("Format:"))
        self.format_combo = QComboBox()
        for mode_id, label in EXPORT_MODES:
            self.format_combo.addItem(label, mode_id)
        self.format_combo.setAccessibleName("Export format")
        controls.addWidget(self.format_combo, 1)
        layout.addLayout(controls)

        self.blank_check = QCheckBox("Blank line between fields")
        layout.addWidget(self.blank_check)

        layout.addWidget(QLabel("Live preview (editable):"))
        self.preview = QPlainTextEdit()
        self.preview.setToolTip(
            "Edit this text directly - your changes are mirrored back into the form."
        )
        self.preview.setAccessibleName("Export preview")
        layout.addWidget(self.preview, 1)

        out_buttons = QHBoxLayout()
        self.copy_btn = QPushButton("Copy text")
        self.copy_btn.setToolTip("Copy the preview to the clipboard")
        self.save_btn = QPushButton("Save .txt")
        self.save_btn.setObjectName("Primary")
        self.save_btn.setToolTip("Save the preview to a text file (Ctrl+S)")
        out_buttons.addWidget(self.copy_btn)
        out_buttons.addStretch(1)
        out_buttons.addWidget(self.save_btn)
        layout.addLayout(out_buttons)

        self.format_combo.currentIndexChanged.connect(self._on_export_options_changed)
        self.blank_check.stateChanged.connect(self._on_export_options_changed)
        self.preview.textChanged.connect(self._on_preview_edited)
        self.copy_btn.clicked.connect(self.on_copy)
        self.save_btn.clicked.connect(self.on_save)

        return frame

    def _build_menu(self):
        menubar = self.menuBar()

        file_menu = menubar.addMenu("&File")
        new_action = QAction("&New Note", self)
        new_action.setShortcut(QKeySequence.New)  # Ctrl+N
        new_action.triggered.connect(self.on_new_note)
        file_menu.addAction(new_action)

        save_action = QAction("&Save Export\u2026", self)
        save_action.setShortcut(QKeySequence.Save)  # Ctrl+S
        save_action.triggered.connect(self.on_save)
        file_menu.addAction(save_action)

        copy_action = QAction("&Copy Export", self)
        copy_action.setShortcut(QKeySequence("Ctrl+Shift+C"))
        copy_action.triggered.connect(self.on_copy)
        file_menu.addAction(copy_action)

        self.act_insert_datetime = QAction("Insert &date/time", self)
        self.act_insert_datetime.setShortcut(QKeySequence("Ctrl+Shift+T"))
        self.act_insert_datetime.triggered.connect(self.insert_datetime)
        file_menu.addAction(self.act_insert_datetime)
        self.addAction(self.act_insert_datetime)

        file_menu.addSeparator()
        exit_action = QAction("E&xit", self)
        exit_action.setShortcut(QKeySequence("Ctrl+Q"))
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)

        view_menu = menubar.addMenu("&View")
        theme_menu = view_menu.addMenu("&Theme")
        self.theme_group = QActionGroup(self)
        self.theme_group.setExclusive(True)
        self._theme_actions = {}
        for theme_id, label in themes.THEME_CHOICES:
            action = QAction(label, self, checkable=True)
            action.triggered.connect(lambda _=False, t=theme_id: self.set_theme(t))
            self.theme_group.addAction(action)
            theme_menu.addAction(action)
            self._theme_actions[theme_id] = action

        # Panel + preferences actions. Their shortcuts stay active because they
        # live in the Preferences menu below.
        self.act_import = QAction("Show &Import Panel", self, checkable=True)
        self.act_import.setChecked(True)
        self.act_import.setShortcut(QKeySequence("Ctrl+1"))
        self.act_import.toggled.connect(self._on_import_toggled)

        self.act_export = QAction("Show &Export Panel", self, checkable=True)
        self.act_export.setChecked(True)
        self.act_export.setShortcut(QKeySequence("Ctrl+3"))
        self.act_export.toggled.connect(self._on_export_toggled)

        self.act_compact = QAction("&Compact mode (live preview only)", self, checkable=True)
        self.act_compact.setShortcut(QKeySequence("Ctrl+2"))
        self.act_compact.setToolTip(
            "Hide the form and edit in the live preview (Ctrl+2)"
        )
        self.act_compact.toggled.connect(self._on_compact_toggled)

        self.act_prefs = QAction("&Preferences\u2026", self)
        self.act_prefs.setShortcut(QKeySequence("Ctrl+,"))
        self.act_prefs.triggered.connect(self.open_preferences)

        prefs_menu = menubar.addMenu("&Preferences")
        prefs_menu.addAction(self.act_prefs)
        prefs_menu.addSeparator()
        prefs_menu.addAction(self.act_import)
        prefs_menu.addAction(self.act_compact)
        prefs_menu.addAction(self.act_export)

        help_menu = menubar.addMenu("&Help")
        contact_action = QAction("&Request a Change / Get Help\u2026", self)
        contact_action.triggered.connect(self._show_contact)
        help_menu.addAction(contact_action)
        help_menu.addSeparator()
        about_action = QAction("&About", self)
        about_action.triggered.connect(self._show_about)
        help_menu.addAction(about_action)

        self._import_collapse_btn.clicked.connect(lambda: self.act_import.setChecked(False))
        self._export_collapse_btn.clicked.connect(lambda: self.act_export.setChecked(False))

        # Version shown on the far right of the menu-bar row.
        self.version_label = QLabel(f"v{__version__}")
        self.version_label.setObjectName("VersionLabel")
        self.version_label.setToolTip("Version")
        menubar.setCornerWidget(self.version_label, Qt.TopRightCorner)

    # ------------------------------------------------------------- panels

    def _on_import_toggled(self, visible: bool):
        self.import_panel.setVisible(visible)
        self._update_rails()

    def _on_export_toggled(self, visible: bool):
        self.export_panel.setVisible(visible)
        self._update_rails()

    def _update_rails(self):
        # Use the toggle state (not isVisible(), which is False before the
        # window is first shown and would wrongly show the rails at startup).
        self.left_rail.setVisible(
            self.persistent_sidebars and not self.act_import.isChecked()
        )
        self.right_rail.setVisible(
            self.persistent_sidebars and not self.act_export.isChecked()
        )

    def open_preferences(self):
        dialog = PreferencesDialog(
            self,
            persistent_sidebars=self.persistent_sidebars,
            compact=self.compact,
            confirm_clear_values=self.confirm_clear_values,
            import_panel_visible=self.import_panel_visible,
            export_panel_visible=self.export_panel_visible,
            remember_splitter_sizes=self.remember_splitter_sizes,
            default_template_id=self.default_template_id,
            template_choices=template_choices(),
            auto_parse_on_paste=self.auto_parse_on_paste,
            default_parse_mode=self.default_parse_mode,
            default_export_mode=self.default_export_mode,
            export_mode_choices=EXPORT_MODES,
        )
        if dialog.exec() != QDialog.Accepted:
            return
        values = dialog.values()
        self.persistent_sidebars = values["persistent_sidebars"]
        self.compact = values["compact"]
        self.confirm_clear_values = values["confirm_clear_values"]
        self.import_panel_visible = values["import_panel_visible"]
        self.export_panel_visible = values["export_panel_visible"]
        self.remember_splitter_sizes = values["remember_splitter_sizes"]
        self.default_template_id = values["default_template_id"]
        self.auto_parse_on_paste = values["auto_parse_on_paste"]
        self.default_parse_mode = values["default_parse_mode"]
        self.default_export_mode = values["default_export_mode"]
        self.act_import.setChecked(self.import_panel_visible)
        self.act_export.setChecked(self.export_panel_visible)
        self.act_compact.blockSignals(True)
        self.act_compact.setChecked(self.compact)
        self.act_compact.blockSignals(False)
        self._apply_default_export_mode_from_settings()
        if not self.remember_splitter_sizes:
            self.splitter.setSizes(DEFAULT_SPLITTER_SIZES)
        self._apply_density()
        self._apply_compact_layout()
        self.set_theme(self.current_theme)  # re-apply stylesheet + save
        self._update_rails()
        self._save_settings()

    def _apply_density(self):
        margin = 4 if self.compact else 12
        self._central_layout.setContentsMargins(margin, margin, margin, margin)

    def _apply_compact_layout(self):
        """Compact mode hides the form and uses the export live preview as the editor."""
        if self.compact:
            self.form_panel.hide()
            if not self.export_panel.isVisible():
                self.act_export.blockSignals(True)
                self.act_export.setChecked(True)
                self.act_export.blockSignals(False)
                self.export_panel.setVisible(True)
            self.splitter.setStretchFactor(0, 0)
            self.splitter.setStretchFactor(1, 0)
            self.splitter.setStretchFactor(2, 1)
            sizes = self.splitter.sizes()
            total = max(sum(sizes), 600)
            import_w = min(max(sizes[0], 180), 280) if sizes[0] > 0 else 220
            self.splitter.setSizes([import_w, 0, total - import_w])
            self._update_preview()
        else:
            self.form_panel.show()
            self.splitter.setStretchFactor(0, 0)
            self.splitter.setStretchFactor(1, 1)
            self.splitter.setStretchFactor(2, 0)
            self._apply_splitter_sizes()

    def _on_compact_toggled(self, checked: bool):
        self.compact = checked
        self._apply_density()
        self._apply_compact_layout()
        self._save_settings()
        if checked:
            self._set_status("Compact mode on — edit in the live preview.")
        else:
            self._set_status("Compact mode off — form visible.")

    def _load_preferences_from_settings(self):
        s = self.settings
        self.persistent_sidebars = bool(s.get("persistent_sidebars", True))
        self.compact = bool(s.get("compact", False))
        self.confirm_clear_values = bool(s.get("confirm_clear_values", True))
        self.import_panel_visible = bool(s.get("import_panel_visible", True))
        self.export_panel_visible = bool(s.get("export_panel_visible", True))
        self.remember_splitter_sizes = bool(s.get("remember_splitter_sizes", True))
        self.default_template_id = s.get("default_template_id", DEFAULT_TEMPLATE_ID)
        self.auto_parse_on_paste = bool(s.get("auto_parse_on_paste", False))
        self.default_parse_mode = s.get("default_parse_mode", PARSE_MODE_PARSE)
        self.default_export_mode = s.get("default_export_mode", MODE_SAME_LINE)

    def _save_settings(self):
        self.settings.update({
            "theme": self.current_theme,
            "persistent_sidebars": self.persistent_sidebars,
            "compact": self.compact,
            "confirm_clear_values": self.confirm_clear_values,
            "import_panel_visible": self.import_panel_visible,
            "export_panel_visible": self.export_panel_visible,
            "remember_splitter_sizes": self.remember_splitter_sizes,
            "default_template_id": self.default_template_id,
            "auto_parse_on_paste": self.auto_parse_on_paste,
            "default_parse_mode": self.default_parse_mode,
            "default_export_mode": self.default_export_mode,
        })
        if self.remember_splitter_sizes:
            self.settings["splitter_sizes"] = self.splitter.sizes()
        storage.save_settings(self.settings)

    def _apply_panel_visibility(self):
        self.act_import.blockSignals(True)
        self.act_export.blockSignals(True)
        self.act_import.setChecked(self.import_panel_visible)
        self.act_export.setChecked(self.export_panel_visible)
        self.act_import.blockSignals(False)
        self.act_export.blockSignals(False)
        self.import_panel.setVisible(self.import_panel_visible)
        self.export_panel.setVisible(self.export_panel_visible)

    def _apply_splitter_sizes(self):
        if not self.remember_splitter_sizes:
            self.splitter.setSizes(DEFAULT_SPLITTER_SIZES)
            return
        sizes = self.settings.get("splitter_sizes")
        if isinstance(sizes, list) and len(sizes) == 3:
            self.splitter.setSizes(sizes)
        else:
            self.splitter.setSizes(DEFAULT_SPLITTER_SIZES)

    def _on_splitter_moved(self, *_):
        if self.remember_splitter_sizes:
            self._splitter_save_timer.start()

    def _persist_splitter_sizes(self):
        if not self.remember_splitter_sizes or self.compact:
            return
        self.settings["splitter_sizes"] = self.splitter.sizes()
        storage.save_settings(self.settings)

    def _apply_default_export_mode_from_settings(self):
        idx = self.format_combo.findData(self.default_export_mode)
        if idx >= 0:
            self.format_combo.setCurrentIndex(idx)

    def _run_default_parse(self):
        if self.default_parse_mode == PARSE_MODE_MERGE:
            self.on_merge()
        else:
            self.on_parse()

    def _apply_template(self, template_id: str) -> bool:
        tpl = resolve_template(template_id)
        if tpl is None:
            return False
        self.paste_box.setPlainText(tpl.sample)
        self._run_default_parse()
        return True

    def _apply_default_template(self) -> bool:
        if not self.default_template_id:
            return False
        return self._apply_template(self.default_template_id)

    def _on_import_pasted(self):
        if self.auto_parse_on_paste:
            self._run_default_parse()

    def _on_focus_changed(self, _old: QWidget, new: QWidget):
        if isinstance(new, (QLineEdit, QPlainTextEdit, QTextEdit)):
            self._last_text_focus = new

    def _datetime_stamp(self) -> str:
        now = datetime.now().astimezone()
        tz_label = now.strftime("%Z").strip()
        if not tz_label:
            tz_label = now.strftime("%z")
        return f"{now.strftime('%Y-%m-%d %H:%M')} {tz_label}"

    def _text_target_for_datetime(self) -> Optional[QWidget]:
        focused = self.focusWidget()
        if isinstance(focused, (QLineEdit, QPlainTextEdit, QTextEdit)):
            return focused
        if self._last_text_focus is not None:
            return self._last_text_focus
        return self.paste_box

    def _insert_text_at_cursor(self, widget: QWidget, text: str):
        if isinstance(widget, QLineEdit):
            widget.insert(text)
        elif isinstance(widget, QPlainTextEdit):
            widget.insertPlainText(text)
        elif isinstance(widget, QTextEdit):
            widget.textCursor().insertText(text)

    def insert_datetime(self):
        target = self._text_target_for_datetime()
        if target is None:
            return
        stamp = self._datetime_stamp()
        self._insert_text_at_cursor(target, stamp)
        self._schedule_save()
        self._set_status(f"Inserted {stamp}.")

    # -------------------------------------------------------------- actions

    def on_prefix_dash_lines(self):
        cursor = self.paste_box.textCursor()
        if not cursor.hasSelection():
            self._set_status('Select text in the paste area, then click Prefix "-".')
            return

        # QPlainTextEdit uses U+2029 between lines in selectedText().
        raw = cursor.selectedText().replace("\u2029", "\n")
        prefixed: list[str] = []
        changed = 0
        for line in raw.splitlines():
            stripped = line.lstrip()
            if not stripped:
                prefixed.append(line)
                continue
            if stripped.startswith("-"):
                prefixed.append(line)
                continue
            indent = line[: len(line) - len(stripped)]
            prefixed.append(f"{indent}- {stripped}")
            changed += 1

        cursor.insertText("\n".join(prefixed))
        self._schedule_save()
        if changed:
            self._set_status(f'Prefixed {changed} line{"s" if changed != 1 else ""} with "-".')
        else:
            self._set_status("Selected lines already start with \"-\".")

    def on_parse(self):
        fields = parse_notes(self.paste_box.toPlainText())
        self._set_fields(fields)
        self._set_status(f"Parsed {len(fields)} field{'s' if len(fields) != 1 else ''}.")
        self._schedule_save()

    def on_merge(self):
        incoming = parse_notes(self.paste_box.toPlainText())
        if not incoming:
            self._set_status("Nothing to merge - the paste area has no recognisable fields.")
            return
        merged, added, updated = merge_fields(self.collect_fields(), incoming)
        self._set_fields(merged)
        self._set_status(f"Merged: {added} added, {updated} updated.")
        self._schedule_save()

    def on_new_note(self):
        if self.collect_fields() or self.paste_box.toPlainText().strip():
            reply = QMessageBox.question(
                self,
                "New Note",
                "Clear the paste area and the form?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if reply != QMessageBox.Yes:
                return
        self.paste_box.clear()
        self._set_fields([])
        self._apply_default_export_mode_from_settings()
        if self._apply_template(DEFAULT_TEMPLATE_ID):
            self._set_status("Started a new note from the default template.")
        else:
            self._set_status("Started a new note.")
        self._schedule_save()
        self.paste_box.setFocus()

    def on_add_field(self):
        self._add_row(Field("", ""))
        self._update_empty_state()
        self._update_preview()
        self.field_rows[-1].focus_label()
        self._schedule_save()

    def on_clear_form_values(self):
        if not self.field_rows:
            self._set_status("No fields to clear.")
            return
        has_values = any(
            row.to_field().value.strip() for row in self.field_rows
        )
        if has_values and self.confirm_clear_values:
            reply = QMessageBox.question(
                self,
                "Clear values",
                "Clear every field's value?\n\nField labels and rows will be kept.",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if reply != QMessageBox.Yes:
                return
        for row in self.field_rows:
            row.clear_value()
        self._update_preview()
        self._schedule_save()
        n = len(self.field_rows)
        self._set_status(
            f"Cleared values in {n} field{'s' if n != 1 else ''}. Labels kept."
        )

    def on_templates(self):
        note_text = self.preview.toPlainText()
        if not note_text.strip():
            note_text = self.paste_box.toPlainText()
        dialog = TemplatesDialog(self, current_note_text=note_text)
        dialog.loadRequested.connect(self._load_template_text)
        dialog.loadAndParseRequested.connect(self._load_and_parse_template_text)
        dialog.exec()

    def _load_template_text(self, text: str):
        self.paste_box.setPlainText(text)
        self._set_status("Template loaded into the paste area. Click Parse to build the form.")
        self.paste_box.setFocus()

    def _load_and_parse_template_text(self, text: str):
        self.paste_box.setPlainText(text)
        self.on_parse()

    def on_copy(self):
        text = self.preview.toPlainText()
        QApplication.clipboard().setText(text)
        self._set_status("Export copied to clipboard.")

    def on_save(self):
        text = self.preview.toPlainText()
        path, _ = QFileDialog.getSaveFileName(
            self, "Save notes as text", "notes.txt", "Text files (*.txt);;All files (*.*)"
        )
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(text)
            self._set_status(f"Saved to {path}")
        except OSError as exc:
            QMessageBox.critical(self, "Save failed", f"Could not save the file:\n{exc}")

    # ---------------------------------------------------------------- theme

    def set_theme(self, theme_id: str):
        self.current_theme = theme_id
        app = QApplication.instance()
        if app is not None:
            app.setStyleSheet(themes.build_stylesheet(theme_id, compact=False))
        action = self._theme_actions.get(theme_id)
        if action and not action.isChecked():
            action.setChecked(True)
        self._save_settings()

    # ----------------------------------------------------------- form model

    def _add_row(self, field: Field):
        row = FieldRow(field, default_export_mode=self._current_export_mode())
        row.changed.connect(self._on_row_changed)
        row.removeRequested.connect(self._remove_row)
        row.copied.connect(self._on_row_copied)
        # Insert before the trailing stretch item.
        self.rows_layout.insertWidget(self.rows_layout.count() - 1, row)
        self.field_rows.append(row)

    def _remove_row(self, row: FieldRow):
        if row in self.field_rows:
            self.field_rows.remove(row)
        self.rows_layout.removeWidget(row)
        row.deleteLater()
        self._update_empty_state()
        self._update_preview()
        self._schedule_save()

    def _set_fields(self, fields: List[Field]):
        for row in list(self.field_rows):
            self.rows_layout.removeWidget(row)
            row.deleteLater()
        self.field_rows.clear()
        for field in fields:
            self._add_row(field)
        self._update_empty_state()
        self._update_preview()

    def collect_fields(self) -> List[Field]:
        fields = []
        for row in self.field_rows:
            f = row.to_field()
            if f.label.strip() or f.value.strip():
                fields.append(f)
        return fields

    def _on_row_changed(self):
        self._update_preview()
        self._schedule_save()

    def _on_row_copied(self, label: str):
        self._set_status(f"Copied value of '{label}' to clipboard.")

    def _update_empty_state(self):
        has_rows = bool(self.field_rows)
        self.empty_state.setVisible(not has_rows)
        self.scroll.setVisible(has_rows)

    # ------------------------------------------------------------- preview

    def _on_export_options_changed(self, *_):
        self._update_preview()
        self._schedule_save()

    def _current_export_mode(self) -> str:
        return self.format_combo.currentData() or MODE_SAME_LINE

    def _update_preview(self):
        # While the user is editing the preview to drive the form, don't write the
        # reformatted text back (it would fight the cursor and lose in-progress edits).
        if self._syncing_from_preview:
            return
        text = exporter.format_output(
            self.collect_fields(),
            mode=self._current_export_mode(),
            blank_between=self.blank_check.isChecked(),
        )
        self._updating_preview = True
        # Preserve the caret position across the programmatic refresh.
        cursor = self.preview.textCursor()
        pos = cursor.position()
        self.preview.setPlainText(text)
        cursor = self.preview.textCursor()
        cursor.setPosition(min(pos, len(text)))
        self.preview.setTextCursor(cursor)
        self._updating_preview = False

    def _on_preview_edited(self):
        # Ignore programmatic refreshes; only react to genuine user typing.
        if self._updating_preview:
            return
        self._preview_sync_timer.start()

    def _sync_form_from_preview(self):
        self._syncing_from_preview = True
        try:
            fields = parse_notes(self.preview.toPlainText())
            self._set_fields(fields)
        finally:
            self._syncing_from_preview = False
        n = len(fields)
        if self.compact:
            self._set_status(
                f"Note updated ({n} field{'s' if n != 1 else ''})."
            )
        else:
            self._set_status(
                f"Form updated from preview ({n} field{'s' if n != 1 else ''})."
            )
        self._schedule_save()

    def _set_status(self, message: str):
        self.status_label.setText(message)

    # --------------------------------------------------------- persistence

    def _schedule_save(self):
        self._save_timer.start()

    def _persist_draft(self):
        storage.save_draft(
            self.collect_fields(),
            self.paste_box.toPlainText(),
            self._current_export_mode(),
            self.blank_check.isChecked(),
        )

    def _load_state(self):
        self.settings = storage.load_settings()
        self._load_preferences_from_settings()
        self.act_compact.blockSignals(True)
        self.act_compact.setChecked(self.compact)
        self.act_compact.blockSignals(False)
        theme = self.settings.get("theme", themes.THEME_SYSTEM)
        self._apply_density()
        self._apply_panel_visibility()
        self._apply_splitter_sizes()
        self._apply_compact_layout()
        self.set_theme(theme)
        self._update_rails()

        draft = storage.load_draft()
        self.paste_box.setPlainText(draft.get("raw_import", ""))

        mode = draft.get("export_mode") or self.default_export_mode
        idx = self.format_combo.findData(mode)
        if idx >= 0:
            self.format_combo.setCurrentIndex(idx)
        blank = draft.get("blank_between")
        if blank is not None:
            self.blank_check.setChecked(bool(blank))

        fields = draft.get("fields", [])
        if fields:
            self._set_fields(fields)
            self._set_status(f"Restored draft with {len(fields)} field(s).")
        elif not draft.get("raw_import", "").strip():
            if self._apply_default_template():
                self._set_status("Loaded the default template.")
            else:
                self._set_fields([])
        else:
            self._set_fields([])

    # -------------------------------------------------------------- dialogs

    def _show_about(self):
        from . import __version__

        QMessageBox.about(
            self,
            f"About {APP_NAME}",
            f"<b>{APP_NAME}</b> v{__version__}<br><br>"
            "Parse messy plain-text ticket notes into an editable form, "
            "then export clean plain text.<br><br>"
            "Created by <b>Adam Torres</b><br>"
            "Software System Technologist Intern 2026<br>"
            '<a href="https://www.linkedin.com/in/adam-venegas-torres/">'
            "linkedin.com/in/adam-venegas-torres</a><br>"
            '<a href="https://github.com/Monotonality/SST-Note-System">'
            "github.com/Monotonality/SST-Note-System</a><br><br>"
            f"Drafts are saved to:<br><code>{storage.app_data_dir()}</code>",
        )

    def _show_contact(self):
        box = QMessageBox(self)
        box.setWindowTitle("Request a Change / Get Help")
        box.setTextFormat(Qt.RichText)
        box.setText(
            f"<b>{APP_NAME}</b> support<br><br>"
            "For change requests and assistance, contact:<br>"
            '<a href="mailto:adam.torres@motorolasolutions.com">'
            "adam.torres@motorolasolutions.com</a>"
        )
        box.setIcon(QMessageBox.Information)
        box.exec()

    # --------------------------------------------------------------- events

    def closeEvent(self, event):
        self._persist_draft()
        super().closeEvent(event)

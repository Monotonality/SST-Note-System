"""Main application window with the Import / Form / Export panels."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import List, Optional

from PySide6.QtCore import QEvent, Qt, QTimer
from PySide6.QtGui import QAction, QActionGroup, QKeySequence, QTextCursor, QTextDocument
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QDialog,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QTextEdit,
    QScrollArea,
    QSizePolicy,
    QSplitter,
    QTabBar,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from . import APP_NAME, __version__
from . import exporter, running_notes, storage, themes
from .exporter import EXPORT_MODES, MODE_SAME_LINE
from .parser import Field, merge_fields, parse_notes
from .templates import DEFAULT_TEMPLATE_ID, resolve_template, template_choices
from .widgets import (
    FieldRow,
    ImportPasteEdit,
    KeyboardShortcutsDialog,
    MIDDLE_PANEL_MINIMALIST,
    MIDDLE_PANEL_STACKED,
    MIDDLE_PANEL_WIDE,
    flags_from_middle_panel_style,
    middle_panel_style_from_flags,
    PARSE_MODE_MERGE,
    PARSE_MODE_PARSE,
    PreferencesDialog,
    TemplatesDialog,
)

DEFAULT_SPLITTER_SIZES = [260, 760, 300]
MIN_SIDE_PANEL_WIDTH = 40


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

    header_host = QWidget()
    header_host.setLayout(header)
    outer.addWidget(header_host)
    return frame, outer, collapse_btn, header_host


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
        self.form_wide_layout = False
        self.middle_panel_style = MIDDLE_PANEL_STACKED
        self.editable_labels = False
        self.minimalist_mode = False
        self.form_focus_on_open = False
        self.confirm_dialogs = True
        self.import_panel_visible = True
        self.export_panel_visible = True
        self.remember_splitter_sizes = True
        self.default_template_id = ""
        self.auto_parse_on_paste = False
        self.default_parse_mode = PARSE_MODE_PARSE
        self.default_export_mode = MODE_SAME_LINE
        self.form_focus_mode = False
        self._pre_focus_state: dict = {}
        self.running_notes_mode = False
        self._search_hits: List[storage.SearchHit] = []

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

        self._search_timer = QTimer(self)
        self._search_timer.setInterval(220)
        self._search_timer.setSingleShot(True)
        self._search_timer.timeout.connect(self._run_search)

        self._running_notes_sync_timer = QTimer(self)
        self._running_notes_sync_timer.setInterval(500)
        self._running_notes_sync_timer.setSingleShot(True)
        self._running_notes_sync_timer.timeout.connect(self._sync_from_running_notes)
        self._updating_running_notes = False

        self._splitter_save_timer = QTimer(self)
        self._splitter_save_timer.setInterval(400)
        self._splitter_save_timer.setSingleShot(True)
        self._splitter_save_timer.timeout.connect(self._persist_splitter_sizes)

        self._last_text_focus: Optional[QWidget] = None
        self._notes: List[storage.NoteState] = []
        self._switching_tabs = False
        self._reordering_tabs = False

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
        self._central_layout = QVBoxLayout(container)
        self._central_layout.setContentsMargins(12, 12, 12, 12)
        self._central_layout.setSpacing(8)

        self.tab_row_widget = QWidget()
        tab_row = QHBoxLayout(self.tab_row_widget)
        tab_row.setContentsMargins(0, 0, 0, 0)
        tab_row.setSpacing(6)
        self.note_tab_bar = QTabBar()
        self.note_tab_bar.setObjectName("NoteTabBar")
        self.note_tab_bar.setAccessibleName("Open notes")
        self.note_tab_bar.setMovable(True)
        self.note_tab_bar.setExpanding(False)
        self.note_tab_bar.currentChanged.connect(self._on_note_tab_changed)
        self.note_tab_bar.tabMoved.connect(self._on_note_tab_moved)
        tab_row.addWidget(self.note_tab_bar)

        self.add_note_tab_btn = QPushButton("+")
        self.add_note_tab_btn.setObjectName("IconButton")
        self.add_note_tab_btn.setToolTip("Open a new note tab")
        self.add_note_tab_btn.setAccessibleName("New note tab")
        self.add_note_tab_btn.setFixedWidth(28)
        self.add_note_tab_btn.clicked.connect(self.on_new_note)
        tab_row.addWidget(self.add_note_tab_btn)

        self.search_toggle_btn = QPushButton("Search")
        self.search_toggle_btn.setToolTip("Search open notes and saved .txt files (Ctrl+F)")
        self.search_toggle_btn.setAccessibleName("Toggle note search")
        self.search_toggle_btn.setCheckable(True)
        self.search_toggle_btn.clicked.connect(self._on_search_toggle_clicked)
        tab_row.addWidget(self.search_toggle_btn)

        self.running_notes_btn = QPushButton("Running notes")
        self.running_notes_btn.setToolTip(
            "Edit all open notes as one continuous document (Ctrl+Shift+R)"
        )
        self.running_notes_btn.setAccessibleName("Toggle running notes view")
        self.running_notes_btn.setCheckable(True)
        self.running_notes_btn.clicked.connect(self._on_running_notes_btn_clicked)
        tab_row.addWidget(self.running_notes_btn)
        tab_row.addStretch(1)
        self._central_layout.addWidget(self.tab_row_widget)

        self.search_panel = self._build_search_panel()
        self.search_panel.setVisible(False)
        self._central_layout.addWidget(self.search_panel)

        content_row = QWidget()
        content_layout = QHBoxLayout(content_row)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(6)
        content_layout.addWidget(self.left_rail)
        content_layout.addWidget(self.splitter, 1)
        content_layout.addWidget(self.right_rail)
        self._central_layout.addWidget(content_row, 1)
        self._content_row = content_row

        self.running_notes_panel = self._build_running_notes_panel()
        self.running_notes_panel.setVisible(False)
        self._central_layout.addWidget(self.running_notes_panel, 1)
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

    def _build_search_panel(self) -> QWidget:
        frame = QFrame()
        frame.setObjectName("SearchPanel")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(6)

        row = QHBoxLayout()
        row.setSpacing(8)
        self.search_input = QLineEdit()
        self.search_input.setObjectName("SearchInput")
        self.search_input.setPlaceholderText(
            "Search open notes and saved .txt files…"
        )
        self.search_input.setAccessibleName("Note search")
        self.search_input.setClearButtonEnabled(True)
        self.search_input.textChanged.connect(self._on_search_text_changed)
        self.search_input.returnPressed.connect(self._activate_first_search_hit)
        row.addWidget(self.search_input, 1)

        self.search_close_btn = QPushButton("\u00d7")
        self.search_close_btn.setObjectName("IconButton")
        self.search_close_btn.setToolTip("Close search")
        self.search_close_btn.setAccessibleName("Close search")
        self.search_close_btn.clicked.connect(self._hide_search_panel)
        row.addWidget(self.search_close_btn)
        layout.addLayout(row)

        self.search_status = QLabel("Type to search all notes.")
        self.search_status.setObjectName("StatusLabel")
        layout.addWidget(self.search_status)

        self.search_results = QListWidget()
        self.search_results.setObjectName("SearchResults")
        self.search_results.setAccessibleName("Search results")
        self.search_results.setMaximumHeight(180)
        self.search_results.itemActivated.connect(self._on_search_result_activated)
        self.search_results.itemClicked.connect(self._on_search_result_activated)
        layout.addWidget(self.search_results)

        # Esc closes the pop-down when focus is in the search UI.
        for widget in (self.search_input, self.search_results):
            widget.installEventFilter(self)
        return frame

    def _build_running_notes_panel(self) -> QWidget:
        frame, layout, _, header = _panel("Running notes")
        self.running_notes_header = header
        hint = QLabel(
            "All open notes in one document. Edits sync back to each note "
            "(and its saved .txt file when one is linked). Keep the "
            "<<<NOTE:…>>> markers so sections stay mapped."
        )
        hint.setObjectName("StatusLabel")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        find_row = QHBoxLayout()
        find_row.setSpacing(8)
        self.running_notes_find_input = QLineEdit()
        self.running_notes_find_input.setObjectName("SearchInput")
        self.running_notes_find_input.setPlaceholderText(
            "Find in running notes…"
        )
        self.running_notes_find_input.setAccessibleName("Find in running notes")
        self.running_notes_find_input.setClearButtonEnabled(True)
        self.running_notes_find_input.textChanged.connect(
            self._on_running_notes_find_text_changed
        )
        find_row.addWidget(self.running_notes_find_input, 1)

        self.running_notes_find_prev_btn = QPushButton("Prev")
        self.running_notes_find_prev_btn.setToolTip("Previous match (Shift+Enter)")
        self.running_notes_find_prev_btn.setAccessibleName("Previous match")
        self.running_notes_find_prev_btn.clicked.connect(
            self._find_prev_in_running_notes
        )
        find_row.addWidget(self.running_notes_find_prev_btn)

        self.running_notes_find_next_btn = QPushButton("Next")
        self.running_notes_find_next_btn.setToolTip("Next match (Enter)")
        self.running_notes_find_next_btn.setAccessibleName("Next match")
        self.running_notes_find_next_btn.clicked.connect(
            self._find_next_in_running_notes
        )
        find_row.addWidget(self.running_notes_find_next_btn)

        self.running_notes_find_status = QLabel("")
        self.running_notes_find_status.setObjectName("StatusLabel")
        self.running_notes_find_status.setMinimumWidth(90)
        find_row.addWidget(self.running_notes_find_status)
        layout.addLayout(find_row)

        self.running_notes_edit = QPlainTextEdit()
        self.running_notes_edit.setObjectName("RunningNotesEdit")
        self.running_notes_edit.setAccessibleName("Running notes editor")
        self.running_notes_edit.setPlaceholderText(
            "Open notes will appear here as one continuous document."
        )
        self.running_notes_edit.textChanged.connect(self._on_running_notes_edited)
        layout.addWidget(self.running_notes_edit, 1)

        buttons = QHBoxLayout()
        self.running_notes_refresh_btn = QPushButton("Refresh from notes")
        self.running_notes_refresh_btn.setToolTip(
            "Rebuild this document from the current open notes"
        )
        self.running_notes_refresh_btn.clicked.connect(self._refresh_running_notes_view)
        self.running_notes_exit_btn = QPushButton("Exit running notes")
        self.running_notes_exit_btn.setObjectName("Primary")
        self.running_notes_exit_btn.setToolTip("Return to the normal note editor")
        self.running_notes_exit_btn.clicked.connect(
            lambda: self.act_running_notes.setChecked(False)
        )
        buttons.addWidget(self.running_notes_refresh_btn)
        buttons.addStretch(1)
        buttons.addWidget(self.running_notes_exit_btn)
        layout.addLayout(buttons)

        self.running_notes_find_input.installEventFilter(self)
        return frame

    def _build_import_panel(self) -> QWidget:
        frame, layout, self._import_collapse_btn, _ = _panel("Import", "\u00ab")

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
        self.prefix_bullet_btn = QPushButton("\u2022")
        self.prefix_bullet_btn.setObjectName("IconButton")
        self.prefix_bullet_btn.setToolTip(
            "Prefix \"\u2022 \" on each line of the selected text"
        )
        self.prefix_bullet_btn.setAccessibleName("Prefix bullet on selected lines")
        self.prefix_bullet_btn.setCursor(Qt.PointingHandCursor)
        self.new_btn = QPushButton("New note")
        self.new_btn.setToolTip("Open a new note tab with the default template (Ctrl+N)")
        buttons.addWidget(self.parse_btn)
        buttons.addWidget(self.merge_btn)
        buttons.addWidget(self.prefix_bullet_btn)
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
        self.prefix_bullet_btn.clicked.connect(self.on_prefix_bullet_lines_import)
        self.new_btn.clicked.connect(self.on_new_note)
        self.templates_btn.clicked.connect(self.on_templates)
        self.paste_box.pasted.connect(self._on_import_pasted)

        return frame

    def _build_form_panel(self) -> QWidget:
        frame, layout, _, self.form_header_widget = _panel("Form")

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
        self.form_toolbar = QWidget()
        self.form_toolbar.setLayout(form_buttons)
        layout.addWidget(self.form_toolbar)

        focus_buttons = QHBoxLayout()
        self.focus_clear_btn = QPushButton("Clear values")
        self.focus_clear_btn.setToolTip(
            "Empty every field's value while keeping all labels and rows"
        )
        self.focus_clear_btn.clicked.connect(self.on_clear_form_values)
        self.focus_new_note_btn = QPushButton("New note")
        self.focus_new_note_btn.setToolTip(
            "Open a new note tab with the default template (Ctrl+N)"
        )
        self.focus_new_note_btn.clicked.connect(self.on_new_note)
        self.focus_bullet_btn = QPushButton("\u2022")
        self.focus_bullet_btn.setObjectName("IconButton")
        self.focus_bullet_btn.setToolTip(
            "Prefix \"\u2022 \" on each line of the selected text (Ctrl+-)"
        )
        self.focus_bullet_btn.setAccessibleName("Prefix bullet on selected lines")
        self.focus_bullet_btn.setCursor(Qt.PointingHandCursor)
        self.focus_bullet_btn.clicked.connect(self.on_prefix_bullet_shortcut)
        self.focus_datetime_btn = QPushButton("Date/time")
        self.focus_datetime_btn.setToolTip(
            "Insert the current date, time, and timezone at the cursor (Ctrl+Shift+T)"
        )
        self.focus_datetime_btn.setAccessibleName("Insert date and time")
        self.focus_datetime_btn.clicked.connect(self.insert_datetime)
        self.focus_copy_btn = QPushButton("Copy")
        self.focus_copy_btn.setToolTip("Copy the export preview to the clipboard")
        self.focus_copy_btn.clicked.connect(self.on_copy)
        self.focus_save_btn = QPushButton("Save .txt")
        self.focus_save_btn.setObjectName("Primary")
        self.focus_save_btn.setToolTip("Save the export preview to a text file (Ctrl+S)")
        self.focus_save_btn.clicked.connect(self.on_save)
        focus_buttons.addWidget(self.focus_clear_btn)
        focus_buttons.addWidget(self.focus_new_note_btn)
        focus_buttons.addWidget(self.focus_bullet_btn)
        focus_buttons.addWidget(self.focus_datetime_btn)
        focus_buttons.addStretch(1)
        focus_buttons.addWidget(self.focus_copy_btn)
        focus_buttons.addWidget(self.focus_save_btn)
        self.form_focus_toolbar = QWidget()
        self.form_focus_toolbar.setLayout(focus_buttons)
        self.form_focus_toolbar.setVisible(False)
        layout.addWidget(self.form_focus_toolbar)

        return frame

    def _build_export_panel(self) -> QWidget:
        frame, layout, self._export_collapse_btn, _ = _panel("Export", "\u00bb")

        layout.addWidget(QLabel("Live preview (editable):"))
        self.preview = QPlainTextEdit()
        self.preview.setToolTip(
            "Edit this text directly - your changes are mirrored back into the form."
        )
        self.preview.setAccessibleName("Export preview")
        layout.addWidget(self.preview, 1)

        out_buttons = QHBoxLayout()
        self.copy_btn = QPushButton("Copy")
        self.copy_btn.setToolTip("Copy the preview to the clipboard")
        self.prefix_bullet_export_btn = QPushButton("\u2022")
        self.prefix_bullet_export_btn.setObjectName("IconButton")
        self.prefix_bullet_export_btn.setToolTip(
            "Prefix \"\u2022 \" on each line of the selected text"
        )
        self.prefix_bullet_export_btn.setAccessibleName("Prefix bullet on selected lines")
        self.prefix_bullet_export_btn.setCursor(Qt.PointingHandCursor)
        self.blank_check = QCheckBox("Blank lines")
        self.blank_check.setToolTip("Insert a blank line between fields in the export")
        self.blank_check.setAccessibleName("Blank line between fields")
        self.save_btn = QPushButton("Save .txt")
        self.save_btn.setObjectName("Primary")
        self.save_btn.setToolTip("Save the preview to a text file (Ctrl+S)")
        out_buttons.addWidget(self.copy_btn)
        out_buttons.addWidget(self.prefix_bullet_export_btn)
        out_buttons.addWidget(self.blank_check)
        out_buttons.addStretch(1)
        out_buttons.addWidget(self.save_btn)
        layout.addLayout(out_buttons)

        self.blank_check.stateChanged.connect(self._on_export_options_changed)
        self.preview.textChanged.connect(self._on_preview_edited)
        self.copy_btn.clicked.connect(self.on_copy)
        self.prefix_bullet_export_btn.clicked.connect(self.on_prefix_bullet_lines_export)
        self.save_btn.clicked.connect(self.on_save)

        return frame

    def _build_menu(self):
        menubar = self.menuBar()

        file_menu = menubar.addMenu("&File")
        new_action = QAction("&New Note", self)
        new_action.setShortcut(QKeySequence.New)  # Ctrl+N
        new_action.triggered.connect(self.on_new_note)
        file_menu.addAction(new_action)

        open_action = QAction("&Open\u2026", self)
        open_action.setShortcut(QKeySequence.Open)  # Ctrl+O
        open_action.triggered.connect(self.on_open)
        file_menu.addAction(open_action)

        self.act_search = QAction("&Search notes\u2026", self)
        self.act_search.setShortcut(QKeySequence.Find)  # Ctrl+F
        self.act_search.setToolTip("Search open notes and saved .txt files")
        self.act_search.triggered.connect(self._show_search_panel)
        file_menu.addAction(self.act_search)
        self.addAction(self.act_search)

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

        self.act_prefix_bullet = QAction("Prefix &bullet on selection", self)
        self.act_prefix_bullet.setShortcut(QKeySequence("Ctrl+-"))
        self.act_prefix_bullet.setToolTip(
            "Prefix \"\u2022 \" on each line of the selected text (Ctrl+-)"
        )
        self.act_prefix_bullet.triggered.connect(self.on_prefix_bullet_shortcut)
        file_menu.addAction(self.act_prefix_bullet)
        self.addAction(self.act_prefix_bullet)

        self.act_clear_values = QAction("&Clear field values", self)
        self.act_clear_values.setShortcut(QKeySequence("Ctrl+Shift+Delete"))
        self.act_clear_values.setToolTip(
            "Clear every field value; labels and rows are kept (Ctrl+Shift+Delete)"
        )
        self.act_clear_values.triggered.connect(self.on_clear_form_values)
        file_menu.addAction(self.act_clear_values)
        self.addAction(self.act_clear_values)

        self.act_clear_field = QAction("Clear &current field value", self)
        self.act_clear_field.setShortcut(QKeySequence("Ctrl+Shift+Backspace"))
        self.act_clear_field.setToolTip(
            "Clear the focused field's value; label is kept (Ctrl+Shift+Backspace)"
        )
        self.act_clear_field.triggered.connect(self.on_clear_field_value)
        file_menu.addAction(self.act_clear_field)
        self.addAction(self.act_clear_field)

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

        # Panel + preferences actions. Import/export/compact shortcuts are also
        # registered on the main window so they work while the menu bar is hidden
        # in form focus mode.
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

        self.act_form_wide = QAction("&Wide form layout", self, checkable=True)
        self.act_form_wide.setShortcut(QKeySequence("Ctrl+Shift+2"))
        self.act_form_wide.setToolTip(
            "Show labels and actions on the left, values on the right (Ctrl+Shift+2)"
        )
        self.act_form_wide.toggled.connect(self._on_form_wide_toggled)

        self.act_edit_labels = QAction("&Editable field labels", self, checkable=True)
        self.act_edit_labels.setShortcut(QKeySequence("Ctrl+E"))
        self.act_edit_labels.setToolTip(
            "Toggle editable label boxes (plain text when off; Ctrl+E)"
        )
        self.act_edit_labels.toggled.connect(self._on_editable_labels_toggled)

        self.act_form_focus = QAction("&Form focus mode", self, checkable=True)
        self.act_form_focus.setShortcut(QKeySequence("Ctrl+Shift+F"))
        self.act_form_focus.setToolTip(
            "Maximize the form — hide side panels, tabs, and toolbars (Ctrl+Shift+F)"
        )
        self.act_form_focus.toggled.connect(self._on_form_focus_toggled)

        self.act_running_notes = QAction("&Running notes", self, checkable=True)
        self.act_running_notes.setShortcut(QKeySequence("Ctrl+Shift+R"))
        self.act_running_notes.setToolTip(
            "Edit all open notes as one continuous document (Ctrl+Shift+R)"
        )
        self.act_running_notes.toggled.connect(self._on_running_notes_toggled)

        self.act_prefs = QAction("&Preferences\u2026", self)
        self.act_prefs.setShortcut(QKeySequence("Ctrl+,"))
        self.act_prefs.triggered.connect(self.open_preferences)

        prefs_menu = menubar.addMenu("&Preferences")
        prefs_menu.addAction(self.act_prefs)
        prefs_menu.addSeparator()
        prefs_menu.addAction(self.act_import)
        prefs_menu.addAction(self.act_compact)
        prefs_menu.addAction(self.act_form_wide)
        prefs_menu.addAction(self.act_edit_labels)
        prefs_menu.addAction(self.act_form_focus)
        prefs_menu.addAction(self.act_running_notes)
        prefs_menu.addAction(self.act_export)
        self.addAction(self.act_import)
        self.addAction(self.act_export)
        self.addAction(self.act_compact)
        self.addAction(self.act_form_wide)
        self.addAction(self.act_edit_labels)
        self.addAction(self.act_form_focus)
        self.addAction(self.act_running_notes)

        view_menu.addSeparator()
        view_menu.addAction(self.act_search)
        view_menu.addAction(self.act_running_notes)

        help_menu = menubar.addMenu("&Help")
        shortcuts_action = QAction("&Keyboard Shortcuts", self)
        shortcuts_action.setShortcut(QKeySequence(Qt.Key_F1))
        shortcuts_action.triggered.connect(self._show_keyboard_shortcuts)
        help_menu.addAction(shortcuts_action)
        self.addAction(shortcuts_action)
        help_menu.addSeparator()
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
        if visible and self.form_focus_mode:
            self._exit_form_focus_mode()
        self.act_import.blockSignals(True)
        self.act_import.setChecked(visible)
        self.act_import.blockSignals(False)
        self.import_panel_visible = visible
        self.import_panel.setVisible(visible)
        if visible and not self.compact:
            self._ensure_side_panel_width(0, DEFAULT_SPLITTER_SIZES[0])
            self._ensure_form_panel_width()
        self._update_rails()

    def _on_export_toggled(self, visible: bool):
        if visible and self.form_focus_mode:
            self._exit_form_focus_mode()
        self.act_export.blockSignals(True)
        self.act_export.setChecked(visible)
        self.act_export.blockSignals(False)
        self.export_panel_visible = visible
        self.export_panel.setVisible(visible)
        if visible and not self.compact:
            self._ensure_side_panel_width(2, DEFAULT_SPLITTER_SIZES[2])
            self._ensure_form_panel_width()
        self._update_rails()

    def _enter_form_focus_mode(self) -> None:
        if self.form_focus_mode:
            return
        if self.running_notes_mode:
            self._exit_running_notes_mode()
        self._save_pre_focus_state()
        self.form_focus_mode = True
        self.act_form_focus.blockSignals(True)
        self.act_form_focus.setChecked(True)
        self.act_form_focus.blockSignals(False)
        self._apply_form_focus_layout()
        self._update_rails()

    def _exit_form_focus_mode(self) -> None:
        if not self.form_focus_mode:
            return
        self.form_focus_mode = False
        self.act_form_focus.blockSignals(True)
        self.act_form_focus.setChecked(False)
        self.act_form_focus.blockSignals(False)
        self._restore_pre_focus_state()
        self._sync_wide_focus_actions()

    def _ensure_form_panel_width(self, target_width: int | None = None) -> None:
        """Restore a usable width when the form panel was collapsed to zero."""
        if self.compact:
            return
        target_width = target_width or DEFAULT_SPLITTER_SIZES[1]
        sizes = list(self.splitter.sizes())
        if len(sizes) != 3 or sizes[1] >= MIN_SIDE_PANEL_WIDTH:
            return
        deficit = target_width - sizes[1]
        donated = 0
        for index in (0, 2):
            spare = sizes[index] - MIN_SIDE_PANEL_WIDTH
            if spare <= 0:
                continue
            take = min(spare, deficit - donated)
            sizes[index] -= take
            donated += take
            if donated >= deficit:
                break
        if donated < deficit:
            self.splitter.setSizes(DEFAULT_SPLITTER_SIZES)
            return
        sizes[1] = target_width
        self.splitter.setSizes(sizes)

    def _ensure_side_panel_width(self, panel_index: int, target_width: int) -> None:
        """Restore a usable width when a side panel is reopened from zero width."""
        if self.compact:
            return
        sizes = list(self.splitter.sizes())
        if len(sizes) != 3 or sizes[panel_index] >= MIN_SIDE_PANEL_WIDTH:
            return
        deficit = target_width - sizes[panel_index]
        form_index = 1
        if sizes[form_index] - deficit < 120:
            self.splitter.setSizes(DEFAULT_SPLITTER_SIZES)
            return
        sizes[panel_index] = target_width
        sizes[form_index] -= deficit
        self.splitter.setSizes(sizes)

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
            confirm_dialogs=self.confirm_dialogs,
            middle_panel_style=self.middle_panel_style,
            import_panel_visible=self.import_panel_visible,
            export_panel_visible=self.export_panel_visible,
            remember_splitter_sizes=self.remember_splitter_sizes,
            editable_labels=self.editable_labels,
            form_focus_on_open=self.form_focus_on_open,
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
        minimalist_before = self.minimalist_mode
        self.persistent_sidebars = values["persistent_sidebars"]
        self.compact = values["compact"]
        self.confirm_dialogs = values["confirm_dialogs"]
        self.minimalist_mode = values["minimalist_mode"]
        self.middle_panel_style = values["middle_panel_style"]
        self.import_panel_visible = values["import_panel_visible"]
        self.export_panel_visible = values["export_panel_visible"]
        self.remember_splitter_sizes = values["remember_splitter_sizes"]
        self.editable_labels = values["editable_labels"]
        self.form_focus_on_open = values["form_focus_on_open"]
        self.form_wide_layout = values["form_wide_layout"]
        self.default_template_id = values["default_template_id"]
        self.auto_parse_on_paste = values["auto_parse_on_paste"]
        self.default_parse_mode = values["default_parse_mode"]
        self.default_export_mode = values["default_export_mode"]
        self.act_compact.blockSignals(True)
        self.act_compact.setChecked(self.compact)
        self.act_compact.blockSignals(False)
        self.act_form_wide.blockSignals(True)
        self.act_form_wide.setChecked(self.form_wide_layout)
        self.act_form_wide.blockSignals(False)
        self.act_edit_labels.blockSignals(True)
        self.act_edit_labels.setChecked(self.editable_labels)
        self.act_edit_labels.blockSignals(False)
        if self.minimalist_mode:
            self._apply_minimalist_mode()
        elif minimalist_before:
            self._exit_minimalist_layout()
            if self.form_focus_on_open and not self.compact:
                self._enter_form_focus_mode()
        else:
            self.act_import.setChecked(self.import_panel_visible)
            self.act_export.setChecked(self.export_panel_visible)
            if not self.remember_splitter_sizes:
                self.splitter.setSizes(DEFAULT_SPLITTER_SIZES)
            self._apply_density()
            self._apply_compact_layout()
            self._apply_form_wide_layout()
            self._apply_editable_labels()
            if self.form_focus_on_open:
                self._enter_form_focus_mode()
        self.set_theme(self.current_theme)  # re-apply stylesheet + save
        self._update_rails()
        self._update_preview()
        self._save_settings()

    def _apply_minimalist_mode(self) -> None:
        """Form focus + wide layout with Import and Export hidden."""
        self.compact = False
        self.form_wide_layout = True
        self.middle_panel_style = MIDDLE_PANEL_MINIMALIST
        self.import_panel_visible = False
        self.export_panel_visible = False
        self.act_compact.blockSignals(True)
        self.act_compact.setChecked(False)
        self.act_compact.blockSignals(False)
        self.act_form_wide.blockSignals(True)
        self.act_form_wide.setChecked(True)
        self.act_form_wide.blockSignals(False)
        self.act_import.blockSignals(True)
        self.act_import.setChecked(False)
        self.act_export.blockSignals(True)
        self.act_export.setChecked(False)
        self.act_import.blockSignals(False)
        self.act_export.blockSignals(False)
        self.import_panel.hide()
        self.export_panel.hide()
        self._apply_density()
        self._apply_form_wide_layout()
        self._apply_editable_labels()
        self._enter_form_focus_mode()
        self._update_rails()

    def _exit_minimalist_layout(self) -> None:
        if self.form_focus_mode:
            self.form_focus_mode = False
            self.act_form_focus.blockSignals(True)
            self.act_form_focus.setChecked(False)
            self.act_form_focus.blockSignals(False)
            self._restore_pre_focus_state()
        else:
            self._apply_panel_visibility()
            self._apply_compact_layout()
            self._apply_form_wide_layout()
            self._update_rails()

    def _apply_density(self):
        margin = 4 if self.compact else 12
        self._central_layout.setContentsMargins(margin, margin, margin, margin)

    # --------------------------------------------------------- note tabs

    def _note_has_content(self, note: storage.NoteState) -> bool:
        if note.raw_import.strip():
            return True
        return any(f.label.strip() or f.value.strip() for f in note.fields)

    def _derive_tab_title(self, note: storage.NoteState, index: int) -> str:
        for field in note.fields:
            label = field.label.lower()
            if "inc" in label and "number" in label:
                value = field.value.strip()
                if value:
                    return value[:32]
        for field in note.fields:
            value = field.value.strip()
            if value:
                return value[:24]
        if note.title.strip():
            return note.title.strip()[:32]
        return f"Note {index + 1}"

    def _refresh_tab_labels(self) -> None:
        self._switching_tabs = True
        for index, note in enumerate(self._notes):
            self.note_tab_bar.setTabText(index, self._derive_tab_title(note, index))
        self._switching_tabs = False

    def _save_ui_to_note(self, index: int) -> None:
        if index < 0 or index >= len(self._notes):
            return
        fields = self.collect_fields()
        title = self._derive_tab_title(
            storage.NoteState(
                id=self._notes[index].id,
                fields=fields,
                raw_import=self.paste_box.toPlainText(),
            ),
            index,
        )
        self._notes[index] = storage.NoteState(
            id=self._notes[index].id,
            title=title,
            fields=fields,
            raw_import=self.paste_box.toPlainText(),
            export_mode=self._current_export_mode(),
            blank_between=self.blank_check.isChecked(),
            source_path=self._notes[index].source_path,
        )
        if self.note_tab_bar.currentIndex() == index:
            self.note_tab_bar.setTabText(index, title)

    def _capture_current_note(self) -> None:
        if self.running_notes_mode:
            return
        self._save_ui_to_note(self.note_tab_bar.currentIndex())

    def _apply_note_to_ui(self, note: storage.NoteState) -> None:
        self._switching_tabs = True
        self.paste_box.setPlainText(note.raw_import)
        self.blank_check.setChecked(note.blank_between)
        self._set_fields(note.fields)
        self._switching_tabs = False

    def _on_note_tab_changed(self, index: int) -> None:
        if index < 0:
            return
        if self._reordering_tabs:
            self._active_note_index = index
            return
        if self._switching_tabs:
            return
        if self.running_notes_mode:
            self._sync_from_running_notes()
            self._active_note_index = index
            return
        previous = getattr(self, "_active_note_index", -1)
        if previous >= 0 and previous != index:
            self._save_ui_to_note(previous)
        self._active_note_index = index
        if index < len(self._notes):
            self._apply_note_to_ui(self._notes[index])

    def _on_note_tab_moved(self, from_index: int, to_index: int) -> None:
        if self._switching_tabs or from_index == to_index:
            return
        self._reordering_tabs = True
        try:
            self._save_ui_to_note(self._active_note_index)
            note = self._notes.pop(from_index)
            self._notes.insert(to_index, note)
            old_active = self._active_note_index
            if old_active == from_index:
                self._active_note_index = to_index
            elif from_index < old_active <= to_index:
                self._active_note_index = old_active - 1
            elif to_index <= old_active < from_index:
                self._active_note_index = old_active + 1
        finally:
            self._reordering_tabs = False
        self._schedule_save()

    def _attach_tab_close_button(self, index: int) -> None:
        wrapper = QWidget(self.note_tab_bar)
        wrapper.setObjectName("TabCloseWrapper")
        layout = QHBoxLayout(wrapper)
        layout.setContentsMargins(0, 0, 8, 0)
        layout.setSpacing(0)
        btn = QToolButton(wrapper)
        btn.setObjectName("TabCloseButton")
        btn.setText("\u00d7")
        btn.setToolTip("Close note tab")
        btn.setAccessibleName("Close note tab")
        btn.setFixedSize(18, 18)
        btn.setCursor(Qt.PointingHandCursor)
        btn.clicked.connect(self._on_tab_close_button_clicked)
        layout.addWidget(btn)
        self.note_tab_bar.setTabButton(index, QTabBar.RightSide, wrapper)

    def _on_tab_close_button_clicked(self) -> None:
        btn = self.sender()
        if btn is None:
            return
        for index in range(self.note_tab_bar.count()):
            wrapper = self.note_tab_bar.tabButton(index, QTabBar.RightSide)
            if wrapper is None:
                continue
            tab_btn = wrapper.findChild(QToolButton, "TabCloseButton")
            if tab_btn is btn:
                self._on_note_tab_close(index)
                return

    def _confirm_action(self, title: str, text: str) -> bool:
        """Return True if the user confirmed (or confirmations are disabled)."""
        if not self.confirm_dialogs:
            return True
        reply = QMessageBox.question(
            self,
            title,
            text,
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        return reply == QMessageBox.Yes

    def _on_note_tab_close(self, index: int) -> None:
        if len(self._notes) <= 1:
            QMessageBox.information(
                self,
                "Cannot close tab",
                "At least one note tab must remain open.",
            )
            return
        note = self._notes[index]
        if self._note_has_content(note):
            if not self._confirm_action(
                "Close note tab",
                f"Close \"{self._derive_tab_title(note, index)}\"?\n\n"
                "Unsaved work in this tab will be removed.",
            ):
                return
        was_active = index == self.note_tab_bar.currentIndex()
        self._switching_tabs = True
        self.note_tab_bar.removeTab(index)
        self._notes.pop(index)
        new_index = self.note_tab_bar.currentIndex()
        self._active_note_index = new_index
        self._refresh_tab_labels()
        self._switching_tabs = False
        if was_active and 0 <= new_index < len(self._notes):
            self._apply_note_to_ui(self._notes[new_index])
        self._schedule_save()
        self._set_status("Closed a note tab.")

    def _add_note_tab(self, *, apply_template: bool = False) -> None:
        self._capture_current_note()
        note = storage.NoteState(id=storage.new_note_id())
        self._notes.append(note)
        index = len(self._notes) - 1
        self._switching_tabs = True
        self.note_tab_bar.addTab(self._derive_tab_title(note, index))
        self._attach_tab_close_button(index)
        self.note_tab_bar.setCurrentIndex(index)
        self._switching_tabs = False
        self._active_note_index = index
        self.paste_box.clear()
        self._set_fields([])
        if apply_template:
            self._apply_default_template()
        self._capture_current_note()
        self._schedule_save()

    def _clear_note_tabs(self) -> None:
        while self.note_tab_bar.count() > 0:
            self.note_tab_bar.removeTab(self.note_tab_bar.count() - 1)

    def _load_workspace_tabs(self, workspace: storage.WorkspaceState) -> None:
        self._notes = workspace.notes or [storage.NoteState(id=storage.new_note_id())]
        self._switching_tabs = True
        self._clear_note_tabs()
        for index, note in enumerate(self._notes):
            self.note_tab_bar.addTab(self._derive_tab_title(note, index))
            self._attach_tab_close_button(index)
        active = max(0, min(workspace.active_index, len(self._notes) - 1))
        self.note_tab_bar.setCurrentIndex(active)
        self._active_note_index = active
        self._switching_tabs = False
        self._apply_note_to_ui(self._notes[active])

    def _update_active_tab_title(self) -> None:
        if self._switching_tabs:
            return
        index = self.note_tab_bar.currentIndex()
        if index < 0 or index >= len(self._notes):
            return
        note = self._notes[index]
        title = self._derive_tab_title(
            storage.NoteState(
                id=note.id,
                fields=self.collect_fields(),
                raw_import=self.paste_box.toPlainText(),
            ),
            index,
        )
        self.note_tab_bar.setTabText(index, title)

    def _notes_dialog_dir(self) -> str:
        return str(storage.resolve_notes_dir(self.settings))

    def _remember_notes_dir(self, file_path: str) -> None:
        storage.remember_notes_dir(self.settings, file_path)
        storage.save_settings(self.settings)

    def _apply_form_focus_layout(self) -> None:
        if not self.form_focus_mode:
            return
        self.tab_row_widget.setVisible(False)
        self.search_panel.setVisible(False)
        self.search_toggle_btn.blockSignals(True)
        self.search_toggle_btn.setChecked(False)
        self.search_toggle_btn.blockSignals(False)
        self.menuBar().setVisible(False)
        self.form_header_widget.setVisible(False)
        self.form_toolbar.setVisible(False)
        self.form_focus_toolbar.setVisible(True)
        self.left_rail.setVisible(False)
        self.right_rail.setVisible(False)
        self.import_panel.hide()
        self.export_panel.hide()
        self.act_import.blockSignals(True)
        self.act_export.blockSignals(True)
        self.act_import.setChecked(False)
        self.act_export.setChecked(False)
        self.act_import.blockSignals(False)
        self.act_export.blockSignals(False)
        self.form_panel.show()
        self.splitter.setStretchFactor(0, 0)
        self.splitter.setStretchFactor(1, 1)
        self.splitter.setStretchFactor(2, 0)
        total = max(sum(self.splitter.sizes()), self.width(), 600)
        self.splitter.setSizes([0, total, 0])
        self._central_layout.setContentsMargins(2, 2, 2, 2)
        self._sync_wide_focus_actions()

    def _save_pre_focus_state(self) -> None:
        self._pre_focus_state = {
            "compact": self.compact,
            "import_visible": self.act_import.isChecked(),
            "export_visible": self.act_export.isChecked(),
            "splitter_sizes": list(self.splitter.sizes()),
            "margins": self._central_layout.getContentsMargins(),
        }

    def _restore_pre_focus_state(self) -> None:
        state = self._pre_focus_state
        self.tab_row_widget.setVisible(True)
        self.menuBar().setVisible(True)
        self.form_header_widget.setVisible(True)
        self.form_toolbar.setVisible(True)
        self.form_focus_toolbar.setVisible(False)

        self.act_import.blockSignals(True)
        self.act_export.blockSignals(True)
        self.act_import.setChecked(state["import_visible"])
        self.act_export.setChecked(state["export_visible"])
        self.act_import.blockSignals(False)
        self.act_export.blockSignals(False)
        self.import_panel_visible = state["import_visible"]
        self.export_panel_visible = state["export_visible"]
        self.import_panel.setVisible(state["import_visible"])
        self.export_panel.setVisible(state["export_visible"])

        self.act_compact.blockSignals(True)
        self.compact = state["compact"]
        self.act_compact.setChecked(self.compact)
        self.act_compact.blockSignals(False)

        left, top, right, bottom = state["margins"]
        self._central_layout.setContentsMargins(left, top, right, bottom)
        self._apply_density()
        self.splitter.setStretchFactor(0, 0)
        self.splitter.setStretchFactor(1, 1)
        self.splitter.setStretchFactor(2, 0)
        if self.compact:
            self._apply_compact_layout()
        else:
            self.form_panel.show()
            self.splitter.setSizes(state["splitter_sizes"])
            self._ensure_form_panel_width()
            if self.import_panel.isVisible():
                self._ensure_side_panel_width(0, DEFAULT_SPLITTER_SIZES[0])
            if self.export_panel.isVisible():
                self._ensure_side_panel_width(2, DEFAULT_SPLITTER_SIZES[2])
        self._update_rails()

    def _on_form_focus_toggled(self, checked: bool) -> None:
        if checked and not self.form_focus_mode:
            self._enter_form_focus_mode()
            self._set_status("Form focus on — Ctrl+Shift+F to restore.")
            return
        if not checked and self.form_focus_mode:
            self._exit_form_focus_mode()
            self._set_status("Form focus off.")

    def _apply_compact_layout(self):
        """Compact mode hides the form and uses the export live preview as the editor."""
        if self.form_focus_mode:
            self._apply_form_focus_layout()
            return
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
            self._ensure_form_panel_width()
            if self.import_panel.isVisible():
                self._ensure_side_panel_width(0, DEFAULT_SPLITTER_SIZES[0])
            if self.export_panel.isVisible():
                self._ensure_side_panel_width(2, DEFAULT_SPLITTER_SIZES[2])

    def _sync_wide_focus_actions(self) -> None:
        wide_focus = self.form_focus_mode and self.form_wide_layout
        for row in self.field_rows:
            row.set_wide_focus_actions(wide_focus)

    def _apply_form_wide_layout(self) -> None:
        self.rows_layout.setSpacing(2 if self.form_wide_layout else 8)
        for row in self.field_rows:
            row.set_wide_layout(self.form_wide_layout)
        self._sync_wide_focus_actions()

    def _apply_editable_labels(self) -> None:
        for row in self.field_rows:
            row.set_labels_editable(self.editable_labels)

    def _on_editable_labels_toggled(self, checked: bool) -> None:
        self.editable_labels = checked
        self._apply_editable_labels()
        self._save_settings()
        if checked:
            self._set_status("Editable labels on.")
        else:
            self._set_status("Editable labels off — compact plain-text labels.")

    def _on_form_wide_toggled(self, checked: bool) -> None:
        self.form_wide_layout = checked
        if not self.minimalist_mode:
            self.middle_panel_style = (
                MIDDLE_PANEL_WIDE if checked else MIDDLE_PANEL_STACKED
            )
        self._apply_form_wide_layout()
        self._save_settings()
        if checked:
            self._set_status("Wide form layout on — more fields visible at once.")
        else:
            self._set_status("Wide form layout off.")

    def _on_compact_toggled(self, checked: bool):
        if checked and self.form_focus_mode:
            self._exit_form_focus_mode()
        if checked and self.running_notes_mode:
            self._exit_running_notes_mode()
        self.act_compact.blockSignals(True)
        self.act_compact.setChecked(checked)
        self.act_compact.blockSignals(False)
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
        self.editable_labels = bool(s.get("editable_labels", False))
        self.confirm_dialogs = bool(
            s.get("confirm_dialogs", s.get("confirm_clear_values", True))
        )
        if "middle_panel_style" in s:
            self.middle_panel_style = s["middle_panel_style"]
            self.form_wide_layout, self.minimalist_mode = (
                flags_from_middle_panel_style(self.middle_panel_style)
            )
        else:
            self.minimalist_mode = bool(s.get("minimalist_mode", False))
            if self.minimalist_mode:
                self.form_wide_layout = True
            else:
                self.form_wide_layout = bool(s.get("form_wide_layout", False))
            self.middle_panel_style = middle_panel_style_from_flags(
                self.form_wide_layout, self.minimalist_mode
            )
        if self.minimalist_mode:
            self.import_panel_visible = False
            self.export_panel_visible = False
            self.compact = False
        else:
            self.import_panel_visible = bool(s.get("import_panel_visible", True))
            self.export_panel_visible = bool(s.get("export_panel_visible", True))
        self.remember_splitter_sizes = bool(s.get("remember_splitter_sizes", True))
        self.default_template_id = s.get("default_template_id", DEFAULT_TEMPLATE_ID)
        self.auto_parse_on_paste = bool(s.get("auto_parse_on_paste", False))
        self.default_parse_mode = s.get("default_parse_mode", PARSE_MODE_PARSE)
        self.default_export_mode = s.get("default_export_mode", MODE_SAME_LINE)
        self.form_focus_on_open = bool(s.get("form_focus_on_open", False))

    def _save_settings(self):
        self.settings.update({
            "theme": self.current_theme,
            "persistent_sidebars": self.persistent_sidebars,
            "compact": self.compact,
            "form_wide_layout": self.form_wide_layout,
            "middle_panel_style": self.middle_panel_style,
            "editable_labels": self.editable_labels,
            "minimalist_mode": self.minimalist_mode,
            "confirm_dialogs": self.confirm_dialogs,
            "import_panel_visible": self.import_panel_visible,
            "export_panel_visible": self.export_panel_visible,
            "remember_splitter_sizes": self.remember_splitter_sizes,
            "default_template_id": self.default_template_id,
            "auto_parse_on_paste": self.auto_parse_on_paste,
            "default_parse_mode": self.default_parse_mode,
            "default_export_mode": self.default_export_mode,
            "form_focus_on_open": self.form_focus_on_open,
        })
        if self.remember_splitter_sizes and not self.compact and not self.form_focus_mode:
            sizes = self.splitter.sizes()
            if len(sizes) == 3 and sizes[1] >= MIN_SIDE_PANEL_WIDTH:
                self.settings["splitter_sizes"] = sizes
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
        else:
            sizes = self.settings.get("splitter_sizes")
            if isinstance(sizes, list) and len(sizes) == 3:
                self.splitter.setSizes(sizes)
            else:
                self.splitter.setSizes(DEFAULT_SPLITTER_SIZES)
        if not self.compact:
            self._ensure_form_panel_width()

    def _on_splitter_moved(self, *_):
        if self.remember_splitter_sizes:
            self._splitter_save_timer.start()

    def _persist_splitter_sizes(self):
        if not self.remember_splitter_sizes or self.compact or self.form_focus_mode:
            return
        sizes = self.splitter.sizes()
        if len(sizes) != 3 or sizes[1] < MIN_SIDE_PANEL_WIDTH:
            return
        self.settings["splitter_sizes"] = sizes
        storage.save_settings(self.settings)

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

    def _prefix_selected_lines(
        self,
        widget: QPlainTextEdit | QTextEdit,
        prefix: str,
        already_prefixed: tuple[str, ...],
    ) -> int:
        cursor = widget.textCursor()
        if not cursor.hasSelection():
            return -1

        raw = cursor.selectedText().replace("\u2029", "\n")
        prefixed: list[str] = []
        changed = 0
        for line in raw.splitlines():
            stripped = line.lstrip()
            if not stripped:
                prefixed.append(line)
                continue
            if any(stripped.startswith(marker) for marker in already_prefixed):
                prefixed.append(line)
                continue
            indent = line[: len(line) - len(stripped)]
            prefixed.append(f"{indent}{prefix}{stripped}")
            changed += 1

        cursor.insertText("\n".join(prefixed))
        return changed

    def _prefix_bullet_in_widget(self, widget: QPlainTextEdit | QTextEdit) -> int:
        return self._prefix_selected_lines(
            widget, "\u2022 ", ("\u2022", "\u2022 ", "-", "- ")
        )

    def _report_bullet_prefix(self, widget: QPlainTextEdit | QTextEdit, changed: int) -> None:
        if changed < 0:
            self._set_status('Select text, then press Ctrl+- or click "\u2022" to add bullets.')
            return
        self._schedule_save()
        if changed:
            self._set_status(
                f'Prefixed {changed} line{"s" if changed != 1 else ""} with "\u2022".'
            )
        else:
            self._set_status("Selected lines already start with a bullet.")

    def on_prefix_bullet_shortcut(self):
        focused = self.focusWidget()
        if isinstance(focused, (QPlainTextEdit, QTextEdit)):
            target = focused
        elif isinstance(self._last_text_focus, (QPlainTextEdit, QTextEdit)):
            target = self._last_text_focus
        else:
            self._set_status('Select text, then press Ctrl+- to add bullets.')
            return
        self._report_bullet_prefix(target, self._prefix_bullet_in_widget(target))

    def on_prefix_bullet_lines_import(self):
        self._report_bullet_prefix(self.paste_box, self._prefix_bullet_in_widget(self.paste_box))

    def on_prefix_bullet_lines_export(self):
        self._report_bullet_prefix(self.preview, self._prefix_bullet_in_widget(self.preview))

    def on_parse(self):
        fields = parse_notes(self.paste_box.toPlainText())
        self._set_fields(fields)
        self._update_active_tab_title()
        self._set_status(f"Parsed {len(fields)} field{'s' if len(fields) != 1 else ''}.")
        self._schedule_save()

    def on_merge(self):
        incoming = parse_notes(self.paste_box.toPlainText())
        if not incoming:
            self._set_status("Nothing to merge - the paste area has no recognisable fields.")
            return
        merged, added, updated = merge_fields(self.collect_fields(), incoming)
        self._set_fields(merged)
        self._update_active_tab_title()
        self._set_status(f"Merged: {added} added, {updated} updated.")
        self._schedule_save()

    def on_new_note(self):
        if self.running_notes_mode:
            self._sync_from_running_notes()
        self._add_note_tab(apply_template=True)
        self._set_status("Opened a new note tab from the default template.")
        if self.running_notes_mode:
            self._refresh_running_notes_view()
            self.running_notes_edit.setFocus()
        else:
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
        if has_values and not self._confirm_action(
            "Clear values",
            "Clear every field's value?\n\nField labels and rows will be kept.",
        ):
            return
        for row in self.field_rows:
            row.clear_value()
        self._update_preview()
        self._schedule_save()
        n = len(self.field_rows)
        self._set_status(
            f"Cleared values in {n} field{'s' if n != 1 else ''}. Labels kept."
        )

    def _field_row_for_widget(self, widget: QWidget | None) -> FieldRow | None:
        while widget is not None:
            if isinstance(widget, FieldRow):
                return widget
            widget = widget.parentWidget()
        return None

    def on_clear_field_value(self):
        focused = self.focusWidget()
        if focused is None:
            focused = self._last_text_focus
        row = self._field_row_for_widget(focused)
        if row is None:
            self._set_status(
                "Click in a field value box, then press Ctrl+Shift+Backspace."
            )
            return
        label = row.to_field().label.strip() or "field"
        if not row.to_field().value.strip():
            self._set_status(f"'{label}' is already empty.")
            return
        row.clear_value()
        self._update_preview()
        self._schedule_save()
        self._set_status(f"Cleared value for '{label}'.")

    def on_templates(self):
        note_text = self.preview.toPlainText()
        if not note_text.strip():
            note_text = self.paste_box.toPlainText()
        dialog = TemplatesDialog(
            self, current_note_text=note_text, confirm_dialogs=self.confirm_dialogs
        )
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

    def on_open(self):
        start_dir = self._notes_dialog_dir()
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Open note",
            start_dir,
            "Text files (*.txt);;All files (*.*)",
        )
        if not path:
            return
        self._open_note_path(path)

    def on_copy(self):
        self._update_preview()
        text = self.preview.toPlainText()
        QApplication.clipboard().setText(text)
        self._set_status("Export copied to clipboard.")

    def _default_save_path(self) -> str:
        index = self.note_tab_bar.currentIndex()
        if 0 <= index < len(self._notes):
            note = storage.NoteState(
                id=self._notes[index].id,
                title=self._notes[index].title,
                fields=self.collect_fields(),
                raw_import=self.paste_box.toPlainText(),
            )
            name = self._derive_tab_title(note, index)
        else:
            name = "notes"
        filename = storage.safe_filename(name) + ".txt"
        return str(Path(self._notes_dialog_dir()) / filename)

    def on_save(self):
        text = self.preview.toPlainText()
        default_path = self._default_save_path()
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Save notes as text",
            default_path,
            "Text files (*.txt);;All files (*.*)",
        )
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(text)
            self._remember_notes_dir(path)
            index = self.note_tab_bar.currentIndex()
            if 0 <= index < len(self._notes):
                self._notes[index].source_path = path
                self._schedule_save()
            self._set_status(f"Saved to {path}")
        except OSError as exc:
            QMessageBox.critical(self, "Save failed", f"Could not save the file:\n{exc}")

    # --------------------------------------------------------------- search

    def _on_search_toggle_clicked(self, checked: bool) -> None:
        if checked:
            self._show_search_panel()
        else:
            self._hide_search_panel()

    def _show_search_panel(self) -> None:
        if self.running_notes_mode:
            self.running_notes_find_input.setFocus()
            self.running_notes_find_input.selectAll()
            query = self.running_notes_find_input.text().strip()
            if query:
                self._find_in_running_notes(forward=True, from_start=True)
            return
        self.search_panel.setVisible(True)
        self.search_toggle_btn.blockSignals(True)
        self.search_toggle_btn.setChecked(True)
        self.search_toggle_btn.blockSignals(False)
        self.search_input.setFocus()
        self.search_input.selectAll()
        if self.search_input.text().strip():
            self._run_search()

    def _hide_search_panel(self) -> None:
        self.search_panel.setVisible(False)
        self.search_toggle_btn.blockSignals(True)
        self.search_toggle_btn.setChecked(False)
        self.search_toggle_btn.blockSignals(False)

    def eventFilter(self, obj, event):
        if event.type() == QEvent.KeyPress:
            if (
                event.key() == Qt.Key_Escape
                and self.search_panel.isVisible()
                and obj in (self.search_input, self.search_results)
            ):
                self._hide_search_panel()
                return True
            if obj is self.running_notes_find_input and event.key() in (
                Qt.Key_Return,
                Qt.Key_Enter,
            ):
                if event.modifiers() & Qt.ShiftModifier:
                    self._find_prev_in_running_notes()
                else:
                    self._find_next_in_running_notes()
                return True
        return super().eventFilter(obj, event)

    def _on_search_text_changed(self, _text: str) -> None:
        self._search_timer.start()

    def _note_search_text(self, note: storage.NoteState) -> str:
        parts = [
            note.title or "",
            note.raw_import or "",
            running_notes.note_body(note, default_mode=self._current_export_mode()),
        ]
        for field in note.fields:
            parts.append(field.label)
            parts.append(field.value)
        return "\n".join(parts)

    def _run_search(self) -> None:
        query = self.search_input.text().strip()
        self.search_results.clear()
        self._search_hits = []
        if not query:
            self.search_status.setText("Type to search all notes.")
            return

        self._capture_current_note()
        hits: List[storage.SearchHit] = []
        open_paths = {
            Path(n.source_path).resolve()
            for n in self._notes
            if n.source_path
        }

        for index, note in enumerate(self._notes):
            text = self._note_search_text(note)
            if not storage.search_note_text(text, query):
                continue
            title = self._derive_tab_title(note, index)
            hits.append(
                storage.SearchHit(
                    kind="tab",
                    title=title,
                    snippet=storage.snippet_around(text, query),
                    note_id=note.id,
                    path=note.source_path,
                    tab_index=index,
                )
            )

        notes_dir = storage.resolve_notes_dir(self.settings)
        for path in storage.list_note_files(notes_dir):
            try:
                resolved = path.resolve()
            except OSError:
                resolved = path
            if resolved in open_paths:
                continue
            text = storage.read_text_file(path)
            if text is None or not storage.search_note_text(text, query):
                continue
            hits.append(
                storage.SearchHit(
                    kind="file",
                    title=path.stem,
                    snippet=storage.snippet_around(text, query),
                    path=str(path),
                )
            )

        self._search_hits = hits
        for hit in hits:
            prefix = "Open tab" if hit.kind == "tab" else "Saved file"
            item = QListWidgetItem(f"{hit.title}\n{prefix} — {hit.snippet}")
            item.setToolTip(hit.path or hit.title)
            self.search_results.addItem(item)

        if hits:
            self.search_status.setText(
                f"{len(hits)} result{'s' if len(hits) != 1 else ''} for “{query}”."
            )
            self.search_results.setCurrentRow(0)
        else:
            self.search_status.setText(f"No matches for “{query}”.")

    def _activate_first_search_hit(self) -> None:
        if self.search_results.count() > 0:
            self.search_results.setCurrentRow(0)
            item = self.search_results.currentItem()
            if item is not None:
                self._on_search_result_activated(item)

    def _on_search_result_activated(self, item: QListWidgetItem) -> None:
        row = self.search_results.row(item)
        if row < 0 or row >= len(self._search_hits):
            return
        hit = self._search_hits[row]
        if hit.kind == "tab" and 0 <= hit.tab_index < len(self._notes):
            if self.running_notes_mode:
                self.act_running_notes.setChecked(False)
            self.note_tab_bar.setCurrentIndex(hit.tab_index)
            self._set_status(f"Opened tab “{hit.title}”.")
            return
        if hit.kind == "file" and hit.path:
            self._open_note_path(hit.path)

    def _open_note_path(self, path: str) -> None:
        try:
            with open(path, encoding="utf-8") as fh:
                text = fh.read()
        except OSError as exc:
            QMessageBox.critical(self, "Open failed", f"Could not open the file:\n{exc}")
            return

        if self.running_notes_mode:
            self.act_running_notes.setChecked(False)

        # Reuse an already-open tab for the same file when possible.
        for index, note in enumerate(self._notes):
            if note.source_path and Path(note.source_path) == Path(path):
                self.note_tab_bar.setCurrentIndex(index)
                self._set_status(f"Opened {path}")
                return

        self._remember_notes_dir(path)
        self._add_note_tab(apply_template=False)
        self.paste_box.setPlainText(text)
        index = self.note_tab_bar.currentIndex()
        if 0 <= index < len(self._notes):
            self._notes[index].title = Path(path).stem[:32]
            self._notes[index].source_path = path
        self.on_parse()
        self._capture_current_note()
        self._schedule_save()
        self._set_status(f"Opened {path}")
        self.paste_box.setFocus()

    # -------------------------------------------------------- running notes

    def _on_running_notes_btn_clicked(self, checked: bool) -> None:
        self.act_running_notes.setChecked(checked)

    def _on_running_notes_toggled(self, checked: bool) -> None:
        if checked and not self.running_notes_mode:
            self._enter_running_notes_mode()
        elif not checked and self.running_notes_mode:
            self._exit_running_notes_mode()

    def _enter_running_notes_mode(self) -> None:
        if self.running_notes_mode:
            return
        if self.form_focus_mode:
            self._exit_form_focus_mode()
        if self.compact:
            self.act_compact.setChecked(False)

        self._capture_current_note()
        self.running_notes_mode = True
        self.act_running_notes.blockSignals(True)
        self.act_running_notes.setChecked(True)
        self.act_running_notes.blockSignals(False)
        self.running_notes_btn.blockSignals(True)
        self.running_notes_btn.setChecked(True)
        self.running_notes_btn.blockSignals(False)

        self._content_row.setVisible(False)
        self.running_notes_panel.setVisible(True)
        self._refresh_running_notes_view()
        self.running_notes_find_status.clear()
        self.running_notes_edit.setFocus()
        self._set_status(
            f"Running notes — {len(self._notes)} note"
            f"{'s' if len(self._notes) != 1 else ''} compiled."
        )

    def _exit_running_notes_mode(self) -> None:
        if not self.running_notes_mode:
            return
        self._running_notes_sync_timer.stop()
        self._sync_from_running_notes()
        self.running_notes_mode = False
        self.act_running_notes.blockSignals(True)
        self.act_running_notes.setChecked(False)
        self.act_running_notes.blockSignals(False)
        self.running_notes_btn.blockSignals(True)
        self.running_notes_btn.setChecked(False)
        self.running_notes_btn.blockSignals(False)

        self.running_notes_panel.setVisible(False)
        self._content_row.setVisible(True)
        index = self.note_tab_bar.currentIndex()
        if 0 <= index < len(self._notes):
            self._apply_note_to_ui(self._notes[index])
        self._refresh_tab_labels()
        self._apply_panel_visibility()
        self._update_rails()
        self._set_status("Exited running notes.")

    def _refresh_running_notes_view(self) -> None:
        if not self.running_notes_mode:
            return
        text = running_notes.compile_running_notes(
            self._notes,
            default_mode=self._current_export_mode(),
        )
        self._updating_running_notes = True
        cursor = self.running_notes_edit.textCursor()
        pos = cursor.position()
        self.running_notes_edit.setPlainText(text)
        cursor = self.running_notes_edit.textCursor()
        cursor.setPosition(min(pos, len(text)))
        self.running_notes_edit.setTextCursor(cursor)
        self._updating_running_notes = False

    def _on_running_notes_edited(self) -> None:
        if self._updating_running_notes or not self.running_notes_mode:
            return
        self._running_notes_sync_timer.start()
        if self.running_notes_find_input.text().strip():
            self._update_running_notes_find_status()

    def _on_running_notes_find_text_changed(self, _text: str) -> None:
        query = self.running_notes_find_input.text()
        if not query.strip():
            self.running_notes_find_status.clear()
            return
        self._find_in_running_notes(forward=True, from_start=True)

    def _find_next_in_running_notes(self) -> None:
        self._find_in_running_notes(forward=True, from_start=False)

    def _find_prev_in_running_notes(self) -> None:
        self._find_in_running_notes(forward=False, from_start=False)

    def _count_running_notes_matches(self, query: str) -> int:
        if not query:
            return 0
        text = self.running_notes_edit.toPlainText()
        lower = text.lower()
        needle = query.lower()
        count = 0
        start = 0
        while True:
            idx = lower.find(needle, start)
            if idx < 0:
                break
            count += 1
            start = idx + max(len(needle), 1)
        return count

    def _update_running_notes_find_status(self, *, current: int | None = None) -> None:
        query = self.running_notes_find_input.text().strip()
        if not query:
            self.running_notes_find_status.clear()
            return
        total = self._count_running_notes_matches(query)
        if total == 0:
            self.running_notes_find_status.setText("No matches")
            return
        if current is None:
            self.running_notes_find_status.setText(f"{total} match{'es' if total != 1 else ''}")
            return
        self.running_notes_find_status.setText(f"{current} of {total}")

    def _match_index_at_cursor(self, query: str) -> int:
        """1-based index of the match at the current selection, or 0."""
        cursor = self.running_notes_edit.textCursor()
        if not cursor.hasSelection():
            return 0
        selected = cursor.selectedText().replace("\u2029", "\n")
        if selected.lower() != query.lower():
            return 0
        pos = min(cursor.selectionStart(), cursor.selectionEnd())
        lower = self.running_notes_edit.toPlainText().lower()
        needle = query.lower()
        index = 0
        start = 0
        while True:
            idx = lower.find(needle, start)
            if idx < 0:
                return 0
            index += 1
            if idx == pos:
                return index
            start = idx + max(len(needle), 1)

    def _find_in_running_notes(self, *, forward: bool, from_start: bool) -> None:
        query = self.running_notes_find_input.text()
        if not query.strip():
            self.running_notes_find_status.clear()
            return

        document = self.running_notes_edit.document()
        flags = QTextDocument.FindBackward if not forward else QTextDocument.FindFlags()

        if from_start:
            cursor = QTextCursor(document)
            if not forward:
                cursor.movePosition(QTextCursor.End)
        else:
            cursor = self.running_notes_edit.textCursor()

        found = document.find(query, cursor, flags)
        if found.isNull():
            # Wrap around.
            wrap = QTextCursor(document)
            if forward:
                wrap.movePosition(QTextCursor.Start)
            else:
                wrap.movePosition(QTextCursor.End)
            found = document.find(query, wrap, flags)

        if found.isNull():
            self.running_notes_find_status.setText("No matches")
            return

        self.running_notes_edit.setTextCursor(found)
        self.running_notes_edit.ensureCursorVisible()
        self.running_notes_edit.setFocus()
        # Keep the find box ready for the next Enter without stealing selection.
        self.running_notes_find_input.setFocus()
        current = self._match_index_at_cursor(query)
        self._update_running_notes_find_status(current=current or None)

    def _sync_from_running_notes(self) -> None:
        if not self.running_notes_mode:
            return
        text = self.running_notes_edit.toPlainText()
        sections = running_notes.split_running_notes(text)
        if not sections:
            self._set_status(
                "Running notes: no <<<NOTE:…>>> markers found — edits not applied."
            )
            return
        updated, count = running_notes.apply_sections_to_notes(
            self._notes,
            sections,
            default_mode=self._current_export_mode(),
        )
        self._notes = updated
        self._write_linked_note_files()
        self._schedule_save()
        self._set_status(
            f"Running notes synced ({count} note{'s' if count != 1 else ''} updated)."
        )

    def _write_linked_note_files(self) -> None:
        """Write each note that has a source_path back to its .txt file."""
        for note in self._notes:
            if not note.source_path:
                continue
            body = running_notes.note_body(
                note, default_mode=self._current_export_mode()
            )
            storage.write_text_file(Path(note.source_path), body)

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
        row.copied.connect(self._on_row_copied)
        row.set_wide_layout(self.form_wide_layout)
        row.set_labels_editable(self.editable_labels)
        row.set_wide_focus_actions(self.form_focus_mode and self.form_wide_layout)
        # Insert before the trailing stretch item.
        self.rows_layout.insertWidget(self.rows_layout.count() - 1, row)
        self.field_rows.append(row)

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
        self._update_active_tab_title()
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
        return self.default_export_mode or MODE_SAME_LINE

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
        self._update_active_tab_title()
        self._schedule_save()

    def _set_status(self, message: str):
        self.status_label.setText(message)

    # --------------------------------------------------------- persistence

    def _schedule_save(self):
        self._save_timer.start()

    def _persist_draft(self):
        if not self.running_notes_mode:
            self._capture_current_note()
        storage.save_workspace(storage.WorkspaceState(
            active_index=max(0, self.note_tab_bar.currentIndex()),
            notes=self._notes,
        ))

    def _load_state(self):
        self.settings = storage.load_settings()
        self._load_preferences_from_settings()
        self.act_compact.blockSignals(True)
        self.act_compact.setChecked(self.compact)
        self.act_compact.blockSignals(False)
        self.act_form_wide.blockSignals(True)
        self.act_form_wide.setChecked(self.form_wide_layout)
        self.act_form_wide.blockSignals(False)
        self.act_edit_labels.blockSignals(True)
        self.act_edit_labels.setChecked(self.editable_labels)
        self.act_edit_labels.blockSignals(False)
        theme = self.settings.get("theme", themes.THEME_SYSTEM)
        self._apply_density()
        self._apply_panel_visibility()
        self._apply_splitter_sizes()
        self._apply_compact_layout()
        self._apply_form_wide_layout()
        self._apply_editable_labels()
        if self.minimalist_mode:
            self._apply_minimalist_mode()
        elif self.form_focus_on_open and not self.compact:
            self._enter_form_focus_mode()
        self.set_theme(theme)
        self._update_rails()

        workspace = storage.load_workspace()
        if not workspace.notes:
            workspace.notes = [storage.NoteState(id=storage.new_note_id())]
        active = workspace.notes[workspace.active_index]
        if (
            not active.fields
            and not active.raw_import.strip()
            and len(workspace.notes) == 1
        ):
            self._load_workspace_tabs(workspace)
            if self._apply_default_template():
                self._capture_current_note()
                self._refresh_tab_labels()
                self._set_status("Loaded the default template.")
            else:
                self._set_status("Ready.")
        else:
            self._load_workspace_tabs(workspace)
            self._set_status(
                f"Restored {len(workspace.notes)} note tab"
                f"{'s' if len(workspace.notes) != 1 else ''}."
            )

    # -------------------------------------------------------------- dialogs

    def _show_keyboard_shortcuts(self):
        KeyboardShortcutsDialog(self).exec()

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
        if self.running_notes_mode:
            self._running_notes_sync_timer.stop()
            self._sync_from_running_notes()
        self._persist_draft()
        super().closeEvent(event)

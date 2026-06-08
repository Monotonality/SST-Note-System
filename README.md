# AdamNote

Improved note-taking software for SSTs — a **standalone Windows desktop app**
(built with Python + PySide6/Qt) that turns messy plain-text ticket notes into a
clean, editable form and exports tidy plain text again.

It is a real native application: native windows, menus, file dialogs, system
tray, and single-instance behavior. It is **not** a website and does not run in
a browser or a local web server.

---

## What it does

Technologists paste messy notes from Notepad, Teams, or tickets. The app parses
`Label: value` (and similar layouts) into editable fields, then exports clean
plain text. Field names vary by team, so parsing is intentionally forgiving.

### Core workflow
- **Import** — large paste area for raw notes.
- **Parse into form** — detects fields and shows label + value inputs.
- **Merge from paste** — add/update fields from a new paste without clearing the form.
- **Edit** — change labels/values, **+ Add field**, remove a field (`×`).
- **Export** — **Copy text** to clipboard or **Save .txt** via a native file picker.

### Parsing rules (all supported, mixable in one paste)
- Same-line: `Client Name: John Doe`
- Empty markers: `Customer Name: (empty)` or a blank value
- Label block (label line, optional blank line, value on the next line):

  ```
  TICKET ID:

  INC12345
  ```
- Tolerant of inconsistent spacing and casing.
- Orphan lines (no colon) are folded into the previous value.

### Templates
Built-in templates (Client / Agency, Customer / Precinct, Ticket / Reason,
On-site Visit, Escalation Handoff) plus your own **custom templates**. Each
offers a description, a preview snippet, and **Copy**, **Load**, and
**Load & parse** actions.

In the Templates window you can also:
- **New…** — create a custom template (name, description, sample text).
- **Save current note…** — turn the note you're working on into a template.
- **Edit… / Delete** — manage your custom templates (built-ins are read-only).

Custom templates are stored in `%AppData%\AdamNote\templates.json` and
persist across launches.

### Export formats
- `Label: value` (same line)
- Label on one line, value on the next line
- Optional blank line between fields (toggle)
- Live preview of the output

### Themes
Dark, Light, System (follows Windows), Ocean, and Warm. Choose from
**View ▸ Theme**; the preference is remembered.

---

## Install & run (from source)

Requires **Python 3.9+** on Windows 10/11.

```powershell
# from the project root
py -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python run.py
```

You can also run it as a module: `python -m tech_notes_form`.

## Build a double-clickable .exe

```powershell
.\.venv\Scripts\Activate.ps1
pip install pyinstaller
python build_exe.py
```

The packaged app appears in `dist\AdamNote\` (run `AdamNote.exe`).
Edit `build_exe.py` and enable `--onefile` for a single-file build.

---

## Where drafts are saved

Everything is stored **app-locally**, not in browser storage:

- Windows: `%AppData%\AdamNote\`
  - `draft.json` — auto-saved current note (fields, paste text, export options)
  - `settings.json` — theme preference
  - `templates.json` — your custom templates
- Other OSes (for development): `~/.config/AdamNote/`

The draft auto-saves as you type and on exit, and is restored on the next launch.

---

## Layout
The window has three resizable panels (drag the dividers). The **Form** takes
most of the width by default. **Import** and **Export** are collapsible — click
the `«` / `»` button in their header, or use the **Preferences / Import Panel /
Export Panel** controls on the right of the menu bar row (next to File / View /
Help), the shortcuts below, to give the Form even more room. The current
**version** is shown on the far right of that same row. Value boxes auto-size to
fit their content as you type.

## Preferences
Open **Preferences** from the menu-bar row or `Ctrl+,`:
- **Persistent sidebars** *(on by default)* — when a side panel is collapsed,
  keep a thin reopen button (`›` / `‹`) docked on that edge so you can bring it
  back instantly.
- **Compact mode** — tighter spacing and fonts so the app stays usable in small
  / narrow windows. The minimum window size is also small for tight areas.

The **theme** (Dark / Light / System / Ocean / Warm) is chosen from
**View ▸ Theme**. Preferences and theme are saved to `settings.json` and
restored on the next launch.

## Versioning
The app follows [Semantic Versioning](https://semver.org/) (`MAJOR.MINOR.PATCH`,
currently `v1.0.0`), shown on the far right of the menu-bar row.

## Keyboard shortcuts
- `Ctrl+N` — New note
- `Ctrl+S` — Save export to `.txt`
- `Ctrl+Shift+C` — Copy export to clipboard
- `Ctrl+1` — Show/hide the Import panel
- `Ctrl+3` — Show/hide the Export panel
- `Ctrl+Q` — Quit

## Notes
- Offline-first; no cloud login, database server, or external integrations.
- Single-instance: launching again focuses the existing app.
- Optional system tray icon (click to show/hide; right-click to quit).

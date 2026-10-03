# unotes

A local-first **Markdown notes app** for Ubuntu Unity (GTK3). Your notes are plain `.md` files in a folder you own, with no database and no sync service. Open them in any editor, back them up with anything.

## Features

- **Plain files**: notes live in `~/Notes` (override with `$NOTES_DIR`). The title field is stored as the first `# Title` line and the file is renamed to match.
- **Live Markdown styling** in the editor: headings, bold, italic, strikethrough, inline code, code blocks, quotes, rules and bullets.
- **`[[Wiki links]]`**: type `[[` to open a note picker, click a link to follow it, and see backlinks for the current note.
- **`#tags`** you can click, listed in the sidebar with counts.
- **Tasks**: `- [ ]` checkboxes are clickable, and a Tasks view collects the open ones from every note.
- **Folders, colors and icons** for organizing; pin or star notes; sort by last modified, oldest, or title A-Z / Z-A.
- **Daily notes** with one keystroke.
- **Version history**: automatic snapshots you can browse and restore per note.
- **Trash**: deleted notes can be restored or purged.
- **Attachments**: paste an image (`Ctrl+V`) or drop files onto a note.
- **Quick open / command palette** to jump to or create a note by name.
- **Focus mode**, light and dark themes, and export of a note to `.md` or `.html`.
- **Quick capture** from the command line, ready to bind to a global shortcut.

## Install

```bash
git clone https://github.com/HamzaAkramv15/unotes.git
cd unotes
./install.sh
```

Installs per-user into `~/.local`: the app, its icon, and a `.desktop` entry (with a **New note** quicklist action in the Unity launcher). It runs `sudo apt install` for `python3-gi gir1.2-gtk-3.0 gir1.2-gtksource-4`.

If `~/.local/bin` isn't on your `PATH` yet, log out and back in once.

## Use

```bash
unotes                   # open the app
unotes --new "text"      # quick capture a new note
unotes "Note title"      # open or create a note by title
```

For quick capture from anywhere, add a custom shortcut in **System Settings > Keyboard > Shortcuts > Custom** with the command `~/.local/bin/unotes --new`.

| Shortcut | Action |
| --- | --- |
| `Ctrl+N` | New note |
| `F2` | Rename |
| `Ctrl+K` | Jump to or create a note |
| `Ctrl+L` | Link a note |
| `Ctrl+T` | Today's daily note |
| `Ctrl+F` | Search |
| `Ctrl+P` | Star / unstar |
| `Ctrl+H` | Version history |
| `Ctrl+D` | Move to trash |
| `Ctrl+\` | Focus mode |

Right-click a note for more options.

## Where things are stored

Everything lives inside your notes folder (`~/Notes` by default):

- `*.md`: your notes
- `.trash/`, `.history/`, `.attachments/`: deleted notes, version snapshots, pasted and dropped files
- `.meta.json`: pins, colors, icons and settings

## Uninstall

```bash
./uninstall.sh           # removes the app, keeps your notes
./uninstall.sh --purge   # also deletes your notes folder (asks you to type 'yes')
```

Python and GTK packages are left installed, since other apps may use them.

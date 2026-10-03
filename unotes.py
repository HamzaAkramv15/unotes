#!/usr/bin/env python3
"""unotes - a local-first Markdown notes app for Ubuntu Unity (GTK3).

Notes are plain .md files in ~/Notes (override with $NOTES_DIR). The title field
is stored as the note's first "# Title" line and the file is renamed to match.

  unotes                  open the app
  unotes --new "text"     quick capture (bind this to a global shortcut)
  unotes "Note title"     open or create a note by title

Ctrl+N new | F2 rename | Ctrl+K jump/create | Ctrl+L link a note | Ctrl+T daily note
Ctrl+F search | Ctrl+P star | Ctrl+H history | Ctrl+D trash | Ctrl+\\ focus mode
Right-click a note for options. Click [[links]], #tags and [ ] checkboxes directly.
Typing [[ opens a note picker. Paste an image (Ctrl+V) or drop files to attach them.
"""
import collections
import json
import os
import re
import shutil
import sys
import time
from datetime import datetime
from string import Template

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
from gi.repository import Gdk, GdkPixbuf, Gio, GLib, Gtk, Pango  # noqa: E402

try:
    gi.require_version("GtkSource", "4")
    from gi.repository import GtkSource
except (ValueError, ImportError):
    GtkSource = None

GLib.set_prgname("unotes")
NOTES_DIR = os.path.expanduser(os.environ.get("NOTES_DIR", "~/Notes"))
TRASH_DIR = os.path.join(NOTES_DIR, ".trash")
HIST_DIR = os.path.join(NOTES_DIR, ".history")
ATT_DIR = os.path.join(NOTES_DIR, ".attachments")
META_FILE = os.path.join(NOTES_DIR, ".meta.json")

COLORS = {"purple": "#7b61f0", "blue": "#4a8cf5", "green": "#4cae7b", "yellow": "#e6b73c",
          "orange": "#f59a3d", "red": "#ef5b6b", "pink": "#e86bb0"}
ICONS = ["📝", "💡", "✅", "📚", "💻", "🌙", "❤️", "⭐", "🎵", "🌿"]
THEMES = {
    "dark": dict(bg="#151120", side="#1a1525", list="#1c1728", edit="#161222", text="#ece8f6",
                 dim="#9b94b3", line="rgba(255,255,255,0.08)", hover="rgba(255,255,255,0.06)",
                 sel="#3a2f6e", selline="#6c55d9", accent="#8b6cf6", field="rgba(255,255,255,0.06)",
                 code="rgba(255,255,255,0.10)"),
    "light": dict(bg="#f5f3fb", side="#ece8f6", list="#f2eff9", edit="#ffffff", text="#241f35",
                  dim="#7a7391", line="rgba(0,0,0,0.09)", hover="rgba(0,0,0,0.05)",
                  sel="#e2dafe", selline="#9a82f5", accent="#6f4df0", field="rgba(0,0,0,0.05)",
                  code="rgba(0,0,0,0.07)"),
}
TAG_RE = re.compile(r"(?<![\w&])#([A-Za-z][\w-]*)")
LINK_RE = re.compile(r"\[\[([^\]\n]+)\]\]")
CODE_RE = re.compile(r"```.*?```", re.S)
TASK_RE = re.compile(r"^(\s*[-*] )\[( |x|X)\] (.*)$")
ATT_RE = re.compile(r"(!?)\[([^\]]*)\]\((\.attachments/[^)]+)\)")
IMG_EXT = (".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".svg")
INLINE = [
    (re.compile(r"`[^`\n]+`"), "code"),
    (re.compile(r"\*\*[^*\n]+\*\*"), "bold"),
    (re.compile(r"(?<![*\w])\*[^*\n]+\*(?![*\w])"), "italic"),
    (re.compile(r"~~[^~\n]+~~"), "strike"),
    (LINK_RE, "wikilink"),
    (TAG_RE, "hashtag"),
]
TAG_NAMES = ["h1", "h2", "h3", "bold", "italic", "strike", "code", "codeblock", "quote", "rule",
             "wikilink", "hashtag", "checkbox", "done", "hidden", "bullet"]
SORTS = [("modified", "Last modified"), ("oldest", "Oldest first"),
         ("az", "Title A–Z"), ("za", "Title Z–A")]

CSS = Template("""
window.unotes { background-color: $bg; color: $text; }
headerbar.unotes-header { background-image: none; background-color: $bg; border: none;
    border-bottom: 1px solid $line; box-shadow: none; color: $text; min-height: 46px; }
headerbar.unotes-header .title { color: $text; font-weight: bold; }
headerbar.unotes-header button { color: $dim; background-image: none; background-color: transparent;
    border-color: transparent; box-shadow: none; }
headerbar.unotes-header button:hover { background-color: $hover; color: $text; }
separator { background-color: $line; min-width: 1px; min-height: 1px; }
.sidebar { background-color: $side; }
.listpane { background-color: $list; }
.editpane { background-color: $edit; }
.sidebar list, .listpane list { background: transparent; }
.sidebar row { padding: 8px 12px; margin: 1px 10px; border-radius: 10px; color: $text; }
.sidebar row:hover { background-color: $hover; }
.sidebar row:selected { background-color: $sel; box-shadow: inset 0 0 0 1px $selline; color: $text; }
.sidebar row:selected label, .sidebar row:selected image { color: $text; }
.sidebar row.head-row, .sidebar row.head-row:hover { background: transparent; box-shadow: none;
    padding: 0; margin: 16px 12px 2px 12px; }
.head-row label { font-size: 11pt; font-weight: 600; }
.count, .card-date, .tagline, .dim { color: $dim; }
.count, .card-date { font-size: 9pt; }
.tagline { font-size: 9pt; }
.heart { color: $accent; }
entry.field { background-image: none; background-color: $field; border: 1px solid $line;
    border-radius: 10px; color: $text; box-shadow: none; padding: 7px 10px; min-height: 0; }
entry.field:focus { border-color: $selline; }
button.accent-btn { background-image: none; background-color: $accent; color: white; border: none;
    border-radius: 10px; min-width: 36px; min-height: 36px; padding: 0; box-shadow: none; }
button.accent-btn:hover { background-color: $selline; }
button.soft-btn { background-image: none; background-color: $field; color: $dim; border: 1px solid $line;
    border-radius: 10px; min-width: 36px; min-height: 36px; padding: 0; box-shadow: none; }
button.soft-btn:hover { color: $text; }
button.tool { background-image: none; background-color: transparent; border: none; box-shadow: none;
    color: $dim; padding: 6px 9px; border-radius: 8px; min-height: 0; min-width: 0; }
button.tool:hover, button.tool:checked { background-color: $hover; color: $text; }
button.starred, button.starred:hover { color: #f5b83d; }
.notelist { background: transparent; }
.notelist row { margin: 2px 10px; padding: 10px; border-radius: 12px; background: transparent;
    border: 1px solid transparent; color: $text; }
.notelist row:hover { background-color: $hover; }
.notelist row:selected { background-color: $sel; border-color: $selline; color: $text; }
.notelist row:selected label { color: $text; }
.card-title { font-weight: 600; }
.card-snip { color: $dim; font-size: 10pt; }
.notelist row:selected .card-snip, .notelist row:selected .card-date { color: $text; opacity: 0.75; }
.tile { border-radius: 11px; background-color: #6e6a85; }
.tile image, .tile label { color: white; }
.list-head { font-size: 17pt; font-weight: bold; margin: 16px 14px 4px 14px; }
.editor, .editor text { background-color: $edit; color: $text;
    font-family: "Ubuntu", "Cantarell", sans-serif; font-size: 12pt; }
.editor text selection, .editor selection { background-color: $accent; color: white; }
entry.title-entry { font-size: 21pt; font-weight: 600; color: $text; background: transparent;
    background-image: none; border: none; box-shadow: none; padding: 0; margin: 0; min-height: 0; }
.subtitle { color: $dim; font-size: 10pt; }
button.chip { padding: 0 9px; min-height: 0; border-radius: 99px; border: none; box-shadow: none;
    background-image: none; font-size: 8.5pt; background-color: $sel; color: $text; }
button.chip:hover { background-color: $selline; }
button.swatch { min-width: 18px; min-height: 18px; padding: 0; border-radius: 99px;
    border: 2px solid $line; background-image: none; }
.toolbar-row { border-top: 1px solid $line; padding: 8px 18px; }
.links-row { padding: 4px 18px; color: $dim; font-size: 9pt; }
.links-row button { padding: 0 6px; min-height: 0; color: $accent; }
.banner { background-color: rgba(245,184,61,0.16); padding: 8px 18px; }
.tasks-title { font-size: 17pt; font-weight: bold; margin: 16px 14px 4px 14px; }
.task-src { color: $dim; font-size: 8.5pt; padding: 0; min-height: 0; }
combobox.field button { background-image: none; background-color: $field; color: $text;
    border: 1px solid $line; border-radius: 10px; box-shadow: none; padding: 5px 10px; min-height: 0; }
check { background-image: none; background-color: $field; border: 1px solid $line; border-radius: 6px;
    min-width: 18px; min-height: 18px; box-shadow: none; }
check:checked { background-color: $accent; border-color: $accent; color: white; }
.empty { color: $dim; padding: 24px; }
.empty-title { font-size: 17pt; font-weight: bold; }
""")


def build_css(theme):
    css = CSS.safe_substitute(**THEMES[theme])
    for k, v in COLORS.items():
        css += f".tile-{k} {{ background-color: {v}; }}\nbutton.swatch-{k} {{ background-color: {v}; }}\n"
        css += f".fcol-{k} {{ color: {v}; }}\n"
    return css


esc = GLib.markup_escape_text


def rgba(s):
    c = Gdk.RGBA()
    c.parse(s)
    return c


def when(ts):
    dt = datetime.fromtimestamp(ts)
    today = datetime.now().date()
    if dt.date() == today:
        return dt.strftime("%H:%M")
    if (today - dt.date()).days == 1:
        return "Yesterday"
    return dt.strftime("%b %d" if dt.year == today.year else "%b %d, %Y")


def split_text(text):
    """'# Title\\n\\nbody' -> ('Title', 'body'); text without a title -> ('', text)."""
    first, _, rest = text.partition("\n")
    if first.startswith("# "):
        return first[2:].strip(), (rest[1:] if rest.startswith("\n") else rest)
    return "", text


def compose_text(title, body):
    title = " ".join(title.split())
    return f"# {title}\n\n{body}" if title else body


def toggle_line(text, i):
    lines = text.split("\n")
    m = TASK_RE.match(lines[i]) if i < len(lines) else None
    if m:
        lines[i] = m.group(1) + ("[x] " if m.group(2) == " " else "[ ] ") + m.group(3)
    return "\n".join(lines)


def delete_line(text, i):
    lines = text.split("\n")
    if i < len(lines):
        del lines[i]
    return "\n".join(lines)


def clean_folder(name):
    parts = [re.sub(r'[\\:*?"<>|]', "-", p).strip() for p in name.split("/")]
    return "/".join(p for p in parts if p not in ("", ".", ".."))


def clean_name(name):
    return re.sub(r'[\\/:*?"<>|\n]', "-", name).strip(" .")[:80]


def folder_color(name):
    return list(COLORS)[sum(map(ord, name)) % len(COLORS)]


def md_to_html(title, text):
    def inl(s):
        s = esc(s)
        s = re.sub(r"`([^`]+)`", r"<code>\1</code>", s)
        s = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", s)
        s = re.sub(r"(?<![*\w])\*([^*]+)\*(?![*\w])", r"<i>\1</i>", s)
        s = re.sub(r"~~(.+?)~~", r"<s>\1</s>", s)
        return re.sub(r"\[\[([^\]]+)\]\]", r"<u>\1</u>", s)

    out, code, ul = [], False, False
    for line in text.split("\n"):
        if line.lstrip().startswith("```"):
            if ul:
                out.append("</ul>")
                ul = False
            out.append("</pre>" if code else "<pre>")
            code = not code
            continue
        if code:
            out.append(esc(line))
            continue
        t = TASK_RE.match(line)
        b = re.match(r"^\s*[-*] (.*)", line)
        h = re.match(r"^(#{1,3}) (.*)", line)
        if t or b:
            if not ul:
                out.append("<ul>")
                ul = True
            if t:
                out.append("<li>%s %s</li>" % ("☑" if t.group(2) != " " else "☐", inl(t.group(3))))
            else:
                out.append(f"<li>{inl(b.group(1))}</li>")
            continue
        if ul:
            out.append("</ul>")
            ul = False
        if h:
            lv = len(h.group(1)) + 1
            out.append(f"<h{lv}>{inl(h.group(2))}</h{lv}>")
        elif line.startswith(">"):
            out.append(f"<blockquote>{inl(line[1:].strip())}</blockquote>")
        elif re.match(r"^(---|\*\*\*)\s*$", line):
            out.append("<hr>")
        elif line.strip():
            out.append(f"<p>{inl(line)}</p>")
    if ul:
        out.append("</ul>")
    if code:
        out.append("</pre>")
    style = ("body{font:16px/1.6 Ubuntu,sans-serif;max-width:720px;margin:40px auto;padding:0 16px}"
             "pre,code{background:#eee;padding:2px 4px;border-radius:4px}pre{padding:12px}")
    return (f"<!doctype html><meta charset=utf-8><title>{esc(title)}</title><style>{style}</style>"
            f"<h1>{esc(title)}</h1>\n" + "\n".join(out))


# --------------------------------------------------------------------- storage
class Note:
    def __init__(self, nid, text, mtime):
        self.id, self.text, self.mtime = nid, text, mtime
        self.last_snap = 0
        self.trashed, self.trash_path, self.key = False, None, None

    @property
    def path(self):
        return self.trash_path if self.trashed else os.path.join(NOTES_DIR, self.id + ".md")

    @property
    def folder(self):
        return os.path.dirname(self.id)

    def _lines(self):
        return [l.strip().lstrip("#").strip() for l in self.text.splitlines() if l.strip()]

    @property
    def title(self):
        ls = self._lines()
        return ls[0][:80] if ls else "Untitled"

    @property
    def snippet(self):
        raw = [l.strip() for l in self.text.splitlines() if l.strip()][1:3]
        out = []
        for l in raw:
            l = re.sub(r"^[-*] \[ \] ", "☐ ", l)
            l = re.sub(r"^[-*] \[[xX]\] ", "☑ ", l)
            l = re.sub(r"^[-*] ", "• ", l)
            l = re.sub(r"^#+\s*", "", l)
            out.append(re.sub(r"[*`]|\[\[|\]\]|^>\s*", "", l)[:80])
        return "\n".join(out)

    @property
    def tags(self):
        return {t.lower() for t in TAG_RE.findall(CODE_RE.sub("", self.text))}


class Store:
    def __init__(self):
        os.makedirs(NOTES_DIR, exist_ok=True)
        self.notes, self.trash = {}, {}
        self.pinned, self.colors, self.icons, self.settings = set(), {}, {}, {}
        try:
            with open(META_FILE) as f:
                meta = json.load(f)
            self.pinned = set(meta.get("pinned", []))
            self.colors = dict(meta.get("colors", {}))
            self.icons = dict(meta.get("icons", {}))
            self.settings = dict(meta.get("settings", {}))
        except (OSError, ValueError):
            pass
        for root, dirs, files in os.walk(NOTES_DIR):
            dirs[:] = [d for d in dirs if not d.startswith(".")]
            for fn in files:
                if fn.endswith(".md") and not fn.startswith("."):
                    p = os.path.join(root, fn)
                    try:
                        with open(p, encoding="utf-8") as f:
                            nid = os.path.relpath(p, NOTES_DIR)[:-3]
                            self.notes[nid] = Note(nid, f.read(), os.path.getmtime(p))
                    except OSError:
                        pass
        if os.path.isdir(TRASH_DIR):
            for fn in os.listdir(TRASH_DIR):
                if fn.endswith(".md"):
                    p = os.path.join(TRASH_DIR, fn)
                    try:
                        with open(p, encoding="utf-8") as f:
                            t = Note(fn[:-3].rsplit("@", 1)[0].replace("__", "/"), f.read(), os.path.getmtime(p))
                    except OSError:
                        continue
                    t.trashed, t.trash_path, t.key = True, p, fn[:-3]
                    self.trash[t.key] = t

    def _meta(self):
        with open(META_FILE, "w") as f:
            json.dump({"pinned": sorted(self.pinned), "colors": self.colors,
                       "icons": self.icons, "settings": self.settings}, f)

    def set_setting(self, k, v):
        self.settings[k] = v
        self._meta()

    # notes
    def new(self, text="", folder=""):
        base = (folder + "/" if folder else "") + time.strftime("%Y%m%d-%H%M%S")
        nid, i = base, 1
        while nid in self.notes:
            i += 1
            nid = f"{base}-{i}"
        n = Note(nid, text, time.time())
        self.notes[nid] = n
        self.save(n)
        return n

    def new_titled(self, title, body="", folder=""):
        n = self.new(compose_text(title, body), folder)
        self.rename(n, title)
        return n

    def save(self, n):
        now = time.time()
        if n.last_snap == 0 and os.path.exists(n.path):  # keep the pre-edit state
            try:
                with open(n.path, encoding="utf-8") as f:
                    self.snapshot(n, f.read())
            except OSError:
                pass
            n.last_snap = now
        elif now - n.last_snap > 120:
            self.snapshot(n, n.text)
            n.last_snap = now
        n.mtime = now
        os.makedirs(os.path.dirname(n.path), exist_ok=True)
        tmp = n.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(n.text)
        os.replace(tmp, n.path)

    def remove(self, n, to_trash=True):
        self.notes.pop(n.id, None)
        if n.id in self.pinned or n.id in self.colors or n.id in self.icons:
            self.pinned.discard(n.id)
            self.colors.pop(n.id, None)
            self.icons.pop(n.id, None)
            self._meta()
        if not os.path.exists(n.path):
            return
        if to_trash:
            os.makedirs(TRASH_DIR, exist_ok=True)
            stem = n.id.replace("/", "__") + "@" + str(int(time.time()))
            dst = os.path.join(TRASH_DIR, stem + ".md")
            shutil.move(n.path, dst)
            t = Note(n.id, n.text, time.time())
            t.trashed, t.trash_path, t.key = True, dst, stem
            self.trash[stem] = t
        else:
            os.remove(n.path)

    def restore(self, t):
        base, nid, i = t.id, t.id, 1
        while nid in self.notes:
            i += 1
            nid = f"{base}-{i}"
        dst = os.path.join(NOTES_DIR, nid + ".md")
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.move(t.trash_path, dst)
        self.trash.pop(t.key, None)
        n = Note(nid, t.text, time.time())
        self.notes[nid] = n
        return n

    def purge(self, t):
        try:
            os.remove(t.trash_path)
        except OSError:
            pass
        self.trash.pop(t.key, None)

    def toggle_pin(self, n):
        self.pinned ^= {n.id}
        self._meta()

    def set_color(self, n, name):
        if name:
            self.colors[n.id] = name
        else:
            self.colors.pop(n.id, None)
        self._meta()

    def set_icon(self, n, icon):
        if icon:
            self.icons[n.id] = icon
        else:
            self.icons.pop(n.id, None)
        self._meta()

    def _relocate(self, n, new_id):
        base, i = new_id, 1
        while new_id in self.notes:
            i += 1
            new_id = f"{base}-{i}"
        dst = os.path.join(NOTES_DIR, new_id + ".md")
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        if os.path.exists(n.path):
            os.replace(n.path, dst)
        old_hist, old_id = self.hist_dir(n), n.id
        del self.notes[old_id]
        n.id = new_id
        self.notes[new_id] = n
        changed = False
        if old_id in self.pinned:
            self.pinned.discard(old_id)
            self.pinned.add(new_id)
            changed = True
        for d in (self.colors, self.icons):
            if old_id in d:
                d[new_id] = d.pop(old_id)
                changed = True
        if changed:
            self._meta()
        if os.path.isdir(old_hist):
            try:
                os.replace(old_hist, self.hist_dir(n))
            except OSError:
                pass

    def move(self, n, folder):
        new_id = (folder + "/" if folder else "") + os.path.basename(n.id)
        if new_id != n.id:
            self._relocate(n, new_id)

    def rename(self, n, title):
        base = clean_name(title)
        if not base:
            return
        new_id = (n.folder + "/" if n.folder else "") + base
        if new_id != n.id and not re.fullmatch(re.escape(new_id) + r"-\d+", n.id):
            self._relocate(n, new_id)

    # folders
    def folders(self):
        found = {n.folder for n in self.notes.values() if n.folder}
        try:
            found |= {e.name for e in os.scandir(NOTES_DIR)
                      if e.is_dir() and not e.name.startswith(".")}
        except OSError:
            pass
        return sorted(found, key=str.lower)

    def make_folder(self, name):
        name = clean_folder(name)
        if name:
            os.makedirs(os.path.join(NOTES_DIR, name), exist_ok=True)
        return name

    # search / tasks
    def query(self, q):
        tags, words = [], []
        for t in q.lower().split():
            if t.startswith("tag:"):
                tags.append(t[4:])
            elif t.startswith("#"):
                tags.append(t[1:])
            else:
                words.append(t)
        tags = [t for t in tags if t]
        out = [n for n in self.notes.values()
               if all(w in n.text.lower() for w in words) and all(t in n.tags for t in tags)]
        out.sort(key=lambda n: -n.mtime)
        return out

    def find(self, q, limit=8):
        ql = q.strip().lower()
        notes = list(self.notes.values())
        if not ql:
            return sorted(notes, key=lambda n: -n.mtime)[:limit]
        hits = [n for n in notes if ql in n.title.lower() or ql in n.text.lower()]
        hits.sort(key=lambda n: (not n.title.lower().startswith(ql),
                                 ql not in n.title.lower(), -n.mtime))
        return hits[:limit]

    def by_title(self, title):
        for n in self.notes.values():
            if n.title.lower() == title.strip().lower():
                return n

    def backlinks(self, n):
        key = f"[[{n.title}]]".lower()
        return [m for m in self.notes.values() if m.id != n.id and key in m.text.lower()]

    def tasks(self):
        out = []
        for n in sorted(self.notes.values(), key=lambda n: -n.mtime):
            code = False
            for i, line in enumerate(n.text.split("\n")):
                if line.lstrip().startswith("```"):
                    code = not code
                elif not code:
                    m = TASK_RE.match(line)
                    if m:
                        out.append((n, i, m.group(2) != " ", m.group(3)))
        out.sort(key=lambda t: t[2])
        return out

    # history
    def hist_dir(self, n):
        return os.path.join(HIST_DIR, n.id.replace("/", "__"))

    def versions(self, n):
        d = self.hist_dir(n)
        out = []
        if os.path.isdir(d):
            for fn in sorted(os.listdir(d), reverse=True):
                try:
                    ts = datetime.strptime(fn[:-3], "%Y%m%d-%H%M%S").timestamp()
                except ValueError:
                    continue
                out.append((ts, os.path.join(d, fn)))
        return out

    def snapshot(self, n, text):
        if not text.strip():
            return
        vs = self.versions(n)
        if vs:
            try:
                with open(vs[0][1], encoding="utf-8") as f:
                    if f.read() == text:
                        return
            except OSError:
                pass
        d = self.hist_dir(n)
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, time.strftime("%Y%m%d-%H%M%S") + ".md"), "w", encoding="utf-8") as f:
            f.write(text)
        for _, old in self.versions(n)[60:]:
            try:
                os.remove(old)
            except OSError:
                pass

    def checkpoint(self, n):
        self.snapshot(n, n.text)
        n.last_snap = time.time()


# ---------------------------------------------------------------------- window
class Win(Gtk.ApplicationWindow):
    def __init__(self, app, store):
        super().__init__(application=app, title="unotes")
        self.store = store
        self.current = None
        self.filter = ("all",)
        self.loading = self.dirty = self.edited = self.focus_mode = self.hot = False
        self.list_lock = self.side_lock = self.task_lock = False
        self.save_id = self.style_id = 0
        self.margin_now = -1
        self.prev_len = 0
        self.task_target_id = None
        self.task_ids = [None]
        self.thumbs = {}
        self.theme = store.settings.get("theme", "dark")
        self.set_default_size(1240, 760)
        self.get_style_context().add_class("unotes")

        self.css = Gtk.CssProvider()
        Gtk.StyleContext.add_provider_for_screen(
            Gdk.Screen.get_default(), self.css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

        self.build_header()
        self.build_sidebar()
        self.build_middle()
        self.build_editor()

        self.sep1 = Gtk.Separator(orientation=Gtk.Orientation.VERTICAL)
        self.sep2 = Gtk.Separator(orientation=Gtk.Orientation.VERTICAL)
        root = Gtk.Box()
        for w, expand in [(self.side_box, False), (self.sep1, False), (self.mid_box, False),
                          (self.sep2, False), (self.ed_box, True)]:
            root.pack_start(w, expand, expand, 0)
        self.panels = [self.side_box, self.sep1, self.mid_box, self.sep2]
        self.add(root)
        self.apply_theme()

        self.connect("key-press-event", self.on_key)
        self.connect("delete-event", self.on_delete)

        if not self.store.notes:
            self.store.new_titled(
                "Welcome to unotes",
                "Notes are plain Markdown files in ~/Notes, saved automatically. The title "
                "above names the note and its file.\n\n## Try it\n- [ ] Click this checkbox\n"
                "- [x] Right-click a note for options\n"
                "- [ ] Click a [[Link to another note]] to create and open it\n"
                "- Tag things with #ideas and search them from the sidebar\n\n"
                "> Quick capture: bind `unotes --new` to a keyboard shortcut.\n\n"
                "```c\nint main(void) { return 0; }\n```\n")
        self.refresh_list()
        first = self.sorted_notes(self.store.query(""))
        if first:
            self.open_note(first[0])

    # ---- theme
    def apply_theme(self):
        t = THEMES[self.theme]
        try:
            self.css.load_from_data(build_css(self.theme).encode())
        except GLib.Error as e:
            print("CSS error:", e, file=sys.stderr)
        Gtk.Settings.get_default().props.gtk_application_prefer_dark_theme = self.theme == "dark"
        if hasattr(self, "tag_obj"):
            g = self.tag_obj
            g["wikilink"].props.foreground = t["accent"]
            g["hashtag"].props.foreground = t["accent"]
            g["checkbox"].props.foreground = t["accent"]
            g["bullet"].props.foreground = t["accent"]
            for name in ("quote", "rule", "done"):
                g[name].props.foreground_rgba = rgba(t["dim"])
            g["code"].props.background_rgba = rgba(t["code"])
            g["codeblock"].props.paragraph_background_rgba = rgba(t["code"])

    def toggle_theme(self):
        self.theme = "light" if self.theme == "dark" else "dark"
        self.store.set_setting("theme", self.theme)
        self.apply_theme()

    # ---- construction
    def tool_btn(self, icon=None, label=None, tip="", cb=None):
        b = Gtk.Button(relief=Gtk.ReliefStyle.NONE)
        b.get_style_context().add_class("tool")
        b.add(Gtk.Image.new_from_icon_name(icon, Gtk.IconSize.BUTTON) if icon else Gtk.Label(label=label))
        b.set_tooltip_text(tip)
        b.set_can_focus(False)
        if cb:
            b.connect("clicked", lambda *_: cb())
        return b

    def build_header(self):
        self.header = Gtk.HeaderBar(show_close_button=True, title="Notes")
        self.header.get_style_context().add_class("unotes-header")
        self.set_titlebar(self.header)
        jump = self.tool_btn("system-search-symbolic", tip="Jump to / create a note (Ctrl+K)", cb=self.quick_open)
        self.header.pack_start(jump)

        menu = Gtk.MenuButton()
        menu.get_style_context().add_class("tool")
        menu.add(Gtk.Image.new_from_icon_name("open-menu-symbolic", Gtk.IconSize.BUTTON))
        pop = Gtk.Popover()
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, margin=8)
        for label, cb in [("Jump to note      Ctrl+K", self.quick_open),
                          ("Daily note      Ctrl+T", self.open_daily),
                          ("Focus mode      Ctrl+\\", self.toggle_focus),
                          ("Switch light / dark theme", self.toggle_theme),
                          ("Empty trash…", self.empty_trash)]:
            b = Gtk.ModelButton(text=label, halign=Gtk.Align.FILL)
            b.connect("clicked", lambda _b, cb=cb: (pop.popdown(), cb()))
            box.pack_start(b, False, False, 0)
        box.show_all()
        pop.add(box)
        menu.set_popover(pop)
        self.header.pack_end(menu)

    def build_sidebar(self):
        self.side = Gtk.ListBox()
        self.side.connect("row-selected", self.on_side_selected)
        sc = Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER)
        sc.add(self.side)
        tag = Gtk.Label(label="Small notes,\nbig dreams.", justify=Gtk.Justification.CENTER)
        tag.get_style_context().add_class("tagline")
        heart = Gtk.Label(label="—  ♥  —")
        heart.get_style_context().add_class("heart")
        foot = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6, margin_bottom=22, margin_top=10)
        foot.pack_start(tag, False, False, 0)
        foot.pack_start(heart, False, False, 0)
        self.side_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.side_box.get_style_context().add_class("sidebar")
        self.side_box.pack_start(Gtk.Box(margin_top=10), False, False, 0)
        self.side_box.pack_start(sc, True, True, 0)
        self.side_box.pack_start(foot, False, False, 0)
        self.side_box.set_size_request(236, -1)

    def build_middle(self):
        self.search = Gtk.SearchEntry(placeholder_text="Search notes…")
        self.search.get_style_context().add_class("field")
        self.search.connect("search-changed", lambda *_: self.refresh_list())

        sort = Gtk.MenuButton()
        sort.get_style_context().add_class("soft-btn")
        sort.add(Gtk.Image.new_from_icon_name("view-sort-descending-symbolic", Gtk.IconSize.BUTTON))
        sort.set_tooltip_text("Sort notes")
        pop = Gtk.Popover()
        sbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, margin=8)
        for key, label in SORTS:
            b = Gtk.ModelButton(text=label, halign=Gtk.Align.FILL)
            b.connect("clicked", lambda _b, key=key: (pop.popdown(), self.set_sort(key)))
            sbox.pack_start(b, False, False, 0)
        sbox.show_all()
        pop.add(sbox)
        sort.set_popover(pop)

        plus = Gtk.Button.new_from_icon_name("list-add-symbolic", Gtk.IconSize.BUTTON)
        plus.get_style_context().add_class("accent-btn")
        plus.set_tooltip_text("New note (Ctrl+N)")
        plus.connect("clicked", lambda *_: self.new_note())
        top = Gtk.Box(spacing=8, margin=12)
        top.pack_start(self.search, True, True, 0)
        top.pack_start(sort, False, False, 0)
        top.pack_start(plus, False, False, 0)

        self.nl = Gtk.ListBox()
        self.nl.get_style_context().add_class("notelist")
        self.nl.connect("row-selected", self.on_note_row)
        ph = Gtk.Label(label="No notes here yet", wrap=True)
        ph.get_style_context().add_class("empty")
        ph.show()
        self.nl.set_placeholder(ph)
        self.nl_scroll = Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER)
        self.nl_scroll.add(self.nl)
        notes_page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        notes_page.pack_start(top, False, False, 0)
        notes_page.pack_start(self.nl_scroll, True, True, 0)

        # tasks page: add-a-task row + list
        self.task_entry = Gtk.Entry(placeholder_text="Add a task…")
        self.task_entry.get_style_context().add_class("field")
        self.task_entry.connect("activate", lambda *_: self.add_task())
        add = Gtk.Button.new_from_icon_name("list-add-symbolic", Gtk.IconSize.BUTTON)
        add.get_style_context().add_class("accent-btn")
        add.set_tooltip_text("Add task")
        add.connect("clicked", lambda *_: self.add_task())
        arow = Gtk.Box(spacing=8, margin_start=12, margin_end=12, margin_top=6)
        arow.pack_start(self.task_entry, True, True, 0)
        arow.pack_start(add, False, False, 0)
        self.task_target = Gtk.ComboBoxText()
        self.task_target.get_style_context().add_class("field")
        self.task_target.connect("changed", self.on_task_target)
        trow = Gtk.Box(spacing=8, margin_start=12, margin_end=12, margin_top=8, margin_bottom=6)
        lbl = Gtk.Label(label="Add to")
        lbl.get_style_context().add_class("dim")
        trow.pack_start(lbl, False, False, 0)
        trow.pack_start(self.task_target, True, True, 0)
        self.tl = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE)
        self.tl.get_style_context().add_class("notelist")
        tph = Gtk.Label(label="No tasks yet. Add one above.", wrap=True)
        tph.get_style_context().add_class("empty")
        tph.show()
        self.tl.set_placeholder(tph)
        tsc = Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER)
        tsc.add(self.tl)
        ttitle = Gtk.Label(label="Tasks", xalign=0)
        ttitle.get_style_context().add_class("tasks-title")
        tasks_page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        for w in (ttitle, arow, trow):
            tasks_page.pack_start(w, False, False, 0)
        tasks_page.pack_start(tsc, True, True, 0)

        self.stack = Gtk.Stack()
        for page, name in ((notes_page, "notes"), (tasks_page, "tasks")):
            page.show()
            self.stack.add_named(page, name)
        self.mid_box = Gtk.Box()
        self.mid_box.get_style_context().add_class("listpane")
        self.mid_box.pack_start(self.stack, True, True, 0)
        self.mid_box.set_size_request(370, -1)

    def logo(self, size):
        try:
            return Gtk.Image.new_from_pixbuf(Gtk.IconTheme.get_default().load_icon("unotes", size, 0))
        except GLib.Error:
            pass
        path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "unotes.svg")
        try:
            return Gtk.Image.new_from_pixbuf(GdkPixbuf.Pixbuf.new_from_file_at_size(path, size, size))
        except GLib.Error:
            return Gtk.Image.new_from_icon_name("accessories-text-editor", Gtk.IconSize.DIALOG)

    def build_editor(self):
        if GtkSource:
            self.buf = GtkSource.Buffer()
            self.view = GtkSource.View(buffer=self.buf, auto_indent=True)
        else:
            self.buf = Gtk.TextBuffer()
            self.view = Gtk.TextView(buffer=self.buf)
        self.view.get_style_context().add_class("editor")
        self.view.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        self.view.set_top_margin(14)
        self.view.set_bottom_margin(40)
        self.view.set_pixels_below_lines(6)
        self.view.set_pixels_inside_wrap(3)
        self.make_tags()
        self.buf.connect("changed", self.on_changed)
        self.view.add_events(Gdk.EventMask.POINTER_MOTION_MASK)
        self.view.connect("button-release-event", self.on_release)
        self.view.connect("motion-notify-event", self.on_motion)
        self.view.connect("paste-clipboard", self.on_paste)
        self.view.connect("size-allocate", self.on_view_size)
        self.view.drag_dest_add_uri_targets()
        self.view.connect("drag-data-received", self.on_drop)
        esw = Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER)
        esw.add(self.view)

        # header: tile, title/subtitle, actions
        self.tile_box = Gtk.Box()
        self.title = Gtk.Entry(has_frame=False, placeholder_text="Add a title…")
        self.title.get_style_context().add_class("title-entry")
        self.title.connect("changed", self.on_changed)
        self.title.connect("activate", lambda *_: self.title_enter())
        self.title.connect("focus-out-event", self.on_title_focus_out)
        self.meta = Gtk.Label(xalign=0)
        self.meta.get_style_context().add_class("subtitle")
        self.chips = Gtk.Box(spacing=6)
        sub = Gtk.Box(spacing=12)
        sub.pack_start(self.meta, False, False, 0)
        sub.pack_start(self.chips, False, False, 0)
        tv = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4, valign=Gtk.Align.CENTER)
        tv.pack_start(self.title, False, False, 0)
        tv.pack_start(sub, False, False, 0)

        self.star_btn = self.tool_btn("non-starred-symbolic", tip="Star (Ctrl+P)", cb=self.toggle_pin)
        self.menu_btn = Gtk.MenuButton()
        self.menu_btn.get_style_context().add_class("tool")
        self.menu_btn.add(Gtk.Image.new_from_icon_name("view-more-symbolic", Gtk.IconSize.BUTTON))
        self.menu_btn.set_popover(self.build_menu())
        self.export_btn = self.tool_btn("send-to-symbolic", tip="Export…", cb=self.export_dialog)
        self.head = Gtk.Box(spacing=14, margin_top=22, margin_bottom=14)
        self.head.pack_start(self.tile_box, False, False, 0)
        self.head.pack_start(tv, True, True, 0)
        for w in (self.star_btn, self.menu_btn, self.export_btn):
            self.head.pack_end(w, False, False, 0)

        # trash banner
        self.banner = Gtk.Box(spacing=10)
        self.banner.get_style_context().add_class("banner")
        self.banner.pack_start(Gtk.Label(label="This note is in the trash."), False, False, 0)
        rb = Gtk.Button(label="Restore")
        rb.connect("clicked", lambda *_: self.restore_current())
        db = Gtk.Button(label="Delete forever")
        db.connect("clicked", lambda *_: self.purge_current())
        self.banner.pack_end(db, False, False, 0)
        self.banner.pack_end(rb, False, False, 0)

        self.att_box = Gtk.Box(spacing=8, margin=8)
        self.att_scroll = Gtk.ScrolledWindow(vscrollbar_policy=Gtk.PolicyType.NEVER)
        self.att_scroll.add(self.att_box)
        self.att_scroll.set_min_content_height(104)

        self.bl_box = Gtk.Box(spacing=2)
        self.bl_box.get_style_context().add_class("links-row")

        # formatting toolbar
        tb = Gtk.Box(spacing=2)
        tb.get_style_context().add_class("toolbar-row")
        items = [
            ("edit-undo-symbolic", None, "Undo (Ctrl+Z)", self.undo),
            ("edit-redo-symbolic", None, "Redo (Ctrl+Shift+Z)", self.redo), None,
            ("format-text-bold-symbolic", None, "Bold", lambda: self.wrap("**")),
            ("format-text-italic-symbolic", None, "Italic", lambda: self.wrap("*")),
            ("format-text-strikethrough-symbolic", None, "Strikethrough", lambda: self.wrap("~~")),
            ("insert-link-symbolic", None, "Link to a note (Ctrl+L)", self.link_picker),
            (None, "</>", "Inline code", lambda: self.wrap("`")), None,
            ("view-list-bullet-symbolic", None, "Bullet list",
             lambda: self.line_prefix("- ", r"^[-*] (?!\[[ xX]\])")),
            ("object-select-symbolic", None, "Checklist",
             lambda: self.line_prefix("- [ ] ", r"^[-*] \[[ xX]\] ")),
            ("view-list-ordered-symbolic", None, "Numbered list", self.numbered)]
        for it in items:
            if it is None:
                s = Gtk.Separator(orientation=Gtk.Orientation.VERTICAL, margin=6)
                tb.pack_start(s, False, False, 4)
            else:
                tb.pack_start(self.tool_btn(*it), False, False, 0)
        tb.pack_end(self.status_widget(), False, False, 6)
        tb.pack_end(self.tool_btn("insert-image-symbolic", tip="Attach image or file", cb=self.attach_dialog),
                    False, False, 0)

        page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        page.get_style_context().add_class("editpane")
        page.pack_start(self.banner, False, False, 0)
        page.pack_start(self.head, False, False, 0)
        page.pack_start(Gtk.Separator(), False, False, 0)
        page.pack_start(esw, True, True, 0)
        page.pack_start(self.bl_box, False, False, 0)
        page.pack_start(self.att_scroll, False, False, 0)
        page.pack_start(tb, False, False, 0)

        empty = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10,
                        halign=Gtk.Align.CENTER, valign=Gtk.Align.CENTER)
        empty.pack_start(self.logo(112), False, False, 6)
        t = Gtk.Label(label="Nothing open")
        t.get_style_context().add_class("empty-title")
        empty.pack_start(t, False, False, 0)
        s = Gtk.Label(label="Pick a note, or start a new one.")
        s.get_style_context().add_class("dim")
        empty.pack_start(s, False, False, 0)
        row = Gtk.Box(spacing=8, halign=Gtk.Align.CENTER, margin_top=8)
        nb = Gtk.Button(label="New note")
        nb.get_style_context().add_class("suggested-action")
        nb.connect("clicked", lambda *_: self.new_note())
        jb = Gtk.Button(label="Jump to note   Ctrl+K")
        jb.connect("clicked", lambda *_: self.quick_open())
        row.pack_start(nb, False, False, 0)
        row.pack_start(jb, False, False, 0)
        empty.pack_start(row, False, False, 0)
        empty_wrap = Gtk.Box()
        empty_wrap.get_style_context().add_class("editpane")
        empty_wrap.pack_start(empty, True, True, 0)

        self.ed_stack = Gtk.Stack()
        for p, name in ((page, "editor"), (empty_wrap, "empty")):
            p.show()
            self.ed_stack.add_named(p, name)
        self.ed_box = Gtk.Box()
        self.ed_box.pack_start(self.ed_stack, True, True, 0)

    def status_widget(self):
        self.status = Gtk.Label()
        self.status.get_style_context().add_class("dim")
        return self.status

    def make_tags(self):
        b = self.buf
        self.tag_obj = {}
        spec = [
            ("h1", dict(scale=1.7, weight=700, pixels_above_lines=14, pixels_below_lines=6)),
            ("h2", dict(scale=1.4, weight=700, pixels_above_lines=10, pixels_below_lines=4)),
            ("h3", dict(scale=1.2, weight=700, pixels_above_lines=8)),
            ("bold", dict(weight=700)),
            ("italic", dict(style=Pango.Style.ITALIC)),
            ("strike", dict(strikethrough=True)),
            ("code", dict(family="monospace")),
            ("codeblock", dict(family="monospace")),
            ("quote", dict(style=Pango.Style.ITALIC)),
            ("rule", {}),
            ("wikilink", dict(underline=Pango.Underline.SINGLE)),
            ("hashtag", {}),
            ("checkbox", dict(weight=700, scale=1.1)),
            ("done", dict(strikethrough=True)),
            ("hidden", dict(invisible=True)),
            ("bullet", dict(weight=700)),
        ]
        for name, props in spec:
            self.tag_obj[name] = b.create_tag(name, **props)

    # ---- note menu (⋮ button and right-click)
    def build_menu(self, rel=None, trash=False):
        pop = Gtk.Popover()
        if rel is not None:
            pop.set_relative_to(rel)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, margin=8, spacing=1)

        def add(label, cb):
            b = Gtk.ModelButton(text=label, halign=Gtk.Align.FILL)
            b.connect("clicked", lambda *_: (pop.popdown(), cb()))
            box.pack_start(b, False, False, 0)

        if trash:
            add("Restore", self.restore_current)
            add("Delete forever", self.purge_current)
        else:
            add("Star / unstar      Ctrl+P", self.toggle_pin)
            add("Rename      F2", self.focus_title)
            sw = Gtk.Box(spacing=6, margin_start=12, margin_top=6, margin_bottom=4)
            sw.pack_start(Gtk.Label(label="Color", xalign=0, margin_end=8), False, False, 0)
            for name in COLORS:
                b = Gtk.Button(relief=Gtk.ReliefStyle.NONE)
                ctx = b.get_style_context()
                ctx.add_class("swatch")
                ctx.add_class(f"swatch-{name}")
                b.set_tooltip_text(name.title())
                b.connect("clicked", lambda _b, name=name: (pop.popdown(), self.set_color(name)))
                sw.pack_start(b, False, False, 0)
            sw.pack_start(self.tool_btn("edit-clear-symbolic", tip="No color",
                                        cb=lambda: (pop.popdown(), self.set_color(None))), False, False, 0)
            box.pack_start(sw, False, False, 0)
            ic = Gtk.FlowBox(max_children_per_line=6, selection_mode=Gtk.SelectionMode.NONE, margin_start=8)
            for e in ICONS:
                ic.add(self.tool_btn(label=e, tip="Set icon",
                                     cb=lambda e=e: (pop.popdown(), self.set_icon(e))))
            ic.add(self.tool_btn("edit-clear-symbolic", tip="Default icon",
                                 cb=lambda: (pop.popdown(), self.set_icon(None))))
            box.pack_start(ic, False, False, 0)
            add("Move to folder…", self.move_dialog)
            add("Duplicate", self.duplicate)
            add("Attach file…", self.attach_dialog)
            add("Version history      Ctrl+H", self.show_history)
            add("Export…", self.export_dialog)
            add("Move to trash      Ctrl+D", self.trash_current)
        box.show_all()
        pop.add(box)
        return pop

    def on_card_press(self, _row, ev, key):
        if ev.button != 3:
            return False
        GLib.idle_add(self.show_card_menu, key)
        return True

    def show_card_menu(self, key):
        n = self.store.notes.get(key) or self.store.trash.get(key)
        if not n:
            return False
        if self.current is not n:
            self.open_note(n)
        for row in self.nl.get_children():
            if getattr(row, "nid", None) == key:
                self.build_menu(row, trash=n.trashed).popup()
                break
        return False

    # ---- sidebar
    def side_row(self, key, label, icon=None, count=None, icon_class=None, hash_=False):
        row = Gtk.ListBoxRow()
        row.key = key
        box = Gtk.Box(spacing=12)
        if icon:
            img = Gtk.Image.new_from_icon_name(icon, Gtk.IconSize.MENU)
            if icon_class:
                img.get_style_context().add_class(icon_class)
            box.pack_start(img, False, False, 0)
        elif hash_:
            box.pack_start(Gtk.Label(label="#"), False, False, 0)
        box.pack_start(Gtk.Label(label=label, xalign=0, ellipsize=Pango.EllipsizeMode.END), True, True, 0)
        if count is not None:
            c = Gtk.Label(label=str(count))
            c.get_style_context().add_class("count")
            box.pack_end(c, False, False, 0)
        row.add(box)
        return row

    def side_head(self, text, plus_cb=None):
        row = Gtk.ListBoxRow(selectable=False, activatable=False)
        row.get_style_context().add_class("head-row")
        box = Gtk.Box()
        box.pack_start(Gtk.Label(label=text, xalign=0), True, True, 0)
        if plus_cb:
            box.pack_end(self.tool_btn("list-add-symbolic", tip="New folder", cb=plus_cb), False, False, 0)
        row.add(box)
        return row

    def rebuild_sidebar(self):
        self.side_lock = True
        for c in self.side.get_children():
            c.destroy()
        notes = list(self.store.notes.values())
        now = time.time()
        open_tasks = sum(1 for t in self.store.tasks() if not t[2])
        rows = [
            self.side_row(("all",), "All Notes", "text-x-generic-symbolic", len(notes)),
            self.side_row(("recent",), "Recent", "document-open-recent-symbolic",
                          sum(1 for n in notes if now - n.mtime < 14 * 86400)),
            self.side_row(("starred",), "Starred", "starred-symbolic",
                          sum(1 for n in notes if n.id in self.store.pinned)),
            self.side_row(("tasks",), "Tasks", "object-select-symbolic", open_tasks),
            self.side_row(("trash",), "Trash", "user-trash-symbolic", len(self.store.trash)),
            self.side_head("Folders", self.new_folder)]
        for f in self.store.folders():
            rows.append(self.side_row(("folder", f), f, "folder-symbolic",
                                      sum(1 for n in notes if n.folder == f),
                                      icon_class=f"fcol-{folder_color(f)}"))
        tags = collections.Counter(t for n in notes for t in n.tags)
        if tags:
            rows.append(self.side_head("Tags"))
            for t, c in sorted(tags.items(), key=lambda kv: (-kv[1], kv[0]))[:30]:
                rows.append(self.side_row(("tag", t), t, None, c, hash_=True))
        for r in rows:
            self.side.add(r)
            if getattr(r, "key", None) == self.filter:
                self.side.select_row(r)
        self.side.show_all()
        self.side_lock = False

    def on_side_selected(self, _lb, row):
        if self.side_lock or not row:
            return
        GLib.idle_add(self.apply_side, row.key)

    def apply_side(self, key):
        self.search.set_text("")
        self.set_filter(key)
        return False

    def set_filter(self, f):
        self.filter = f
        self.stack.set_visible_child_name("tasks" if f[0] == "tasks" else "notes")
        self.refresh_list()

    def set_sort(self, key):
        self.store.set_setting("sort", key)
        self.refresh_list()

    def sorted_notes(self, notes):
        m = self.store.settings.get("sort", "modified")
        if m == "oldest":
            return sorted(notes, key=lambda n: n.mtime)
        if m == "az":
            return sorted(notes, key=lambda n: n.title.lower())
        if m == "za":
            return sorted(notes, key=lambda n: n.title.lower(), reverse=True)
        return sorted(notes, key=lambda n: -n.mtime)

    # ---- note list
    def make_tile(self, n, size):
        box = Gtk.Box(halign=Gtk.Align.START, valign=Gtk.Align.CENTER)
        box.set_size_request(size, size)
        ctx = box.get_style_context()
        ctx.add_class("tile")
        ctx.add_class("tile-" + self.store.colors.get(n.id, "gray"))
        icon = self.store.icons.get(n.id)
        if icon:
            child = Gtk.Label()
            child.set_markup('<span size="%d">%s</span>' % (int(size * 0.4) * 1024, esc(icon)))
        else:
            child = Gtk.Image.new_from_icon_name("text-x-generic-symbolic", Gtk.IconSize.LARGE_TOOLBAR)
            child.set_pixel_size(int(size * 0.5))
        child.set_halign(Gtk.Align.CENTER)
        child.set_valign(Gtk.Align.CENTER)
        box.pack_start(child, True, True, 0)
        return box

    def card(self, n):
        key = n.key if n.trashed else n.id
        row = Gtk.ListBoxRow()
        row.nid = key
        row.connect("button-press-event", self.on_card_press, key)
        box = Gtk.Box(spacing=12)
        box.pack_start(self.make_tile(n, 42), False, False, 0)
        col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2, valign=Gtk.Align.CENTER)
        top = Gtk.Box(spacing=6)
        t = Gtk.Label(label=n.title, xalign=0, ellipsize=Pango.EllipsizeMode.END)
        t.get_style_context().add_class("card-title")
        d = Gtk.Label(label=when(n.mtime))
        d.get_style_context().add_class("card-date")
        top.pack_start(t, True, True, 0)
        top.pack_end(d, False, False, 0)
        col.pack_start(top, False, False, 0)
        if n.snippet:
            s = Gtk.Label(label=n.snippet, xalign=0, wrap=True, lines=2,
                          ellipsize=Pango.EllipsizeMode.END, max_width_chars=30)
            s.get_style_context().add_class("card-snip")
            col.pack_start(s, False, False, 0)
        box.pack_start(col, True, True, 0)
        if n.id in self.store.pinned and not n.trashed:
            star = Gtk.Label()
            star.set_markup('<span foreground="#f5b83d">★</span>')
            star.set_valign(Gtk.Align.END)
            box.pack_end(star, False, False, 0)
        row.add(box)
        return row

    def refresh_list(self):
        if self.filter[0] == "tasks":
            self.refresh_tasks()
            self.rebuild_sidebar()
            return
        kind, q = self.filter[0], self.search.get_text()
        if kind == "trash":
            words = q.lower().split()
            notes = [t for t in self.store.trash.values() if all(w in t.text.lower() for w in words)]
        else:
            notes = self.store.query(q)
            if kind == "starred":
                notes = [n for n in notes if n.id in self.store.pinned]
            elif kind == "recent":
                notes = [n for n in notes if time.time() - n.mtime < 14 * 86400]
            elif kind == "folder":
                notes = [n for n in notes if n.folder == self.filter[1]]
            elif kind == "tag":
                notes = [n for n in notes if self.filter[1] in n.tags]
        notes = self.sorted_notes(notes)
        vadj = self.nl_scroll.get_vadjustment()
        pos = vadj.get_value()
        self.list_lock = True
        for c in self.nl.get_children():
            c.destroy()
        sel = None
        for n in notes:
            row = self.card(n)
            self.nl.add(row)
            if self.current is n:
                sel = row
        self.nl.show_all()
        if sel:
            self.nl.select_row(sel)
        self.list_lock = False
        GLib.idle_add(vadj.set_value, pos)
        self.rebuild_sidebar()

    def on_note_row(self, _lb, row):
        if self.list_lock or not row:
            return
        GLib.idle_add(self.open_by_id, row.nid)

    def open_by_id(self, key):
        n = self.store.notes.get(key) or self.store.trash.get(key)
        if n and n is not self.current:
            self.open_note(n)
        return False

    # ---- tasks view
    def on_task_target(self, combo):
        if self.task_lock:
            return
        i = combo.get_active()
        self.task_target_id = self.task_ids[i] if 0 <= i < len(self.task_ids) else None

    def refresh_tasks(self):
        self.task_lock = True
        self.task_target.remove_all()
        self.task_ids = [None]
        self.task_target.append_text("Tasks (inbox note)")
        for n in sorted(self.store.notes.values(), key=lambda n: -n.mtime)[:25]:
            if n.title != "Tasks":
                self.task_target.append_text(n.title[:42])
                self.task_ids.append(n.id)
        idx = self.task_ids.index(self.task_target_id) if self.task_target_id in self.task_ids else 0
        self.task_target.set_active(idx)
        self.task_lock = False

        for c in self.tl.get_children():
            c.destroy()
        for n, i, done, text in self.store.tasks()[:300]:
            row = Gtk.ListBoxRow(selectable=False)
            box = Gtk.Box(spacing=8)
            cb = Gtk.CheckButton(active=done, valign=Gtk.Align.START)
            cb.connect("toggled", lambda _b, n=n, i=i: self.toggle_task(n, i))
            col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
            lbl = Gtk.Label(xalign=0, wrap=True)
            lbl.set_markup(f"<s>{esc(text)}</s>" if done else esc(text))
            if done:
                lbl.set_opacity(0.5)
            src = Gtk.Button(label=n.title, relief=Gtk.ReliefStyle.NONE, halign=Gtk.Align.START)
            src.get_style_context().add_class("task-src")
            src.connect("clicked", lambda _b, n=n: self.open_from_tasks(n))
            col.pack_start(lbl, False, False, 0)
            col.pack_start(src, False, False, 0)
            rm = self.tool_btn("window-close-symbolic", tip="Delete task",
                               cb=lambda n=n, i=i: self.delete_task(n, i))
            box.pack_start(cb, False, False, 0)
            box.pack_start(col, True, True, 0)
            box.pack_end(rm, False, False, 0)
            row.add(box)
            self.tl.add(row)
        self.tl.show_all()

    def edit_note_text(self, n, new_text):
        if self.current is n:
            self.flush()
        n.text = new_text
        self.store.save(n)
        if self.current is n:
            self.load_buffer(n.text)

    def add_task(self):
        text = self.task_entry.get_text().strip()
        if not text:
            return
        n = self.store.notes.get(self.task_target_id) if self.task_target_id else None
        if not n:
            n = self.store.by_title("Tasks") or self.store.new_titled("Tasks", "")
        if self.current is n:
            self.flush()
        base = n.text.rstrip("\n")
        sep = "\n\n" if base.count("\n") == 0 and base else "\n"
        self.edit_note_text(n, (base + sep if base else "") + f"- [ ] {text}\n")
        self.task_entry.set_text("")
        self.refresh_list()
        self.task_entry.grab_focus()

    def toggle_task(self, n, i):
        self.edit_note_text(n, toggle_line(n.text, i))
        GLib.idle_add(self.refresh_list)

    def delete_task(self, n, i):
        self.edit_note_text(n, delete_line(n.text, i))
        GLib.idle_add(self.refresh_list)

    def open_from_tasks(self, n):
        self.set_filter(("all",))
        self.open_note(n)

    # ---- note operations
    def load_buffer(self, text):
        title, body = split_text(text)
        self.loading = True
        self.title.set_text(title)
        if GtkSource:
            self.buf.begin_not_undoable_action()
        self.buf.set_text(body)
        if GtkSource:
            self.buf.end_not_undoable_action()
        self.loading = False
        self.prev_len = self.buf.get_char_count()
        self.restyle()

    def open_note(self, n):
        self.commit_title(refresh=False)
        self.flush()
        prev = self.current
        if prev is not None and prev is not n and not prev.trashed:
            if self.edited:
                self.store.checkpoint(prev)
            if not prev.text.strip():
                self.store.remove(prev, to_trash=False)
        self.edited = False
        self.current = n
        ro = n.trashed
        self.view.set_editable(not ro)
        self.title.set_editable(not ro)
        self.banner.set_visible(ro)
        self.load_buffer(n.text)
        self.refresh_list()
        self.update_footer()

    def new_note(self, text="", folder=None):
        if folder is None:
            folder = self.filter[1] if self.filter[0] == "folder" else ""
        self.search.set_text("")
        if self.filter[0] not in ("all", "folder"):
            self.set_filter(("all",))
        n = self.store.new(text + "\n" if text else "", folder)
        self.open_note(n)
        if text:
            self.view.grab_focus()
        else:
            self.title.grab_focus()

    def open_title(self, title):
        n = self.store.by_title(title) or self.store.new_titled(title.strip())
        self.search.set_text("")
        self.set_filter(("all",))
        self.open_note(n)
        self.view.grab_focus()

    def open_daily(self):
        title = datetime.now().strftime("%A, %d %B %Y")
        n = self.store.by_title(title)
        if not n:
            self.store.make_folder("Daily")
            n = self.store.new_titled(title, "## Plan\n- [ ] \n\n## Notes\n\n", "Daily")
        self.search.set_text("")
        self.set_filter(("all",))
        self.open_note(n)
        self.view.grab_focus()

    def live(self):
        return self.current if self.current and not self.current.trashed else None

    def toggle_pin(self):
        if self.live():
            self.store.toggle_pin(self.current)
            self.refresh_list()
            self.update_footer()

    def set_color(self, name):
        if self.live():
            self.store.set_color(self.current, name)
            self.refresh_list()
            self.update_footer()

    def set_icon(self, icon):
        if self.live():
            self.store.set_icon(self.current, icon)
            self.refresh_list()
            self.update_footer()

    def duplicate(self):
        n = self.live()
        if n:
            self.flush()
            title, body = split_text(n.text)
            c = self.store.new_titled((title or n.title) + " copy", body, n.folder)
            self.open_note(c)

    def trash_current(self):
        n = self.live()
        if not n:
            return
        self.flush()
        self.store.remove(n)
        self.current = None
        self.load_buffer("")
        rest = self.sorted_notes(self.store.query(self.search.get_text()))
        if rest:
            self.open_note(rest[0])
        else:
            self.refresh_list()
            self.update_footer()

    def restore_current(self):
        t = self.current
        if t and t.trashed:
            n = self.store.restore(t)
            self.current = None
            self.set_filter(("all",))
            self.open_note(n)

    def purge_current(self):
        t = self.current
        if not (t and t.trashed):
            return
        dlg = Gtk.MessageDialog(transient_for=self, modal=True, message_type=Gtk.MessageType.WARNING,
                                buttons=Gtk.ButtonsType.CANCEL, text=f"Delete “{t.title}” forever?")
        dlg.add_button("Delete forever", Gtk.ResponseType.OK)
        ok = dlg.run() == Gtk.ResponseType.OK
        dlg.destroy()
        if ok:
            self.store.purge(t)
            self.current = None
            self.load_buffer("")
            self.banner.hide()
            self.view.set_editable(True)
            self.title.set_editable(True)
            self.refresh_list()
            self.update_footer()

    def empty_trash(self):
        if not self.store.trash:
            return
        dlg = Gtk.MessageDialog(transient_for=self, modal=True, message_type=Gtk.MessageType.WARNING,
                                buttons=Gtk.ButtonsType.CANCEL,
                                text=f"Permanently delete {len(self.store.trash)} note(s) in the trash?")
        dlg.add_button("Empty trash", Gtk.ResponseType.OK)
        ok = dlg.run() == Gtk.ResponseType.OK
        dlg.destroy()
        if ok:
            for t in list(self.store.trash.values()):
                self.store.purge(t)
            if self.current and self.current.trashed:
                self.current = None
                self.load_buffer("")
                self.banner.hide()
            self.refresh_list()
            self.update_footer()

    def toggle_focus(self):
        self.focus_mode = not self.focus_mode
        for w in self.panels:
            w.set_visible(not self.focus_mode)

    # ---- titles
    def focus_title(self):
        if self.live():
            self.title.grab_focus()
            self.title.select_region(0, -1)

    def title_enter(self):
        self.commit_title()
        self.view.grab_focus()
        self.buf.place_cursor(self.buf.get_start_iter())

    def on_title_focus_out(self, *_):
        self.commit_title(refresh=False, later=True)
        return False

    def commit_title(self, refresh=True, later=False):
        n = self.current
        title = self.title.get_text().strip()
        if not n or n.trashed or not title:
            return
        self.flush()
        old = n.id
        self.store.rename(n, title)
        if n.id != old:
            self.update_footer()
            if later:
                GLib.timeout_add(250, lambda: (self.refresh_list(), False)[1])
            elif refresh:
                self.refresh_list()

    # ---- dialogs
    def ask_text(self, title, label, default="", choices=()):
        dlg = Gtk.Dialog(title=title, transient_for=self, modal=True)
        dlg.add_button("Cancel", Gtk.ResponseType.CANCEL)
        ok = dlg.add_button("OK", Gtk.ResponseType.OK)
        ok.get_style_context().add_class("suggested-action")
        dlg.set_default_response(Gtk.ResponseType.OK)
        area = dlg.get_content_area()
        area.set_border_width(14)
        area.set_spacing(8)
        area.pack_start(Gtk.Label(label=label, xalign=0), False, False, 0)
        if choices:
            combo = Gtk.ComboBoxText.new_with_entry()
            for c in choices:
                combo.append_text(c)
            entry = combo.get_child()
            area.pack_start(combo, False, False, 0)
        else:
            entry = Gtk.Entry()
            area.pack_start(entry, False, False, 0)
        entry.set_text(default)
        entry.set_activates_default(True)
        area.show_all()
        resp = dlg.run()
        text = entry.get_text()
        dlg.destroy()
        return text if resp == Gtk.ResponseType.OK else None

    def new_folder(self):
        name = self.ask_text("New folder", "Folder name:")
        if name and (name := self.store.make_folder(name)):
            self.set_filter(("folder", name))

    def move_dialog(self):
        if not self.live():
            return
        name = self.ask_text("Move to folder", "Folder (leave empty for none, or type a new one):",
                             self.current.folder, self.store.folders())
        if name is None:
            return
        self.flush()
        self.store.move(self.current, self.store.make_folder(name) if name.strip() else "")
        self.refresh_list()
        self.update_footer()

    def export_dialog(self):
        n = self.current
        if not n:
            return
        self.flush()
        dlg = Gtk.FileChooserNative.new("Export note", self, Gtk.FileChooserAction.SAVE, "Export", "Cancel")
        dlg.set_current_name(clean_name(n.title) + ".md")
        dlg.set_do_overwrite_confirmation(True)
        if dlg.run() == Gtk.ResponseType.ACCEPT and dlg.get_filename():
            path = dlg.get_filename()
            if path.lower().endswith((".html", ".htm")):
                title, body = split_text(n.text)
                data = md_to_html(title or n.title, body)
            else:
                data = n.text
            with open(path, "w", encoding="utf-8") as f:
                f.write(data)

    def build_palette(self):
        dlg = Gtk.Dialog(transient_for=self, modal=True)
        dlg.set_decorated(False)
        dlg.set_default_size(560, -1)
        dlg.set_position(Gtk.WindowPosition.CENTER_ON_PARENT)
        area = dlg.get_content_area()
        area.set_border_width(12)
        area.set_spacing(8)
        entry = Gtk.SearchEntry(placeholder_text="Jump to a note, or type a name to create one…")
        entry.get_style_context().add_class("field")
        lb = Gtk.ListBox()
        lb.get_style_context().add_class("notelist")
        sc = Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER)
        sc.set_min_content_height(300)
        sc.add(lb)
        area.pack_start(entry, False, False, 0)
        area.pack_start(sc, True, True, 0)
        result = {}

        def mkrow(n, title, sub, act):
            row = Gtk.ListBoxRow()
            row.act = act
            box = Gtk.Box(spacing=10)
            if n:
                box.pack_start(self.make_tile(n, 30), False, False, 0)
            t = Gtk.Label(label=title, xalign=0, ellipsize=Pango.EllipsizeMode.END)
            t.get_style_context().add_class("card-title")
            s = Gtk.Label(label=sub)
            s.get_style_context().add_class("card-date")
            box.pack_start(t, True, True, 0)
            box.pack_end(s, False, False, 0)
            row.add(box)
            return row

        def fill(*_):
            for c in lb.get_children():
                c.destroy()
            q = entry.get_text().strip()
            for n in self.store.find(q):
                lb.add(mkrow(n, n.title, n.folder or when(n.mtime), ("open", n)))
            if q and not self.store.by_title(q):
                lb.add(mkrow(None, f"Create “{q}”", "new note", ("create", q)))
            lb.show_all()
            first = lb.get_row_at_index(0)
            if first:
                lb.select_row(first)

        def go(row):
            if row:
                result["act"] = row.act
                dlg.response(Gtk.ResponseType.OK)

        def on_key(_w, ev):
            k = Gdk.keyval_name(ev.keyval)
            row = lb.get_selected_row()
            idx = row.get_index() if row else -1
            if k in ("Down", "Up"):
                nxt = lb.get_row_at_index(idx + (1 if k == "Down" else -1))
                if nxt:
                    lb.select_row(nxt)
                return True
            return False

        entry.connect("search-changed", fill)
        entry.connect("activate", lambda *_: go(lb.get_selected_row()))
        entry.connect("key-press-event", on_key)
        lb.connect("row-activated", lambda _l, r: go(r))
        fill()
        return dlg, entry, lb, result

    def run_palette(self):
        dlg, entry, _lb, result = self.build_palette()
        dlg.show_all()
        entry.grab_focus()
        resp = dlg.run()
        dlg.destroy()
        return result.get("act") if resp == Gtk.ResponseType.OK else None

    def quick_open(self):
        act = self.run_palette()
        if not act:
            return
        if act[0] == "open":
            self.search.set_text("")
            self.set_filter(("all",))
            self.open_note(act[1])
            self.view.grab_focus()
        else:
            self.open_title(act[1])

    def link_picker(self, replace_open=False):
        """Pick (or create) a note and insert [[its title]] at the cursor."""
        if not self.live():
            return
        act = self.run_palette()
        if replace_open:
            ins = self.buf.get_iter_at_mark(self.buf.get_insert())
            st = ins.copy()
            if st.backward_chars(2) and self.buf.get_text(st, ins, True) == "[[":
                if act:
                    self.buf.delete(st, ins)
        if not act:
            return
        if act[0] == "open":
            title = act[1].title
        else:
            title = self.store.new_titled(act[1]).title
            self.refresh_list()
        self.buf.insert_at_cursor(f"[[{title}]]")
        self.view.grab_focus()

    def maybe_link_picker(self):
        self.link_picker(replace_open=True)
        return False

    # ---- formatting toolbar
    def undo(self):
        if GtkSource and self.buf.can_undo():
            self.buf.undo()

    def redo(self):
        if GtkSource and self.buf.can_redo():
            self.buf.redo()

    def wrap(self, a, b=None):
        if not self.live():
            return
        b = a if b is None else b
        buf = self.buf
        if buf.get_has_selection():
            s, e = buf.get_selection_bounds()
            text = buf.get_text(s, e, True)
            if len(text) >= len(a) + len(b) and text.startswith(a) and text.endswith(b):
                new = text[len(a):len(text) - len(b)]
            else:
                new = a + text + b
            buf.begin_user_action()
            buf.delete(s, e)
            buf.insert_at_cursor(new)
            buf.end_user_action()
        else:
            buf.insert_at_cursor(a + b)
            it = buf.get_iter_at_mark(buf.get_insert())
            it.backward_chars(len(b))
            buf.place_cursor(it)
        self.view.grab_focus()

    def selected_lines(self):
        buf = self.buf
        if buf.get_has_selection():
            s, e = buf.get_selection_bounds()
            first, last = s.get_line(), e.get_line()
            if e.starts_line() and last > first:
                last -= 1
        else:
            first = last = buf.get_iter_at_mark(buf.get_insert()).get_line()
        out = []
        for ln in range(first, last + 1):
            a = buf.get_iter_at_line(ln)
            b = a.copy()
            if not b.ends_line():
                b.forward_to_line_end()
            out.append((ln, buf.get_text(a, b, True)))
        return out

    def line_prefix(self, prefix, pat, numbered=False):
        if not self.live():
            return
        lines = self.selected_lines()
        filled = [(ln, t) for ln, t in lines if t.strip()]
        all_have = bool(filled) and all(re.match(pat, t) for _, t in filled)
        buf = self.buf
        buf.begin_user_action()
        for idx, (ln, t) in enumerate(lines):
            a = buf.get_iter_at_line(ln)
            m = re.match(pat, t)
            if all_have:
                if m:
                    b = a.copy()
                    b.forward_chars(len(m.group(0)))
                    buf.delete(a, b)
            elif not m:
                buf.insert(a, f"{idx + 1}. " if numbered else prefix)
        buf.end_user_action()
        self.view.grab_focus()

    def numbered(self):
        self.line_prefix("1. ", r"^\d+\. ", numbered=True)

    # ---- autosave / styling
    def on_changed(self, *_):
        if self.loading or not self.current or self.current.trashed:
            return
        body = self.buf.get_text(*self.buf.get_bounds(), True)
        self.current.text = compose_text(self.title.get_text(), body)
        self.dirty = self.edited = True
        self.status.set_text("Editing…")
        if self.save_id:
            GLib.source_remove(self.save_id)
        self.save_id = GLib.timeout_add(500, self.do_save)
        if not self.style_id:
            self.style_id = GLib.idle_add(self.restyle)
        grew = self.buf.get_char_count() == self.prev_len + 1
        self.prev_len = self.buf.get_char_count()
        if grew and self.view.has_focus():
            ins = self.buf.get_iter_at_mark(self.buf.get_insert())
            st = ins.copy()
            if st.backward_chars(2) and self.buf.get_text(st, ins, True) == "[[":
                GLib.idle_add(self.maybe_link_picker)

    def do_save(self):
        self.save_id = 0
        self.flush()
        self.refresh_list()
        self.update_footer()
        return False

    def flush(self):
        if self.save_id:
            GLib.source_remove(self.save_id)
            self.save_id = 0
        if self.dirty and self.current and not self.current.trashed:
            self.store.save(self.current)
        self.dirty = False

    def on_delete(self, *_):
        self.commit_title(refresh=False)
        self.flush()
        if self.current and self.edited and not self.current.trashed:
            self.store.checkpoint(self.current)
        return False

    def restyle(self):
        self.style_id = 0
        b = self.buf
        start, end = b.get_bounds()
        for name in TAG_NAMES:
            b.remove_tag_by_name(name, start, end)
        text = b.get_text(start, end, True)

        def ap(name, a, z):
            b.apply_tag_by_name(name, b.get_iter_at_offset(a), b.get_iter_at_offset(z))

        off, code = 0, False
        for line in text.split("\n"):
            n = len(line)
            if line.lstrip().startswith("```"):
                code = not code
                ap("codeblock", off, off + n)
            elif code:
                ap("codeblock", off, off + n)
            else:
                h = re.match(r"(#{1,3}) ", line)
                if h:
                    ap("h%d" % len(h.group(1)), off, off + n)
                elif line.startswith(">"):
                    ap("quote", off, off + n)
                elif re.match(r"^(---|\*\*\*)\s*$", line):
                    ap("rule", off, off + n)
                t = TASK_RE.match(line)
                if t:
                    a = len(t.group(1))
                    ap("hidden", off, off + a)
                    ap("checkbox", off + a, off + a + 3)
                    if t.group(2) != " ":
                        ap("done", off + a + 4, off + n)
                else:
                    bl = re.match(r"^(\s*)([-*]|\d+\.) ", line)
                    if bl:
                        ap("bullet", off + len(bl.group(1)), off + bl.end())
                for pat, name in INLINE:
                    for m in pat.finditer(line):
                        ap(name, off + m.start(), off + m.end())
            off += n + 1
        return False

    def on_view_size(self, _w, alloc):
        m = max(24, (alloc.width - 800) // 2)
        if m != self.margin_now:
            self.margin_now = m
            GLib.idle_add(self.apply_margins, m)

    def apply_margins(self, m):
        self.view.set_left_margin(m + 22)
        self.view.set_right_margin(m + 22)
        for w in (self.head, self.bl_box):
            w.set_margin_start(m)
            w.set_margin_end(m)
        return False

    # ---- header, chips, backlinks, attachments, status
    def thumb(self, path):
        if path not in self.thumbs:
            try:
                self.thumbs[path] = GdkPixbuf.Pixbuf.new_from_file_at_scale(path, 130, 84, True)
            except GLib.Error:
                self.thumbs[path] = None
        return self.thumbs[path]

    def update_footer(self):
        n = self.current
        self.ed_stack.set_visible_child_name("editor" if n else "empty")
        for c in self.tile_box.get_children():
            c.destroy()
        for c in self.chips.get_children():
            c.destroy()
        if n:
            self.tile_box.pack_start(self.make_tile(n, 48), False, False, 0)
            self.tile_box.show_all()
            starred = n.id in self.store.pinned and not n.trashed
            ctx = self.star_btn.get_style_context()
            (ctx.add_class if starred else ctx.remove_class)("starred")
            self.star_btn.get_child().set_from_icon_name(
                "starred-symbolic" if starred else "non-starred-symbolic", Gtk.IconSize.BUTTON)
            for w in (self.star_btn, self.menu_btn):
                w.set_sensitive(not n.trashed)
            self.meta.set_text(datetime.fromtimestamp(n.mtime).strftime("%b %d, %Y  •  %H:%M")
                               + (f"  •  {n.folder}" if n.folder else ""))
            for t in sorted(n.tags)[:6]:
                b = Gtk.Button(label="#" + t, relief=Gtk.ReliefStyle.NONE)
                b.get_style_context().add_class("chip")
                b.connect("clicked", lambda _b, t=t: self.set_filter(("tag", t)))
                self.chips.pack_start(b, False, False, 0)
        self.chips.show_all()

        for c in self.bl_box.get_children():
            c.destroy()
        links = self.store.backlinks(n) if n and not n.trashed else []
        if links:
            self.bl_box.pack_start(Gtk.Label(label="Linked from:  "), False, False, 0)
            for m in links[:6]:
                b = Gtk.Button(label=m.title, relief=Gtk.ReliefStyle.NONE)
                b.connect("clicked", lambda _b, note=m: self.open_note(note))
                self.bl_box.pack_start(b, False, False, 0)
        self.bl_box.show_all()
        self.bl_box.set_visible(bool(links))

        for c in self.att_box.get_children():
            c.destroy()
        found = False
        if n:
            for m in ATT_RE.finditer(n.text):
                path = os.path.join(NOTES_DIR, m.group(3))
                if not os.path.exists(path):
                    continue
                found = True
                btn = Gtk.Button(relief=Gtk.ReliefStyle.NONE)
                btn.set_tooltip_text(os.path.basename(path))
                pb = self.thumb(path)
                btn.add(Gtk.Image.new_from_pixbuf(pb) if pb else Gtk.Label(label=os.path.basename(path)))
                btn.connect("clicked", lambda _b, p=path: Gio.AppInfo.launch_default_for_uri(
                    Gio.File.new_for_path(p).get_uri(), None))
                self.att_box.pack_start(btn, False, False, 0)
        self.att_box.show_all()
        self.att_scroll.set_visible(found)
        words = len(n.text.split()) if n else 0
        self.status.set_text(f"Saved  ·  {words} words" if n and not n.trashed else "")

    # ---- attachments
    def insert_ref(self, dst):
        rel = os.path.relpath(dst, NOTES_DIR).replace(os.sep, "/")
        bang = "!" if dst.lower().endswith(IMG_EXT) else ""
        self.buf.insert_at_cursor(f"{bang}[{os.path.basename(dst)}]({rel})\n")

    def attach_path(self, src):
        if not self.live():
            self.new_note()
        os.makedirs(ATT_DIR, exist_ok=True)
        name = os.path.basename(src)
        base, ext = os.path.splitext(name)
        dst, i = os.path.join(ATT_DIR, name), 1
        while os.path.exists(dst):
            i += 1
            dst = os.path.join(ATT_DIR, f"{base}-{i}{ext}")
        shutil.copy2(src, dst)
        self.insert_ref(dst)

    def attach_dialog(self):
        dlg = Gtk.FileChooserNative.new("Attach file", self, Gtk.FileChooserAction.OPEN, "Attach", "Cancel")
        if dlg.run() == Gtk.ResponseType.ACCEPT and dlg.get_filename():
            self.attach_path(dlg.get_filename())

    def on_paste(self, view):
        cb = Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD)
        if cb.wait_is_text_available() or not cb.wait_is_image_available():
            return
        pb = cb.wait_for_image()
        if not pb:
            return
        if not self.live():
            self.new_note()
        os.makedirs(ATT_DIR, exist_ok=True)
        dst = os.path.join(ATT_DIR, time.strftime("pasted-%Y%m%d-%H%M%S") + ".png")
        pb.savev(dst, "png", [], [])
        view.stop_emission_by_name("paste-clipboard")
        self.insert_ref(dst)

    def on_drop(self, view, ctx, _x, _y, data, _info, tm):
        uris = data.get_uris() or []
        if not uris:
            return
        view.stop_emission_by_name("drag-data-received")
        for u in uris:
            p = Gio.File.new_for_uri(u).get_path()
            if p and os.path.isfile(p):
                self.attach_path(p)
        Gtk.drag_finish(ctx, True, False, tm)

    # ---- history
    def show_history(self):
        if not self.live():
            return
        self.commit_title(refresh=False)
        self.flush()
        versions = self.store.versions(self.current)
        dlg = Gtk.Dialog(title="Version history", transient_for=self, modal=True)
        dlg.set_default_size(780, 480)
        dlg.add_button("Close", Gtk.ResponseType.CLOSE)
        restore = dlg.add_button("Restore this version", Gtk.ResponseType.OK)
        restore.get_style_context().add_class("suggested-action")
        restore.set_sensitive(False)
        lb = Gtk.ListBox()
        lb.get_style_context().add_class("notelist")
        for ts, path in versions:
            row = Gtk.ListBoxRow()
            row.path = path
            try:
                with open(path, encoding="utf-8") as f:
                    first = next((l.strip().lstrip("#").strip() for l in f if l.strip()), "")
            except OSError:
                first = ""
            box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
            a = Gtk.Label(xalign=0)
            a.set_markup("<b>%s</b>" % esc(datetime.fromtimestamp(ts).strftime("%b %d, %Y  %H:%M:%S")))
            c = Gtk.Label(label=first[:40], xalign=0, ellipsize=Pango.EllipsizeMode.END)
            c.get_style_context().add_class("card-snip")
            box.pack_start(a, False, False, 0)
            box.pack_start(c, False, False, 0)
            row.add(box)
            lb.add(row)
        left = Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER)
        left.set_size_request(250, -1)
        left.add(lb)
        tv = Gtk.TextView(editable=False, wrap_mode=Gtk.WrapMode.WORD_CHAR, left_margin=14,
                          right_margin=14, top_margin=12, cursor_visible=False)
        if not versions:
            tv.get_buffer().set_text("No earlier versions yet.\n\nSnapshots are saved as you edit "
                                     "(at most every two minutes, and whenever you switch notes).")
        right = Gtk.ScrolledWindow()
        right.add(tv)

        def on_sel(_l, row):
            restore.set_sensitive(bool(row))
            if row:
                with open(row.path, encoding="utf-8") as f:
                    tv.get_buffer().set_text(f.read())

        lb.connect("row-selected", on_sel)
        paned = Gtk.Paned()
        paned.pack1(left, False, False)
        paned.pack2(right, True, False)
        dlg.get_content_area().pack_start(paned, True, True, 0)
        dlg.show_all()
        resp = dlg.run()
        row = lb.get_selected_row()
        if resp == Gtk.ResponseType.OK and row:
            with open(row.path, encoding="utf-8") as f:
                text = f.read()
            self.store.checkpoint(self.current)  # keep what we're replacing
            self.current.text = text
            self.store.save(self.current)
            self.load_buffer(text)
            self.refresh_list()
            self.update_footer()
        dlg.destroy()

    # ---- clicking links, tags and checkboxes
    def iter_at(self, x, y):
        bx, by = self.view.window_to_buffer_coords(Gtk.TextWindowType.TEXT, x, y)
        res = self.view.get_iter_at_location(bx, by)
        if isinstance(res, tuple):
            return res[1] if res[0] else None
        return res

    def target_at(self, it):
        start = it.copy()
        start.set_line_offset(0)
        end = it.copy()
        if not end.ends_line():
            end.forward_to_line_end()
        line = self.buf.get_text(start, end, True)
        col = it.get_line_offset()
        t = TASK_RE.match(line)
        if t and t.start(2) - 1 <= col <= t.start(2) + 1:
            return ("task", t, start)
        for m in LINK_RE.finditer(line):
            if m.start() <= col < m.end():
                return ("link", m.group(1))
        for m in TAG_RE.finditer(line):
            if m.start() <= col < m.end():
                return ("tag", m.group(1).lower())
        return None

    def follow(self, target):
        kind = target[0]
        if kind == "link":
            self.open_title(target[1])
        elif kind == "tag":
            self.set_filter(("tag", target[1]))
        elif kind == "task" and self.live():
            _, t, start = target
            a = start.copy()
            a.forward_chars(t.start(2))
            z = a.copy()
            z.forward_char()
            self.buf.begin_user_action()
            self.buf.delete(a, z)
            self.buf.insert(a, "x" if t.group(2) == " " else " ")
            self.buf.end_user_action()

    def on_release(self, view, ev):
        if ev.button != 1 or self.buf.get_has_selection():
            return False
        it = self.iter_at(int(ev.x), int(ev.y))
        target = self.target_at(it) if it else None
        if target:
            GLib.idle_add(lambda: (self.follow(target), False)[1])
            return True
        return False

    def on_motion(self, view, ev):
        it = self.iter_at(int(ev.x), int(ev.y))
        hot = bool(it and self.target_at(it))
        if hot != self.hot:
            self.hot = hot
            w = view.get_window(Gtk.TextWindowType.TEXT)
            if w:
                w.set_cursor(Gdk.Cursor.new_from_name(w.get_display(), "pointer" if hot else "text"))
        return False

    def on_key(self, _w, ev):
        k = (Gdk.keyval_name(ev.keyval) or "").lower()
        if k == "f2":
            self.focus_title()
            return True
        if not ev.state & Gdk.ModifierType.CONTROL_MASK:
            return False
        actions = {"n": self.new_note, "f": self.search.grab_focus, "p": self.toggle_pin,
                   "d": self.trash_current, "h": self.show_history, "k": self.quick_open,
                   "l": self.link_picker, "t": self.open_daily, "backslash": self.toggle_focus}
        if k in actions:
            actions[k]()
            return True
        return False


class App(Gtk.Application):
    def __init__(self):
        super().__init__(application_id="io.github.unotes",
                         flags=Gio.ApplicationFlags.HANDLES_COMMAND_LINE)
        self.win = None

    def do_startup(self):
        Gtk.Application.do_startup(self)
        here = os.path.dirname(os.path.abspath(__file__))
        icon = os.path.join(here, "unotes.svg")
        if Gtk.IconTheme.get_default().has_icon("unotes"):
            Gtk.Window.set_default_icon_name("unotes")
        elif os.path.exists(icon):
            try:
                Gtk.Window.set_default_icon_from_file(icon)
            except GLib.Error:
                pass

    def do_activate(self):
        if not self.win:
            self.win = Win(self, Store())
        self.win.show_all()
        self.win.update_footer()
        self.win.present()

    def do_command_line(self, cl):
        args = cl.get_arguments()[1:]
        self.activate()
        if args and args[0] == "--new":
            self.win.new_note(" ".join(args[1:]).strip())
        elif args:
            self.win.open_title(" ".join(args))
        return 0


if __name__ == "__main__":
    sys.exit(App().run(sys.argv))

#!/usr/bin/env bash
# Install unotes for the current user.
set -e
HERE="$(cd "$(dirname "$0")" && pwd)"
BIN="$HOME/.local/bin/unotes"
ICON="$HOME/.local/share/icons/hicolor/scalable/apps/unotes.svg"
DESKTOP="$HOME/.local/share/applications/unotes.desktop"

echo "Installing dependencies (needs sudo)..."
sudo apt install -y python3-gi gir1.2-gtk-3.0 gir1.2-gtksource-4

install -Dm755 "$HERE/unotes.py"  "$BIN"
install -Dm644 "$HERE/unotes.svg" "$ICON"
mkdir -p "$(dirname "$DESKTOP")"
cat > "$DESKTOP" <<D
[Desktop Entry]
Type=Application
Name=unotes
GenericName=Notes
Comment=Local-first Markdown notes
Exec=$BIN
Icon=unotes
Terminal=false
Categories=Utility;TextEditor;
Keywords=notes;markdown;todo;
StartupWMClass=unotes
Actions=NewNote;
X-Ayatana-Desktop-Shortcuts=NewNote

[Desktop Action NewNote]
Name=New note
Exec=$BIN --new

[NewNote Shortcut Group]
Name=New note
Exec=$BIN --new
TargetEnvironment=Unity
D

gtk-update-icon-cache -f -t "$HOME/.local/share/icons/hicolor" 2>/dev/null || true
update-desktop-database "$HOME/.local/share/applications" 2>/dev/null || true

echo
echo "unotes installed. Find it in the Dash, or run: unotes"
case ":$PATH:" in *":$HOME/.local/bin:"*) ;; *) echo "Note: ~/.local/bin is not on your PATH yet. Log out and in once.";; esac
echo "Quick capture: System Settings > Keyboard > Shortcuts > Custom > command: $BIN --new"

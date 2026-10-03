#!/usr/bin/env bash
# Remove unotes. Your notes in ~/Notes are kept unless you pass --purge.
set -e
rm -f "$HOME/.local/bin/unotes" \
      "$HOME/.local/share/icons/hicolor/scalable/apps/unotes.svg" \
      "$HOME/.local/share/applications/unotes.desktop"
gtk-update-icon-cache -f -t "$HOME/.local/share/icons/hicolor" 2>/dev/null || true
update-desktop-database "$HOME/.local/share/applications" 2>/dev/null || true
echo "unotes removed."

NOTES="${NOTES_DIR:-$HOME/Notes}"
if [ "$1" = "--purge" ]; then
    read -r -p "Permanently delete ALL notes in $NOTES? Type 'yes' to confirm: " a
    if [ "$a" = "yes" ]; then rm -rf "$NOTES"; echo "Notes deleted."; else echo "Notes kept."; fi
else
    echo "Your notes in $NOTES were kept. Run with --purge to delete them too."
fi
echo "Python/GTK packages were left installed (other apps may use them)."

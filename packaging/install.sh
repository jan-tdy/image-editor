#!/usr/bin/env bash
# Install PyView Editor as a launchable, XDG-registered app on Linux and
# (optionally) set it as the default handler for the image types it supports.
#
# Usage:
#   ./packaging/install.sh            install + register as default
#   ./packaging/install.sh --no-default   install only, skip default-app step
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BIN_DIR="$HOME/.local/bin"
APPS_DIR="$HOME/.local/share/applications"
ICONS_DIR="$HOME/.local/share/icons/hicolor/scalable/apps"
DESKTOP_ID="com.japysoft.PyViewEditor.desktop"
LAUNCHER="$BIN_DIR/pyview-editor"

SET_DEFAULT=1
if [[ "${1:-}" == "--no-default" ]]; then
    SET_DEFAULT=0
fi

mkdir -p "$BIN_DIR" "$APPS_DIR" "$ICONS_DIR"

cat > "$LAUNCHER" <<EOF
#!/usr/bin/env bash
exec python3 "$REPO_DIR/main.py" "\$@"
EOF
chmod +x "$LAUNCHER"

cp "$REPO_DIR/assets/icon.svg" "$ICONS_DIR/pyview-editor.svg"

sed "s|^Exec=.*|Exec=$LAUNCHER %F|" "$REPO_DIR/packaging/$DESKTOP_ID" > "$APPS_DIR/$DESKTOP_ID"

command -v update-desktop-database >/dev/null && update-desktop-database "$APPS_DIR" || true
command -v gtk-update-icon-cache >/dev/null && gtk-update-icon-cache -f "$HOME/.local/share/icons/hicolor" 2>/dev/null || true

echo "Installed launcher:     $LAUNCHER"
echo "Installed desktop file: $APPS_DIR/$DESKTOP_ID"

if [[ "$SET_DEFAULT" == "1" ]]; then
    if ! command -v xdg-mime >/dev/null; then
        echo "xdg-mime not found; skipping default-app registration." >&2
        exit 0
    fi
    MIME_TYPES=$(sed -n 's/^MimeType=//p' "$REPO_DIR/packaging/$DESKTOP_ID" | tr ';' '\n' | grep -v '^$')
    for mime in $MIME_TYPES; do
        xdg-mime default "$DESKTOP_ID" "$mime"
    done
    echo "Set as default handler for: $(echo "$MIME_TYPES" | paste -sd' ')"
fi

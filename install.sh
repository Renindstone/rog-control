#!/bin/sh
# Installs ROG Control for the current user (no root needed) and adds it to the app launcher.
# Run install-udev.sh once first so the app can talk to the mouse without sudo.
set -e
cd "$(dirname "$0")"

DEST="$HOME/.local/share/rog-control"
ICON_DIR="$HOME/.local/share/icons/hicolor/scalable/apps"
mkdir -p "$DEST" "$HOME/.local/share/applications" "$ICON_DIR"
cp -r rog-control.py rogmouse assets "$DEST/"
rm -rf "$DEST/rogmouse/__pycache__"
cp assets/icon.svg "$ICON_DIR/io.github.rogcontrol.HarpeAceMini.svg"

cat > "$HOME/.local/share/applications/io.github.rogcontrol.HarpeAceMini.desktop" <<EOF
[Desktop Entry]
Name=ROG Control
Comment=Configura tu ROG Harpe Ace Mini
Exec=python3 $DEST/rog-control.py
Icon=io.github.rogcontrol.HarpeAceMini
Terminal=false
Type=Application
Categories=Settings;HardwareSettings;
EOF

echo "Instalado en $DEST. Búscalo como \"ROG Control\" en tu lanzador."

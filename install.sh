#!/bin/sh
# Installs ROG Control for the current user (no root needed) and adds it to the app launcher.
# Run install-udev.sh once first so the app can talk to the mouse without sudo.
set -e
cd "$(dirname "$0")"

DEST="$HOME/.local/share/rog-control"
mkdir -p "$DEST" "$HOME/.local/share/applications"
cp -r rog-control.py rogmouse "$DEST/"
rm -rf "$DEST/rogmouse/__pycache__"

cat > "$HOME/.local/share/applications/io.github.rogcontrol.HarpeAceMini.desktop" <<EOF
[Desktop Entry]
Name=ROG Control
Comment=Configura tu ROG Harpe Ace Mini
Exec=python3 $DEST/rog-control.py
Icon=input-mouse
Terminal=false
Type=Application
Categories=Settings;HardwareSettings;
EOF

echo "Instalado en $DEST. Búscalo como \"ROG Control\" en tu lanzador."

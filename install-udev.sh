#!/bin/sh
# Installs the udev rule so the app can talk to the mouse without sudo.
set -e
cd "$(dirname "$0")"
sudo install -m 644 70-rog-mouse.rules /etc/udev/rules.d/70-rog-mouse.rules
sudo udevadm control --reload-rules
sudo udevadm trigger --subsystem-match=hidraw
echo "Listo. Permisos actuales:"
ls -l /dev/hidraw*

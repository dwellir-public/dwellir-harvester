#!/bin/bash
set -e

# Stop and disable service
systemctl stop dwellir-harvester 2>/dev/null || true
systemctl disable dwellir-harvester 2>/dev/null || true

# Remove systemd service
rm -f /etc/systemd/system/dwellir-harvester.service
systemctl daemon-reload

# Remove config files
rm -f /etc/dwellir-harvester/config
rmdir /etc/dwellir-harvester 2>/dev/null || true

# Remove data directory (prompt first)
read -p "Remove data directory (/var/lib/dwellir-harvester)? [y/N] " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    rm -rf /var/lib/dwellir-harvester
fi

# Remove user and group
userdel harvester 2>/dev/null || true
groupdel harvester 2>/dev/null || true

echo "Dwellir Harvester uninstalled successfully"
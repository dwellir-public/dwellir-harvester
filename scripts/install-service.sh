#!/bin/bash
set -e

# Create system user if it doesn't exist
if ! id -u harvester >/dev/null 2>&1; then
    useradd --system --shell /usr/sbin/nologin --home-dir /nonexistent harvester
fi

# Create directories
install -d -o harvester -g harvester /var/lib/dwellir-harvester
install -d -o root -g root /etc/dwellir-harvester

# Install the package
pip install .

# Install systemd service
install -D -m 644 scripts/dwellir-harvester.service /etc/systemd/system/dwellir-harvester.service

# Install config file if it doesn't exist
if [ ! -f /etc/dwellir-harvester/config ]; then
    cat > /etc/dwellir-harvester/config << EOF
# Dwellir Harvester Configuration
# Uncomment and modify as needed

# Data directory
# DATA_DIR=/var/lib/dwellir-harvester

# Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
# LOG_LEVEL=INFO

# HTTP server port
# PORT=18080

# Collection interval in seconds
# INTERVAL=300

# Space-separated list of collectors to run
# COLLECTORS="host"

# Enable/disable schema validation (true/false)
# VALIDATE=true
EOF
fi

# Set permissions
chown -R harvester:harvester /var/lib/dwellir-harvester
chmod 750 /var/lib/dwellir-harvester

# Reload systemd
systemctl daemon-reload

echo "Dwellir Harvester installed successfully"
echo "To start the service:"
echo "  systemctl start dwellir-harvester"
echo "To enable on boot:"
echo "  systemctl enable dwellir-harvester"
echo ""
echo "Edit /etc/dwellir-harvester/config to change settings"
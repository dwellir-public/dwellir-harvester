#!/bin/bash
set -e

# Default values
DATA_DIR=${DATA_DIR:-/var/lib/dwellir-harvester}
LOG_LEVEL=${LOG_LEVEL:-INFO}
PORT=${PORT:-18080}
INTERVAL=${INTERVAL:-300}
COLLECTORS=${COLLECTORS:-"host"}
VALIDATE=${VALIDATE:-"true"}

# Create data directory if it doesn't exist
mkdir -p "$DATA_DIR"

# Set up environment
export PYTHONPATH="${PYTHONPATH}:$(pwd)/src"

# Start the daemon
exec python3 -m dwellir_harvester.daemon \
    --host 0.0.0.0 \
    --port "$PORT" \
    --interval "$INTERVAL" \
    --log-level "$LOG_LEVEL" \
    ${VALIDATE:+--validate} \
    --collectors $COLLECTORS
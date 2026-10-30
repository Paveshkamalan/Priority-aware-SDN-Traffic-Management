#!/usr/bin/env bash
# ==============================================================================
# Helper Script: Generate Custom Traffic Flow
# Usage:
#   ./scripts/generate_traffic.sh high 5 30
#   ./scripts/generate_traffic.sh low 40 60
# ==============================================================================

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

if [ -z "$VIRTUAL_ENV" ]; then
    if [ -f "/home/pavesh/sdn-env/bin/activate" ]; then
        source "/home/pavesh/sdn-env/bin/activate"
    elif [ -f "$PROJECT_DIR/.venv/bin/activate" ]; then
        source "$PROJECT_DIR/.venv/bin/activate"
    fi
fi

CLASS="${1:-low}"
RATE="${2:-38}"
DURATION="${3:-30}"
PROTOCOL="${4:-udp}"

echo "Injecting $CLASS priority traffic ($RATE Mbps $PROTOCOL) for $DURATION seconds..."
python3 "$PROJECT_DIR/mininet/traffic_generator.py" start \
    --class "$CLASS" \
    --rate "$RATE" \
    --duration "$DURATION" \
    --protocol "$PROTOCOL"

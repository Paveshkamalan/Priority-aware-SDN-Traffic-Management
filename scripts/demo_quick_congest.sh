#!/usr/bin/env bash
# ==============================================================================
# Helper Script: Instant Congestion Demonstration (< 2s Color Transition)
# Blasts 38 Mbps UDP burst over Path 1 bottleneck (40 Mbps limit).
# ==============================================================================

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

if [ -z "$VIRTUAL_ENV" ]; then
    if [ -f "/home/pavesh/sdn-env/bin/activate" ]; then
        source "/home/pavesh/sdn-env/bin/activate"
    elif [ -f "$PROJECT_DIR/.venv/bin/activate" ]; then
        source "$PROJECT_DIR/.venv/bin/activate"
    fi
fi

DURATION="${1:-30}"

echo "======================================================================"
echo " ⚡ Launching Instant Congestion Demo Workload (38 Mbps UDP Burst)"
echo " Path 1 bottleneck (S2-S4, 40 Mbps) will turn RED in 1-2 seconds!"
echo " Duration: ${DURATION}s"
echo "======================================================================"

python3 "$PROJECT_DIR/mininet/traffic_generator.py" demo-congest --duration "$DURATION"

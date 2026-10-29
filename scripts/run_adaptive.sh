#!/usr/bin/env bash
# ==============================================================================
# Experiment 4: Full Proposed System (Adaptive Rerouting + QoS Queueing)
# When the primary path (Path 1) crosses the 85% congestion threshold for 3 intervals:
#   1. Low-priority bulk flow (TCP 40M) is automatically rerouted to Path 2 or Path 3.
#   2. High-priority voice/video flow (UDP 5M) stays protected in Queue 2 on Path 1.
#   3. High-priority delay and loss remain near-zero.
# ==============================================================================

set -e
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RESULTS_DIR="$PROJECT_DIR/results/adaptive"
mkdir -p "$RESULTS_DIR"

if [ -z "$VIRTUAL_ENV" ]; then
    if [ -f "/home/pavesh/sdn-env/bin/activate" ]; then
        source "/home/pavesh/sdn-env/bin/activate"
    elif [ -f "$PROJECT_DIR/.venv/bin/activate" ]; then
        source "$PROJECT_DIR/.venv/bin/activate"
    fi
fi

echo "======================================================================"
echo " Running Experiment 4: Proposed System (Adaptive Rerouting + QoS)     "
echo "======================================================================"

# Reset controller and enable adaptive rerouting & QoS
curl -s -X POST http://127.0.0.1:8080/api/reset
curl -s -X POST http://127.0.0.1:8080/api/reroute/toggle -H "Content-Type: application/json" -d '{"enabled": true}'
curl -s -X POST http://127.0.0.1:8080/api/qos/toggle -H "Content-Type: application/json" -d '{"enabled": true}'

echo "Controller set to PROPOSED mode: Adaptive Rerouting=ON, QoS Queues=ON"

# Launch traffic flows
echo "Generating traffic on Server A -> Server B for 45 seconds..."
python3 "$PROJECT_DIR/mininet/traffic_generator.py" run-profile --duration 45 --results-dir "$RESULTS_DIR"

# Collect ping RTT
echo "Measuring Latency & Loss with Adaptive Protection..."
python3 "$PROJECT_DIR/mininet/traffic_generator.py" ping --src h1 --dst 10.0.0.2 > "$RESULTS_DIR/ping_metrics.json"

# Export metrics
curl -s "http://127.0.0.1:8000/api/results/export?format=json" > "$RESULTS_DIR/experiment_summary.json"

echo "======================================================================"
echo " Experiment 4 Complete! Results saved in: results/adaptive/          "
echo "======================================================================"

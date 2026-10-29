#!/usr/bin/env bash
# ==============================================================================
# Experiment 1: Baseline Shortest-Path Routing
# All flows statically take Path 1 (S1-S2-S4-S6).
# As traffic increases, the 40 Mbps bottleneck link saturates, causing packet loss
# and delay spikes for all traffic classes.
# ==============================================================================

set -e
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RESULTS_DIR="$PROJECT_DIR/results/baseline"
mkdir -p "$RESULTS_DIR"

if [ -z "$VIRTUAL_ENV" ]; then
    if [ -f "/home/pavesh/sdn-env/bin/activate" ]; then
        source "/home/pavesh/sdn-env/bin/activate"
    elif [ -f "$PROJECT_DIR/.venv/bin/activate" ]; then
        source "$PROJECT_DIR/.venv/bin/activate"
    fi
fi

echo "======================================================================"
echo " Running Experiment 1: Baseline Shortest-Path Routing                 "
echo "======================================================================"

# Disable adaptive rerouting and QoS priority queueing via REST
curl -s -X POST http://127.0.0.1:8080/api/reroute/toggle -H "Content-Type: application/json" -d '{"enabled": false}'
curl -s -X POST http://127.0.0.1:8080/api/qos/toggle -H "Content-Type: application/json" -d '{"enabled": false}'

echo "Controller set to BASELINE mode: Adaptive Rerouting=OFF, QoS Queues=OFF"

# Launch traffic flows:
# High: 5 Mbps UDP (port 5001)
# Medium: 20 Mbps TCP (port 5002)
# Low: 40 Mbps TCP (port 5003) -> Total 65 Mbps on 40 Mbps bottleneck!
echo "Generating traffic on Server A -> Server B for 45 seconds..."
python3 "$PROJECT_DIR/mininet/traffic_generator.py" run-profile --duration 45 --results-dir "$RESULTS_DIR"

# Collect ping RTT under congestion
echo "Measuring Latency & Loss under Congestion..."
python3 "$PROJECT_DIR/mininet/traffic_generator.py" ping --src h1 --dst 10.0.0.2 > "$RESULTS_DIR/ping_metrics.json"

# Export experiment metrics from Dashboard API
curl -s "http://127.0.0.1:8000/api/results/export?format=json" > "$RESULTS_DIR/experiment_summary.json"

echo "======================================================================"
echo " Experiment 1 Complete! Results saved in: results/baseline/          "
echo "======================================================================"

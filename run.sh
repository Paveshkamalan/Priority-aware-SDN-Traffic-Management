#!/usr/bin/env bash
# ==============================================================================
# Master Execution Script: Priority-Aware Adaptive SDN Simulation
# Starts Ryu Controller, Mininet Emulation, and Web Dashboard.
# Handles graceful shutdown on Ctrl+C.
# ==============================================================================

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_DIR"

# Clean up any leftover processes
"$PROJECT_DIR/scripts/cleanup.sh"

echo "======================================================================"
echo " Starting Priority-Aware Adaptive SDN Simulation                     "
echo "======================================================================"

# Determine Python environment and activate venv
if [ -z "$VIRTUAL_ENV" ]; then
    if [ -f "/home/pavesh/sdn-env/bin/activate" ]; then
        source "/home/pavesh/sdn-env/bin/activate"
    elif [ -f "$PROJECT_DIR/.venv/bin/activate" ]; then
        source "$PROJECT_DIR/.venv/bin/activate"
    fi
fi

if [ -n "$VIRTUAL_ENV" ]; then
    PY_BIN="$VIRTUAL_ENV/bin/python3"
elif [ -d "/home/pavesh/sdn-env" ]; then
    PY_BIN="/home/pavesh/sdn-env/bin/python3"
elif [ -d "$PROJECT_DIR/.venv" ]; then
    PY_BIN="$PROJECT_DIR/.venv/bin/python3"
else
    PY_BIN="python3"
fi

# Trap signals for graceful shutdown
cleanup_all() {
    echo ""
    echo "*** Caught termination signal. Shutting down all components... ***"
    "$PROJECT_DIR/scripts/cleanup.sh"
    exit 0
}
trap cleanup_all SIGINT SIGTERM EXIT

# 1. Start Ryu Controller
echo "[1/3] Starting Ryu SDN Controller on port 6653 (REST API on port 8080)..."
if command -v ryu-manager &> /dev/null; then
    ryu-manager "$PROJECT_DIR/controller/ryu_app.py" --ofp-tcp-listen-port 6653 > /tmp/ryu_controller.log 2>&1 &
elif [ -f "/tmp/test_venv/bin/ryu-manager" ]; then
    /tmp/test_venv/bin/ryu-manager "$PROJECT_DIR/controller/ryu_app.py" --ofp-tcp-listen-port 6653 > /tmp/ryu_controller.log 2>&1 &
elif [ -f "/home/pavesh/sdn-env/bin/ryu-manager" ]; then
    /home/pavesh/sdn-env/bin/ryu-manager "$PROJECT_DIR/controller/ryu_app.py" --ofp-tcp-listen-port 6653 > /tmp/ryu_controller.log 2>&1 &
else
    $PY_BIN "$PROJECT_DIR/controller/ryu_app.py" > /tmp/ryu_controller.log 2>&1 &
fi
CONTROLLER_PID=$!
sleep 2

# Verify controller is running
if ! kill -0 $CONTROLLER_PID 2>/dev/null; then
    echo "Error starting controller! See /tmp/ryu_controller.log:"
    cat /tmp/ryu_controller.log | tail -n 20
    exit 1
fi
echo "Controller running (PID: $CONTROLLER_PID)."

# 2. Start Dashboard Backend
echo "[2/3] Starting Web Dashboard backend at http://localhost:8000..."
$PY_BIN -m uvicorn dashboard.app:app --host 0.0.0.0 --port 8000 > /tmp/dashboard.log 2>&1 &
DASHBOARD_PID=$!
sleep 1
echo "Dashboard running at http://localhost:8000 (PID: $DASHBOARD_PID)."

# 3. Start Mininet Network
echo "[3/3] Starting Mininet Network (requires sudo)..."
echo "======================================================================"
echo " Web Dashboard:  http://localhost:8000                               "
echo " REST API:       http://localhost:8080/api/topology                  "
echo " Press Ctrl+C at any time to shut down all processes cleanly.        "
echo "======================================================================"

sudo python3 "$PROJECT_DIR/mininet/start_network.py" \
    --controller-ip 127.0.0.1 \
    --controller-port 6653 \
    --config-dir "$PROJECT_DIR/config"

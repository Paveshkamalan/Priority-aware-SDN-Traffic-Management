#!/usr/bin/env bash
# ==============================================================================
# Setup Script: Priority-Aware Adaptive SDN Network
# Sets up Python virtual environment, dependencies, and verifies system packages.
# ==============================================================================

set -e

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_DIR"

echo "========================================================"
echo " Setting up SDN Priority Traffic Management Project    "
echo "========================================================"

# Check for required system binaries
echo "[1/4] Checking system tools..."
MISSING_PKGS=()
for bin in mn ovs-vsctl iperf3; do
    if ! command -v $bin &> /dev/null; then
        MISSING_PKGS+=("$bin")
    fi
done

if [ ${#MISSING_PKGS[@]} -ne 0 ]; then
    echo "Warning: The following packages are missing: ${MISSING_PKGS[*]}"
    echo "Please install them via: sudo apt-get update && sudo apt-get install -y mininet openvswitch-switch iperf3"
else
    echo "Core networking packages detected: mininet, openvswitch, iperf3."
fi

# Create Python virtual environment if not present
echo "[2/4] Setting up Python virtual environment..."
VENV_PATH="$PROJECT_DIR/.venv"
if [ ! -d "$VENV_PATH" ]; then
    python3 -m venv "$VENV_PATH"
fi

source "$VENV_PATH/bin/activate"

# Install requirements
echo "[3/4] Installing Python requirements..."
pip install --upgrade pip
pip install -r "$PROJECT_DIR/requirements.txt"

# Make helper scripts executable
echo "[4/4] Setting executable permissions on scripts..."
chmod +x "$PROJECT_DIR/setup.sh" "$PROJECT_DIR/run.sh" 2>/dev/null || true
chmod +x "$PROJECT_DIR"/scripts/*.sh 2>/dev/null || true
chmod +x "$PROJECT_DIR"/mininet/*.py 2>/dev/null || true

echo "========================================================"
echo " Setup Complete! You can now start the network:        "
echo "   ./run.sh                                             "
echo "========================================================"

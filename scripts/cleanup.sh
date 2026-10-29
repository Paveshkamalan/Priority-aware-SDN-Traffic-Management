#!/usr/bin/env bash
# ==============================================================================
# Comprehensive Cleanup Script for Priority SDN Simulation
# Safely terminates controller, Mininet, iperf3, and clears temporary OVS state.
# ==============================================================================

echo "========================================================"
echo " Stopping Priority SDN Simulation and Cleaning Up State "
echo "========================================================"

# 1. Terminate python applications
echo "[1/5] Killing running controller, dashboard, and traffic processes..."
fuser -k -9 6653/tcp 8080/tcp 8000/tcp 2>/dev/null || true
pkill -9 -f "ryu.cmd.manager" 2>/dev/null || true
pkill -9 -f "ryu-manager" 2>/dev/null || true
pkill -9 -f "start_network.py" 2>/dev/null || true
pkill -9 -f "app:app" 2>/dev/null || true
pkill -9 -f "uvicorn" 2>/dev/null || true
pkill -9 -f "traffic_generator.py" 2>/dev/null || true
pkill -9 iperf3 2>/dev/null || true

# 2. Stop Mininet environment
echo "[2/5] Cleaning Mininet network namespaces..."
mn -c 2>/dev/null || sudo -n mn -c 2>/dev/null || true

# 3. Clean Open vSwitch temporary bridges and QoS tables
echo "[3/5] Cleaning Open vSwitch temporary bridges and QoS tables..."
for i in {1..6}; do
    ovs-vsctl --if-exists del-br "s$i" 2>/dev/null || sudo -n ovs-vsctl --if-exists del-br "s$i" 2>/dev/null || true
done

# Clear QoS & Queue tables
ovs-vsctl --all destroy qos 2>/dev/null || sudo -n ovs-vsctl --all destroy qos 2>/dev/null || true
ovs-vsctl --all destroy queue 2>/dev/null || sudo -n ovs-vsctl --all destroy queue 2>/dev/null || true

# 4. Remove temporary lock / PID files
echo "[4/5] Removing temporary PID and socket files..."
rm -f /tmp/sdn_traffic_pids.json 2>/dev/null || true
rm -f /tmp/vconn* 2>/dev/null || true

echo "[5/5] Cleanup complete. Network is clean and ready."

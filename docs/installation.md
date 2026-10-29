# Installation and Setup Guide

This guide details how to install and execute the Priority-Aware Adaptive SDN Simulation on Ubuntu Linux or WSL2 (Windows Subsystem for Linux).

---

## 1. Prerequisites & System Requirements

- **Operating System**: Ubuntu 22.04 LTS, 24.04 LTS, or WSL2 (Windows 10/11 with WSL2 Ubuntu).
- **Kernel Privileges**: `sudo` access required for Mininet and Open vSwitch operations.
- **Python**: Python 3.10+ (compatible with Python 3.10 through 3.14).

---

## 2. Package Installation

Execute the following commands inside Ubuntu terminal / WSL2:

```bash
sudo apt-get update
sudo apt-get install -y \
    mininet \
    openvswitch-switch \
    openvswitch-testcontroller \
    iperf3 \
    iproute2 \
    python3 \
    python3-pip \
    python3-venv \
    git \
    curl
```

### Verify Open vSwitch Service
Ensure Open vSwitch daemon is active:
```bash
sudo /etc/init.d/openvswitch-switch status
# If not running:
sudo /etc/init.d/openvswitch-switch start
```

---

## 3. Project Environment Setup

1. **Clone or navigate to the project directory**:
   ```bash
   cd priority-aware-sdn-traffic-management
   ```

2. **Execute the automated setup script**:
   ```bash
   chmod +x setup.sh run.sh scripts/*.sh
   ./setup.sh
   ```

   The setup script creates a Python virtual environment in `.venv/` and installs all dependencies (`fastapi`, `uvicorn`, `pyyaml`, `pytest`, `jinja2`, `httpx`, `networkx`, etc.).

---

## 4. Running the Complete Simulation

To launch the full system (Ryu Controller, Web Dashboard, and Mininet Topology):

```bash
./run.sh
```

This single command:
1. Performs pre-flight cleanup of old bridges and processes.
2. Launches the **Ryu SDN Controller** on port 6653 (REST API on port 8080).
3. Launches the **FastAPI Web Dashboard** at `http://localhost:8000`.
4. Boots the **Mininet 6-switch topology** with OpenFlow 1.3 and OVS QoS queues.

Once launched, open your web browser at:
👉 **`http://localhost:8000`**

---

## 5. Running Experiments from Command Line

You can also run experiments directly via CLI scripts:

### Experiment 1: Baseline Shortest Path
```bash
./scripts/run_baseline.sh
```

### Experiment 4: Full Proposed Adaptive + QoS System
```bash
./scripts/run_adaptive.sh
```

### Clean Up Network State
```bash
./scripts/cleanup.sh
```

---

## 6. Running Automated Tests

Run the full pytest test suite:
```bash
pytest -v tests/
```
All 15 tests covering path computation, hysteresis, priority discrimination, and REST APIs will execute.

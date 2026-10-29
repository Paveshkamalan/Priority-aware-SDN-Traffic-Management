# System Architecture: Priority-Aware Adaptive SDN Traffic Management

## 1. Architectural Overview

This system implements a three-tier Software-Defined Networking (SDN) architecture designed to guarantee Quality of Service (QoS) for mission-critical traffic while dynamically optimizing multi-path link utilization under network congestion.

```
+-------------------------------------------------------------------------+
|                           APPLICATION PLANE                             |
|                                                                         |
|   +-----------------------+              +--------------------------+   |
|   |  FastAPI REST Server  |<--- REST --->|   Web Browser Dashboard  |   |
|   |   (Port 8000)         |<-- WSS/SSE --|   (vis.js & Chart.js)    |   |
|   +-----------+-----------+              +--------------------------+   |
+---------------|---------------------------------------------------------+
                | REST (Port 8080)
+---------------v---------------------------------------------------------+
|                            CONTROL PLANE                                |
|                                                                         |
|   +-----------------------------------------------------------------+   |
|   |                 Ryu SDN Controller (OpenFlow 1.3)               |   |
|   |                                                                 |   |
|   |   +-------------------+    +--------------------------------+   |   |
|   |   |  TopologyManager  |    |         PathComputer           |   |   |
|   |   | (LLDP & Discovery)|    |     (Multipath Dijkstra)       |   |   |
|   |   +---------+---------+    +----------------+---------------+   |   |
|   |             |                               |                   |   |   |
|   |   +---------v---------+    +----------------v---------------+   |   |
|   |   |  NetworkMonitor   |    |        PriorityRerouter        |   |   |
|   |   | (Port/Queue Stats)|--->|   (Hysteresis & Migration)     |   |   |
|   |   +-------------------+    +----------------+---------------+   |   |
|   |                                             |                   |   |   |
|   |   +-----------------------------------------v---------------+   |   |
|   |   |                        QoSManager                       |   |   |
|   |   |         (Queue ID 0/1/2 & OFPActionSetQueue)            |   |   |
|   |   +---------------------------------------------------------+   |   |
|   +-----------------------------------------------------------------+   |
+--------------------------------|----------------------------------------+
                                 | OpenFlow 1.3 (TCP Port 6653)
+--------------------------------v----------------------------------------+
|                             DATA PLANE                                  |
|                                                                         |
|   +-----------------------------------------------------------------+   |
|   |                  Mininet Network Emulation                      |   |
|   |                                                                 |   |
|   |    Server A (h1)                Switch Fabric        Server B (h2)| |
|   |      10.0.0.1                    (S1 to S6)           10.0.0.2    | |
|   |   +------------+                +----------+        +-----------+ | |
|   |   | iperf3 /   |--- 100M/1ms ---| Open     |---...--| iperf3    | | |
|   |   | ping Client|                | vSwitch  |        | Server    | | |
|   |   +------------+                +----------+        +-----------+ | |
|   |                                 | tc-htb   |                      | |
|   |                                 | Queues   |                      | |
|   |                                 +----------+                      | |
|   +-----------------------------------------------------------------+   |
+-------------------------------------------------------------------------+
```

---

## 2. Component Interaction & Communication

### 2.1 Data Plane (Mininet & Open vSwitch)
- **Mininet 2.3.x**: Creates virtual network namespaces running isolated network stacks for Server A (`10.0.0.1`) and Server B (`10.0.0.2`).
- **Open vSwitch (OVS)**: 6 software-defined bridges (`s1` through `s6`) operating OpenFlow 1.3 datapaths.
- **Linux Traffic Control (tc-htb)**: Attached to egress ports of OVS switches, providing three classful priority queues:
  - **Queue 2 (High Priority)**: Min 60% bandwidth, low burst latency.
  - **Queue 1 (Medium Priority)**: Min 30% bandwidth.
  - **Queue 0 (Low Priority)**: Min 10% bandwidth (best-effort burst up to 100%).

### 2.2 Control Plane (Ryu Controller)
- **Port/Queue Statistics Polling**: Emits `OFPPortStatsRequest` and `OFPQueueStatsRequest` every 1.0 second.
- **Link Utilization Calculation**:
  $$\text{Transmit Rate (bps)} = \frac{(\text{tx\_bytes}_{t} - \text{tx\_bytes}_{t-\Delta t}) \times 8}{\Delta t}$$
  $$\text{Utilization} = \frac{\text{Transmit Rate}}{\text{Link Capacity}}$$
- **Priority-Aware Rerouting**:
  When a link on Path 1 exceeds 85% utilization for 3 consecutive intervals, the controller maintains high-priority flows in Queue 2 on Path 1, while selectively migrating the low-priority flow to Path 2 or Path 3.

### 2.3 Application & Presentation Plane
- **Controller REST API (Port 8080)**: Direct thread in controller process exposing internal topology, metrics, and flow tables.
- **Dashboard Backend (FastAPI, Port 8000)**: Serves single-page application and streams metrics over WebSockets (`ws://localhost:8000/ws/metrics`).
- **Browser Frontend (HTML5/vis.js/Chart.js)**: Displays real-time graph topology with green/yellow/red link edges, latency charts, and experiment control buttons.

---

## 3. Communication Sequence Flow

```
+------------+          +-------------+          +------------+          +------------+
|  Host A/B  |          |   Switch    |          |    Ryu     |          | Dashboard  |
+------------+          +-------------+          +------------+          +------------+
      |                        |                        |                       |
      |--- [1] Data Packet --->|                        |                       |
      |    (DSCP/Port Tagged)  |--- [2] PacketIn ------>|                       |
      |                        |    (Table-Miss)        |                       |
      |                        |                        |-- [3] Classify & Path |
      |                        |<-- [4] FlowMod --------|       Compute         |
      |                        |    (set_queue + out)   |                       |
      |                        |<-- [5] PortStatsReq ---| (Every 1s)            |
      |                        |--- [6] PortStatsRep -->|                       |
      |                        |                        |-- [7] Calc Util &     |
      |                        |                        |       Hysteresis      |
      |                        |                        |--- [8] WS Telemetry ->|
      |<-- [9] Forwarded ------|                        |                       |
      |    via Queue ID        |                        |                       |
```

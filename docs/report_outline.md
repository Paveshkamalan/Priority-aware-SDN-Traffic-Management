# Academic Report Outline

## Title: Priority-Aware Adaptive Traffic Management in Multi-Path SDN Networks Using Mininet and Ryu

---

### Abstract
- Brief contextualization of Software-Defined Networking (SDN) and traditional shortest-path routing limitations.
- Statement of the core problem: bottleneck link saturation causes indiscriminate packet loss and latency inflation across all traffic classes.
- Proposed solution: A dual-layer framework combining OpenFlow 1.3 multi-path adaptive rerouting with ingress priority discrimination and egress Hierarchical Token Bucket (tc-htb) queue scheduling.
- Key empirical findings: Under 162.5% bottleneck saturation, high-priority voice/video UDP flows achieve 0% packet loss and 8.14 ms latency, while low-priority bulk TCP traffic is dynamically offloaded to alternate paths without route flapping.

---

### 1. Introduction
- Background: Emergence of heterogeneous IP network traffic (real-time voice, video streaming, interactive web, bulk backup).
- SDN architectural advantages: Centralized global network visibility, programmatic datapath control via OpenFlow.
- Scope and objectives of the project.

---

### 2. Problem Statement
- Limitations of static Single Shortest Path (SPF / Dijkstra) routing:
  - Bottleneck creation on primary links.
  - Suboptimal utilization of idle alternate network topologies.
  - Fairness paradox: Low-priority bulk TCP streams crowd out latency-sensitive UDP flows in FIFO queues.
- Formulation of the multi-path traffic distribution challenge.

---

### 3. Literature Review & Related Work
- Equal-Cost Multi-Path (ECMP) routing and hash-collision degradation.
- SDN traffic engineering frameworks: Hedera, Mahout, and MicroTE.
- Quality of Service (QoS) in OpenFlow: DiffServ mapping, metering, and egress queue slicing.
- Gaps in prior work: Failure to decouple path selection (WHERE packets travel) from queue scheduling (WHICH packets are served first).

---

### 4. System Architecture
- **Data Plane**: Mininet 2.3.x, Open vSwitch (OVS 2.17+), Linux Traffic Control (HTB).
- **Control Plane**: Ryu SDN Controller (OpenFlow 1.3), Topology Manager, Network Monitor, Path Computer, Priority Rerouter, QoS Manager.
- **Application & Visualization Plane**: FastAPI REST backend, WebSocket telemetry streaming, browser UI (vis.js network canvas, Chart.js).

---

### 5. Methodology & Algorithmic Formulation
- Multipath Dijkstra graph traversal with edge delay, bandwidth, and utilization weighting.
- Real-time link utilization formulation:
  $$U_t(e) = \frac{\Delta \text{tx\_bytes}(e) \times 8}{\Delta t \times C(e)}$$
- Dual-threshold hysteresis state machine:
  - Congestion trigger: $\ge 85\%$ for 3 consecutive intervals.
  - Recovery trigger: $\le 50\%$ for 5 consecutive intervals.
  - Prevention of route oscillation / route flapping.
- Multi-class flow prioritization:
  - Class 3 (High): Queue 2 (60% weight, protected from reroute).
  - Class 2 (Medium): Queue 1 (30% weight, conditional reroute).
  - Class 1 (Low): Queue 0 (10% weight, first to reroute).

---

### 6. Implementation Details
- Configurable YAML-driven architecture (`topology.yaml`, `qos.yaml`, `experiment.yaml`).
- Flow affinity preservation: 5-tuple matching preventing packet reordering within active TCP sessions.
- Make-before-break OpenFlow rule modification using strict priority weighting (priority 150 overrides priority 100).

---

### 7. Experimental Setup & Scenarios
- **Scenario 1**: Baseline Shortest-Path Routing (All flows on Path 1; no rerouting, no QoS).
- **Scenario 2**: Adaptive Rerouting Only (Rerouting enabled; QoS queues disabled).
- **Scenario 3**: QoS Priority Queueing Only (Shortest path retained; QoS queues enabled).
- **Scenario 4**: Full Proposed System (Adaptive Rerouting + QoS Priority Queues).
- **Scenario 5**: Link Failure Recovery (Dynamic link drop S2-S4 and automatic failover).

---

### 8. Results & Performance Evaluation
- Throughput comparison across traffic classes.
- End-to-end latency and jitter evaluation.
- Packet loss percentage under bottleneck saturation.
- Link utilization distribution across alternate paths.
- Route flap suppression metrics under transient traffic spikes.

---

### 9. Discussion & Critical Analysis
- Trade-offs between computational overhead and rerouting responsiveness.
- Scalability to larger spine-and-leaf data center networks.
- Impact of TCP window adjustments during flow migration.

---

### 10. Conclusion & Future Work
- Summary of research contributions.
- Future work: Integration of machine learning for predictive congestion forecasting and P4 programmable data planes.

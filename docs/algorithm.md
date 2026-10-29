# Algorithm Specification: Priority-Aware Adaptive Rerouting & QoS Scheduling

## 1. Mathematical Formulation

Let the network be modeled as a directed graph $G = (V, E)$, where $V$ denotes Open vSwitch datapaths ($|V| = 6$) and $E$ represents directional links.
Each edge $e = (u, v) \in E$ is characterized by:
- Capacity $C(e)$ in Mbps.
- Propagation delay $D(e)$ in ms.
- Dynamic transmit byte count $B_t(e)$ recorded at epoch $t$.

### 1.1 Real-Time Link Utilization
At each monitoring interval $\Delta t = 1.0\text{ s}$, the controller samples cumulative egress byte counters:
$$\Delta B_t(e) = \max\left(0, B_t(e) - B_{t-\Delta t}(e)\right)$$
$$\text{Bitrate } R_t(e) = \frac{\Delta B_t(e) \times 8}{\Delta t} \quad [\text{bps}]$$
$$\text{Utilization } U_t(e) = \min\left(1.0, \frac{R_t(e)}{C(e) \times 10^6}\right)$$

---

## 2. Hysteresis State Machine

To prevent route oscillations (route flapping) due to transient bursty traffic, a two-threshold hysteresis state machine governs link congestion classification:
- **Warning Threshold**: $\theta_w = 0.70$ (70%)
- **Congestion Threshold**: $\theta_c = 0.85$ (85%)
- **Recovery Threshold**: $\theta_r = 0.50$ (50%)

```
                  +-----------------------------------+
                  |             NORMAL                |
                  |     (Utilization < 70%)           |
                  +-----------------------------------+
                     |                             ^
       U >= 85% for  |                             | U <= 50% for
       3 intervals   |                             | 5 intervals
                     v                             |
                  +-----------------------------------+
                  |           CONGESTED               |
                  |  (Trigger Low-Priority Reroute)   |
                  +-----------------------------------+
```

- **Congestion Confirmation**: Link $e$ transitions to `CONGESTED` only if $U_t(e) \ge 0.85$ for $N_c = 3$ consecutive monitoring intervals.
- **Recovery Confirmation**: Link $e$ transitions back to `NORMAL` only if $U_t(e) \le 0.50$ for $N_r = 5$ consecutive monitoring intervals.

---

## 3. Priority Discrimination Rerouting Logic

When link $e \in \text{Path}(f)$ is flagged as `CONGESTED`:

| Flow Priority | Traffic Class | Action Taken | Rationale |
|---|---|---|---|
| **Class 3 (High)** | Voice / Video UDP | **Preserve on current path** | Strictly protected in egress Queue 2 (60% weight); avoiding rerouting eliminates packet reordering and transient jitter. |
| **Class 2 (Medium)** | Web / Interactive TCP | **Conditional Reroute** | Reroute to alternate path only if alternate bottleneck capacity $\ge 25$ Mbps and low-priority migration did not relieve congestion. |
| **Class 1 (Low)** | Bulk Backup TCP | **Immediate Reroute** | Migrate first to Path 2 or Path 3 to relieve bottleneck pressure. |

---

## 4. Pseudocode

```python
Algorithm: Priority-Aware Adaptive Reroute Evaluation
Input: Active flows F, Network Graph G, Monitoring epoch t
Output: Reroute directives R

1:  for each link e = (u, v) in E do:
2:      U = compute_utilization(e)
3:      if U >= 0.85 then:
4:          congested_count[e] += 1
5:          recovery_count[e] = 0
6:          if congested_count[e] >= 3 then:
7:              confirmed_congested.add(e)
8:      else if U <= 0.50 then:
9:          recovery_count[e] += 1
10:         congested_count[e] = 0
11:         if recovery_count[e] >= 5 then:
12:             confirmed_congested.remove(e)
13:     end if
14: end for

15: R = []
16: Sort flows F by priority ascending (Low priority first)
17: for flow f in F do:
18:     if any link in path(f) in confirmed_congested then:
19:         if f.priority == 3 then:
20:             continue  # High priority preserved in Queue 2
21:         else if f.priority == 1 then:
22:             alt_path = find_best_alternate_path(G, f.src, f.dst, path(f))
23:             if alt_path != None then:
24:                 install_rules(alt_path, f, priority=150)
25:                 log_event(f, path(f), alt_path, reason="Congestion relief")
26:                 f.current_path = alt_path
27:                 f.rerouted = True
28:             end if
29:         end if
30:     else if f.rerouted and original_path(f) is clear then:
31:         restore_rules(original_path(f), f)
32:         f.current_path = original_path(f)
33:         f.rerouted = False
34:     end if
35: end for
36: return R
```

---

## 5. Algorithmic Flowchart

```
       [Start Monitoring Tick (1s)]
                   |
     [Poll Port & Queue Stats]
                   |
  [Calculate Link Utilization U_t]
                   |
           Is U_t >= 85%?
           /            \
        (Yes)           (No)
         /                \
[Increment Congest]    Is U_t <= 50%?
[Count for 3 ticks]    /           \
       |             (Yes)         (No)
Is Count >= 3?         |             |
   /        \    [Increment Recv] [Maintain]
 (Yes)      (No) [Count for 5]       |
  /           \        |             |
[Mark Link   [Wait]  Is Count >= 5?  |
CONGESTED]             /      \      |
  |                  (Yes)    (No)   |
[Examine Flows]        |        \    |
  |              [Mark Link    [Wait]|
Flow Priority?    NORMAL]            |
 /     |     \         \____________/
(Low) (Med) (High)           |
  |    |      |         [Next Tick]
  |    |   [Keep on Path 1 / Queue 2]
  |    |
  |  [Check Alt Capacity >= 25M]
  |    |
[Reroute to Path 2 or Path 3]
  |
[Install OpenFlow Rules (Make-Before-Break)]
  |
[End Tick]
```

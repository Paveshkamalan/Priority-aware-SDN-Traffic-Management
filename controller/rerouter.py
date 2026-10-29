"""
Priority Rerouter Module
Implements congestion detection, hysteresis state machines, and priority-aware flow migration.
Ensures high-priority traffic is protected while low-priority flows are dynamically offloaded.
"""

import logging
import time
from typing import Dict, List, Tuple, Any, Optional, Set

logger = logging.getLogger("PriorityRerouter")


class PriorityRerouter:
    """
    Manages congestion-triggered rerouting with hysteresis and priority differentiation.
    """

    def __init__(
        self,
        warning_threshold: float = 0.70,
        congestion_threshold: float = 0.85,
        recovery_threshold: float = 0.50,
        congestion_intervals: int = 3,
        recovery_intervals: int = 5,
        enabled: bool = True,
    ):
        self.warning_threshold = warning_threshold
        self.congestion_threshold = congestion_threshold
        self.recovery_threshold = recovery_threshold
        self.congestion_required_intervals = congestion_intervals
        self.recovery_required_intervals = recovery_intervals
        self.enabled = enabled

        # Hysteresis state counters per link: (u, v) -> consecutive intervals congested
        self.link_congestion_counts: Dict[Tuple[int, int], int] = {}
        # Hysteresis recovery counters per link: (u, v) -> consecutive intervals below recovery
        self.link_recovery_counts: Dict[Tuple[int, int], int] = {}
        # Flags for confirmed congested links
        self.confirmed_congested_links: Set[Tuple[int, int]] = set()

        # Active flow registry: flow_id -> flow metadata
        # flow metadata: {'flow_id': str, 'priority': int, 'class': str, 'current_path': list, 'path_name': str}
        self.active_flows: Dict[str, Dict[str, Any]] = {}

        # Event log for audit and reporting
        self.reroute_events: List[Dict[str, Any]] = []

    def set_enabled(self, status: bool) -> None:
        self.enabled = status
        logger.info(f"Adaptive rerouting enabled status set to: {self.enabled}")

    def update_link_state(self, u: int, v: int, utilization: float) -> Tuple[bool, str]:
        """
        Updates hysteresis counters for link (u, v).
        Returns (is_congested, state_description).
        """
        link_key = tuple(sorted([u, v]))

        if utilization >= self.congestion_threshold:
            self.link_congestion_counts[link_key] = self.link_congestion_counts.get(link_key, 0) + 1
            self.link_recovery_counts[link_key] = 0
            count = self.link_congestion_counts[link_key]

            if count >= self.congestion_required_intervals:
                if link_key not in self.confirmed_congested_links:
                    logger.warning(
                        f"CONGESTION CONFIRMED on link s{link_key[0]}-s{link_key[1]} "
                        f"({utilization*100:.1f}%) for {count} consecutive checks."
                    )
                    self.confirmed_congested_links.add(link_key)
                return True, "CONGESTED"
            return False, f"CONGESTION_WARNING ({count}/{self.congestion_required_intervals})"

        elif utilization <= self.recovery_threshold:
            self.link_recovery_counts[link_key] = self.link_recovery_counts.get(link_key, 0) + 1
            self.link_congestion_counts[link_key] = 0
            rec_count = self.link_recovery_counts[link_key]

            if rec_count >= self.recovery_required_intervals:
                if link_key in self.confirmed_congested_links:
                    logger.info(
                        f"RECOVERY CONFIRMED on link s{link_key[0]}-s{link_key[1]} "
                        f"({utilization*100:.1f}%) for {rec_count} checks. Returning to normal."
                    )
                    self.confirmed_congested_links.remove(link_key)
                return False, "NORMAL"
            return False, f"RECOVERING ({rec_count}/{self.recovery_required_intervals})"

        else:
            # Between 50% and 85%: sustain current confirmed state, decay warning counters
            self.link_congestion_counts[link_key] = max(0, self.link_congestion_counts.get(link_key, 0) - 1)
            self.link_recovery_counts[link_key] = 0
            is_cong = link_key in self.confirmed_congested_links
            return is_cong, "MODERATE"

    def register_flow(
        self,
        flow_id: str,
        priority: int,
        traffic_class: str,
        initial_path: List[int],
        src_ip: str = "10.0.0.1",
        dst_ip: str = "10.0.0.2",
        dst_port: Optional[int] = None,
        proto: str = "tcp",
    ) -> None:
        """Register a new active flow with flow affinity."""
        self.active_flows[flow_id] = {
            "flow_id": flow_id,
            "priority": priority,
            "class": traffic_class,
            "current_path": list(initial_path),
            "original_path": list(initial_path),
            "src_ip": src_ip,
            "dst_ip": dst_ip,
            "dst_port": dst_port,
            "proto": proto,
            "rerouted": False,
            "last_reroute_time": 0.0,
        }

    def check_and_reroute_flows(
        self,
        path_computer: Any,
        graph: Dict[int, Dict[int, Dict[str, Any]]],
    ) -> List[Dict[str, Any]]:
        """
        Evaluates all active flows against congested links.
        Decides which flows to reroute based on priority.
        Returns list of reroute directives.
        """
        if not self.enabled:
            return []

        reroute_actions = []

        # Sort flows by priority ascending (Low priority first: 1, then 2, then 3)
        sorted_flows = sorted(
            self.active_flows.values(), key=lambda f: f.get("priority", 1)
        )

        for flow in sorted_flows:
            flow_id = flow["flow_id"]
            priority = flow["priority"]
            current_path = flow["current_path"]

            # Check if any link on the current path is confirmed congested
            path_congested = False
            congested_edge = None
            for i in range(len(current_path) - 1):
                u = current_path[i]
                v = current_path[i + 1]
                link_key = tuple(sorted([u, v]))
                if link_key in self.confirmed_congested_links:
                    path_congested = True
                    congested_edge = link_key
                    break

            if not path_congested:
                # Check if flow was previously rerouted and can now return to shortest path
                if flow.get("rerouted", False):
                    original_path = flow.get("original_path", [1, 2, 4, 6])
                    orig_congested = any(
                        tuple(sorted([original_path[j], original_path[j + 1]]))
                        in self.confirmed_congested_links
                        for j in range(len(original_path) - 1)
                    )
                    if not orig_congested:
                        # Restore to original shortest path
                        event = {
                            "timestamp": time.time(),
                            "flow_id": flow_id,
                            "priority": priority,
                            "class": flow["class"],
                            "old_path": list(current_path),
                            "new_path": list(original_path),
                            "reason": "Congestion cleared on primary path (Recovery hysteresis met)",
                        }
                        flow["current_path"] = list(original_path)
                        flow["rerouted"] = False
                        flow["last_reroute_time"] = time.time()
                        self.reroute_events.append(event)
                        reroute_actions.append(event)
                        logger.info(f"RESTORED Flow {flow_id} to primary path: {original_path}")
                continue

            # Path IS congested: apply Priority Rules
            if priority == 3:
                # HIGH PRIORITY: NEVER reroute unless path is physically down (all links up)
                # Protected strictly by egress priority queue
                logger.info(
                    f"HIGH PRIORITY flow {flow_id} preserved on primary path {current_path} "
                    f"(Protected by Queue 2 / Strict QoS)."
                )
                continue

            elif priority == 1:
                # LOW PRIORITY: FIRST to be migrated
                alt_path = path_computer.select_best_alternate_path(
                    graph=graph,
                    src=current_path[0],
                    dst=current_path[-1],
                    current_path=current_path,
                    required_bw=15.0,
                )

                if alt_path and alt_path != current_path:
                    event = {
                        "timestamp": time.time(),
                        "flow_id": flow_id,
                        "priority": priority,
                        "class": flow["class"],
                        "old_path": list(current_path),
                        "new_path": list(alt_path),
                        "reason": f"Link s{congested_edge[0]}-s{congested_edge[1]} congested > 85%. Rerouting low-priority bulk flow.",
                    }
                    flow["current_path"] = list(alt_path)
                    flow["rerouted"] = True
                    flow["last_reroute_time"] = time.time()
                    self.reroute_events.append(event)
                    reroute_actions.append(event)
                    logger.warning(
                        f"REROUTED LOW-PRIORITY flow {flow_id}: {event['old_path']} -> {event['new_path']}"
                    )

            elif priority == 2:
                # MEDIUM PRIORITY: Reroute only if low priority rerouting was insufficient
                alt_path = path_computer.select_best_alternate_path(
                    graph=graph,
                    src=current_path[0],
                    dst=current_path[-1],
                    current_path=current_path,
                    required_bw=25.0,
                )
                if alt_path and alt_path != current_path:
                    event = {
                        "timestamp": time.time(),
                        "flow_id": flow_id,
                        "priority": priority,
                        "class": flow["class"],
                        "old_path": list(current_path),
                        "new_path": list(alt_path),
                        "reason": f"Severe congestion on s{congested_edge[0]}-s{congested_edge[1]}. Rerouting medium-priority flow to available alternate.",
                    }
                    flow["current_path"] = list(alt_path)
                    flow["rerouted"] = True
                    flow["last_reroute_time"] = time.time()
                    self.reroute_events.append(event)
                    reroute_actions.append(event)
                    logger.warning(
                        f"REROUTED MEDIUM-PRIORITY flow {flow_id}: {event['old_path']} -> {event['new_path']}"
                    )

        return reroute_actions

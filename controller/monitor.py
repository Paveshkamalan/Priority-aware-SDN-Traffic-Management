"""
Network Monitor Module
Periodically collects OpenFlow 1.3 port statistics and queue statistics,
computes transmit bitrates and link utilization percentages, and maintains historical data.
"""

import collections
import logging
import time
from typing import Dict, Tuple, Any, List, Optional

logger = logging.getLogger("NetworkMonitor")


class NetworkMonitor:
    """
    Monitors switch ports, links, and queues to compute real-time throughput and utilization.
    """

    def __init__(self, poll_interval: float = 0.5, history_length: int = 60):
        self.poll_interval = poll_interval
        self.history_length = history_length

        # (dpid, port_no) -> {'tx_bytes': int, 'rx_bytes': int, 'timestamp': float}
        self.prev_port_stats: Dict[Tuple[int, int], Dict[str, Any]] = {}
        # (dpid, port_no) -> current bitrate in bits per second
        self.port_speed_bps: Dict[Tuple[int, int], float] = {}

        # (dpid, port_no, queue_id) -> {'tx_bytes': int, 'tx_packets': int, 'tx_errors': int, 'timestamp': float}
        self.prev_queue_stats: Dict[Tuple[int, int, int], Dict[str, Any]] = {}
        self.queue_speed_bps: Dict[Tuple[int, int, int], float] = {}

        # Link utilization: (u_dpid, v_dpid) -> float [0.0, 1.0]
        self.link_utilization: Dict[Tuple[int, int], float] = {}
        # Directional link speed in bps: (u, v) -> tx_bps
        self.directional_speed_bps: Dict[Tuple[int, int], float] = {}
        # History of link utilization: (u, v) -> deque of (timestamp, util)
        self.history: Dict[Tuple[int, int], collections.deque] = {}

        # Flow throughput tracking: flow_id -> current bps
        self.flow_throughput_bps: Dict[str, float] = {}
        self.prev_flow_stats: Dict[str, Dict[str, Any]] = {}

    def update_port_stats(
        self, dpid: int, port_no: int, tx_bytes: int, rx_bytes: int, timestamp: Optional[float] = None
    ) -> float:
        """
        Record port stats and compute transmit bitrate in bits per second.
        """
        now = timestamp or time.time()
        key = (dpid, port_no)
        speed_bps = 0.0

        if key in self.prev_port_stats:
            prev = self.prev_port_stats[key]
            dt = max(now - prev["timestamp"], 0.001)
            delta_tx = max(tx_bytes - prev["tx_bytes"], 0)
            speed_bps = (delta_tx * 8.0) / dt

        self.prev_port_stats[key] = {
            "tx_bytes": tx_bytes,
            "rx_bytes": rx_bytes,
            "timestamp": now,
        }
        self.port_speed_bps[key] = speed_bps
        return speed_bps

    def update_queue_stats(
        self,
        dpid: int,
        port_no: int,
        queue_id: int,
        tx_bytes: int,
        tx_packets: int,
        tx_errors: int,
        timestamp: Optional[float] = None,
    ) -> float:
        """
        Record queue stats and compute queue transmit bitrate.
        """
        now = timestamp or time.time()
        key = (dpid, port_no, queue_id)
        speed_bps = 0.0

        if key in self.prev_queue_stats:
            prev = self.prev_queue_stats[key]
            dt = max(now - prev["timestamp"], 0.001)
            delta_tx = max(tx_bytes - prev["tx_bytes"], 0)
            speed_bps = (delta_tx * 8.0) / dt

        self.prev_queue_stats[key] = {
            "tx_bytes": tx_bytes,
            "tx_packets": tx_packets,
            "tx_errors": tx_errors,
            "timestamp": now,
        }
        self.queue_speed_bps[key] = speed_bps
        return speed_bps

    def calculate_link_utilization(
        self, u: int, v: int, port_no: int, link_capacity_mbps: float
    ) -> float:
        """
        Calculates link utilization = current_transmit_rate / link_capacity.
        Tracks directional traffic rates to ensure peak link utilization across both directions.
        """
        key = (u, port_no)
        tx_bps = self.port_speed_bps.get(key, 0.0)
        self.directional_speed_bps[(u, v)] = tx_bps

        capacity_bps = max(link_capacity_mbps * 1_000_000.0, 1.0)

        # Peak utilization across both directions of the link (u -> v and v -> u)
        rev_tx = self.directional_speed_bps.get((v, u), 0.0)
        peak_tx_bps = max(tx_bps, rev_tx)
        utilization = min(peak_tx_bps / capacity_bps, 1.0)

        link_key = tuple(sorted([u, v]))
        self.link_utilization[link_key] = round(utilization, 4)

        if link_key not in self.history:
            self.history[link_key] = collections.deque(maxlen=self.history_length)
        self.history[link_key].append({"timestamp": time.time(), "utilization": round(utilization, 4)})

        return round(utilization, 4)

    def get_link_utilization(self, u: int, v: int) -> float:
        link_key = tuple(sorted([u, v]))
        return self.link_utilization.get(link_key, 0.0)

    def get_all_metrics(self) -> Dict[str, Any]:
        """Returns consolidated metrics summary for API and dashboard."""
        links_data = []
        for (u, v), util in self.link_utilization.items():
            links_data.append({
                "link": f"s{u}-s{v}",
                "u": u,
                "v": v,
                "utilization": util,
                "utilization_pct": round(util * 100.0, 2),
            })

        queues_data = []
        for (dpid, port, qid), speed in self.queue_speed_bps.items():
            queues_data.append({
                "switch": f"s{dpid}",
                "port": port,
                "queue_id": qid,
                "throughput_mbps": round(speed / 1_000_000.0, 3),
            })

        return {
            "links": links_data,
            "queues": queues_data,
            "timestamp": time.time(),
        }

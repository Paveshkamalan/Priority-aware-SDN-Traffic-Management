"""
QoS Manager Module
Implements priority-aware forwarding, traffic classification, and OpenFlow 1.3 queue action mapping.
Maps high-, medium-, and low-priority traffic flows into designated hardware/software queues.
"""

import logging
from typing import Dict, Any, Tuple, Optional

logger = logging.getLogger("QoSManager")


class QoSManager:
    """
    Manages QoS queue assignments and OpenFlow queue action rules.
    Queues:
      - Queue 2: High Priority (Weight: 60%, Voice/Emergency UDP port 5001, DSCP 46 / TOS 184)
      - Queue 1: Medium Priority (Weight: 30%, Interactive TCP port 5002, DSCP 26 / TOS 104)
      - Queue 0: Low Priority (Weight: 10%, Bulk TCP port 5003, DSCP 0 / TOS 0)
    """

    def __init__(self, enabled: bool = True):
        self.enabled = enabled
        self.port_priority_map = {
            5001: {"priority": 3, "class": "high", "queue_id": 2, "dscp": 46},
            5002: {"priority": 2, "class": "medium", "queue_id": 1, "dscp": 26},
            5003: {"priority": 1, "class": "low", "queue_id": 0, "dscp": 0},
        }

    def set_enabled(self, status: bool) -> None:
        self.enabled = status
        logger.info(f"QoS priority queueing enabled status set to: {self.enabled}")

    def classify_packet(
        self,
        ip_proto: Optional[int] = None,
        src_port: Optional[int] = None,
        dst_port: Optional[int] = None,
        tos: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Classifies incoming packet into priority class and queue ID.
        Returns dict with keys: 'priority', 'class', 'queue_id', 'description'.
        """
        # 1. Check by transport port
        target_port = dst_port or src_port
        if target_port in self.port_priority_map:
            info = dict(self.port_priority_map[target_port])
            if not self.enabled:
                info["queue_id"] = 0  # Default queue when QoS disabled
            return info

        # 2. Check by IP TOS / DSCP
        if tos is not None:
            dscp = (tos >> 2) & 0x3F
            if dscp >= 40:  # Expedited Forwarding / High
                return {
                    "priority": 3,
                    "class": "high",
                    "queue_id": 2 if self.enabled else 0,
                    "dscp": dscp,
                }
            elif dscp >= 20:  # Assured Forwarding / Medium
                return {
                    "priority": 2,
                    "class": "medium",
                    "queue_id": 1 if self.enabled else 0,
                    "dscp": dscp,
                }

        # 3. Default: Low Priority / Best Effort
        return {
            "priority": 1,
            "class": "low",
            "queue_id": 0,
            "dscp": 0,
        }

    def get_queue_id_for_flow(self, flow_meta: Dict[str, Any]) -> int:
        """Determines queue ID for a flow dictionary."""
        if not self.enabled:
            return 0
        classification = self.classify_packet(
            ip_proto=flow_meta.get("proto"),
            dst_port=flow_meta.get("dst_port"),
            tos=flow_meta.get("tos"),
        )
        return classification["queue_id"]

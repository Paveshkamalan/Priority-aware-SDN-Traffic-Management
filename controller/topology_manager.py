"""
Topology Manager Module
Maintains network topology graph, switch port mappings, host locations, and link attributes.
Supports both static configuration bootstrapping and dynamic OpenFlow/LLDP discovery.
"""

import logging
import os
import re
from typing import Dict, Any, List, Tuple, Optional, Set
import yaml

logger = logging.getLogger("TopologyManager")


class TopologyManager:
    """
    Tracks network topology state: switches, links, ports, hosts, and capacities.
    """

    def __init__(self, config_path: Optional[str] = None):
        self.config_path = config_path or os.path.join(
            os.path.dirname(__file__), "..", "config", "topology.yaml"
        )
        self.switches: Dict[int, Dict[str, Any]] = {}  # dpid -> info
        self.hosts: Dict[str, Dict[str, Any]] = {}     # ip/mac -> info
        # port_map: (src_dpid, dst_dpid) -> egress_port_on_src
        self.port_map: Dict[Tuple[int, int], int] = {}
        # host_port_map: (dpid, host_ip) -> port
        self.host_port_map: Dict[Tuple[int, str], int] = {}
        # Adjacency graph: {u_dpid: {v_dpid: {'bw': Mbps, 'delay': ms, 'cost': int, 'utilization': float}}}
        self.graph: Dict[int, Dict[int, Dict[str, Any]]] = {}
        self.links: List[Dict[str, Any]] = []

        self._load_from_config()

    def _parse_delay_ms(self, delay_str: Any) -> float:
        """Parses '2ms' or 2.0 to numeric float 2.0."""
        if isinstance(delay_str, (int, float)):
            return float(delay_str)
        m = re.match(r"([0-9.]+)\s*ms", str(delay_str).lower())
        if m:
            return float(m.group(1))
        return 1.0

    def _load_from_config(self) -> None:
        """Bootstraps topology metadata from YAML configuration file."""
        if not os.path.exists(self.config_path):
            logger.warning(f"Config path {self.config_path} does not exist. Using empty graph.")
            return

        with open(self.config_path, "r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f)

        # 1. Switches
        for sw in cfg.get("switches", []):
            sw_id = sw["id"]
            dpid_int = int(sw_id.replace("s", ""))
            self.switches[dpid_int] = {
                "id": sw_id,
                "dpid": dpid_int,
                "dpid_hex": f"{dpid_int:016x}",
                "description": sw.get("description", ""),
                "ports": {},
            }
            self.graph[dpid_int] = {}

        # 2. Hosts
        for h in cfg.get("hosts", []):
            h_id = h["id"]
            ip = h.get("ip", "10.0.0.1")
            mac = h.get("mac", "")
            connected_sw = int(h.get("connected_to", "s1").replace("s", ""))
            port = h.get("port", 1)
            self.hosts[ip] = {
                "id": h_id,
                "name": h.get("name", h_id),
                "ip": ip,
                "mac": mac,
                "switch_dpid": connected_sw,
                "port": port,
            }
            self.host_port_map[(connected_sw, ip)] = port

        # 3. Links
        for link in cfg.get("links", []):
            n1 = link["node1"]
            n2 = link["node2"]
            bw = float(link.get("bw", 100))
            delay = self._parse_delay_ms(link.get("delay", "1ms"))
            loss = float(link.get("loss", 0))
            cost = int(link.get("cost", 1))

            if n1.startswith("s") and n2.startswith("s"):
                u = int(n1.replace("s", ""))
                v = int(n2.replace("s", ""))

                self.graph.setdefault(u, {})[v] = {
                    "bw": bw,
                    "delay": delay,
                    "loss": loss,
                    "cost": cost,
                    "utilization": 0.0,
                    "tx_bytes": 0,
                    "status": "UP",
                }
                self.graph.setdefault(v, {})[u] = {
                    "bw": bw,
                    "delay": delay,
                    "loss": loss,
                    "cost": cost,
                    "utilization": 0.0,
                    "tx_bytes": 0,
                    "status": "UP",
                }
                self.links.append({
                    "src": u,
                    "dst": v,
                    "bw": bw,
                    "delay": delay,
                    "loss": loss,
                    "utilization": 0.0,
                })

        # Switch-to-switch port mapping
        standard_ports = {
            (1, 2): 2, (2, 1): 1,
            (1, 3): 3, (3, 1): 1,
            (2, 4): 2, (4, 2): 1,
            (2, 5): 3, (5, 2): 1,
            (3, 5): 2, (5, 3): 2,
            (4, 6): 2, (6, 4): 2,
            (5, 6): 3, (6, 5): 3,
        }
        self.port_map.update(standard_ports)

    def add_switch(self, dpid: int) -> None:
        if dpid not in self.switches:
            self.switches[dpid] = {
                "id": f"s{dpid}",
                "dpid": dpid,
                "dpid_hex": f"{dpid:016x}",
                "ports": {},
            }
        self.graph.setdefault(dpid, {})

    def add_link(self, src_dpid: int, src_port: int, dst_dpid: int, dst_port: int) -> None:
        """Register link discovery event from LLDP."""
        self.port_map[(src_dpid, dst_dpid)] = src_port
        self.port_map[(dst_dpid, src_dpid)] = dst_port

        self.graph.setdefault(src_dpid, {}).setdefault(
            dst_dpid, {"bw": 40.0, "delay": 2.0, "cost": 2, "utilization": 0.0, "status": "UP"}
        )
        self.graph.setdefault(dst_dpid, {}).setdefault(
            src_dpid, {"bw": 40.0, "delay": 2.0, "cost": 2, "utilization": 0.0, "status": "UP"}
        )

    def remove_link(self, src_dpid: int, dst_dpid: int) -> None:
        """Mark link as down / removed."""
        if src_dpid in self.graph and dst_dpid in self.graph[src_dpid]:
            self.graph[src_dpid][dst_dpid]["status"] = "DOWN"
            self.graph[src_dpid][dst_dpid]["utilization"] = 1.0
        if dst_dpid in self.graph and src_dpid in self.graph[dst_dpid]:
            self.graph[dst_dpid][src_dpid]["status"] = "DOWN"
            self.graph[dst_dpid][src_dpid]["utilization"] = 1.0

    def update_link_utilization(self, u: int, v: int, utilization: float, tx_bytes: int = 0) -> None:
        """Update real-time utilization measurement for link (u, v)."""
        if u in self.graph and v in self.graph[u]:
            self.graph[u][v]["utilization"] = round(utilization, 4)
            self.graph[u][v]["tx_bytes"] = tx_bytes
        if v in self.graph and u in self.graph[v]:
            self.graph[v][u]["utilization"] = round(utilization, 4)
            self.graph[v][u]["tx_bytes"] = tx_bytes

    def get_egress_port(self, current_dpid: int, next_hop_dpid: int) -> int:
        """Return the switch port connected to the next hop switch."""
        if (current_dpid, next_hop_dpid) in self.port_map:
            return self.port_map[(current_dpid, next_hop_dpid)]

        # Fallback standard Mininet port ordering based on link definition
        # S1: port 1->h1, port 2->s2, port 3->s3
        # S2: port 1->s1, port 2->s4, port 3->s5
        # S3: port 1->s1, port 2->s5
        # S4: port 1->s2, port 2->s6
        # S5: port 1->s2, port 2->s3, port 3->s6
        # S6: port 1->h2, port 2->s4, port 3->s5
        fallback_ports = {
            (1, 2): 2, (1, 3): 3,
            (2, 1): 1, (2, 4): 2, (2, 5): 3,
            (3, 1): 1, (3, 5): 2,
            (4, 2): 1, (4, 6): 2,
            (5, 2): 1, (5, 3): 2, (5, 6): 3,
            (6, 4): 2, (6, 5): 3,
        }
        return fallback_ports.get((current_dpid, next_hop_dpid), 1)

    def get_host_port(self, dpid: int, host_ip: str) -> Optional[int]:
        """Return the port connecting switch dpid to host_ip."""
        return self.host_port_map.get((dpid, host_ip), 1 if (dpid == 1 or dpid == 6) else None)

    def to_dict(self) -> Dict[str, Any]:
        """Export serialized topology for Web UI and REST API."""
        nodes = []
        for dpid, sw in self.switches.items():
            nodes.append({
                "id": f"s{dpid}",
                "label": f"Switch S{dpid}",
                "type": "switch",
                "dpid": dpid,
            })
        for ip, h in self.hosts.items():
            nodes.append({
                "id": h["id"],
                "label": f"{h['name']}\n({ip})",
                "type": "host",
                "ip": ip,
                "connected_to": f"s{h['switch_dpid']}",
            })

        edges = []
        # Host edges
        for ip, h in self.hosts.items():
            edges.append({
                "from": h["id"],
                "to": f"s{h['switch_dpid']}",
                "bw": 100,
                "delay": "1ms",
                "utilization": 0.0,
                "status": "UP",
            })

        # Switch edges (undirected representation)
        seen = set()
        for u, neighbors in self.graph.items():
            for v, attrs in neighbors.items():
                edge_id = tuple(sorted([u, v]))
                if edge_id not in seen:
                    seen.add(edge_id)
                    edges.append({
                        "from": f"s{u}",
                        "to": f"s{v}",
                        "bw": attrs.get("bw", 40),
                        "delay": f"{attrs.get('delay', 2)}ms",
                        "utilization": attrs.get("utilization", 0.0),
                        "status": attrs.get("status", "UP"),
                    })

        return {"nodes": nodes, "edges": edges}

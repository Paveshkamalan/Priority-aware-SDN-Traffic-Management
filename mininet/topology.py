"""
Custom Mininet Multi-Path Topology
Loads configuration strictly from config/topology.yaml.
Supports 6 Open vSwitch switches and 2 server hosts with defined link characteristics.
"""

import os
from typing import Dict, Any, Optional
import yaml
from mininet.topo import Topo


class MultiPathSDNTopo(Topo):
    r"""
    Priority-Aware Multi-Path SDN Topology based on config/topology.yaml.
    Topology structure:
      h1 (Server A) --- s1 --- s2 --- s4 --- s6 --- h2 (Server B)
                         |      \     /       |
                         |       \   /        |
                         |        s5 ---------+
                         |       /
                         +---- s3
    """

    def __init__(self, config_path: Optional[str] = None, **opts):
        """
        Initialize topology from YAML configuration file.
        :param config_path: Absolute or relative path to topology.yaml
        """
        if config_path is None:
            # Default to ../config/topology.yaml relative to this script
            base_dir = os.path.dirname(os.path.abspath(__file__))
            config_path = os.path.join(base_dir, "..", "config", "topology.yaml")

        self.config_path = os.path.abspath(config_path)
        self.config_data = self._load_config(self.config_path)
        super(MultiPathSDNTopo, self).__init__(**opts)

    @staticmethod
    def _load_config(path: str) -> Dict[str, Any]:
        """Load and parse YAML topology configuration."""
        if not os.path.exists(path):
            raise FileNotFoundError(f"Topology configuration file not found at: {path}")
        with open(path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)

    def build(self, **_opts):
        """Build switches, hosts, and links dynamically from configuration."""
        # 1. Add Switches
        switches_cfg = self.config_data.get("switches", [])
        for sw in switches_cfg:
            sw_id = sw["id"]
            dpid = sw.get("dpid")
            # Mininet expects dpid as hex string without leading '0x' if formatted,
            # or decimal/hex representation
            self.addSwitch(sw_id, dpid=dpid)

        # 2. Add Hosts
        hosts_cfg = self.config_data.get("hosts", [])
        for h in hosts_cfg:
            h_id = h["id"]
            ip = h.get("ip", "10.0.0.1")
            mac = h.get("mac", None)
            self.addHost(h_id, ip=ip, mac=mac)

        # 3. Add Links
        links_cfg = self.config_data.get("links", [])
        for link in links_cfg:
            node1 = link["node1"]
            node2 = link["node2"]
            bw = link.get("bw", 100)
            delay = link.get("delay", "1ms")
            loss = link.get("loss", 0)
            max_queue_size = link.get("max_queue_size", 1000)

            link_opts = {
                "bw": bw,
                "delay": delay,
                "loss": loss,
                "max_queue_size": max_queue_size,
                "use_htb": True,
            }
            self.addLink(node1, node2, **link_opts)


topos = {"multipath_sdn": MultiPathSDNTopo}

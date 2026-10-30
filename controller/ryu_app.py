"""
Main Ryu SDN Controller Application
Priority-Aware Adaptive Traffic Management in Multi-Path SDN Networks.
OpenFlow 1.3 implementation integrating Topology Discovery, Dijkstra Routing,
Real-Time Port/Queue Monitoring, Congestion-Aware Rerouting, and QoS Queue Mapping.
"""

import json
import logging
import time
from typing import Dict, Any, List, Optional

try:
    from ryu.base import app_manager
    from ryu.controller import ofp_event
    from ryu.controller.handler import CONFIG_DISPATCHER, MAIN_DISPATCHER, set_ev_cls
    from ryu.ofproto import ofproto_v1_3
    from ryu.lib.packet import packet, ethernet, ether_types, arp, ipv4, tcp, udp
    from ryu.lib import hub
except ImportError:
    # Fallback to os_ken if ryu is aliased
    from os_ken.base import app_manager
    from os_ken.controller import ofp_event
    from os_ken.controller.handler import CONFIG_DISPATCHER, MAIN_DISPATCHER, set_ev_cls
    from os_ken.ofproto import ofproto_v1_3
    from os_ken.lib.packet import packet, ethernet, ether_types, arp, ipv4, tcp, udp
    from os_ken.lib import hub

from topology_manager import TopologyManager
from path_computer import PathComputer
from monitor import NetworkMonitor
from qos_manager import QoSManager
from rerouter import PriorityRerouter
from rest_api import start_rest_server

logger = logging.getLogger("SDNControllerApp")


class PrioritySDNController(app_manager.RyuApp):
    """
    Ryu SDN Controller for Multi-Path Priority-Aware Adaptive Traffic Management.
    """

    OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION]

    def __init__(self, *args, **kwargs):
        super(PrioritySDNController, self).__init__(*args, **kwargs)

        # Core modules
        self.topo_mgr = TopologyManager()
        self.path_computer = PathComputer(default_congestion_penalty=10.0)
        self.monitor = NetworkMonitor(poll_interval=0.5)
        self.qos_mgr = QoSManager(enabled=True)
        self.rerouter = PriorityRerouter(
            warning_threshold=0.60,
            congestion_threshold=0.80,
            recovery_threshold=0.45,
            congestion_intervals=2,
            recovery_intervals=4,
            enabled=True,
        )

        # Connected datapaths: dpid -> datapath object
        self.datapaths: Dict[int, Any] = {}
        # MAC-to-port learning table: dpid -> {mac: port}
        self.mac_to_port: Dict[int, Dict[str, int]] = {}

        # Default paths: S1 -> S6
        # Path 1: S1 -> S2 -> S4 -> S6 (Shortest baseline)
        self.default_path = [1, 2, 4, 6]

        # Register standard default flows
        self._register_default_traffic_flows()

        # Start periodic monitoring greenlet (1 Hz)
        self.monitor_thread = hub.spawn(self._monitor_loop)

        # Start REST API server on port 8080
        self.rest_server = start_rest_server(self, host="0.0.0.0", port=8080)
        logger.info("PrioritySDNController initialized successfully with OF 1.3.")

    def _register_default_traffic_flows(self) -> None:
        """Register the 3 standard traffic classes into rerouter flow registry."""
        self.rerouter.register_flow(
            flow_id="flow_high_voip",
            priority=3,
            traffic_class="high",
            initial_path=[1, 2, 4, 6],
            src_ip="10.0.0.1",
            dst_ip="10.0.0.2",
            dst_port=5001,
            proto="udp",
        )
        self.rerouter.register_flow(
            flow_id="flow_medium_web",
            priority=2,
            traffic_class="medium",
            initial_path=[1, 2, 4, 6],
            src_ip="10.0.0.1",
            dst_ip="10.0.0.2",
            dst_port=5002,
            proto="tcp",
        )
        self.rerouter.register_flow(
            flow_id="flow_low_bulk",
            priority=1,
            traffic_class="low",
            initial_path=[1, 2, 4, 6],
            src_ip="10.0.0.1",
            dst_ip="10.0.0.2",
            dst_port=5003,
            proto="tcp",
        )

    # --------------------------------------------------------------------------
    # Switch Handshake & Table-Miss Rule Installation
    # --------------------------------------------------------------------------

    @set_ev_cls(ofp_event.EventOFPSwitchFeatures, CONFIG_DISPATCHER)
    def switch_features_handler(self, ev):
        """Install table-miss entry on switch connection."""
        datapath = ev.msg.datapath
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser
        dpid = datapath.id

        self.datapaths[dpid] = datapath
        self.topo_mgr.add_switch(dpid)
        logger.info(f"Switch S{dpid} connected. Installing table-miss flow entry.")

        # Table-miss entry: match any packet, send to controller (priority 0)
        match = parser.OFPMatch()
        actions = [
            parser.OFPActionOutput(ofproto.OFPP_CONTROLLER, ofproto.OFPCML_NO_BUFFER)
        ]
        self.add_flow(datapath, priority=0, match=match, actions=actions)

    def add_flow(
        self,
        datapath,
        priority: int,
        match,
        actions,
        buffer_id: Optional[int] = None,
        idle_timeout: int = 0,
        hard_timeout: int = 0,
    ) -> None:
        """Helper to construct and send OFPFlowMod to datapath."""
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser

        inst = [parser.OFPInstructionActions(ofproto.OFPIT_APPLY_ACTIONS, actions)]
        if buffer_id:
            mod = parser.OFPFlowMod(
                datapath=datapath,
                buffer_id=buffer_id,
                priority=priority,
                match=match,
                instructions=inst,
                idle_timeout=idle_timeout,
                hard_timeout=hard_timeout,
            )
        else:
            mod = parser.OFPFlowMod(
                datapath=datapath,
                priority=priority,
                match=match,
                instructions=inst,
                idle_timeout=idle_timeout,
                hard_timeout=hard_timeout,
            )
        datapath.send_msg(mod)

    # --------------------------------------------------------------------------
    # Packet-In Processing (ARP, IPv4, TCP/UDP Classification & Path Setup)
    # --------------------------------------------------------------------------

    @set_ev_cls(ofp_event.EventOFPPacketIn, MAIN_DISPATCHER)
    def packet_in_handler(self, ev):
        """Handles incoming PacketIn messages from switches."""
        msg = ev.msg
        datapath = msg.datapath
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser
        in_port = msg.match["in_port"]
        dpid = datapath.id

        pkt = packet.Packet(msg.data)
        eth = pkt.get_protocols(ethernet.ethernet)[0]

        # Ignore LLDP packets
        if eth.ethertype == ether_types.ETH_TYPE_LLDP:
            return

        dst = eth.dst
        src = eth.src

        # Learn MAC address for simple flooding prevention
        self.mac_to_port.setdefault(dpid, {})[src] = in_port

        # Handle ARP (Broadcast / Flood across edge or reply)
        pkt_arp = pkt.get_protocol(arp.arp)
        if pkt_arp:
            self._handle_arp(datapath, in_port, pkt, eth, pkt_arp)
            return

        # Handle IPv4 Packets
        pkt_ipv4 = pkt.get_protocol(ipv4.ipv4)
        if pkt_ipv4:
            self._handle_ipv4(datapath, in_port, pkt, eth, pkt_ipv4, msg)
            return

        # Fallback L2 forwarding
        out_port = self.mac_to_port[dpid].get(dst, ofproto.OFPP_FLOOD)
        actions = [parser.OFPActionOutput(out_port)]
        out = parser.OFPPacketOut(
            datapath=datapath,
            buffer_id=msg.buffer_id,
            in_port=in_port,
            actions=actions,
            data=msg.data if msg.buffer_id == ofproto.OFP_NO_BUFFER else None,
        )
        datapath.send_msg(out)

    def _handle_arp(self, datapath, in_port, pkt, eth, pkt_arp):
        """
        Handles ARP resolution using Proxy ARP to eliminate broadcast loops
        and packet loss across multi-path meshed topologies.
        """
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser
        dpid = datapath.id

        if pkt_arp.opcode == arp.ARP_REQUEST:
            target_ip = pkt_arp.dst_ip
            target_host = self.topo_mgr.hosts.get(target_ip)
            if target_host:
                target_mac = target_host["mac"]
                # Formulate instant ARP Reply from controller proxy
                pkt_reply = packet.Packet()
                pkt_reply.add_protocol(ethernet.ethernet(
                    ethertype=ether_types.ETH_TYPE_ARP,
                    dst=eth.src,
                    src=target_mac,
                ))
                pkt_reply.add_protocol(arp.arp(
                    opcode=arp.ARP_REPLY,
                    src_mac=target_mac,
                    src_ip=target_ip,
                    dst_mac=pkt_arp.src_mac,
                    dst_ip=pkt_arp.src_ip,
                ))
                pkt_reply.serialize()
                actions = [parser.OFPActionOutput(in_port)]
                out = parser.OFPPacketOut(
                    datapath=datapath,
                    buffer_id=ofproto.OFP_NO_BUFFER,
                    in_port=ofproto.OFPP_CONTROLLER,
                    actions=actions,
                    data=pkt_reply.data,
                )
                datapath.send_msg(out)
                return

        # Forward non-request ARPs directly to destination host edge port if known
        host_port = self.topo_mgr.get_host_port(dpid, pkt_arp.dst_ip)
        if host_port:
            actions = [parser.OFPActionOutput(host_port)]
            out = parser.OFPPacketOut(
                datapath=datapath,
                buffer_id=ofproto.OFP_NO_BUFFER,
                in_port=in_port,
                actions=actions,
                data=pkt.data,
            )
            datapath.send_msg(out)

    def _handle_ipv4(self, datapath, in_port, pkt, eth, pkt_ipv4, msg):
        """
        Classifies IPv4 flow, assigns priority queue, computes path, and installs rules.
        """
        parser = datapath.ofproto_parser
        ofproto = datapath.ofproto
        dpid = datapath.id

        src_ip = pkt_ipv4.src
        dst_ip = pkt_ipv4.dst
        proto = pkt_ipv4.proto
        tos = pkt_ipv4.tos

        dst_port = None
        src_port = None
        pkt_tcp = pkt.get_protocol(tcp.tcp)
        pkt_udp = pkt.get_protocol(udp.udp)

        if pkt_tcp:
            dst_port = pkt_tcp.dst_port
            src_port = pkt_tcp.src_port
        elif pkt_udp:
            dst_port = pkt_udp.dst_port
            src_port = pkt_udp.src_port

        # Classify flow using QoS Manager
        class_info = self.qos_mgr.classify_packet(
            ip_proto=proto, src_port=src_port, dst_port=dst_port, tos=tos
        )
        queue_id = class_info["queue_id"]
        priority_level = class_info["priority"]

        # Determine path: Check if flow already exists in rerouter registry
        flow_key = f"{src_ip}:{dst_ip}:{dst_port or 0}"
        assigned_path = self.default_path

        # Check rerouter flow entries
        for f_id, f_data in self.rerouter.active_flows.items():
            if f_data.get("dst_port") == dst_port:
                assigned_path = f_data["current_path"]
                break

        # Install path across all switches along assigned_path
        self._install_path_rules(assigned_path, src_ip, dst_ip, dst_port, proto, queue_id)

        # Output current packet
        if dpid in assigned_path:
            idx = assigned_path.index(dpid)
            if idx < len(assigned_path) - 1:
                next_hop = assigned_path[idx + 1]
                out_port = self.topo_mgr.get_egress_port(dpid, next_hop)
            else:
                out_port = self.topo_mgr.get_host_port(dpid, dst_ip) or 1
        else:
            out_port = ofproto.OFPP_FLOOD

        actions = []
        if self.qos_mgr.enabled and queue_id > 0:
            actions.append(parser.OFPActionSetQueue(queue_id))
        actions.append(parser.OFPActionOutput(out_port))

        out = parser.OFPPacketOut(
            datapath=datapath,
            buffer_id=msg.buffer_id,
            in_port=in_port,
            actions=actions,
            data=msg.data if msg.buffer_id == ofproto.OFP_NO_BUFFER else None,
        )
        datapath.send_msg(out)

    def _install_path_rules(
        self,
        path: List[int],
        src_ip: str,
        dst_ip: str,
        dst_port: Optional[int],
        proto: int,
        queue_id: int,
        flow_priority: int = 100,
    ) -> None:
        """
        Installs OpenFlow 1.3 forwarding rules along every switch in 'path'.
        Forward path: src_ip -> dst_ip
        Reverse path: dst_ip -> src_ip
        """
        for i in range(len(path)):
            curr_dpid = path[i]
            dp = self.datapaths.get(curr_dpid)
            if not dp:
                continue

            parser = dp.ofproto_parser

            # Determine out_port for forward direction
            if i < len(path) - 1:
                next_dpid = path[i + 1]
                out_port_fwd = self.topo_mgr.get_egress_port(curr_dpid, next_dpid)
            else:
                out_port_fwd = self.topo_mgr.get_host_port(curr_dpid, dst_ip) or 1

            # Determine in_port / reverse out_port for backward direction
            if i > 0:
                prev_dpid = path[i - 1]
                out_port_rev = self.topo_mgr.get_egress_port(curr_dpid, prev_dpid)
            else:
                out_port_rev = self.topo_mgr.get_host_port(curr_dpid, src_ip) or 1

            # Construct Forward Match & Actions
            actions_fwd = []
            if self.qos_mgr.enabled and queue_id > 0:
                actions_fwd.append(parser.OFPActionSetQueue(queue_id))
            actions_fwd.append(parser.OFPActionOutput(out_port_fwd))

            match_args_fwd = {
                "eth_type": ether_types.ETH_TYPE_IP,
                "ipv4_src": src_ip,
                "ipv4_dst": dst_ip,
                "ip_proto": proto,
            }
            if dst_port:
                if proto == 6:  # TCP
                    match_args_fwd["tcp_dst"] = dst_port
                elif proto == 17:  # UDP
                    match_args_fwd["udp_dst"] = dst_port

            match_fwd = parser.OFPMatch(**match_args_fwd)
            self.add_flow(dp, priority=flow_priority, match=match_fwd, actions=actions_fwd, idle_timeout=30)

            # Construct Reverse Match & Actions
            actions_rev = [parser.OFPActionOutput(out_port_rev)]
            match_args_rev = {
                "eth_type": ether_types.ETH_TYPE_IP,
                "ipv4_src": dst_ip,
                "ipv4_dst": src_ip,
                "ip_proto": proto,
            }
            if dst_port:
                if proto == 6:
                    match_args_rev["tcp_src"] = dst_port
                elif proto == 17:
                    match_args_rev["udp_src"] = dst_port

            match_rev = parser.OFPMatch(**match_args_rev)
            self.add_flow(dp, priority=flow_priority, match=match_rev, actions=actions_rev, idle_timeout=30)

    # --------------------------------------------------------------------------
    # Monitoring & Dynamic Congestion Rerouting Loop
    # --------------------------------------------------------------------------

    def _monitor_loop(self):
        """Greenlet periodic stats polling thread running at 2 Hz (every 0.5s for fast demo feedback)."""
        while True:
            for dp in list(self.datapaths.values()):
                self._request_stats(dp)
            hub.sleep(0.5)

    def _request_stats(self, datapath):
        """Sends OFPPortStatsRequest and OFPQueueStatsRequest to datapath."""
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser
        # Port stats request
        req_port = parser.OFPPortStatsRequest(datapath, 0, ofproto.OFPP_ANY)
        datapath.send_msg(req_port)
        # Queue stats request
        req_queue = parser.OFPQueueStatsRequest(datapath, 0, ofproto.OFPP_ANY, ofproto.OFPQ_ALL)
        datapath.send_msg(req_queue)

    @set_ev_cls(ofp_event.EventOFPPortStatsReply, MAIN_DISPATCHER)
    def port_stats_reply_handler(self, ev):
        """Handles port statistics replies, computes link utilization, and triggers rerouting."""
        body = ev.msg.body
        dpid = ev.msg.datapath.id

        for stat in body:
            port_no = stat.port_no
            if port_no > 50:  # Skip LOCAL port
                continue

            tx_bytes = stat.tx_bytes
            rx_bytes = stat.rx_bytes
            self.monitor.update_port_stats(dpid, port_no, tx_bytes, rx_bytes)

            # Find peer node connected to this port
            peer_dpid = None
            for (u, v), p in self.topo_mgr.port_map.items():
                if u == dpid and p == port_no:
                    peer_dpid = v
                    break

            if peer_dpid:
                # Get link capacity
                link_bw = self.topo_mgr.graph.get(dpid, {}).get(peer_dpid, {}).get("bw", 40.0)
                util = self.monitor.calculate_link_utilization(dpid, peer_dpid, port_no, link_bw)
                self.topo_mgr.update_link_utilization(dpid, peer_dpid, util, tx_bytes)

                # Update hysteresis counters
                self.rerouter.update_link_state(dpid, peer_dpid, util)

        # Check for congestion and execute rerouting
        if self.rerouter.enabled:
            reroute_actions = self.rerouter.check_and_reroute_flows(
                path_computer=self.path_computer,
                graph=self.topo_mgr.graph,
            )
            for action in reroute_actions:
                self._apply_reroute_action(action)

    @set_ev_cls(ofp_event.EventOFPQueueStatsReply, MAIN_DISPATCHER)
    def queue_stats_reply_handler(self, ev):
        """Handles queue statistics replies for fine-grained per-queue QoS telemetry."""
        body = ev.msg.body
        dpid = ev.msg.datapath.id
        for stat in body:
            port_no = stat.port_no
            queue_id = stat.queue_id
            self.monitor.update_queue_stats(
                dpid=dpid,
                port_no=port_no,
                queue_id=queue_id,
                tx_bytes=stat.tx_bytes,
                tx_packets=stat.tx_packets,
                tx_errors=stat.tx_errors,
            )

    def _apply_reroute_action(self, action: Dict[str, Any]) -> None:
        """
        Safely migrates a flow to its new path using make-before-break rule installation.
        """
        flow_id = action["flow_id"]
        new_path = action["new_path"]
        old_path = action["old_path"]

        flow_data = self.rerouter.active_flows.get(flow_id, {})
        src_ip = flow_data.get("src_ip", "10.0.0.1")
        dst_ip = flow_data.get("dst_ip", "10.0.0.2")
        dst_port = flow_data.get("dst_port")
        proto = 6 if flow_data.get("proto") == "tcp" else 17
        queue_id = self.qos_mgr.get_queue_id_for_flow(flow_data)

        logger.info(f"Applying Reroute for {flow_id}: Installing rules along {new_path}")
        # Install higher priority rules along new path
        self._install_path_rules(
            path=new_path,
            src_ip=src_ip,
            dst_ip=dst_ip,
            dst_port=dst_port,
            proto=proto,
            queue_id=queue_id,
            flow_priority=150,  # Higher priority to override old path rules immediately
        )

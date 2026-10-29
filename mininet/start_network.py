#!/usr/bin/env python3
"""
Mininet Network Startup and QoS Management Script
Instantiates the SDN topology with OpenFlow 1.3, connects to Ryu controller,
configures OVS priority queues, and provides programmatic control.
"""

import argparse
import json
import logging
import os
import re
import signal
import subprocess
import sys
import threading
import time
from http.server import HTTPServer, BaseHTTPRequestHandler
from typing import Dict, Any, List

import yaml
from mininet.net import Mininet
from mininet.node import RemoteController, OVSSwitch
from mininet.link import TCLink
from mininet.cli import CLI
from mininet.log import setLogLevel, info, error

# Import custom topology
from topology import MultiPathSDNTopo

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("MininetStarter")


def load_yaml(path: str) -> Dict[str, Any]:
    """Load and parse YAML file."""
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def configure_ovs_queues(net: Mininet, topo_config_path: str, qos_config_path: str) -> None:
    """
    Configures Linux HTB QoS and 3 queues (0: Low, 1: Medium, 2: High) on all switch ports
    using ovs-vsctl commands.
    Queue 0: Low priority (10% min, 100% max)
    Queue 1: Medium priority (30% min, 80% max)
    Queue 2: High priority (60% min, 100% max)
    """
    if not os.path.exists(qos_config_path):
        logger.warning(f"QoS config not found at {qos_config_path}, skipping queue setup.")
        return

    qos_cfg = load_yaml(qos_config_path)
    topo_cfg = load_yaml(topo_config_path)

    # Build map of link bandwidth per switch interface
    link_bw_map: Dict[str, int] = {}
    for link in topo_cfg.get("links", []):
        n1 = link["node1"]
        n2 = link["node2"]
        bw = link.get("bw", 100) # Mbps
        link_bw_map[f"{n1}-{n2}"] = bw
        link_bw_map[f"{n2}-{n1}"] = bw

    logger.info("Configuring OVS QoS queues on switch interfaces...")

    for sw in net.switches:
        sw_name = sw.name
        for intf in sw.intfList():
            intf_name = intf.name
            if intf_name == "lo":
                continue

            # Default link bandwidth: 100 Mbps = 100,000,000 bps
            link_rate_bps = 100_000_000
            # Try to match interface to link capacity
            for k, bw in link_bw_map.items():
                parts = k.split("-")
                if parts[0] == sw_name:
                    # check peer
                    link_rate_bps = bw * 1_000_000

            # Calculate queue min/max rates based on qos.yaml weights
            # High priority (Queue 2): 60%
            q2_min = int(link_rate_bps * 0.60)
            q2_max = int(link_rate_bps * 1.00)
            # Medium priority (Queue 1): 30%
            q1_min = int(link_rate_bps * 0.30)
            q1_max = int(link_rate_bps * 0.80)
            # Low priority (Queue 0): 10%
            q0_min = int(link_rate_bps * 0.10)
            q0_max = int(link_rate_bps * 1.00)

            # Construct ovs-vsctl command to clear old QoS and configure new HTB queues
            cmd_clear = f"ovs-vsctl --if-exists clear Port {intf_name} qos"
            subprocess.run(cmd_clear, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

            cmd_qos = (
                f"ovs-vsctl -- set Port {intf_name} qos=@newqos -- "
                f"--id=@newqos create QoS type=linux-htb "
                f"other-config:max-rate={link_rate_bps} "
                f"other-config:r2q=100 "
                f"queues=0=@q0,1=@q1,2=@q2 -- "
                f"--id=@q0 create Queue other-config:min-rate={q0_min} other-config:max-rate={q0_max} -- "
                f"--id=@q1 create Queue other-config:min-rate={q1_min} other-config:max-rate={q1_max} -- "
                f"--id=@q2 create Queue other-config:min-rate={q2_min} other-config:max-rate={q2_max}"
            )
            ret = subprocess.run(cmd_qos, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
            if ret.returncode != 0:
                logger.debug(f"OVS QoS setup for {intf_name}: {ret.stderr.strip()}")

    logger.info("OVS QoS queue configuration completed.")


class HostExecServer(BaseHTTPRequestHandler):
    net_ref = None

    def log_message(self, format, *args):
        return

    def do_POST(self):
        content_len = int(self.headers.get("Content-Length", 0))
        post_body = self.rfile.read(content_len).decode("utf-8")
        try:
            data = json.loads(post_body)
            host_name = data.get("host", "h1")
            cmd = data.get("cmd", "")
            background = data.get("background", False)
            host = self.net_ref.get(host_name) if self.net_ref else None
            if not host:
                self.send_response(404)
                self.end_headers()
                self.wfile.write(b'{"error": "Host not found"}')
                return

            if background:
                proc = host.popen(cmd, shell=True)
                res = {"status": "ok", "pid": proc.pid}
            else:
                out = host.cmd(cmd)
                res = {"status": "ok", "output": out}

            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(res).encode("utf-8"))
        except Exception as e:
            self.send_response(500)
            self.end_headers()
            self.wfile.write(json.dumps({"error": str(e)}).encode("utf-8"))


def start_host_exec_server(net, port=8001):
    HostExecServer.net_ref = net
    server = HTTPServer(("127.0.0.1", port), HostExecServer)
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    logger.info(f"Host Execution IPC Server active on 127.0.0.1:{port}")
    return server


def cleanup_stale_interfaces() -> None:
    """
    Removes lingering veth interfaces and OVS bridges from previous interrupted runs.
    Prevents 'RTNETLINK answers: File exists' errors during topology instantiation.
    """
    logger.info("Pre-cleaning stale network interfaces and bridges...")
    try:
        out = subprocess.check_output(["ip", "-o", "link", "show"]).decode()
        for line in out.splitlines():
            parts = line.split(":")
            if len(parts) >= 2:
                intf = parts[1].strip().split("@")[0]
                if re.match(r"^(s[0-9]+|h[0-9]+)-eth[0-9]+", intf):
                    subprocess.run(["ip", "link", "delete", intf], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        for i in range(1, 7):
            subprocess.run(["ovs-vsctl", "--if-exists", "del-br", f"s{i}"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception as e:
        logger.debug(f"Interface cleanup note: {e}")


def run_network(
    cli_mode: bool = False,
    enable_qos: bool = True,
    controller_ip: str = "127.0.0.1",
    controller_port: int = 6653,
    config_dir: str = "../config",
):
    """Start Mininet network and handle lifecycle."""
    # Ensure any lingering veth interfaces from prior runs are purged first
    cleanup_stale_interfaces()

    topo_config = os.path.join(config_dir, "topology.yaml")
    qos_config = os.path.join(config_dir, "qos.yaml")

    info("*** Initializing MultiPath SDN Topology ***\n")
    topo = MultiPathSDNTopo(config_path=topo_config)

    # Use OVSSwitch with OpenFlow 1.3 protocol
    switch_cls = lambda name, **params: OVSSwitch(
        name, protocols="OpenFlow13", **params
    )

    controller = lambda name: RemoteController(
        name, ip=controller_ip, port=controller_port
    )

    net = Mininet(
        topo=topo,
        switch=switch_cls,
        controller=controller,
        link=TCLink,
        autoSetMacs=True,
        autoStaticArp=True,
    )

    # Clean shutdown handler
    def cleanup_handler(signum, frame):
        info("\n*** Interrupted: Shutting down Mininet network gracefully... ***\n")
        try:
            net.stop()
        except Exception:
            pass
        cleanup_stale_interfaces()
        sys.exit(0)

    signal.signal(signal.SIGINT, cleanup_handler)
    signal.signal(signal.SIGTERM, cleanup_handler)

    info("*** Starting Network ***\n")
    net.start()

    # Start IPC host execution server on port 8001
    start_host_exec_server(net, port=8001)

    # Pre-populate static ARP entries to prevent broadcast storms in multi-path loops
    try:
        net.staticArp()
    except Exception:
        pass

    # Ensure iperf3 servers are active on Server B (h2)
    h2 = net.get("h2")
    for port in [5001, 5002, 5003]:
        h2.cmd(f"iperf3 -s -p {port} -D")

    # Configure QoS priority queues if requested
    if enable_qos:
        configure_ovs_queues(net, topo_config, qos_config)

    # Output host info
    h1 = net.get("h1")
    h2 = net.get("h2")
    info(f"*** Host Server A (h1): IP={h1.IP()}, MAC={h1.MAC()} ***\n")
    info(f"*** Host Server B (h2): IP={h2.IP()}, MAC={h2.MAC()} ***\n")

    # Give switches a moment to finish OpenFlow handshake
    time.sleep(1.0)

    # Initial reachability test
    info("*** Testing initial reachability (ping h1 -> h2)... ***\n")
    loss = net.ping([h1, h2], timeout="3")
    if loss > 0:
        # Second ping confirms warm OpenFlow flow cache
        loss = net.ping([h1, h2], timeout="3")
    info(f"*** Verified Reachability Ping Loss: {loss}% ***\n")

    # Control loop / CLI mode
    if cli_mode:
        info("*** Starting Mininet CLI (type 'exit' to quit) ***\n")
        CLI(net)
        info("*** Stopping Network ***\n")
        try:
            net.stop()
        except Exception:
            pass
        cleanup_stale_interfaces()
    else:
        info("*** Network is running headless. Press Ctrl+C or kill process to terminate. ***\n")
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            pass
        finally:
            info("*** Stopping Network ***\n")
            try:
                net.stop()
            except Exception:
                pass
            cleanup_stale_interfaces()


def main():
    parser = argparse.ArgumentParser(description="Start Mininet Priority SDN Network")
    parser.add_argument("--cli", action="store_true", help="Launch interactive Mininet CLI")
    parser.add_argument("--no-qos", action="store_true", help="Disable OVS QoS queues")
    parser.add_argument("--controller-ip", default="127.0.0.1", help="SDN Controller IP")
    parser.add_argument("--controller-port", type=int, default=6653, help="SDN Controller Port")
    parser.add_argument("--config-dir", default="../config", help="Directory containing YAML configs")
    parser.add_argument("--log-level", default="info", help="Mininet log level (info, debug, warning)")
    args = parser.parse_args()

    setLogLevel(args.log_level)
    run_network(
        cli_mode=args.cli,
        enable_qos=not args.no_qos,
        controller_ip=args.controller_ip,
        controller_port=args.controller_port,
        config_dir=args.config_dir,
    )


if __name__ == "__main__":
    main()

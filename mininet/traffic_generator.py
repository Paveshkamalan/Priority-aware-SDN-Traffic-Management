#!/usr/bin/env python3
"""
Traffic Generator Module
Manages multi-class iperf3 and ping traffic between Mininet hosts (Server A & Server B).
Supports:
  - Class 3 (High): UDP (VoIP/Emergency) -> port 5001, TOS 184 (DSCP EF)
  - Class 2 (Medium): TCP (Web/Interactive) -> port 5002, TOS 104 (DSCP AF31)
  - Class 1 (Low): TCP (Bulk/Backup) -> port 5003, TOS 0 (DSCP BE)
"""

import argparse
import json
import logging
import os
import subprocess
import time
from typing import Dict, Any, List, Optional

import yaml

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("TrafficGen")

PID_FILE = "/tmp/sdn_traffic_pids.json"


def load_yaml(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def save_active_pids(pids: List[int]) -> None:
    try:
        with open(PID_FILE, "w", encoding="utf-8") as f:
            json.dump(pids, f)
    except Exception as e:
        logger.error(f"Failed to save PID file: {e}")


def get_active_pids() -> List[int]:
    if not os.path.exists(PID_FILE):
        return []
    try:
        with open(PID_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def stop_traffic() -> None:
    """Stop all active traffic generation processes and iperf3 servers/clients."""
    pids = get_active_pids()
    for pid in pids:
        try:
            os.kill(pid, 9)
        except ProcessLookupError:
            pass
        except Exception as e:
            logger.debug(f"Error killing PID {pid}: {e}")

    # Also kill any lingering iperf3 instances
    subprocess.run("pkill -9 iperf3", shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    if os.path.exists(PID_FILE):
        os.remove(PID_FILE)
    logger.info("All traffic generators and iperf3 processes stopped.")


def get_host_pid(host_name: str) -> Optional[int]:
    """Retrieve host bash/namespace PID from Mininet environment."""
    # Mininet stores host PIDs in /tmp or can be queried via ps
    cmd = f"pgrep -f 'mininet:{host_name}'"
    res = subprocess.run(cmd, shell=True, stdout=subprocess.PIPE, text=True)
    out = res.stdout.strip()
    if out:
        return int(out.split()[0])
    return None


def execute_in_host(host_name: str, cmd: str, background: bool = False):
    """Execute command inside Mininet host namespace using IPC agent or mnexec."""
    import urllib.request
    try:
        req = urllib.request.Request(
            "http://127.0.0.1:8001/exec",
            data=json.dumps({"host": host_name, "cmd": cmd, "background": background}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=3.0) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            if background:
                class DummyProc:
                    def __init__(self, pid):
                        self.pid = pid
                return DummyProc(data.get("pid", 1000))
            else:
                return subprocess.CompletedProcess(args=cmd, returncode=0, stdout=data.get("output", ""))
    except Exception:
        pass

    # Fallback to mnexec
    h_pid = get_host_pid(host_name)
    if h_pid:
        full_cmd = f"mnexec -a {h_pid} {cmd}"
    else:
        # Fallback to direct shell execution if outside Mininet CLI
        full_cmd = cmd

    logger.debug(f"Executing for {host_name}: {full_cmd}")
    if background:
        proc = subprocess.Popen(full_cmd, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return proc
    else:
        return subprocess.run(full_cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)


def start_iperf_servers(target_host: str = "h2", ports: List[int] = [5001, 5002, 5003]) -> List[int]:
    """Start iperf3 servers listening on specified ports in the destination host."""
    pids = []
    for port in ports:
        cmd = f"iperf3 -s -p {port} -D"
        execute_in_host(target_host, cmd, background=False)
        time.sleep(0.1)
    logger.info(f"iperf3 servers started on {target_host} for ports {ports}")
    return pids


def start_stream(
    src_host: str,
    dst_ip: str,
    traffic_class: str,
    rate_mbps: float,
    duration: int,
    protocol: str = "tcp",
    port: int = 5001,
    tos: int = 0,
    output_json: Optional[str] = None,
) -> Optional[subprocess.Popen]:
    """
    Launch a single traffic stream from source host to destination IP.
    """
    proto_flag = "-u" if protocol.lower() == "udp" else ""
    bitrate_flag = f"-b {rate_mbps}M"
    tos_flag = f"-S {tos}"
    json_flag = f"-J --logfile {output_json}" if output_json else ""

    cmd = (
        f"iperf3 -c {dst_ip} -p {port} {proto_flag} {bitrate_flag} {tos_flag} "
        f"-t {duration} {json_flag} &"
    )

    logger.info(
        f"Starting {traffic_class.upper()} traffic ({protocol.upper()} {rate_mbps}Mbps, port {port}, TOS {tos}) for {duration}s"
    )
    proc = execute_in_host(src_host, cmd, background=True)
    return proc


def measure_ping_rtt(src_host: str, dst_ip: str, count: int = 5) -> Dict[str, float]:
    """Measure ping latency and packet loss between hosts."""
    cmd = f"ping -c {count} -W 2 {dst_ip}"
    res = execute_in_host(src_host, cmd, background=False)
    output = res.stdout if hasattr(res, "stdout") else ""
    
    rtt_metrics = {"loss_pct": 0.0, "avg_rtt_ms": 0.0, "min_rtt_ms": 0.0, "max_rtt_ms": 0.0}
    try:
        lines = output.splitlines()
        for line in lines:
            if "packets transmitted" in line:
                # e.g., 5 packets transmitted, 5 received, 0% packet loss
                parts = line.split(",")
                for p in parts:
                    if "packet loss" in p:
                        loss_str = p.strip().split("%")[0].strip().split()[-1]
                        rtt_metrics["loss_pct"] = float(loss_str)
            elif "rtt min/avg/max" in line or "round-trip min/avg/max" in line:
                # e.g., rtt min/avg/max/mdev = 8.123/9.456/10.789/0.512 ms
                vals = line.split("=")[1].strip().split()[0].split("/")
                rtt_metrics["min_rtt_ms"] = float(vals[0])
                rtt_metrics["avg_rtt_ms"] = float(vals[1])
                rtt_metrics["max_rtt_ms"] = float(vals[2])
    except Exception as e:
        logger.error(f"Error parsing ping output: {e}")

    return rtt_metrics


def run_experiment_traffic(
    config_path: str = "../config/experiment.yaml",
    profile_name: str = "high_medium_low",
    duration: int = 60,
    results_dir: str = "../results",
) -> None:
    """Run full three-class traffic generation according to experiment profile."""
    os.makedirs(results_dir, exist_ok=True)
    cfg = load_yaml(config_path)
    profiles = cfg.get("traffic_profiles", {})

    # Start iperf servers on Server B (h2)
    start_iperf_servers(target_host="h2", ports=[5001, 5002, 5003])
    time.sleep(1)

    dst_ip = "10.0.0.2"
    procs = []

    # Launch High Priority (Voice/UDP)
    hp = profiles.get("high", {})
    p1 = start_stream(
        src_host="h1",
        dst_ip=dst_ip,
        traffic_class="high",
        rate_mbps=hp.get("target_rate_mbps", 5.0),
        duration=duration,
        protocol=hp.get("protocol", "udp"),
        port=hp.get("dst_port", 5001),
        tos=hp.get("tos", 184),
        output_json=os.path.join(results_dir, "iperf_high.json"),
    )
    if p1 and p1.pid:
        procs.append(p1.pid)

    # Launch Medium Priority (Web/TCP)
    mp = profiles.get("medium", {})
    p2 = start_stream(
        src_host="h1",
        dst_ip=dst_ip,
        traffic_class="medium",
        rate_mbps=mp.get("target_rate_mbps", 20.0),
        duration=duration,
        protocol=mp.get("protocol", "tcp"),
        port=mp.get("dst_port", 5002),
        tos=mp.get("tos", 104),
        output_json=os.path.join(results_dir, "iperf_medium.json"),
    )
    if p2 and p2.pid:
        procs.append(p2.pid)

    # Launch Low Priority (Backup/TCP)
    lp = profiles.get("low", {})
    p3 = start_stream(
        src_host="h1",
        dst_ip=dst_ip,
        traffic_class="low",
        rate_mbps=lp.get("target_rate_mbps", 40.0),
        duration=duration,
        protocol=lp.get("protocol", "tcp"),
        port=lp.get("dst_port", 5003),
        tos=lp.get("tos", 0),
        output_json=os.path.join(results_dir, "iperf_low.json"),
    )
    if p3 and p3.pid:
        procs.append(p3.pid)

    save_active_pids(procs)
    logger.info(f"Traffic streams running for {duration} seconds...")


def main():
    parser = argparse.ArgumentParser(description="Multi-Class Traffic Generator for SDN Simulation")
    parser.add_argument("action", choices=["start", "stop", "run-profile", "ping"], help="Traffic generator action")
    parser.add_argument("--class", dest="traffic_class", choices=["high", "medium", "low"], default="low")
    parser.add_argument("--rate", type=float, default=20.0, help="Traffic rate in Mbps")
    parser.add_argument("--duration", type=int, default=30, help="Duration in seconds")
    parser.add_argument("--protocol", choices=["tcp", "udp"], default="tcp")
    parser.add_argument("--dst", default="10.0.0.2", help="Destination IP")
    parser.add_argument("--src", default="h1", help="Source host name")
    parser.add_argument("--config", default="../config/experiment.yaml", help="Path to experiment config")
    args = parser.parse_args()

    if args.action == "stop":
        stop_traffic()
    elif args.action == "start":
        start_iperf_servers(target_host="h2")
        port_map = {"high": 5001, "medium": 5002, "low": 5003}
        tos_map = {"high": 184, "medium": 104, "low": 0}
        start_stream(
            src_host=args.src,
            dst_ip=args.dst,
            traffic_class=args.traffic_class,
            rate_mbps=args.rate,
            duration=args.duration,
            protocol=args.protocol,
            port=port_map[args.traffic_class],
            tos=tos_map[args.traffic_class],
        )
    elif args.action == "run-profile":
        run_experiment_traffic(config_path=args.config, duration=args.duration)
    elif args.action == "ping":
        res = measure_ping_rtt(src_host=args.src, dst_ip=args.dst)
        print(json.dumps(res, indent=2))


if __name__ == "__main__":
    main()

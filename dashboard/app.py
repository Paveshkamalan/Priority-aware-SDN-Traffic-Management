"""
Dashboard Backend Server (FastAPI)
Serves Web UI at http://localhost:8000 and provides REST APIs & WebSockets
for network telemetry, experiment execution, traffic generation, and data export.
"""

import asyncio
import csv
import json
import logging
import os
import subprocess
import sys
import time
from typing import Dict, Any, List, Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.requests import Request
import httpx
import yaml

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("DashboardBackend")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(BASE_DIR, ".."))
CONTROLLER_URL = "http://127.0.0.1:8080"

app = FastAPI(title="SDN Priority Traffic Management Dashboard")

# Static files & Templates
app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "static")), name="static")
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))

# Global Experiment State
current_experiment = {
    "running": False,
    "name": "idle",
    "start_time": 0.0,
    "duration": 0,
    "mode": "baseline",
    "metrics_log": [],
}


def load_yaml(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


async def query_controller(endpoint: str, method: str = "GET", json_body: Optional[dict] = None) -> Dict[str, Any]:
    """Helper to communicate with Ryu Controller REST API."""
    async with httpx.AsyncClient(timeout=2.0) as client:
        try:
            if method == "GET":
                resp = await client.get(f"{CONTROLLER_URL}{endpoint}")
            else:
                resp = await client.post(f"{CONTROLLER_URL}{endpoint}", json=json_body or {})
            if resp.status_code == 200:
                return resp.json()
            return {"error": f"Controller returned status {resp.status_code}"}
        except Exception as e:
            return {"error": f"Could not connect to Ryu Controller: {str(e)}"}


# ==============================================================================
# Web UI Entrypoint
# ==============================================================================

@app.get("/", response_class=HTMLResponse)
async def get_index(request: Request):
    """Render main dashboard view."""
    return templates.TemplateResponse(request=request, name="index.html")


# ==============================================================================
# REST APIs for Dashboard & Experiments
# ==============================================================================

@app.get("/api/topology")
async def get_topology():
    """Retrieve network nodes, edges, capacities, and real-time utilization."""
    data = await query_controller("/api/topology")
    if "error" in data:
        # Fallback to topology.yaml if controller is not yet running
        cfg_path = os.path.join(PROJECT_ROOT, "config", "topology.yaml")
        if os.path.exists(cfg_path):
            topo_cfg = load_yaml(cfg_path)
            nodes = [
                {"id": s["id"], "label": f"Switch {s['id'].upper()}", "type": "switch"}
                for s in topo_cfg.get("switches", [])
            ]
            for h in topo_cfg.get("hosts", []):
                nodes.append({"id": h["id"], "label": f"{h['name']}\n({h['ip']})", "type": "host"})
            edges = [
                {
                    "from": l["node1"],
                    "to": l["node2"],
                    "bw": l.get("bw", 100),
                    "delay": l.get("delay", "1ms"),
                    "utilization": 0.0,
                }
                for l in topo_cfg.get("links", [])
            ]
            return {"nodes": nodes, "edges": edges, "source": "config_fallback"}
    return data


@app.get("/api/metrics")
async def get_metrics():
    """Retrieve real-time link utilization, queue throughput, and latency."""
    data = await query_controller("/api/metrics")
    if "error" in data:
        # Provide simulated/baseline structure when controller is offline
        return {
            "links": [],
            "queues": [],
            "reroute_events_count": 0,
            "adaptive_enabled": True,
            "qos_enabled": True,
            "timestamp": time.time(),
        }
    return data


@app.get("/api/flows")
async def get_flows():
    """Retrieve active registered flows and their current path assignments."""
    data = await query_controller("/api/flows")
    if "error" in data:
        return [
            {"flow_id": "flow_high_voip", "class": "high", "priority": 3, "current_path": [1, 2, 4, 6], "rerouted": False},
            {"flow_id": "flow_medium_web", "class": "medium", "priority": 2, "current_path": [1, 2, 4, 6], "rerouted": False},
            {"flow_id": "flow_low_bulk", "class": "low", "priority": 1, "current_path": [1, 2, 4, 6], "rerouted": False},
        ]
    return data


@app.get("/api/reroutes")
async def get_reroutes():
    """Retrieve full audit log of rerouting events."""
    return await query_controller("/api/reroutes")


@app.post("/api/traffic/start")
async def start_traffic(payload: dict):
    """
    Launch traffic generation stream.
    Expected payload: { traffic_class: 'high'|'medium'|'low', rate_mbps: 20.0, duration: 30, protocol: 'tcp'|'udp' }
    """
    t_class = payload.get("traffic_class", "low")
    rate = float(payload.get("rate_mbps", 20.0))
    duration = int(payload.get("duration", 30))
    protocol = payload.get("protocol", "tcp")

    script_path = os.path.join(PROJECT_ROOT, "mininet", "traffic_generator.py")
    cmd = (
        f"python3 {script_path} start --class {t_class} --rate {rate} "
        f"--duration {duration} --protocol {protocol}"
    )

    proc = subprocess.Popen(cmd, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return {"status": "started", "pid": proc.pid, "class": t_class, "rate_mbps": rate}


@app.post("/api/traffic/stop")
async def stop_traffic():
    """Halt all active traffic generation streams."""
    script_path = os.path.join(PROJECT_ROOT, "mininet", "traffic_generator.py")
    subprocess.run(f"python3 {script_path} stop", shell=True)
    return {"status": "stopped"}


@app.post("/api/config")
async def update_config(payload: dict):
    """Update thresholds or controller parameters."""
    return await query_controller("/api/config", method="POST", json_body=payload)


@app.post("/api/reroute/toggle")
async def toggle_rerouting(payload: dict):
    """Toggle adaptive rerouting enable/disable."""
    return await query_controller("/api/reroute/toggle", method="POST", json_body=payload)


@app.post("/api/qos/toggle")
async def toggle_qos(payload: dict):
    """Toggle QoS priority queues enable/disable."""
    return await query_controller("/api/qos/toggle", method="POST", json_body=payload)


@app.post("/api/reset")
async def reset_network():
    """Reset network flows and clear congestion states."""
    # Stop any running traffic
    script_path = os.path.join(PROJECT_ROOT, "mininet", "traffic_generator.py")
    subprocess.run(f"python3 {script_path} stop", shell=True)
    return await query_controller("/api/reset", method="POST", json_body={})


@app.post("/api/experiment/{exp_type}")
async def run_experiment(exp_type: str):
    """
    Trigger automated experiment:
      - 'baseline': Exp 1 (No Rerouting, No QoS)
      - 'adaptive': Exp 4 (Adaptive Rerouting + QoS)
    """
    if exp_type == "baseline":
        # Disable adaptive rerouting and QoS
        await query_controller("/api/reroute/toggle", method="POST", json_body={"enabled": False})
        await query_controller("/api/qos/toggle", method="POST", json_body={"enabled": False})
        mode = "baseline"
    else:
        # Enable both
        await query_controller("/api/reroute/toggle", method="POST", json_body={"enabled": True})
        await query_controller("/api/qos/toggle", method="POST", json_body={"enabled": True})
        mode = "adaptive_qos"

    # Launch experiment profile traffic in background
    script_path = os.path.join(PROJECT_ROOT, "mininet", "traffic_generator.py")
    cmd = f"python3 {script_path} run-profile --duration 45 &"
    subprocess.Popen(cmd, shell=True)

    current_experiment["running"] = True
    current_experiment["name"] = f"experiment_{exp_type}"
    current_experiment["start_time"] = time.time()
    current_experiment["duration"] = 45
    current_experiment["mode"] = mode
    current_experiment["metrics_log"].clear()

    return {"status": "started", "experiment": exp_type, "mode": mode, "duration": 45}


@app.get("/api/results/export")
async def export_results(format: str = "json"):
    """Export recorded experiment telemetry as CSV or JSON."""
    results_dir = os.path.join(PROJECT_ROOT, "results")
    os.makedirs(results_dir, exist_ok=True)

    # Fetch latest controller metrics & flow state
    metrics = await query_controller("/api/metrics")
    flows = await query_controller("/api/flows")
    reroutes = await query_controller("/api/reroutes")

    export_data = {
        "export_time": time.strftime("%Y-%m-%d %H:%M:%S"),
        "experiment_mode": current_experiment["mode"],
        "metrics": metrics,
        "flows": flows,
        "reroute_events": reroutes,
        "history": current_experiment["metrics_log"],
    }

    if format.lower() == "csv":
        csv_file = os.path.join(results_dir, f"experiment_results_{int(time.time())}.csv")
        with open(csv_file, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["Timestamp", "Link", "Utilization_Pct", "Flow_ID", "Flow_Class", "Current_Path", "Rerouted"])
            # Flatten metrics into CSV rows
            for m in current_experiment["metrics_log"]:
                t = m.get("timestamp", time.time())
                for link in m.get("links", []):
                    writer.writerow([t, link.get("link"), link.get("utilization_pct"), "", "", "", ""])
        return JSONResponse({"status": "exported", "format": "csv", "file": csv_file})

    json_file = os.path.join(results_dir, f"experiment_results_{int(time.time())}.json")
    with open(json_file, "w", encoding="utf-8") as f:
        json.dump(export_data, f, indent=2)

    return JSONResponse({"status": "exported", "format": "json", "file": json_file, "data": export_data})


# ==============================================================================
# WebSocket for Live Telemetry Streaming (1 Hz)
# ==============================================================================

@app.websocket("/ws/metrics")
async def websocket_metrics(websocket: WebSocket):
    """Streams live metrics, link utilization, and flow states at 1-second intervals."""
    await websocket.accept()
    try:
        while True:
            metrics = await query_controller("/api/metrics")
            flows = await query_controller("/api/flows")
            reroutes = await query_controller("/api/reroutes")

            payload = {
                "timestamp": time.time(),
                "metrics": metrics,
                "flows": flows,
                "reroutes": reroutes,
                "experiment": {
                    "running": current_experiment["running"],
                    "mode": current_experiment["mode"],
                    "elapsed": round(time.time() - current_experiment["start_time"], 1)
                    if current_experiment["running"]
                    else 0,
                },
            }

            # If an experiment is running, record snapshot
            if current_experiment["running"]:
                current_experiment["metrics_log"].append(payload)
                if (time.time() - current_experiment["start_time"]) >= current_experiment["duration"]:
                    current_experiment["running"] = False

            await websocket.send_text(json.dumps(payload))
            await asyncio.sleep(1.0)
    except WebSocketDisconnect:
        logger.debug("WebSocket client disconnected.")
    except Exception as e:
        logger.error(f"WebSocket error: {e}")


def main():
    import uvicorn
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=False)


if __name__ == "__main__":
    main()

"""
Controller REST API Service
Exposes REST endpoints on port 8080 providing live controller state, topology,
link metrics, flow routing status, and configuration toggles.
"""

import json
import logging
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from typing import Any, Dict

logger = logging.getLogger("ControllerREST")


class ControllerHTTPHandler(BaseHTTPRequestHandler):
    """HTTP Request Handler exposing Controller APIs to Dashboard backend."""

    controller_instance: Any = None

    def _set_headers(self, status: int = 200, content_type: str = "application/json"):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_OPTIONS(self):
        self._set_headers(200)

    def log_message(self, format, *args):
        # Suppress routine HTTP logging
        return

    def do_GET(self):
        controller = self.controller_instance
        if not controller:
            self._set_headers(500)
            self.wfile.write(json.dumps({"error": "Controller not initialized"}).encode())
            return

        path = self.path.split("?")[0]

        if path == "/api/topology":
            data = controller.topo_mgr.to_dict()
            self._set_headers(200)
            self.wfile.write(json.dumps(data).encode())

        elif path == "/api/metrics":
            metrics = controller.monitor.get_all_metrics()
            metrics["reroute_events_count"] = len(controller.rerouter.reroute_events)
            metrics["adaptive_enabled"] = controller.rerouter.enabled
            metrics["qos_enabled"] = controller.qos_mgr.enabled
            self._set_headers(200)
            self.wfile.write(json.dumps(metrics).encode())

        elif path == "/api/flows":
            flows = list(controller.rerouter.active_flows.values())
            self._set_headers(200)
            self.wfile.write(json.dumps(flows).encode())

        elif path == "/api/reroutes":
            events = controller.rerouter.reroute_events
            self._set_headers(200)
            self.wfile.write(json.dumps(events).encode())

        elif path == "/api/status":
            status = {
                "switches_connected": len(controller.datapaths),
                "adaptive_routing": controller.rerouter.enabled,
                "qos_queuing": controller.qos_mgr.enabled,
                "congested_links": [f"s{u}-s{v}" for (u, v) in controller.rerouter.confirmed_congested_links],
            }
            self._set_headers(200)
            self.wfile.write(json.dumps(status).encode())

        else:
            self._set_headers(404)
            self.wfile.write(json.dumps({"error": "Endpoint not found"}).encode())

    def do_POST(self):
        controller = self.controller_instance
        if not controller:
            self._set_headers(500)
            self.wfile.write(json.dumps({"error": "Controller not initialized"}).encode())
            return

        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length).decode("utf-8") if content_length > 0 else "{}"
        try:
            payload = json.loads(body) if body else {}
        except Exception:
            payload = {}

        path = self.path.split("?")[0]

        if path == "/api/reroute/toggle":
            enabled = payload.get("enabled", not controller.rerouter.enabled)
            controller.rerouter.set_enabled(bool(enabled))
            self._set_headers(200)
            self.wfile.write(json.dumps({"adaptive_routing": controller.rerouter.enabled}).encode())

        elif path == "/api/qos/toggle":
            enabled = payload.get("enabled", not controller.qos_mgr.enabled)
            controller.qos_mgr.set_enabled(bool(enabled))
            self._set_headers(200)
            self.wfile.write(json.dumps({"qos_queuing": controller.qos_mgr.enabled}).encode())

        elif path == "/api/config":
            if "congestion_threshold" in payload:
                controller.rerouter.congestion_threshold = float(payload["congestion_threshold"])
            if "warning_threshold" in payload:
                controller.rerouter.warning_threshold = float(payload["warning_threshold"])
            if "recovery_threshold" in payload:
                controller.rerouter.recovery_threshold = float(payload["recovery_threshold"])
            self._set_headers(200)
            self.wfile.write(json.dumps({"status": "Config updated", "payload": payload}).encode())

        elif path == "/api/reset":
            # Reset link state, flows to default path
            controller.rerouter.confirmed_congested_links.clear()
            controller.rerouter.link_congestion_counts.clear()
            controller.rerouter.link_recovery_counts.clear()
            for flow in controller.rerouter.active_flows.values():
                flow["current_path"] = list(flow.get("original_path", [1, 2, 4, 6]))
                flow["rerouted"] = False
            self._set_headers(200)
            self.wfile.write(json.dumps({"status": "Controller reset complete"}).encode())

        else:
            self._set_headers(404)
            self.wfile.write(json.dumps({"error": "Endpoint not found"}).encode())


def start_rest_server(controller_app: Any, host: str = "0.0.0.0", port: int = 8080) -> HTTPServer:
    """Spawns background HTTP server for controller REST API."""
    ControllerHTTPHandler.controller_instance = controller_app
    server = HTTPServer((host, port), ControllerHTTPHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    logger.info(f"Controller REST API server started on http://{host}:{port}")
    return server

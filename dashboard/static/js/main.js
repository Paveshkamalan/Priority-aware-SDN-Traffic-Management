/**
 * Main Dashboard Application Client
 * WebSocket & Polling lifecycle, UI table rendering, and REST event handlers.
 */

let ws = null;
let pollTimer = null;

function connectWebSocket() {
  const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
  const wsUrl = `${protocol}//${window.location.host}/ws/metrics`;

  try {
    ws = new WebSocket(wsUrl);

    ws.onopen = () => {
      setControllerStatus(true);
      if (pollTimer) {
        clearInterval(pollTimer);
        pollTimer = null;
      }
    };

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        handleLiveTelemetry(data);
      } catch (err) {
        console.error("Error parsing telemetry message:", err);
      }
    };

    ws.onclose = () => {
      setControllerStatus(false);
      startPollingFallback();
      setTimeout(connectWebSocket, 3000); // Reconnect after 3s
    };

    ws.onerror = (err) => {
      setControllerStatus(false);
      startPollingFallback();
    };
  } catch (e) {
    startPollingFallback();
  }
}

function startPollingFallback() {
  if (pollTimer) return;
  pollTimer = setInterval(async () => {
    try {
      const resp = await fetch("/api/metrics");
      if (resp.ok) {
        const metrics = await resp.json();
        const flowsResp = await fetch("/api/flows");
        const flows = flowsResp.ok ? await flowsResp.json() : [];
        const reroutesResp = await fetch("/api/reroutes");
        const reroutes = reroutesResp.ok ? await reroutesResp.json() : [];

        setControllerStatus(true);
        handleLiveTelemetry({ metrics, flows, reroutes });
      } else {
        setControllerStatus(false);
      }
    } catch (e) {
      setControllerStatus(false);
    }
  }, 1000);
}

function setControllerStatus(online) {
  const dot = document.getElementById("controller-status-dot");
  const txt = document.getElementById("controller-status-text");
  if (dot && txt) {
    if (online) {
      dot.className = "status-dot online";
      txt.textContent = "Controller Connected";
    } else {
      dot.className = "status-dot offline";
      txt.textContent = "Controller Offline / Connecting...";
    }
  }
}

function handleLiveTelemetry(data) {
  // 1. Update Topology Canvas
  if (typeof updateTopologyEdges === "function") {
    updateTopologyEdges(data.metrics, data.flows);
  }

  // 2. Update Telemetry Charts
  if (typeof updateTelemetryCharts === "function") {
    updateTelemetryCharts(data);
  }

  // 3. Update Flows Table
  renderFlowsTable(data.flows || []);

  // 4. Update Events Table
  renderEventsTable(data.reroutes || []);

  // 5. Update Experiment Badge
  const expBadge = document.getElementById("experiment-badge");
  if (expBadge && data.experiment) {
    if (data.experiment.running) {
      expBadge.style.display = "inline-block";
      expBadge.textContent = `Experiment Running: ${data.experiment.elapsed}s (${data.experiment.mode})`;
    } else {
      expBadge.style.display = "none";
    }
  }

  // 6. Update Mode Badge
  const modeBadge = document.getElementById("mode-badge");
  const adaptiveOn = data.metrics?.adaptive_enabled ?? true;
  const qosOn = data.metrics?.qos_enabled ?? true;

  if (modeBadge) {
    if (adaptiveOn && qosOn) {
      modeBadge.className = "status-badge";
      modeBadge.textContent = "Proposed System: Adaptive + QoS Active";
    } else if (adaptiveOn && !qosOn) {
      modeBadge.className = "status-badge warning";
      modeBadge.textContent = "Adaptive Rerouting Only";
    } else if (!adaptiveOn && qosOn) {
      modeBadge.className = "status-badge warning";
      modeBadge.textContent = "QoS Queuing Only";
    } else {
      modeBadge.className = "status-badge warning";
      modeBadge.textContent = "Baseline Mode (Static Shortest Path)";
    }
  }
}

function renderFlowsTable(flows) {
  const tbody = document.getElementById("flows-table-body");
  if (!tbody) return;

  if (flows.length === 0) return;

  tbody.innerHTML = "";
  flows.forEach((f) => {
    const tr = document.createElement("tr");

    const classBadge = `<span class="badge ${f.class}">${f.class.toUpperCase()}</span>`;
    const priorityText = `${f.priority} (Queue ${f.priority === 3 ? 2 : f.priority === 2 ? 1 : 0})`;
    const protoText = `${(f.proto || "tcp").toUpperCase()} ${f.dst_port || ""}`;
    const pathText = JSON.stringify(f.current_path || [1, 2, 4, 6]);
    const statusBadge = f.rerouted
      ? `<span class="badge rerouted"><i class="fa-solid fa-route"></i> Rerouted</span>`
      : `<span class="badge normal">Primary Path</span>`;

    tr.innerHTML = `
      <td>${classBadge}</td>
      <td>${priorityText}</td>
      <td>${protoText}</td>
      <td><strong>${pathText}</strong></td>
      <td>${statusBadge}</td>
    `;
    tbody.appendChild(tr);
  });
}

function renderEventsTable(events) {
  const tbody = document.getElementById("events-table-body");
  const countBadge = document.getElementById("event-count-badge");
  if (!tbody) return;

  if (countBadge) {
    countBadge.textContent = `${events.length} Events`;
  }

  if (events.length === 0) {
    tbody.innerHTML = `<tr><td colspan="7" class="text-center">No reroute events recorded yet. Primary path uncongested.</td></tr>`;
    return;
  }

  tbody.innerHTML = "";
  // Show most recent events first
  const reversed = [...events].reverse();
  reversed.forEach((ev) => {
    const tr = document.createElement("tr");
    const timeStr = new Date(ev.timestamp * 1000).toLocaleTimeString();
    const classBadge = `<span class="badge ${ev.class || "low"}">${(ev.class || "low").toUpperCase()}</span>`;

    tr.innerHTML = `
      <td>${timeStr}</td>
      <td><code>${ev.flow_id}</code></td>
      <td>${ev.priority}</td>
      <td>${classBadge}</td>
      <td>${JSON.stringify(ev.old_path)}</td>
      <td><strong>${JSON.stringify(ev.new_path)}</strong></td>
      <td><span style="color: #38bdf8;">${ev.reason}</span></td>
    `;
    tbody.appendChild(tr);
  });
}

// ==============================================================================
// Event Listeners & Button Bindings
// ==============================================================================

function setupEventListeners() {
  // Experiment 1: Baseline
  document.getElementById("btn-exp-baseline")?.addEventListener("click", async () => {
    if (confirm("Start Baseline Experiment (Static Shortest Path, QoS & Adaptive Off)?")) {
      const res = await fetch("/api/experiment/baseline", { method: "POST" });
      const data = await res.json();
      alert(`Baseline Experiment Started (${data.duration}s duration). Watch bottleneck links congest!`);
    }
  });

  // Experiment 4: Proposed Adaptive + QoS
  document.getElementById("btn-exp-adaptive")?.addEventListener("click", async () => {
    if (confirm("Start Proposed System Experiment (Adaptive Rerouting + QoS Priority Queues)?")) {
      const res = await fetch("/api/experiment/adaptive", { method: "POST" });
      const data = await res.json();
      alert(`Adaptive Experiment Started (${data.duration}s duration). Low priority will reroute automatically.`);
    }
  });

  // Reset Network
  document.getElementById("btn-reset")?.addEventListener("click", async () => {
    const res = await fetch("/api/reset", { method: "POST" });
    if (res.ok) alert("Network flows reset and traffic stopped.");
  });

  // Export JSON
  document.getElementById("btn-export-json")?.addEventListener("click", async () => {
    const res = await fetch("/api/results/export?format=json");
    const data = await res.json();
    alert(`Results exported successfully to: ${data.file}`);
  });

  // Export CSV
  document.getElementById("btn-export-csv")?.addEventListener("click", async () => {
    const res = await fetch("/api/results/export?format=csv");
    const data = await res.json();
    alert(`Results exported successfully to CSV: ${data.file}`);
  });

  // Toggles
  document.getElementById("toggle-adaptive")?.addEventListener("change", async (e) => {
    await fetch("/api/reroute/toggle", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ enabled: e.target.checked }),
    });
  });

  document.getElementById("toggle-qos")?.addEventListener("change", async (e) => {
    await fetch("/api/qos/toggle", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ enabled: e.target.checked }),
    });
  });

  // Custom Traffic Injection
  document.getElementById("btn-start-traffic")?.addEventListener("click", async () => {
    const tClass = document.getElementById("traffic-class-select").value;
    const rate = document.getElementById("traffic-rate-input").value;
    const duration = document.getElementById("traffic-duration-input").value;
    const protocol = tClass === "high" ? "udp" : "tcp";

    const res = await fetch("/api/traffic/start", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        traffic_class: tClass,
        rate_mbps: parseFloat(rate),
        duration: parseInt(duration),
        protocol: protocol,
      }),
    });
    if (res.ok) {
      alert(`Traffic flow (${tClass.toUpperCase()} ${rate}Mbps ${protocol.toUpperCase()}) started.`);
    }
  });

  document.getElementById("btn-stop-traffic")?.addEventListener("click", async () => {
    await fetch("/api/traffic/stop", { method: "POST" });
    alert("All active traffic flows stopped.");
  });
}

document.addEventListener("DOMContentLoaded", () => {
  setupEventListeners();
  connectWebSocket();
});

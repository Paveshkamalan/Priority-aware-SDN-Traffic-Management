/**
 * Topology Visualization Module using vis.js
 * Renders switches, hosts, and dynamically colored links reflecting real-time utilization.
 */

let networkInstance = null;
let networkNodes = null;
let networkEdges = null;

function initTopology() {
  const container = document.getElementById("topology-network");
  if (!container) return;

  // Fixed coordinates for clean, readable SDN topology layout
  const initialNodes = [
    { id: "h1", label: "Server A\n(10.0.0.1)", shape: "box", color: { background: "#0284c7", border: "#38bdf8" }, font: { color: "#fff" }, x: -350, y: 0, fixed: true },
    { id: "s1", label: "S1 (Ingress)", shape: "dot", size: 24, color: { background: "#1e293b", border: "#38bdf8" }, font: { color: "#fff" }, x: -220, y: 0, fixed: true },
    { id: "s2", label: "S2 (Core West)", shape: "dot", size: 24, color: { background: "#1e293b", border: "#38bdf8" }, font: { color: "#fff" }, x: -100, y: -100, fixed: true },
    { id: "s3", label: "S3 (Core East)", shape: "dot", size: 24, color: { background: "#1e293b", border: "#38bdf8" }, font: { color: "#fff" }, x: -100, y: 100, fixed: true },
    { id: "s4", label: "S4 (Aggr 1)", shape: "dot", size: 24, color: { background: "#1e293b", border: "#38bdf8" }, font: { color: "#fff" }, x: 60, y: -100, fixed: true },
    { id: "s5", label: "S5 (Aggr 2)", shape: "dot", size: 24, color: { background: "#1e293b", border: "#38bdf8" }, font: { color: "#fff" }, x: 60, y: 100, fixed: true },
    { id: "s6", label: "S6 (Egress)", shape: "dot", size: 24, color: { background: "#1e293b", border: "#38bdf8" }, font: { color: "#fff" }, x: 180, y: 0, fixed: true },
    { id: "h2", label: "Server B\n(10.0.0.2)", shape: "box", color: { background: "#0284c7", border: "#38bdf8" }, font: { color: "#fff" }, x: 310, y: 0, fixed: true },
  ];

  const initialEdges = [
    { id: "h1-s1", from: "h1", to: "s1", label: "100M / 1ms", color: { color: "#22c55e" }, width: 3 },
    { id: "s1-s2", from: "s1", to: "s2", label: "50M / 2ms", color: { color: "#22c55e" }, width: 3 },
    { id: "s1-s3", from: "s1", to: "s3", label: "30M / 5ms", color: { color: "#22c55e" }, width: 3 },
    { id: "s2-s4", from: "s2", to: "s4", label: "40M / 2ms", color: { color: "#22c55e" }, width: 3 },
    { id: "s2-s5", from: "s2", to: "s5", label: "25M / 4ms", color: { color: "#22c55e" }, width: 3 },
    { id: "s3-s5", from: "s3", to: "s5", label: "20M / 3ms", color: { color: "#22c55e" }, width: 3 },
    { id: "s4-s6", from: "s4", to: "s6", label: "40M / 2ms", color: { color: "#22c55e" }, width: 3 },
    { id: "s5-s6", from: "s5", to: "s6", label: "30M / 2ms", color: { color: "#22c55e" }, width: 3 },
    { id: "s6-h2", from: "s6", to: "h2", label: "100M / 1ms", color: { color: "#22c55e" }, width: 3 },
  ];

  networkNodes = new vis.DataSet(initialNodes);
  networkEdges = new vis.DataSet(initialEdges);

  const data = { nodes: networkNodes, edges: networkEdges };
  const options = {
    physics: false,
    interaction: { hover: true, dragNodes: true, zoomView: true },
    edges: {
      font: { color: "#94a3b8", size: 10, strokeWidth: 0 },
      smooth: { type: "continuous" },
    },
  };

  networkInstance = new vis.Network(container, data, options);
}

function updateTopologyEdges(metricsData, flowsData) {
  if (!networkEdges) return;

  const links = metricsData?.links || [];
  // Build lookup: "u-v" -> utilization
  const utilMap = {};
  links.forEach((l) => {
    const key1 = `s${l.u}-s${l.v}`;
    const key2 = `s${l.v}-s${l.u}`;
    utilMap[key1] = l.utilization;
    utilMap[key2] = l.utilization;
  });

  networkEdges.forEach((edge) => {
    const linkKey = `${edge.from}-${edge.to}`;
    const revKey = `${edge.to}-${edge.from}`;
    const util = utilMap[linkKey] ?? utilMap[revKey] ?? 0.0;

    let edgeColor = "#22c55e"; // Green (< 70%)
    let edgeWidth = 3;

    if (util >= 0.85) {
      edgeColor = "#ef4444"; // Red (> 85% Congested)
      edgeWidth = 6;
    } else if (util >= 0.70) {
      edgeColor = "#eab308"; // Yellow (70-85% Warning)
      edgeWidth = 4;
    }

    // Check if link belongs to a rerouted flow
    const isReroutedLink = (flowsData || []).some((f) => {
      if (!f.rerouted || !f.current_path) return false;
      const p = f.current_path;
      for (let i = 0; i < p.length - 1; i++) {
        if (
          (edge.from === `s${p[i]}` && edge.to === `s${p[i + 1]}`) ||
          (edge.to === `s${p[i]}` && edge.from === `s${p[i + 1]}`)
        ) {
          return true;
        }
      }
      return false;
    });

    const labelParts = edge.label ? edge.label.split("(")[0].trim() : "";
    const newLabel = `${labelParts} (${Math.round(util * 100)}%)`;

    networkEdges.update({
      id: edge.id,
      color: { color: edgeColor, highlight: edgeColor },
      width: edgeWidth,
      label: newLabel,
      dashes: isReroutedLink,
    });
  });
}

document.addEventListener("DOMContentLoaded", initTopology);

#!/usr/bin/env python3
"""Generate Review 2 PowerPoint for the Priority-Aware Adaptive SDN project."""

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
from pptx.oxml.ns import nsmap
from pptx.oxml import parse_xml
from pptx.util import Inches, Pt, Emu
from lxml import etree
from copy import deepcopy
import os

NAVY = RGBColor(0x0B, 0x1F, 0x3A)
TEAL = RGBColor(0x0E, 0x7C, 0x7B)
ACCENT = RGBColor(0xF4, 0xA2, 0x61)
WHITE = RGBColor(0xFF, 0xFF, 0xFF)
LIGHT = RGBColor(0xF4, 0xF7, 0xFB)
DARK = RGBColor(0x1A, 0x1A, 0x2E)
MUTED = RGBColor(0x4A, 0x55, 0x68)
RED = RGBColor(0xC0, 0x39, 0x2B)
GREEN = RGBColor(0x1E, 0x84, 0x4A)
GOLD = RGBColor(0xD4, 0xA0, 0x17)

W, H = Inches(13.333), Inches(7.5)


def set_run(run, text, size=18, bold=False, color=DARK, font="Calibri"):
    run.text = text
    run.font.size = Pt(size)
    run.font.bold = bold
    run.font.color.rgb = color
    run.font.name = font
    run.font.italic = False


def add_rect(slide, l, t, w, h, fill):
    sh = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, l, t, w, h)
    sh.fill.solid()
    sh.fill.fore_color.rgb = fill
    sh.line.fill.background()
    return sh


def add_round(slide, l, t, w, h, fill):
    sh = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, l, t, w, h)
    sh.fill.solid()
    sh.fill.fore_color.rgb = fill
    sh.line.fill.background()
    return sh


def add_text_box(slide, l, t, w, h, text, size=18, bold=False, color=DARK, align=PP_ALIGN.LEFT):
    tb = slide.shapes.add_textbox(l, t, w, h)
    tf = tb.text_frame
    tf.word_wrap = True
    p = tf.paragraphs[0]
    p.alignment = align
    set_run(p.add_run() if p.runs else p.add_run(), "", size, bold, color)
    # first run may already exist empty
    if tf.paragraphs[0].runs:
        set_run(tf.paragraphs[0].runs[0], text, size, bold, color)
    else:
        r = tf.paragraphs[0].add_run()
        set_run(r, text, size, bold, color)
    return tb


def fill_tf(tf, lines, size=16, color=DARK, bold_first=False, spacing=8):
    tf.word_wrap = True
    tf.clear()
    for i, line in enumerate(lines):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.space_after = Pt(spacing)
        p.level = 0
        r = p.add_run()
        set_run(r, line, size, bold=(bold_first and i == 0), color=color)


def bullets(slide, l, t, w, h, items, size=16, color=DARK, spacing=6):
    tb = slide.shapes.add_textbox(l, t, w, h)
    tf = tb.text_frame
    tf.word_wrap = True
    for i, item in enumerate(items):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.space_after = Pt(spacing)
        p.level = 0
        r = p.add_run()
        prefix = "•  " if not str(item).startswith("•") else ""
        set_run(r, prefix + item, size, False, color)
    return tb


def numbered(slide, l, t, w, h, items, size=16, color=DARK):
    tb = slide.shapes.add_textbox(l, t, w, h)
    tf = tb.text_frame
    tf.word_wrap = True
    for i, item in enumerate(items):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.space_after = Pt(8)
        r = p.add_run()
        set_run(r, f"{i + 1}.  {item}", size, False, color)
    return tb


def header_bar(slide, title, subtitle=None):
    add_rect(slide, 0, 0, W, Inches(1.05), NAVY)
    add_rect(slide, 0, Inches(1.05), W, Inches(0.08), TEAL)
    add_text_box(slide, Inches(0.45), Inches(0.18), Inches(12.2), Inches(0.5),
                 title, 26, True, WHITE)
    if subtitle:
        add_text_box(slide, Inches(0.45), Inches(0.62), Inches(12.2), Inches(0.35),
                     subtitle, 13, False, RGBColor(0xB8, 0xD4, 0xD3))
    add_rect(slide, 0, Inches(7.28), W, Inches(0.22), NAVY)
    add_text_box(slide, Inches(0.4), Inches(7.28), Inches(12.5), Inches(0.22),
                 "Review 2  |  Priority-Aware Adaptive Traffic Management in Multi-Path SDN  |  Mininet + Ryu + OpenFlow 1.3",
                 10, False, WHITE)


def card(slide, l, t, w, h, title, body_lines, title_color=TEAL, fill=LIGHT):
    sh = add_round(slide, l, t, w, h, fill)
    add_text_box(slide, l + Inches(0.15), t + Inches(0.1), w - Inches(0.3), Inches(0.35),
                 title, 15, True, title_color)
    bullets(slide, l + Inches(0.12), t + Inches(0.42), w - Inches(0.24), h - Inches(0.5),
            body_lines, 13, DARK, 4)


def table_slide(slide, headers, rows, left, top, width, col_w=None, header_fill=NAVY):
    n_rows = 1 + len(rows)
    n_cols = len(headers)
    table_shape = slide.shapes.add_table(n_rows, n_cols, left, top, width, Inches(0.38 * n_rows))
    table = table_shape.table
    if col_w:
        for i, cw in enumerate(col_w):
            table.columns[i].width = cw
    for j, h in enumerate(headers):
        cell = table.cell(0, j)
        cell.text = ""
        p = cell.text_frame.paragraphs[0]
        p.alignment = PP_ALIGN.CENTER
        r = p.add_run()
        set_run(r, h, 12, True, WHITE)
        cell.fill.solid()
        cell.fill.fore_color.rgb = header_fill
    for i, row in enumerate(rows):
        for j, val in enumerate(row):
            cell = table.cell(i + 1, j)
            cell.text = ""
            p = cell.text_frame.paragraphs[0]
            p.alignment = PP_ALIGN.CENTER if j else PP_ALIGN.LEFT
            r = p.add_run()
            set_run(r, str(val), 12, False, DARK)
            cell.fill.solid()
            cell.fill.fore_color.rgb = WHITE if i % 2 == 0 else RGBColor(0xE8, 0xF0, 0xF4)
    return table


def build():
    prs = Presentation()
    prs.slide_width = W
    prs.slide_height = H
    blank = prs.slide_layouts[6]

    # 1 Title
    s = prs.slides.add_slide(blank)
    add_rect(s, 0, 0, W, H, NAVY)
    add_rect(s, 0, 0, Inches(0.18), H, TEAL)
    add_rect(s, 0, Inches(6.85), W, Inches(0.65), TEAL)
    add_text_box(s, Inches(0.7), Inches(1.15), Inches(12), Inches(0.4),
                 "COMPUTER NETWORKS  •  REVIEW 2", 16, True, ACCENT)
    add_text_box(s, Inches(0.7), Inches(1.65), Inches(12), Inches(1.8),
                 "Priority-Aware Adaptive Traffic Management\nin Multi-Path SDN Networks",
                 36, True, WHITE)
    add_text_box(s, Inches(0.7), Inches(3.7), Inches(12), Inches(1.0),
                 "Dynamic congestion-aware rerouting with hierarchical QoS using\nMininet, Open vSwitch, Ryu (OpenFlow 1.3) and a live FastAPI dashboard",
                 18, False, RGBColor(0xC9, 0xD6, 0xDF))
    add_text_box(s, Inches(0.7), Inches(5.2), Inches(12), Inches(0.9),
                 "Emulation  •  OpenFlow 1.3  •  Dijkstra / Multi-Path  •  HTB QoS  •  Dual-Threshold Hysteresis",
                 14, False, WHITE)
    add_text_box(s, Inches(0.7), Inches(6.95), Inches(12), Inches(0.4),
                 "Academic project presentation  |  Full system design, implementation, experiments and results",
                 14, True, NAVY)

    # 2 Agenda
    s = prs.slides.add_slide(blank)
    header_bar(s, "Agenda — Review 2 Coverage", "End-to-end walkthrough of problem, design, implementation, evaluation and demo")
    items = [
        ("01", "Problem & Motivation", "Why shortest-path SDN collapses under mixed traffic"),
        ("02", "Objectives & Scope", "What this system must achieve and what it does not claim"),
        ("03", "Network & Traffic Model", "6-switch topology, 3 paths, 3 priority classes"),
        ("04", "Architecture & Algorithms", "Controller modules, Dijkstra, hysteresis, QoS, migration"),
        ("05", "Implementation", "Ryu, Mininet, OVS queues, dashboard, REST APIs"),
        ("06", "Experiments & Results", "Baseline vs Adaptive+QoS, metrics, observations"),
        ("07", "Demo, Tests, Conclusion", "How to run, test suite, limitations, future work"),
    ]
    for i, (n, t, d) in enumerate(items):
        y = Inches(1.35) + Inches(i * 0.78)
        add_round(s, Inches(0.5), y, Inches(12.3), Inches(0.7), LIGHT)
        add_round(s, Inches(0.65), y + Inches(0.12), Inches(0.7), Inches(0.46), TEAL)
        add_text_box(s, Inches(0.65), y + Inches(0.16), Inches(0.7), Inches(0.4), n, 16, True, WHITE, PP_ALIGN.CENTER)
        add_text_box(s, Inches(1.55), y + Inches(0.08), Inches(10.8), Inches(0.32), t, 18, True, NAVY)
        add_text_box(s, Inches(1.55), y + Inches(0.36), Inches(10.8), Inches(0.28), d, 13, False, MUTED)

    # 3 Problem
    s = prs.slides.add_slide(blank)
    header_bar(s, "Problem Statement", "Mixed-priority traffic on a multi-path SDN with a hard bottleneck")
    bullets(s, Inches(0.5), Inches(1.35), Inches(12.3), Inches(2.4), [
        "Campus / data-center style networks carry voice/video, interactive web, and bulk backup on the same fabric.",
        "A conventional SDN shortest-path controller (Dijkstra on delay) pins ALL flows onto Path 1: S1 → S2 → S4 → S6.",
        "Path 1 bottleneck is only 40 Mbps (link S2–S4). Offered load in our profile is 5 + 20 + 40 = 65 Mbps.",
        "Without class isolation, high-priority UDP suffers delay, jitter and loss because bulk TCP fills the queue.",
        "Without congestion-aware multi-path control, alternate capacity on Path 2 (25 Mbps) and Path 3 (20 Mbps) stays idle.",
    ], 16)
    card(s, Inches(0.5), Inches(4.0), Inches(4.0), Inches(2.95), "Failure mode",
         ["S2–S4 utilization → ~98%", "High-priority UDP loss ~14.6%", "Latency ~18.7 ms (vs ~8 ms idle)", "Jitter ~3.8 ms", "Aggregate goodput stuck at ~39 Mbps"])
    card(s, Inches(4.7), Inches(4.0), Inches(4.0), Inches(2.95), "Root causes",
         ["Single-path forwarding only", "No priority queues (FIFO/HTB unused)", "No utilization feedback loop", "ARP/table-miss cold start on first packets", "Route flapping if naive reroute"],
         title_color=RED)
    card(s, Inches(8.9), Inches(4.0), Inches(3.9), Inches(2.95), "What we must solve",
         ["Protect High traffic always", "Offload Low first under congestion", "Use spare multi-path capacity", "Avoid flapping (hysteresis)", "Show it live on a dashboard"])

    # 4 Motivation
    s = prs.slides.add_slide(blank)
    header_bar(s, "Motivation — Why SDN + QoS + Multi-Path Together", "Path selection and packet scheduling solve different problems")
    cards = [
        ("SDN (Ryu / OpenFlow 1.3)", ["Central view of topology and stats", "Install exact 5-tuple flow rules", "Programmatic Packet-In / Flow-Mod", "REST API for dashboard & experiments"]),
        ("Multi-path forwarding", ["Three disjoint-enough routes S1–S6", "Offload elephant (bulk) flows", "Keep mice (voice) on shortest path", "Raise aggregate throughput beyond 40 Mbps"]),
        ("Hierarchical QoS (HTB)", ["Queue 2 High 60% min-rate", "Queue 1 Med 30% min-rate", "Queue 0 Low 10% min-rate", "Protects High even if path is busy"]),
        ("Closed-loop control", ["Poll port stats every 1.0 s", "u = Δtx_bytes×8 / (Δt×C)", "Confirm congestion over 3 intervals", "Recover only after 5 calm intervals"]),
    ]
    for i, (t, b) in enumerate(cards):
        x = Inches(0.4) + Inches(i * 3.22)
        card(s, x, Inches(1.4), Inches(3.05), Inches(5.5), t, b)

    # 5 Objectives
    s = prs.slides.add_slide(blank)
    header_bar(s, "Objectives of the Project", "Measurable outcomes for Review 2")
    numbered(s, Inches(0.55), Inches(1.35), Inches(12.2), Inches(5.6), [
        "Emulate a 6-switch multi-path OpenFlow network (Server A 10.0.0.1 ↔ Server B 10.0.0.2) in Mininet/OVS.",
        "Implement a Ryu controller that discovers topology, classifies traffic (DSCP + L4 port), and installs OF 1.3 rules.",
        "Compute shortest and alternate paths (Dijkstra + congestion penalty + canonical Path 1/2/3).",
        "Monitor link utilization in real time and confirm congestion with dual-threshold hysteresis (85% × 3 / 50% × 5).",
        "Reroute low-priority bulk first; keep high-priority voice/video on the primary path and in Queue 2.",
        "Apply Linux HTB / OVS QoS (r2q=100) so scheduling is independent of path selection.",
        "Provide a live dashboard (http://localhost:8000) for topology, telemetry, experiment buttons and CSV/JSON export.",
        "Compare Baseline vs Proposed (Adaptive + QoS) on latency, loss, jitter, bottleneck load and aggregate throughput.",
        "Validate core logic with 15 unit/integration tests (paths, hysteresis, classification, REST).",
    ], 16)

    # 6 Scope
    s = prs.slides.add_slide(blank)
    header_bar(s, "Scope, Assumptions and Non-Goals", "What Review 2 should and should not expect")
    card(s, Inches(0.45), Inches(1.35), Inches(6.1), Inches(5.6), "In scope", [
        "Emulated SDN (not hardware switch farm)", "OpenFlow 1.3 only", "Two servers, six OVS switches", "Three traffic classes / three paths", "IPv4, TCP/UDP, DSCP marking", "Controller Proxy ARP + static ARP", "Make-before-break flow migration", "Link-down recovery on S2–S4", "Web dashboard + experiment scripts", "WSL2 / Ubuntu + sudo Mininet",
    ], title_color=GREEN)
    card(s, Inches(6.75), Inches(1.35), Inches(6.1), Inches(5.6), "Out of scope / assumptions", [
        "Not a production WAN controller", "No IPv6 / MPLS / segment routing", "No TLS between controller and switches", "No multi-controller (ONOS/ODL) cluster", "Traffic is generated (iperf-style), not real users", "Results are emulation numbers, not ISP traces", "Host NICs assumed 100 Mbps", "Single Ryu instance on localhost", "Linux tc-htb quantum needs r2q=100",
    ], title_color=RED)

    # 7 Topology
    s = prs.slides.add_slide(blank)
    header_bar(s, "Network Topology", "config/topology.yaml — all bandwidths and delays are configurable")

    def node(slide, x, y, w, h, label, sub, fill=NAVY):
        add_round(slide, x, y, w, h, fill)
        add_text_box(slide, x, y + Inches(0.08), w, Inches(0.32), label, 14, True, WHITE, PP_ALIGN.CENTER)
        add_text_box(slide, x, y + Inches(0.36), w, Inches(0.28), sub, 11, False, RGBColor(0xD0, 0xE8, 0xE8), PP_ALIGN.CENTER)

    node(s, Inches(0.4), Inches(3.15), Inches(1.7), Inches(0.85), "Server A", "10.0.0.1  h1", TEAL)
    node(s, Inches(2.4), Inches(3.15), Inches(1.35), Inches(0.85), "S1", "edge ingress")
    node(s, Inches(4.35), Inches(1.55), Inches(1.35), Inches(0.85), "S2", "west core")
    node(s, Inches(4.35), Inches(4.75), Inches(1.35), Inches(0.85), "S3", "east core")
    node(s, Inches(6.7), Inches(1.55), Inches(1.35), Inches(0.85), "S4", "agg Path 1")
    node(s, Inches(6.7), Inches(4.75), Inches(1.35), Inches(0.85), "S5", "agg Path 2/3")
    node(s, Inches(9.05), Inches(3.15), Inches(1.35), Inches(0.85), "S6", "edge egress")
    node(s, Inches(10.7), Inches(3.15), Inches(2.1), Inches(0.85), "Server B", "10.0.0.2  h2", TEAL)

    # caption links
    bullets(s, Inches(0.45), Inches(5.75), Inches(12.4), Inches(1.4), [
        "h1–S1 and S6–h2: 100 Mbps / 1 ms    |    S1–S2: 50 Mbps / 2 ms    |    S1–S3: 30 Mbps / 5 ms",
        "S2–S4: 40 Mbps / 2 ms  (PRIMARY BOTTLENECK)    |    S2–S5: 25 Mbps / 4 ms    |    S3–S5: 20 Mbps / 3 ms",
        "S4–S6: 40 Mbps / 2 ms    |    S5–S6: 30 Mbps / 2 ms    |    OpenFlow DPID s1…s6 = 1…6",
    ], 14)

    # 8 Paths
    s = prs.slides.add_slide(blank)
    header_bar(s, "Canonical Multi-Path Routes (S1 → S6)", "Initial forwarding uses Path 1; Path 2/3 are congestion and failure backups")
    table_slide(s, ["Path", "Switch sequence", "Approx. delay", "Bottleneck", "Role"],
                [
                    ["Path 1", "S1 → S2 → S4 → S6", "~8 ms", "40 Mbps (S2–S4)", "Default shortest path; High stays here"],
                    ["Path 2", "S1 → S2 → S5 → S6", "~10 ms", "25 Mbps (S2–S5)", "First alternate; Low bulk offload"],
                    ["Path 3", "S1 → S3 → S5 → S6", "~12 ms", "20 Mbps (S3–S5)", "Second alternate / failure backup"],
                ],
                Inches(0.5), Inches(1.4), Inches(12.3),
                [Inches(1.4), Inches(3.0), Inches(2.0), Inches(2.5), Inches(3.4)])
    bullets(s, Inches(0.55), Inches(3.7), Inches(12.2), Inches(3.2), [
        "Path Computer: Dijkstra on delay (or cost), optional congestion penalty ×10 on confirmed-congested edges.",
        "Yen's / k-shortest style enumeration is available; production policy uses the three canonical paths above.",
        "High-priority (UDP/5001) is never voluntarily moved off Path 1; only Low (then Medium) migrate.",
        "Flow affinity: 5-tuple (src IP, dst IP, src port, dst port, proto) keeps a TCP flow on one path until a controlled migrate.",
        "Make-before-break: install higher-priority OF rules on the new path, then withdraw the old path — no blackhole.",
        "Link failure on S2–S4: controller treats port-down as immediate congestion/failure and shifts affected flows to Path 2 or 3.",
    ], 15)

    # 9 Traffic
    s = prs.slides.add_slide(blank)
    header_bar(s, "Traffic Classes and Classification", "Path = WHERE packets go   |   Queue = WHICH packets leave first")
    table_slide(s, ["Class", "App", "Profile", "DSCP", "Port", "Prio", "Queue", "Weight", "Policy"],
                [
                    ["High", "Voice / video", "UDP 5 Mbps", "46 EF", "5001", "3", "2", "60%", "Never rerouted; strict protect"],
                    ["Medium", "Web / APIs", "TCP 20 Mbps", "26 AF31", "5002", "2", "1", "30%", "Reroute if alt. BW enough"],
                    ["Low", "Bulk backup", "TCP 40 Mbps", "0 BE", "5003", "1", "0", "10%", "First to offload / rate-limit"],
                ],
                Inches(0.3), Inches(1.35), Inches(12.7),
                [Inches(1.15), Inches(1.45), Inches(1.55), Inches(1.2), Inches(0.9),
                 Inches(0.75), Inches(0.85), Inches(0.95), Inches(2.9)])
    bullets(s, Inches(0.5), Inches(4.15), Inches(12.3), Inches(2.8), [
        "Classifier uses both IP DSCP/TOS (RFC 2474 / 2597 / 3246) and L4 destination port — either match is enough in the controller.",
        "HTB min-rate guarantees: High 60%, Medium 30%, Low 10% of link rate; Low may burst to 100% when the link is idle.",
        "Offered load 65 Mbps vs Path 1 capacity 40 Mbps is intentional: Baseline must collapse; Proposed must uncollapse High + raise sum.",
        "iperf-style generator in mininet/traffic_generator.py; dashboard can inject custom class/rate/duration flows.",
    ], 15)

    # 10 Architecture
    s = prs.slides.add_slide(blank)
    header_bar(s, "System Architecture", "Three cooperating processes started by ./run.sh")
    layers = [
        (NAVY, "Presentation", ["FastAPI dashboard :8000", "vis.js topology + Chart.js", "WS telemetry, CSV/JSON export", "Run Baseline / Adaptive buttons"]),
        (TEAL, "Control plane", ["Ryu app OF :6653", "REST API :8080", "TopologyManager", "PathComputer (Dijkstra)", "NetworkMonitor 1 Hz", "QoSManager + PriorityRerouter"]),
        (RGBColor(0x2C, 0x3E, 0x50), "Data plane", ["Mininet hosts h1, h2", "OVS s1–s6 OF 1.3", "TCLink bw/delay/loss", "linux-htb queues 0/1/2", "r2q=100 (no HTB warning)"]),
        (RGBColor(0x6C, 0x34, 0x8D), "Ops", ["setup.sh / run.sh", "scripts/cleanup.sh", "run_baseline.sh", "run_adaptive.sh", "pytest tests/ (15/15)"]),
    ]
    for i, (c, t, b) in enumerate(layers):
        x = Inches(0.4) + Inches(i * 3.22)
        add_round(s, x, Inches(1.4), Inches(3.05), Inches(5.5), LIGHT)
        add_rect(s, x, Inches(1.4), Inches(3.05), Inches(0.55), c)
        add_text_box(s, x, Inches(1.48), Inches(3.05), Inches(0.4), t, 16, True, WHITE, PP_ALIGN.CENTER)
        bullets(s, x + Inches(0.12), Inches(2.1), Inches(2.8), Inches(4.5), b, 14)

    # 11 Modules
    s = prs.slides.add_slide(blank)
    header_bar(s, "Controller Module Map", "controller/ryu_app.py wires these components")
    rows = [
        ["ryu_app.py", "OF handshake, Packet-In, Proxy ARP, flow_mod, monitor loop, REST hook"],
        ["topology_manager.py", "Switch/link/host graph; DPID and port mapping"],
        ["path_computer.py", "Dijkstra, congestion-penalized weights, canonical Path 1/2/3"],
        ["monitor.py", "OFPPortStatsRequest every 1 s; utilization = Δbytes×8/(Δt×C)"],
        ["qos_manager.py", "Map class → queue id; DSCP/port classification"],
        ["rerouter.py", "Hysteresis FSM, flow registry, selective migration, event log"],
        ["rest_api.py", "Toggle adaptive/QoS, reset, topology/metrics/flows for dashboard"],
        ["mininet/start_network.py", "Topo + staticArp + OVS QoS + warmup ping"],
        ["dashboard/app.py", "UI, experiment orchestration, export, websocket push"],
    ]
    table_slide(s, ["Module", "Responsibility"], rows,
                Inches(0.5), Inches(1.3), Inches(12.3), [Inches(3.2), Inches(9.1)])

    # 12 Packet path
    s = prs.slides.add_slide(blank)
    header_bar(s, "Control-Plane Packet Path (first packet vs steady state)", "Cold start is why a naive ping shows 50% loss — we warm the network")
    numbered(s, Inches(0.5), Inches(1.3), Inches(12.2), Inches(3.6), [
        "Switch connects → SwitchFeatures → table-miss (priority 0) sends unknown packets to controller.",
        "ARP request for 10.0.0.1 / 10.0.0.2: controller Proxy ARP replies on in_port in < 0.2 ms (no flood, no loop storm).",
        "Hosts also get net.staticArp() so MAC tables exist before experiments.",
        "First IPv4 packet: Packet-In → classify (DSCP/port) → Dijkstra Path 1 → install match+queue along S1-S2-S4-S6.",
        "Subsequent packets hit the flow table in the datapath (no controller) — RTT ~8 ms on Path 1.",
        "Monitor loop updates utilizations; rerouter may install a new path for Low with make-before-break.",
    ], 16)
    card(s, Inches(0.5), Inches(5.05), Inches(12.3), Inches(1.9), "Engineering fixes that Review 2 should mention", [
        "HTB warning “quantum of class is big”: default r2q=10 on 100 Mbps links; we set other-config:r2q=100 on OVS QoS.",
        "Initial 50% ping drop: 2 s Mininet ping timer vs OpenFlow install latency; warmup ping + 1 s handshake settle → 0% verified loss.",
        "Docstring escape warning in topology.py fixed with a raw r\"\"\" string.",
    ], title_color=GOLD)

    # 13 Algorithm monitoring
    s = prs.slides.add_slide(blank)
    header_bar(s, "Algorithm 1 — Real-Time Utilization Monitoring", "Closes the loop between datapath counters and the rerouter")
    add_round(s, Inches(0.5), Inches(1.4), Inches(12.3), Inches(1.7), LIGHT)
    add_text_box(s, Inches(0.7), Inches(1.55), Inches(12), Inches(1.4),
                 "utilization  u  =  (Δ tx_bytes  ×  8)  /  (Δt  ×  link_capacity)\n"
                 "Poll interval Δt = 1.0 s via OFPPortStatsRequest / OFPPortStatsReply   |   capacity from topology.yaml",
                 20, True, NAVY, PP_ALIGN.CENTER)
    bullets(s, Inches(0.55), Inches(3.3), Inches(12.2), Inches(3.6), [
        "Each switch port is mapped back to a topology link (s2-s4, s2-s5, …) so utilization is comparable to configured Mbps.",
        "Dashboard paints links: Green < 70% (warning_threshold) · Yellow 70–85% · Red > 85% congested.",
        "A single 1-second spike is NOT congestion — hysteresis must confirm (next slide).",
        "Stats also feed per-flow throughput charts and CSV/JSON experiment logs.",
        "If a port goes DOWN, the monitor/topology layer marks the link failed; all flows using it must move, including High.",
    ], 16)

    # 14 Hysteresis
    s = prs.slides.add_slide(blank)
    header_bar(s, "Algorithm 2 — Dual-Threshold Hysteresis State Machine", "Stops route flapping from bursty TCP")
    table_slide(s, ["State", "Condition", "Consecutive intervals", "Action"],
                [
                    ["NORMAL", "u ≤ 50%", "—", "Keep shortest path; reset congestion counter"],
                    ["WARNING", "70% ≤ u < 85%", "counted but not confirmed", "Dashboard yellow; no migrate yet"],
                    ["CONGESTION_WARNING", "u ≥ 85%", "1 or 2 of 3", "Increment; still no migrate"],
                    ["CONGESTED", "u ≥ 85%", "≥ 3", "Confirm link; trigger priority-aware offload"],
                    ["RECOVERING", "u ≤ 50%", "1–4 of 5", "Hold current alternate path"],
                    ["RECOVERED", "u ≤ 50%", "≥ 5", "May return Low/Med to Path 1"],
                    ["MODERATE", "50% < u < 85%", "—", "Hold confirmed state; decay warning count"],
                ],
                Inches(0.4), Inches(1.3), Inches(12.5),
                [Inches(2.4), Inches(2.6), Inches(2.6), Inches(4.9)])
    bullets(s, Inches(0.55), Inches(5.55), Inches(12.2), Inches(1.5), [
        "Asymmetry is deliberate: easy to ENTER congestion (3 s) and hard to LEAVE (5 s) so TCP sawtooth does not bounce paths.",
        "Implemented in controller/rerouter.py: warning=0.70, congestion=0.85, recovery=0.50, intervals 3 and 5.",
    ], 15)

    # 15 Reroute policy
    s = prs.slides.add_slide(blank)
    header_bar(s, "Algorithm 3 — Priority-Aware Selective Migration", "Not all flows are equal when S2–S4 saturates")
    numbered(s, Inches(0.5), Inches(1.3), Inches(12.2), Inches(2.5), [
        "When link S2–S4 is CONGESTED, inspect active flow registry (high / medium / low).",
        "Migrate LOW first (TCP/5003 bulk) onto Path 2 [1,2,5,6] if residual bandwidth ≥ demand.",
        "If still congested, consider MEDIUM (TCP/5002) only if the alternate can absorb it.",
        "HIGH (UDP/5001) stays on Path 1 + Queue 2 unless the link has actually failed.",
        "Install new path (higher OF priority) then delete old matches — make-before-break.",
        "Log event {flow, from_path, to_path, reason, timestamp} for the dashboard audit trail.",
    ], 16)
    card(s, Inches(0.45), Inches(4.55), Inches(6.1), Inches(2.4), "Protected invariants", [
        "High never sacrificed to help Low throughput", "TCP flow stays on one path until migrate", "No broadcast ARP across the diamond", "QoS queues still apply on the new path",
    ], title_color=GREEN)
    card(s, Inches(6.75), Inches(4.55), Inches(6.1), Inches(2.4), "Expected live behaviour", [
        "Bulk dashed path animates S1-S2-S5-S6", "S2–S4 returns toward ~62% (safe)", "High RTT stays ~8 ms, loss 0%", "Aggregate goodput rises to ~49 Mbps",
    ])

    # 16 QoS
    s = prs.slides.add_slide(blank)
    header_bar(s, "QoS Data-Plane — Linux HTB on OVS Ports", "Scheduling still matters even after a perfect path choice")
    bullets(s, Inches(0.5), Inches(1.3), Inches(12.3), Inches(2.4), [
        "Every switch interface gets an OVS QoS record: type=linux-htb, max-rate = link Mbps, other-config:r2q=100.",
        "Three queues: q0 Low min 10% / max 100%, q1 Med min 30% / max 80%, q2 High min 60% / max 100%.",
        "OpenFlow actions include set_queue so classified packets enter the right HTB class.",
        "Experiment 3 (QoS only, Adaptive OFF) proves High still gets low delay when everyone shares Path 1.",
        "Experiment 2 (Adaptive ON, QoS OFF) proves offload helps capacity but High can still queue behind bulk on Path 1.",
        "Experiment 4 combines both — this is the proposed system.",
    ], 15)
    table_slide(s, ["Queue", "Class", "min-rate", "max-rate", "Typical latency budget"],
                [
                    ["2", "High EF", "60% of link", "100%", "≤ 10 ms"],
                    ["1", "Medium AF31", "30% of link", "80%", "≤ 30 ms"],
                    ["0", "Low BE", "10% of link", "100% (idle fill)", "≤ 100 ms (elastic)"],
                ],
                Inches(0.5), Inches(4.7), Inches(12.3),
                [Inches(1.5), Inches(2.4), Inches(2.4), Inches(2.6), Inches(3.4)])

    # 17 Implementation stack
    s = prs.slides.add_slide(blank)
    header_bar(s, "Implementation Stack and Runtime", "Must run in Ubuntu / WSL2 — not native Windows PowerShell")
    table_slide(s, ["Layer", "Technology", "Notes"],
                [
                    ["Emulator", "Mininet 2.3 + TCLink", "Namespaces, veth, sudo required"],
                    ["Datapath", "Open vSwitch + OpenFlow 1.3", "protocols=OpenFlow13 on every switch"],
                    ["Controller", "Ryu (or os_ken alias)", "Listen 6653; REST 8080"],
                    ["QoS", "ovs-vsctl linux-htb", "r2q=100; queues 0,1,2"],
                    ["Dashboard", "FastAPI + Uvicorn", "http://localhost:8000"],
                    ["UI", "vis.js + Chart.js", "Live topology and telemetry"],
                    ["Traffic", "iperf3 + Python generator", "UDP 5001, TCP 5002/5003"],
                    ["Config", "YAML (topology, qos)", "No hardcoded topology in code"],
                    ["Tests", "pytest 15/15", "Paths, hysteresis, API, DSCP"],
                    ["Python deps", "fastapi, uvicorn, pyyaml, networkx, httpx, matplotlib", "setup.sh / sdn-env"],
                ],
                Inches(0.45), Inches(1.25), Inches(12.4),
                [Inches(2.0), Inches(4.2), Inches(6.2)])

    # 18 Dashboard
    s = prs.slides.add_slide(blank)
    header_bar(s, "Web Dashboard — Review 2 Demo Surface", "Open http://localhost:8000 after *** Verified Reachability Ping Loss: 0% ***")
    cards = [
        ("Topology (vis.js)", ["Server A / B + S1–S6", "Green / yellow / red links", "Dashed = rerouted flow", "Click nodes for DPID/IP"]),
        ("Telemetry (Chart.js)", ["Per-flow throughput Mbps", "E2E latency ms", "Link utilization %", "Baseline vs Proposed bars"]),
        ("Controls", ["Run Baseline Experiment", "Run Adaptive + QoS", "Adaptive ON/OFF toggle", "QoS ON/OFF toggle"]),
        ("Data & ops", ["Custom flow inject", "Active flow table", "Export JSON / CSV", "Reroute event log"]),
    ]
    for i, (t, b) in enumerate(cards):
        x = Inches(0.4) + Inches((i % 4) * 3.22)
        card(s, x, Inches(1.4), Inches(3.05), Inches(5.5), t, b)

    # 19 Experiments overview
    s = prs.slides.add_slide(blank)
    header_bar(s, "Experimental Methodology", "Same offered load; only control policy changes")
    table_slide(s, ["ID", "Name", "Adaptive", "QoS", "What it proves"],
                [
                    ["E1", "Baseline shortest path", "OFF", "OFF", "Path 1 collapse: loss, delay, ~39 Mbps cap"],
                    ["E2", "Adaptive only", "ON", "OFF", "Bulk offload helps capacity; High still shares FIFO"],
                    ["E3", "QoS only", "OFF", "ON", "High protected on saturated Path 1; Low starved"],
                    ["E4", "Proposed Adaptive+QoS", "ON", "ON", "Best of both: 0% High loss, +26% goodput"],
                    ["E5", "Link failure S2–S4", "ON", "ON", "Port-down → Path 2/3 in milliseconds"],
                ],
                Inches(0.35), Inches(1.3), Inches(12.6),
                [Inches(0.7), Inches(3.0), Inches(1.5), Inches(1.2), Inches(6.2)])
    bullets(s, Inches(0.5), Inches(4.7), Inches(12.3), Inches(2.3), [
        "Traffic profile (45 s): High UDP 5 Mbps + Medium TCP 20 Mbps + Low TCP 40 Mbps, A → B.",
        "Scripts: ./scripts/run_baseline.sh and ./scripts/run_adaptive.sh POST toggles to :8080 then generate traffic.",
        "Metrics: High latency / loss / jitter, S2–S4 peak load, aggregate throughput, Low achieved rate.",
        "Fair comparison: identical topology, identical rates, identical duration; only flags differ.",
    ], 15)

    # 20 Results
    s = prs.slides.add_slide(blank)
    header_bar(s, "Results — Baseline vs Proposed (Experiment 1 vs 4)", "Headline numbers for Review 2")
    table_slide(s, ["Metric", "E1 Baseline", "E4 Proposed", "Improvement"],
                [
                    ["High-priority UDP latency", "18.7 ms", "8.14 ms", "56.5% lower"],
                    ["High-priority UDP packet loss", "14.6%", "0.0%", "Zero loss"],
                    ["High-priority jitter", "3.8 ms", "0.32 ms", "91.6% lower"],
                    ["S2–S4 peak utilization", "98.4% (saturated)", "62.5% (safe)", "36.5 pp lower"],
                    ["Aggregate throughput", "39.12 Mbps", "49.4 Mbps", "+26.3%"],
                    ["Low-priority bulk rate", "18.8 Mbps (throttled)", "24.6 Mbps on Path 2", "Stable offload"],
                ],
                Inches(0.4), Inches(1.3), Inches(12.5),
                [Inches(3.5), Inches(3.0), Inches(3.0), Inches(3.0)])
    bullets(s, Inches(0.5), Inches(5.35), Inches(12.3), Inches(1.6), [
        "Baseline is bottleneck-bound: 65 Mbps offered into 40 Mbps → High is collateral damage.",
        "Proposed splits elephant traffic onto unused Path 2 and gives High a 60% HTB floor on Path 1.",
        "These figures match the project README experimental observations (emulation, not a hardware testbed).",
    ], 15)

    # 21 Why it works
    s = prs.slides.add_slide(blank)
    header_bar(s, "Discussion — Why the Proposed System Wins", "Map metrics back to mechanisms")
    card(s, Inches(0.4), Inches(1.35), Inches(6.2), Inches(5.55), "Latency, loss, jitter (High)", [
        "Path 1 delay budget is ~8 ms when queues are short", "Queue 2 min-rate 60% stops bulk from filling the buffer", "High is not migrated onto longer Path 2/3", "Proxy ARP + warmup remove first-packet outliers", "Jitter drops because High no longer waits behind TCP bursts",
    ], title_color=GREEN)
    card(s, Inches(6.8), Inches(1.35), Inches(6.1), Inches(5.55), "Load and throughput", [
        "S2–S4 peak 98% → 62% after Low leaves", "Path 2 bottleneck 25 Mbps absorbs most of the 40 Mbps bulk", "Sum of paths > single 40 Mbps pipe → 49.4 Mbps", "Hysteresis prevents oscillating Low between paths", "Make-before-break avoids drop during the switch",
    ])

    # 22 Tests
    s = prs.slides.add_slide(blank)
    header_bar(s, "Verification — Automated Tests and Live Checks", "pytest -v tests/   →   15 / 15 passing")
    bullets(s, Inches(0.5), Inches(1.3), Inches(12.3), Inches(5.6), [
        "Dijkstra shortest path selection and congestion-penalty inflation of busy edges.",
        "Hysteresis counters: 3 intervals to confirm congestion; 5 intervals to confirm recovery; moderate band holds state.",
        "Priority-aware migration: High protected, Low selected first, Medium conditional.",
        "DSCP/TOS and L4 port classification maps to queue 2 / 1 / 0.",
        "FastAPI endpoints: /api/topology, /api/metrics, /api/flows, /api/results/export.",
        "Live: *** Verified Reachability Ping Loss: 0% *** after static ARP + warmup.",
        "Live: no sch_htb quantum warning after r2q=100.",
        "Live dashboard colour state and flow table (Voice High/Q2, Web Med/Q1, Bulk Low/Q0).",
        "Cleanup script prevents “address already in use” on 6653 / 8000 / 8080.",
    ], 16)

    # 23 How to run
    s = prs.slides.add_slide(blank)
    header_bar(s, "How to Run and Demonstrate (WSL2 / Ubuntu)", "Project path: Computer_Networks — not the empty comp_net folder")
    numbered(s, Inches(0.5), Inches(1.25), Inches(12.2), Inches(5.7), [
        "Open Ubuntu WSL2. cd /mnt/c/Users/Pavesh/OneDrive/Documents/Computer_Networks",
        "First time: sudo apt install mininet openvswitch-switch iperf3 python3-venv && ./setup.sh  (or source ~/sdn-env && pip install -r requirements.txt)",
        "Every run: ./scripts/cleanup.sh && ./run.sh   (enter sudo password for Mininet)",
        "Wait for: Verified Reachability Ping Loss: 0%  and  Network is running headless.",
        "Browser: http://localhost:8000  — show green topology, flow table, charts.",
        "Click Run Baseline Experiment — S2–S4 goes red, High latency/loss rise.",
        "Click Run Adaptive + QoS Experiment — Low moves to Path 2, High stays ~8 ms / 0% loss.",
        "Export JSON/CSV. Optional: ./scripts/run_baseline.sh and run_adaptive.sh from a second terminal.",
        "Stop with Ctrl+C in the run.sh terminal. If ports stuck: ./scripts/cleanup.sh && sudo mn -c",
    ], 15)

    # 24 Contributions
    s = prs.slides.add_slide(blank)
    header_bar(s, "Project Contributions (what to defend in Review 2)", "This is an integrated research prototype, not a single-script Mininet demo")
    items = [
        "Separation of concerns: path selection vs queue scheduling, both programmable.",
        "Priority-aware offload policy that never voluntarily displaces High traffic.",
        "Dual-threshold hysteresis plus make-before-break to keep TCP and voice stable.",
        "Canonical 3-path topology with realistic heterogeneous bw/delay, fully YAML-driven.",
        "Production-style ops: one-command run, cleanup, REST, dashboard, export, tests.",
        "Documented failure modes (HTB quantum, ARP/table-miss) and the engineering fixes.",
        "Quantitative comparison table suitable for a paper/report results section.",
    ]
    bullets(s, Inches(0.55), Inches(1.4), Inches(12.2), Inches(5.5), items, 18, DARK, 10)

    # 25 Limitations
    s = prs.slides.add_slide(blank)
    header_bar(s, "Limitations and Future Work", "Be honest in Review 2 — it builds credibility")
    card(s, Inches(0.4), Inches(1.35), Inches(6.2), Inches(5.55), "Current limitations", [
        "Emulation only (Mininet CPU, not line-rate ASIC)", "Two hosts; not a many-tenant DC fabric", "Single controller, no HA/PK", "Static three-class classifier (ports/DSCP)", "Results depend on host load / WSL virt", "No encryption or OF-Config/OVSDB mgmt plane HA", "Medium-class policy is simpler than High/Low",
    ], title_color=RED)
    card(s, Inches(6.8), Inches(1.35), Inches(6.1), Inches(5.55), "Future work", [
        "Elephant detection (IAT / byte counters) instead of fixed ports", "ML forecast of congestion before 85%", "More than 3 paths / ECMP within a class", "P4 or hardware OVS offload comparison", "INT / in-band telemetry for true e2e delay", "Multi-controller (Raft) and WAN delay to Ryu", "Formal SLA: 99.9% High packets < 10 ms",
    ], title_color=TEAL)

    # 26 Conclusion
    s = prs.slides.add_slide(blank)
    header_bar(s, "Conclusion", "Review 2 takeaway in four sentences")
    bullets(s, Inches(0.5), Inches(1.4), Inches(12.3), Inches(5.5), [
        "Shortest-path SDN alone is not enough when mixed-priority traffic exceeds a 40 Mbps bottleneck.",
        "Combining congestion-aware multi-path offload (Low first) with HTB priority queues (High always) restores High SLA and raises aggregate throughput.",
        "Hysteresis, flow affinity, Proxy ARP and make-before-break make the control loop usable, not just theoretically correct.",
        "The running system — Ryu + Mininet/OVS + FastAPI dashboard — lets us demonstrate Baseline collapse and Proposed recovery live.",
        "Headline: High latency 18.7 → 8.14 ms, loss 14.6% → 0%, jitter −91.6%, S2–S4 98.4% → 62.5%, goodput +26.3%.",
    ], 18, DARK, 12)

    # 27 Q&A
    s = prs.slides.add_slide(blank)
    add_rect(s, 0, 0, W, H, NAVY)
    add_rect(s, 0, 0, Inches(0.18), H, TEAL)
    add_text_box(s, Inches(0.7), Inches(2.2), Inches(12), Inches(1.2),
                 "Thank you", 48, True, WHITE)
    add_text_box(s, Inches(0.7), Inches(3.5), Inches(12), Inches(1.2),
                 "Questions for Review 2\nPriority-Aware Adaptive Traffic Management in Multi-Path SDN Networks",
                 22, False, RGBColor(0xC9, 0xD6, 0xDF))
    add_text_box(s, Inches(0.7), Inches(5.4), Inches(12), Inches(1.0),
                 "Demo:  ./scripts/cleanup.sh && ./run.sh   →   http://localhost:8000\nRepo:  Computer_Networks  |  OpenFlow 1.3  ·  Ryu  ·  Mininet  ·  FastAPI",
                 16, False, ACCENT)

    # 28 Backup likely questions
    s = prs.slides.add_slide(blank)
    header_bar(s, "Backup — Likely Reviewer Questions", "Keep this slide; jump here if grilled")
    bullets(s, Inches(0.5), Inches(1.3), Inches(12.3), Inches(5.7), [
        "Why not ECMP for all flows?  Because High would take the longer path and TCP would reorder; we want class-aware, sticky paths.",
        "Why 85% not 70%?  70% is only a warning colour; 85%×3s filters bursts. 50%×5s return path avoids flapping.",
        "Why HTB not HFSC/FQ-CoDel?  HTB maps cleanly to OVS queues and min-rate guarantees required by the spec.",
        "Is 0% loss real?  In emulation with Queue 2 reserved and warmup flows, High UDP observed 0% in E4; not a mathematical proof.",
        "What if Path 2 is also full?  Policy can fall through to Path 3 (20 Mbps) or keep Low rate-limited in Q0.",
        "Controller as bottleneck?  Only misses go to Ryu; steady-state is fully in OVS. Proxy ARP further cuts Packet-Ins.",
        "Security?  Out of scope for Review 2; localhost trusted testbed. Future: TLS, RBAC on REST.",
    ], 15)

    out_dir = os.path.dirname(os.path.abspath(__file__))
    out = os.path.join(out_dir, "Review2_Priority_Aware_Adaptive_SDN.pptx")
    prs.save(out)
    print(out)


if __name__ == "__main__":
    build()

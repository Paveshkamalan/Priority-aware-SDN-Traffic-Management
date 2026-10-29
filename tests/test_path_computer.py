"""
Unit Tests for PathComputer Module
Verifies Dijkstra routing, congestion penalties, and multi-path selection.
"""

import sys
import os
import pytest

# Ensure controller directory is in path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "controller")))

from path_computer import PathComputer


@pytest.fixture
def sample_network_graph():
    """Builds standard 6-switch multi-path network graph."""
    return {
        1: {
            2: {"bw": 50.0, "delay": 2.0, "cost": 2, "utilization": 0.0},
            3: {"bw": 30.0, "delay": 5.0, "cost": 5, "utilization": 0.0},
        },
        2: {
            1: {"bw": 50.0, "delay": 2.0, "cost": 2, "utilization": 0.0},
            4: {"bw": 40.0, "delay": 2.0, "cost": 2, "utilization": 0.0},
            5: {"bw": 25.0, "delay": 4.0, "cost": 4, "utilization": 0.0},
        },
        3: {
            1: {"bw": 30.0, "delay": 5.0, "cost": 5, "utilization": 0.0},
            5: {"bw": 20.0, "delay": 3.0, "cost": 3, "utilization": 0.0},
        },
        4: {
            2: {"bw": 40.0, "delay": 2.0, "cost": 2, "utilization": 0.0},
            6: {"bw": 40.0, "delay": 2.0, "cost": 2, "utilization": 0.0},
        },
        5: {
            2: {"bw": 25.0, "delay": 4.0, "cost": 4, "utilization": 0.0},
            3: {"bw": 20.0, "delay": 3.0, "cost": 3, "utilization": 0.0},
            6: {"bw": 30.0, "delay": 2.0, "cost": 2, "utilization": 0.0},
        },
        6: {
            4: {"bw": 40.0, "delay": 2.0, "cost": 2, "utilization": 0.0},
            5: {"bw": 30.0, "delay": 2.0, "cost": 2, "utilization": 0.0},
        },
    }


def test_initial_shortest_path(sample_network_graph):
    pc = PathComputer()
    path = pc.dijkstra_shortest_path(sample_network_graph, src=1, dst=6, weight_key="delay")
    # Path 1: S1 -> S2 -> S4 -> S6 has total delay 2 + 2 + 2 = 6 ms
    # Path 2: S1 -> S2 -> S5 -> S6 has delay 2 + 4 + 2 = 8 ms
    # Path 3: S1 -> S3 -> S5 -> S6 has delay 5 + 3 + 2 = 10 ms
    assert path == [1, 2, 4, 6]


def test_penalized_routing_on_congestion(sample_network_graph):
    pc = PathComputer(default_congestion_penalty=15.0)

    # Congest link (2, 4)
    congested_links = {(2, 4), (4, 2)}
    path = pc.dijkstra_shortest_path(
        sample_network_graph,
        src=1,
        dst=6,
        weight_key="delay",
        penalize_congested=True,
        congested_links=congested_links,
    )
    # When (2, 4) is penalized, Dijkstra must divert to Path 2: S1 -> S2 -> S5 -> S6
    assert path == [1, 2, 5, 6]


def test_path_metrics_evaluation(sample_network_graph):
    metrics = PathComputer.evaluate_path_metrics(sample_network_graph, [1, 2, 4, 6])
    assert metrics["bottleneck_bw"] == 40.0
    assert metrics["total_delay"] == 6.0
    assert metrics["hops"] == 3


def test_best_alternate_path_selection(sample_network_graph):
    pc = PathComputer()
    current = [1, 2, 4, 6]
    # Mark (2, 4) congested in graph
    sample_network_graph[2][4]["utilization"] = 0.95
    sample_network_graph[4][2]["utilization"] = 0.95

    alt = pc.select_best_alternate_path(sample_network_graph, src=1, dst=6, current_path=current)
    assert alt in [[1, 2, 5, 6], [1, 3, 5, 6]]
    assert alt != current

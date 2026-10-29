"""
Unit Tests for PriorityRerouter Module
Verifies hysteresis thresholds, priority discrimination, and make-before-break logging.
"""

import sys
import os
import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "controller")))

from rerouter import PriorityRerouter
from path_computer import PathComputer


@pytest.fixture
def rerouter():
    return PriorityRerouter(
        warning_threshold=0.70,
        congestion_threshold=0.85,
        recovery_threshold=0.50,
        congestion_intervals=3,
        recovery_intervals=5,
    )


@pytest.fixture
def dummy_graph():
    return {
        1: {2: {"bw": 50, "delay": 2, "utilization": 0.0}, 3: {"bw": 30, "delay": 5, "utilization": 0.0}},
        2: {4: {"bw": 40, "delay": 2, "utilization": 0.90}, 5: {"bw": 25, "delay": 4, "utilization": 0.1}},
        3: {5: {"bw": 20, "delay": 3, "utilization": 0.0}},
        4: {6: {"bw": 40, "delay": 2, "utilization": 0.0}},
        5: {6: {"bw": 30, "delay": 2, "utilization": 0.0}},
        6: {4: {"bw": 40, "delay": 2, "utilization": 0.0}, 5: {"bw": 30, "delay": 2, "utilization": 0.0}},
    }


def test_hysteresis_congestion_intervals(rerouter):
    # Interval 1: High utilization, but not yet confirmed
    is_cong, state = rerouter.update_link_state(2, 4, 0.92)
    assert not is_cong
    assert "CONGESTION_WARNING" in state

    # Interval 2
    is_cong, state = rerouter.update_link_state(2, 4, 0.91)
    assert not is_cong

    # Interval 3: 3rd consecutive check reaches threshold -> Confirmed Congestion!
    is_cong, state = rerouter.update_link_state(2, 4, 0.89)
    assert is_cong
    assert state == "CONGESTED"
    assert (2, 4) in rerouter.confirmed_congested_links


def test_priority_discrimination_rerouting(rerouter, dummy_graph):
    pc = PathComputer()

    # Register High and Low flows on Path 1: [1, 2, 4, 6]
    rerouter.register_flow("flow_high", priority=3, traffic_class="high", initial_path=[1, 2, 4, 6])
    rerouter.register_flow("flow_low", priority=1, traffic_class="low", initial_path=[1, 2, 4, 6])

    # Mark link (2, 4) congested for 3 intervals
    for _ in range(3):
        rerouter.update_link_state(2, 4, 0.92)

    actions = rerouter.check_and_reroute_flows(pc, dummy_graph)

    # Low-priority flow must be rerouted!
    low_rerouted = [a for a in actions if a["flow_id"] == "flow_low"]
    assert len(low_rerouted) == 1
    assert low_rerouted[0]["new_path"] != [1, 2, 4, 6]

    # High-priority flow must NOT be rerouted!
    high_rerouted = [a for a in actions if a["flow_id"] == "flow_high"]
    assert len(high_rerouted) == 0
    assert rerouter.active_flows["flow_high"]["current_path"] == [1, 2, 4, 6]


def test_recovery_hysteresis(rerouter):
    # Confirm congestion first
    for _ in range(3):
        rerouter.update_link_state(2, 4, 0.90)
    assert (2, 4) in rerouter.confirmed_congested_links

    # Link drops below 50%
    for _ in range(4):
        is_cong, _ = rerouter.update_link_state(2, 4, 0.35)
        # Not yet 5 intervals
        assert (2, 4) in rerouter.confirmed_congested_links

    # 5th check below 50%
    is_cong, state = rerouter.update_link_state(2, 4, 0.35)
    assert not is_cong
    assert state == "NORMAL"
    assert (2, 4) not in rerouter.confirmed_congested_links

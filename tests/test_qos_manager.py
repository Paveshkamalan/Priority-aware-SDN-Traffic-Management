"""
Unit Tests for QoSManager Module
Verifies priority queue classification by port and IP DSCP byte.
"""

import sys
import os
import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "controller")))

from qos_manager import QoSManager


def test_port_based_classification():
    qos = QoSManager(enabled=True)

    # Port 5001 -> High Priority (Voice UDP), Queue 2
    c_high = qos.classify_packet(ip_proto=17, dst_port=5001)
    assert c_high["priority"] == 3
    assert c_high["queue_id"] == 2
    assert c_high["class"] == "high"

    # Port 5002 -> Medium Priority (Web TCP), Queue 1
    c_med = qos.classify_packet(ip_proto=6, dst_port=5002)
    assert c_med["priority"] == 2
    assert c_med["queue_id"] == 1
    assert c_med["class"] == "medium"

    # Port 5003 -> Low Priority (Bulk TCP), Queue 0
    c_low = qos.classify_packet(ip_proto=6, dst_port=5003)
    assert c_low["priority"] == 1
    assert c_low["queue_id"] == 0
    assert c_low["class"] == "low"


def test_dscp_based_classification():
    qos = QoSManager(enabled=True)

    # DSCP 46 (EF) -> TOS = 46 << 2 = 184
    c_ef = qos.classify_packet(tos=184)
    assert c_ef["priority"] == 3
    assert c_ef["queue_id"] == 2

    # DSCP 26 (AF31) -> TOS = 26 << 2 = 104
    c_af = qos.classify_packet(tos=104)
    assert c_af["priority"] == 2
    assert c_af["queue_id"] == 1


def test_qos_disabled_behavior():
    qos = QoSManager(enabled=False)

    # When disabled, all traffic maps to default Queue 0
    c_high = qos.classify_packet(dst_port=5001)
    assert c_high["queue_id"] == 0

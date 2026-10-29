"""
Integration Tests for Dashboard FastAPI REST APIs
Verifies endpoints /api/topology, /api/metrics, /api/flows, /api/results/export.
"""

import sys
import os
import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "dashboard")))

from app import app


@pytest.fixture
def client():
    return TestClient(app)


def test_index_page(client):
    response = client.get("/")
    assert response.status_code == 200
    assert "Priority-Aware Adaptive Traffic Management" in response.text


def test_get_topology_api(client):
    response = client.get("/api/topology")
    assert response.status_code == 200
    data = response.json()
    assert "nodes" in data
    assert "edges" in data
    assert len(data["nodes"]) >= 8  # 6 switches + 2 hosts


def test_get_metrics_api(client):
    response = client.get("/api/metrics")
    assert response.status_code == 200
    data = response.json()
    assert "links" in data
    assert "adaptive_enabled" in data


def test_get_flows_api(client):
    response = client.get("/api/flows")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) >= 3


def test_export_results_api(client):
    response = client.get("/api/results/export?format=json")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "exported"
    assert data["format"] == "json"

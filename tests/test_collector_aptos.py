from __future__ import annotations
from typing import Dict, List, Optional, Tuple
from unittest.mock import patch

from blockchain_collector.core import load_collectors, run_collector, bundled_schema_path


def test_discovery_aptos_registered():
    names = set(load_collectors().keys())
    assert "aptos" in names


def _probe_ok_mainnet(url: str):
    # body can be empty; we rely on headers for chain id & version
    body: Optional[Dict] = None
    headers: Dict[str, str] = {
        "x-aptos-chain-id": "1",
        "x-aptos-node-version": "aptos-node/1.2.3",
    }
    return body, headers, []


@patch("blockchain_collector.collectors.aptos._probe_ledger", side_effect=_probe_ok_mainnet)
def test_run_aptos_success_mainnet(mock_probe):
    data = run_collector(
        collector_name="aptos",
        schema_path=bundled_schema_path(),
        validate=True,
    )
    assert data["metadata"]["collector_name"] == "aptos"
    assert data["metadata"]["last_collect_status"] == "success"
    assert data["blockchain"]["blockchain_ecosystem"] == "Aptos"
    assert data["blockchain"]["blockchain_network_name"] == "mainnet"
    assert data["blockchain"]["chain_id"] == 1
    assert data["workload"]["client_name"] == "aptos-node"
    assert data["workload"]["client_version"].startswith("aptos-node/")


def _probe_only_version(url: str):
    body = None
    headers = {
        "x-aptos-node-version": "aptos-node/2.0.1",
    }
    return body, headers, []


@patch("blockchain_collector.collectors.aptos._probe_ledger", side_effect=_probe_only_version)
def test_run_aptos_partial_unknown_network(mock_probe):
    data = run_collector(
        collector_name="aptos",
        schema_path=bundled_schema_path(),
        validate=True,
    )
    assert data["metadata"]["last_collect_status"] == "partial"
    assert data["blockchain"]["blockchain_network_name"] == "unknown"

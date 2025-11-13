from __future__ import annotations
import json
from unittest.mock import patch, Mock

from blockchain_collector.core import load_collectors, run_collector, bundled_schema_path


def test_discovery_reth_variants_registered():
    names = set(load_collectors().keys())
    assert "reth" in names
    assert "op-reth" in names
    assert "bera-reth" in names


def _mock_jsonrpc_success(url: str, method: str, params=None, timeout=2.5):
    if method == "web3_clientVersion":
        return "reth/v1.0.0", None
    if method == "eth_chainId":
        return "0x1", None  # mainnet
    if method == "net_version":
        return "1", None
    return None, f"unexpected method {method}"


@patch("blockchain_collector.collectors._reth_common._find_reth_bin", return_value=None)
@patch("blockchain_collector.collectors._reth_common._jsonrpc", side_effect=_mock_jsonrpc_success)
def test_run_collector_reth_success(mock_rpc: Mock, mock_bin: Mock):
    data = run_collector(
        collector_name="reth",
        schema_path=bundled_schema_path(),
        validate=True,
    )
    assert data["metadata"]["collector_name"] == "reth"
    assert data["metadata"]["last_collect_status"] == "success"
    assert data["workload"]["client_name"] == "reth"
    assert data["workload"]["client_version"] == "reth/v1.0.0"
    assert data["blockchain"]["chain_id"] == 1
    assert data["blockchain"]["blockchain_network_name"] == "mainnet"


@patch("blockchain_collector.collectors._reth_common._find_reth_bin", return_value=None)
@patch("blockchain_collector.collectors._reth_common._jsonrpc", side_effect=_mock_jsonrpc_success)
def test_run_collector_variants_success(mock_rpc: Mock, mock_bin: Mock):
    for name in ("op-reth", "bera-reth"):
        data = run_collector(
            collector_name=name,
            schema_path=bundled_schema_path(),
            validate=True,
        )
        assert data["metadata"]["collector_name"] == name
        assert data["metadata"]["last_collect_status"] == "success"
        assert data["workload"]["client_name"] == name

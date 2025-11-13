from __future__ import annotations
from unittest.mock import patch

from blockchain_collector.core import load_collectors, run_collector, bundled_schema_path


def test_discovery_polkadot_registered():
    names = set(load_collectors().keys())
    assert "substrate" in names


def _mock_jsonrpc(url: str, method: str, params=None, timeout: float = 2.5):
    if method == "system_version":
        return "polkadot/v1.0.0", None
    if method == "system_chain":
        return "Polkadot", None
    if method == "chain_getBlockHash":
        return "0x1111222233334444555566667777888899990000aaaabbbbccccddddeeeeffff", None
    if method == "system_name":
        return "polkadot", None
    return None, f"unexpected method {method}"


@patch("blockchain_collector.collectors._substrate_common._jsonrpc", side_effect=_mock_jsonrpc)
def test_run_substrate_polkd_success(mock_rpc):
    data = run_collector(
        collector_name="substrate",
        schema_path=bundled_schema_path(),
        validate=True,
    )
    assert data["metadata"]["collector_name"] == "substrate"
    assert data["metadata"]["last_collect_status"] == "success"
    assert data["blockchain"]["blockchain_ecosystem"] == "Polkadot"
    assert data["blockchain"]["blockchain_network_name"] == "Polkadot"
    assert data["workload"]["client_name"] == "polkadot"
    assert data["workload"]["client_version"] == "polkadot/v1.0.0"
    assert isinstance(data["blockchain"].get("chain_id"), str)

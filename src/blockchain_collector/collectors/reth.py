
from __future__ import annotations
import os
import json
import subprocess
from typing import Dict, Optional
from urllib import request, error
from ..core import BaseCollector, CollectResult

RPC_ENV = "RETH_RPC_URL"
DEFAULT_RPC = "http://127.0.0.1:8545"

def _jsonrpc(url: str, method: str, params=None, timeout=2.5):
    if params is None:
        params = []
    payload = json.dumps({"jsonrpc":"2.0","id":1,"method":method,"params":params}).encode()
    req = request.Request(url, data=payload, headers={"Content-Type":"application/json"})
    with request.urlopen(req, timeout=timeout) as resp:
        data = json.loads(resp.read().decode())
        if "error" in data:
            raise RuntimeError(f"RPC error {data['error']}")
        return data["result"]

def _get_client_version_from_rpc(url: str) -> Optional[str]:
    try:
        return _jsonrpc(url, "web3_clientVersion")
    except Exception:
        return None

def _get_chain_id(url: str) -> Optional[int]:
    try:
        hex_id = _jsonrpc(url, "eth_chainId")
        return int(hex_id, 16)
    except Exception:
        return None

def _get_net_version(url: str) -> Optional[str]:
    try:
        return _jsonrpc(url, "net_version")
    except Exception:
        return None

def _map_network_name(chain_id: Optional[int], net_version: Optional[str]) -> str:
    # Prefer chain_id mapping; fallback to net_version
    mapping = {
        1: "mainnet",
        11155111: "sepolia",
        17000: "holesky",
        5: "goerli",
    }
    if chain_id in mapping:
        return mapping[chain_id]
    if net_version:
        # some clients return decimal as string
        try:
            cid = int(net_version)
            return mapping.get(cid, f"network-{cid}")
        except Exception:
            pass
        return str(net_version)
    return "unknown"

class RethCollector(BaseCollector):
    """
    Collector for the Reth (Rust Ethereum) execution client.

    It attempts to:
      1) read `reth --version` for the binary version, and
      2) query local JSON-RPC for chain id and network info.

    You can override the RPC URL using the env var RETH_RPC_URL (default: http://127.0.0.1:8545).
    """
    NAME = "reth"
    VERSION = "0.1.0"

    def collect(self) -> CollectResult:
        # 1) Binary version (best-effort)
        client_version_cli = None
        try:
            proc = subprocess.run(["reth", "--version"], capture_output=True, text=True, check=True)
            # first line like "reth X.Y.Z (git SHA)"
            client_version_cli = proc.stdout.strip().splitlines()[0]
        except Exception:
            pass  # keep best-effort

        # 2) RPC-derived info
        rpc_url = os.environ.get(RPC_ENV, DEFAULT_RPC)

        client_version_rpc = _get_client_version_from_rpc(rpc_url)
        chain_id = _get_chain_id(rpc_url)
        net_version = _get_net_version(rpc_url)
        network_name = _map_network_name(chain_id, net_version)

        # Compose workload + blockchain sections
        workload: Dict = {
            "client_name": "reth",
            "client_version": client_version_rpc or client_version_cli or "unknown",
            "rpc_url": rpc_url,
        }
        blockchain: Dict = {
            "blockchain_ecosystem": "Ethereum",
            "blockchain_network_name": network_name,
            "chain_id": chain_id if chain_id is not None else -1,
        }
        return CollectResult(blockchain=blockchain, workload=workload)

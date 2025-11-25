from __future__ import annotations
import os
import subprocess
import shutil
from typing import Dict, Optional, List

from ..custom_types import CollectResult, CollectorPartialError, CollectorFailedError
from ..rpc_evm import (
    rpc_get_client_version,
    rpc_get_chain_id,
    rpc_get_net_version,
    map_network_name as _map_network_name
)

# Version for all reth-derived collectors
RETH_COLLECTOR_VERSION = "0.1.2"

# RPC configuration
RPC_ENV = "RETH_RPC_URL"
DEFAULT_RPC = "http://127.0.0.1:8545"


def _find_reth_bin() -> Optional[str]:
    p = os.environ.get("RETH_BIN")
    if p and os.path.isfile(p) and os.access(p, os.X_OK):
        return p
    w = shutil.which("reth")
    if w and os.access(w, os.X_OK):
        return w
    for cand in ("/snap/bin/reth", "/usr/bin/reth", "/usr/local/bin/reth", "/home/reth/reth"):
        if os.path.isfile(cand) and os.access(cand, os.X_OK):
            return cand
    return None


def collect_reth(client_name: str, rpc_env: str = RPC_ENV, default_rpc: str = DEFAULT_RPC) -> CollectResult:
    messages: List[str] = []

    # CLI version (best-effort)
    client_version_cli: Optional[str] = None
    reth_bin = _find_reth_bin()
    if reth_bin:
        try:
            proc = subprocess.run([reth_bin, "--version"], capture_output=True, text=True, check=True)
            vline = (proc.stdout or "").strip().splitlines()
            client_version_cli = vline[0] if vline else None
            if not client_version_cli:
                messages.append("reth --version returned no output")
        except Exception as e:
            messages.append(f"{reth_bin} --version failed: {e!r}")
    else:
        messages.append("reth binary not found (set RETH_BIN or install reth)")

    # RPC info (with detailed error messages)
    rpc_url = os.environ.get(rpc_env, default_rpc)

    # Get client version from RPC
    client_version_rpc, err_cv = rpc_get_client_version(rpc_url)
    if client_version_rpc is None:
        messages.append(err_cv or "RPC web3_clientVersion unavailable")

    # Get chain ID from RPC
    chain_id, err_cid = rpc_get_chain_id(rpc_url)
    if chain_id is None:
        messages.append(err_cid or "RPC eth_chainId unavailable")

    # Get network version from RPC
    net_version, err_net = rpc_get_net_version(rpc_url)
    if net_version is None:
        messages.append(err_net or "RPC net_version unavailable")

    network_name = _map_network_name(chain_id, net_version)

    # Compose payload we have so far
    workload: Dict = {
        "client_name": client_name,
        "client_version": client_version_rpc or client_version_cli or "unknown",
        "rpc_url": rpc_url,
    }
    blockchain: Dict = {
        "blockchain_ecosystem": "Ethereum",
        "blockchain_network_name": network_name,
        "chain_id": chain_id if chain_id is not None else -1,
    }

    # Decide status
    have_any_info = any([client_version_rpc, client_version_cli, chain_id is not None, net_version is not None])
    workload_complete = (workload["client_version"] != "unknown")
    blockchain_complete = (chain_id is not None) and (network_name != "unknown")

    if not have_any_info:
        raise CollectorFailedError("; ".join(messages) or "no RPC or CLI info")

    if not (workload_complete and blockchain_complete):
        partial = CollectResult(blockchain=blockchain, workload=workload)
        if not workload_complete:
            messages.append("Missing client_version (both RPC and CLI failed).")
        if chain_id is None:
            messages.append("Missing chain_id.")
        if network_name == "unknown":
            messages.append("Unable to determine known network name.")
        raise CollectorPartialError(messages or ["Partial data only."], partial=partial)

    # Success
    return CollectResult(blockchain=blockchain, workload=workload)

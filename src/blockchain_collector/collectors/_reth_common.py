from __future__ import annotations
import os, json, subprocess, socket, shutil
from typing import Dict, Optional, List, Tuple
from urllib import request, error as urlerror
from ..core import CollectResult, CollectorPartialError, CollectorFailedError

# Version for all reth-derived collectors
RETH_COLLECTOR_VERSION = "0.1.2"

# RPC configuration
RPC_ENV = "RETH_RPC_URL"
DEFAULT_RPC = "http://127.0.0.1:8545"


def _jsonrpc(url: str, method: str, params=None, timeout=2.5) -> Tuple[Optional[object], Optional[str]]:
    if params is None:
        params = []
    payload = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params}).encode()
    req = request.Request(url, data=payload, headers={"Content-Type": "application/json"})
    try:
        with request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode())
            if "error" in data:
                return None, f"rpc {method} error: {data['error']}"
            return data.get("result"), None
    except socket.timeout:
        return None, f"rpc {method} timeout after {timeout}s (url={url})"
    except urlerror.URLError as e:
        reason = getattr(e, "reason", e)
        return None, f"rpc {method} connection error (url={url}): {reason}"
    except Exception as e:
        return None, f"rpc {method} unexpected error (url={url}): {e}"


def _get_client_version_from_rpc(url: str):
    return _jsonrpc(url, "web3_clientVersion")


def _get_chain_id(url: str):
    res, err = _jsonrpc(url, "eth_chainId")
    if res is None:
        return None, err
    try:
        return int(res, 16), None
    except Exception as e:
        return None, f"rpc eth_chainId parse error for {res!r}: {e}"


def _get_net_version(url: str):
    return _jsonrpc(url, "net_version")


def _map_network_name(chain_id: Optional[int], net_version: Optional[str]) -> str:
    mapping = {1: "mainnet", 11155111: "sepolia", 17000: "holesky", 5: "goerli"}
    if chain_id in mapping:
        return mapping[chain_id]
    if net_version:
        try:
            cid = int(net_version)
            return mapping.get(cid, f"network-{cid}")
        except Exception:
            return str(net_version)
    return "unknown"


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

    client_version_rpc, err_cv = _get_client_version_from_rpc(rpc_url)
    if client_version_rpc is None:
        messages.append(err_cv or "RPC web3_clientVersion unavailable")

    chain_id, err_cid = _get_chain_id(rpc_url)
    if chain_id is None:
        messages.append(err_cid or "RPC eth_chainId unavailable")

    net_version, err_net = _get_net_version(rpc_url)
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

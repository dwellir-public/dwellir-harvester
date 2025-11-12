from __future__ import annotations
import os
import json
import subprocess
from typing import Dict, Optional, List
from urllib import request
from ..core import BaseCollector, CollectResult, CollectorPartialError, CollectorFailedError
import socket
from urllib import request, error as urlerror

RPC_ENV = "RETH_RPC_URL"
DEFAULT_RPC = "http://127.0.0.1:8545"

def _jsonrpc(url: str, method: str, params=None, timeout=2.5):
    """
    Return (result, errstr). On success errstr is None.
    On connection errors / timeouts, result is None and errstr is a human-readable reason.
    """
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
        # e.reason may be a str or an exception like ConnectionRefusedError
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

class RethCollector(BaseCollector):
    """
    Collector for the Reth (Rust Ethereum) execution client.

    Decision logic:
      - SUCCESS  => we have a client_version (RPC or CLI) AND a chain_id AND a known network_name.
      - PARTIAL  => we have *some* info (e.g., client_version or chain hints) but one or more
                    critical fields are missing/unknown.
      - FAILED   => we couldn't get anything meaningful (no RPC, CLI not found, etc).
    """
    NAME = "reth"
    VERSION = "0.1.1"

    def collect(self) -> CollectResult:
        messages: List[str] = []

        # 1) Try CLI version (best-effort)
        client_version_cli: Optional[str] = None
        try:
            proc = subprocess.run(["/snap/bin/reth", "--version"], capture_output=True, text=True, check=True)
            client_version_cli = (proc.stdout or "").strip().splitlines()[0] or None
            if not client_version_cli:
                messages.append("reth --version returned no output")
        except Exception as e:
            messages.append(f"Could not run 'reth --version': {e!r}")

        # RPC-derived info
        rpc_url = os.environ.get(RPC_ENV, DEFAULT_RPC)

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

        # Compose what we have
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

        # Decide status
        have_any_info = any([
            client_version_rpc, client_version_cli, chain_id is not None, net_version is not None
        ])
        workload_complete = (workload["client_version"] != "unknown")
        blockchain_complete = (chain_id is not None) and (network_name != "unknown")

        if not have_any_info:
            # Nothing useful at all → fail hard
            raise CollectorFailedError("Unable to retrieve client version or chain/network information from RPC or CLI." + messages)

        if not (workload_complete and blockchain_complete):
            # We got some info, but not all critical bits → mark partial
            if not workload_complete:
                messages.append("Missing client_version (both RPC and CLI failed).")
            if chain_id is None:
                messages.append("Missing chain_id.")
            if network_name == "unknown":
                messages.append("Unable to determine known network name.")
            # Signal partial (core will set status=partial; note it clears blockchain/workload)
            raise CollectorPartialError(messages or ["Partial data only."])

        # All good → success
        return CollectResult(blockchain=blockchain, workload=workload)

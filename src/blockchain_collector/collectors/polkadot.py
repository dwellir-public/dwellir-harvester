from __future__ import annotations
import json
import os
import socket
from typing import Dict, Optional, Tuple, List
from urllib import request, error as urlerror

from ..core import BaseCollector, CollectResult, CollectorPartialError, CollectorFailedError

RPC_ENV = "POLKADOT_RPC_URL"
DEFAULT_RPC = "http://127.0.0.1:9933"


def _jsonrpc(url: str, method: str, params=None, timeout: float = 2.5) -> Tuple[Optional[object], Optional[str]]:
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


def _get_system_version(url: str) -> Tuple[Optional[str], Optional[str]]:
    res, err = _jsonrpc(url, "system_version")
    if res is None:
        return None, err
    try:
        return str(res), None
    except Exception as e:
        return None, f"rpc system_version parse error for {res!r}: {e}"


def _get_system_chain(url: str) -> Tuple[Optional[str], Optional[str]]:
    res, err = _jsonrpc(url, "system_chain")
    if res is None:
        return None, err
    try:
        return str(res), None
    except Exception as e:
        return None, f"rpc system_chain parse error for {res!r}: {e}"


def _get_genesis_hash(url: str) -> Tuple[Optional[str], Optional[str]]:
    res, err = _jsonrpc(url, "chain_getBlockHash", [0])
    if res is None:
        return None, err
    try:
        return str(res), None
    except Exception as e:
        return None, f"rpc chain_getBlockHash parse error for {res!r}: {e}"


class PolkadotCollector(BaseCollector):
    NAME = "polkadot"
    VERSION = "0.1.0"

    def collect(self) -> CollectResult:
        messages: List[str] = []

        rpc_url = os.environ.get(RPC_ENV, DEFAULT_RPC)

        system_version, err_ver = _get_system_version(rpc_url)
        if system_version is None:
            messages.append(err_ver or "RPC system_version unavailable")

        system_chain, err_chain = _get_system_chain(rpc_url)
        if system_chain is None:
            messages.append(err_chain or "RPC system_chain unavailable")

        genesis_hash, err_gen = _get_genesis_hash(rpc_url)
        if genesis_hash is None:
            messages.append(err_gen or "RPC chain_getBlockHash(0) unavailable")

        workload: Dict = {
            "client_name": "polkadot",
            "client_version": system_version or "unknown",
            "rpc_url": rpc_url,
        }
        blockchain: Dict = {
            "blockchain_ecosystem": "Polkadot",
            "blockchain_network_name": system_chain or "unknown",
        }
        if genesis_hash:
            blockchain["chain_id"] = genesis_hash

        have_any_info = any([system_version, system_chain, genesis_hash])
        workload_complete = bool(system_version)
        blockchain_complete = bool(system_chain)

        if not have_any_info:
            raise CollectorFailedError("; ".join(messages) or "no RPC info from node")

        if not (workload_complete and blockchain_complete):
            partial = CollectResult(blockchain=blockchain, workload=workload)
            if not workload_complete:
                messages.append("Missing client_version (RPC system_version failed).")
            if not blockchain_complete:
                messages.append("Missing blockchain_network_name (RPC system_chain failed).")
            raise CollectorPartialError(messages or ["Partial data only."], partial=partial)

        return CollectResult(blockchain=blockchain, workload=workload)

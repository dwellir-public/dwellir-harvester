from __future__ import annotations
import os
import json
import socket
from typing import Dict, Optional, Tuple, List
from urllib import request, error as urlerror

from ..core import BaseCollector, CollectResult, CollectorPartialError, CollectorFailedError


APTOS_COLLECTOR_VERSION = "0.1.0"

# REST configuration
RPC_ENV = "APTOS_RPC_URL"
DEFAULT_RPC = "http://127.0.0.1:8080"


def _http_get(url: str, timeout: float = 2.5) -> Tuple[Optional[Dict], Dict[str, str], Optional[str]]:
    """Simple GET that tries to parse JSON body and always returns headers.

    Returns (json_body_or_None, headers_lowercased, error_str_or_None)
    """
    req = request.Request(url, headers={"Accept": "application/json"})
    try:
        with request.urlopen(req, timeout=timeout) as resp:
            headers = {k.lower(): v for k, v in resp.headers.items()}
            data: Optional[Dict] = None
            try:
                raw = resp.read()
                if raw:
                    data = json.loads(raw.decode())
            except Exception:
                # Non-JSON body; that's fine for our purposes
                data = None
            return data, headers, None
    except socket.timeout:
        return None, {}, f"GET timeout after {timeout}s (url={url})"
    except urlerror.HTTPError as e:
        return None, {}, f"HTTP {e.code} for {url}: {e.reason}"
    except urlerror.URLError as e:
        reason = getattr(e, "reason", e)
        return None, {}, f"Connection error (url={url}): {reason}"
    except Exception as e:
        return None, {}, f"Unexpected error (url={url}): {e}"


def _probe_ledger(rest_base: str) -> Tuple[Optional[Dict], Dict[str, str], List[str]]:
    """Try a few likely paths to obtain ledger info and headers."""
    base = rest_base.rstrip("/")
    candidates = [
        base,              # if user already provided / or /v1
        base + "/",
        base + "/v1",
        base + "/v1/",
    ]
    messages: List[str] = []
    for u in candidates:
        body, headers, err = _http_get(u)
        if err:
            messages.append(err)
            continue
        # Accept if we see chain id in headers or body
        if "x-aptos-chain-id" in headers or (isinstance(body, dict) and "chain_id" in body):
            return body, headers, []
        # Some deployments return useful headers only from "/"; continue trying
        messages.append(f"No ledger info at {u} (no chain id in headers/body)")
    return None, {}, messages


def _parse_chain_id(body: Optional[Dict], headers: Dict[str, str]) -> Optional[int]:
    if "x-aptos-chain-id" in headers:
        try:
            return int(headers["x-aptos-chain-id"])  # already decimal
        except Exception:
            pass
    if body and isinstance(body, dict) and "chain_id" in body:
        try:
            return int(body["chain_id"])  # e.g. 1, 2, ...
        except Exception:
            pass
    return None


def _parse_client_version(body: Optional[Dict], headers: Dict[str, str]) -> Optional[str]:
    # Prefer explicit version if provided, otherwise git hash
    for hk in ("x-aptos-node-version", "x-aptos-git-hash"):
        if hk in headers and headers[hk]:
            return headers[hk]
    if body and isinstance(body, dict):
        for bk in ("node_version", "git_hash"):
            v = body.get(bk)
            if v:
                return str(v)
    return None


def _get_network_name(chain_id: Optional[int]) -> Optional[str]:
    if chain_id is not None:
        if chain_id == 1:
            return "mainnet"
        if chain_id == 2:
            return "testnet"
    return None


class AptosCollector(BaseCollector):
    NAME = "aptos"
    VERSION = APTOS_COLLECTOR_VERSION

    def collect(self) -> CollectResult:
        messages: List[str] = []

        rpc_url = os.environ.get(RPC_ENV, DEFAULT_RPC)

        body, headers, errs = _probe_ledger(rpc_url)
        messages.extend(errs)

        chain_id = _parse_chain_id(body, headers)
        if chain_id is None:
            messages.append("Unable to determine chain_id from REST headers/body.")

        client_version = _parse_client_version(body, headers) or "unknown"
        if client_version == "unknown":
            messages.append("Client version not exposed (no node_version/git_hash headers).")

        network_name = _get_network_name(chain_id) or "unknown"
        if network_name == "unknown":
            messages.append("Unable to determine network name.")

        workload: Dict = {
            "client_name": "aptos-node",
            "client_version": client_version,
            "rpc_url": rpc_url,
        }
        blockchain: Dict = {
            "blockchain_ecosystem": "Aptos",
            "blockchain_network_name": network_name,
        }
        if chain_id is not None:
            blockchain["chain_id"] = chain_id

        # Decide status
        have_any_info = any([chain_id is not None, client_version != "unknown", network_name != "unknown"])
        workload_complete = True  # schema only requires client_name
        blockchain_complete = network_name != "unknown"

        if not have_any_info:
            raise CollectorFailedError("; ".join(messages) or "no REST info from node")

        if not (workload_complete and blockchain_complete):
            partial = CollectResult(blockchain=blockchain, workload=workload)
            raise CollectorPartialError(messages or ["Partial data only."], partial=partial)

        return CollectResult(blockchain=blockchain, workload=workload)

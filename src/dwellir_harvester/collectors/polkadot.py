from __future__ import annotations
import os
import subprocess
import shutil
from typing import Dict, Optional, List

from ..core import CollectResult, CollectorPartialError, CollectorFailedError
from ..rpc_substrate import (
    rpc_get_system_version,
    rpc_get_system_name,
    rpc_get_system_chain,
    rpc_get_genesis_hash
)
from ..collector_base import CollectorBase

DEFAULT_RPC_URL = "http://127.0.0.1:9944"

# RPC functions are now imported from rpc_substrate

class PolkadotCollector(CollectorBase):
    NAME = "polkadot"
    VERSION = "0.0.1"
    
    def collect(self) -> CollectResult:
        messages: List[str] = []
        client_name = None
        client_version_cli = None
        binary_path = None

        workload: Dict = {
            "client_name": client_name,
            "client_version": client_version_cli
        }
        blockchain: Dict = {
            "blockchain_ecosystem": "Polkadot",
            "blockchain_network_name": None
        }

        # Check SNAP path first (if running as a snap)
        snap_path = os.environ.get('SNAP', '')
        if snap_path:
            snap_binary = os.path.join(snap_path, 'usr', 'local', 'bin', 'polkadot')
            if os.path.isfile(snap_binary) and os.access(snap_binary, os.X_OK):
                binary_path = snap_binary
                client_name = "polkadot"
                workload["client_name"] = client_name        
        # Check system PATH for 'polkadot' or 'polkadot.polkadot-cli' if not found in SNAP
        if binary_path is None:
            # Try 'polkadot' first
            system_binary = shutil.which('polkadot')
            if system_binary:
                binary_path = system_binary
                client_name = "polkadot"
                workload["client_name"] = client_name
            else:
                # Try 'polkadot.polkadot-cli' if 'polkadot' not found
                system_binary = shutil.which('polkadot.polkadot-cli')
                if system_binary:
                    binary_path = system_binary
                    client_name = "polkadot.polkadot-cli"
                    workload["client_name"] = client_name
                else:
                    messages.append("Could not find polkadot, polkadot.polkadot-cli in SNAP path or system PATH, did you connect the snaps?")
        try:
            proc = subprocess.run([binary_path, "--version"], capture_output=True, text=True, check=True)
            vline = (proc.stdout or "").strip().splitlines()
            client_version_cli = vline[0] if vline else None
            if not client_version_cli:
                messages.append(f"{binary_path} --version returned no output")
            else:
                workload["client_version"] = client_version_cli
        except Exception as e:
            messages.append(f"{binary_path} --version failed: {e!r}")

        # Collect data from the node using the RPC endpoint from environment variable or default
        rpc_url = os.environ.get("RPC_ENV", DEFAULT_RPC_URL)

        system_version, err_ver = _get_system_version(rpc_url)
        if system_version is None:
            messages.append(err_ver or "RPC system_version unavailable at {rpc_url}")
        else:
            blockchain["system_version_from_rpc"] = system_version

        system_chain, err_chain = _get_system_chain(rpc_url)
        if system_chain is None:
            messages.append(err_chain or "RPC system_chain unavailable at {rpc_url}")
        else:
            blockchain["blockchain_network_name"] = system_chain

        genesis_hash, err_gen = _get_genesis_hash(rpc_url)
        if genesis_hash is None:
            messages.append(err_gen or "RPC chain_getBlockHash(0) unavailable at {rpc_url}")
        else:
            blockchain["chain_id"] = genesis_hash

        # Determine the completeness of the data and raise appropriate errors
        have_any_info = any([system_version, system_chain, genesis_hash, 
                            client_name, client_version_cli])
        workload_complete = bool(system_version) and bool(client_name) and bool(client_version_cli)
        blockchain_complete = bool(system_chain)

        if not have_any_info:
            raise CollectorFailedError("; ".join(messages) or "no RPC info from node")

        if not (workload_complete and blockchain_complete):
            partial = CollectResult(blockchain=blockchain, workload=workload)
            if not bool(client_version_cli):
                messages.append("Missing client_version (RPC system_version failed).")
            if not bool(client_name):
                messages.append("Missing client_name (RPC system_name failed and no override provided).")
            if not blockchain_complete:
                messages.append("Missing blockchain_network_name (RPC system_chain failed).")
            raise CollectorPartialError(messages or ["Partial data only."], partial=partial)

        return CollectResult(blockchain=blockchain, workload=workload)

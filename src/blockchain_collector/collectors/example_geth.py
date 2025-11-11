
from __future__ import annotations
import subprocess
import json
from typing import Dict
from ..core import BaseCollector, CollectResult, CollectorFailedError

class ExampleGethCollector(BaseCollector):
    """
    Example collector demonstrating how to populate the schema for a local geth node.

    Strategy (replace as needed):
    - Call `geth version` for client version.
    - Read static config or query local JSON-RPC for chainid & network (if available).
    """
    NAME = "example_geth"
    VERSION = "0.1.0"

    def collect(self) -> CollectResult:
        # Get client version
        try:
            proc = subprocess.run(["geth", "version"], capture_output=True, text=True, check=True)
            client_version = proc.stdout.strip().splitlines()[0]
        except Exception as e:
            raise CollectorFailedError([f"Could not run 'geth version': {e}"])

        # Minimal illustrative data — replace with real RPC/config reads in your environment
        blockchain: Dict = {
            "blockchain_ecosystem": "Ethereum",
            "blockchain_network_name": "mainnet",
            "chain_id": 1,
        }
        workload: Dict = {
            "client_name": "geth",
            "client_version": client_version,
        }
        return CollectResult(blockchain=blockchain, workload=workload)

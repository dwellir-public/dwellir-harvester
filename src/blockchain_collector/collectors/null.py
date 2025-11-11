from __future__ import annotations
from typing import Dict
from ..core import BaseCollector, CollectResult

class NullCollector(BaseCollector):
    """
    No-op collector that emits static, schema-valid metadata.
    Useful as a safe default when no local client is available.
    """
    NAME = "null"
    VERSION = "1.0.0"

    def collect(self) -> CollectResult:
        blockchain: Dict = {
            "blockchain_ecosystem": "Unknown",
            "blockchain_network_name": "unknown",
            "chain_id": -1,  # sentinel for "unknown"
        }
        workload: Dict = {
            "client_name": "null",
            "client_version": self.VERSION,
            "notes": "static placeholder produced by NullCollector",
        }
        return CollectResult(blockchain=blockchain, workload=workload)

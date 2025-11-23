"""Collectors for gathering node metadata.

This package provides base classes for creating collectors and specific collector
implementations for different blockchain clients and system information.
"""
# Base classes
from .collector_base import (
    BlockchainCollector,
    GenericCollector,
    CollectorError
)

# Re-export collectors so the framework can discover them by import.
from .null import NullCollector
from .reth import RethCollector
from .reth_op import OpRethCollector
from .reth_bera import BeraRethCollector
from .substrate import SubstrateCollector
from .substrate_ajuna import AjunaCollector
from .polkadot import PolkadotCollector
from .dummychain import DummychainCollector
from .host import HostCollector

# What this package exports
__all__ = [
    # Base classes
    "BlockchainCollector",
    "GenericCollector",
    "CollectorError",
    
    # Concrete collectors
    "NullCollector",
    "RethCollector",
    "OpRethCollector",
    "BeraRethCollector",
    "SubstrateCollector",
    "AjunaCollector",
    "DummychainCollector",
    "PolkadotCollector",
    "HostCollector"
]

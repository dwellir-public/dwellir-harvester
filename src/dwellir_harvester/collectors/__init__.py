"""Collectors for gathering node metadata.

This package provides base classes for creating collectors and specific collector
implementations for different blockchain clients and system information.
"""
# Base classes
from ..collector_base import (
    BlockchainCollector,
    GenericCollector,
    CollectorError
)

# Re-export collectors so the framework can discover them by import.
from .null import NullCollector
from .dummychain import DummychainCollector
from .host import HostCollector
# from .substrate import SubstrateCollector

# What this package exports
__all__ = [
    # Base classes
    "BlockchainCollector",
    "GenericCollector",
    "CollectorError",
    
    # Concrete collectors
    "NullCollector",
    "DummychainCollector",
#    "PolkadotCollector",
    "HostCollector"
]

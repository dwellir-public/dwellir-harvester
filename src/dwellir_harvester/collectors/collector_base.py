"""Base classes for collectors."""
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Type, TypeVar, Generic, List

T = TypeVar('T')


class CollectorError(Exception):
    """Base exception for collector errors."""
    pass


class CollectorBase(ABC):
    """Base class for all collectors."""
    
    # These should be overridden by subclasses
    COLLECTOR_TYPE: str
    NAME: str
    VERSION: str = "0.0.0"
    
    def __init__(self):
        if not hasattr(self, 'COLLECTOR_TYPE') or not self.COLLECTOR_TYPE:
            raise NotImplementedError("Subclasses must define COLLECTOR_TYPE")
        if not hasattr(self, 'NAME') or not self.NAME:
            raise NotImplementedError("Subclasses must define NAME")
    
    def _get_metadata(self) -> Dict[str, Any]:
        """Get the standard metadata for this collector."""
        return {
            "collector_type": self.COLLECTOR_TYPE,
            "collector_name": self.NAME,
            "collector_version": self.VERSION,
            "collection_time": datetime.now(timezone.utc).isoformat()
        }
    
    @abstractmethod
    def collect(self) -> Dict[str, Any]:
        """Collect and return data.
        
        Returns:
            Dict containing the collected data.
        """
        return {}


class BlockchainCollector(CollectorBase):
    """Base class for blockchain collectors."""
    
    COLLECTOR_TYPE = "blockchain"
    
    def __init__(self, rpc_url: Optional[str] = None):
        """Initialize the blockchain collector.
        
        Args:
            rpc_url: Optional RPC URL for the blockchain node.
        """
        super().__init__()
        self.rpc_url = rpc_url
    
    def collect(self) -> Dict[str, Any]:
        """Collect blockchain data.
        
        Returns:
            Dict with 'metadata' and 'data' keys. The 'data' dict must contain
            'blockchain' and 'client' keys with appropriate data.
        """
        data = super().collect()
        return {
            "metadata": self._get_metadata(),
            "data": data
        }



class GenericCollector(CollectorBase):
    """Base class for generic collectors with no specific schema."""
    
    COLLECTOR_TYPE = "generic"
    
    def collect(self) -> Dict[str, Any]:
        """Collect arbitrary data.
        
        Returns:
            Dict with 'metadata' and 'data' keys. The 'data' dict can contain
            any key-value pairs.
        """
        data = super().collect()
        return {
            "metadata": self._get_metadata(),
            "data": data
        }

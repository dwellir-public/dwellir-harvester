"""Shared type and exception definitions for the harvester."""
from dataclasses import dataclass, field
import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, TypeVar, Generic

class CollectorError(Exception):
    """Base exception for collector errors."""
    pass

class CollectorFailedError(CollectorError):
    """Raised when a collector fails completely."""
    pass

class CollectorPartialError(CollectorError):
    """Raised when a collector partially succeeds."""
    def __init__(self, messages: List[str], partial: Optional[Dict[str, Any]] = None):
        self.messages = messages
        self.partial = partial
        super().__init__("; ".join(messages))

T = TypeVar('T')

@dataclass
class CollectorMetadata:
    """Metadata about a collector run."""
    collector_name: str
    collector_version: str
    collection_time: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    collector_type: str = "generic"
    status: str = "success"
    errors: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Convert metadata to a dictionary."""
        return {
            "collector_name": self.collector_name,
            "collector_version": self.collector_version,
            "collection_time": self.collection_time,  # This is already an ISO format string
            "collector_type": self.collector_type,
            "status": self.status,
            "errors": self.errors
        }

@dataclass
class CollectResult(Generic[T]):
    """Result of a collector run."""
    metadata: CollectorMetadata
    data: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def create(
        cls,
        collector_name: str,
        collector_version: str,
        data: Optional[Dict[str, Any]] = None,
        errors: Optional[List[str]] = None
    ) -> 'CollectResult':
        """Create a new CollectResult with proper metadata."""
        metadata = CollectorMetadata(
            collector_name=collector_name,
            collector_version=collector_version,
            status="partial" if errors else "success",
            errors=errors or []
        )
        return cls(metadata=metadata, data=data or {})

    def to_dict(self) -> Dict[str, Any]:
        """Convert the CollectResult to a dictionary.
        
        Returns:
            A dictionary representation of the CollectResult that is JSON-serializable.
        """
        # Create a deep copy of the data to avoid modifying the original
        data = json.loads(json.dumps(self.data, default=str))
        
        return {
            "metadata": {
                "collector_name": str(self.metadata.collector_name),
                "collector_version": str(self.metadata.collector_version),
                "collection_time": str(self.metadata.collection_time),
                "collector_type": str(self.metadata.collector_type),
                "status": str(self.metadata.status),
                "errors": [str(error) for error in self.metadata.errors]
            },
            "data": data
        }
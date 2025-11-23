from datetime import datetime, timezone
from typing import Dict, Any
from .collector_base import GenericCollector

class NullCollector(GenericCollector):
    """
    A generic collector that returns a simple data structure.
    Useful as a template for new collectors or when you need a no-op collector.
    """
    NAME = "null"
    VERSION = "1.0.0"
    COLLECTOR_TYPE = "generic"

    @classmethod
    def create(cls, *args, **kwargs) -> 'NullCollector':
        """Factory method to create a new instance."""
        return cls(*args, **kwargs)

    def collect(self) -> Dict[str, Any]:
        """
        Collect and return data in the new schema format.

        Returns:
            Dictionary with the collected data in the new schema format.
        """
        collection_time = datetime.now(timezone.utc).isoformat()

        return {
            "meta": {
                "collector_type": self.COLLECTOR_TYPE,
                "collector_name": self.NAME,
                "collector_version": self.VERSION,
                "collection_time": collection_time
            },
            "data": {
                "foo": "bar",
                "number": 42
            },
            "message": "This is a message from the null GenericCollector"
        }
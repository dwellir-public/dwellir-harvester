"""Base classes for collectors."""
import importlib
import sys
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple, Type, TypeVar, Union, Generic

from ..types import CollectResult, CollectorMetadata, CollectorError, CollectorFailedError, CollectorPartialError

T = TypeVar('T')




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
    
    def _get_metadata(self) -> CollectorMetadata:
        """Get the standard metadata for this collector."""
        return CollectorMetadata(
            collector_name=self.NAME,
            collector_version=self.VERSION,
            collector_type=self.COLLECTOR_TYPE
        )
    
    @abstractmethod
    def collect(self) -> Dict[str, Any]:
        """Collect and return data.
        
        Returns:
            Dict containing the collected data.
        """
        return {}
        
    def run(self, debug: bool = False) -> Dict[str, Any]:
        """Run the collector and return its result with metadata.
        
        Args:
            debug: If True, include detailed error information in the output.
        
        Returns:
            Dict containing 'meta' and 'data' keys with the collected data.
        """
        collection_start = datetime.now(timezone.utc)
        debug_info = {}
        
        if debug:
            print(f"[DEBUG] Starting collector: {self.NAME} (version: {self.VERSION})", file=sys.stderr)
            debug_info.update({
                "start_time": collection_start.isoformat(),
                "python_version": sys.version,
                "platform": sys.platform,
                "executable": sys.executable,
                "collector_module": self.__class__.__module__
            })
        
        try:
            if debug:
                print(f"[DEBUG] Collecting data with {self.NAME}...", file=sys.stderr)
            
            # Run the collector
            result = self.collect()
            
            if debug:
                print(f"[DEBUG] {self.NAME} collection completed successfully", file=sys.stderr)
            
            # If the collector didn't return a CollectResult, wrap it
            if not isinstance(result, CollectResult):
                if debug:
                    print(f"[DEBUG] Wrapping raw result in CollectResult", file=sys.stderr)
                result = CollectResult.create(
                    collector_name=self.NAME,
                    collector_version=self.VERSION,
                    data=result
                )
            
            # Convert to dict
            result_dict = result.to_dict()
            
            # Ensure the result has the correct structure
            if "meta" not in result_dict or "data" not in result_dict:
                if debug:
                    print(f"[DEBUG] Restructuring result to standard format", file=sys.stderr)
                result_dict = {
                    "meta": {
                        "collector_type": result_dict.get("metadata", {}).get("collector_type", self.COLLECTOR_TYPE),
                        "collector_name": result_dict.get("metadata", {}).get("collector_name", self.NAME),
                        "collector_version": result_dict.get("metadata", {}).get("collector_version", self.VERSION),
                        "collection_time": result_dict.get("metadata", {}).get("collection_time", 
                            datetime.now(timezone.utc).isoformat())
                    },
                    "data": result_dict.get("data", {})
                }
                
            # Add debug information if enabled
            if debug:
                debug_info["end_time"] = datetime.now(timezone.utc).isoformat()
                debug_info["duration_seconds"] = (datetime.now(timezone.utc) - collection_start).total_seconds()
                debug_info["result_structure"] = {
                    "has_meta": "meta" in result_dict,
                    "has_data": "data" in result_dict,
                    "data_keys": list(result_dict.get("data", {}).keys()) if isinstance(result_dict.get("data"), dict) else []
                }
                result_dict["meta"]["debug"] = debug_info
                print(f"[DEBUG] Collector {self.NAME} completed in {debug_info['duration_seconds']:.2f} seconds", file=sys.stderr)
                
            return result_dict
            
        except CollectorPartialError as e:
            # Handle partial results
            result = e.partial or {}
            error_info = {
                "messages": e.messages,
                "type": "CollectorPartialError"
            }
            if debug:
                error_info["traceback"] = traceback.format_exc()
                
            return {
                "meta": {
                    "collector_type": result.get("metadata", {}).get("collector_type", self.COLLECTOR_TYPE),
                    "collector_name": result.get("metadata", {}).get("collector_name", self.NAME),
                    "collector_version": result.get("metadata", {}).get("collector_version", self.VERSION),
                    "collection_time": result.get("metadata", {}).get("collection_time", 
                        datetime.now(timezone.utc).isoformat()),
                    "status": "partial",
                    "errors": e.messages,
                    "debug": error_info if debug else None
                },
                "data": result.get("data", {})
            }
            
        except Exception as e:
            error_msg = str(e)
            print(f"Error in collector {self.NAME}: {error_msg}", file=sys.stderr)
            
            error_info = {
                "message": error_msg,
                "type": type(e).__name__,
                "args": getattr(e, 'args', [])
            }
            if debug:
                error_info["traceback"] = traceback.format_exc()
            
            # Create a failed result
            return {
                "meta": {
                    "collector_type": self.COLLECTOR_TYPE,
                    "collector_name": self.NAME,
                    "collector_version": self.VERSION,
                    "collection_time": datetime.now(timezone.utc).isoformat(),
                    "status": "failed",
                    "errors": [error_msg],
                    "debug": error_info if debug else None
                },
                "data": {}
            }


# In collector_base.py, update the BlockchainCollector class

# In collector_base.py, update the BlockchainCollector class

class BlockchainCollector(CollectorBase):
    """Base class for blockchain collectors."""
    
    COLLECTOR_TYPE = "blockchain"
    
    # Define required fields that must be present in the blockchain data
    REQUIRED_FIELDS = {
        "blockchain_ecosystem": (str,),
        "blockchain_network_name": (str,),
        "chain_id": (str, int, type(None)),  # Can be string, int, or None
        "client_name": (str,),
        "client_version": (str, type(None))  # Can be string or None
    }
    
    def __init__(self, rpc_url: Optional[str] = None):
        """Initialize the blockchain collector.
        
        Args:
            rpc_url: Optional RPC URL for the blockchain node.
        """
        super().__init__()
        self.rpc_url = rpc_url
    
    def _validate_blockchain_data(self, data: Dict[str, Any]) -> None:
        """Validate that the blockchain data contains all required fields.
        
        Args:
            data: The blockchain data to validate.
            
        Raises:
            CollectorError: If any required fields are missing or have incorrect types.
        """
        if "blockchain" not in data:
            raise CollectorError("Missing 'blockchain' key in collector data")
            
        blockchain_data = data["blockchain"]
        missing_fields = []
        type_errors = []
        
        for field, expected_types in self.REQUIRED_FIELDS.items():
            if field not in blockchain_data:
                missing_fields.append(field)
                continue
                
            value = blockchain_data[field]
            if value is not None and not any(isinstance(value, t) for t in expected_types):
                expected_type_names = [t.__name__ for t in expected_types if t is not type(None)]
                if None in expected_types:
                    expected_type_names.append("None")
                type_errors.append(
                    f"Field '{field}' has type {type(value).__name__}, "
                    f"expected {' or '.join(expected_type_names)}"
                )
        
        errors = []
        if missing_fields:
            errors.append(f"Missing required fields: {', '.join(missing_fields)}")
        if type_errors:
            errors.extend(type_errors)
            
        if errors:
            raise CollectorError("; ".join(errors))
    
    def collect(self) -> Dict[str, Any]:
        """Collect blockchain data.
        
        Returns:
            Dict with 'metadata' and 'data' keys. The 'data' dict must contain
            'blockchain' and 'client' keys with appropriate data.
            
        Note:
            Subclasses should implement their own collection logic and call
            super().collect() to include the metadata.
        """
        # This is the base implementation that subclasses should extend
        data = {
            "blockchain": {
                # These should be overridden by subclasses
                "blockchain_ecosystem": None,
                "blockchain_network_name": None,
                "chain_id": None,
                "client_name": None,
                "client_version": None
            }
        }
        
        # Validate the collected data
        self._validate_blockchain_data(data)
        
        # Convert metadata to dict before returning
        metadata = self._get_metadata()
        if hasattr(metadata, 'to_dict'):
            metadata = metadata.to_dict()
        
        return {
            "metadata": metadata,
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

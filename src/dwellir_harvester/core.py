
from __future__ import annotations
import importlib
import json
import platform
import socket
import sys
import time
import pkgutil
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any, TypedDict, Union, Type, ClassVar

# Try to import optional dependencies
try:
    import jsonschema  # type: ignore
except ImportError:
    jsonschema = None

try:
    import distro
    HAS_DISTRO = True
except ImportError:
    HAS_DISTRO = False

class CollectorFailedError(Exception):
    pass

class CollectorPartialError(Exception):
    def __init__(self, messages: List[str], partial: Optional["CollectResult"]=None):
        self.messages = messages
        self.partial = partial
        super().__init__("; ".join(messages))


class CollectorData(TypedDict, total=False):
    """Base type for collector-specific data."""
    pass

class BlockchainData(CollectorData, total=False):
    """Data specific to blockchain collectors."""
    blockchain_ecosystem: str
    blockchain_network_name: str
    chain_id: Union[str, int, None]
    client_name: str
    client_version: str
    systemd_status: Optional[Dict[str, Any]]

@dataclass
class CollectorMetadata:
    """Metadata about a collector run."""
    collector_name: str
    collector_version: str
    collection_time: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    status: str = "success"
    errors: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Convert metadata to a dictionary."""
        return {
            "collector_name": self.collector_name,
            "collector_version": self.collector_version,
            "collection_time": self.collection_time,
            "status": self.status,
            "errors": self.errors
        }

@dataclass
class CollectResult:
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
        status = "failed" if (errors and len(errors) > 0) else "success"
        metadata = CollectorMetadata(
            collector_name=collector_name,
            collector_version=collector_version,
            status=status,
            errors=errors or []
        )
        return cls(metadata=metadata, data=data or {})

    def to_dict(self) -> Dict[str, Any]:
        """Convert the CollectResult to a dictionary."""
        return {
            "metadata": self.metadata.to_dict(),
            "data": self.data
        }

# Base collector class has been moved to collectors.collector_base.CollectorBase

def now_iso_tz() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")

def validate_output(instance: Dict, schema_path: str) -> None:
    if jsonschema is None:
        return
    with open(schema_path, "r", encoding="utf-8") as f:
        schema = json.load(f)
    jsonschema.validate(instance=instance, schema=schema)

def bundled_schema_path() -> str:
    import importlib.resources as ir
    with ir.as_file(ir.files(__package__) / "data" / "blockchain_node_metadata.schema.json") as p:
        return str(p)

def load_collectors():
    try:
        from . import collectors
    except ImportError:
        # This handles the case when running as a script
        import sys
        from pathlib import Path
        sys.path.append(str(Path(__file__).parent.parent))

        import dwellir_harvester.collectors as collectors
    
    from .collectors.collector_base import CollectorBase
    
    mapping = {}
    for _, module_name, _ in pkgutil.iter_modules(collectors.__path__):
        mod = importlib.import_module(f"{collectors.__name__}.{module_name}")
        names = getattr(mod, "__all__", [])
        if not names:
            for attr in dir(mod):
                obj = getattr(mod, attr)
                try:
                    if (isinstance(obj, type) and 
                        issubclass(obj, CollectorBase) and 
                        obj is not CollectorBase):
                        mapping[obj.NAME] = obj
                except (TypeError, AttributeError):
                    continue
        else:
            for attr in names:
                obj = getattr(mod, attr)
                if (isinstance(obj, type) and 
                    issubclass(obj, CollectorBase) and 
                    obj is not CollectorBase):
                    mapping[obj.NAME] = obj
    return mapping

def collect_system_info() -> Dict[str, Any]:
    """Collect system information."""
    system_info: Dict[str, Any] = {
        "hostname": socket.gethostname(),
        "kernel": {
            "release": platform.release(),
            "version": platform.version()
        },
        "uptime": time.monotonic()
    }
    
    # Add LSB information if available
    if HAS_DISTRO:
        system_info["lsb"] = {
            "id": distro.id(),
            "release": distro.version(),
            "codename": distro.codename(),
            "description": distro.name(pretty=True)
        }
    
    return system_info

def run_collector(collector_name: str, schema_path: str = None) -> Dict[str, Any]:
    """Run a single collector and return its result.
    
    Args:
        collector_name: Name of the collector to run
        schema_path: Optional path to the JSON schema file for validation
        
    Returns:
        Dict containing the collector's result with 'meta' and 'data' keys
    """
    try:
        collectors = load_collectors()
        if collector_name not in collectors:
            raise CollectorFailedError(f"Unknown collector: {collector_name}")

        CollectorCls = collectors[collector_name]
        collector = CollectorCls.create()
        
        # Run the collector
        result = collector.collect()
        
        # If the collector didn't return a CollectResult, wrap it
        if not isinstance(result, CollectResult):
            result = CollectResult.create(
                collector_name=collector_name,
                collector_version=getattr(CollectorCls, "VERSION", "0.0.0"),
                data=result
            )
        
        # Convert to dict
        result_dict = result.to_dict()
        
        # For the host collector, just return the data as is
        if collector_name == "host":
            return {
                "meta": {
                    "collector_type": "host",
                    "collector_name": collector_name,
                    "collector_version": getattr(CollectorCls, "VERSION", "0.0.0"),
                    "collection_time": now_iso_tz()
                },
                "data": result_dict.get("data", {})
            }
        
        # For other collectors, ensure they have the correct structure
        if "meta" not in result_dict or "data" not in result_dict:
            result_dict = {
                "meta": {
                    "collector_type": result_dict.get("metadata", {}).get("collector_type", "generic"),
                    "collector_name": result_dict.get("metadata", {}).get("collector_name", collector_name),
                    "collector_version": result_dict.get("metadata", {}).get("collector_version", getattr(CollectorCls, "VERSION", "0.0.0")),
                    "collection_time": result_dict.get("metadata", {}).get("collection_time", now_iso_tz())
                },
                "data": result_dict.get("data", {})
            }
            
        # Add message if present
        if "message" in result_dict:
            result_dict["message"] = result_dict["message"]
            
        return result_dict
        
    except Exception as e:
        error_msg = str(e)
        print(f"Error in collector {collector_name}: {error_msg}", file=sys.stderr)
        
        # Create a failed result
        return {
            "meta": {
                "collector_type": "generic",
                "collector_name": collector_name,
                "collector_version": getattr(CollectorCls, "VERSION", "0.0.0"),
                "collection_time": now_iso_tz(),
                "status": "failed",
                "errors": [error_msg]
            },
            "data": {}
        }
        
    except CollectorPartialError as e:
        # Handle partial results
        result = e.partial or {}
        return {
            "meta": {
                "collector_type": result.get("metadata", {}).get("collector_type", "generic"),
                "collector_name": result.get("metadata", {}).get("collector_name", collector_name),
                "collector_version": result.get("metadata", {}).get("collector_version", getattr(CollectorCls, "VERSION", "0.0.0")),
                "collection_time": result.get("metadata", {}).get("collection_time", now_iso_tz()),
                "status": "partial",
                "errors": e.messages
            },
            "data": result.get("data", {})
        }

def collect_all(collector_names: List[str], schema_path: str, validate: bool = True) -> Dict[str, Any]:
    """Run multiple collectors and merge their results.
    
    Args:
        collector_names: List of collector names to run
        schema_path: Path to the JSON schema file for validation
        
    Returns:
        Dict containing the collected data in the format:
        {
            "harvester": { ... },
            "system": { ... },
            "collectors": {
                "collector_name": {
                    "meta": { ... },
                    "data": { ... },
                    "message": "..."  # Optional
                },
                ...
            }
        }
    """
    collection_time = now_iso_tz()
    
    # Initialize the result structure
    result = {
        "harvester": {
            "harvester-version": "1.0.0",
            "collection_time": collection_time,
            "collectors_used": collector_names.copy()  # Make a copy to avoid modifying the input
        },
        "host": {},
        "collectors": {}
    }
    
    # Run all collectors, including host
    for name in collector_names:
        try:
            collector_result = run_collector(name, schema_path)
            
            # Handle the collector result
            collector_data = {
                "meta": collector_result.get("meta", {
                    "collector_type": collector_result.get("metadata", {}).get("collector_type", "generic"),
                    "collector_name": collector_result.get("metadata", {}).get("collector_name", name),
                    "collector_version": collector_result.get("metadata", {}).get("collector_version", "0.0.0"),
                    "collection_time": collector_result.get("metadata", {}).get("collection_time", collection_time)
                }),
                "data": collector_result.get("data", {})
            }
            
            # Add message if present
            if "message" in collector_result:
                collector_data["message"] = collector_result["message"]
                
            # Special case: host collector goes to the top level
            if name == "host":
                result["host"] = collector_data["data"]
            else:
                result["collectors"][name] = collector_data
                    
        except Exception as e:
            print(f"Warning: Failed to run collector {name}: {e}", file=sys.stderr)
            result["collectors"][name] = {
                "meta": {
                    "collector_type": "generic",
                    "collector_name": name,
                    "collector_version": "0.0.0",
                    "collection_time": collection_time
                },
                "data": {},
                "message": f"Collector failed: {str(e)}"
            }
    
    # Validate the final merged result if requested
    if validate and jsonschema:
        validate_output(result, schema_path)
    
    return result

from __future__ import annotations
import importlib
import json
import platform
from . import __version__
import socket
import time
import sys
import pkgutil
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any, TypedDict, Union

# Import types and exceptions
from .collector_base import CollectResult, CollectorMetadata, CollectorError, CollectorFailedError, CollectorPartialError

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
    
    from .collector_base import CollectorBase
    
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

def run_collector(collector_name: str, schema_path: str = None, debug: bool = False) -> Dict[str, Any]:
    """Run a single collector and return its result.
    
    Args:
        collector_name: Name of the collector to run
        schema_path: Optional path to the JSON schema file for validation
        debug: If True, include detailed debug information in the output
        
    Returns:
        Dict containing the collector's result with 'meta' and 'data' keys
    """
    try:
        collectors = load_collectors()
        if collector_name not in collectors:
            error_msg = f"Unknown collector: {collector_name}"
            if debug:
                error_msg += f"\nAvailable collectors: {', '.join(collectors.keys())}"
            raise CollectorFailedError(error_msg)

        CollectorCls = collectors[collector_name]
        
        try:
            collector = CollectorCls.create()
        except Exception as e:
            if debug:
                import traceback
                raise CollectorFailedError(
                    f"Failed to create collector {collector_name}: {str(e)}\n"
                    f"Traceback:\n{traceback.format_exc()}"
                ) from e
            raise CollectorFailedError(f"Failed to create collector {collector_name}: {str(e)}")
        
        try:
            # Run the collector with debug flag
            result = collector.run(debug=debug)
            
            # If the result is a CollectResult instance, convert it to dict
            if hasattr(result, 'to_dict'):
                result = result.to_dict()
            # If the result has a 'metadata' key that's an object with to_dict
            elif isinstance(result, dict) and hasattr(result.get('metadata'), 'to_dict'):
                result['metadata'] = result['metadata'].to_dict()
                
        except Exception as e:
            if debug:
                import traceback
                raise CollectorFailedError(
                    f"Error in collector {collector_name}: {str(e)}\n"
                    f"Traceback:\n{traceback.format_exc()}"
                ) from e
            raise
        
        # For the host collector, ensure it has the correct structure
        if collector_name == "host":
            return CollectResult(
            metadata=CollectorMetadata(
                collector_name=collector_name,
                collector_version=getattr(CollectorCls, "VERSION", "0.0.0"),
                collector_type="host",
                status=result.get("meta", {}).get("status", "success"),
                errors=result.get("meta", {}).get("errors", [])
            ),
            data=result.get("data", {})
        ).to_dict()
        
        # Ensure the result has the expected structure
        if not isinstance(result, dict):
            result = {"data": result}
            
        if "meta" not in result:
            result["meta"] = {
                "collector_type": getattr(collector, "COLLECTOR_TYPE", "generic"),
                "collector_name": getattr(collector, "NAME", collector_name),
                "collector_version": getattr(collector, "VERSION", "0.0.0"),
                "collection_time": now_iso_tz()
            }
            
        # Add debug info if enabled
        if debug and "debug" not in result.get("meta", {}):
            import sys
            result["meta"]["debug"] = {
                "python_version": sys.version,
                "platform": sys.platform,
                "executable": sys.executable,
                "collector_module": CollectorCls.__module__
            }
        
        return result
        
    except CollectorFailedError:
        raise  # Re-raise CollectorFailedError as-is
    except Exception as e:
        error_msg = f"Unexpected error in collector {collector_name}: {str(e)}"
        if debug:
            import traceback
            error_msg += f"\nTraceback:\n{traceback.format_exc()}"
        raise CollectorFailedError(error_msg) from e

def collect_all(collector_names: List[str], schema_path: str, validate: bool = True, debug: bool = False) -> Dict[str, Any]:
    """Run multiple collectors and merge their results.
    
    Args:
        collector_names: List of collector names to run
        schema_path: Path to the JSON schema file for validation
        validate: Whether to validate the output against the schema
        debug: If True, include detailed debug information in the output
        
    Returns:
        Dict containing the collected data in the format:
        {
            "harvester": { ... },
            "system": { ... }, # special collector. Always populated.
            "host": { ... },   # special collector. Can be empty if no host collector is specified
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
            "harvester-version": __version__.__version__,
            "collection_time": collection_time,
            "collectors_used": collector_names.copy()  # Make a copy to avoid modifying the input
        },
        "host": {},
        "collectors": {}
    }
    
    # Run all collectors, including host
    for name in collector_names:
        try:
            collector_result = run_collector(name, schema_path, debug=debug)
            
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
                
            # Special handling for host collector
            # Add that to a top level result key
            if name == "host":
                result["host"] = collector_data["data"]
            else:
                result["collectors"][name] = collector_data
                
        except CollectorFailedError as e:
            if debug:
                import traceback
                result["collectors"][name] = {
                    "meta": {
                        "collector_name": name,
                        "status": "failed",
                        "collection_time": now_iso_tz(),
                        "errors": [str(e)],
                        "debug": {
                            "traceback": traceback.format_exc()
                        }
                    },
                    "data": {}
                }
            else:
                result["collectors"][name] = {
                    "meta": {
                        "collector_name": name,
                        "status": "failed",
                        "collection_time": now_iso_tz(),
                        "errors": [str(e)]
                    },
                    "data": {}
                }
    
    # Add system information
    try:
        result["system"] = collect_system_info()
    except Exception as e:
        if debug:
            import traceback
            result["system"] = {
                "error": f"Failed to collect system info: {str(e)}",
                "debug": {
                    "traceback": traceback.format_exc()
                }
            }
        else:
            result["system"] = {
                "error": f"Failed to collect system info: {str(e)}"
            }
    
    # Validate the output if requested
    if validate and schema_path:
        try:
            validate_output(result, schema_path)
        except Exception as e:
            if debug:
                import traceback
                result["harvester"]["validation_error"] = {
                    "error": str(e),
                    "traceback": traceback.format_exc()
                }
            else:
                result["harvester"]["validation_error"] = str(e)
    
    return result

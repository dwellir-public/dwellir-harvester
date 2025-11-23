"""
Module for interacting with systemd services via systemctl show command.
Provides a simple interface to retrieve service properties.
"""

import json
import subprocess
from typing import Dict, List, Optional, Set, Union


def get_service_properties(
    service_name: str,
    fields: Optional[List[str]] = None,
    output_format: str = "json"
) -> Dict[str, Union[str, int, float, bool, Dict, List]]:
    """
    Get properties for a systemd service using systemctl show.

    Args:
        service_name: Name of the systemd service (e.g., 'opgeth.service')
        fields: List of fields to include. If None, includes all fields.
        output_format: Output format ('json', 'json-pretty', 'property')

    Returns:
        Dictionary containing the requested service properties
    """
    try:
        # Build the systemctl command
        cmd = ["systemctl", "show", service_name]
        
        # Add output format
        if output_format in ("json", "json-pretty"):
            cmd.extend(["--output", "json"])
        
        # Run the command and capture output
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=True
        )
        
        # Parse the output
        if output_format in ("json", "json-pretty"):
            try:
                properties = json.loads(result.stdout)
                # Filter fields if specified
                if fields is not None:
                    return {k: v for k, v in properties.items() if k in fields}
                return properties
            except json.JSONDecodeError:
                return {"error": "Failed to parse systemctl show output as JSON"}
        else:
            # Parse property format (key=value)
            properties = {}
            for line in result.stdout.strip().split('\n'):
                if '=' in line:
                    key, value = line.split('=', 1)
                    if fields is None or key in fields:
                        properties[key] = _parse_value(value)
            return properties
            
    except subprocess.CalledProcessError as e:
        return {"error": f"systemctl command failed: {e}", "stderr": e.stderr}
    except Exception as e:
        return {"error": f"Unexpected error: {e}"}


def get_essential_service_properties(service_name: str) -> Dict[str, Union[str, int, float, bool]]:
    """
    Get essential properties for a service in a more structured format.
    
    Args:
        service_name: Name of the systemd service
        
    Returns:
        Dictionary with essential service properties
    """
    # Systemd service properties to fetch
    fields = [
        # Basic service info
        "Id", "Description", "LoadState", "ActiveState", "SubState",
        "StateChangeTimestamp", "ActiveEnterTimestamp", 
        
        # Process info
        "MainPID", "ExecMainStartTimestamp", "ExecMainStatus",
        
        # Resource usage
        "MemoryCurrent", "CPUUsageNSec", "TasksCurrent",
        
        # Restart info
        "RestartCount", "RestartUSec", "StartLimitBurst", "StartLimitIntervalUSec",
        
        # Dependencies
        "Wants", "Requires", "After", "Before",
        
        # Security
        "User", "Group", "UMask",
        
        # Paths
        "WorkingDirectory", "RootDirectory",
        
        # Resource limits (ulimit)
        "LimitCPU", "LimitCPUSoft",
        "LimitFSIZE", "LimitFSIZESoft",
        "LimitDATA", "LimitDATASoft",
        "LimitSTACK", "LimitSTACKSoft",
        "LimitCORE", "LimitCORESoft",
        "LimitRSS", "LimitRSSSoft",
        "LimitNOFILE", "LimitNOFILESoft",
        "LimitAS", "LimitASSoft",
        "LimitNPROC", "LimitNPROCSoft",
        "LimitMEMLOCK", "LimitMEMLOCKSoft",
        "LimitLOCKS", "LimitLOCKSSoft",
        "LimitSIGPENDING", "LimitSIGPENDINGSoft",
        "LimitMSGQUEUE", "LimitMSGQUEUESoft",
        "LimitNICE", "LimitNICESoft",
        "LimitRTPRIO", "LimitRTPRIOSoft",
        "LimitRTTIME", "LimitRTTIMESoft"
    ]
    
    raw_props = get_service_properties(service_name, fields=fields, output_format="property")
    
    # Process and structure the output
    result = {
        "service": {
            "id": raw_props.get("Id"),
            "description": raw_props.get("Description"),
            "state": {
                "load": raw_props.get("LoadState"),
                "active": raw_props.get("ActiveState"),
                "sub": raw_props.get("SubState"),
                "since": raw_props.get("StateChangeTimestamp"),
                "active_since": raw_props.get("ActiveEnterTimestamp")
            },
            "pid": _parse_int(raw_props.get("MainPID")),
            "started_at": raw_props.get("ExecMainStartTimestamp"),
            "exit_status": _parse_int(raw_props.get("ExecMainStatus")),
            "restart": {
                "count": _parse_int(raw_props.get("RestartCount")),
                "interval_sec": _parse_seconds(raw_props.get("RestartUSec")),
                "start_limit": {
                    "burst": _parse_int(raw_props.get("StartLimitBurst")),
                    "interval_sec": _parse_seconds(raw_props.get("StartLimitIntervalUSec"))
                }
            },
            "resources": {
                "memory_bytes": _parse_int(raw_props.get("MemoryCurrent")),
                "cpu_ns": _parse_int(raw_props.get("CPUUsageNSec")),
                "tasks": _parse_int(raw_props.get("TasksCurrent")),
            },
            "user": {
                "name": raw_props.get("User"),
                "group": raw_props.get("Group"),
                "umask": raw_props.get("UMask"),
            #    "capabilities": raw_props.get("CapabilityBoundingSet", "").split()
            },
            "paths": {
                "working_directory": raw_props.get("WorkingDirectory"),
                "root_directory": raw_props.get("RootDirectory")
            },
            "dependencies": {
                "wants": _parse_list(raw_props.get("Wants")),
                "requires": _parse_list(raw_props.get("Requires")),
                "after": _parse_list(raw_props.get("After")),
                "before": _parse_list(raw_props.get("Before"))
            },
            "limits": {
                "cpu": {
                    "hard": raw_props.get("LimitCPU"),
                    "soft": raw_props.get("LimitCPUSoft")
                },
                "file_size": {
                    "hard": raw_props.get("LimitFSIZE"),
                    "soft": raw_props.get("LimitFSIZESoft")
                },
                "data": {
                    "hard": raw_props.get("LimitDATA"),
                    "soft": raw_props.get("LimitDATASoft")
                },
                "stack": {
                    "hard": raw_props.get("LimitSTACK"),
                    "soft": raw_props.get("LimitSTACKSoft")
                },
                "core": {
                    "hard": raw_props.get("LimitCORE"),
                    "soft": raw_props.get("LimitCORESoft")
                },
                "rss": {
                    "hard": raw_props.get("LimitRSS"),
                    "soft": raw_props.get("LimitRSSSoft")
                },
                "open_files": {
                    "hard": raw_props.get("LimitNOFILE"),
                    "soft": raw_props.get("LimitNOFILESoft")
                },
                "address_space": {
                    "hard": raw_props.get("LimitAS"),
                    "soft": raw_props.get("LimitASSoft")
                },
                "processes": {
                    "hard": raw_props.get("LimitNPROC"),
                    "soft": raw_props.get("LimitNPROCSoft")
                },
                "locked_memory": {
                    "hard": raw_props.get("LimitMEMLOCK"),
                    "soft": raw_props.get("LimitMEMLOCKSoft")
                },
                "file_locks": {
                    "hard": raw_props.get("LimitLOCKS"),
                    "soft": raw_props.get("LimitLOCKSSoft")
                },
                "pending_signals": {
                    "hard": raw_props.get("LimitSIGPENDING"),
                    "soft": raw_props.get("LimitSIGPENDINGSoft")
                },
                "message_queue": {
                    "hard": raw_props.get("LimitMSGQUEUE"),
                    "soft": raw_props.get("LimitMSGQUEUESoft")
                },
                "nice": {
                    "hard": raw_props.get("LimitNICE"),
                    "soft": raw_props.get("LimitNICESoft")
                },
                "realtime_priority": {
                    "hard": raw_props.get("LimitRTPRIO"),
                    "soft": raw_props.get("LimitRTPRIOSoft")
                },
                "realtime_timeout": {
                    "hard": raw_props.get("LimitRTTIME"),
                    "soft": raw_props.get("LimitRTTIMESoft")
                }
            }
        }
    }
    
    return result


def _parse_value(value: str) -> Union[str, int, float, bool, List[str]]:
    """Parse a string value from systemctl show into appropriate Python type."""
    if value == "":
        return ""
    
    # Check for boolean values
    if value.lower() in ("yes", "no"):
        return value.lower() == "yes"
    
    # Check for numeric values
    try:
        if '.' in value:
            return float(value)
        return int(value)
    except (ValueError, TypeError):
        pass
    
    # Check for lists (comma-separated)
    if ',' in value:
        return [item.strip() for item in value.split(',') if item.strip()]
    
    return value


def _parse_int(value: Optional[str]) -> Optional[int]:
    """Safely parse an integer value from systemctl output."""
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (ValueError, TypeError):
        return None


def _parse_seconds(value: Optional[str]) -> Optional[float]:
    """Convert systemd time values to seconds."""
    if not value or value.lower() in ("n/a", ""):
        return None
    
    # Remove any non-numeric characters except for decimal point
    value = ''.join(c for c in value if c.isdigit() or c == '.')
    
    try:
        # Convert from microseconds to seconds
        return float(value) / 1_000_000
    except (ValueError, TypeError):
        return None


def _parse_list(value: Optional[Union[str, List[str]]]) -> List[str]:
    """Parse a comma-separated string into a list, handling empty/None values."""
    if not value:
        return []
    if isinstance(value, list):
        return value
    return [item.strip() for item in str(value).split(',') if item.strip()]

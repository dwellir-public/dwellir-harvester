"""
Module for interacting with systemd services via systemctl and journalctl commands.
Provides a unified interface to retrieve service properties and logs.
"""

import json
import subprocess
from typing import Dict, List, Optional, Union, Any

import logging
logger = logging.getLogger(__name__)
# Add NullHandler to prevent "No handlers could be found" warnings
logger.addHandler(logging.NullHandler())

# Systemctl functions
def get_service_properties(
    service_name: str,
    fields: Optional[List[str]] = None,
    output_format: str = "json"
) -> Dict[str, Union[str, int, float, bool, Dict, List]]:
    """
    Get properties for a systemd service using systemctl show.

    Args:
        service_name: Name of the systemd service (e.g., 'opgeth.service')
        fields: Optional list of specific properties to retrieve
        output_format: Output format ('json' or 'dict')

    Returns:
        Dictionary of service properties
    """
    cmd = ["systemctl", "show", service_name, "--no-page"]
    if fields:
        cmd.extend(["--property", ",".join(fields)])

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=True
        )
        
        # Parse the output into a dictionary
        properties = {}
        for line in result.stdout.splitlines():
            if "=" in line:
                key, value = line.split("=", 1)
                properties[key] = _parse_value(value)

        if output_format.lower() == "json":
            return json.dumps(properties, indent=2)
        return properties

    except subprocess.CalledProcessError as e:
        error_msg = f"Error getting service properties: {e.stderr}"
        if output_format.lower() == "json":
            return json.dumps({"error": error_msg}, indent=2)
        return {"error": error_msg}


def get_essential_service_properties(service_name: str) -> Dict[str, Any]:
    """
    Get essential properties for a service in a more structured format.
    
    Args:
        service_name: Name of the systemd service
        
    Returns:
        Dictionary with essential service properties
    """
    # Get all properties first
    properties = get_service_properties(service_name, output_format="dict")
    
    if isinstance(properties, dict) and "error" in properties:
        return properties
    
    # Extract and format essential properties
    essential = {
        "name": service_name,
        "active_state": properties.get("ActiveState", "unknown"),
        "sub_state": properties.get("SubState", "unknown"),
        "load_state": properties.get("LoadState", "unknown"),
        "unit_file_state": properties.get("UnitFileState", "unknown"),
        "enabled": properties.get("UnitFileState") == "enabled",
        "running": properties.get("ActiveState") == "active",
        "pid": _parse_int(properties.get("MainPID")),
        "memory_current": _parse_memory(properties.get("MemoryCurrent")),
        "memory_peak": _parse_memory(properties.get("MemoryPeak")),
        "cpu_usage_nsec": _parse_int(properties.get("CPUUsageNSec")),
        "tasks_current": _parse_int(properties.get("TasksCurrent")),
        "tasks_max": _parse_int(properties.get("TasksMax")),
        "exec_start_timestamp": properties.get("ExecMainStartTimestamp"),
        "exec_start_timestamp_monotonic": _parse_int(properties.get("ExecMainStartTimestampMonotonic")),
        "active_enter_timestamp": properties.get("ActiveEnterTimestamp"),
        "active_enter_timestamp_monotonic": _parse_int(properties.get("ActiveEnterTimestampMonotonic")),
        "inactive_exit_timestamp": properties.get("InactiveExitTimestamp"),
        "inactive_exit_timestamp_monotonic": _parse_int(properties.get("InactiveExitTimestampMonotonic")),
        "active_time": _parse_seconds(properties.get("ActiveEnterTimestampMonotonic")),
        "inactive_time": _parse_seconds(properties.get("InactiveEnterTimestampMonotonic")),
        "runtime_max_usec": _parse_seconds(properties.get("RuntimeMaxUSec")),
        "runtime_random_seed": properties.get("RuntimeRandomSeed"),
        "runtime_directory_mode": properties.get("RuntimeDirectoryMode"),
        "runtime_directory": _parse_list(properties.get("RuntimeDirectory")),
        "environment": _parse_environment(properties.get("Environment")),
        "environment_files": _parse_list(properties.get("EnvironmentFiles")),
        "umask": properties.get("UMask"),
        "limit_cpu": properties.get("LimitCPU"),
        "limit_fsize": properties.get("LimitFSIZE"),
        "limit_data": properties.get("LimitDATA"),
        "limit_stack": properties.get("LimitSTACK"),
        "limit_core": properties.get("LimitCORE"),
        "limit_rss": properties.get("LimitRSS"),
        "limit_nofile": properties.get("LimitNOFILE"),
        "limit_as": properties.get("LimitAS"),
        "limit_nproc": properties.get("LimitNPROC"),
        "limit_memlock": properties.get("LimitMEMLOCK"),
        "limit_locks": properties.get("LimitLOCKS"),
        "limit_sigpending": properties.get("LimitSIGPENDING"),
        "limit_msgqueue": properties.get("LimitMSGQUEUE"),
        "limit_nice": properties.get("LimitNICE"),
        "limit_rtprio": properties.get("LimitRTPRIO"),
        "limit_rttime": properties.get("LimitRTTIME"),
        "control_group": properties.get("ControlGroup"),
        "memory_current_human": _format_bytes(_parse_memory(properties.get("MemoryCurrent")) or 0),
        "memory_peak_human": _format_bytes(_parse_memory(properties.get("MemoryPeak")) or 0),
        "cpu_usage_percent": _calculate_cpu_percent(properties),
        "uptime": _parse_seconds(properties.get("ActiveEnterTimestampMonotonic")),
        "startup_time": properties.get("ActiveEnterTimestamp"),
        "wants": _parse_list(properties.get("Wants")),
        "wanted_by": _parse_list(properties.get("WantedBy")),
        "required_by": _parse_list(properties.get("RequiredBy")),
        "documentation": _parse_list(properties.get("Documentation")),
        "description": properties.get("Description"),
        "fragment_path": properties.get("FragmentPath"),
        "drop_in_paths": _parse_list(properties.get("DropInPaths")),
        "source_path": properties.get("SourcePath"),
        "unit_file_preset": properties.get("UnitFilePreset"),
        "state_change_timestamp": properties.get("StateChangeTimestamp"),
        "inactive_exit_timestamp": properties.get("InactiveExitTimestamp"),
        "active_enter_timestamp": properties.get("ActiveEnterTimestamp"),
        "active_exit_timestamp": properties.get("ActiveExitTimestamp"),
        "inactive_enter_timestamp": properties.get("InactiveEnterTimestamp"),
        "can_start": properties.get("CanStart") == "yes",
        "can_stop": properties.get("CanStop") == "yes",
        "can_reload": properties.get("CanReload") == "yes",
        "can_isolate": properties.get("CanIsolate") == "yes"
    }
    
    return essential


def _parse_value(value: str) -> Union[str, int, float, bool, Dict, List]:
    """Parse a string value from systemctl show into appropriate Python type."""
    if not value:
        return ""
    
    # Handle boolean values
    if value.lower() in ("true", "yes", "1"):
        return True
    if value.lower() in ("false", "no", "0"):
        return False
    
    # Handle numeric values
    if value.isdigit():
        try:
            return int(value)
        except (ValueError, TypeError):
            pass
    
    # Handle float values
    try:
        return float(value)
    except (ValueError, TypeError):
        pass
    
    # Handle JSON-like structures
    if value.startswith('{') and value.endswith('}'):
        try:
            return json.loads(value.replace("'", '"'))
        except (json.JSONDecodeError, AttributeError):
            pass
    
    # Handle lists
    if "," in value and "=" not in value:
        return [item.strip() for item in value.split(",") if item.strip()]
    
    return value


def _parse_int(value: Optional[str]) -> Optional[int]:
    """Safely parse an integer value from systemctl output."""
    if not value or value in ("(null)", ""):
        return None
    try:
        return int(value)
    except (ValueError, TypeError):
        return None


def _parse_seconds(value: Optional[str]) -> Optional[float]:
    """Convert systemd time values to seconds."""
    if not value or value in ("(null)", ""):
        return None
    
    # Handle time values like "2.123456s" or "1min 30.123456s"
    try:
        if " " in value:
            # Handle compound time values like "1min 30.123456s"
            parts = value.split()
            total_seconds = 0.0
            for part in parts:
                if part.endswith("min"):
                    total_seconds += float(part[:-3]) * 60
                elif part.endswith("s"):
                    total_seconds += float(part[:-1])
                elif part.endswith("ms"):
                    total_seconds += float(part[:-2]) / 1000
                elif part.endswith("us"):
                    total_seconds += float(part[:-2]) / 1_000_000
                elif part.endswith("ns"):
                    total_seconds += float(part[:-2]) / 1_000_000_000
                else:
                    total_seconds += float(part)
            return total_seconds
        else:
            # Handle simple time values like "2.123456s"
            if value.endswith("s"):
                return float(value[:-1])
            elif value.endswith("ms"):
                return float(value[:-2]) / 1000
            elif value.endswith("us"):
                return float(value[:-2]) / 1_000_000
            elif value.endswith("ns"):
                return float(value[:-2]) / 1_000_000_000
            else:
                return float(value)
    except (ValueError, TypeError):
        return None


def _parse_list(value: Optional[Union[str, List[str]]]) -> List[str]:
    """Parse a comma-separated string into a list, handling empty/None values."""
    if not value or value == "":
        return []
    if isinstance(value, list):
        return value
    return [item.strip() for item in value.split(",") if item.strip()]


def _parse_environment(env_str: Optional[str]) -> Dict[str, str]:
    """Parse environment variables from systemd output."""
    if not env_str:
        return {}
    
    env = {}
    for line in env_str.splitlines():
        if "=" in line:
            key, value = line.split("=", 1)
            env[key] = value
    return env


def _parse_memory(value: Optional[str]) -> Optional[int]:
    """Parse memory values from systemd output."""
    if not value or value in ("(null)", "", "infinity"):
        return None
    return _parse_int(value)


def _format_bytes(size_bytes: int) -> str:
    """Format bytes to human-readable format."""
    if not size_bytes:
        return "0 B"
    
    size_names = ("B", "KB", "MB", "GB", "TB", "PB", "EB", "ZB", "YB")
    i = 0
    size = float(size_bytes)
    
    while size >= 1024 and i < len(size_names) - 1:
        size /= 1024
        i += 1
    
    return f"{size:.2f} {size_names[i]}"


def _calculate_cpu_percent(properties: Dict[str, Any]) -> Optional[float]:
    """Calculate CPU usage percentage from systemd properties."""
    cpu_usage_nsec = _parse_int(properties.get("CPUUsageNSec"))
    active_enter_monotonic = _parse_int(properties.get("ActiveEnterTimestampMonotonic"))
    now_monotonic = _parse_int(properties.get("TimestampMonotonic"))
    
    if not all([cpu_usage_nsec, active_enter_monotonic, now_monotonic]):
        return None
    
    if now_monotonic <= active_enter_monotonic:
        return 0.0
    
    # Convert to seconds and calculate percentage
    cpu_seconds = cpu_usage_nsec / 1_000_000_000
    elapsed_seconds = (now_monotonic - active_enter_monotonic) / 1_000_000
    
    if elapsed_seconds <= 0:
        return 0.0
    
    return min(100.0, (cpu_seconds / elapsed_seconds) * 100.0)

# Journalctl functions
def get_journal_entries(
    service_name: str,
    num_entries: int = 1,
    output_format: str = "json"
) -> List[Dict[str, str]]:
    """
    Retrieve journal entries for a specified systemd service.

    Args:
        service_name: Name of the systemd service (e.g., 'snap.dummychain.daemon.service')
        num_entries: Number of log entries to retrieve (default: 1)
        output_format: Output format ('json' or 'list')

    Returns:
        List of journal entries as dictionaries
    """
    cmd = [
        "journalctl",
        "--unit", service_name,
        "--no-pager",
        "--no-hostname",
        "-n", str(num_entries),
        "-o", "json"
    ]

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=True
        )
        
        # Parse the JSON output
        if output_format.lower() == "json":
            return result.stdout.strip()
            
        # Parse and return as list of dictionaries
        entries = []
        for line in result.stdout.strip().split('\n'):
            if line.strip():
                try:
                    entries.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
        return entries

    except subprocess.CalledProcessError as e:
        error_msg = f"Error getting journal entries: {e.stderr}"
        if output_format.lower() == "json":
            return json.dumps({"error": error_msg}, indent=2)
        return [{"error": error_msg}]


def get_last_journal_message(service_name: str) -> Dict[str, str]:
    """
    Get the most recent journal message for a service with some metadata.

    Args:
        service_name: Name of the systemd service

    Returns: Dict 
        return {
        "message": entry.get("MESSAGE", ""),
        "timestamp": timestamp,
        "service": service_name,
        "priority": entry.get("PRIORITY", ""),
        "pid": entry.get("_PID", ""),
        "unit": entry.get("_SYSTEMD_UNIT", "")
    }
    """
    entries = get_journal_entries(service_name, num_entries=1, output_format="list")
    
    if not entries or not isinstance(entries, list) or "error" in entries[0]:
        return {
            "message": entries[0]["error"] if entries and "error" in entries[0] else "No journal entries found",
            "timestamp": "",
            "service": service_name
        }
    
    # Get the most recent entry
    entry = entries[0]
    
    # Format the timestamp if available
    timestamp = entry.get("__REALTIME_TIMESTAMP", "")
    logger.debug(f"Timestamp: {timestamp}")
    if timestamp and isinstance(timestamp, str) and timestamp.endswith("Z"):
        try:
            # Convert ISO 8601 format to a more readable format
            from datetime import datetime
            dt = datetime.fromisoformat(timestamp.rstrip("Z"))
            timestamp = dt.strftime("%Y-%m-%d %H:%M:%S")
        except (ValueError, TypeError):
            pass
    
    return {
        "message": entry.get("MESSAGE", ""),
        "timestamp": timestamp,
        "service": service_name,
        "priority": entry.get("PRIORITY", ""),
        "pid": entry.get("_PID", ""),
        "unit": entry.get("_SYSTEMD_UNIT", "")
    }


def get_journal_messages(service_name: str, num_entries: int = 10) -> List[Dict[str, str]]:
    """
    Get the most recent journal messages for a service.

    Args:
        service_name: Name of the systemd service
        num_entries: Number of entries to retrieve (default: 10)

    Returns:
        List of message dictionaries
    """
    entries = get_journal_entries(service_name, num_entries=num_entries, output_format="list")
    
    if not entries or not isinstance(entries, list) or (len(entries) > 0 and "error" in entries[0]):
        error_msg = entries[0]["error"] if entries and "error" in entries[0] else "No journal entries found"
        return [{"message": error_msg, "timestamp": "", "service": service_name}]
    
    messages = []
    for entry in entries:
        # Format the timestamp if available
        timestamp = entry.get("__REALTIME_TIMESTAMP", "")
        if timestamp and isinstance(timestamp, str) and timestamp.endswith("Z"):
            try:
                # Convert ISO 8601 format to a more readable format
                from datetime import datetime
                dt = datetime.fromisoformat(timestamp.rstrip("Z"))
                timestamp = dt.strftime("%Y-%m-%d %H:%M:%S")
            except (ValueError, TypeError):
                pass
        
        messages.append({
            "message": entry.get("MESSAGE", ""),
            "timestamp": timestamp,
            "service": service_name,
            "priority": entry.get("PRIORITY", ""),
            "pid": entry.get("_PID", ""),
            "unit": entry.get("_SYSTEMD_UNIT", "")
        })
    
    return messages

def get_systemd_status(service_name: str) -> Dict[str, Any]:
    """Get systemd status for the dummychain service.
    Merges in some data from the journal as well.
    
    Returns:
        Dict containing service status, journal messages, and systemd properties.
    """
    result = {}
    
    # Get the latest systemd+journal entry
    try:
        journal_entry = get_last_journal_message(service_name)
        if not journal_entry:
            result["journal_warning"] = "No journal entries found"
        else:
            result.update(journal_entry)

    except Exception as e:
        result["journal_error"] = {
            "error": str(e),
            "type": type(e).__name__,
            "args": getattr(e, 'args', [])
        }
    
    # Get systemd service properties
    try:

        service_props = get_essential_service_properties(service_name)

        if not service_props:
            result["service_warning"] = "No service properties found"
        else:
            # result["service"] = service_props.get("service", {})
            result["service"] = service_props
    except Exception as e:
        result["service_error"] = {
            "error": str(e),
            "type": type(e).__name__,
            "args": getattr(e, 'args', [])
        }
    
    return result
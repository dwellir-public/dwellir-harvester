"""
Module for interacting with journald via the journalctl command.
Provides a simple interface to retrieve journal entries for systemd services.
"""

import json
import subprocess
from typing import Dict, List, Optional, Union


def get_journal_entries(
    service_name: str,
    num_entries: int = 1,
    output_format: str = "json"
) -> List[Dict[str, str]]:
    """
    Retrieve journal entries for a specified systemd service.

    Args:
        service_name: Name of the systemd service (e.g., 'snap.dummychain.daemon.service')
        num_entries: Number of most recent log entries to retrieve (default: 1)
        output_format: Output format ('json', 'json-pretty', 'short', etc.)

    Returns:
        List of journal entries as dictionaries
    """
    try:
        # Build the journalctl command
        cmd = [
            "journalctl",
            f"-u{service_name}",
            f"-n{num_entries}",
            f"-o{output_format}",
            "--no-pager"
        ]

        # Run the command and capture output
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=True
        )

        # Parse the output
        if output_format.startswith("json"):
            try:
                # Handle both single JSON object and newline-delimited JSON
                if result.stdout.strip().startswith('{'):
                    return [json.loads(result.stdout)]
                else:
                    return [
                        json.loads(line)
                        for line in result.stdout.strip().split('\n')
                        if line.strip()
                    ]
            except json.JSONDecodeError as e:
                return [{"error": f"Failed to parse journal output: {e}"}]
        else:
            # For non-JSON output, return as raw text
            return [{"raw_output": result.stdout}]

    except subprocess.CalledProcessError as e:
        return [{"error": f"journalctl command failed: {e}"}]
    except Exception as e:
        return [{"error": f"Unexpected error: {e}"}]


def get_last_journal_message(service_name: str) -> Dict[str, str]:
    """
    Get the most recent journal message for a service.

    Args:
        service_name: Name of the systemd service

    Returns:
        Dictionary with the message and metadata
    """
    entries = get_journal_entries(service_name, 1, "json-pretty")
    if not entries or "error" in entries[0]:
        return {
            "error": entries[0]["error"] if entries and "error" in entries[0] 
                    else "No journal entries found"
        }
    
    # Extract relevant fields
    entry = entries[0]
    return {
        "message": entry.get("MESSAGE", ""),
        "timestamp": entry.get("__REALTIME_TIMESTAMP", ""),
        "unit": entry.get("_SYSTEMD_UNIT", ""),
        "pid": entry.get("_PID", ""),
        "cmdline": entry.get("_CMDLINE", ""),
        "priority": entry.get("PRIORITY", ""),
        "raw_entry": entry  # Include the full entry for reference
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
    entries = get_journal_entries(service_name, num_entries, "json-pretty")
    if not entries or "error" in entries[0]:
        return [{
            "error": entries[0]["error"] if entries and "error" in entries[0] 
                    else "No journal entries found"
        }]
    
    return [
        {
            "message": entry.get("MESSAGE", ""),
            "timestamp": entry.get("__REALTIME_TIMESTAMP", ""),
            "unit": entry.get("_SYSTEMD_UNIT", ""),
            "pid": entry.get("_PID", ""),
            "cmdline": entry.get("_CMDLINE", ""),
            "priority": entry.get("PRIORITY", "")
        }
        for entry in entries
    ]

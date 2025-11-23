from typing import Dict, Any, Tuple, Optional, List
import subprocess
from ..journalctl import get_last_journal_message
from ..systemctl_status import get_essential_service_properties
from .collector_base import BlockchainCollector

class DummychainCollector(BlockchainCollector):
    """Collector for Dummychain nodes."""
    
    NAME = "dummychain"
    VERSION = "0.1.0"
    
    def __init__(self, rpc_url: Optional[str] = None):
        """Initialize the Dummychain collector.
        
        Args:
            rpc_url: Optional RPC URL for the Dummychain node.
        """
        super().__init__(rpc_url=rpc_url)
        self.rpc_url = rpc_url or "http://localhost:9933"
    
    @classmethod
    def create(cls, **kwargs) -> 'DummychainCollector':
        """Factory method to create a new DummychainCollector instance.
        
        Args:
            **kwargs: Additional arguments to pass to the collector.
            
        Returns:
            DummychainCollector: A new instance of the DummychainCollector.
        """
        return cls(**kwargs)
    
    def _jsonrpc(self, url: str, method: str, params: list = None) -> Tuple[Any, Optional[str]]:
        """Make a JSON-RPC call to the node."""
        try:
            import requests
            payload = {
                "jsonrpc": "2.0",
                "method": method,
                "params": params or [],
                "id": 1
            }
            response = requests.post(url, json=payload)
            response.raise_for_status()
            result = response.json()
            return result.get("result"), result.get("error")
        except Exception as e:
            return None, str(e)
    
    def _get_systemd_status(self) -> Dict[str, Any]:
        """Get systemd status for the dummychain service.
        
        Returns:
            Dict containing service status, journal messages, and systemd properties.
        """
        service_name = "snap.dummychain.daemon.service"
        result = {}
        
        # Get the latest journal entry
        try:
            journal_entry = get_last_journal_message(service_name)
            result.update({
                "journal": {
                    "message": journal_entry.get("message", ""),
                    "timestamp": journal_entry.get("timestamp", ""),
                    "cmdline": journal_entry.get("cmdline", "")
                },
                "pid": journal_entry.get("pid", "")
            })
        except Exception as e:
            result["journal_error"] = str(e)
        
        # Get systemd service properties
        try:
            service_props = get_essential_service_properties(service_name)
            result["service"] = service_props.get("service", {})
        except Exception as e:
            result["service_error"] = str(e)
        
        return result
    
    def _get_client_version(self) -> Tuple[Optional[str], List[str]]:
        """Get the dummychain client version.
        
        Returns:
            Tuple of (version, messages) where version is the version string or None,
            and messages is a list of status/info messages.
        """
        messages = []
        try:
            result = subprocess.run(
                ["dummychain", "--version"],
                capture_output=True,
                text=True
            )
            
            if result.returncode != 0:
                messages.append(f"Failed to get version: {result.stderr}")
                return None, messages
                
            version_str = result.stdout.strip()
            if " " in version_str:
                version = version_str.split(" ", 1)[1].lstrip("v")
                return version, messages
                
            messages.append(f"Unexpected version format: {version_str}")
            return None, messages
        except Exception as e:
            messages.append(f"Failed to get dummychain version: {e}")
            return None, messages
    
    def collect(self) -> Dict[str, Any]:
        """Collect dummychain node information.
        
        Returns:
            Dictionary containing the collected data.
        """
        # Get client version and systemd status
        version, version_msgs = self._get_client_version()
        systemd_status = self._get_systemd_status()
        
        # Initialize the result structure
        result = {
            "meta": self._get_metadata(),
            "data": {
                "blockchain": {
                    "ecosystem": "Dwellir",
                    "network": "dummy-network",
                    "chain_id": -1  # sentinel for "unknown"
                },
                "workload": {
                    "client": {
                        "name": "dummychain",
                        "version": version or "unknown",
                        "systemd_status": systemd_status
                    }
                }
            }
        }
        
        # Try to get chain info via RPC if available
        try:
            chain_info, err = self._jsonrpc(
                self.rpc_url,
                "chain_getBlockHash",
                [0]  # Get genesis hash
            )
            if chain_info:
                result["data"]["blockchain"]["genesis_hash"] = chain_info
                
            # Get node name and version
            system_properties, _ = self._jsonrpc(
                self.rpc_url,
                "system_properties"
            )
            if system_properties:
                if "name" in system_properties:
                    result["data"]["blockchain"]["network"] = system_properties["name"]
                if "chain" in system_properties:
                    result["data"]["blockchain"]["network"] = system_properties["chain"]
                if "chainId" in system_properties:
                    result["data"]["blockchain"]["chain_id"] = system_properties["chainId"]
                    
        except Exception as e:
            result["meta"]["warnings"] = [f"Failed to get chain info: {str(e)}"]
        
        return result
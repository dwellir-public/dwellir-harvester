from typing import Dict, Any, Optional, List, Tuple
import subprocess
from ..systemd_utils import get_last_journal_message, get_essential_service_properties
from .collector_base import BlockchainCollector, CollectResult
import logging
logger = logging.getLogger(__name__)
# Add NullHandler to prevent "No handlers could be found" warnings
logger.addHandler(logging.NullHandler())


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

    
    # In dummychain.py, update the _get_systemd_status method:
    def _get_systemd_status(self) -> Dict[str, Any]:
        """Get systemd status for the dummychain service.
        Merges in some data from the journal as well.
        
        Returns:
            Dict containing service status, journal messages, and systemd properties.
        """
        service_name = "snap.dummychain.daemon.service"
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

    # Update the _get_client_version method:
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
                error_msg = f"Command failed with return code {result.returncode}"
                if result.stderr:
                    error_msg += f": {result.stderr.strip()}"
                messages.append(error_msg)
                return None, messages
                
            version_str = result.stdout.strip()
            if not version_str:
                messages.append("Empty version string received")
                return None, messages
                
            return version_str, messages
                
        except FileNotFoundError:
            messages.append("dummychain executable not found in PATH")
        except Exception as e:
            messages.append(f"Unexpected error: {str(e)}")
        
        return None, messages
    

    def collect(self) -> Dict[str, Any]:
        """Collect dummychain node information.
        
        Returns:
            Dict containing the collected data.
        """
        # First collect all the data we need
        version, messages = self._get_client_version()
        logger.debug(f"Fetched client version: {version}, err: {messages}")

        # Get systemd status
        try:
            systemd_status = self._get_systemd_status()
            logger.debug(f"Fetched systemd: {systemd_status}")
        except Exception as e:
            systemd_status = {
                "error": str(e),
                "type": type(e).__name__
            }
        
        # Create the result with all data
        result = CollectResult.create(
            collector_name=self.NAME,
            collector_version=self.VERSION,
            data={
                "blockchain": {
                    "blockchain_ecosystem": "dummychain",
                    "blockchain_network_name": "dummychain",
                    "chain_id": "dummychain-1",  # Provide a default chain_id
                    "client_name": "dummychain-node",
                    "client_version": version or "1.0.0",  # Fallback to default if version is None
                    "systemd_status": systemd_status,
                    **({"client_errors": messages} if messages else {})
                }
            }
        )
        
        # Validate the final data structure
        logger.debug(f"Validating blockchain data...")
        self._validate_blockchain_data(result.data)
        logger.debug(f"Validated blockchain data")
        

        return result
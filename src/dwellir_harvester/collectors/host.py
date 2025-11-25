"""Host information collector."""
from datetime import datetime, timezone
from typing import Dict, Any, Optional
import platform
import socket
import sys
import time
import psutil

from ..collector_base import GenericCollector

def get_system_uptime() -> float:
    """Get system uptime in seconds from /proc/uptime."""
    try:
        with open('/proc/uptime', 'r') as f:
            return float(f.readline().split()[0])
    except (FileNotFoundError, IndexError, ValueError):
        # Fallback to psutil if /proc/uptime is not available
        try:
            return time.time() - psutil.boot_time()
        except Exception:
            return time.clock_gettime(time.CLOCK_MONOTONIC)  # type: ignore

def _get_cpu_model() -> Optional[str]:
    """Get CPU model information from /proc/cpuinfo."""
    try:
        with open("/proc/cpuinfo", "r") as f:
            for line in f:
                if line.startswith("model name"):
                    return line.split(":")[1].strip()
        return None
    except Exception:
        return None

class HostCollector(GenericCollector):
    """
    Collects host information. This collector is a built in collector 
    In the sense that it populates the "host" key in the output dictionary.
    """
    
    NAME = "host"
    VERSION = "1.0.0"
    COLLECTOR_TYPE = "host"
    
    @classmethod
    def create(cls, *args, **kwargs) -> 'HostCollector':
        """Factory method to create a new instance."""
        return cls(*args, **kwargs)
    
    def collect(self) -> Dict[str, Any]:
        """
        Collect and return host information in a structured format.

        Returns:
            Dictionary with the collected host information in a structured format.
        """
        collection_time = datetime.now(timezone.utc).isoformat()
        
        # Initialize host info
        host_info: Dict[str, Any] = {
            "hostname": socket.getfqdn(),
            "kernel": {
                "release": platform.release(),
                "version": platform.version(),
            },
            "uptime": get_system_uptime()
        }
        
        # Add LSB information if available
        try:
            import distro
            host_info["lsb"] = {
                "id": distro.id(),
                "release": distro.version(),
                "codename": distro.codename() or "",
                "description": distro.name(pretty=True)
            }
        except ImportError:
            pass
            
        # Add additional system information if available
        try:
            host_info.update({
                "python_version": platform.python_version(),
                "architecture": platform.machine(),
                "processor": platform.processor() or "unknown",
            })
            
            # Add CPU and memory info using psutil
            try:
                # CPU information
                host_info["cpu"] = {
                    "cores": psutil.cpu_count(logical=True),
                    "physical_cores": psutil.cpu_count(logical=False),
                    "model": _get_cpu_model(),
                    "usage_percent": psutil.cpu_percent(interval=0.1),
                    "load_avg": psutil.getloadavg() if hasattr(psutil, 'getloadavg') else None
                }
                
                # Memory information
                mem = psutil.virtual_memory()
                swap = psutil.swap_memory()
                host_info["memory"] = {
                    "total": mem.total,
                    "available": mem.available,
                    "used": mem.used,
                    "free": mem.free,
                    "percent_used": mem.percent,
                    "swap_total": swap.total,
                    "swap_used": swap.used,
                    "swap_free": swap.free,
                    "swap_percent_used": swap.percent
                }
                
            except Exception as e:
                print(f"Warning: Could not collect CPU/memory info: {e}", file=sys.stderr)
                
        except Exception as e:
            # Don't fail the whole collection if additional info fails
            print(f"Warning: Could not collect additional host info: {e}", file=sys.stderr)
        
        return {
            "meta": {
                "collector_type": self.COLLECTOR_TYPE,
                "collector_name": self.NAME,
                "collector_version": self.VERSION,
                "collection_time": collection_time
            },
            "data": host_info,
            "message": "Host information collected successfully"
        }

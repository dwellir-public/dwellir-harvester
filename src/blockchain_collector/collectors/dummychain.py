from __future__ import annotations
import json
import os
import shutil
import socket
import subprocess
from typing import Dict, List, Optional, Tuple
from urllib import error as urlerror, request

from ..core import BaseCollector, CollectResult, CollectResult, CollectorPartialError
from ..core import CollectResult, CollectorFailedError, CollectorPartialError


class DummychainCollector(BaseCollector):
    """
    The dummychain collector interacts with the dummychain snap to collect metadata.
    Its principally a testing tool to allow for easy testing of the collector framework.
    """
    NAME = "dummychain"
    VERSION = "0.0.0"
    DEFAULT_RPC_URL = "http://127.0.0.1:8080"

    def _jsonrpc(url: str, method: str, params=None, timeout: float = 2.5):
        if params is None:
            params = []
        payload = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params}).encode()
        req = request.Request(url, data=payload, headers={"Content-Type": "application/json"})
        try:
            with request.urlopen(req, timeout=timeout) as resp:
                data = json.loads(resp.read().decode())
                if "error" in data:
                    return None, f"rpc {method} error: {data['error']}"
                return data.get("result"), None
        except socket.timeout:
            return None, f"rpc {method} timeout after {timeout}s (url={url})"
        except urlerror.URLError as e:
            reason = getattr(e, "reason", e)
            return None, f"rpc {method} connection error (url={url}): {reason}"
        except Exception as e:
            return None, f"rpc {method} unexpected error (url={url}): {e}"

    def _find_executable(self) -> Optional[str]:
        p = os.environ.get("DUMMYCHAIN_BIN")
        if p and os.path.isfile(p) and os.access(p, os.X_OK):
            return p
        w = shutil.which("dummychain")
        if w and os.access(w, os.X_OK):
            return w
        for cand in ("/snap/bin/dymmychain", "/usr/bin/dummychain", "/usr/local/bin/dummychain"):
            if os.path.isfile(cand) and os.access(cand, os.X_OK):
                return cand
        return None


    def _get_system_name() -> Tuple[Optional[str], Optional[str]]:
        return str("dummychain"), None

    def _get_system_chain(url: str) -> Tuple[Optional[str], Optional[str]]:
        return str("dummychain"), None

    def _get_executable_version(self) -> Tuple[Optional[str], Optional[str]]:
        """Find the bin and get the version string"""


    def collect(self) -> CollectResult:
        messages: List[str] = []

        ## This is our static placeholders
        blockchain: Dict = {
            "blockchain_ecosystem": "Dwellir",
            "blockchain_network_name": "dummy-network",
            "chain_id": -1,  # sentinel for "unknown"
        }
        workload: Dict = {
            "client_name": "dummychain",
            "client_version": "unknown",
        }

        # Populate workload
        client_version_cli = "unknown"
        try:
            proc = subprocess.run(["/snap/bin/dummychain", "--version"], capture_output=True, text=True, check=True)
            vline = (proc.stdout or "").strip().splitlines()
            client_version_cli = vline[0] if vline else None
            if not client_version_cli:
                messages.append("dummychain --version returned no output")
        except UnboundLocalError as e:
            messages.append("dummychain binary not found (install dummychain snap)")
        except Exception as e:
            messages.append(f"dummychain --version failed: {e!r}")
        else:
            messages.append("dummychain binary not found (install dummychain)")

        if client_version_cli != "unknown":
            # Parse version string to a format "X.X.X"
            workload["client_version"] = client_version_cli.rsplit(" ", 1)[1]
            workload["notes"] = "Snap installed."
        else:
            partial = CollectResult(blockchain=blockchain, workload=workload)
            messages.append("dummychain binary not found (install dummychain snap)")
            raise CollectorPartialError(messages or ["Partial data only."], partial=partial)

        return CollectResult(blockchain=blockchain, workload=workload)

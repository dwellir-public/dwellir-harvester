from __future__ import annotations
from ..core import BaseCollector, CollectResult
from ._substrate_common import collect_substrate, SUBSTRATE_COLLECTOR_VERSION

# Note: This can be used for any substrate chain as long as the system_name RPC method returns the correct binary name.
#       For some substrate binaries this system_name returns the current file name of the binary which is not reliable.
class SubstrateCollector(BaseCollector):
    NAME = "substrate"
    VERSION = SUBSTRATE_COLLECTOR_VERSION

    def collect(self) -> CollectResult:
        return collect_substrate()

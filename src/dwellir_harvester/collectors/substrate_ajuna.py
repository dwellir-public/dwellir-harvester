from __future__ import annotations
from ..core import CollectResult
from .collector_base import CollectorBase
from ._substrate_common import collect_substrate, SUBSTRATE_COLLECTOR_VERSION


class AjunaCollector(CollectorBase):
    NAME = "ajuna"
    VERSION = SUBSTRATE_COLLECTOR_VERSION

    def collect(self) -> CollectResult:
        # Hardcode the client_name to a stable label
        return collect_substrate(self.NAME)

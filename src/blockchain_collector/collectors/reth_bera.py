from __future__ import annotations
from typing import Dict
from ..core import BaseCollector, CollectResult
from ._reth_common import collect_reth, RETH_COLLECTOR_VERSION


class BeraRethCollector(BaseCollector):
    NAME = "bera-reth"
    VERSION = RETH_COLLECTOR_VERSION

    def collect(self) -> CollectResult:
        return collect_reth(self.NAME)

from __future__ import annotations
from typing import Dict
from ..core import BaseCollector, CollectResult
from ._reth_common import collect_reth, RETH_COLLECTOR_VERSION


class OpRethCollector(BaseCollector):
    NAME = "op-reth"
    VERSION = RETH_COLLECTOR_VERSION

    def collect(self) -> CollectResult:
        return collect_reth(self.NAME)

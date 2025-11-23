from __future__ import annotations
from typing import Dict
from ..core import CollectResult
from .collector_base import CollectorBase
from ._reth_common import collect_reth, RETH_COLLECTOR_VERSION


class OpRethCollector(CollectorBase):
    NAME = "op-reth"
    VERSION = RETH_COLLECTOR_VERSION

    def collect(self) -> CollectResult:
        return collect_reth(self.NAME)

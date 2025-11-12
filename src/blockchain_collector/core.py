
from __future__ import annotations
import importlib
import pkgutil
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict, List, Optional
from typing import Tuple

try:
    import jsonschema  # type: ignore
except Exception:
    jsonschema = None

class CollectorFailedError(Exception):
    pass

class CollectorPartialError(Exception):
    def __init__(self, messages: List[str], partial: Optional["CollectResult"]=None):
        self.messages = messages
        self.partial = partial
        super().__init__("; ".join(messages))


@dataclass
class CollectResult:
    blockchain: Dict
    workload: Dict

class BaseCollector:
    NAME: str = "base"
    VERSION: str = "0.0.0"
    def collect(self) -> CollectResult:
        raise NotImplementedError

def now_iso_tz() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")

def validate_output(instance: Dict, schema_path: str) -> None:
    if jsonschema is None:
        return
    with open(schema_path, "r", encoding="utf-8") as f:
        schema = json.load(f)
    jsonschema.validate(instance=instance, schema=schema)

def bundled_schema_path() -> str:
    import importlib.resources as ir
    with ir.as_file(ir.files(__package__) / "data" / "blockchain_node_metadata.schema.json") as p:
        return str(p)

def load_collectors():
    from . import collectors
    mapping = {}
    for _, module_name, _ in pkgutil.iter_modules(collectors.__path__):
        mod = importlib.import_module(f"{collectors.__name__}.{module_name}")
        names = getattr(mod, "__all__", [])
        if not names:
            for attr in dir(mod):
                obj = getattr(mod, attr)
                try:
                    if isinstance(obj, type) and issubclass(obj, BaseCollector) and obj is not BaseCollector:
                        mapping[obj.NAME] = obj
                except Exception:
                    continue
        else:
            for attr in names:
                obj = getattr(mod, attr)
                if isinstance(obj, type) and issubclass(obj, BaseCollector) and obj is not BaseCollector:
                    mapping[obj.NAME] = obj
    return mapping

def run_collector(collector_name: str, schema_path: str, validate: bool = True,
                  extra_metadata: Optional[Dict] = None) -> Dict:
    collectors = load_collectors()
    if collector_name not in collectors:
        raise KeyError(f"Collector '{collector_name}' not found. Available: {', '.join(sorted(collectors.keys())) or '(none)'}")
    CollectorCls = collectors[collector_name]
    collector = CollectorCls()

    attempt_time = now_iso_tz()
    errors: List[str] = []
    status = "failed"
    res: Optional[CollectResult] = None

    try:
        res = collector.collect()
        status = "success"
    except CollectorPartialError as e:
        # keep partial data if provided
        res = e.partial or CollectResult(blockchain={}, workload={})
        status = "partial"
        errors = e.messages
    except Exception as e:
        # treat as failed but still emit a structured output
        errors = [repr(e)]
        status = "failed"
        res = CollectResult(blockchain={}, workload={})

    output = {
        "metadata": {
            "collector_name": CollectorCls.NAME,
            "collector_version": getattr(CollectorCls, "VERSION", "0.0.0"),
            "last_collect_attempt_at": attempt_time,
            "last_collect_status": status,
            "last_collect_errors": errors,
        },
        "blockchain": res.blockchain if res else {},
        "workload": res.workload if res else {},
    }
    if status == "success":
        output["metadata"]["last_successful_collect_at"] = attempt_time
    if extra_metadata:
        output["metadata"].update(extra_metadata)

    # Only validate successful outputs (partial/failed may be intentionally incomplete)
    if validate and status == "success":
        validate_output(output, schema_path)

    return output


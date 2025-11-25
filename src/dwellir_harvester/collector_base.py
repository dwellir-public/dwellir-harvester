"""Collector types and base classes in a single module."""

import importlib
import json
import logging
import sys
import traceback
from dataclasses import dataclass, field
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Any, Dict, Generic, List, Optional, TypeVar


# Exceptions
class CollectorError(Exception):
    """Base exception for collector errors."""
    pass


class CollectorFailedError(CollectorError):
    """Raised when a collector fails completely."""
    pass


class CollectorPartialError(CollectorError):
    """Raised when a collector partially succeeds."""

    def __init__(self, messages: List[str], partial: Optional[Dict[str, Any]] = None):
        self.messages = messages
        self.partial = partial
        super().__init__("; ".join(messages))


T = TypeVar("T")


# Metadata and result containers
@dataclass
class CollectorMetadata:
    """Metadata about a collector run."""

    collector_name: str
    collector_version: str
    collection_time: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    collector_type: str = "generic"
    status: str = "success"
    errors: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Convert metadata to a dictionary."""
        return {
            "collector_name": self.collector_name,
            "collector_version": self.collector_version,
            "collection_time": self.collection_time,
            "collector_type": self.collector_type,
            "status": self.status,
            "errors": self.errors,
        }


@dataclass
class CollectResult(Generic[T]):
    """Result of a collector run."""

    metadata: CollectorMetadata
    data: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def create(
        cls,
        collector_name: str,
        collector_version: str,
        data: Optional[Dict[str, Any]] = None,
        errors: Optional[List[str]] = None,
    ) -> "CollectResult":
        """Create a new CollectResult with proper metadata."""
        metadata = CollectorMetadata(
            collector_name=collector_name,
            collector_version=collector_version,
            status="partial" if errors else "success",
            errors=errors or [],
        )
        return cls(metadata=metadata, data=data or {})

    def to_dict(self) -> Dict[str, Any]:
        """Convert the CollectResult to a dictionary."""
        # Create a deep copy of the data to avoid modifying the original
        data = json.loads(json.dumps(self.data, default=str))

        return {
            "metadata": {
                "collector_name": str(self.metadata.collector_name),
                "collector_version": str(self.metadata.collector_version),
                "collection_time": str(self.metadata.collection_time),
                "collector_type": str(self.metadata.collector_type),
                "status": str(self.metadata.status),
                "errors": [str(error) for error in self.metadata.errors],
            },
            "data": data,
        }


logger = logging.getLogger(__name__)


class CollectorBase(ABC):
    """Base class for all collectors."""

    # These should be overridden by subclasses
    COLLECTOR_TYPE: str
    NAME: str
    VERSION: str = "0.0.0"

    def __init__(self):
        if not hasattr(self, "COLLECTOR_TYPE") or not self.COLLECTOR_TYPE:
            raise NotImplementedError("Subclasses must define COLLECTOR_TYPE")
        if not hasattr(self, "NAME") or not self.NAME:
            raise NotImplementedError("Subclasses must define NAME")

    def _get_metadata(self) -> CollectorMetadata:
        """Get the standard metadata for this collector."""
        return CollectorMetadata(
            collector_name=self.NAME,
            collector_version=self.VERSION,
            collector_type=self.COLLECTOR_TYPE,
        )

    @abstractmethod
    def collect(self) -> Dict[str, Any]:
        """Collect and return data."""
        return {}

    def run(self, debug: bool = False) -> Dict[str, Any]:
        """Run the collector and return its result with metadata."""
        collection_start = datetime.now(timezone.utc)
        debug_info = {}

        if debug:
            print(f"[DEBUG] Starting collector: {self.NAME} (version: {self.VERSION})", file=sys.stderr)
            debug_info.update(
                {
                    "start_time": collection_start.isoformat(),
                    "python_version": sys.version,
                    "platform": sys.platform,
                    "executable": sys.executable,
                    "collector_module": self.__class__.__module__,
                }
            )

        try:
            if debug:
                print(f"[DEBUG] Collecting data with {self.NAME}...", file=sys.stderr)

            # Run the collector
            result = self.collect()

            if debug:
                print(f"[DEBUG] {self.NAME} collection completed successfully", file=sys.stderr)

            # If the collector didn't return a CollectResult, wrap it
            if not isinstance(result, CollectResult):
                if debug:
                    print(f"[DEBUG] Wrapping raw result in CollectResult", file=sys.stderr)
                result = CollectResult.create(collector_name=self.NAME, collector_version=self.VERSION, data=result)

            # Convert to dict
            result_dict = result.to_dict()

            # Ensure the result has the correct structure
            if "meta" not in result_dict or "data" not in result_dict:
                if debug:
                    print(f"[DEBUG] Restructuring result to standard format", file=sys.stderr)
                result_dict = {
                    "meta": {
                        "collector_type": result_dict.get("metadata", {}).get("collector_type", self.COLLECTOR_TYPE),
                        "collector_name": result_dict.get("metadata", {}).get("collector_name", self.NAME),
                        "collector_version": result_dict.get("metadata", {}).get("collector_version", self.VERSION),
                        "collection_time": result_dict.get("metadata", {}).get(
                            "collection_time", datetime.now(timezone.utc).isoformat()
                        ),
                    },
                    "data": result_dict.get("data", {}),
                }

            # Enforce blockchain payload invariants even if subclass forgot to validate
            if self.COLLECTOR_TYPE == "blockchain":
                try:
                    self._validate_blockchain_data(result_dict.get("data", {}))  # type: ignore[attr-defined]
                except Exception as e:
                    logger.error(
                        "Validation failed in blockchain collector %s: %s",
                        self.NAME,
                        str(e),
                        exc_info=debug,
                    )
                    raise

            # Add debug information if enabled
            if debug:
                debug_info["end_time"] = datetime.now(timezone.utc).isoformat()
                debug_info["duration_seconds"] = (datetime.now(timezone.utc) - collection_start).total_seconds()
                debug_info["result_structure"] = {
                    "has_meta": "meta" in result_dict,
                    "has_data": "data" in result_dict,
                    "data_keys": list(result_dict.get("data", {}).keys())
                    if isinstance(result_dict.get("data"), dict)
                    else [],
                }
                result_dict["meta"]["debug"] = debug_info
                print(
                    f"[DEBUG] Collector {self.NAME} completed in {debug_info['duration_seconds']:.2f} seconds",
                    file=sys.stderr,
                )

            return result_dict

        except CollectorPartialError as e:
            # Handle partial results
            result = e.partial or {}
            error_info = {"messages": e.messages, "type": "CollectorPartialError"}
            logger.warning("Collector %s produced partial data: %s", self.NAME, "; ".join(e.messages))
            if debug:
                error_info["traceback"] = traceback.format_exc()

            return {
                "meta": {
                    "collector_type": result.get("metadata", {}).get("collector_type", self.COLLECTOR_TYPE),
                    "collector_name": result.get("metadata", {}).get("collector_name", self.NAME),
                    "collector_version": result.get("metadata", {}).get("collector_version", self.VERSION),
                    "collection_time": result.get("metadata", {}).get(
                        "collection_time", datetime.now(timezone.utc).isoformat()
                    ),
                    "status": "partial",
                    "errors": e.messages,
                    "debug": error_info if debug else None,
                },
                "data": result.get("data", {}),
            }

        except Exception as e:
            error_msg = str(e)
            print(f"Error in collector {self.NAME}: {error_msg}", file=sys.stderr)
            # Log so missing required fields surface in logs
            logger.error("Collector %s failed: %s", self.NAME, error_msg, exc_info=debug)

            error_info = {
                "message": error_msg,
                "type": type(e).__name__,
                "args": getattr(e, "args", []),
            }
            if debug:
                error_info["traceback"] = traceback.format_exc()

            # Create a failed result
            return {
                "meta": {
                    "collector_type": self.COLLECTOR_TYPE,
                    "collector_name": self.NAME,
                    "collector_version": self.VERSION,
                    "collection_time": datetime.now(timezone.utc).isoformat(),
                    "status": "failed",
                    "errors": [error_msg],
                    "debug": error_info if debug else None,
                },
                "data": {},
            }


class BlockchainCollector(CollectorBase):
    """Base class for blockchain collectors."""

    COLLECTOR_TYPE = "blockchain"

    # Required fields for each section of the blockchain payload
    REQUIRED_BLOCKCHAIN_FIELDS = {
        "blockchain_ecosystem": (str,),
        "blockchain_network_name": (str,),
        "chain_id": (str, int),  # Must be provided (no None)
    }
    REQUIRED_WORKLOAD_FIELDS = {
        "client_name": (str,),
        "client_version": (str,),  # Must be provided (no None)
        "service_data": (dict,),  # Systemd/service inspection data
    }

    def __init__(self, rpc_url: Optional[str] = None):
        super().__init__()
        self.rpc_url = rpc_url

    def _validate_blockchain_data(self, data: Dict[str, Any]) -> None:
        """Validate that the blockchain and workload sections have required fields."""
        if "blockchain" not in data:
            raise CollectorError("Missing 'blockchain' key in collector data")
        if "workload" not in data:
            raise CollectorError("Missing 'workload' key in collector data")

        blockchain_data = data["blockchain"]
        workload_data = data["workload"]

        if not isinstance(blockchain_data, dict):
            raise CollectorError("'blockchain' must be a dict")
        if not isinstance(workload_data, dict):
            raise CollectorError("'workload' must be a dict")

        def _check_required(section: Dict[str, Any], required: Dict[str, tuple], section_name: str) -> List[str]:
            missing_fields = []
            type_errors = []
            none_fields = []
            for field, expected_types in required.items():
                if field not in section:
                    logging.debug(
                        f"Missing required field: {section_name}.{field} "
                        f"(expected types: {[t.__name__ for t in expected_types]})"
                    )
                    missing_fields.append(field)
                    continue

                value = section[field]
                if value is None and None not in expected_types:
                    logging.debug(
                        f"Required field {section_name}.{field} is None "
                        f"(expected types: {[t.__name__ for t in expected_types]})"
                    )
                    none_fields.append(field)
                    continue

                if value is not None and not any(isinstance(value, t) for t in expected_types):
                    expected_type_names = [t.__name__ for t in expected_types if t is not type(None)]
                    if type(None) in expected_types:
                        expected_type_names.append("None")
                    type_errors.append(
                        f"Field '{section_name}.{field}' has type {type(value).__name__}, "
                        f"expected {' or '.join(expected_type_names)}"
                    )
            errors: List[str] = []
            if missing_fields:
                errors.append(f"{section_name} missing: {', '.join(missing_fields)}")
            if none_fields:
                errors.append(f"{section_name} cannot be None: {', '.join(none_fields)}")
            if type_errors:
                errors.extend(type_errors)
            return errors

        errors = _check_required(blockchain_data, self.REQUIRED_BLOCKCHAIN_FIELDS, "blockchain")
        errors += _check_required(workload_data, self.REQUIRED_WORKLOAD_FIELDS, "workload")

        if errors:
            raise CollectorError("; ".join(errors))

    def _prepare_blockchain_data(self) -> Dict[str, Any]:
        """Prepare the blockchain and workload sections. Subclasses should override."""
        return {
            "blockchain": {
                "blockchain_ecosystem": None,
                "blockchain_network_name": None,
                "chain_id": None,
            },
            "workload": {
                "client_name": None,
                "client_version": None,
                "service_data": {},
            },
        }

    def collect(self) -> Dict[str, Any]:
        """Collect blockchain data."""
        # Get the blockchain/workload data from the subclass implementation
        prepared = self._prepare_blockchain_data()

        # If a subclass only returns the blockchain section, wrap it to the new structure
        if "blockchain" in prepared and "workload" in prepared:
            data = prepared
        else:
            data = {
                "blockchain": prepared,
                "workload": {"client_name": None, "client_version": None, "service_data": {}},
            }

        # Validate the collected data
        self._validate_blockchain_data(data)

        # Convert metadata to dict before returning
        metadata = self._get_metadata()
        if hasattr(metadata, "to_dict"):
            metadata = metadata.to_dict()

        return {"metadata": metadata, "data": data}


class GenericCollector(CollectorBase):
    """Base class for generic collectors with no specific schema."""

    COLLECTOR_TYPE = "generic"

    def collect(self) -> Dict[str, Any]:
        """Collect arbitrary data."""
        data = super().collect()
        return {"metadata": self._get_metadata(), "data": data}

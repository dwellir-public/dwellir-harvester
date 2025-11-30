from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("dwellir-harvester")
except PackageNotFoundError:
    __version__ = "0.0.0"

__all__ = ["cli", "daemon"]

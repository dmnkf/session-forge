"""Session Forge package."""

from importlib.metadata import PackageNotFoundError, version

try:  # pragma: no cover
    __version__ = version("session-forge")
except PackageNotFoundError:  # pragma: no cover
    __version__ = "0.0.0"

__all__ = ["__version__"]

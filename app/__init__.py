"""Stemmy — local AI stem separation studio."""

__version__ = "1.5.0"

from .server import create_app as _create_app
from .tools_ui import install_tools


def create_app():
    """Create Stemmy and attach isolated musician tools."""
    return install_tools(_create_app())


__all__ = ["create_app", "__version__"]

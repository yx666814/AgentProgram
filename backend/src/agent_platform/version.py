from importlib.metadata import version
from typing import Final

PACKAGE_NAME: Final[str] = "agent-platform-backend"
__version__: Final[str] = version(PACKAGE_NAME)

"""
Python version compatibility check for XGBoost/OpenMP.

This module ensures Python 3.11 is used for ML training scripts
to prevent recurring XGBoost/OpenMP compatibility issues.
"""
import sys

REQUIRED_VERSION = (3, 11)
PYTHON_311_PATH = "/Users/nickcuskey/.pyenv/versions/3.11.13/bin/python3"


def check_python_version():
    """
    Verify Python 3.11 is being used for XGBoost compatibility.

    Raises:
        RuntimeError: If Python version is not 3.11.x
    """
    current_version = sys.version_info[:2]

    if current_version != REQUIRED_VERSION:
        error_msg = f"""
╔══════════════════════════════════════════════════════════════════════════════╗
║                        PYTHON VERSION ERROR                                  ║
╚══════════════════════════════════════════════════════════════════════════════╝

This script requires Python 3.11 for XGBoost/OpenMP compatibility.

Current version: {sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}
Required version: {REQUIRED_VERSION[0]}.{REQUIRED_VERSION[1]}.x

SOLUTION:
1. Use the virtual environment:
   .venv/bin/python3 {sys.argv[0]}

2. Or use Python 3.11 directly:
   {PYTHON_311_PATH} {sys.argv[0]}

WHY THIS MATTERS:
XGBoost requires OpenMP (libomp.dylib) which has architecture compatibility
issues with Python 3.13+ on this system. Python 3.11 has been verified to work.
"""
        raise RuntimeError(error_msg)


def get_python_version_string() -> str:
    """Return formatted Python version string."""
    return f"Python {sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"


# Auto-check when module is imported
if __name__ != "__main__":
    check_python_version()

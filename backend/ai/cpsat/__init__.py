"""CP-SAT scheduler (needs the optional OR-Tools package)."""
from importlib.util import find_spec


def available() -> bool:
    """True when OR-Tools is installed. It has no wheels for every Python version (none yet for 3.15)."""
    return find_spec("ortools") is not None

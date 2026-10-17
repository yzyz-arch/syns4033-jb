"""Make `import core.*` resolve when pytest is invoked from the repo root or
anywhere else — a3-farm must be runnable as `pytest a3-farm/tests`."""
import sys
from pathlib import Path

_A3 = Path(__file__).resolve().parent.parent  # a3-farm/
if str(_A3) not in sys.path:
    sys.path.insert(0, str(_A3))

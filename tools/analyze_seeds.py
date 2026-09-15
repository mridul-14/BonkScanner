"""Forwarding shim for tools/inspect_live/analyze_seeds.py."""
from __future__ import annotations

import runpy
import sys
from pathlib import Path

TARGET = Path(__file__).resolve().parent / "inspect_live" / "analyze_seeds.py"

if __name__ == "__main__":
    runpy.run_path(str(TARGET), run_name="__main__")
else:
    if str(TARGET.parent) not in sys.path:
        sys.path.insert(0, str(TARGET.parent))
    from analyze_seeds import *


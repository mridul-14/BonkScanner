"""Quick analyzer for Shady Guy seed dataset using pandas and rich."""
from __future__ import annotations

import sys
from pathlib import Path

TOOL_DIR = Path(__file__).resolve().parent
DEPS_DIR = TOOL_DIR / "dependencies"
ARTIFACTS_DIR = TOOL_DIR / "artifacts"
SEED_TRACKER_FILE = ARTIFACTS_DIR / "shady_seed_data.json"

if str(DEPS_DIR) not in sys.path:
    sys.path.insert(0, str(DEPS_DIR))
if str(TOOL_DIR) not in sys.path:
    sys.path.insert(0, str(TOOL_DIR))

from inspect_live import analyze_seed_data, SEED_TRACKER_FILE


def main():
    target_file = Path(sys.argv[1]) if len(sys.argv) > 1 else SEED_TRACKER_FILE
    analyze_seed_data(target_file)


if __name__ == "__main__":
    main()

"""Compatibility launcher for running the GUI from the source tree."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from md5_tool.gui import main  # noqa: E402


if __name__ == "__main__":
    raise SystemExit(main())

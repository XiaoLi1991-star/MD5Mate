"""Compatibility wrapper for the desktop GUI entry point."""

from __future__ import annotations

from .qt_gui import main

__all__ = ["main"]


if __name__ == "__main__":
    raise SystemExit(main())

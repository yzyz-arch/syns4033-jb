#!/usr/bin/env python3
"""Standalone launcher so `python3 tools/osintkit.py <cmd>` works without -m."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from osintkit.cli import main  # noqa: E402

if __name__ == "__main__":
    main()

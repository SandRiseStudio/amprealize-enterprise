"""Pytest configuration for amprealize-enterprise tests."""

import sys
from pathlib import Path

# Ensure the enterprise src is on the path for editable-mode-free testing
_src = Path(__file__).resolve().parent.parent / "src"
if str(_src) not in sys.path:
    sys.path.insert(0, str(_src))

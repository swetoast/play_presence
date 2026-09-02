"""Make the src-layout package importable on TF1's stock pytest 6.2.5."""
from __future__ import annotations
import sys
from pathlib import Path
SRC = Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

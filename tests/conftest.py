"""Make the src-layout package importable on TF1's stock pytest 6.2.5."""
from __future__ import annotations
import sys
from pathlib import Path
SRC = Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import pytest


@pytest.fixture(autouse=True)
def _clear_detection_caches():
    """Reset the module-level RetroArch scan caches around every test."""
    from play_presence import detection

    detection._RETROARCH_REGION_CACHE.clear()
    detection._RETROARCH_CONTENT_CACHE.clear()
    yield
    detection._RETROARCH_REGION_CACHE.clear()
    detection._RETROARCH_CONTENT_CACHE.clear()

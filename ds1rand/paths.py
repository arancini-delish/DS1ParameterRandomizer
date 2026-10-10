"""Where ds1rand finds its data and writes its output, from a source checkout or a packaged (PyInstaller) build.

    RESOURCES   read-only data shipped with ds1rand: `data/` (vanilla baseline, reference catalogue) and
                `ds1paramdefs/`. The repository root, or the bundle's data folder when frozen.
    APP_DIR     the folder the user runs ds1rand from: the repository root, or the folder holding the executables.
                The default output (`out/randomized`) goes here.
"""
from __future__ import annotations

import sys
from pathlib import Path

FROZEN = getattr(sys, "frozen", False)
REPO_ROOT = Path(__file__).resolve().parents[1]
RESOURCES = Path(getattr(sys, "_MEIPASS", REPO_ROOT)) if FROZEN else REPO_ROOT
APP_DIR = Path(sys.executable).resolve().parent if FROZEN else REPO_ROOT

DATA_DIR = RESOURCES / "data"
PARAMDEFS_DIR = RESOURCES / "ds1paramdefs"
DEFAULT_OUT = APP_DIR / "out" / "randomized"

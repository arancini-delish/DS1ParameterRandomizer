"""Build the packaged app with PyInstaller and zip it for release (Phase 8).

Produces `dist/ds1rand/` (ds1rand.exe: the UI; ds1rand-cli.exe: the command line; `_internal/`: runtime and data) and
`dist/ds1rand-<version>-win64.zip` containing that folder plus the README. Then smoke-tests the build: the CLI
prints its version, and the UI starts and quits (`--smoke`).

Usage: uv run --group build python tools/build_release.py [--no-zip] [--no-smoke]
"""
import argparse
import os
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DIST = ROOT / "dist"
APP = DIST / "ds1rand"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--no-zip", action="store_true")
    parser.add_argument("--no-smoke", action="store_true")
    args = parser.parse_args()
    sys.path.insert(0, str(ROOT))
    from ds1rand import __version__

    subprocess.run([sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--distpath", str(DIST),
                    "--workpath", str(ROOT / "build"), str(ROOT / "packaging" / "ds1rand.spec")], check=True)
    shutil.copy(ROOT / "README.md", APP / "README.md")

    if not args.no_smoke:
        version = subprocess.run([str(APP / "ds1rand-cli.exe"), "--version"], capture_output=True, text=True,
                                 check=True).stdout.strip()
        assert version == f"ds1rand {__version__}", version
        env = {**os.environ, "QT_QPA_PLATFORM": "offscreen"}
        subprocess.run([str(APP / "ds1rand.exe"), "--smoke"], env=env, check=True, timeout=120)
        print(f"Smoke test passed: {version}, UI starts")

    if not args.no_zip:
        archive = DIST / f"ds1rand-{__version__}-win64.zip"
        with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as zf:
            for path in sorted(APP.rglob("*")):
                zf.write(path, Path("ds1rand") / path.relative_to(APP))
        print(f"Wrote {archive} ({archive.stat().st_size / 2**20:.0f} MB)")


if __name__ == "__main__":
    main()

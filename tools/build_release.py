"""Build the packaged app with PyInstaller and zip it for release (Phase 8).

Produces `dist/ds1rand/` (ds1rand.exe: the UI; ds1rand-cli.exe: the command line; `_internal/`: runtime and data) and
`dist/ds1rand-<version>-win64.zip` containing that folder plus the README.

The folder also holds a portable `soulstruct_config.json`. Frozen, soulstruct reads its config next to the executable
and, if there is none, writes one with paths of the machine it runs on (its log file under the user's AppData), then
creates that log folder at import. A complete config with file logging off means soulstruct never writes anything:
nothing machine-specific ships, and a read-only install folder works.

The release is then checked as a user would get it: the zip is extracted into a temporary folder and smoke-tested
there (the CLI prints its version, the UI starts and quits with `--smoke`) with the user profile pointed at an empty
fake profile. The build fails if a shipped text file mentions this machine's home folder, or if running the app
writes into its own folder.

Usage: uv run --group build python tools/build_release.py [--no-smoke]
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DIST = ROOT / "dist"
APP = DIST / "ds1rand"
TEXT_SUFFIXES = {".json", ".txt", ".md", ".toml", ".ini", ".cfg", ".xml"}


def soulstruct_config() -> dict:
    """soulstruct's default config with nothing machine-specific: file logging off, no log path in the user folder."""
    from soulstruct.config import SoulstructConfig

    config = SoulstructConfig().to_dict()
    config.update(AUTO_SETUP_LOG=False, LOG_PATH="soulstruct.log")
    return config


def check_no_home_paths(folder: Path) -> None:
    home = str(Path.home())
    needles = {home, home.replace("\\", "\\\\"), home.replace("\\", "/")}
    for path in folder.rglob("*"):
        if path.is_file() and path.suffix.lower() in TEXT_SUFFIXES:
            text = path.read_text(encoding="utf-8", errors="ignore")
            leaked = [n for n in needles if n in text]
            if leaked:
                raise SystemExit(f"{path} contains this machine's home folder ({leaked[0]})")


def smoke_test(archive: Path, version: str) -> None:
    with tempfile.TemporaryDirectory(prefix="ds1rand-smoke-") as tmp:
        tmp = Path(tmp)
        with zipfile.ZipFile(archive) as zf:
            zf.extractall(tmp / "release")
        app = tmp / "release" / "ds1rand"
        before = {p: p.stat().st_mtime_ns for p in app.rglob("*")}
        profile = tmp / "fake-user"  # never created: anything writing under the user profile fails like it would
        env = {**os.environ, "QT_QPA_PLATFORM": "offscreen", "USERPROFILE": str(profile), "HOME": str(profile),
               "APPDATA": str(profile / "AppData" / "Roaming"), "LOCALAPPDATA": str(profile / "AppData" / "Local")}
        out = subprocess.run([str(app / "ds1rand-cli.exe"), "--version"], capture_output=True, text=True, env=env,
                             cwd=tmp)
        if out.returncode or out.stdout.strip() != f"ds1rand {version}":
            raise SystemExit(f"CLI smoke test failed:\n{out.stdout}\n{out.stderr}")
        ui = subprocess.run([str(app / "ds1rand.exe"), "--smoke"], capture_output=True, text=True, env=env, cwd=tmp,
                            timeout=120)
        if ui.returncode:
            raise SystemExit(f"UI smoke test failed:\n{ui.stdout}\n{ui.stderr}")
        after = {p: p.stat().st_mtime_ns for p in app.rglob("*")}
        written = sorted(str(p.relative_to(app)) for p in after if before.get(p) != after[p])
        if written:
            raise SystemExit(f"Running the app wrote into its folder: {written}")
        print(f"Smoke test passed from a fresh extract: ds1rand {version}, UI starts, nothing written")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--no-smoke", action="store_true")
    args = parser.parse_args()
    sys.path.insert(0, str(ROOT))
    from ds1rand import __version__

    subprocess.run([sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--distpath", str(DIST),
                    "--workpath", str(ROOT / "build"), str(ROOT / "packaging" / "ds1rand.spec")], check=True)
    shutil.copy(ROOT / "README.md", APP / "README.md")
    (APP / "soulstruct_config.json").write_text(json.dumps(soulstruct_config(), indent=4) + "\n", encoding="utf-8")
    check_no_home_paths(APP)

    archive = DIST / f"ds1rand-{__version__}-win64.zip"
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in sorted(APP.rglob("*")):
            zf.write(path, Path("ds1rand") / path.relative_to(APP))
    print(f"Wrote {archive} ({archive.stat().st_size / 2**20:.0f} MB)")
    if not args.no_smoke:
        smoke_test(archive, __version__)


if __name__ == "__main__":
    main()

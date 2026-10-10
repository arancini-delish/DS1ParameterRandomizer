"""A seed gives the same output in every process: nothing may depend on Python's per-process string hashing (set
iteration order of graph nodes). Runs every feature in two processes with different hash seeds."""
import hashlib
import os
import subprocess
import sys

SNIPPET = """
import hashlib, json, sys
from pathlib import Path
from ds1rand.io.install import GameInstall
from tests.conftest import RedirectedInstall
from ds1rand.presets.schema import BUILTIN, Preset
from ds1rand.run import run
install = RedirectedInstall(GameInstall.default().root, Path(sys.argv[1]))
preset = Preset.from_dict(BUILTIN["Standard"].to_dict())
preset.seed = 11
result = run(preset, install, out_dir=Path(sys.argv[1]) / "out", log=lambda _: None, spoiler=False)
changes = result.session.store.changes()
print(hashlib.sha256(json.dumps({p: {str(k): v for k, v in rows.items()} for p, rows in sorted(changes.items())},
                                sort_keys=True, default=str).encode()).hexdigest())
"""


def _digest(redirected_install, tmp_path, hash_seed: str) -> str:
    import shutil

    work = tmp_path / hash_seed
    work.mkdir()
    shutil.copy(redirected_install.gameparam, work / "GameParam.parambnd.dcx")
    shutil.copy(redirected_install.item_msgbnd, work / "item.msgbnd.dcx")
    env = {**os.environ, "PYTHONHASHSEED": hash_seed}
    out = subprocess.run([sys.executable, "-c", SNIPPET, str(work)], env=env, capture_output=True, text=True,
                         check=True, cwd=os.path.dirname(os.path.dirname(__file__)))
    output = out.stdout.strip().splitlines()[-1]
    data = (work / "out" / "param" / "GameParam" / "GameParam.parambnd.dcx").read_bytes()
    return output + hashlib.sha256(data).hexdigest()


def test_same_output_across_processes(redirected_install, tmp_path):
    assert _digest(redirected_install, tmp_path, "1") == _digest(redirected_install, tmp_path, "2")

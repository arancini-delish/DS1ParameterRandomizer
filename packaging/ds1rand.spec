# PyInstaller spec: one folder holding ds1rand.exe (windowed UI) and ds1rand-cli.exe (command line), sharing one
# runtime. Build with `uv run python tools/build_release.py` (or `uv run pyinstaller packaging/ds1rand.spec`).
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

ROOT = Path(SPECPATH).parent
PARAMDEFS = ROOT / "ds1paramdefs"

datas = [
    (str(ROOT / "data" / "baseline"), "data/baseline"),
    (str(ROOT / "data" / "catalogue"), "data/catalogue"),
    (str(PARAMDEFS / "Defs"), "ds1paramdefs/Defs"),
    (str(PARAMDEFS / "Meta"), "ds1paramdefs/Meta"),
    (str(PARAMDEFS / "Community Row Names"), "ds1paramdefs/Community Row Names"),
    (str(PARAMDEFS / "Shared Param Enums.json"), "ds1paramdefs"),
] + collect_data_files("soulstruct")

# soulstruct picks game modules by name at run time; only the Dark Souls ones (and the shared base) are needed.
hiddenimports = [m for m in collect_submodules("soulstruct")
                 if m.split(".")[1:2] in (["base"], ["containers"], ["darksouls1r"], ["darksouls1ptde"], ["utilities"],
                                          ["dcx"], ["config"], ["games"], ["logging_utils"], ["exceptions"],
                                          ["version"], ["flver"], [])]

# Qt modules ds1rand does not use.
excludes = ["PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets", "PySide6.QtQml", "PySide6.QtQuick",
            "PySide6.Qt3DCore", "PySide6.QtMultimedia", "PySide6.QtPdf", "PySide6.QtCharts",
            "PySide6.QtDataVisualization", "PySide6.QtBluetooth", "tkinter", "matplotlib", "numpy.tests"]

analysis = Analysis(
    [str(ROOT / "packaging" / "ds1rand_gui.py"), str(ROOT / "packaging" / "ds1rand_cli.py")],
    pathex=[str(ROOT)],
    datas=datas,
    hiddenimports=hiddenimports,
    excludes=excludes,
)
pyz = PYZ(analysis.pure)
gui_script, cli_script = analysis.scripts[-2], analysis.scripts[-1]
common = [s for s in analysis.scripts[:-2]]
gui = EXE(pyz, common + [gui_script], exclude_binaries=True, name="ds1rand", console=False)
cli = EXE(pyz, common + [cli_script], exclude_binaries=True, name="ds1rand-cli", console=True)
COLLECT(gui, cli, analysis.binaries, analysis.datas, name="ds1rand")

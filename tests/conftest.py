import pytest

from ds1rand.io.install import GameInstall


@pytest.fixture(scope="session")
def install() -> GameInstall:
    """The local DSR install (`DS1R_GAME_DIR` or the default Steam path). Tests needing it skip if it is absent."""
    install = GameInstall.default()
    if install.missing_files():
        pytest.skip(f"No DSR install at {install.root}; set DS1R_GAME_DIR")
    return install


@pytest.fixture(scope="session")
def vanilla_gameparam(install):
    """The install's GameParam, or its `.bak`, whichever matches the vanilla baseline (skips if neither does)."""
    from ds1rand.baseline.store import Baseline, sha256_file

    vanilla = Baseline.load().manifest["sources"]["GameParam.parambnd.dcx"]
    for candidate in (install.gameparam, install.gameparam.with_name(install.gameparam.name + ".bak")):
        if candidate.is_file() and sha256_file(candidate) == vanilla:
            return candidate
    pytest.skip("No vanilla GameParam in the install")


class RedirectedInstall(GameInstall):
    """The real install for events/maps/animations/AI, with GameParam and item text redirected to copies in `files`,
    so sessions can write without touching the game folder."""

    def __init__(self, root, files):
        object.__setattr__(self, "root", root)
        object.__setattr__(self, "_files", files)

    @property
    def gameparam(self):
        return self._files / "GameParam.parambnd.dcx"

    @property
    def item_msgbnd(self):
        return self._files / "item.msgbnd.dcx"


@pytest.fixture
def redirected_install(install, vanilla_gameparam, tmp_path):
    """Redirected install starting from the vanilla GameParam and the installed item text."""
    import shutil

    redirected = RedirectedInstall(install.root, tmp_path)
    shutil.copy(vanilla_gameparam, redirected.gameparam)
    shutil.copy(install.item_msgbnd, redirected.item_msgbnd)
    return redirected

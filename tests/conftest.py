import pytest

from ds1rand.io.install import GameInstall


@pytest.fixture(scope="session")
def install() -> GameInstall:
    """The local DSR install (`DS1R_GAME_DIR` or the default Steam path). Tests needing it skip if it is absent."""
    install = GameInstall.default()
    if install.missing_files():
        pytest.skip(f"No DSR install at {install.root}; set DS1R_GAME_DIR")
    return install

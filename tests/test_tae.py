import pytest
from soulstruct.containers import Binder

from ds1rand.io.tae import TAE


@pytest.fixture(scope="module")
def stray_demon_tae(install) -> TAE:
    binder = Binder.from_path(install.root / "chr" / "c2230.anibnd.dcx")
    return TAE.from_bytes(bytes(next(e for e in binder.entries if e.name.lower().endswith(".tae"))))


def test_reads_dsr_tae(stray_demon_tae):
    assert stray_demon_tae.id == 202230
    assert len(stray_demon_tae.animations) == 38
    first = stray_demon_tae.animations[0]
    assert first.id == 0
    assert [e.type for e in first.events] == [16, 128]
    assert first.events[1].params[:2] == (1, 223005000)  # sound event
    assert (first.events[1].start, round(first.events[1].end, 3)) == (1.5, 1.6)


def test_rejects_other_versions():
    data = bytearray(b"TAE " + bytes(0x60))
    data[8:12] = (0x1000C).to_bytes(4, "little")
    with pytest.raises(ValueError, match="version"):
        TAE.from_bytes(bytes(data))

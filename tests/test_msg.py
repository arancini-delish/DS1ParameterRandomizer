import pytest

from ds1rand.io.msg import CATEGORIES, ItemText


@pytest.fixture
def text(install) -> ItemText:
    return ItemText.from_path(install.item_msgbnd)


def test_categories():
    assert CATEGORIES["Accessory_name"] == 13
    assert CATEGORIES["Accessory_description"] == 23
    assert CATEGORIES["Magic_description"] == 28


def test_ring_names_present(text):
    # Ring IDs 100+ are EquipParamAccessory rows; every vanilla ring has a name.
    assert text.get("Accessory_name", 100)
    assert text.get("Accessory_name", 999_999) is None


def test_set_updates_base_and_patch(text, tmp_path):
    text.set("Accessory_description", 100, "Physical Defense: +50")
    text.set("Magic_description", 3000, "Unpatched category")
    out = tmp_path / "item.msgbnd.dcx"
    text.save(out)

    saved = ItemText.from_path(out)
    assert saved.get("Accessory_description", 100) == "Physical Defense: +50"
    assert saved._fmgs[23].entries[100] == saved._fmgs[112].entries[100] == "Physical Defense: +50"
    assert saved.get("Magic_description", 3000) == "Unpatched category"

"""Our first test. pytest runs every function whose name starts with test_."""

from ky_ree import config


def test_data_folders_exist():
    assert config.RAW_DIR.exists()
    assert config.PROCESSED_DIR.exists()


def test_ree_list_has_lanthanides_plus_y_and_sc():
    assert len(config.REE_ELEMENTS) == 17
    assert "Nd" in config.REE_ELEMENTS  # neodymium, used in magnets

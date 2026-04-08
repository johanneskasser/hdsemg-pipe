import pytest
from hdsemg_pipe.actions.file_grouping import get_group_key, shorten_group_labels


def test_get_group_key_strips_trailing_number():
    assert get_group_key("Block1_Pyramid_3.mat") == "Block1_Pyramid"


def test_get_group_key_no_trailing_number():
    assert get_group_key("Block1_Pyramid.mat") == "Block1_Pyramid"


def test_get_group_key_full_path():
    assert get_group_key("/data/1_20260202_FT_Block1_Pyramid_2.json") == "1_20260202_FT_Block1_Pyramid"


def test_shorten_group_labels_strips_common_prefix():
    keys = ["2_20260216_130218_FT_Block1_Pyramid", "2_20260216_130218_FT_Block1_Trapezoid"]
    labels = shorten_group_labels(keys)
    assert labels["2_20260216_130218_FT_Block1_Pyramid"] == "Pyramid"
    assert labels["2_20260216_130218_FT_Block1_Trapezoid"] == "Trapezoid"


def test_shorten_group_labels_empty():
    assert shorten_group_labels([]) == {}


def test_shorten_group_labels_single_key():
    labels = shorten_group_labels(["only_key"])
    assert labels["only_key"] == "key"

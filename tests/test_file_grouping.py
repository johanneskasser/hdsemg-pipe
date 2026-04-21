import pytest
from hdsemg_pipe.actions.file_grouping import build_auto_mapping, get_group_key, shorten_group_labels


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


class TestBuildAutoMapping:
    def test_unambiguous_mapping(self):
        decomp_files = [
            "stem1_8mm_4x8.json",
            "stem1_8mm_4x8_2.json",
            "stem1_8mm_13x5.json",
        ]
        chan_files = ["stem1.mat"]
        result = build_auto_mapping(decomp_files, chan_files)
        assert result == {
            "stem1_8mm_4x8.json": "stem1.mat",
            "stem1_8mm_4x8_2.json": "stem1.mat",
            "stem1_8mm_13x5.json": "stem1.mat",
        }

    def test_multiple_sessions_mapped_correctly(self):
        decomp_files = [
            "subject1_8mm_4x8.json",
            "subject2_8mm_4x8.json",
        ]
        chan_files = ["subject1.mat", "subject2.mat"]
        result = build_auto_mapping(decomp_files, chan_files)
        assert result == {
            "subject1_8mm_4x8.json": "subject1.mat",
            "subject2_8mm_4x8.json": "subject2.mat",
        }

    def test_ambiguous_returns_none(self):
        decomp_files = ["stem1_8mm_4x8.json"]
        chan_files = ["stem1_trial1.mat", "stem1_trial2.mat"]
        result = build_auto_mapping(decomp_files, chan_files)
        assert result is None

    def test_no_match_returns_none(self):
        decomp_files = ["stem1_8mm_4x8.json"]
        chan_files = ["completely_different.mat"]
        result = build_auto_mapping(decomp_files, chan_files)
        assert result is None

    def test_empty_decomp_files_returns_empty_dict(self):
        result = build_auto_mapping([], ["stem1.mat"])
        assert result == {}

    def test_pkl_files_supported(self):
        decomp_files = ["stem1_8mm_4x8.pkl"]
        chan_files = ["stem1.mat"]
        result = build_auto_mapping(decomp_files, chan_files)
        assert result == {"stem1_8mm_4x8.pkl": "stem1.mat"}

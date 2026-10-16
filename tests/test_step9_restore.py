import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np
import pandas as pd
import pytest
from PyQt5.QtWidgets import QApplication

import hdsemg_pipe.widgets.wizard.FileQualitySelectionWizardWidget  # noqa: F401  (binds matplotlib to PyQt5 first)
from hdsemg_pipe.state.global_state import global_state
from hdsemg_pipe.widgets.wizard import MUQualityReviewWizardWidget as mod

NAMES = ["rec_1_a.json", "rec_1_b.json", "rec_2_a.json"]
_APP = QApplication.instance() or QApplication([])  # keep a reference, or Qt tears it down


@pytest.fixture
def widget(tmp_path):
    w = mod.MUQualityReviewWizardWidget()
    files = [str(tmp_path / "decomposition_auto" / n) for n in NAMES]
    for fp in files:  # pre-fill the caches so nothing is loaded from disk
        w._reliability_cache[fp] = pd.DataFrame({
            "mu_index": range(3), "port_index": 0, "sil": [0.95] * 3, "pnr": [40.0] * 3,
            "covisi": [20.0, 20.0, 20.0], "dr_mean": [10.0] * 3, "n_spikes": [300] * 3, "is_reliable": True,
        })
        w._emgfile_cache[fp] = None
    w._populate_file_list(files)
    return w, files


def test_restore_maps_stale_manifest_paths_onto_current_files(widget):
    w, files = widget
    manifest = {  # written in a workfolder that has since been renamed
        "kept_files": ["rec_1_a.json", "rec_2_a.json"],
        "mu_overrides": {r"D:\old\folder-2026\decomposition_auto\rec_1_a.json": {"1": "Filter"}},
    }

    w.restore_from_manifest(manifest)

    assert [w._checked[f] for f in files] == [True, False, True]
    assert w._overrides == {files[0]: {"1": "Filter"}}
    # the table of the current file already reflects the restored override
    assert w._current_file == files[0]
    assert w._mu_table.item(1, 6).text() == "Filter *"


def test_proceed_passes_overrides_keyed_by_file_name(widget, tmp_path, monkeypatch):
    w, files = widget
    w._overrides = {files[0]: {"1": "Keep"}, files[1]: {}}
    global_state.reset()
    global_state.workfolder = str(tmp_path)
    captured = {}

    class FakeSignal:
        def connect(self, *_): pass

    class FakeWorker:
        def __init__(self, **kwargs):
            captured.update(kwargs)
            self.finished = self.error = self.progress = FakeSignal()
        def start(self): pass

    monkeypatch.setattr(mod, "_ProceedWorker", FakeWorker)
    w._on_proceed()

    assert captured["overrides"] == {"rec_1_a.json": {"1": "Keep"}}   # the worker looks files up by name


def test_kept_files_fall_back_to_the_filtered_folder(tmp_path):
    folder = tmp_path / "filtered"
    folder.mkdir()
    for n in ("rec_1_a_covisi_filtered.json", "rec_2_a_covisi_filtered.json", "rec_2_a_covisi_filtered.pkl"):
        (folder / n).write_text("")

    assert mod._kept_names_from_filtered_folder(folder) == {"rec_1_a.json", "rec_2_a.json"}
    assert mod._kept_names_from_filtered_folder(tmp_path / "missing") == set()

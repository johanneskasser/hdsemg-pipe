import json
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PyQt5.QtTest import QTest
from PyQt5.QtWidgets import QApplication

from hdsemg_pipe.actions.enum.FolderNames import FolderNames
from hdsemg_pipe.state.global_state import global_state


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def _grid(drop):
    chans = [{"channel_index": i, "channel_number": i + 1, "selected": (i + 1) not in drop, "labels": []}
             for i in range(10)]
    return {"grid_key": "g", "rows": 2, "columns": 5, "inter_electrode_distance_mm": 8,
            "channels": chans, "reference_signals": []}


def test_step7_shows_restored_run_and_edit(app, tmp_path, monkeypatch):
    from hdsemg_pipe.widgets.wizard import ChannelSelectionWizardWidget as mod

    chan = tmp_path / FolderNames.CHANNELSELECTION.value
    (chan / "discarded").mkdir(parents=True)
    names = ["P_1_a.mat", "P_2_a.mat", "P_3_a.mat"]
    for n in names[:2]:
        (chan / n).write_text("")
        (chan / n.replace(".mat", ".json")).write_text(json.dumps({"grids": [_grid({3})]}))
    (chan / "discarded" / names[2]).write_text("")

    global_state.reset()
    global_state.workfolder = str(tmp_path)
    global_state.cropped_files = [str(tmp_path / n) for n in names]
    w = mod.ChannelSelectionWizardWidget()
    w.on_shown()
    QTest.qWait(50)
    for _ in range(100):  # wait for the background summary worker
        if w.summary_view.isVisibleTo(w):
            break
        QTest.qWait(50)

    view = w.summary_view
    assert view.isVisibleTo(w)
    assert [v.text() for v in view._fig.values()] == ["2", "1", "0"]
    assert len(view._rows) == 3

    view._filter_buttons["discarded"].click()
    assert [r.isVisibleTo(view) for r in view._rows] == [False, False, True]

    launched = []

    class FakeWorker:
        def __init__(self, path, output_path=None):
            launched.append((path, output_path))
            self.finished = type("S", (), {"connect": lambda *_: None})()
            self.failed = type("S", (), {"connect": lambda *_: None})()
        def start(self): pass
        def isRunning(self): return False

    monkeypatch.setattr(mod, "ChannelSelectionWorker", FakeWorker)
    view._filter_buttons[None].click()
    view._rows[0].edit_button.click()
    assert launched == [(str(chan / "P_1_a.mat"),) * 2]

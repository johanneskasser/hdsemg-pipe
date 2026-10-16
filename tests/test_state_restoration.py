import json
import os

from hdsemg_pipe.actions.channel_selection_summary import (
    DISCARDED, KEPT, PENDING, collect_channel_selection_summary,
)
from hdsemg_pipe.actions.load_helpers import rebase_paths_to_folder


def _touch(path, content=""):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as fh:
        fh.write(content)


def test_rebase_stale_windows_paths_onto_current_folder(tmp_path):
    folder = tmp_path / "ID641" / "line_noise_cleaned"
    _touch(str(folder / "a.mat"))
    stale = [
        r"D:\MU_TRAIL\folder-2026-03-16T20-17-21\line_noise_cleaned\a.mat",
        r"D:\MU_TRAIL\folder-2026-03-16T20-17-21\line_noise_cleaned\gone.mat",
    ]
    assert rebase_paths_to_folder(stale, str(folder)) == [os.path.normpath(str(folder / "a.mat"))]


def test_channel_selection_summary(tmp_path):
    chan = tmp_path / "channelselection"
    grid = {
        "grid_key": "8mm_4x8", "rows": 4, "columns": 8, "inter_electrode_distance_mm": 8,
        "channels": [
            {"channel_index": 0, "channel_number": 1, "selected": True, "labels": []},
            {"channel_index": 1, "channel_number": 2, "selected": False, "labels": ["bad"]},
        ],
        "reference_signals": [{"ref_index": 2, "selected": True}],
    }
    _touch(str(chan / "kept.mat"))
    _touch(str(chan / "kept.json"), json.dumps({"grids": [grid]}))
    _touch(str(chan / "discarded" / "bad.mat"))
    _touch(str(chan / "bad.json"), json.dumps({"grids": [grid]}))  # sidecar stays behind
    cropped = [str(tmp_path / n) for n in ("kept.mat", "bad.mat", "todo.mat")]

    kept, bad, todo = collect_channel_selection_summary(cropped, str(chan))

    assert (kept.status, bad.status, todo.status) == (KEPT, DISCARDED, PENDING)
    g = kept.grids[0]
    assert (g.n_selected, g.n_dropped, g.n_refs_selected, g.excluded_channels) == (1, 1, 1, [2])
    assert bad.has_sidecar and todo.grids == []

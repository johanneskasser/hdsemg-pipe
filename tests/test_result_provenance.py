import json

import numpy as np
import openhdemg.library as emg
import pandas as pd

from hdsemg_pipe.actions.decomposition_export import extract_grid_metadata_from_extras
from hdsemg_pipe.actions.result_provenance import (
    PROVENANCE_KEY, annotate_result_json, detect_route, read_channel_set,
)


def _write_result(path, extras_cell):
    n = 20
    emgfile = {
        "SOURCE": "OPENHDEMG", "FILENAME": "D:\\x\\decomposition_muedit\\a.mat",
        "RAW_SIGNAL": pd.DataFrame(np.zeros((n, 3))), "REF_SIGNAL": pd.DataFrame(np.zeros((n, 1))),
        "ACCURACY": pd.DataFrame(np.zeros((1, 1))), "IPTS": pd.DataFrame(np.zeros((n, 1))),
        "MUPULSES": [np.array([1, 5])], "FSAMP": 2048.0, "IED": 8.0, "EMG_LENGTH": n,
        "NUMBER_OF_MUS": 1, "BINARY_MUS_FIRING": pd.DataFrame(np.zeros((n, 1))),
        "EXTRAS": pd.DataFrame([extras_cell]),
    }
    emg.save_json_emgfile(emgfile, str(path), compresslevel=4)


def _sidecar(tmp_path):
    mat = tmp_path / "rec.mat"
    mat.write_text("")
    chans = [{"channel_index": i, "selected": i != 1} for i in range(3)]
    (tmp_path / "rec.json").write_text(json.dumps({"grids": [{"grid_key": "8mm_1x3", "channels": chans}]}))
    return str(mat)


def test_read_channel_set(tmp_path):
    cs = read_channel_set(_sidecar(tmp_path))
    assert cs == [{"grid_key": "8mm_1x3", "n_channels_total": 3, "selected_channel_indices": [0, 2]}]
    assert read_channel_set(str(tmp_path / "missing.mat")) is None


def test_annotate_survives_openhdemg_roundtrip(tmp_path):
    res = tmp_path / "res.json"
    _write_result(res, json.dumps({"grids": [{"file_name": "g.mat", "rows": 1, "cols": 3}]}))
    assert annotate_result_json(str(res), _sidecar(tmp_path))

    loaded = emg.emg_from_json(str(res))
    cell = json.loads(str(loaded["EXTRAS"].iloc[0, 0]))
    prov = cell[PROVENANCE_KEY]
    assert prov["decomposition_route"] == "muedit"
    assert prov["channel_set"][0]["selected_channel_indices"] == [0, 2]
    # existing grid metadata still parses, and a re-save keeps the provenance
    assert extract_grid_metadata_from_extras(loaded["EXTRAS"])["ngrid"] == 1
    emg.save_json_emgfile(loaded, str(res), compresslevel=4)
    assert PROVENANCE_KEY in json.loads(str(emg.emg_from_json(str(res))["EXTRAS"].iloc[0, 0]))


def test_annotate_skips_files_without_json_extras(tmp_path):
    res = tmp_path / "res.json"
    _write_result(res, "not json")
    assert annotate_result_json(str(res)) is False


def test_detect_route(tmp_path):
    j = tmp_path / "a.json"
    assert detect_route(str(j), "x\\decomposition_muedit\\a") == "muedit"
    assert detect_route(str(j), "x") == "unknown"
    (tmp_path / "a.pkl").write_text("")
    assert detect_route(str(j), "x") == "scd-edition"

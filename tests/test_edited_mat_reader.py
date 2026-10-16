"""MUedit-edited MAT files store Pulsetrainclean in different shapes; the reader must handle all of them."""
import h5py
import numpy as np
import pytest

from hdsemg_pipe.actions.decomposition_file import DecompositionFile, ReliabilityThresholds

T, N_MU = 2000, 3


def _cell(f, parent, name, items):
    """Write a MATLAB-style cell (HDF5 object-reference dataset) of arrays, h5py-view shape (n, 1)."""
    refs = f.require_group("#refs#")
    ds = parent.create_dataset(name, (len(items), 1), dtype=h5py.ref_dtype)
    for i, arr in enumerate(items):
        r = refs.create_dataset(f"{name}_{i}", data=arr)
        ds[i, 0] = r.ref
    return ds


def _nest(f, parent, name, inner):
    """1x1 cell whose single element is `inner` (a dataset)."""
    ds = parent.create_dataset(name, (1, 1), dtype=h5py.ref_dtype)
    ds[0, 0] = inner.ref
    return ds


def _make_edited_mat(path, layout, flat_discharge=False):
    rng = np.random.default_rng(0)
    discharges = [np.arange(50 + 7 * k, T - 10, 30 + 5 * k) for k in range(N_MU)]
    trains = np.zeros((T, N_MU))
    for k, d in enumerate(discharges):
        trains[:, k] = rng.normal(0, 0.05, T)
        trains[d, k] += 1.0
    with h5py.File(path, "w") as f:
        ed = f.create_group("edition")
        ed.create_dataset("time", data=np.arange(T, dtype=float).reshape(-1, 1))
        # Distimeclean: nested (1x1 -> cell of per-MU times) or flat; MATLAB is 1-based.
        # MU 1 has no discharges (empty) to check that order is preserved.
        times = [(d + 1).astype(float).reshape(-1, 1) for d in discharges]
        times[1] = np.zeros((0, 1))
        if flat_discharge:
            _cell(f, ed, "Distimeclean", times)
        else:
            _nest(f, ed, "Distimeclean", _cell(f, f.require_group("#refs#"), "dtc_inner", times))
        # Pulsetrainclean, as written by different MUedit versions (h5py view is (T, nMU)):
        refs = f.require_group("#refs#")
        if layout == "nested_cell":        # 1x1 -> cell of matrices
            _nest(f, ed, "Pulsetrainclean", _cell(f, refs, "ptc_inner", [trains]))
        elif layout == "nested_matrix":    # 1x1 -> the matrix itself
            _nest(f, ed, "Pulsetrainclean", refs.create_dataset("ptc_inner", data=trains))
        elif layout == "flat_cell":        # cell of (nMU, T) matrices, one per grid (previous reader's assumption)
            _cell(f, ed, "Pulsetrainclean", [trains.T[:2], trains.T[2:]])
        elif layout == "flat_cell_time_first":  # same, but (T, nMU) per grid
            _cell(f, ed, "Pulsetrainclean", [trains[:, :2], trains[:, 2:]])
        elif layout == "flat_cell_per_mu":  # cell of one pulse-train vector per MU
            _cell(f, ed, "Pulsetrainclean", [trains[:, k] for k in range(N_MU)])
        _cell(f, ed, "silval", [np.array([[0.95]])] * N_MU)


@pytest.mark.parametrize("layout", ["nested_cell", "nested_matrix", "flat_cell", "flat_cell_time_first", "flat_cell_per_mu"])
def test_sil_pnr_available_for_every_pulsetrainclean_layout(tmp_path, layout):
    path = tmp_path / "rec_muedit.mat_edited.mat"
    _make_edited_mat(path, layout)

    df = DecompositionFile.load(path).compute_reliability(ReliabilityThresholds())

    assert len(df) == N_MU
    with_spikes = df[df["n_spikes"] > 0]          # MU 1 is empty by construction
    assert list(with_spikes["mu_index"]) == [0, 2]
    assert with_spikes["sil"].notna().all() and with_spikes["pnr"].notna().all()


@pytest.mark.parametrize("flat_discharge", [False, True])
def test_discharge_times_keep_mu_order_for_nested_and_flat_cells(tmp_path, flat_discharge):
    from hdsemg_pipe.actions.decomposition_file import _read_mat_edited_h5py

    path = tmp_path / "rec_muedit.mat_edited.mat"
    _make_edited_mat(path, "nested_cell", flat_discharge=flat_discharge)

    ef = _read_mat_edited_h5py(path)

    assert [len(p) for p in ef["MUPULSES"]][1] == 0       # the empty MU stays at index 1
    assert len(ef["MUPULSES"][0]) > 0 and len(ef["MUPULSES"][2]) > 0
    assert ef["IPTS"].shape == (T, N_MU)


def _add_original_signal(f, n_mu):
    """The original (pre-edit) `signal` struct that MUedit keeps inside *_edited.mat files."""
    rng = np.random.default_rng(1)
    refs = f.require_group("#refs#")
    sig = f.create_group("signal")
    sig.create_dataset("fsamp", data=np.array([[2048.0]]))
    trains = rng.normal(0, 0.05, (T, n_mu))           # h5py view of MATLAB (nMU x T)
    discharges = [np.arange(40 + 5 * k, T - 10, 28 + 3 * k) for k in range(n_mu)]
    for k, d in enumerate(discharges):
        trains[d, k] += 1.0
    _nest(f, sig, "Pulsetrain", refs.create_dataset("sig_pt", data=trains))
    _cell(f, sig, "Dischargetimes", [(d + 1).astype(float).reshape(-1, 1) for d in discharges])
    return discharges


def test_edited_file_that_also_contains_signal_is_read_as_edited(tmp_path):
    """*_edited.mat keeps the original `signal` next to `edition`; the edited data must win."""
    path = tmp_path / "rec_muedit.mat_edited.mat"
    _make_edited_mat(path, "nested_cell")
    with h5py.File(path, "a") as f:
        _add_original_signal(f, N_MU + 1)             # original had one more MU before cleaning

    df = DecompositionFile.load(path).compute_reliability(ReliabilityThresholds())

    assert len(df) == N_MU


def test_unedited_signal_reader_handles_time_first_pulsetrain(tmp_path):
    from hdsemg_pipe.actions.decomposition_file import _read_mat_signal_h5py

    path = tmp_path / "rec_muedit.mat"
    with h5py.File(path, "w") as f:
        discharges = _add_original_signal(f, N_MU)

    ef = _read_mat_signal_h5py(path)

    assert ef["NUMBER_OF_MUS"] == N_MU
    assert ef["EMG_LENGTH"] == T
    assert ef["IPTS"].shape == (T, N_MU)
    assert [len(p) for p in ef["MUPULSES"]] == [len(d) for d in discharges]

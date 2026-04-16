"""
DecompositionFile -- format-agnostic wrapper over openhdemg JSON, scd-edition PKL, and
MUedit MAT files.

All three backends expose the same public interface so that wizard steps can
work with either format without conditional branching at the call site.

Backends
--------
JSON  -- openhdemg .json files (existing MUedit pathway, unchanged)
PKL   -- multi-port scd-edition .pkl files produced by merge_grid_pkls
MAT   -- MUedit-exported .mat files (pulsetrain format or edited format)

Note: PKL files are trusted internal SCD decomposition outputs, not
user-supplied data.  The pickle module is used only for these internal files.
"""

from __future__ import annotations

import copy
import math
import pickle  # SCD result files are trusted internal outputs
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import List, Optional

import numpy as np
import pandas as pd

from hdsemg_pipe._log.log_config import logger

try:
    import openhdemg.library as emg

    _OPENHDEMG_AVAILABLE = True
except ImportError:
    _OPENHDEMG_AVAILABLE = False
    logger.warning("openhdemg not available -- JSON backend disabled")

try:
    import h5py
    import scipy.io as sio

    _H5PY_AVAILABLE = True
except ImportError:
    _H5PY_AVAILABLE = False

# -------------------------------------------------------------------------
# MAT subtype constants
# -------------------------------------------------------------------------
_MAT_PULSETRAIN = "pulsetrain"   # *_muedit.mat  -- signal.Dischargetimes
_MAT_EDITED = "edited"           # *_muedit.mat_edited.mat -- edition.Distimeclean
_MAT_UNKNOWN = "unknown"


def _detect_mat_subtype(path: Path) -> str:
    """Inspect a MAT file and return its subtype string."""
    if not _H5PY_AVAILABLE:
        return _MAT_UNKNOWN

    # Try legacy scipy format first
    try:
        mat_data = sio.loadmat(str(path), squeeze_me=True, struct_as_record=False)
        if "signal" in mat_data and hasattr(mat_data["signal"], "Dischargetimes"):
            return _MAT_PULSETRAIN
        if "edition" in mat_data:
            return _MAT_EDITED
    except Exception:
        pass

    # HDF5/v7.3 format
    try:
        with h5py.File(str(path), "r") as f:
            if "signal" in f and "Dischargetimes" in f["signal"]:
                return _MAT_PULSETRAIN
            if "edition" in f and "Distimeclean" in f["edition"]:
                return _MAT_EDITED
    except Exception:
        pass

    return _MAT_UNKNOWN


# -------------------------------------------------------------------------
# Helpers
# -------------------------------------------------------------------------

def _cov_isi(timestamps: np.ndarray) -> float:
    """Return CoV of ISI in percent, or NaN when fewer than 2 spikes."""
    ts = np.asarray(timestamps, dtype=np.int64).flatten()
    ts = np.sort(ts)
    if len(ts) < 2:
        return float("nan")
    isi = np.diff(ts)
    mean_isi = float(np.mean(isi))
    if mean_isi == 0:
        return float("nan")
    return float(np.std(isi) / mean_isi * 100.0)


def _load_ref_signal_from_sibling_json(json_path: Path) -> pd.DataFrame:
    """Read only the REF_SIGNAL field from a sibling openhdemg JSON without loading full EMG."""
    if not json_path.exists():
        return pd.DataFrame()
    try:
        import gzip
        import json as _json
        import io
        with gzip.open(str(json_path), "rt", encoding="utf-8") as fh:
            raw = _json.load(fh)
        ref_str = raw.get("REF_SIGNAL")
        if not ref_str:
            return pd.DataFrame()
        ref_df = pd.read_json(io.StringIO(ref_str), orient="split")
        if not ref_df.empty:
            return ref_df
    except Exception as exc:
        logger.debug("Could not load REF_SIGNAL from %s: %s", json_path.name, exc)
    return pd.DataFrame()


def _parse_ied_from_port_name(port_name: str) -> float:
    """Parse inter-electrode distance from port name like '10mm_4x8' -> 10.0."""
    import re
    m = re.match(r'(\d+)mm', str(port_name))
    return float(m.group(1)) if m else 0.0


def _extract_raw_signal_for_port(pkl: dict, port_idx: int) -> pd.DataFrame:
    """Extract per-port EMG as openhdemg RAW_SIGNAL DataFrame (samples × channels).

    The merged PKL stores all ports' EMG stacked in ``data`` (total_ch × n_samples).
    ``channel_indices[port_idx]`` holds the global column indices for that port.
    """
    data = pkl.get("data")
    if data is None:
        return pd.DataFrame()
    emg_array = np.asarray(data)
    if emg_array.ndim != 2:
        return pd.DataFrame()
    channel_indices = pkl.get("channel_indices", [])
    if port_idx >= len(channel_indices):
        return pd.DataFrame()
    ci = channel_indices[port_idx]
    if ci is None or len(ci) == 0:
        return pd.DataFrame()
    try:
        port_emg = emg_array[ci, :]   # (n_ch, n_samples)
        return pd.DataFrame(port_emg.T)  # (n_samples, n_ch) — openhdemg convention
    except Exception:
        return pd.DataFrame()


def _infer_emg_length_from_pkl(pkl: dict, port_idx: int) -> int:
    """Infer EMG length (number of samples) from a merged PKL dict."""
    pulse_trains = pkl.get("pulse_trains", [])
    if port_idx < len(pulse_trains):
        for pt in pulse_trains[port_idx]:
            arr = np.asarray(pt)
            if arr.size > 0:
                return int(arr.size)

    data = pkl.get("data")
    if data is not None:
        arr = np.asarray(data)
        if arr.ndim == 2:
            return int(arr.shape[1])

    return 0


def _build_binary_mus_firing(mupulses: List[np.ndarray], emg_length: int) -> pd.DataFrame:
    """Reconstruct BINARY_MUS_FIRING DataFrame (time x nMU) from MUPULSES."""
    n_mu = len(mupulses)
    if n_mu == 0 or emg_length == 0:
        return pd.DataFrame()
    mat = np.zeros((emg_length, n_mu), dtype=np.int32)
    for mu_idx, pulses in enumerate(mupulses):
        indices = np.asarray(pulses, dtype=np.int64).flatten()
        valid = indices[(indices >= 0) & (indices < emg_length)]
        mat[valid, mu_idx] = 1
    return pd.DataFrame(mat)


def _pkl_to_emgfile_dict(pkl: dict, port_idx: int, port_name: str,
                         ref_signal: Optional[pd.DataFrame] = None) -> dict:
    """Reconstruct a minimal openhdemg-compatible dict from one port of a PKL."""
    fsamp = float(pkl.get("sampling_rate", 2000))

    discharge_times = pkl.get("discharge_times", [])
    pulse_trains_all = pkl.get("pulse_trains", [])

    dt_port = discharge_times[port_idx] if port_idx < len(discharge_times) else []
    pt_port = pulse_trains_all[port_idx] if port_idx < len(pulse_trains_all) else []

    n_mus = len(dt_port)

    # MUPULSES: 0-based sample indices
    mupulses = [
        np.asarray(dt, dtype=np.int64).flatten()
        for dt in dt_port
    ]

    emg_length = _infer_emg_length_from_pkl(pkl, port_idx)

    # IPTS: pulse trains as DataFrame (time x nMU)
    if n_mus > 0 and len(pt_port) > 0:
        max_len = max(
            (np.asarray(pt).size for pt in pt_port if np.asarray(pt).size > 0),
            default=0,
        )
        if max_len == 0:
            max_len = emg_length
        ipts_mat = np.zeros((max_len, n_mus), dtype=np.float64)
        for mu_idx, pt in enumerate(pt_port):
            arr = np.asarray(pt, dtype=np.float64).flatten()
            length = min(len(arr), max_len)
            ipts_mat[:length, mu_idx] = arr[:length]
        ipts_df = pd.DataFrame(ipts_mat)
        if emg_length == 0:
            emg_length = max_len
    else:
        ipts_df = pd.DataFrame()

    binary_mus_firing = _build_binary_mus_firing(mupulses, emg_length)

    raw_signal = _extract_raw_signal_for_port(pkl, port_idx)
    ied = _parse_ied_from_port_name(port_name)
    if ref_signal is None or ref_signal.empty:
        ref_signal_length = emg_length if emg_length > 0 else 1
        ref_signal = pd.DataFrame(np.zeros((ref_signal_length, 1), dtype=np.float64))

    return {
        "SOURCE": "OTB",
        "FILENAME": port_name,
        "FSAMP": fsamp,
        "IED": ied,
        "NUMBER_OF_MUS": n_mus,
        "EMG_LENGTH": emg_length,
        "MUPULSES": mupulses,
        "IPTS": ipts_df,
        "BINARY_MUS_FIRING": binary_mus_firing,
        "RAW_SIGNAL": raw_signal,
        "REF_SIGNAL": ref_signal,
        "ACCURACY": pd.DataFrame(np.zeros((n_mus, 1)) if n_mus > 0 else np.empty((0, 1))),
        "EXTRAS": pd.DataFrame(),
    }


# -------------------------------------------------------------------------
# Reliability thresholds
# -------------------------------------------------------------------------

@dataclass(frozen=True)
class ReliabilityThresholds:
    """Thresholds for multi-metric MU reliability filtering.

    A MU is considered reliable if all *enabled* criteria pass (OR logic on
    failure: filtered if ANY enabled criterion fails).
    """

    sil_min: float = 0.9
    pnr_min: float = 30.0
    covisi_max: float = 30.0
    sil_enabled: bool = True
    pnr_enabled: bool = True
    covisi_enabled: bool = True

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "ReliabilityThresholds":
        valid = {f for f in cls.__dataclass_fields__}  # type: ignore[attr-defined]
        return cls(**{k: v for k, v in d.items() if k in valid})

    def is_reliable(self, sil: float, pnr: float, covisi: float) -> bool:
        """Return True if the MU passes all enabled thresholds."""
        if self.sil_enabled:
            if math.isnan(sil) or sil < self.sil_min:
                return False
        if self.pnr_enabled:
            if math.isnan(pnr) or pnr < self.pnr_min:
                return False
        if self.covisi_enabled:
            if math.isnan(covisi) or covisi > self.covisi_max:
                return False
        return True


# -------------------------------------------------------------------------
# MAT in-memory conversion helpers
# -------------------------------------------------------------------------

def _cell_row_read_h5py(f, ds) -> list:
    """Read a 1×N (or N×1) MATLAB cell array (HDF5 format) into list of arrays.

    Elements are expected to be h5py object references.  Non-valid references
    produce a ``None`` entry in the returned list.
    """
    obj = ds[()]
    if obj.ndim == 2:
        if obj.shape[0] == 1:
            refs = [obj[0, j] for j in range(obj.shape[1])]
        elif obj.shape[1] == 1:
            refs = [obj[i, 0] for i in range(obj.shape[0])]
        else:
            refs = [obj[0, j] for j in range(obj.shape[1])]
    elif obj.ndim == 1:
        refs = list(obj)
    else:
        return []

    out = []
    for r in refs:
        if _H5PY_AVAILABLE and isinstance(r, (h5py.Reference, h5py.h5r.Reference)) and bool(r):
            out.append(np.array(f[r]))
        else:
            out.append(None)
    return out


def _read_mat_signal_scipy(path: Path) -> Optional[dict]:
    """Read ``signal.*`` from a MUedit pulsetrain MAT (legacy scipy format).

    Returns an openhdemg-compatible dict or ``None`` if the file cannot be
    parsed (e.g. it is HDF5/v7.3 format, which raises ``NotImplementedError``).
    """
    if not _H5PY_AVAILABLE:
        return None
    try:
        mat = sio.loadmat(str(path), squeeze_me=False, struct_as_record=False)
    except NotImplementedError:
        return None  # v7.3 HDF5 — caller should try _read_mat_signal_h5py
    except Exception:
        return None

    sig = mat.get("signal")
    if sig is None:
        return None

    # --- FSAMP ---
    fsamp = 2048.0
    fsamp_attr = getattr(sig, "fsamp", None)
    if fsamp_attr is not None:
        try:
            fsamp = float(np.asarray(fsamp_attr).flat[0])
        except Exception:
            pass

    # --- REF_SIGNAL from target or path ---
    ref_signal = None
    for attr_name in ("target", "path"):
        arr = getattr(sig, attr_name, None)
        if arr is not None:
            a = np.asarray(arr, dtype=np.float64).flatten()
            if a.size > 0:
                ref_signal = pd.DataFrame(a.reshape(-1, 1))
                break

    # --- Pulsetrain: (1 × ngrid) dtype=object, each cell (nMU × n_samples) ---
    pt_attr = getattr(sig, "Pulsetrain", None)
    if pt_attr is None:
        return None

    pt_arr = np.asarray(pt_attr, dtype=object)
    pt_flat = pt_arr.flatten()
    pt_parts = []
    for cell in pt_flat:
        if cell is None:
            continue
        g = np.asarray(cell, dtype=np.float64)
        if g.ndim == 1:
            g = g.reshape(1, -1)
        if g.size > 0:
            pt_parts.append(g)

    if not pt_parts:
        return None

    pt_combined = np.vstack(pt_parts)  # (nMU_total, n_samples)
    n_mus = pt_combined.shape[0]
    emg_length = pt_combined.shape[1]
    ipts_df = pd.DataFrame(pt_combined.T)  # (n_samples, nMU)

    # --- Dischargetimes: (ngrid × maxMU) dtype=object, 1-based indices ---
    dt_attr = getattr(sig, "Dischargetimes", None)
    mupulses = []
    if dt_attr is not None:
        dt_arr = np.asarray(dt_attr, dtype=object)
        if dt_arr.ndim < 2:
            dt_arr = dt_arr.reshape(1, -1)
        mu_global = 0
        for grid_idx, pt_grid in enumerate(pt_parts):
            grid_n_mus = pt_grid.shape[0]
            for mu_local in range(grid_n_mus):
                if grid_idx < dt_arr.shape[0] and mu_local < dt_arr.shape[1]:
                    cell = dt_arr[grid_idx, mu_local]
                    if cell is not None and np.asarray(cell).size > 0:
                        ts = np.asarray(cell, dtype=np.int64).flatten() - 1  # 1-based → 0-based
                        mupulses.append(ts)
                    else:
                        mupulses.append(np.array([], dtype=np.int64))
                else:
                    mupulses.append(np.array([], dtype=np.int64))
                mu_global += 1
    else:
        mupulses = [np.array([], dtype=np.int64)] * n_mus

    if ref_signal is None:
        ref_signal = pd.DataFrame(np.zeros((max(emg_length, 1), 1)))

    return {
        "SOURCE": "OTB",
        "FILENAME": str(path),
        "FSAMP": fsamp,
        "IED": 8.0,
        "NUMBER_OF_MUS": n_mus,
        "EMG_LENGTH": emg_length,
        "MUPULSES": mupulses,
        "IPTS": ipts_df,
        "BINARY_MUS_FIRING": _build_binary_mus_firing(mupulses, emg_length),
        "RAW_SIGNAL": pd.DataFrame(),
        "REF_SIGNAL": ref_signal,
        "ACCURACY": pd.DataFrame(np.zeros((n_mus, 1)) if n_mus > 0 else np.empty((0, 1))),
        "EXTRAS": pd.DataFrame(),
    }


def _read_mat_signal_h5py(path: Path) -> Optional[dict]:
    """Read ``signal.*`` from a MUedit pulsetrain MAT (HDF5/v7.3 format).

    Returns an openhdemg-compatible dict or ``None`` on failure.
    """
    if not _H5PY_AVAILABLE:
        return None
    try:
        with h5py.File(str(path), "r") as f:
            if "signal" not in f:
                return None
            sig = f["signal"]

            # FSAMP
            fsamp = 2048.0
            if "fsamp" in sig:
                try:
                    fsamp = float(np.asarray(sig["fsamp"][()]).flat[0])
                except Exception:
                    pass

            # REF_SIGNAL
            ref_signal = None
            for key in ("target", "path"):
                if key in sig:
                    a = np.asarray(sig[key][()], dtype=np.float64).flatten()
                    if a.size > 0:
                        ref_signal = pd.DataFrame(a.reshape(-1, 1))
                        break

            # Pulsetrain: (1 × ngrid) of refs, each (nMU × n_samples)
            if "Pulsetrain" not in sig:
                return None
            pt_obj = sig["Pulsetrain"][()]  # (1, ngrid)
            pt_parts = []
            ngrid = pt_obj.shape[1] if pt_obj.ndim >= 2 else len(pt_obj)
            for g_idx in range(ngrid):
                ref = pt_obj[0, g_idx] if pt_obj.ndim >= 2 else pt_obj[g_idx]
                if isinstance(ref, (h5py.Reference, h5py.h5r.Reference)) and bool(ref):
                    arr = np.array(f[ref], dtype=np.float64)
                    if arr.ndim == 1:
                        arr = arr.reshape(1, -1)
                    if arr.size > 0:
                        pt_parts.append(arr)

            if not pt_parts:
                return None

            pt_combined = np.vstack(pt_parts)  # (nMU_total, n_samples)
            n_mus = pt_combined.shape[0]
            emg_length = pt_combined.shape[1]
            ipts_df = pd.DataFrame(pt_combined.T)

            # Dischargetimes: (ngrid × maxMU) of refs
            mupulses = []
            if "Dischargetimes" in sig:
                dt_obj = sig["Dischargetimes"][()]
                if dt_obj.ndim < 2:
                    dt_obj = dt_obj.reshape(1, -1)
                for g_idx, pt_grid in enumerate(pt_parts):
                    for mu_local in range(pt_grid.shape[0]):
                        if g_idx < dt_obj.shape[0] and mu_local < dt_obj.shape[1]:
                            ref = dt_obj[g_idx, mu_local]
                            if isinstance(ref, (h5py.Reference, h5py.h5r.Reference)) and bool(ref):
                                ts = np.array(f[ref], dtype=np.int64).flatten() - 1
                                mupulses.append(ts)
                            else:
                                mupulses.append(np.array([], dtype=np.int64))
                        else:
                            mupulses.append(np.array([], dtype=np.int64))
            else:
                mupulses = [np.array([], dtype=np.int64)] * n_mus

            if ref_signal is None:
                ref_signal = pd.DataFrame(np.zeros((max(emg_length, 1), 1)))

            return {
                "SOURCE": "OTB",
                "FILENAME": str(path),
                "FSAMP": fsamp,
                "IED": 8.0,
                "NUMBER_OF_MUS": n_mus,
                "EMG_LENGTH": emg_length,
                "MUPULSES": mupulses,
                "IPTS": ipts_df,
                "BINARY_MUS_FIRING": _build_binary_mus_firing(mupulses, emg_length),
                "RAW_SIGNAL": pd.DataFrame(),
                "REF_SIGNAL": ref_signal,
                "ACCURACY": pd.DataFrame(np.zeros((n_mus, 1)) if n_mus > 0 else np.empty((0, 1))),
                "EXTRAS": pd.DataFrame(),
            }
    except Exception as exc:
        logger.warning("_read_mat_signal_h5py: failed for %s: %s", path.name, exc)
        return None


def _read_mat_edited_h5py(path: Path) -> Optional[dict]:
    """Read ``edition.*`` from a MUedit-edited MAT (HDF5/v7.3 format).

    Reconstructs an openhdemg-compatible dict in memory — no disk write needed.
    Tries to read FSAMP from the companion unedited MAT (same folder, stem
    without ``_edited.mat`` suffix).

    Returns ``None`` on failure.
    """
    if not _H5PY_AVAILABLE:
        return None
    try:
        with h5py.File(str(path), "r") as f:
            if "edition" not in f:
                return None
            edit = f["edition"]

            if "Pulsetrainclean" not in edit:
                return None
            pt_cells = _cell_row_read_h5py(f, edit["Pulsetrainclean"])
            pt_parts = []
            for cell in pt_cells:
                if cell is None:
                    continue
                g = np.asarray(cell, dtype=np.float64)
                if g.ndim == 1:
                    g = g.reshape(1, -1)
                if g.size > 0:
                    pt_parts.append(g)

            if not pt_parts:
                return None

            pt_combined = np.vstack(pt_parts)  # (nMU_total, n_samples)
            n_mus = pt_combined.shape[0]
            emg_length = pt_combined.shape[1]
            ipts_df = pd.DataFrame(pt_combined.T)

            # Distimeclean: 1×1 cell → inner 1×nMU cell of refs
            mupulses = []
            if "Distimeclean" in edit:
                top = edit["Distimeclean"][()]
                inner_ref = top.flat[0]
                inner_ds = f[inner_ref]
                disc_nested = _cell_row_read_h5py(f, inner_ds)
                for mu_timing in disc_nested:
                    if mu_timing is not None and np.asarray(mu_timing).size > 0:
                        ts = np.asarray(mu_timing, dtype=np.int64).flatten() - 1
                        mupulses.append(ts)
                    else:
                        mupulses.append(np.array([], dtype=np.int64))
            else:
                mupulses = [np.array([], dtype=np.int64)] * n_mus

            # SIL values as ACCURACY
            accuracy_arr = np.zeros((n_mus, 1))
            if "silval" in edit:
                sil_cells = _cell_row_read_h5py(f, edit["silval"])
                sil_flat: list = []
                for cell in sil_cells:
                    if cell is not None:
                        sil_flat.extend(np.asarray(cell, dtype=np.float64).flatten().tolist())
                if len(sil_flat) >= n_mus:
                    accuracy_arr = np.array(sil_flat[:n_mus], dtype=np.float64).reshape(-1, 1)

    except Exception as exc:
        logger.warning("_read_mat_edited_h5py: failed for %s: %s", path.name, exc)
        return None

    # FSAMP from companion unedited MAT (stem without "_edited.mat")
    fsamp = 2048.0
    companion = Path(str(path).replace(".mat_edited.mat", ".mat"))
    if companion.exists() and companion != path:
        try:
            mat = sio.loadmat(str(companion), squeeze_me=False, struct_as_record=False)
            sig = mat.get("signal")
            if sig is not None:
                f_attr = getattr(sig, "fsamp", None)
                if f_attr is not None:
                    fsamp = float(np.asarray(f_attr).flat[0])
        except NotImplementedError:
            try:
                with h5py.File(str(companion), "r") as fc:
                    if "signal" in fc and "fsamp" in fc["signal"]:
                        fsamp = float(np.asarray(fc["signal"]["fsamp"][()]).flat[0])
            except Exception:
                pass
        except Exception:
            pass

    ref_signal = pd.DataFrame(np.zeros((max(emg_length, 1), 1)))

    return {
        "SOURCE": "OTB",
        "FILENAME": str(path),
        "FSAMP": fsamp,
        "IED": 8.0,
        "NUMBER_OF_MUS": n_mus,
        "EMG_LENGTH": emg_length,
        "MUPULSES": mupulses,
        "IPTS": ipts_df,
        "BINARY_MUS_FIRING": _build_binary_mus_firing(mupulses, emg_length),
        "RAW_SIGNAL": pd.DataFrame(),
        "REF_SIGNAL": ref_signal,
        "ACCURACY": pd.DataFrame(accuracy_arr),
        "EXTRAS": pd.DataFrame(),
    }


def _mat_to_emgfile_dict(path: Path, mat_subtype: str) -> Optional[dict]:
    """Dispatch to the appropriate MAT reader and return an openhdemg-compatible dict."""
    if mat_subtype == _MAT_PULSETRAIN:
        return _read_mat_signal_scipy(path) or _read_mat_signal_h5py(path)
    if mat_subtype == _MAT_EDITED:
        return _read_mat_edited_h5py(path)
    return None


# -------------------------------------------------------------------------
# Main class
# -------------------------------------------------------------------------

class DecompositionFile:
    """Format-agnostic wrapper for decomposition files.

    Use :meth:`load` to create an instance from a .json, .pkl, or .mat path.
    """

    def __init__(self) -> None:
        self._path: Optional[Path] = None
        self._backend: str = ""  # "json", "pkl", "mat"
        self._mat_subtype: str = _MAT_UNKNOWN

        # JSON backend
        self._emgfile: Optional[dict] = None

        # PKL backend -- raw merged dict plus optional keep-indices
        self._pkl: Optional[dict] = None
        # {port_idx: set of mu_indices to keep} -- None means keep all
        self._pkl_keep_indices: Optional[dict] = None

        # MAT backend -- set of 0-based MU indices to retain after filtering
        # None means keep all (unfiltered)
        self._mat_keep_indices: Optional[set] = None

    # -- Factory ---------------------------------------------------------------

    @classmethod
    def load(cls, path: Path) -> "DecompositionFile":
        """Detect format by extension and load the file.

        Args:
            path: Path to a .json, .pkl, or .mat file.

        Returns:
            A populated DecompositionFile instance.

        Raises:
            ValueError: If the MAT file is not a decomposition file (raw EMG MAT).
        """
        path = Path(path)
        inst = cls()
        inst._path = path

        suffix = path.suffix.lower()

        if suffix == ".json":
            inst._backend = "json"
            inst._load_json(path)
        elif suffix == ".pkl":
            inst._backend = "pkl"
            inst._load_pkl(path)
        elif suffix == ".mat":
            inst._backend = "mat"
            inst._load_mat(path)
        else:
            raise ValueError(f"Unsupported file extension: {suffix}")

        return inst

    # -- Internal loaders ------------------------------------------------------

    def _load_json(self, path: Path) -> None:
        if not _OPENHDEMG_AVAILABLE:
            raise RuntimeError("openhdemg is required for JSON backend")
        self._emgfile = emg.emg_from_json(str(path))

    def _load_pkl(self, path: Path) -> None:
        with open(path, "rb") as fh:
            self._pkl = pickle.load(fh)  # trusted internal SCD output

    def _load_mat(self, path: Path) -> None:
        self._mat_subtype = _detect_mat_subtype(path)
        if self._mat_subtype == _MAT_UNKNOWN:
            raise ValueError(
                f"Not a decomposition MAT file (no 'signal.Dischargetimes' or "
                f"'edition.Distimeclean' found): {path.name}"
            )

    # -- Properties ------------------------------------------------------------

    @property
    def is_pkl(self) -> bool:
        return self._backend == "pkl"

    @property
    def is_mat(self) -> bool:
        return self._backend == "mat"

    @property
    def is_json(self) -> bool:
        return self._backend == "json"

    @property
    def path(self) -> Path:
        return self._path

    # -- Public interface ------------------------------------------------------

    def get_motor_unit_count(self) -> int:
        """Total number of (kept) motor units across all ports."""
        if self._backend == "json":
            return int(self._emgfile.get("NUMBER_OF_MUS", 0))
        if self._backend == "pkl":
            total = 0
            dt_list = self._pkl.get("discharge_times", [])
            for port_idx, dt_port in enumerate(dt_list):
                if self._pkl_keep_indices is not None:
                    keep = self._pkl_keep_indices.get(port_idx)
                    if keep is not None:
                        total += len(keep)
                        continue
                total += len(dt_port)
            return total
        return 0

    def get_sampling_rate(self) -> float:
        """Return sampling rate in Hz."""
        if self._backend == "json":
            return float(self._emgfile.get("FSAMP", 0.0))
        if self._backend == "pkl":
            return float(self._pkl.get("sampling_rate", 0.0))
        return 0.0

    def compute_covisi(self, method: str = "auto") -> pd.DataFrame:
        """Compute CoVISI for all motor units.

        Returns a DataFrame with columns:
          - mu_index   (int, 0-based within port)
          - port_index (int, 0-based; always 0 for JSON/MAT single-port files)
          - covisi_all (float, percent)

        Args:
            method: ``"auto"`` or ``"steady"`` (only meaningful for JSON backend).
        """
        if self._backend == "json":
            return self._compute_covisi_json(method)
        if self._backend == "pkl":
            return self._compute_covisi_pkl()
        if self._backend == "mat":
            return self._compute_covisi_mat()
        raise RuntimeError(f"Unknown backend: {self._backend}")

    def filter_mus_by_covisi(
        self,
        threshold: float,
        overrides: Optional[dict] = None,
    ) -> "DecompositionFile":
        """Return a new DecompositionFile with MUs above threshold removed.

        Args:
            threshold: CoVISI percent threshold.  MUs with covisi_all > threshold
                are filtered out.
            overrides: dict mapping (port_index, mu_index) -> "Keep" | "Filter"
                for manual per-MU decisions.

        Returns:
            A new DecompositionFile instance with filtered content.
        """
        overrides = overrides or {}

        if self._backend == "json":
            return self._filter_json(threshold, overrides)
        if self._backend == "pkl":
            return self._filter_pkl(threshold, overrides)
        raise NotImplementedError(
            "filter_mus_by_covisi is not supported for the MAT backend"
        )

    def compute_reliability(
        self, thresholds: "ReliabilityThresholds"
    ) -> pd.DataFrame:
        """Compute per-MU SIL, PNR, CoVISI and is_reliable flag.

        Returns a DataFrame with columns:
          mu_index, port_index, sil, pnr, covisi, dr_mean, n_spikes, is_reliable
        """
        if self._backend == "json":
            return self._compute_reliability_json(thresholds)
        if self._backend == "pkl":
            return self._compute_reliability_pkl(thresholds)
        if self._backend == "mat":
            return self._compute_reliability_mat(thresholds)
        return pd.DataFrame(
            columns=["mu_index", "port_index", "sil", "pnr", "covisi",
                     "dr_mean", "n_spikes", "is_reliable"]
        )

    def filter_mus_by_reliability(
        self,
        thresholds: "ReliabilityThresholds",
        overrides: Optional[dict] = None,
    ) -> "DecompositionFile":
        """Return a new DecompositionFile with unreliable MUs removed.

        Args:
            thresholds: Reliability thresholds to apply.
            overrides: dict mapping (port_index, mu_index) -> "Keep" | "Filter"

        Returns:
            A new DecompositionFile instance with filtered content.
        """
        overrides = overrides or {}
        if self._backend == "json":
            return self._filter_json_by_reliability(thresholds, overrides)
        if self._backend == "pkl":
            return self._filter_pkl_by_reliability(thresholds, overrides)
        if self._backend == "mat":
            return self._filter_mat_by_reliability(thresholds, overrides)
        raise NotImplementedError(
            f"filter_mus_by_reliability is not supported for backend: {self._backend}"
        )

    def get_emgfile_for_plotting(self) -> Optional[dict]:
        """Return the openhdemg emgfile dict suitable for plotting.

        JSON backend: returns sorted copy via tools.sort_mus().
        PKL backend: not yet supported — returns None.
        MAT backend: reconstructs an openhdemg-compatible dict in memory from
                     the MAT file (no disk I/O beyond the initial load).

        Returns:
            openhdemg emgfile dict, or None if unavailable.
        """
        if not _OPENHDEMG_AVAILABLE:
            return None

        if self._backend == "json":
            if self._emgfile is None:
                return None
            try:
                from openhdemg.library import tools
                ef = tools.sort_mus(copy.deepcopy(self._emgfile))
            except Exception as exc:
                logger.warning("get_emgfile_for_plotting: sort_mus failed: %s", exc)
                ef = copy.deepcopy(self._emgfile)

        elif self._backend == "mat":
            ef = _mat_to_emgfile_dict(self._path, self._mat_subtype)
            if ef is None:
                return None

        else:
            return None

        # Normalize REF_SIGNAL to 0-100 % MVC range.
        # Openhdemg expects REF_SIGNAL in percent (0-100).  Some acquisition
        # systems store it in raw ADC units (e.g., millivolts × 1000), producing
        # values like 40000 instead of 40.  Divide by 1000 until max ≤ 100.
        ref = ef.get("REF_SIGNAL")
        if ref is not None and hasattr(ref, "values"):
            ref_max = float(ref.values.max())
            if ref_max > 100:
                divisor = 1.0
                while ref_max / divisor > 100:
                    divisor *= 10.0
                ef["REF_SIGNAL"] = ref / divisor
        return ef

    def save(self, path: Path) -> None:
        """Write to disk.

        JSON: uses openhdemg save.
        PKL:  writes filtered PKL dict via pickle.
        MAT:  no-op (MAT files are written by MUedit, not by the pipe).
        """
        path = Path(path)

        if self._backend == "json":
            if not _OPENHDEMG_AVAILABLE:
                raise RuntimeError("openhdemg is required for JSON save")
            path.parent.mkdir(parents=True, exist_ok=True)
            emg.save_json_emgfile(self._emgfile, str(path), compresslevel=4)
            return

        if self._backend == "pkl":
            path.parent.mkdir(parents=True, exist_ok=True)
            filtered_pkl = self._build_filtered_pkl()
            with open(path, "wb") as fh:
                pickle.dump(filtered_pkl, fh)  # trusted internal SCD output
            return

        if self._backend == "mat":
            path.parent.mkdir(parents=True, exist_ok=True)
            if self._mat_keep_indices is not None and self._mat_subtype == _MAT_PULSETRAIN:
                self._filter_mat_pulsetrain_by_indices(self._mat_keep_indices, path)
            elif path != self._path:
                import shutil as _shutil
                _shutil.copy2(str(self._path), str(path))
            return

    def to_json(self, output_dir: Path, stem: str) -> List[Path]:
        """Export to openhdemg JSON format.

        JSON: copies/saves to ``output_dir/{stem}.json``.
        PKL:  writes one JSON per port:
              ``{output_dir}/{stem}_{port_name}_cleaned.json``
        MAT:  not implemented here -- handled by apply_muedit_edits_to_json()
              directly in the widget.

        Returns:
            List of paths of written JSON files.
        """
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        if self._backend == "json":
            if not _OPENHDEMG_AVAILABLE:
                raise RuntimeError("openhdemg is required for JSON export")
            out_path = output_dir / f"{stem}.json"
            emg.save_json_emgfile(self._emgfile, str(out_path), compresslevel=4)
            return [out_path]

        if self._backend == "pkl":
            return self._pkl_to_json_files(output_dir, stem)

        raise NotImplementedError(
            "to_json() is not implemented for the MAT backend -- "
            "use apply_muedit_edits_to_json() directly."
        )

    # -- JSON backend ----------------------------------------------------------

    def _compute_covisi_json(self, method: str) -> pd.DataFrame:
        from hdsemg_pipe.actions.covisi_analysis import compute_covisi_for_all_mus

        raw_df = compute_covisi_for_all_mus(self._emgfile, method=method)
        if "port_index" not in raw_df.columns:
            raw_df = raw_df.copy()
            raw_df.insert(1, "port_index", 0)
        return raw_df

    def _filter_json(self, threshold: float, overrides: dict) -> "DecompositionFile":
        from hdsemg_pipe.actions.covisi_analysis import filter_mus_by_covisi

        # Convert (port_idx, mu_idx) tuple keys to plain mu_idx for single-port
        flat_overrides = {
            (k[1] if isinstance(k, tuple) else k): v
            for k, v in overrides.items()
        }
        filtered_emgfile, _ = filter_mus_by_covisi(
            self._emgfile, threshold=threshold, manual_overrides=flat_overrides
        )
        inst = DecompositionFile()
        inst._path = self._path
        inst._backend = "json"
        inst._emgfile = filtered_emgfile
        return inst

    def _compute_reliability_json(
        self, thresholds: "ReliabilityThresholds"
    ) -> pd.DataFrame:
        if not _OPENHDEMG_AVAILABLE or self._emgfile is None:
            return pd.DataFrame(
                columns=["mu_index", "port_index", "sil", "pnr", "covisi",
                         "dr_mean", "n_spikes", "is_reliable"]
            )
        ef = self._emgfile
        fsamp = float(ef.get("FSAMP", 2048.0))
        n_mus = int(ef.get("NUMBER_OF_MUS", 0))
        ipts = ef.get("IPTS")
        mupulses = ef.get("MUPULSES", [])

        # Estimate contraction duration from signal length
        ref_signal = ef.get("REF_SIGNAL")
        if ref_signal is not None and hasattr(ref_signal, "__len__"):
            duration_s = len(ref_signal) / fsamp
        else:
            duration_s = float("nan")

        # Build CoVISI map from existing helper
        covisi_df = self._compute_covisi_json("auto")
        covisi_map = {
            int(r["mu_index"]): float(r["covisi_all"])
            for _, r in covisi_df.iterrows()
        }

        rows = []
        for mu in range(n_mus):
            pulses = mupulses[mu] if mu < len(mupulses) else []
            n_spikes = len(pulses)
            dr_mean = n_spikes / duration_s if duration_s > 0 else float("nan")

            # SIL and PNR via openhdemg
            try:
                ipts_mu = ipts.iloc[:, mu] if hasattr(ipts, "iloc") else ipts[mu]
            except Exception:
                ipts_mu = None

            try:
                sil_val = float(emg.compute_sil(ipts_mu, np.array(pulses)))
            except Exception:
                sil_val = float("nan")

            try:
                if ipts_mu is not None:
                    pnr_val = float(
                        emg.compute_pnr(ipts_mu, np.array(pulses), fsamp)
                    )
                else:
                    pnr_val = float("nan")
            except Exception:
                pnr_val = float("nan")

            covisi_val = covisi_map.get(mu, float("nan"))
            reliable = thresholds.is_reliable(sil_val, pnr_val, covisi_val)

            rows.append({
                "mu_index": mu,
                "port_index": 0,
                "sil": sil_val,
                "pnr": pnr_val,
                "covisi": covisi_val,
                "dr_mean": dr_mean,
                "n_spikes": n_spikes,
                "is_reliable": reliable,
            })

        return pd.DataFrame(rows)

    def _filter_json_by_reliability(
        self,
        thresholds: "ReliabilityThresholds",
        overrides: dict,
    ) -> "DecompositionFile":
        rel_df = self._compute_reliability_json(thresholds)
        mus_to_remove = []
        for _, row in rel_df.iterrows():
            mu = int(row["mu_index"])
            key = (0, mu)
            decision = overrides.get(key, "Auto")
            if decision == "Keep":
                continue
            if decision == "Filter" or not row["is_reliable"]:
                mus_to_remove.append(mu)

        if not mus_to_remove:
            inst = DecompositionFile()
            inst._path = self._path
            inst._backend = "json"
            inst._emgfile = self._emgfile
            return inst

        new_ef = copy.deepcopy(self._emgfile)
        new_ef = emg.delete_mus(new_ef, mus_to_remove)

        inst = DecompositionFile()
        inst._path = self._path
        inst._backend = "json"
        inst._emgfile = new_ef
        return inst

    # -- PKL backend -----------------------------------------------------------

    def _compute_covisi_pkl(self) -> pd.DataFrame:
        dt_list = self._pkl.get("discharge_times", [])
        rows = []
        for port_idx, dt_port in enumerate(dt_list):
            keep = None
            if self._pkl_keep_indices is not None:
                keep = self._pkl_keep_indices.get(port_idx)
            for mu_idx, timestamps in enumerate(dt_port):
                if keep is not None and mu_idx not in keep:
                    continue
                cov = _cov_isi(timestamps)
                rows.append(
                    {
                        "mu_index": mu_idx,
                        "port_index": port_idx,
                        "covisi_all": cov,
                    }
                )
        if not rows:
            return pd.DataFrame(columns=["mu_index", "port_index", "covisi_all"])
        return pd.DataFrame(rows)

    def _filter_pkl(self, threshold: float, overrides: dict) -> "DecompositionFile":
        covisi_df = self._compute_covisi_pkl()
        keep_indices: dict = {}

        dt_list = self._pkl.get("discharge_times", [])
        for port_idx, dt_port in enumerate(dt_list):
            keep = set()
            for mu_idx in range(len(dt_port)):
                key = (port_idx, mu_idx)
                if key in overrides:
                    if overrides[key] == "Keep":
                        keep.add(mu_idx)
                    continue  # "Filter" -- skip

                row = covisi_df[
                    (covisi_df["port_index"] == port_idx)
                    & (covisi_df["mu_index"] == mu_idx)
                ]
                if row.empty:
                    keep.add(mu_idx)
                    continue
                cov_val = float(row.iloc[0]["covisi_all"])
                if np.isnan(cov_val) or cov_val <= threshold:
                    keep.add(mu_idx)
            keep_indices[port_idx] = keep

        inst = DecompositionFile()
        inst._path = self._path
        inst._backend = "pkl"
        inst._pkl = self._pkl
        inst._pkl_keep_indices = keep_indices
        return inst

    def _compute_reliability_pkl(
        self, thresholds: "ReliabilityThresholds"
    ) -> pd.DataFrame:
        rows = []
        covisi_df = self._compute_covisi_pkl()
        covisi_map = {
            (int(r["port_index"]), int(r["mu_index"])): float(r["covisi_all"])
            for _, r in covisi_df.iterrows()
        }

        pkl = self._pkl
        fsamp = float(pkl.get("sampling_rate", 2048.0))
        dt_list = pkl.get("discharge_times", [])
        ipts_list = pkl.get("ipts", [])

        for port_idx, dt_port in enumerate(dt_list):
            ipts_port = ipts_list[port_idx] if port_idx < len(ipts_list) else None
            emg_length = _infer_emg_length_from_pkl(pkl, port_idx)
            duration_s = emg_length / fsamp if emg_length > 0 else float("nan")

            for mu, pulses in enumerate(dt_port):
                n_spikes = len(pulses) if pulses is not None else 0
                dr_mean = n_spikes / duration_s if duration_s > 0 else float("nan")

                try:
                    if ipts_port is not None:
                        ipts_col = (
                            ipts_port.iloc[:, mu]
                            if hasattr(ipts_port, "iloc")
                            else np.array(ipts_port)[:, mu]
                        )
                        sil_val = float(emg.compute_sil(ipts_col, np.array(pulses)))
                        pnr_val = float(emg.compute_pnr(ipts_col, np.array(pulses), fsamp))
                    else:
                        sil_val = pnr_val = float("nan")
                except Exception:
                    sil_val = pnr_val = float("nan")

                covisi_val = covisi_map.get((port_idx, mu), float("nan"))
                reliable = thresholds.is_reliable(sil_val, pnr_val, covisi_val)

                rows.append({
                    "mu_index": mu,
                    "port_index": port_idx,
                    "sil": sil_val,
                    "pnr": pnr_val,
                    "covisi": covisi_val,
                    "dr_mean": dr_mean,
                    "n_spikes": n_spikes,
                    "is_reliable": reliable,
                })

        return pd.DataFrame(rows)

    def _filter_pkl_by_reliability(
        self,
        thresholds: "ReliabilityThresholds",
        overrides: dict,
    ) -> "DecompositionFile":
        rel_df = self._compute_reliability_pkl(thresholds)
        keep_indices: dict = {}

        for port_idx in rel_df["port_index"].unique():
            port_rows = rel_df[rel_df["port_index"] == port_idx]
            kept = []
            for _, row in port_rows.iterrows():
                mu = int(row["mu_index"])
                key = (port_idx, mu)
                decision = overrides.get(key, "Auto")
                if decision == "Keep" or (
                    decision != "Filter" and row["is_reliable"]
                ):
                    kept.append(mu)
            keep_indices[int(port_idx)] = set(kept)

        inst = DecompositionFile()
        inst._path = self._path
        inst._backend = "pkl"
        inst._pkl = self._pkl
        inst._pkl_keep_indices = keep_indices
        return inst

    # -- MAT reliability / filtering ---------------------------------------

    def _compute_reliability_mat(
        self, thresholds: "ReliabilityThresholds"
    ) -> pd.DataFrame:
        """Compute per-MU reliability from a MAT file via the in-memory dict."""
        empty = pd.DataFrame(
            columns=["mu_index", "port_index", "sil", "pnr", "covisi",
                     "dr_mean", "n_spikes", "is_reliable"]
        )
        if not _OPENHDEMG_AVAILABLE:
            return empty

        ef = _mat_to_emgfile_dict(self._path, self._mat_subtype)
        if ef is None:
            return empty

        n_mus = ef["NUMBER_OF_MUS"]
        fsamp = ef["FSAMP"]
        ipts = ef.get("IPTS")
        mupulses = ef.get("MUPULSES", [])
        emg_length = ef.get("EMG_LENGTH", 0)
        duration_s = emg_length / fsamp if emg_length > 0 and fsamp > 0 else float("nan")

        rows = []
        for mu in range(n_mus):
            pulses = mupulses[mu] if mu < len(mupulses) else []
            n_spikes = len(pulses)
            dr_mean = n_spikes / duration_s if duration_s > 0 else float("nan")
            covisi_val = _cov_isi(pulses)

            try:
                ipts_mu = ipts.iloc[:, mu] if hasattr(ipts, "iloc") else None
            except Exception:
                ipts_mu = None

            try:
                sil_val = float(emg.compute_sil(ipts_mu, np.array(pulses))) if ipts_mu is not None else float("nan")
            except Exception:
                sil_val = float("nan")

            try:
                pnr_val = float(emg.compute_pnr(ipts_mu, np.array(pulses), fsamp)) if ipts_mu is not None else float("nan")
            except Exception:
                pnr_val = float("nan")

            rows.append({
                "mu_index": mu,
                "port_index": 0,
                "sil": sil_val,
                "pnr": pnr_val,
                "covisi": covisi_val,
                "dr_mean": dr_mean,
                "n_spikes": n_spikes,
                "is_reliable": thresholds.is_reliable(sil_val, pnr_val, covisi_val),
            })

        return pd.DataFrame(rows)

    def _filter_mat_by_reliability(
        self,
        thresholds: "ReliabilityThresholds",
        overrides: dict,
    ) -> "DecompositionFile":
        rel_df = self._compute_reliability_mat(thresholds)
        keep_set: set = set()
        for _, row in rel_df.iterrows():
            mu = int(row["mu_index"])
            key = (0, mu)
            decision = overrides.get(key, "Auto")
            if decision == "Keep" or (decision != "Filter" and row["is_reliable"]):
                keep_set.add(mu)

        inst = DecompositionFile()
        inst._path = self._path
        inst._backend = "mat"
        inst._mat_subtype = self._mat_subtype
        inst._mat_keep_indices = keep_set
        return inst

    def _build_filtered_pkl(self) -> dict:
        """Return a PKL dict with non-kept MUs removed from list fields."""
        if self._pkl_keep_indices is None:
            return copy.deepcopy(self._pkl)

        result = copy.copy(self._pkl)
        list_keys = ["discharge_times", "pulse_trains", "mu_filters", "peel_off_sequence"]

        for key in list_keys:
            orig = self._pkl.get(key, [])
            if not orig:
                continue
            new_outer = []
            for port_idx, port_data in enumerate(orig):
                keep = self._pkl_keep_indices.get(port_idx)
                if keep is None:
                    new_outer.append(copy.deepcopy(port_data))
                else:
                    new_outer.append(
                        [copy.deepcopy(item) for i, item in enumerate(port_data) if i in keep]
                    )
            result[key] = new_outer

        return result

    def _pkl_to_json_files(self, output_dir: Path, stem: str) -> List[Path]:
        """Write one openhdemg JSON per port from the (filtered) PKL."""
        if not _OPENHDEMG_AVAILABLE:
            raise RuntimeError("openhdemg is required for PKL-to-JSON conversion")

        filtered_pkl = self._build_filtered_pkl()
        ports = filtered_pkl.get("ports", [])
        written = []

        pkl_dir = self._path.parent
        for port_idx, port_name in enumerate(ports):
            sibling_json = pkl_dir / f"{stem}_{port_name}.json"
            ref_signal = _load_ref_signal_from_sibling_json(sibling_json)
            emgfile_dict = _pkl_to_emgfile_dict(filtered_pkl, port_idx, port_name,
                                                 ref_signal=ref_signal)
            out_name = f"{stem}_{port_name}_cleaned.json"
            out_path = output_dir / out_name
            emg.save_json_emgfile(emgfile_dict, str(out_path), compresslevel=4)
            logger.info("PKL->JSON: wrote %s", out_path.name)
            written.append(out_path)

        return written

    # -- MAT backend -----------------------------------------------------------

    def _filter_mat_pulsetrain_by_indices(
        self, keep_mu_indices: set, dest_path: Path
    ) -> None:
        """Write a filtered copy of a pulsetrain MAT file keeping only ``keep_mu_indices``.

        Modifies ``signal.Dischargetimes`` and ``signal.Pulsetrains`` in-place on
        the loaded struct and saves to ``dest_path``.  Works for both legacy scipy
        (HDF5-free) and HDF5 v7.3 MAT files.

        Args:
            keep_mu_indices: 0-based MU indices to retain.
            dest_path: Output path for the filtered MAT file.
        """
        dest_path.parent.mkdir(parents=True, exist_ok=True)

        try:
            # ---- Legacy scipy (non-HDF5) ----------------------------------------
            mat_data = sio.loadmat(str(self._path), squeeze_me=True,
                                   struct_as_record=False)
            signal = mat_data.get("signal")
            if signal is not None:
                dt = getattr(signal, "Dischargetimes", None)
                if dt is not None:
                    orig = list(dt) if hasattr(dt, "__iter__") else []
                    signal.Dischargetimes = np.array(
                        [orig[i] for i in sorted(keep_mu_indices) if i < len(orig)],
                        dtype=object,
                    )
                pt = getattr(signal, "Pulsetrains", None)
                if pt is not None:
                    orig_pt = list(pt) if hasattr(pt, "__iter__") else []
                    signal.Pulsetrains = np.array(
                        [orig_pt[i] for i in sorted(keep_mu_indices) if i < len(orig_pt)],
                        dtype=object,
                    )
                mat_data["signal"] = signal
                sio.savemat(str(dest_path), mat_data)
                logger.info("MAT filter (scipy): wrote %s (%d MUs)",
                            dest_path.name, len(keep_mu_indices))
                return
        except NotImplementedError:
            pass  # HDF5 v7.3 — fall through to h5py path
        except Exception as exc:
            logger.warning("MAT scipy filter failed, trying h5py: %s", exc)

        # ---- HDF5 v7.3 (h5py) ---------------------------------------------------
        import shutil
        # Copy original then surgically replace datasets
        shutil.copy2(str(self._path), str(dest_path))

        try:
            with h5py.File(str(dest_path), "r+") as f:
                if "signal" not in f:
                    return
                sig = f["signal"]
                for field in ("Dischargetimes", "Pulsetrains"):
                    ds = sig.get(field)
                    if ds is None:
                        continue
                    arr = ds[()]  # shape (1, n_mu) or (n_mu,)
                    if arr.ndim == 2 and arr.shape[0] == 1:
                        orig_refs = [arr[0, i] for i in range(arr.shape[1])]
                    elif arr.ndim == 1:
                        orig_refs = list(arr)
                    else:
                        continue

                    kept_refs = [orig_refs[i] for i in sorted(keep_mu_indices)
                                 if i < len(orig_refs)]
                    new_arr = np.array([kept_refs], dtype=arr.dtype)

                    del sig[field]
                    sig.create_dataset(field, data=new_arr)

            logger.info("MAT filter (h5py): wrote %s (%d MUs)",
                        dest_path.name, len(keep_mu_indices))
        except Exception as exc:
            logger.error("MAT h5py filter failed for %s: %s", dest_path.name, exc)
            # dest_path is a copy of the original — leave it as-is rather than
            # leaving a corrupted file
            dest_path.unlink(missing_ok=True)
            raise

    def _compute_covisi_mat(self) -> pd.DataFrame:
        from hdsemg_pipe.actions.covisi_analysis import compute_covisi_from_muedit_mat

        if self._mat_subtype == _MAT_EDITED:
            fsamp = self.get_sampling_rate() or 2048.0
            raw_df = compute_covisi_from_muedit_mat(str(self._path), fsamp=fsamp)
            if "port_index" not in raw_df.columns:
                raw_df = raw_df.copy()
                raw_df.insert(1, "port_index", 0)
            return raw_df

        if self._mat_subtype == _MAT_PULSETRAIN:
            return self._compute_covisi_mat_pulsetrain()

        return pd.DataFrame(columns=["mu_index", "port_index", "covisi_all"])

    def _compute_covisi_mat_pulsetrain(self) -> pd.DataFrame:
        """Compute CoVISI from a MUedit pulsetrain MAT file (signal.Dischargetimes)."""
        rows = []
        try:
            # Try legacy scipy format first
            try:
                mat_data = sio.loadmat(str(self._path), squeeze_me=True, struct_as_record=False)
                signal = mat_data.get("signal")
                if signal is not None:
                    discharge_times = getattr(signal, "Dischargetimes", None)
                    if discharge_times is not None:
                        for mu_idx, dt in enumerate(discharge_times):
                            ts = np.asarray(dt, dtype=np.int64).flatten()
                            rows.append(
                                {
                                    "mu_index": mu_idx,
                                    "port_index": 0,
                                    "covisi_all": _cov_isi(ts),
                                }
                            )
                        return (
                            pd.DataFrame(rows)
                            if rows
                            else pd.DataFrame(columns=["mu_index", "port_index", "covisi_all"])
                        )
            except NotImplementedError:
                pass

            with h5py.File(str(self._path), "r") as f:
                if "signal" not in f:
                    return pd.DataFrame(columns=["mu_index", "port_index", "covisi_all"])
                signal_group = f["signal"]
                dt_dataset = signal_group.get("Dischargetimes")
                if dt_dataset is None:
                    return pd.DataFrame(columns=["mu_index", "port_index", "covisi_all"])

                dt_arr = dt_dataset[()]
                if dt_arr.ndim == 2:
                    n_mu = dt_arr.shape[1]
                    for mu_idx in range(n_mu):
                        ref = dt_arr[0, mu_idx]
                        if isinstance(ref, (h5py.Reference, h5py.h5r.Reference)) and bool(ref):
                            ts = np.array(f[ref], dtype=np.int64).flatten()
                        else:
                            ts = np.asarray(ref, dtype=np.int64).flatten()
                        rows.append(
                            {
                                "mu_index": mu_idx,
                                "port_index": 0,
                                "covisi_all": _cov_isi(ts),
                            }
                        )
        except Exception as exc:
            logger.warning("Could not compute CoVISI from MAT pulsetrain: %s", exc)

        if not rows:
            return pd.DataFrame(columns=["mu_index", "port_index", "covisi_all"])
        return pd.DataFrame(rows)

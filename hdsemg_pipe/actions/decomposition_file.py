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

@dataclass
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
            logger.debug("DecompositionFile.save() is a no-op for MAT files")

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

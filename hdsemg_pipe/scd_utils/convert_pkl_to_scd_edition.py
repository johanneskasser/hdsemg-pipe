"""
Convert old SCD pickle format to scd-edition compatible format.

Old format keys: silhouettes, timestamps, source, RoA, filters, fr, cov, best_exp
New format keys: ports, discharge_times, pulse_trains, mu_filters, version, sampling_rate, ...

With --mat-dir or --mat-file the raw EMG is embedded so scd-edition can compute
reliability scores, MUAPs, etc.  Without it the file loads but all MUs show as
"not reliable" (no data = no silhouette recalculation).

Note: Uses pickle for loading/saving SCD result files (trusted internal files only).

Usage:
    # Basic conversion (no EMG data — MUs load but show as unreliable)
    python utils/convert_pkl_to_scd_edition.py input.pkl output.pkl
    python utils/convert_pkl_to_scd_edition.py input_dir/ output_dir/

    # With EMG data embedded (recommended — auto-finds .mat and channel JSON)
    python utils/convert_pkl_to_scd_edition.py input_dir/ output_dir/ --mat-dir /path/to/mat/files

    # With explicit mat file (grid key auto-detected from pkl filename)
    python utils/convert_pkl_to_scd_edition.py input.pkl output.pkl --mat-file recording.mat

    # With explicit mat file and grid key
    python utils/convert_pkl_to_scd_edition.py input.pkl output.pkl --mat-file rec.mat --grid-key 8mm_5x13_2

    # If decomposition started at a non-zero time offset
    python utils/convert_pkl_to_scd_edition.py input.pkl output.pkl --mat-file rec.mat --start-sample 4000
"""

import argparse
import io
import pickle  # noqa: S403 — trusted SCD result files only
import sys
from pathlib import Path

import numpy as np
import scipy.io as sio
import torch

sys.path.insert(0, str(Path(__file__).parent))
from scd_channel_utils import (
    load_channel_selection_json,
    get_grids_from_json,
    get_good_channels_from_grid,
)


class CPUUnpickler(pickle.Unpickler):
    """Load pickle files containing CUDA tensors on a CPU-only machine."""
    def find_class(self, module, name):
        if module == "torch.storage" and name == "_load_from_bytes":
            return lambda b: torch.load(io.BytesIO(b), map_location="cpu", weights_only=False)
        return super().find_class(module, name)


def load_old_pkl(path: Path) -> dict:
    with open(path, "rb") as f:
        return CPUUnpickler(f).load()


def to_numpy(val):
    """Convert tensor or array-like to numpy array."""
    if isinstance(val, torch.Tensor):
        return val.cpu().numpy()
    return np.asarray(val)


# ---------------------------------------------------------------------------
# Plateau detection from mat file force signal
# ---------------------------------------------------------------------------

def detect_plateau_from_mat(
    mat_file: Path,
    grid_key: str | None = None,
    n_std: float = 7.0,
    sFrom: float = 1.0,
    sTo: float = 3.0,
) -> tuple[int, int, int]:
    """
    Detect plateau start/end sample indices from the force/reference signal.

    Uses the same force-threshold logic as loadEMG_updConfig in
    scd/utils/preprocessing.py.  Reference signal indices are read from
    the sidecar channel-selection JSON when available; otherwise the
    OTBio Muovi/Syncstation defaults (measured=70, target=71) are used.

    Returns
    -------
    start_sample : int
        First sample of the detected plateau (0-based, into the full recording).
    end_sample : int
        One-past-last sample of the plateau.
    sampling_rate : int
        Sampling frequency extracted from the mat file.

    On any failure, returns (0, total_samples, sampling_rate).
    """
    mat = sio.loadmat(mat_file)
    fsamp = int(mat["SamplingFrequency"][0][0])
    n_total = int(mat["Data"].shape[0])

    # Default reference signal indices (OTBio Muovi/Syncstation)
    ref_target_idx   = 71   # "Original Path" / target
    ref_measured_idx = 70   # "Performed Path" / measured

    # Override from sidecar JSON if the grid_key is known
    json_data = load_channel_selection_json(mat_file)
    if json_data and grid_key:
        grids = get_grids_from_json(json_data)
        matched = next((g for g in grids if g["grid_key"] == grid_key), None)
        if matched:
            for ref_sig in matched.get("reference_signals", []):
                name = ref_sig.get("name", "").lower()
                idx  = ref_sig.get("ref_index")
                if idx is None:
                    continue
                if "original" in name or "target" in name:
                    ref_target_idx = int(idx)
                elif "performed" in name or "measured" in name:
                    ref_measured_idx = int(idx)

    try:
        ref_target   = mat["Data"][:, ref_target_idx].astype(np.float64)
        ref_measured = mat["Data"][:, ref_measured_idx].astype(np.float64)

        # Compute force threshold from baseline statistics at start and end
        baseline_s = ref_measured[int(fsamp * sFrom) : int(fsamp * sTo)]
        thr_s = baseline_s.mean() + baseline_s.std() * n_std
        baseline_e = ref_measured[::-1][int(fsamp * sFrom) : int(fsamp * sTo)]
        thr_e = baseline_e.mean() + baseline_e.std() * n_std
        force_threshold = (thr_s + thr_e) / 2.0

        if ref_target.sum() == 0:
            print("  Plateau detect : ref_target is zero → using full signal")
            return 0, n_total, fsamp

        above = np.where(ref_target > force_threshold)[0]
        if len(above) == 0:
            print(f"  Plateau detect : threshold {force_threshold:.4g} never exceeded "
                  f"→ using full signal")
            return 0, n_total, fsamp

        start_idx = int(above[0])
        above_rev = np.where(ref_target[::-1] > force_threshold)[0]
        end_idx   = int(1 + n_total - above_rev[0])
        end_idx   = min(end_idx, n_total)

        print(f"  Plateau detect : start={start_idx} ({start_idx/fsamp:.2f}s)  "
              f"end={end_idx} ({end_idx/fsamp:.2f}s)  fs={fsamp}")
        return start_idx, end_idx, fsamp

    except Exception as exc:
        print(f"  Plateau detect : failed ({exc}) → using start=0")
        return 0, n_total, fsamp


# ---------------------------------------------------------------------------
# EMG loading from .mat
# ---------------------------------------------------------------------------

def _detect_grid_key_from_stem(pkl_stem: str, mat_stem: str, mat_file: Path) -> str | None:
    """
    Given pkl stem and mat stem, infer the grid key by matching against
    grid keys known from the sidecar channel-selection JSON.

    pkl_stem  = "865_20260319_FT_Block1_8mm_5x13_2_VastusMedialisRight"
    mat_stem  = "865_20260319_FT_Block1"
    -> remaining = "8mm_5x13_2_VastusMedialisRight"
    -> matches JSON grid_key "8mm_5x13_2"
    """
    if not pkl_stem.startswith(mat_stem):
        return None
    remaining = pkl_stem[len(mat_stem):].lstrip("_")
    if not remaining:
        return None

    # Try to match against known grid keys from the sidecar JSON
    json_data = load_channel_selection_json(mat_file)
    if json_data:
        grids = get_grids_from_json(json_data)
        known_keys = {g["grid_key"] for g in grids}
        parts = remaining.split("_")
        for n in range(len(parts), 0, -1):
            candidate = "_".join(parts[:n])
            if candidate in known_keys:
                return candidate

    # Fallback heuristic: strip trailing CamelCase muscle name
    parts = remaining.split("_")
    key_parts = []
    for p in parts:
        if p and p[0].isupper() and p.isalpha():
            break  # looks like muscle name (e.g. "VastusMedialisRight")
        key_parts.append(p)
    return "_".join(key_parts) if key_parts else None


def find_mat_for_pkl(pkl_path: Path, mat_dirs: list[Path]) -> tuple[Path | None, str | None]:
    """
    Auto-detect the corresponding .mat file for a pkl by progressively trimming
    underscore-separated suffixes from the pkl stem.

    Returns (mat_path, grid_key) or (None, None) if not found.
    """
    stem = pkl_path.stem
    parts = stem.split("_")

    for n in range(len(parts) - 1, 0, -1):
        mat_stem = "_".join(parts[:n])
        for d in mat_dirs:
            candidate = d / f"{mat_stem}.mat"
            if candidate.exists():
                grid_key = _detect_grid_key_from_stem(stem, mat_stem, candidate)
                return candidate, grid_key

    return None, None


def load_emg_from_mat(
    mat_file: Path,
    grid_key: str | None = None,
    start_sample: int = 0,
    n_samples: int | None = None,
) -> tuple[np.ndarray, int, list[int]]:
    """
    Load raw EMG from a .mat file for the specified grid.

    Uses the sidecar channel-selection JSON (same stem as mat file) to select
    only the good channels — identical logic to main.py / loadEMG_updConfig.

    Returns
    -------
    emg : np.ndarray, shape (n_channels, n_samples)
    n_channels : int
    good_channels_global : list[int]  — absolute channel indices used
    """
    mat = sio.loadmat(mat_file)
    raw = mat["Data"]  # (time, all_channels)

    good_channels = None

    json_data = load_channel_selection_json(mat_file)
    if json_data and grid_key:
        grids = get_grids_from_json(json_data)
        matched = next((g for g in grids if g["grid_key"] == grid_key), None)
        if matched:
            good_channels, _, _, _ = get_good_channels_from_grid(matched)
            print(f"  Channel JSON : grid '{grid_key}' -> {len(good_channels)} good channels")
        else:
            print(f"  Channel JSON : grid '{grid_key}' not found in JSON (known: {[g['grid_key'] for g in grids]})")

    if good_channels is None:
        good_channels = list(range(raw.shape[1]))
        print(f"  Channel JSON : not found or no grid match -> using all {len(good_channels)} channels")

    end_sample = (start_sample + n_samples) if n_samples else raw.shape[0]
    emg = raw[start_sample:end_sample, good_channels].T.astype(np.float32)  # (ch, time)
    return emg, len(good_channels), good_channels


# ---------------------------------------------------------------------------
# Core conversion
# ---------------------------------------------------------------------------

def convert(
    old_data: dict,
    sampling_rate: int = 2000,
    port_name: str = "Port_1",
    emg: np.ndarray | None = None,
    n_channels: int | None = None,
    channel_indices_global: list[int] | None = None,
    time_differentiate: bool = False,
    extension_factor: int | None = None,
    peel_off_window_size_ms: int = 50,
    notch_params: list | None = None,
) -> dict:
    """
    Convert old SCD result dict to scd-edition format.

    Parameters
    ----------
    old_data : dict
        Loaded old-format pickle dict.
    sampling_rate : int
        Sampling frequency in Hz.
    port_name : str
        Name to assign to the single port.
    emg : np.ndarray or None
        Raw EMG array, shape (n_channels, n_samples).  If provided, enables
        MUAP and reliability computation in scd-edition.
    n_channels : int or None
        Number of physical channels (used for chans_per_electrode).
    channel_indices_global : list[int] or None
        Global channel indices (used for channel_indices).
    time_differentiate : bool
        Whether time differentiation was applied during decomposition.
        CRITICAL: must match the original decomposition config.
    extension_factor : int or None
        Temporal extension factor used during decomposition.
        If None, inferred from filter shape (filter_dim / n_channels).
        CRITICAL: must match the original decomposition config.
    peel_off_window_size_ms : int
        Peel-off window size in milliseconds used during decomposition.
        Default: 50 ms.
    """
    n_mu = len(old_data.get("timestamps", []))

    # Infer extension_factor from filter shape when not explicitly provided.
    # SCD's extend() uses range(factor) shifts → total channels = n_ch * factor.
    # So filter_dim = n_ch * extension_factor.
    _n_ch_actual = n_channels or (emg.shape[0] if emg is not None else None)
    if extension_factor is None and _n_ch_actual:
        filters = old_data.get("filters", [])
        if filters:
            _filt_dim = int(np.asarray(filters[0]).size)
            if _filt_dim % _n_ch_actual == 0:
                extension_factor = _filt_dim // _n_ch_actual
    if extension_factor is None:
        extension_factor = 20  # fallback default

    discharge_times_port = [
        to_numpy(ts).astype(np.int64) for ts in old_data.get("timestamps", [])
    ]

    # peel_off_sequence: one entry per MU with the stored discharge timestamps.
    # scd-edition's _replay_peel_off_for_port() iterates this list to recompute
    # sources via STA + peel-off replay.  An empty list → 0 sources computed.
    # plateau_coords starts at 0, so timestamps are absolute sample indices.
    peel_seq_port = [
        {"accepted_unit_idx": i, "timestamps": discharge_times_port[i].tolist()}
        for i in range(len(discharge_times_port))
    ]

    sources = old_data.get("source", [])
    # Each source is (n_samples, 1); store as list of 1-D arrays [mu0, mu1, ...]
    # so scd-edition's _normalise_filters / pulse_trains indexing works correctly.
    pulse_trains_port = [to_numpy(s).squeeze() for s in sources]
    n_pkl_samples = int(pulse_trains_port[0].shape[0]) if pulse_trains_port else 0

    filters = old_data.get("filters", [])
    # Each filter is (n_ext_ch, 1); store as list of 1-D arrays [mu0, mu1, ...]
    # _normalise_filters expects List[np.ndarray] or 2-D array with shape (n_mu, n_ext_ch).
    # The hstack approach produced (n_ext_ch, n_mu) — transposed — which caused dimension
    # mismatches when the filter was applied to the (n_samples, n_ext_ch) EMG tensor.
    mu_filters_port = [to_numpy(f).squeeze() for f in filters]

    # -- data / channel fields -----------------------------------------------
    if emg is not None:
        data_field = emg                          # (n_ch, n_samples)
        chans_field = [int(n_channels or emg.shape[0])]
        # channel_indices must be LOCAL (0..n_ch-1) because scd-edition indexes
        # directly into the stored EMG array, not the original full recording.
        ch_idx_field = [list(range(emg.shape[0]))]
    else:
        # Omit 'data' entirely so compute_all_full_sources() exits cleanly
        # via its "Missing key" guard rather than crashing on _to_numpy(None).
        data_field = None
        chans_field = []      # [] -> scd-edition falls back to its 64-ch default
        ch_idx_field = [None]

    new_data = {
        # Required by scd-edition
        "ports": [port_name],
        "discharge_times": [discharge_times_port],

        # Signal arrays
        "pulse_trains": [pulse_trains_port],
        "mu_filters": [mu_filters_port],

        # Metadata
        "version": 1.0,
        "sampling_rate": sampling_rate,
        "plateau_coords": [0, n_pkl_samples],

        # Channel info
        "chans_per_electrode": chans_field,
        "channel_indices": ch_idx_field,

        # Optional fields (not available in old format)
        # preprocessing_config mirrors what scd/models/scd.py stores at runtime.
        # Old pkl files don't carry this, so we reconstruct with main.py defaults.
        "peel_off_sequence": [peel_seq_port],
        "preprocessing_config": [{
            "sampling_frequency":     sampling_rate,
            "peel_off_window_size":   int(peel_off_window_size_ms * sampling_rate / 1000),
            "low_pass_cutoff":        500,
            "high_pass_cutoff":       10,
            "time_differentiate":     time_differentiate,
            "extension_factor":       extension_factor,
            "whitening_method":       "zca",
            "autocorrelation_whiten": False,
            "clamp_percentile":       0.999,
            "edge_mask_size":         200,
            **({"notch_params": notch_params} if notch_params is not None else {}),
        }],
        "dewhitened_filters": [None],
        "emg_mask": [None],
        "electrodes": [None],
        "aux_channels": [{}],

        # Legacy quality metrics preserved for reference
        "_legacy_silhouettes": [to_numpy(s).item() for s in old_data.get("silhouettes", [])],
        "_legacy_fr": old_data.get("fr", []),
        "_legacy_cov": [to_numpy(c).item() for c in old_data.get("cov", [])],
        "_legacy_best_exp": [float(e) for e in old_data.get("best_exp", [])],
        "_legacy_RoA": old_data.get("RoA", []),
        "_n_motor_units": n_mu,
    }

    # Only include 'data' key when we actually have data
    if data_field is not None:
        new_data["data"] = data_field

    # Preserve whitening matrix from old pkl so scd-edition can apply the
    # exact same linear transform rather than re-whitening from scratch.
    # Shape: (n_ext_ch, n_ext_ch) — stored as a single-element list (per port).
    if "w_mat" in old_data:
        w_mat_np = to_numpy(old_data["w_mat"])
        if w_mat_np.size > 0:
            new_data["w_mat"] = [w_mat_np]

    return new_data


# ---------------------------------------------------------------------------
# File-level helpers
# ---------------------------------------------------------------------------

def convert_file(
    src: Path,
    dst: Path,
    sampling_rate: int = 2000,
    mat_file: Path | None = None,
    mat_dirs: list[Path] | None = None,
    grid_key: str | None = None,
    start_sample: int = 0,
    time_differentiate: bool = False,
    extension_factor: int | None = None,
    peel_off_window_size_ms: int = 50,
):
    print(f"  Loading  : {src.name}")
    old_data = load_old_pkl(src)
    n_pkl_samples = len(old_data.get("source", [{}])[0]) if old_data.get("source") else None

    emg = n_ch = ch_idx = None

    # Try to resolve mat file
    resolved_mat = mat_file
    resolved_grid = grid_key

    if resolved_mat is None and mat_dirs:
        resolved_mat, resolved_grid = find_mat_for_pkl(src, mat_dirs)
        if resolved_mat:
            print(f"  Mat file  : {resolved_mat.name}  (grid: {resolved_grid})")
        else:
            print(f"  Mat file  : not found in {[str(d) for d in mat_dirs]}")

    if resolved_mat and resolved_mat.exists():
        try:
            # Auto-detect plateau start from force signal when start_sample is not
            # explicitly overridden by the caller (default 0).  The original SCD
            # decomposition operates on the plateau window only, so we must load
            # EMG from that same offset — otherwise stored timestamps point to the
            # wrong samples and STA replay in scd-edition will produce wrong sources.
            if start_sample == 0:
                plateau_start, _, _ = detect_plateau_from_mat(resolved_mat, resolved_grid)
            else:
                plateau_start = start_sample

            emg, n_ch, ch_idx = load_emg_from_mat(
                resolved_mat,
                grid_key=resolved_grid,
                start_sample=plateau_start,
                n_samples=n_pkl_samples,
            )
            print(f"  EMG shape : {emg.shape}  ({n_ch} channels, "
                  f"start_sample={plateau_start})")
        except Exception as e:
            print(f"  EMG load  : FAILED ({e}) — converting without data")

    new_data = convert(
        old_data,
        sampling_rate=sampling_rate,
        emg=emg,
        n_channels=n_ch,
        channel_indices_global=ch_idx,
        time_differentiate=time_differentiate,
        extension_factor=extension_factor,
        peel_off_window_size_ms=peel_off_window_size_ms,
    )

    n_mu = new_data["_n_motor_units"]
    has_data = "data" in new_data
    dst.parent.mkdir(parents=True, exist_ok=True)
    with open(dst, "wb") as f:
        pickle.dump(new_data, f)
    print(f"  Saved    : {dst.name}  ({n_mu} MUs, EMG={'yes' if has_data else 'no'})")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Convert old SCD pickles to scd-edition format",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__.split("Usage:")[1] if "Usage:" in __doc__ else "",
    )
    parser.add_argument("input", type=Path, help="Input .pkl file or directory")
    parser.add_argument("output", type=Path, help="Output .pkl file or directory")
    parser.add_argument("--sampling-rate", type=int, default=2000,
                        help="Sampling frequency in Hz (default: 2000)")
    parser.add_argument("--mat-file", type=Path, default=None,
                        help="Path to the original .mat file (embeds raw EMG)")
    parser.add_argument("--mat-dir", type=Path, action="append", dest="mat_dirs",
                        metavar="DIR", default=None,
                        help="Directory to search for .mat files (repeatable; auto-detected)")
    parser.add_argument("--grid-key", type=str, default=None,
                        help="Grid key to select from channel-selection JSON (e.g. '8mm_5x13_2')")
    parser.add_argument("--start-sample", type=int, default=0,
                        help="First sample index in mat file (if decomposition started mid-recording, default: 0)")
    args = parser.parse_args()

    mat_dirs = args.mat_dirs or []

    if args.input.is_dir():
        pkl_files = [p for p in sorted(args.input.glob("*.pkl")) if not p.name.endswith(".bak")]
        if not pkl_files:
            print(f"No .pkl files found in {args.input}")
            return
        print(f"Converting {len(pkl_files)} file(s) from {args.input} -> {args.output}\n")
        for src in pkl_files:
            dst = args.output / src.name
            convert_file(src, dst, args.sampling_rate, args.mat_file, mat_dirs, args.grid_key, args.start_sample)
            print()
    else:
        convert_file(args.input, args.output, args.sampling_rate, args.mat_file, mat_dirs, args.grid_key, args.start_sample)

    print("Done.")


if __name__ == "__main__":
    main()

"""
Merge single-grid scd-edition .pkl files into multi-port .pkl files.

Each contraction was decomposed per electrode grid, producing one pkl per grid.
This script groups those files by contraction (shared base stem) and merges
them into a single pkl where each grid is a separate port.

Grouping strategy:
  With --mat-dir: uses the sidecar channel-selection JSON to identify the grid
  key precisely, then extracts the task prefix from the remaining stem.
  Without --mat-dir: falls back to a regex heuristic
  (matches patterns like 10mm_4x8_2, 8mm_5x13 in the filename).

Output filename: {base_stem}.pkl  (the shared prefix, e.g. "343_..._Pyramid_1.pkl")
Port names:      {grid_key}_{muscle}  (e.g. "10mm_4x8_2_VastusLateralisRight")

Files whose names contain no recognisable grid key are skipped (they are
assumed to already be merged or unrelated).

Note: Uses pickle for SCD result files (trusted internal files only).

Usage:
    # Dry-run: show grouping, no files written
    python utils/merge_grid_pkls.py data/output/ --mat-dir /path/to/mat --dry-run

    # Merge, write alongside originals in same directory
    python utils/merge_grid_pkls.py data/output/ --mat-dir /path/to/mat

    # Merge to a separate output directory
    python utils/merge_grid_pkls.py data/output/ --mat-dir /path/to/mat --out-dir data/merged/
"""

import argparse
import io  # noqa: F401 (used by CPUUnpickler via import)
import pickle  # noqa: S403 — trusted SCD result files only
import re
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
from convert_pkl_to_scd_edition import (
    find_mat_for_pkl,
    convert,
    load_emg_from_mat,
    detect_plateau_from_mat,
)
from detect_and_upgrade_pkl import (
    detect_format,
    FORMAT_OLD,
    FORMAT_NEW,
    FORMAT_BUGGY_NEW,
    _get_electrode_type,
    _patch_peel_off_sequence,
    _patch_pulse_trains,
    _patch_mu_filters,
    _patch_preprocessing_params,
    _patch_channel_indices,
)


# ---------------------------------------------------------------------------
# Grid-key detection from filename
# ---------------------------------------------------------------------------

# Matches patterns like: 10mm_4x8, 10mm_4x8_2, 8mm_5x13, 8mm_5x13_2
_GRID_KEY_RE = re.compile(r'\d+mm_\d+x\d+(?:_\d+)?')

# Pipeline step suffixes that may appear in stems when merging from filtered folders
_KNOWN_SUFFIXES = ("_covisi_filtered", "_duplicates_removed")


def _strip_known_suffix(s: str) -> str:
    """Strip a trailing pipeline step suffix from a stem or muscle string."""
    for suf in _KNOWN_SUFFIXES:
        if s.endswith(suf):
            return s[: -len(suf)]
    return s


def _split_stem(pkl_path: Path, mat_dirs: list) -> tuple | None:
    """
    Return (base_stem, grid_key, muscle) or None if the file has no grid key.

    base_stem  — shared prefix for all grids of the same contraction
    grid_key   — e.g. "10mm_4x8_2"
    muscle     — e.g. "VastusLateralisRight" (may be empty string)
    """
    stem = pkl_path.stem

    # --- Strategy 1: use mat sidecar JSON to get exact grid key ---
    if mat_dirs:
        mat_file, grid_key = find_mat_for_pkl(pkl_path, [Path(d) for d in mat_dirs])
        if mat_file and grid_key:
            mat_stem = mat_file.stem
            if stem.startswith(mat_stem):
                remaining = stem[len(mat_stem):].lstrip("_")
                idx = remaining.find(grid_key)
                if idx >= 0:
                    task_prefix = remaining[:idx].rstrip("_")
                    muscle = _strip_known_suffix(remaining[idx + len(grid_key):].lstrip("_"))
                    base = _strip_known_suffix(
                        (mat_stem + "_" + task_prefix) if task_prefix else mat_stem
                    )
                    return base, grid_key, muscle

    # --- Strategy 2: regex heuristic (no mat file needed) ---
    m = _GRID_KEY_RE.search(stem)
    if not m:
        return None  # no grid key found — skip
    grid_key = m.group(0)
    base = _strip_known_suffix(stem[: m.start()].rstrip("_"))
    muscle = _strip_known_suffix(stem[m.end():].lstrip("_"))
    return base, grid_key, muscle


# ---------------------------------------------------------------------------
# Merging
# ---------------------------------------------------------------------------

def _unwrap_port(data: dict, key: str, default=None):
    """Return data[key][0] for single-port files, or default if key is absent."""
    val = data.get(key, [default])
    return val[0] if (isinstance(val, list) and len(val) > 0) else default


def merge_group(entries: list) -> dict:
    """
    Merge a list of (port_name, pkl_data) pairs into a multi-port pkl dict.
    entries should already be sorted in the desired port order.
    """
    ports              = []
    discharge_times    = []
    pulse_trains       = []
    mu_filters         = []
    peel_off_seqs      = []
    preproc_cfgs       = []
    electrodes         = []
    emg_masks          = []
    chans_per_electrode = []
    channel_indices    = []
    w_mats             = []
    emg_chunks         = []
    ch_offset          = 0
    first_data         = None

    for port_name, data in entries:
        if first_data is None:
            first_data = data

        ports.append(port_name)

        # Per-port signal arrays
        discharge_times.append(_unwrap_port(data, "discharge_times", []))
        pulse_trains.append(_unwrap_port(data, "pulse_trains", []))
        mu_filters.append(_unwrap_port(data, "mu_filters", []))

        # Peel-off sequence — handle both [list[dict]] and flat list[dict]
        raw_peel = data.get("peel_off_sequence", [[]])
        if (isinstance(raw_peel, list) and len(raw_peel) > 0
                and isinstance(raw_peel[0], list)):
            peel_off_seqs.append(raw_peel[0])   # per-port format: unwrap
        else:
            peel_off_seqs.append(raw_peel)       # flat single-port list

        # Preprocessing config — handle both [dict] and plain dict
        raw_cfg = data.get("preprocessing_config", [{}])
        if isinstance(raw_cfg, list):
            preproc_cfgs.append(raw_cfg[0] if raw_cfg else {})
        else:
            preproc_cfgs.append(raw_cfg)

        electrodes.append(_unwrap_port(data, "electrodes"))
        emg_masks.append(_unwrap_port(data, "emg_mask"))
        w_mats.append(data.get("w_mat"))   # None or ndarray

        # EMG — stack into a single (total_ch, n_samples) array
        emg = data.get("data")
        if emg is not None:
            emg = np.asarray(emg)
            if emg.ndim == 2 and emg.shape[0] > emg.shape[1]:
                emg = emg.T   # ensure (n_ch, n_samples)
            n_ch = emg.shape[0]
            emg_chunks.append(emg)
            chans_per_electrode.append(n_ch)
            # channel_indices are now global into the stacked EMG array
            channel_indices.append(list(range(ch_offset, ch_offset + n_ch)))
            ch_offset += n_ch
        else:
            n_ch = _unwrap_port(data, "chans_per_electrode") or 0
            chans_per_electrode.append(int(n_ch))
            channel_indices.append(None)

    merged = {
        "ports":                ports,
        "discharge_times":      discharge_times,
        "pulse_trains":         pulse_trains,
        "mu_filters":           mu_filters,
        "peel_off_sequence":    peel_off_seqs,
        "preprocessing_config": preproc_cfgs,
        "electrodes":           electrodes,
        "emg_mask":             emg_masks,
        "chans_per_electrode":  chans_per_electrode,
        "channel_indices":      channel_indices,
        "version":              1.0,
    }

    if first_data:
        merged["sampling_rate"] = first_data.get("sampling_rate", 2000)
        if "plateau_coords" in first_data:
            merged["plateau_coords"] = first_data["plateau_coords"]

    if emg_chunks:
        merged["data"] = np.vstack(emg_chunks)

    # Whitening matrices: keep as list (one per port) so scd-edition picks
    # the correct one during per-port peel-off replay.
    if any(w is not None for w in w_mats):
        merged["w_mat"] = w_mats

    return merged


# ---------------------------------------------------------------------------
# Format detection + conversion
# ---------------------------------------------------------------------------

def _load_and_convert(pkl_path: Path, mat_dirs: list,
                      sampling_rate: int = 2000,
                      time_differentiate: bool = False,
                      extension_factor: int | None = None,
                      peel_off_window_size_ms: int = 50) -> tuple[dict, str]:
    """
    Load a pkl and convert to scd-edition format if needed.
    Returns (data_dict, format_tag) where format_tag is one of
    'old→converted', 'buggy-new→converted', 'new', 'unknown'.
    """
    fmt, data = detect_format(pkl_path)

    if fmt == FORMAT_NEW:
        # Apply patches for known format bugs from the old converter
        _patch_peel_off_sequence(data)
        _patch_pulse_trains(data)
        _patch_mu_filters(data)
        _patch_channel_indices(data)
        # Also patch preprocessing_config with correct decomposition params
        _patch_preprocessing_params(data, time_differentiate=time_differentiate,
                                    extension_factor=extension_factor,
                                    peel_off_window_size_ms=peel_off_window_size_ms,
                                    sampling_rate=sampling_rate)
        # Re-embed EMG from mat file with correct plateau offset.
        # FORMAT_NEW pkls were often converted with start_sample=0, which loads
        # EMG from the beginning of the recording rather than the actual plateau
        # window.  When a mat file is available we auto-detect the plateau start
        # and reload the correct segment so that STA replay in scd-edition
        # operates on the same samples the original decomposition used.
        if mat_dirs:
            mat_file, grid_key = find_mat_for_pkl(pkl_path, [Path(d) for d in mat_dirs])
            if mat_file:
                try:
                    # Determine n_pkl_samples from existing data or pulse trains
                    existing_data = data.get("data")
                    if existing_data is not None:
                        _d = np.asarray(existing_data)
                        n_pkl_samples = _d.shape[1] if _d.ndim == 2 else int(_d.size)
                    else:
                        pt_list = data.get("pulse_trains", [[]])
                        pt0 = pt_list[0] if pt_list else []
                        n_pkl_samples = (
                            int(np.asarray(pt0[0]).size) if pt0 else None
                        )
                    plateau_start, _, _ = detect_plateau_from_mat(mat_file, grid_key)
                    emg_new, n_ch_new, _ = load_emg_from_mat(
                        mat_file, grid_key=grid_key,
                        start_sample=plateau_start, n_samples=n_pkl_samples,
                    )
                    data["data"]               = emg_new
                    data["chans_per_electrode"] = [n_ch_new]
                    data["channel_indices"]     = [list(range(n_ch_new))]
                    data["plateau_coords"]      = [0, int(emg_new.shape[1])]
                    print(f"      Re-embedded EMG: {emg_new.shape}  "
                          f"(start_sample={plateau_start})")
                except Exception as e:
                    print(f"      EMG re-embed failed for {pkl_path.name}: {e}")
        return data, "new"

    if fmt in (FORMAT_OLD, FORMAT_BUGGY_NEW):
        # For buggy-new, data is already loaded; for old, same.
        emg = n_ch = ch_idx = None
        etype = None
        if mat_dirs:
            mat_file, grid_key = find_mat_for_pkl(pkl_path, [Path(d) for d in mat_dirs])
            if mat_file:
                try:
                    n_pkl_samples = (
                        len(data.get("source", [{}])[0])
                        if data.get("source") else None
                    )
                    # Auto-detect plateau start — original SCD decomposed only the
                    # plateau window, so timestamps are relative to that offset.
                    plateau_start, _, _ = detect_plateau_from_mat(mat_file, grid_key)
                    emg, n_ch, ch_idx = load_emg_from_mat(
                        mat_file, grid_key=grid_key,
                        start_sample=plateau_start, n_samples=n_pkl_samples,
                    )
                    etype = _get_electrode_type(mat_file, grid_key)
                except Exception as e:
                    print(f"      EMG load failed for {pkl_path.name}: {e}")

        converted = convert(data, sampling_rate=sampling_rate,
                            emg=emg, n_channels=n_ch,
                            channel_indices_global=ch_idx,
                            time_differentiate=time_differentiate,
                            extension_factor=extension_factor,
                            peel_off_window_size_ms=peel_off_window_size_ms)
        if emg is not None and etype is not None:
            converted["electrodes"] = [etype]
        tag = "old→converted" if fmt == FORMAT_OLD else "buggy-new→converted"
        return converted, tag

    return data, "unknown"


# ---------------------------------------------------------------------------
# Main processing
# ---------------------------------------------------------------------------

def process(target: Path, out_dir: Path, mat_dirs: list,
            sampling_rate: int = 2000,
            time_differentiate: bool = False,
            extension_factor: int | None = None,
            peel_off_window_size_ms: int = 50,
            dry_run: bool = False, recursive: bool = True):

    pattern = "**/*.pkl" if recursive else "*.pkl"
    all_pkls = [
        p for p in sorted(target.glob(pattern))
        if not p.name.endswith(".bak")
    ]

    # Group files by base stem
    groups: dict[str, list] = defaultdict(list)
    skipped = []

    for pkl_path in all_pkls:
        result = _split_stem(pkl_path, mat_dirs)
        if result is None:
            skipped.append(pkl_path)
            continue
        base_stem, grid_key, muscle = result
        port_name = f"{grid_key}_{muscle}" if muscle else grid_key
        groups[base_stem].append((port_name, pkl_path))

    print(f"Found {len(all_pkls)} pkl file(s) → "
          f"{len(groups)} group(s), {len(skipped)} skipped (no grid key)\n")

    for base_stem in sorted(groups):
        entries = sorted(groups[base_stem])   # sort alphabetically by port name
        out_path = out_dir / f"{base_stem}.pkl"
        print(f"  [{base_stem}]")
        for pn, fp in entries:
            print(f"    + {pn}  ({fp.name})")
        print(f"    → {out_path.name}  ({len(entries)} port(s))")

        if dry_run:
            print()
            continue

        # Load (+ convert old-format files on the fly)
        loaded = []
        ok = True
        for port_name, pkl_path in entries:
            try:
                data, tag = _load_and_convert(
                    pkl_path, mat_dirs, sampling_rate,
                    time_differentiate=time_differentiate,
                    extension_factor=extension_factor,
                    peel_off_window_size_ms=peel_off_window_size_ms,
                )
                if tag == "unknown":
                    print(f"    WARN  {pkl_path.name}: unrecognised format — included as-is")
                else:
                    print(f"    load  {pkl_path.name}  [{tag}]")
                loaded.append((port_name, data))
            except Exception as e:
                print(f"    ERROR loading {pkl_path.name}: {e}")
                ok = False

        if not ok:
            print("    Skipping group due to load error.\n")
            continue

        # Merge
        try:
            merged = merge_group(loaded)
        except Exception as e:
            print(f"    ERROR merging: {e}")
            print()
            continue

        # Save
        out_dir.mkdir(parents=True, exist_ok=True)
        with open(out_path, "wb") as f:
            pickle.dump(merged, f)

        n_mus = sum(
            len(dt) for dt in merged["discharge_times"]
            if isinstance(dt, list)
        )
        if "data" in merged:
            emg_note = f"yes ({merged['data'].shape[0]} ch)"
        else:
            emg_note = "no"
        print(f"    Saved: {n_mus} total MUs, EMG={emg_note}")
        print()

    if skipped:
        print(f"\nSkipped ({len(skipped)} file(s) with no grid key in filename):")
        for p in skipped:
            print(f"  {p.name}")


def main():
    parser = argparse.ArgumentParser(
        description="Merge single-grid scd-edition pkl files into multi-port pkl files"
    )
    parser.add_argument("target", type=Path,
                        help="Directory containing single-grid .pkl files")
    parser.add_argument("--out-dir", type=Path, default=None,
                        help="Output directory (default: same as target)")
    parser.add_argument("--mat-dir", type=Path, action="append", dest="mat_dirs",
                        metavar="DIR", default=None,
                        help="Directory to search for .mat and sidecar JSON files "
                             "(repeatable). Improves grid-key detection accuracy.")
    parser.add_argument("--sampling-rate", type=int, default=2000,
                        help="Sampling rate in Hz used when converting old-format files "
                             "(default: 2000)")
    parser.add_argument("--time-differentiate", action="store_true",
                        help="Signal was time-differentiated during decomposition. "
                             "MUST match the original decomposition config.")
    parser.add_argument("--extension-factor", type=int, default=None,
                        help="Temporal extension factor used during decomposition. "
                             "If not given, inferred from filter shape (filter_dim/n_ch). "
                             "MUST match the original decomposition config.")
    parser.add_argument("--peel-off-window-ms", type=int, default=50,
                        help="Peel-off window size in ms used during decomposition "
                             "(default: 50). MUST match the original decomposition config.")
    parser.add_argument("--dry-run", action="store_true",
                        help="Show grouping without writing any files")
    parser.add_argument("--no-recursive", action="store_true",
                        help="Only scan the top level of target, not subdirectories")
    args = parser.parse_args()

    if not args.target.is_dir():
        print(f"ERROR: {args.target} is not a directory.")
        return

    out_dir = args.out_dir or args.target

    print(f"{'DRY RUN — ' if args.dry_run else ''}Target : {args.target}")
    print(f"{'DRY RUN — ' if args.dry_run else ''}Out dir: {out_dir}\n")

    process(
        target=args.target,
        out_dir=out_dir,
        mat_dirs=args.mat_dirs or [],
        sampling_rate=args.sampling_rate,
        time_differentiate=args.time_differentiate,
        extension_factor=args.extension_factor,
        peel_off_window_size_ms=args.peel_off_window_ms,
        dry_run=args.dry_run,
        recursive=not args.no_recursive,
    )


if __name__ == "__main__":
    main()

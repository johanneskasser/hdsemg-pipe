"""
Detect old SCD pickle format and upgrade in-place to scd-edition format.

Format detection:
  [old]       - has 'timestamps' but no 'ports'/'discharge_times' -> will upgrade
  [new]       - has 'ports' + 'discharge_times', no known issues -> skip
  [buggy-new] - has 'ports' + 'discharge_times' but still has the old
                None-values that crash scd-edition (data=None, chans_per_electrode=[None]).
                Will re-convert from .pkl.bak if available, otherwise skip.
  [unknown]   - unrecognised structure -> skip

When --mat-dir is given, raw EMG is always embedded (required for reliability scores
and MUAPs in scd-edition). Files without EMG are patched in-place automatically.

Note: Uses pickle for SCD result files (trusted internal files only).

Usage:
    # Check and upgrade a single file
    python utils/detect_and_upgrade_pkl.py file.pkl

    # Check and upgrade all .pkl files in a directory (recursively)
    python utils/detect_and_upgrade_pkl.py data/output/

    # Upgrade and embed EMG (recommended — enables reliability scores and MUAPs)
    python utils/detect_and_upgrade_pkl.py data/output/ --mat-dir /path/to/mat/files

    # Dry-run: only report, do not modify
    python utils/detect_and_upgrade_pkl.py data/output/ --mat-dir /path/to/mat/files --dry-run

    # Custom sampling rate
    python utils/detect_and_upgrade_pkl.py data/output/ --sampling-rate 2048
"""

import argparse
import io
import pickle  # noqa: S403 - trusted SCD result files only
import shutil
from pathlib import Path

import numpy as np
import torch

import sys
sys.path.insert(0, str(Path(__file__).parent))
from convert_pkl_to_scd_edition import CPUUnpickler, convert


FORMAT_OLD = "old"
FORMAT_NEW = "new"
FORMAT_BUGGY_NEW = "buggy-new"
FORMAT_UNKNOWN = "unknown"


def _is_buggy_new(data: dict) -> bool:
    """Return True if a new-format file still has the crash-causing None values."""
    # Symptom 1: 'data' key present with None value
    if "data" in data and data["data"] is None:
        return True
    # Symptom 2: chans_per_electrode is a list containing None
    chans = data.get("chans_per_electrode")
    if isinstance(chans, list) and any(v is None for v in chans):
        return True
    return False


def detect_format(path: Path):
    try:
        with open(path, "rb") as f:
            data = CPUUnpickler(f).load()
    except Exception:
        return FORMAT_UNKNOWN, None

    if not isinstance(data, dict):
        return FORMAT_UNKNOWN, None

    if "ports" in data and "discharge_times" in data:
        if _is_buggy_new(data):
            return FORMAT_BUGGY_NEW, data
        return FORMAT_NEW, data
    if "timestamps" in data and "ports" not in data:
        return FORMAT_OLD, data
    return FORMAT_UNKNOWN, data


def upgrade_in_place(path: Path, data: dict, sampling_rate: int = 2000, backup: bool = True,
                     mat_dirs: list = None):
    if backup:
        shutil.copy2(path, path.with_suffix(".pkl.bak"))

    emg = n_ch = ch_idx = None
    if mat_dirs:
        from convert_pkl_to_scd_edition import find_mat_for_pkl, load_emg_from_mat
        n_pkl_samples = len(data.get("source", [{}])[0]) if data.get("source") else None
        mat_file, grid_key = find_mat_for_pkl(path, [Path(d) for d in mat_dirs])
        if mat_file:
            try:
                emg, n_ch, ch_idx = load_emg_from_mat(mat_file, grid_key=grid_key, n_samples=n_pkl_samples)
                print(f"      EMG: {mat_file.name}  {emg.shape}")
            except Exception as e:
                print(f"      EMG load failed: {e}")

    new_data = convert(data, sampling_rate=sampling_rate, emg=emg, n_channels=n_ch, channel_indices_global=ch_idx)
    with open(path, "wb") as f:
        pickle.dump(new_data, f)


def _bak_path(path: Path) -> Path:
    return path.with_suffix(".pkl.bak")


# scd-edition electrode type strings (from ELECTRODE_GRIDS in edition_tab.py).
# Keyed by (rows, columns, ied_mm) from the channel-selection JSON.
# GR* entries: original scd-edition types (kept for backward compat with already-converted files).
# HD* entries: new types added in forked scd-edition.
_ELECTRODE_TYPE_MAP = {
    (5, 13,  4): "HD04MM1305",
    (5, 13,  8): "HD08MM1305",
    (8,  8, 10): "GR10MM0808",
    (4,  8, 10): "HD10MM0804",
    (4,  8,  5): "HD05MM0804",
    (20, 2,  5): "Thin-film",
}


def _get_electrode_type(mat_file: Path, grid_key: str | None) -> str | None:
    """
    Look up the scd-edition electrode type string for the given grid.
    Returns None if the grid dimensions don't match a known type.
    """
    if not mat_file or not grid_key:
        return None
    from scd_channel_utils import load_channel_selection_json, get_grids_from_json
    json_data = load_channel_selection_json(mat_file)
    if not json_data:
        return None
    grids = get_grids_from_json(json_data)
    matched = next((g for g in grids if g["grid_key"] == grid_key), None)
    if not matched:
        return None
    rows = matched.get("rows", 0)
    cols = matched.get("columns", 0)
    ied  = int(matched.get("inter_electrode_distance_mm", 0))
    return _ELECTRODE_TYPE_MAP.get((rows, cols, ied))


_PREPROCESSING_CONFIG_DEFAULTS = {
    "low_pass_cutoff":        500,
    "high_pass_cutoff":       10,
    "time_differentiate":     False,
    "extension_factor":       20,
    "whitening_method":       "zca",
    "autocorrelation_whiten": False,
    "clamp_percentile":       0.999,
    "edge_mask_size":         200,
}


def _patch_peel_off_sequence(data: dict) -> bool:
    """
    Rebuild peel_off_sequence from discharge_times if it is empty.
    scd-edition iterates this list to replay peel-off and compute full sources;
    an empty sequence → 0 sources computed → all MUs unreliable.
    Returns True if the dict was changed.
    """
    peel_seq = data.get("peel_off_sequence")
    if not peel_seq or not isinstance(peel_seq, list):
        return False
    discharge_times = data.get("discharge_times", [])
    changed = False
    for port_idx, port_seq in enumerate(peel_seq):
        if port_seq:  # already populated
            continue
        if port_idx >= len(discharge_times):
            continue
        dt_port = discharge_times[port_idx]
        if not isinstance(dt_port, list) or len(dt_port) == 0:
            continue
        import numpy as np
        new_seq = []
        for mu_idx, ts in enumerate(dt_port):
            ts_arr = np.asarray(ts).flatten().astype(np.int64)
            new_seq.append({"accepted_unit_idx": mu_idx, "timestamps": ts_arr.tolist()})
        peel_seq[port_idx] = new_seq
        changed = True
    if changed:
        data["peel_off_sequence"] = peel_seq
    return changed


def _patch_pulse_trains(data: dict) -> bool:
    """
    Fix pulse_trains stored as (n_samples, n_mu) 2-D array to a list of 1-D arrays.

    The old converter used np.hstack on column vectors, producing (n_samples, n_mu).
    scd-edition's _ensure_list_of_arrays() splits by the first axis (rows), yielding
    n_samples "units" of length n_mu each — completely wrong.  Correct format is a
    list of n_mu 1-D arrays (each column of the original 2-D array).
    Returns True if the dict was changed.
    """
    import numpy as np
    pt_list = data.get("pulse_trains")
    dt_list = data.get("discharge_times", [])
    if not pt_list:
        return False
    changed = False
    for i, port_pt in enumerate(pt_list):
        if not isinstance(port_pt, np.ndarray) or port_pt.ndim != 2:
            continue
        n_mu = len(dt_list[i]) if i < len(dt_list) and isinstance(dt_list[i], list) else 0
        if n_mu == 0 or port_pt.shape[1] != n_mu:
            continue
        pt_list[i] = [port_pt[:, j] for j in range(n_mu)]
        changed = True
    if changed:
        data["pulse_trains"] = pt_list
    return changed


def _patch_mu_filters(data: dict) -> bool:
    """
    Fix mu_filters stored as (n_ext_ch, n_mu) 2-D array to a list of 1-D arrays.

    The old converter used np.hstack on column vectors, producing (n_ext_ch, n_mu).
    scd-edition's _normalise_filters() splits by the first axis (rows), treating each
    row as a separate filter — yielding n_ext_ch "filters" of length n_mu each, which
    is completely wrong.  Correct format is a list of n_mu 1-D arrays of length n_ext_ch.
    Returns True if the dict was changed.
    """
    import numpy as np
    mf_list = data.get("mu_filters")
    dt_list = data.get("discharge_times", [])
    if not mf_list:
        return False
    changed = False
    for i, port_mf in enumerate(mf_list):
        if not isinstance(port_mf, np.ndarray) or port_mf.ndim != 2:
            continue
        n_mu = len(dt_list[i]) if i < len(dt_list) and isinstance(dt_list[i], list) else 0
        if n_mu == 0 or port_mf.shape[1] != n_mu:
            continue
        mf_list[i] = [port_mf[:, j] for j in range(n_mu)]
        changed = True
    if changed:
        data["mu_filters"] = mf_list
    return changed


def _patch_channel_indices(data: dict) -> bool:
    """
    Fix global channel_indices to local (0..n_ch-1) when the stored indices exceed
    the bounds of the embedded EMG array.

    The old converter sometimes stored the original global mat-file indices instead
    of the local indices needed to index into the stored data array.
    Returns True if the dict was changed.
    """
    import numpy as np
    raw_data = data.get("data")
    if raw_data is None:
        return False
    emg = np.asarray(raw_data)
    n_ch_total = emg.shape[0]
    ch_idx_list = data.get("channel_indices")
    if not ch_idx_list:
        return False
    changed = False
    ch_offset = 0
    chans_per = data.get("chans_per_electrode", [])
    for i, ci in enumerate(ch_idx_list):
        if ci is None:
            continue
        n_ch = int(chans_per[i]) if i < len(chans_per) and chans_per[i] else None
        if n_ch is None and isinstance(ci, list):
            n_ch = len(ci)
        if n_ch is None:
            continue
        if isinstance(ci, list) and ci and max(ci) >= n_ch_total:
            # Global indices out of bounds — replace with local sequential range
            ch_idx_list[i] = list(range(ch_offset, ch_offset + n_ch))
            changed = True
        ch_offset += n_ch
    if changed:
        data["channel_indices"] = ch_idx_list
    return changed


def _patch_preprocessing_params(
    data: dict,
    time_differentiate: bool | None = None,
    extension_factor: int | None = None,
    peel_off_window_size_ms: int | None = None,
    sampling_rate: int | None = None,
    notch_params: list | None = None,
) -> bool:
    """
    Overwrite specific preprocessing_config entries with the correct decomposition
    parameters.  Extension factor is also auto-inferred from the filter shape when
    extension_factor is None.

    Only updates values that differ from what is stored.
    Returns True if any entry was changed.
    """
    import numpy as np
    cfg_list = data.get("preprocessing_config")
    if not cfg_list:
        return False

    sr = sampling_rate or data.get("sampling_rate", 2000)
    changed = False

    for port_idx, cfg in enumerate(cfg_list):
        if not isinstance(cfg, dict):
            continue

        # Auto-infer extension_factor from filter shape for this port
        ext = extension_factor
        if ext is None:
            mf_list = data.get("mu_filters", [])
            chans_list = data.get("chans_per_electrode", [])
            if port_idx < len(mf_list) and port_idx < len(chans_list):
                port_mf = mf_list[port_idx]
                n_ch = chans_list[port_idx]
                if n_ch and n_ch > 0:
                    if isinstance(port_mf, list) and port_mf:
                        filt_dim = int(np.asarray(port_mf[0]).size)
                    elif isinstance(port_mf, np.ndarray):
                        filt_dim = port_mf.shape[0]
                    else:
                        filt_dim = None
                    if filt_dim and filt_dim % n_ch == 0:
                        ext = filt_dim // n_ch

        updates = {}
        if ext is not None and cfg.get("extension_factor") != ext:
            updates["extension_factor"] = ext
        if time_differentiate is not None and cfg.get("time_differentiate") != time_differentiate:
            updates["time_differentiate"] = time_differentiate
        if peel_off_window_size_ms is not None:
            target_samples = int(peel_off_window_size_ms * sr / 1000)
            if cfg.get("peel_off_window_size") != target_samples:
                updates["peel_off_window_size"] = target_samples

        if notch_params is not None and cfg.get("notch_params") != notch_params:
            updates["notch_params"] = notch_params

        if updates:
            cfg.update(updates)
            changed = True

    if changed:
        data["preprocessing_config"] = cfg_list
    return changed


def _patch_preprocessing_config(data: dict) -> bool:
    """
    Ensure preprocessing_config[0] contains all keys scd-edition expects.
    Fills missing keys with main.py defaults.  Returns True if the dict was changed.
    """
    cfg_list = data.get("preprocessing_config", [{}])
    if not cfg_list or not isinstance(cfg_list[0], dict):
        return False
    cfg = cfg_list[0]
    sr = data.get("sampling_rate", 2000)
    needed = {
        "sampling_frequency":  sr,
        "peel_off_window_size": int(50 * sr / 1000),
        **_PREPROCESSING_CONFIG_DEFAULTS,
    }
    missing = {k: v for k, v in needed.items() if k not in cfg}
    if not missing:
        return False
    cfg.update(missing)
    data["preprocessing_config"] = cfg_list
    return True


def _add_emg_to_new(path: Path, data: dict, mat_dirs: list, dry_run: bool) -> bool:
    """
    Embed raw EMG into an already-converted new-format file that lacks 'data'.
    Also patches preprocessing_config if keys are missing.
    Returns True if action was taken (or would be taken in dry-run).
    """
    from convert_pkl_to_scd_edition import find_mat_for_pkl, load_emg_from_mat

    # n_samples from pulse_trains shape
    pt = data.get("pulse_trains", [[]])[0]
    n_pkl_samples = pt.shape[0] if hasattr(pt, "shape") else None

    mat_file, grid_key = find_mat_for_pkl(path, [Path(d) for d in mat_dirs])
    if not mat_file:
        print(f"  [no-emg]   {path.name}  -- mat file not found, skipped")
        return False

    if dry_run:
        print(f"  [no-emg]   {path.name}  -- would embed EMG from {mat_file.name} (grid: {grid_key})")
        return True

    try:
        emg, n_ch, ch_idx = load_emg_from_mat(mat_file, grid_key=grid_key, n_samples=n_pkl_samples)
        data["data"] = emg
        data["chans_per_electrode"] = [int(n_ch)]
        # Local indices (0..n_ch-1): scd-edition indexes into the stored EMG, not the full recording
        data["channel_indices"] = [list(range(n_ch))]
        data["electrodes"] = [_get_electrode_type(mat_file, grid_key)]
        _patch_preprocessing_config(data)
        with open(path, "wb") as f:
            pickle.dump(data, f)
        etype = data["electrodes"][0] or "unknown grid"
        print(f"  [emg-added]{path.name}  ({n_ch} ch, {emg.shape[1]} samples, {etype})")
        return True
    except Exception as e:
        print(f"  [ERROR]    {path.name}  -- EMG embed failed: {e}")
        return False


def process_path(target: Path, sampling_rate=2000, dry_run=False, no_backup=False,
                 recursive=True, mat_dirs=None):
    counts = {"old": 0, "new": 0, "no_emg": 0, "buggy": 0, "unknown": 0, "upgraded": 0, "errors": 0}

    if target.is_file():
        files = [target]
    elif target.is_dir():
        pattern = "**/*.pkl" if recursive else "*.pkl"
        files = [p for p in sorted(target.glob(pattern)) if not p.name.endswith(".bak")]
    else:
        print(f"ERROR: {target} is not a file or directory.")
        return counts

    for path in files:
        fmt, data = detect_format(path)

        if fmt == FORMAT_NEW:
            has_emg = "data" in data and data["data"] is not None
            if not has_emg and mat_dirs:
                # Always embed EMG when --mat-dir is given and file lacks it
                counts["no_emg"] += 1
                ok = _add_emg_to_new(path, data, mat_dirs, dry_run)
                if ok and not dry_run:
                    counts["upgraded"] += 1
                elif not ok and not dry_run:
                    counts["errors"] += 1
            else:
                # File already has EMG — patch preprocessing_config, channel_indices, electrodes,
                # peel_off_sequence, pulse_trains, and mu_filters if needed
                changed = _patch_preprocessing_config(data)
                if _patch_peel_off_sequence(data):
                    changed = True
                if _patch_pulse_trains(data):
                    changed = True
                if _patch_mu_filters(data):
                    changed = True
                if _patch_channel_indices(data):
                    changed = True
                if has_emg:
                    emg_array = data["data"]
                    n_ch = emg_array.shape[0]
                    ch_idx = data.get("channel_indices", [None])
                    # Fix global->local if any stored index exceeds the EMG array bounds
                    if (ch_idx and ch_idx[0] is not None
                            and isinstance(ch_idx[0], (list, range))
                            and max(ch_idx[0]) >= n_ch):
                        data["channel_indices"] = [list(range(n_ch))]
                        changed = True
                    # Fix electrodes if still None and mat_dirs available
                    if data.get("electrodes", [None])[0] is None and mat_dirs:
                        from convert_pkl_to_scd_edition import find_mat_for_pkl
                        mat_file, grid_key = find_mat_for_pkl(path, [Path(d) for d in mat_dirs])
                        etype = _get_electrode_type(mat_file, grid_key)
                        if etype is not None:
                            data["electrodes"] = [etype]
                            changed = True
                if not dry_run and changed:
                    with open(path, "wb") as f:
                        pickle.dump(data, f)
                counts["new"] += 1
                emg_note = "" if has_emg else "  (no EMG — use --mat-dir to embed)"
                print(f"  [new]      {path}{emg_note}")

        elif fmt == FORMAT_OLD:
            counts["old"] += 1
            n_mu = len(data.get("timestamps", []))
            if dry_run:
                print(f"  [old]      {path}  ({n_mu} MUs) -- would upgrade")
            else:
                try:
                    upgrade_in_place(path, data, sampling_rate=sampling_rate, backup=not no_backup, mat_dirs=mat_dirs)
                    bak_note = "  (backup: .pkl.bak)" if not no_backup else ""
                    print(f"  [upgraded] {path}  ({n_mu} MUs){bak_note}")
                    counts["upgraded"] += 1
                except Exception as e:
                    print(f"  [ERROR]    {path}  -- {e}")
                    counts["errors"] += 1

        elif fmt == FORMAT_BUGGY_NEW:
            counts["buggy"] += 1
            bak = _bak_path(path)
            if not bak.exists():
                print(f"  [buggy-new]{path}  -- no .bak found, cannot re-convert (skip)")
                continue
            bak_fmt, bak_data = detect_format(bak)
            if bak_fmt != FORMAT_OLD:
                print(f"  [buggy-new]{path}  -- .bak is not old format ({bak_fmt}), skip")
                continue
            n_mu = len(bak_data.get("timestamps", []))
            if dry_run:
                print(f"  [buggy-new]{path}  ({n_mu} MUs) -- would re-convert from .bak")
            else:
                try:
                    # Overwrite the buggy file directly from .bak data (no new backup needed)
                    upgrade_in_place(path, bak_data, sampling_rate=sampling_rate, backup=False, mat_dirs=mat_dirs)
                    print(f"  [fixed]    {path}  ({n_mu} MUs)  (re-converted from .bak)")
                    counts["upgraded"] += 1
                except Exception as e:
                    print(f"  [ERROR]    {path}  -- {e}")
                    counts["errors"] += 1

        else:
            counts["unknown"] += 1
            print(f"  [unknown]  {path}  -- skipped (unrecognised format)")

    return counts


def restore_from_bak(target: Path, dry_run: bool = False, recursive: bool = True):
    """For every .pkl.bak found: delete the corresponding .pkl and rename .bak → .pkl."""
    if not target.is_dir():
        print(f"ERROR: {target} is not a directory.")
        return

    pattern = "**/*.pkl.bak" if recursive else "*.pkl.bak"
    bak_files = sorted(target.glob(pattern))

    if not bak_files:
        print("No .pkl.bak files found.")
        return

    restored = 0
    for bak in bak_files:
        pkl = bak.with_suffix("")  # strips .bak → .pkl
        if dry_run:
            note = "(would delete + rename)" if pkl.exists() else "(would rename)"
            print(f"  [restore]  {pkl.name}  {note}")
        else:
            if pkl.exists():
                pkl.unlink()
            bak.rename(pkl)
            print(f"  [restored] {pkl.name}")
        restored += 1

    print(f"\n{'Would restore' if dry_run else 'Restored'} {restored} file(s).")


def main():
    parser = argparse.ArgumentParser(
        description="Detect and in-place upgrade old SCD pickles to scd-edition format"
    )
    parser.add_argument("target", type=Path, help=".pkl file or directory to process")
    parser.add_argument("--restore", action="store_true",
                        help="Restore .pkl files from .pkl.bak backups (delete converted, "
                             "rename .bak → .pkl). Use before re-running upgrade.")
    parser.add_argument("--sampling-rate", type=int, default=2000,
                        help="Sampling frequency in Hz for old files (default: 2000)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Report what would be changed without modifying files")
    parser.add_argument("--no-backup", action="store_true",
                        help="Skip creating .pkl.bak backup before overwriting")
    parser.add_argument("--no-recursive", action="store_true",
                        help="Only scan top-level of directory, not subdirectories")
    parser.add_argument("--mat-dir", type=Path, action="append", dest="mat_dirs",
                        metavar="DIR", default=None,
                        help="Directory to search for .mat files to embed raw EMG (repeatable). "
                             "When given, EMG is always embedded into files that lack it.")
    args = parser.parse_args()

    if args.restore:
        print(f"{'DRY RUN -- ' if args.dry_run else ''}Restoring from .bak: {args.target}\n")
        restore_from_bak(args.target, dry_run=args.dry_run, recursive=not args.no_recursive)
        return

    print(f"{'DRY RUN -- ' if args.dry_run else ''}Scanning: {args.target}\n")

    counts = process_path(
        args.target,
        sampling_rate=args.sampling_rate,
        dry_run=args.dry_run,
        no_backup=args.no_backup,
        recursive=not args.no_recursive,
        mat_dirs=args.mat_dirs or [],
    )

    print()
    print(f"Summary: {counts['new']} already new | {counts['no_emg']} emg-added | "
          f"{counts['old']} old | {counts['buggy']} buggy-new | "
          f"{counts['unknown']} unknown | {counts['upgraded']} upgraded | {counts['errors']} errors")


if __name__ == "__main__":
    main()

"""
Backfill the "Performed Path" reference signal into existing scd-edition PKL files.

Existing PKL files (including edited ones) that were created before ref-signal
embedding was added have an empty or absent aux_channels list.  This script
finds the original .mat file for each PKL, extracts the Performed Path channel
via EMGFile (reads the MAT Description field -- no hardcoded indices), and writes
it into aux_channels so that downstream PKL->JSON export produces the correct
REF_SIGNAL instead of all-zeros.

The PKL data and discharge_times are never touched; only aux_channels is added.
A .bak backup is written before modifying (skipped if one already exists).

Edited-file naming: scd-edition appends "_edited" (or "_edited2" etc.) to PKL
stems after manual cleaning.  This suffix is stripped before searching for the
corresponding .mat file so that "recording_edited.pkl" correctly matches
"recording.mat".

Note: PKL files are trusted internal SCD decomposition outputs.

Usage:
    # Single PKL directory, single MAT directory
    python repair_pkl_ref_signal.py pkl_dir/ --mat-dir mat_dir/

    # Multiple MAT search directories
    python repair_pkl_ref_signal.py pkl_dir/ --mat-dir mat_dir1/ --mat-dir mat_dir2/

    # Preview only -- no files written
    python repair_pkl_ref_signal.py pkl_dir/ --mat-dir mat_dir/ --dry-run

    # Recurse into subdirectories
    python repair_pkl_ref_signal.py pkl_dir/ --mat-dir mat_dir/ --recursive
"""

import argparse
import pickle  # noqa: S403 -- trusted SCD decomposition outputs only
import re
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
from convert_pkl_to_scd_edition import (
    detect_plateau_from_mat,
    find_mat_for_pkl,
    load_ref_signal_from_mat,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _strip_edit_suffix(pkl_path: Path) -> Path:
    """Return a path with trailing _edited / _edited2 / _edited_N stripped.

    "recording_8mm_5x13_2_edited.pkl"  ->  "recording_8mm_5x13_2.pkl"
    "recording_edited2.pkl"             ->  "recording.pkl"

    The original path is unchanged; a new Path is returned for MAT lookup only.
    """
    stem = re.sub(r"_edited\d*$", "", pkl_path.stem, flags=re.IGNORECASE)
    return pkl_path.with_name(stem + pkl_path.suffix)


def _has_ref_signal(pkl: dict) -> bool:
    """Return True if aux_channels already contains a ref_signal entry."""
    for entry in pkl.get("aux_channels", []):
        if not isinstance(entry, dict):
            continue
        meta = entry.get("meta", {})
        if meta.get("type") == "ref_signal":
            return True
        if "performed" in str(meta.get("name", "")).lower():
            return True
    return False


def _infer_n_samples(pkl: dict) -> int | None:
    """Infer number of plateau samples from plateau_coords or pulse_train length."""
    coords = pkl.get("plateau_coords")
    if coords and len(coords) >= 2:
        n = int(coords[1]) - int(coords[0])
        if n > 0:
            return n
    for pt_port in pkl.get("pulse_trains", []):
        for pt in pt_port:
            if pt is not None:
                arr = np.asarray(pt)
                if arr.size > 0:
                    return int(arr.size)
    return None


def _infer_grid_key(pkl: dict, mat_path: Path) -> str | None:
    """Match port names against grids known from the MAT file's Description."""
    from hdsemg_shared.fileio.file_io import EMGFile

    ports = pkl.get("ports", [])
    if not ports:
        return None

    try:
        emg_file = EMGFile.load(str(mat_path))
        known_keys = {g.grid_key for g in emg_file.grids}
    except Exception:
        known_keys = set()

    for port in ports:
        if port in known_keys:
            return port

    # Fall back to first port; load_ref_signal_from_mat will use grids[0] if
    # the name doesn't match any known grid key.
    return ports[0] if ports else None


# ---------------------------------------------------------------------------
# Core repair function
# ---------------------------------------------------------------------------

def repair(
    pkl_path: Path,
    mat_dirs: list[Path],
    *,
    dry_run: bool = False,
) -> str:
    """Repair a single PKL file.  Returns a short status string."""
    with open(pkl_path, "rb") as f:
        pkl = pickle.load(f)  # noqa: S301 -- trusted internal SCD output

    if _has_ref_signal(pkl):
        return "skip  (ref_signal already present)"

    # Strip _edited suffix so "recording_edited.pkl" matches "recording.mat".
    # Try the exact stripped stem first (e.g. "recording_Pyramid_4.mat"), then
    # fall back to find_mat_for_pkl's progressive suffix trimming.
    lookup_path = _strip_edit_suffix(pkl_path)
    mat_path = next(
        (d / f"{lookup_path.stem}.mat" for d in mat_dirs
         if (d / f"{lookup_path.stem}.mat").exists()),
        None,
    )
    if mat_path is None:
        mat_path, _ = find_mat_for_pkl(lookup_path, mat_dirs)
    if mat_path is None:
        return "skip  (no matching .mat file found)"

    grid_key = _infer_grid_key(pkl, mat_path)
    n_samples = _infer_n_samples(pkl)

    try:
        plateau_start, _, _ = detect_plateau_from_mat(mat_path, grid_key)
    except Exception as exc:
        return f"error (plateau detection failed: {exc})"

    try:
        ref_sig, ref_chan_idx = load_ref_signal_from_mat(
            mat_path,
            grid_key=grid_key,
            start_sample=plateau_start,
            n_samples=n_samples,
        )
    except Exception as exc:
        return f"error (ref signal load failed: {exc})"

    if ref_chan_idx == -1:
        return f"skip  (performed path not found in {mat_path.name})"

    aux_entry = {
        "data": ref_sig.astype(np.float64),
        "meta": {"name": "Performed Path", "type": "ref_signal"},
        "start_chan": ref_chan_idx,
        "end_chan": ref_chan_idx + 1,
    }

    existing_aux = pkl.get("aux_channels", [])
    new_aux = list(existing_aux) if isinstance(existing_aux, list) else []
    new_aux.append(aux_entry)

    if dry_run:
        return (
            f"would patch  mat={mat_path.name}  "
            f"grid={grid_key}  chan={ref_chan_idx}  samples={ref_sig.shape[0]}"
        )

    # Backup before modifying (never overwrite an existing backup)
    bak_path = pkl_path.with_suffix(".pkl.bak")
    bak_created = not bak_path.exists()
    if bak_created:
        bak_path.write_bytes(pkl_path.read_bytes())

    patched = dict(pkl)
    patched["aux_channels"] = new_aux

    with open(pkl_path, "wb") as f:
        pickle.dump(patched, f)  # noqa: S301 -- trusted internal SCD output

    return (
        f"patched  mat={mat_path.name}  grid={grid_key}  "
        f"chan={ref_chan_idx}  samples={ref_sig.shape[0]}  "
        f"bak={'created' if bak_created else 'existed'}"
    )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Backfill Performed Path ref signal into existing scd-edition PKL files",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__.split("Usage:")[1] if "Usage:" in __doc__ else "",
    )
    parser.add_argument("pkl_dir", type=Path,
                        help="Directory containing .pkl files to repair")
    parser.add_argument("--mat-dir", type=Path, action="append", dest="mat_dirs",
                        metavar="DIR", required=True,
                        help="Directory to search for .mat files (repeatable)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print what would happen without writing any files")
    parser.add_argument("--recursive", action="store_true",
                        help="Search pkl_dir recursively for .pkl files")
    args = parser.parse_args()

    pattern = "**/*.pkl" if args.recursive else "*.pkl"
    pkl_files = [
        p for p in sorted(args.pkl_dir.glob(pattern))
        if not p.name.endswith(".bak")
    ]

    if not pkl_files:
        print(f"No .pkl files found in {args.pkl_dir}")
        return

    print(
        f"{'DRY RUN -- ' if args.dry_run else ''}"
        f"Repairing {len(pkl_files)} PKL file(s)\n"
        f"  pkl_dir  : {args.pkl_dir}\n"
        f"  mat_dirs : {[str(d) for d in args.mat_dirs]}\n"
    )

    counts = {"patched": 0, "skipped": 0, "error": 0}

    for pkl_path in pkl_files:
        try:
            status = repair(pkl_path, args.mat_dirs, dry_run=args.dry_run)
        except Exception as exc:
            status = f"error ({exc})"

        first_word = status.split()[0].rstrip("(")
        if first_word in ("patched", "would"):
            counts["patched"] += 1
        elif first_word == "error":
            counts["error"] += 1
        else:
            counts["skipped"] += 1

        print(f"  {pkl_path.name:<60}  {status}")

    print(
        f"\nDone.  patched={counts['patched']}  "
        f"skipped={counts['skipped']}  errors={counts['error']}"
    )


if __name__ == "__main__":
    main()

"""
Repair scd-edition PKL files where peel_off_sequence timestamps were not
updated with edited discharge times (bug in scd-edition <=0.1.0).

Symptom: Edits made in scd-edition (spike deletions/additions) are visible
when saving (discharge_times is updated) but are lost on the next open because
peel_off_sequence still contains the original decomposition timestamps.

This script patches the peel_off_sequence entries in-place by copying the
edited timestamps from discharge_times into each entry.

Note: Uses pickle for loading/saving SCD result files (trusted internal files only).

Usage:
    python repair_peel_off_sequence.py file_edited.pkl
    python repair_peel_off_sequence.py file_edited.pkl --out file_repaired.pkl
    python repair_peel_off_sequence.py *.pkl               # batch
"""

import argparse
import pickle  # noqa: S403 — trusted SCD result files only
import sys
from pathlib import Path

import numpy as np


def _repair(data: dict) -> tuple[dict, list[str]]:
    """
    Returns a patched copy of data and a list of human-readable change notes.
    Raises ValueError if the file does not have the expected structure.
    """
    if "peel_off_sequence" not in data:
        raise ValueError("No 'peel_off_sequence' key — nothing to repair.")
    if "discharge_times" not in data:
        raise ValueError("No 'discharge_times' key — cannot determine edited timestamps.")

    peel = data["peel_off_sequence"]
    dt   = data["discharge_times"]

    if not (isinstance(peel, list) and len(peel) > 0 and isinstance(peel[0], list)):
        raise ValueError("peel_off_sequence is not in per-port list format.")

    notes = []
    new_peel = []

    for port_idx, port_seq in enumerate(peel):
        port_dt = dt[port_idx] if port_idx < len(dt) else []
        new_port_seq = []

        for entry in port_seq:
            uid = entry.get("accepted_unit_idx")
            if uid is None:
                new_port_seq.append(entry)
                continue

            if uid >= len(port_dt):
                new_port_seq.append(entry)
                notes.append(f"  port {port_idx} MU {uid}: no discharge_times entry — skipped")
                continue

            edited_ts = np.asarray(port_dt[uid], dtype=np.int64).flatten()
            old_ts    = np.asarray(entry.get("timestamps", []), dtype=np.int64).flatten()

            if np.array_equal(np.sort(edited_ts), np.sort(old_ts)):
                new_port_seq.append(entry)
                notes.append(f"  port {port_idx} MU {uid}: unchanged ({len(edited_ts)} spikes)")
            else:
                new_port_seq.append({**entry, "timestamps": edited_ts.tolist()})
                notes.append(
                    f"  port {port_idx} MU {uid}: {len(old_ts)} → {len(edited_ts)} spikes"
                    f"  (Δ {len(edited_ts) - len(old_ts):+d})"
                )

        new_peel.append(new_port_seq)

    repaired = {**data, "peel_off_sequence": new_peel}
    return repaired, notes


def repair_file(src: Path, dst: Path) -> None:
    print(f"Loading  : {src.name}")
    with open(src, "rb") as f:
        data = pickle.load(f)  # noqa: S301

    try:
        repaired, notes = _repair(data)
    except ValueError as e:
        print(f"  SKIP: {e}")
        return

    for note in notes:
        print(note)

    dst.parent.mkdir(parents=True, exist_ok=True)
    with open(dst, "wb") as f:
        pickle.dump(repaired, f)
    print(f"Saved    : {dst.name}\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("inputs", nargs="+", type=Path,
                        help="PKL file(s) to repair")
    parser.add_argument("--out", type=Path, default=None,
                        help="Output path (single-file mode only). "
                             "Default: overwrite in-place with .bak backup.")
    args = parser.parse_args()

    files = [p for p in args.inputs if p.exists()]
    if not files:
        print("No files found.", file=sys.stderr)
        sys.exit(1)

    if args.out and len(files) > 1:
        print("--out can only be used with a single input file.", file=sys.stderr)
        sys.exit(1)

    for src in files:
        if args.out:
            dst = args.out
        else:
            bak = src.with_suffix(".bak")
            src.rename(bak)
            print(f"  Backup : {bak.name}")
            dst = src
        repair_file(src if args.out else bak, dst)

    print("Done.")


if __name__ == "__main__":
    main()

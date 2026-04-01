"""
Restore .pkl files from .pkl.bak backups.

For every .pkl.bak found in the target directory:
  1. Delete the corresponding .pkl (if it exists).
  2. Rename .pkl.bak → .pkl.

Usage:
    # Dry-run: show what would happen
    python utils/restore_from_bak.py data/output/ --dry-run

    # Restore all
    python utils/restore_from_bak.py data/output/

    # Non-recursive (top-level only)
    python utils/restore_from_bak.py data/output/ --no-recursive
"""

import argparse
from pathlib import Path


def restore(target: Path, dry_run: bool = False, recursive: bool = True):
    pattern = "**/*.pkl.bak" if recursive else "*.pkl.bak"
    bak_files = sorted(target.glob(pattern))

    if not bak_files:
        print("No .pkl.bak files found.")
        return

    restored = 0
    skipped  = 0

    for bak in bak_files:
        pkl = bak.with_suffix("")  # strips .bak → .pkl

        if dry_run:
            action = f"would delete {pkl.name} + rename {bak.name} → {pkl.name}"
            print(f"  [dry-run] {bak.parent / action}")
        else:
            if pkl.exists():
                pkl.unlink()
            bak.rename(pkl)
            print(f"  [restored] {pkl}")

        restored += 1

    print(f"\nDone: {restored} file(s) {'would be ' if dry_run else ''}restored.")


def main():
    parser = argparse.ArgumentParser(
        description="Restore .pkl files from .pkl.bak backups"
    )
    parser.add_argument("target", type=Path, help="Directory to scan")
    parser.add_argument("--dry-run", action="store_true",
                        help="Report what would happen without making changes")
    parser.add_argument("--no-recursive", action="store_true",
                        help="Only scan top-level directory")
    args = parser.parse_args()

    if not args.target.is_dir():
        print(f"ERROR: {args.target} is not a directory.")
        return

    print(f"{'DRY RUN — ' if args.dry_run else ''}Scanning: {args.target}\n")
    restore(args.target, dry_run=args.dry_run, recursive=not args.no_recursive)


if __name__ == "__main__":
    main()

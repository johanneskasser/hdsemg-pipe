"""Helpers for loading persisted file lists and reporting load failures."""
import os
from typing import Iterable, List, Sequence, Tuple

from PyQt5.QtWidgets import QMessageBox

_MAX_LISTED = 10


def rebase_paths_to_folder(paths: Iterable[str], folder: str) -> List[str]:
    """Map persisted (possibly stale, absolute) paths onto files in *folder* by basename.

    Workfolders can be moved or renamed after a manifest was written, which leaves
    absolute paths in sidecar JSONs pointing nowhere. Only files that actually
    exist in *folder* are returned; order of *paths* is preserved.
    """
    rebased = []
    for p in paths:
        # Handle both Windows and POSIX separators regardless of the current OS.
        name = os.path.basename(str(p).replace("\\", "/"))
        candidate = os.path.normpath(os.path.join(folder, name))
        if os.path.isfile(candidate) and candidate not in rebased:
            rebased.append(candidate)
    return rebased


def basenames(paths: Iterable[str]) -> set:
    return {os.path.basename(str(p).replace("\\", "/")) for p in paths}


def show_load_errors(parent, errors: Sequence[Tuple[str, str]], title: str = "Loading Error") -> None:
    """Show ONE dialog summarising all file load failures.

    *errors* is a sequence of ``(file_path, message)`` tuples.
    """
    if not errors:
        return
    lines = [f"• {os.path.basename(fp)}: {msg}" for fp, msg in errors[:_MAX_LISTED]]
    if len(errors) > _MAX_LISTED:
        lines.append(f"… and {len(errors) - _MAX_LISTED} more (see log for details)")
    first_dir = os.path.dirname(errors[0][0])
    QMessageBox.warning(
        parent,
        title,
        f"Failed to load {len(errors)} file(s) from:\n{first_dir}\n\n" + "\n".join(lines),
    )

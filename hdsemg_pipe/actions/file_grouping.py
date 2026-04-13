"""Shared helpers for grouping decomposition files by recording session."""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Dict, List, Optional


def get_group_key(filename: str, regex: Optional[str] = None) -> str:
    """Return the group key for *filename*.

    Groups files from the same recording session by stripping grid-dimension
    and condition suffixes (e.g. ``_8mm_1305``, ``_10mm_4x8_2``) and keeping
    the session/subject identifier prefix (e.g. ``2_Pyr_1``).

    Falls back to stripping only a trailing ``_N`` number when no mm-pattern
    is found in the stem.

    Args:
        filename: Filename (with or without directory/extension).
        regex:    Optional custom regex.  If provided and the pattern matches
                  the stem, ``group(1)`` (or ``group(0)`` when there is no
                  capture group) is returned as the key.
    """
    stem = Path(filename).stem.rstrip(".")

    # Strip known processing suffixes before applying any logic
    for suffix in (
        "_covisi_filtered_cleaned",
        "_covisi_filtered",
        "_cleaned",
        "_edited",
    ):
        if stem.endswith(suffix):
            stem = stem[: -len(suffix)]
            break

    # Custom regex takes priority
    if regex:
        try:
            m = re.search(regex, stem)
            if m:
                return m.group(1) if m.lastindex else m.group(0)
        except re.error:
            pass  # fall through to default logic

    # Smart grouping: strip _Nmm_ and everything after it.
    # This collapses grid-dimension and condition suffixes such as
    #   2_Pyr_1_8mm_1305       → 2_Pyr_1
    #   2_Pyr_1_8mm_1305_2     → 2_Pyr_1
    #   2_Pyr1_10mm_4x8_2      → 2_Pyr1
    mm_stripped = re.sub(r"_\d+mm_.*$", "", stem)
    if mm_stripped and mm_stripped != stem:
        return mm_stripped

    # Fallback: strip a single trailing _N (grid/repetition number)
    return re.sub(r"_\d+$", "", stem)


def shorten_group_labels(group_keys: List[str]) -> Dict[str, str]:
    """Return a human-readable label for each group key.

    Strips the shared filename prefix (proband/date/time/protocol) so the
    label shows only the part that differs between groups.

    e.g. keys ``['2_Pyr_1', '2_Pyr_2']``
      → labels ``{'2_Pyr_1': 'Pyr 1', '2_Pyr_2': 'Pyr 2'}``
    """
    if not group_keys:
        return {}
    common = os.path.commonprefix(group_keys)
    if "_" in common:
        # Trim to the last underscore so we don't cut mid-word
        common = common[: common.rfind("_") + 1]
    result = {}
    for key in group_keys:
        unique = key[len(common):]
        label = unique.replace("_", " ").strip()
        # Fall back to the full key when the stripped label is too terse
        if len(label) < 2:
            label = key.replace("_", " ").strip()
        result[key] = label or key
    return result

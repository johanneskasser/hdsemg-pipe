"""Shared helpers for grouping decomposition files by recording session."""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Dict, List


def get_group_key(filename: str) -> str:
    """Strip trailing _N number from the stem to get the group key.

    e.g. ``Block1_Pyramid_3.mat`` → ``Block1_Pyramid``
    Files without a trailing number form their own singleton group.
    """
    stem = Path(filename).stem.rstrip(".")
    return re.sub(r"_\d+$", "", stem)


def shorten_group_labels(group_keys: List[str]) -> Dict[str, str]:
    """Return a human-readable label for each group key by stripping the
    shared filename prefix (proband/date/time/protocol).

    e.g. ``2_20260216_130218_FT_Block1_Pyramid`` → ``Block1 Pyramid``
    """
    if not group_keys:
        return {}
    common = os.path.commonprefix(group_keys)
    if "_" in common:
        common = common[: common.rfind("_") + 1]
    result = {}
    for key in group_keys:
        unique = key[len(common):]
        result[key] = unique.replace("_", " ").strip() or key
    return result

"""
Standalone reimplementation of SCD channel-selection JSON helpers.

Mirrors the logic of scd/utils/preprocessing.py:
  load_channel_selection_json(), get_grids_from_json(), get_good_channels_from_grid()

This module is intentionally self-contained (no imports from the SCD package)
so that the converter scripts can be used outside the repo.
"""

import json
from pathlib import Path


def load_channel_selection_json(mat_path: Path) -> dict | None:
    """
    Load the sidecar channel-selection JSON created by hdsemg-select.

    The JSON file must have the same stem as the .mat file:
        recording.mat -> recording.json
    """
    json_path = Path(mat_path).with_suffix(".json")
    if not json_path.exists():
        return None
    try:
        with open(json_path, encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"  Warning: could not load channel JSON {json_path.name}: {e}")
        return None


def get_grids_from_json(json_data: dict | None) -> list[dict]:
    """
    Extract grid list from channel-selection JSON.

    Returns a list of grid dicts, each with at least:
        grid_key, rows, columns, inter_electrode_distance_mm, channels, reference_signals
    """
    if json_data is None or "grids" not in json_data:
        return []
    grids = []
    for g in json_data["grids"]:
        grids.append({
            "grid_key": g.get("grid_key", "unknown"),
            "rows": g.get("rows", 0),
            "columns": g.get("columns", 0),
            "inter_electrode_distance_mm": g.get("inter_electrode_distance_mm", 8),
            "channels": g.get("channels", []),
            "reference_signals": g.get("reference_signals", []),
        })
    return grids


def get_good_channels_from_grid(grid_info: dict) -> tuple[list[int], list[int], list[int], float]:
    """
    Extract selected (good) channel indices from a grid dict.

    A channel is good when  ch['selected'] == True.

    Returns
    -------
    good_indices : list[int]
        Global channel indices that are selected (good).
    bad_relative_indices : list[int]
        Indices *relative to channel_range[0]* that are excluded.
    channel_range : list[int]
        [first_global_idx, last_global_idx + 1]
    ied : float
        Inter-electrode distance in mm.
    """
    channels = grid_info.get("channels", [])
    if not channels:
        return [], [], [0, 0], 8.0

    all_indices = [ch["channel_index"] for ch in channels]
    good_indices = [ch["channel_index"] for ch in channels if ch.get("selected", False)]

    min_idx = min(all_indices)
    max_idx = max(all_indices)
    channel_range = [min_idx, max_idx + 1]

    bad_relative = [
        ch["channel_index"] - min_idx
        for ch in channels
        if not ch.get("selected", False)
    ]

    ied = grid_info.get("inter_electrode_distance_mm", 8.0)
    return good_indices, bad_relative, channel_range, ied

"""Record which channels / which tool a decomposition result came from (#152).

The channel set stored in a result file otherwise depends on the external
decomposition tool. At ingest the pipeline writes what it knows itself into the
``EXTRAS`` field of the openhdemg JSON (the only free-form field that survives
openhdemg's own save/load round trips) under the key ``pipeline_provenance``.
"""
import gzip
import json
import os
from typing import List, Optional

from hdsemg_pipe._log.log_config import logger

PROVENANCE_KEY = "pipeline_provenance"


def detect_route(json_path: str, filename_field: str = "") -> str:
    """``scd-edition`` when a sibling .pkl exists, ``muedit`` when FILENAME points into a muedit folder."""
    if os.path.isfile(os.path.splitext(json_path)[0] + ".pkl"):
        return "scd-edition"
    if "muedit" in str(filename_field).lower():
        return "muedit"
    return "unknown"


def read_channel_set(chan_mat_path: str) -> Optional[List[dict]]:
    """Per-grid selected channel indices from the hdsemg-select sidecar of ``chan_mat_path``."""
    sidecar = os.path.splitext(chan_mat_path)[0] + ".json"
    try:
        with open(sidecar, encoding="utf-8") as fh:
            grids = json.load(fh).get("grids", [])
    except (OSError, ValueError):
        return None
    return [
        {
            "grid_key": g.get("grid_key"),
            "n_channels_total": len(g.get("channels", [])),
            "selected_channel_indices": [
                c["channel_index"] for c in g.get("channels", []) if c.get("selected")
            ],
        }
        for g in grids
    ]


def annotate_result_json(json_path: str, chan_mat_path: Optional[str] = None) -> bool:
    """Add route + channel set to ``json_path`` in place. Returns False if the file was left untouched."""
    try:
        with gzip.open(json_path, "rt", encoding="utf-8") as fh:
            raw = json.load(fh)
        extras = json.loads(raw["EXTRAS"])
        cell = json.loads(extras["data"][0][0])
        if not isinstance(cell, dict):
            raise ValueError("first EXTRAS cell is not a JSON object")
    except (OSError, ValueError, KeyError, IndexError, TypeError) as exc:
        # ponytail: files without a JSON-object EXTRAS cell are skipped, add a new carrier if they show up
        logger.warning("Provenance not written for %s: %s", os.path.basename(json_path), exc)
        return False

    cell[PROVENANCE_KEY] = {
        "decomposition_route": detect_route(json_path, raw.get("FILENAME", "")),
        "channel_selection_file": os.path.basename(chan_mat_path) if chan_mat_path else None,
        "channel_set": read_channel_set(chan_mat_path) if chan_mat_path else None,
    }
    extras["data"][0][0] = json.dumps(cell)
    raw["EXTRAS"] = json.dumps(extras)

    tmp = json_path + ".tmp"
    with gzip.open(tmp, "wt", encoding="utf-8", compresslevel=4) as fh:
        json.dump(raw, fh)
    os.replace(tmp, json_path)
    return True

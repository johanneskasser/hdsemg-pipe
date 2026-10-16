"""Read-only summary of a finished (or partial) hdsemg-select channel-selection run.

hdsemg-select writes a sidecar ``<stem>.json`` next to each saved ``<stem>.mat``;
discarded files are moved to ``<channelselection>/discarded/``. This module turns
those sidecars into plain dataclasses so the wizard can show what was kept/dropped
without re-running anything. No Qt — safe to call from a worker thread.
"""
import json
import os
from dataclasses import dataclass, field
from typing import List, Optional

from hdsemg_pipe._log.log_config import logger

REVIEW_JSON = "channel_selection_review.json"
KEPT, DISCARDED, PENDING = "kept", "discarded", "pending"


@dataclass
class GridSummary:
    grid_key: str
    rows: int = 0
    columns: int = 0
    ied_mm: Optional[float] = None
    n_selected: int = 0
    n_total: int = 0
    n_refs_selected: int = 0
    n_refs_total: int = 0
    n_labeled: int = 0
    excluded_channels: List[int] = field(default_factory=list)  # 1-based channel numbers

    @property
    def n_dropped(self) -> int:
        return self.n_total - self.n_selected


@dataclass
class FileSummary:
    name: str                       # basename of the .mat file
    status: str                     # KEPT | DISCARDED | PENDING
    path: Optional[str] = None      # existing .mat (channelselection or discarded/), None if pending
    grids: List[GridSummary] = field(default_factory=list)
    has_sidecar: bool = False
    reason: str = ""
    notes: str = ""


def _summarize_grid(g: dict) -> GridSummary:
    channels = g.get("channels", []) or []
    refs = g.get("reference_signals", []) or []
    excluded = [c.get("channel_number", c.get("channel_index", -1) + 1)
                for c in channels if not c.get("selected", False)]
    return GridSummary(
        grid_key=str(g.get("grid_key", "unknown")),
        rows=g.get("rows") or 0,
        columns=g.get("columns") or 0,
        ied_mm=g.get("inter_electrode_distance_mm"),
        n_selected=sum(1 for c in channels if c.get("selected", False)),
        n_total=len(channels),
        n_refs_selected=sum(1 for r in refs if r.get("selected", False)),
        n_refs_total=len(refs),
        n_labeled=sum(1 for c in channels if c.get("labels")),
        excluded_channels=excluded,
    )


def _read_sidecar(mat_path: str) -> Optional[List[GridSummary]]:
    json_path = os.path.splitext(mat_path)[0] + ".json"
    if not os.path.isfile(json_path):
        return None
    try:
        with open(json_path, encoding="utf-8") as fh:
            data = json.load(fh)
        return [_summarize_grid(g) for g in data.get("grids", [])]
    except Exception as exc:  # corrupt/partial sidecar must not break the summary
        logger.warning("Could not read channel-selection sidecar %s: %s", json_path, exc)
        return None


def _read_review_entries(channel_sel_dir: str) -> dict:
    path = os.path.join(channel_sel_dir, REVIEW_JSON)
    try:
        with open(path, encoding="utf-8") as fh:
            return {e["file"]: e for e in json.load(fh).get("files", []) if "file" in e}
    except Exception:
        return {}


def collect_channel_selection_summary(cropped_files: List[str], channel_sel_dir: str) -> List[FileSummary]:
    """One FileSummary per cropped file, in the given order."""
    discarded_dir = os.path.join(channel_sel_dir, "discarded")
    reviews = _read_review_entries(channel_sel_dir)
    out = []
    for cropped in cropped_files:
        name = os.path.basename(cropped)
        kept_path = os.path.join(channel_sel_dir, name)
        disc_path = os.path.join(discarded_dir, name)
        review = reviews.get(name, {})
        if os.path.isfile(kept_path):
            status, path = KEPT, kept_path
        elif os.path.isfile(disc_path):
            status, path = DISCARDED, disc_path
        else:
            status, path = PENDING, None
        grids = _read_sidecar(path) if path else None
        if grids is None and status == DISCARDED:
            # Only the .mat is moved to discarded/; the sidecar JSON may stay behind.
            grids = _read_sidecar(kept_path)
        out.append(FileSummary(
            name=name, status=status, path=path,
            grids=grids or [], has_sidecar=grids is not None,
            reason=review.get("reason", "") or "", notes=review.get("notes", "") or "",
        ))
    return out

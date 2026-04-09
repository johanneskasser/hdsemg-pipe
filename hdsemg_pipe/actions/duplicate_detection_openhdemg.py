"""
Duplicate Motor Unit Detection — openhdemg MUAP-shape-based implementation.

Replaces the custom spike-train-overlap algorithm in ``duplicate_detection.py``
with openhdemg's ``tracking()`` function, which computes STA-based MUAPs and
a normalised 2-D cross-correlation (XCC) to identify duplicate MUs across files.

Typical use case: two HD-sEMG grids placed on the same muscle may decompose the
same underlying motor unit independently.  This module detects such cross-grid
duplicates and keeps the more reliable copy (per ``DecompositionFile.compute_reliability``).
"""

import itertools
import re
from typing import Optional
from unittest.mock import patch

import pandas as pd

from hdsemg_pipe._log.log_config import logger

try:
    from openhdemg.library.muap import tracking as _openhdemg_tracking
    _OPENHDEMG_AVAILABLE = True
except ImportError:
    _openhdemg_tracking = None  # type: ignore[assignment]
    _OPENHDEMG_AVAILABLE = False
    logger.warning("openhdemg not available — MUAP-based duplicate detection will not work")


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

# Matrixcodes natively supported by openhdemg's channel-sorting logic.
_OPENHDEMG_KNOWN_CODES = frozenset({"GR04MM1305", "GR08MM1305", "GR10MM0808"})


def _extract_grid_params_from_emgfile(emgfile: dict) -> tuple:
    """Return ``(matrixcode, n_rows, n_cols)`` from an emgfile's EXTRAS field.

    OT Biolab encodes grids as ``HD{ied}MM{cols:02d}{rows:02d}`` (cols-first).
    openhdemg expects ``GR{ied}MM{rows:02d}{cols:02d}`` (rows-first).
    When the derived code is not in openhdemg's known list, returns
    ``("None", rows, cols)`` so ``tracking()`` can use explicit dimensions.
    """
    try:
        extras = emgfile.get("EXTRAS")
        if hasattr(extras, "iloc"):
            extras_str = str(extras.iloc[0])
        elif hasattr(extras, "loc"):
            extras_str = str(extras.loc[0.0])
        else:
            extras_str = str(extras) if extras is not None else ""

        m = re.search(r'HD(\d{2})MM(\d{2})(\d{2})', extras_str)
        if not m:
            logger.debug("No HD grid code found in EXTRAS; using default GR08MM1305")
            return "GR08MM1305", None, None

        ied = m.group(1)
        cols = int(m.group(2))   # OT Biolab: cols first
        rows = int(m.group(3))   # OT Biolab: rows second

        gr_code = f"GR{ied}MM{rows:02d}{cols:02d}"

        if gr_code in _OPENHDEMG_KNOWN_CODES:
            logger.debug("Grid code from EXTRAS: %s", gr_code)
            return gr_code, None, None

        logger.debug(
            "Grid code %s not in openhdemg known list; using matrixcode='None' "
            "with n_rows=%d, n_cols=%d",
            gr_code, rows, cols,
        )
        return "None", rows, cols

    except Exception as exc:
        logger.debug("Could not parse grid params from EXTRAS: %s", exc)
        return "GR08MM1305", None, None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def detect_duplicates_between_files(
    emgfile1: dict,
    emgfile2: dict,
    *,
    threshold: float = 0.9,
    timewindow: int = 50,
    firings: str = "all",
    derivation: str = "sd",
    matrixcode: Optional[str] = None,
    orientation: int = 180,
    n_rows: Optional[int] = None,
    n_cols: Optional[int] = None,
    show_gui: bool = False,
) -> pd.DataFrame:
    """Run openhdemg MU tracking between two emgfiles.

    Args:
        emgfile1: First openhdemg emgfile dict (loaded via ``emg.emg_from_json``).
        emgfile2: Second openhdemg emgfile dict.
        threshold: Minimum XCC to consider two MUs duplicates (default 0.9).
        timewindow: STA window in milliseconds (default 50).
        firings: Which firings to use for STA; ``"all"`` or ``[start, stop]``.
        derivation: Signal derivation — ``"mono"``, ``"sd"``, or ``"dd"``.
        matrixcode: OT Biolab grid code for channel sorting. When ``None``
            (default), auto-detected from *emgfile1*'s EXTRAS field.
            Pass ``"None"`` (string) to disable channel sorting entirely; then
            *n_rows* and *n_cols* are required.
        orientation: Grid orientation in degrees (default 180).
        n_rows: Grid rows override (required when *matrixcode* is ``"None"``).
        n_cols: Grid columns override (required when *matrixcode* is ``"None"``).

    Returns:
        DataFrame with columns ``MU_file1``, ``MU_file2``, ``XCC``.
        Empty DataFrame if no duplicates found or tracking fails.

    Raises:
        RuntimeError: If openhdemg is not installed.
    """
    if not _OPENHDEMG_AVAILABLE or _openhdemg_tracking is None:
        raise RuntimeError(
            "openhdemg is required for MUAP-based duplicate detection. "
            "Install it with: pip install openhdemg"
        )

    # Auto-detect grid parameters from emgfile1's EXTRAS when not provided.
    if matrixcode is None:
        matrixcode, n_rows, n_cols = _extract_grid_params_from_emgfile(emgfile1)
        logger.debug(
            "Auto-detected grid params: matrixcode=%s, n_rows=%s, n_cols=%s",
            matrixcode, n_rows, n_cols,
        )

    try:
        # openhdemg's tracking() unconditionally calls plt.show() at line ~1196
        # even when show=False — a bug that crashes macOS from a non-main thread.
        # Patch it to a no-op for this call.
        import matplotlib.pyplot as _plt
        with patch.object(_plt, "show"):
            result = _openhdemg_tracking(
                emgfile1=emgfile1,
                emgfile2=emgfile2,
                firings=firings,
                derivation=derivation,
                timewindow=timewindow,
                threshold=threshold,
                matrixcode=matrixcode,
                orientation=orientation,
                n_rows=n_rows,
                n_cols=n_cols,
                exclude_belowthreshold=True,
                filter=True,
                multiprocessing=True,
                show=False,
                gui=show_gui,
            )
        if result is None:
            return pd.DataFrame(columns=["MU_file1", "MU_file2", "XCC"])
        return result
    except Exception as exc:
        logger.error("openhdemg tracking() failed: %s", exc)
        raise


def detect_duplicates_in_group(
    emgfiles: list,
    *,
    reliability_per_file: list,
    threshold: float = 0.9,
    timewindow: int = 50,
    firings: str = "all",
    derivation: str = "sd",
    orientation: int = 180,
    show_gui: bool = False,
) -> dict:
    """Detect duplicate MUs in a group of emgfiles using openhdemg tracking.

    Calls :func:`detect_duplicates_between_files` for every pair, builds
    connected components via union-find, then selects the survivor in each
    component using reliability scores.

    Args:
        emgfiles: List of openhdemg emgfile dicts (same order as reliability_per_file).
        reliability_per_file: List of ``pd.DataFrame`` from
            ``DecompositionFile.compute_reliability()``, one per file.
            Pass an empty list or ``[None, ...]`` to fall back to n_spikes tiebreaker.
        threshold: XCC threshold for duplicate detection.
        timewindow: STA window in ms.
        firings: Firings to use for STA.
        derivation: Signal derivation.
        orientation: Grid orientation in degrees (default 180). Grid code and
            dimensions are auto-detected per file from their EXTRAS field.

    Returns:
        Dict with the same structure as the legacy ``detect_duplicates_in_group``:

        .. code-block:: python

            {
                "duplicate_groups": [
                    {
                        "mus": [(file_idx, mu_idx), ...],
                        "survivor": (file_idx, mu_idx),
                        "xcc_pairs": {(fi1, mi1, fi2, mi2): xcc, ...},
                        "reliability_per_mu": {(fi, mi): {"is_reliable": bool, "sil": float, ...}},
                        "reason": "Best reliability score",
                    },
                    ...
                ],
                "all_mus": [(file_idx, mu_idx), ...],
                "unique_mus": [(file_idx, mu_idx), ...],
            }
    """
    # Build flat MU list: (file_idx, mu_idx)
    all_mus: list = []
    for file_idx, ef in enumerate(emgfiles):
        n_mus = ef.get("NUMBER_OF_MUS", 0)
        for mu_idx in range(n_mus):
            all_mus.append((file_idx, mu_idx))

    n_total = len(all_mus)
    mu_to_gidx = {mu: i for i, mu in enumerate(all_mus)}

    if n_total == 0:
        logger.warning("detect_duplicates_in_group: no MUs found in group")
        return {"duplicate_groups": [], "all_mus": [], "unique_mus": []}

    logger.info(
        "openhdemg tracking: %d MUs across %d file(s), XCC threshold=%.2f",
        n_total, len(emgfiles), threshold,
    )

    # Pairwise tracking across all file pairs
    duplicate_pairs: list = []          # (global_idx_i, global_idx_j)
    xcc_map: dict = {}                  # (fi1, mi1, fi2, mi2) -> xcc

    for i, j in itertools.combinations(range(len(emgfiles)), 2):
        ef1 = emgfiles[i]
        ef2 = emgfiles[j]
        if ef1.get("NUMBER_OF_MUS", 0) == 0 or ef2.get("NUMBER_OF_MUS", 0) == 0:
            logger.debug("Skipping pair (%d, %d): one file has 0 MUs", i, j)
            continue

        try:
            df = detect_duplicates_between_files(
                ef1, ef2,
                threshold=threshold,
                timewindow=timewindow,
                firings=firings,
                derivation=derivation,
                orientation=orientation,
                show_gui=show_gui,
            )
        except Exception as exc:
            logger.error("tracking() failed for file pair (%d, %d): %s", i, j, exc)
            continue

        if df is None or df.empty:
            logger.debug("No duplicates found between file %d and file %d", i, j)
            continue

        for _, row in df.iterrows():
            mi1 = int(row["MU_file1"])
            mi2 = int(row["MU_file2"])
            xcc = float(row["XCC"])
            mu1 = (i, mi1)
            mu2 = (j, mi2)
            gi = mu_to_gidx[mu1]
            gj = mu_to_gidx[mu2]
            duplicate_pairs.append((gi, gj))
            xcc_map[(i, mi1, j, mi2)] = xcc
            logger.debug("  Duplicate detected: %s <-> %s (XCC=%.3f)", mu1, mu2, xcc)

    # Connected components via union-find
    comp_sets = _union_find_groups(duplicate_pairs, n_total)

    # Build duplicate groups
    duplicate_groups = []
    for comp in comp_sets:
        group_mus = [all_mus[idx] for idx in comp]
        rel_scores = _extract_reliability_per_mu(group_mus, reliability_per_file)
        survivor = select_survivor_by_reliability(group_mus, reliability_per_file)
        duplicate_groups.append({
            "mus": group_mus,
            "survivor": survivor,
            "xcc_pairs": xcc_map,
            "reliability_per_mu": rel_scores,
            "reason": "Best reliability score",
        })
        logger.info(
            "  Duplicate group %d MUs=%s  survivor=%s",
            len(group_mus), group_mus, survivor,
        )

    mus_in_dups: set = {mu for g in duplicate_groups for mu in g["mus"]}
    unique_mus = [mu for mu in all_mus if mu not in mus_in_dups]

    logger.info(
        "Tracking complete: %d duplicate group(s), %d unique MU(s)",
        len(duplicate_groups), len(unique_mus),
    )

    return {
        "duplicate_groups": duplicate_groups,
        "all_mus": all_mus,
        "unique_mus": unique_mus,
    }


def select_survivor_by_reliability(
    group: list,
    reliability_per_file: list,
) -> tuple:
    """Choose which MU to keep from a duplicate group based on reliability.

    Priority (descending):
      1. ``is_reliable=True`` over ``False``
      2. Higher SIL score
      3. More spikes (``n_spikes``)
      4. Lower file index (deterministic tiebreaker)

    Args:
        group: List of ``(file_idx, mu_idx)`` tuples.
        reliability_per_file: Reliability DataFrames, indexed by file position.

    Returns:
        ``(file_idx, mu_idx)`` of the chosen survivor.
    """
    def _score(file_mu: tuple) -> tuple:
        file_idx, mu_idx = file_mu
        if not reliability_per_file or file_idx >= len(reliability_per_file):
            return (0, 0.0, 0, -file_idx)
        df = reliability_per_file[file_idx]
        if df is None or (hasattr(df, "empty") and df.empty):
            return (0, 0.0, 0, -file_idx)
        row = df[df["mu_index"] == mu_idx]
        if row.empty:
            return (0, 0.0, 0, -file_idx)
        r = row.iloc[0]
        is_rel = int(bool(r.get("is_reliable", False)))
        sil = float(r.get("sil", 0.0))
        n_spikes = int(r.get("n_spikes", 0))
        return (is_rel, sil, n_spikes, -file_idx)

    return max(group, key=_score)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _union_find_groups(pairs: list, n: int) -> list:
    """Return connected components (size > 1) for *n* nodes and *pairs* edges."""
    parent = list(range(n))

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]  # path compression
            x = parent[x]
        return x

    def union(x: int, y: int) -> None:
        rx, ry = find(x), find(y)
        if rx != ry:
            parent[rx] = ry

    for i, j in pairs:
        union(i, j)

    groups: dict = {}
    for idx in range(n):
        root = find(idx)
        groups.setdefault(root, set()).add(idx)

    return [g for g in groups.values() if len(g) > 1]


def _extract_reliability_per_mu(
    group_mus: list,
    reliability_per_file: list,
) -> dict:
    """Build {(file_idx, mu_idx): row_dict} for display in the UI."""
    result = {}
    for file_idx, mu_idx in group_mus:
        if not reliability_per_file or file_idx >= len(reliability_per_file):
            result[(file_idx, mu_idx)] = {}
            continue
        df = reliability_per_file[file_idx]
        if df is None or (hasattr(df, "empty") and df.empty):
            result[(file_idx, mu_idx)] = {}
            continue
        row = df[df["mu_index"] == mu_idx]
        if row.empty:
            result[(file_idx, mu_idx)] = {}
        else:
            result[(file_idx, mu_idx)] = row.iloc[0].to_dict()
    return result

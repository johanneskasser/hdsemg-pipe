"""Cross-grid duplicate motor units with a constant discharge-time offset (#153).

The same motor unit decomposed on two grids shows up with its discharge times
shifted by a constant offset per grid (typically 2-6 ms, up to ~20 ms), so a
zero-lag comparison misses most of them. Here every cross-file MU pair is
compared over a lag range, and candidates are confirmed by MUAP shape: the
spike-triggered average (STA) of unit A's shifted discharges on grid B must
reproduce unit B's own MUAP.

Lag convention: ``lag`` is added to A's discharge samples to match B's.
"""
import itertools
from typing import List, Optional, Tuple

import numpy as np


def _spikes(emgfile: dict, mu_idx: int) -> np.ndarray:
    return np.sort(np.asarray(emgfile["MUPULSES"][mu_idx], dtype=int))


def best_lag(a: np.ndarray, b: np.ndarray, fsamp: float,
             max_lag_ms: float = 25.0, tol_ms: float = 0.5) -> Tuple[int, float, int]:
    """Best constant offset of ``a`` onto ``b``.

    Returns ``(lag_samples, coincidence, n_matched)``; coincidence is
    ``n_matched / min(len(a), len(b))`` (clipped to 1) after shifting by the lag,
    with a match being a ``b`` discharge within ``tol_ms`` of a shifted ``a`` discharge.
    """
    if len(a) == 0 or len(b) == 0:
        return 0, 0.0, 0
    max_lag = int(round(max_lag_ms * fsamp / 1000.0))
    tol = int(round(tol_ms * fsamp / 1000.0))
    size = int(max(a.max(), b.max())) + max_lag + tol + 2
    b_dilated = np.zeros(size, dtype=bool)
    for d in range(-tol, tol + 1):
        b_dilated[np.clip(b + d, 0, size - 1)] = True

    best = (0, -1)  # (lag, n_matched)
    for lag in sorted(range(-max_lag, max_lag + 1), key=abs):  # ties -> smallest |lag|
        idx = a + lag
        n = int(b_dilated[idx[(idx >= 0) & (idx < size)]].sum())
        if n > best[1]:
            best = (lag, n)
    lag, n_matched = best
    return lag, min(1.0, n_matched / min(len(a), len(b))), n_matched


def muap_similarity(raw: np.ndarray, spikes_a_shifted: np.ndarray, spikes_b: np.ndarray,
                    fsamp: float, win_ms: float = 15.0, max_spikes: int = 300) -> Optional[float]:
    """Pearson r between the STA of A's shifted discharges and B's own STA, both on B's channels."""
    half = int(round(win_ms * fsamp / 1000.0))

    def sta(spikes):
        spikes = spikes[(spikes >= half) & (spikes < raw.shape[0] - half)][:max_spikes]
        if len(spikes) < 3:
            return None
        seg = np.stack([raw[s - half:s + half + 1] for s in spikes]).mean(axis=0)
        return (seg - seg.mean(axis=0)).ravel()

    sta_a, sta_b = sta(spikes_a_shifted), sta(spikes_b)
    if sta_a is None or sta_b is None or not sta_a.any() or not sta_b.any():
        return None
    return float(np.corrcoef(sta_a, sta_b)[0, 1])


def find_cross_grid_duplicates(emgfiles: List[dict], *, max_lag_ms: float = 25.0, tol_ms: float = 0.5,
                               min_coincidence: float = 0.3, muap_r_min: float = 0.8) -> List[dict]:
    """All cross-file MU pairs with at least ``min_coincidence`` after the best lag.

    Each entry: ``file_a, mu_a, file_b, mu_b, lag_ms, coincidence, n_matched, muap_r, decision``.
    ``decision`` is ``"duplicate"`` when the MUAP check reaches ``muap_r_min`` and
    ``"ambiguous"`` otherwise (including when no raw signal is available).
    """
    pairs = []
    for i, j in itertools.combinations(range(len(emgfiles)), 2):
        ef_a, ef_b = emgfiles[i], emgfiles[j]
        fs = float(ef_b.get("FSAMP", ef_a.get("FSAMP", 2048.0)))
        raw_b = None
        for mu_a in range(ef_a.get("NUMBER_OF_MUS", 0)):
            sp_a = _spikes(ef_a, mu_a)
            for mu_b in range(ef_b.get("NUMBER_OF_MUS", 0)):
                sp_b = _spikes(ef_b, mu_b)
                lag, coincidence, n_matched = best_lag(sp_a, sp_b, fs, max_lag_ms, tol_ms)
                if coincidence < min_coincidence:
                    continue
                if raw_b is None and "RAW_SIGNAL" in ef_b:
                    raw_b = np.asarray(ef_b["RAW_SIGNAL"], dtype=float)
                r = muap_similarity(raw_b, sp_a + lag, sp_b, fs) if raw_b is not None else None
                pairs.append({
                    "file_a": i, "mu_a": mu_a, "file_b": j, "mu_b": mu_b,
                    "lag_ms": round(lag * 1000.0 / fs, 3),
                    "coincidence": round(coincidence, 4), "n_matched": n_matched,
                    "muap_r": None if r is None else round(r, 4),
                    "decision": "duplicate" if r is not None and r >= muap_r_min else "ambiguous",
                })
    return pairs

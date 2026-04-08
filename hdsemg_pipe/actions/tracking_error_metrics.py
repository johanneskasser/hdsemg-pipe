"""
Tracking Error Metrics

Computes quality scores (0–100, higher = better) from required vs. performed
path signals. Each metric normalises its raw error into the same 0–100 scale
so the existing colour-mapping logic in FileQualitySelectionWizardWidget works
unchanged when the user switches metric.

Default tier thresholds (score boundaries for Excellent / Good / OK / Troubled)
are stored in ``DEFAULT_THRESHOLDS`` keyed by metric name.  These are also the
factory-reset values used by ``TrackingErrorThresholdsDialog``.
"""

from __future__ import annotations

from typing import Dict, Optional

import numpy as np


# ---------------------------------------------------------------------------
# Metric names (used as keys everywhere)
# ---------------------------------------------------------------------------

METRIC_NRMSE = "NRMSE"
METRIC_RMSE = "RMSE"
METRIC_MSE = "MSE"
METRIC_MAE = "MAE"
METRIC_PEARSON_R = "Pearson r"

METRIC_NAMES = [METRIC_NRMSE, METRIC_RMSE, METRIC_MSE, METRIC_MAE, METRIC_PEARSON_R]

# Human-readable labels shown in the combo box
METRIC_LABELS: Dict[str, str] = {
    METRIC_NRMSE: "NRMSE",
    METRIC_RMSE: "RMSE",
    METRIC_MSE: "MSE",
    METRIC_MAE: "MAE",
    METRIC_PEARSON_R: "Pearson r",
}

# ---------------------------------------------------------------------------
# Default tier thresholds  (score >= value → tier)
# Order: excellent, good, ok, troubled  (anything below troubled → bad)
# ---------------------------------------------------------------------------

DEFAULT_THRESHOLDS: Dict[str, Dict[str, float]] = {
    METRIC_NRMSE: {
        "excellent": 90.0,
        "good": 80.0,
        "ok": 70.0,
        "troubled": 60.0,
    },
    METRIC_RMSE: {
        "excellent": 90.0,
        "good": 80.0,
        "ok": 70.0,
        "troubled": 60.0,
    },
    METRIC_MSE: {
        "excellent": 90.0,
        "good": 80.0,
        "ok": 70.0,
        "troubled": 60.0,
    },
    METRIC_MAE: {
        "excellent": 90.0,
        "good": 80.0,
        "ok": 70.0,
        "troubled": 60.0,
    },
    METRIC_PEARSON_R: {
        "excellent": 90.0,
        "good": 80.0,
        "ok": 70.0,
        "troubled": 60.0,
    },
}

# Tier display labels and order (descending)
TIER_ORDER = ["excellent", "good", "ok", "troubled"]
TIER_DISPLAY: Dict[str, str] = {
    "excellent": "Excellent",
    "good": "Good",
    "ok": "OK",
    "troubled": "Troubled",
}


# ---------------------------------------------------------------------------
# Individual metric implementations (return 0–100 quality score)
# ---------------------------------------------------------------------------

def _nrmse_score(required: np.ndarray, performed: np.ndarray) -> Optional[float]:
    """score = max(0, (1 − RMSE / range(required)) × 100)."""
    req_range = required.max() - required.min()
    if req_range < 1e-10:
        return None
    rmse = float(np.sqrt(np.mean((required - performed) ** 2)))
    return max(0.0, (1.0 - rmse / req_range) * 100.0)


def _rmse_score(required: np.ndarray, performed: np.ndarray) -> Optional[float]:
    """score = max(0, (1 − RMSE / std(required)) × 100).

    Normalises by std instead of range so it is robust to extreme spikes.
    """
    std = float(np.std(required))
    if std < 1e-10:
        return None
    rmse = float(np.sqrt(np.mean((required - performed) ** 2)))
    return max(0.0, (1.0 - rmse / std) * 100.0)


def _mse_score(required: np.ndarray, performed: np.ndarray) -> Optional[float]:
    """score = max(0, (1 − MSE / var(required)) × 100).

    Equivalent to 100 × (1 − normalised MSE).
    """
    var = float(np.var(required))
    if var < 1e-10:
        return None
    mse = float(np.mean((required - performed) ** 2))
    return max(0.0, (1.0 - mse / var) * 100.0)


def _mae_score(required: np.ndarray, performed: np.ndarray) -> Optional[float]:
    """score = max(0, (1 − MAE / (0.5 × range(required))) × 100).

    Normalises MAE by half the signal range to give a comparable scale.
    """
    req_range = required.max() - required.min()
    if req_range < 1e-10:
        return None
    mae = float(np.mean(np.abs(required - performed)))
    return max(0.0, (1.0 - mae / (req_range * 0.5)) * 100.0)


def _pearson_r_score(required: np.ndarray, performed: np.ndarray) -> Optional[float]:
    """score = max(0, r) × 100  where r is the Pearson correlation coefficient."""
    req_std = float(np.std(required))
    perf_std = float(np.std(performed))
    if req_std < 1e-10 or perf_std < 1e-10:
        return None
    r = float(np.corrcoef(required, performed)[0, 1])
    if np.isnan(r):
        return None
    return max(0.0, r) * 100.0


# ---------------------------------------------------------------------------
# Public dispatcher
# ---------------------------------------------------------------------------

_DISPATCH = {
    METRIC_NRMSE: _nrmse_score,
    METRIC_RMSE: _rmse_score,
    METRIC_MSE: _mse_score,
    METRIC_MAE: _mae_score,
    METRIC_PEARSON_R: _pearson_r_score,
}


def compute_metric(
    metric_name: str,
    required: np.ndarray,
    performed: np.ndarray,
) -> Optional[float]:
    """Return a 0–100 quality score for the given metric.

    Parameters
    ----------
    metric_name:
        One of the ``METRIC_*`` constants (e.g. ``METRIC_NRMSE``).
    required:
        1-D array of the required / target path signal.
    performed:
        1-D array of the performed path signal.  Trimmed to ``len(required)``
        if longer; padded with the last value if shorter.

    Returns
    -------
    float or None
        Score in [0, 100] where 100 is a perfect match, or ``None`` if the
        score cannot be computed (e.g. constant required signal).
    """
    fn = _DISPATCH.get(metric_name)
    if fn is None:
        raise ValueError(
            f"Unknown metric '{metric_name}'. "
            f"Valid choices: {list(_DISPATCH.keys())}"
        )

    min_len = min(len(required), len(performed))
    req = np.asarray(required[:min_len], dtype=float)
    perf = np.asarray(performed[:min_len], dtype=float)

    return fn(req, perf)

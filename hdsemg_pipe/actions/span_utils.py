"""Helpers for validating coordinates coming from matplotlib span/click selection."""


def clamp_to_range(x, lo, hi):
    """Clamp ``x`` into ``[lo, hi]``; ``None`` (click outside the axes) stays ``None``."""
    if x is None:
        return None
    return min(max(x, lo), hi)

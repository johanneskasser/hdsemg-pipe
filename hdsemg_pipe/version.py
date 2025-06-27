# hdsemg_pipe/version.py
from __future__ import annotations

import re
import subprocess
from hdsemg_pipe._log.log_config import logger


def _raw_tag() -> str | None:
    """Return the newest Git tag (without the leading 'v') or None."""
    try:
        tag = subprocess.check_output(
            ["git", "describe", "--tags", "--abbrev=0"],
            stderr=subprocess.DEVNULL,
        ).decode().strip()
        return tag[1:] if tag.startswith("v") else tag
    except Exception:  # noqa: BLE001
        return None


# ──────────────────────────── PEP-440 fixer ────────────────────────────
_dash_pat = re.compile(
    r"""
    ^
    (?P<core>[\d.]+)                # 1.2.3
    -                               # dash that breaks PEP 440
    (?P<label>(?:alpha|beta|rc)?)   # pre-release label
    (?P<num>\d*)$                   # optional number
    """,
    re.IGNORECASE | re.VERBOSE,
)


def _pep440(tag: str) -> str:
    """
    Convert `1.2.3-rc1` → `1.2.3rc1`, `1.2.3-beta2` → `1.2.3b2`, etc.
    If the dash doesn’t match a known pattern we just strip everything
    after the first dash (so `1.2.3-whatever` → `1.2.3`).
    """
    m = _dash_pat.match(tag)
    if m:
        label = m["label"].lower()
        label = {"alpha": "a", "beta": "b"}.get(label, label)  # alpha→a, beta→b
        return f"{m['core']}{label}{m['num']}"
    return tag.split("-", 1)[0]  # generic fallback


_raw = _raw_tag()
__version__ = _pep440(_raw) if _raw else "0.0.0"

logger.info("hdsemg-pipe version: %s", __version__)

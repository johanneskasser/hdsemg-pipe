"""
Background update checker for scd-edition, openhdemg, and MUedit.

Runs in a QThread on startup and emits signals when newer versions are available.
Results are shown as toast notifications or dialogs (for scd-edition upgrade choice).

Checks performed:
  scd-edition  — latest commit on main branch vs. installed commit (from direct_url.json)
  openhdemg    — latest version on PyPI vs. installed version
  MUedit       — latest commit on devHP branch vs. last-seen commit (stored in cache)
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from dataclasses import dataclass
from importlib.metadata import version as pkg_version
from pathlib import Path
from typing import Optional

import requests
from PyQt5.QtCore import QThread, pyqtSignal
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QApplication,
)

from hdsemg_pipe._log.log_config import logger
from hdsemg_pipe.ui_elements.theme import Colors, Styles, Fonts, Spacing, BorderRadius

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

_TIMEOUT = 6  # seconds per HTTP request

_SCD_EDITION_OWNER  = "AgneGris"
_SCD_EDITION_REPO   = "scd-edition"
_SCD_EDITION_BRANCH = "main"
_SCD_EDITION_GIT_URL = f"git+https://github.com/{_SCD_EDITION_OWNER}/{_SCD_EDITION_REPO}.git"

_MUEDIT_OWNER  = "haripen"
_MUEDIT_REPO   = "MUedit"
_MUEDIT_BRANCH = "devHP"
_MUEDIT_URL    = f"https://github.com/{_MUEDIT_OWNER}/{_MUEDIT_REPO}/tree/{_MUEDIT_BRANCH}"

_OPENHDEMG_PACKAGE = "openhdemg"
_OPENHDEMG_PYPI_URL = f"https://pypi.org/pypi/{_OPENHDEMG_PACKAGE}/json"

_CACHE_FILE = Path.home() / ".hdsemg_pipe" / "update_cache.json"


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class ReleaseInfo:
    """Describes one available update."""
    package: str
    installed: str
    latest: str
    url: str
    latest_sha: Optional[str] = None          # full SHA for cache storage
    has_stable_release: bool = False          # scd-edition: whether GH releases exist
    latest_stable: Optional[str] = None      # scd-edition: latest release tag, if any
    latest_stable_url: Optional[str] = None


# ---------------------------------------------------------------------------
# Cache helpers (for MUedit / commit-based packages)
# ---------------------------------------------------------------------------

def _load_cache() -> dict:
    try:
        if _CACHE_FILE.exists():
            return json.loads(_CACHE_FILE.read_text())
    except Exception:
        pass
    return {}


def _save_cache(data: dict) -> None:
    try:
        _CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        _CACHE_FILE.write_text(json.dumps(data, indent=2))
    except Exception as exc:
        logger.warning(f"[update_checker] Could not write cache: {exc}")


# ---------------------------------------------------------------------------
# Installed-version helpers
# ---------------------------------------------------------------------------

def _installed_scd_commit() -> Optional[str]:
    """Read the installed git commit of scd-edition from its dist-info."""
    try:
        import importlib.metadata as meta
        dist = meta.distribution("scd-edition")
        direct_url_text = dist.read_text("direct_url.json")
        if direct_url_text:
            info = json.loads(direct_url_text)
            return info.get("vcs_info", {}).get("commit_id")
    except Exception:
        pass
    return None


def _installed_version(package: str) -> Optional[str]:
    try:
        return pkg_version(package)
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Remote-version helpers
# ---------------------------------------------------------------------------

def _github_latest_commit(owner: str, repo: str, branch: str) -> Optional[dict]:
    """Returns {'sha': ..., 'message': ..., 'date': ...} or None."""
    url = f"https://api.github.com/repos/{owner}/{repo}/commits/{branch}"
    try:
        r = requests.get(url, timeout=_TIMEOUT,
                         headers={"Accept": "application/vnd.github+json"})
        r.raise_for_status()
        data = r.json()
        return {
            "sha": data["sha"],
            "sha_short": data["sha"][:7],
            "message": data["commit"]["message"].splitlines()[0],
            "date": data["commit"]["committer"]["date"][:10],
        }
    except Exception as exc:
        logger.debug(f"[update_checker] GitHub commit check failed ({owner}/{repo}): {exc}")
        return None


def _github_latest_release(owner: str, repo: str) -> Optional[dict]:
    """Returns {'tag': ..., 'url': ..., 'date': ...} or None."""
    url = f"https://api.github.com/repos/{owner}/{repo}/releases/latest"
    try:
        r = requests.get(url, timeout=_TIMEOUT,
                         headers={"Accept": "application/vnd.github+json"})
        if r.status_code == 404:
            return None  # no releases
        r.raise_for_status()
        data = r.json()
        return {
            "tag": data["tag_name"],
            "url": data["html_url"],
            "date": data.get("published_at", "")[:10],
        }
    except Exception as exc:
        logger.debug(f"[update_checker] GitHub release check failed ({owner}/{repo}): {exc}")
        return None


def _pypi_latest_version(package: str) -> Optional[str]:
    try:
        r = requests.get(f"https://pypi.org/pypi/{package}/json", timeout=_TIMEOUT)
        r.raise_for_status()
        return r.json()["info"]["version"]
    except Exception as exc:
        logger.debug(f"[update_checker] PyPI check failed ({package}): {exc}")
        return None


# ---------------------------------------------------------------------------
# Per-package checks
# ---------------------------------------------------------------------------

def _check_scd_edition() -> Optional[ReleaseInfo]:
    installed_commit = _installed_scd_commit()
    latest = _github_latest_commit(_SCD_EDITION_OWNER, _SCD_EDITION_REPO, _SCD_EDITION_BRANCH)
    if not latest:
        return None

    latest_release = _github_latest_release(_SCD_EDITION_OWNER, _SCD_EDITION_REPO)

    installed_display = installed_commit[:7] if installed_commit else "unknown"
    latest_display = f"{latest['sha_short']} ({latest['date']})"

    if installed_commit and installed_commit == latest["sha"]:
        logger.debug("[update_checker] scd-edition is up to date")
        return None

    return ReleaseInfo(
        package="scd-edition",
        installed=installed_display,
        latest=latest_display,
        url=f"https://github.com/{_SCD_EDITION_OWNER}/{_SCD_EDITION_REPO}/commits/{_SCD_EDITION_BRANCH}",
        has_stable_release=latest_release is not None,
        latest_stable=latest_release["tag"] if latest_release else None,
        latest_stable_url=latest_release["url"] if latest_release else None,
    )


def _check_openhdemg() -> Optional[ReleaseInfo]:
    installed = _installed_version(_OPENHDEMG_PACKAGE)
    if not installed:
        return None
    latest = _pypi_latest_version(_OPENHDEMG_PACKAGE)
    if not latest:
        return None
    if _version_tuple(latest) <= _version_tuple(installed):
        logger.debug("[update_checker] openhdemg is up to date")
        return None
    return ReleaseInfo(
        package="openhdemg",
        installed=installed,
        latest=latest,
        url=f"https://pypi.org/project/{_OPENHDEMG_PACKAGE}/{latest}/",
    )


def _check_muedit(cache: dict) -> Optional[ReleaseInfo]:
    latest = _github_latest_commit(_MUEDIT_OWNER, _MUEDIT_REPO, _MUEDIT_BRANCH)
    if not latest:
        return None

    seen_sha = cache.get("muedit_seen_commit")
    if seen_sha and seen_sha == latest["sha"]:
        logger.debug("[update_checker] MUedit is up to date")
        return None

    return ReleaseInfo(
        package="MUedit",
        installed=seen_sha[:7] if seen_sha else "unknown",
        latest=f"{latest['sha_short']} ({latest['date']}: {latest['message'][:60]})",
        url=_MUEDIT_URL,
        latest_sha=latest["sha"],
    )


def _version_tuple(v: str) -> tuple:
    try:
        return tuple(int(x) for x in re.findall(r"\d+", v))
    except Exception:
        return (0,)


# ---------------------------------------------------------------------------
# QThread worker
# ---------------------------------------------------------------------------

class UpdateCheckerThread(QThread):
    """Checks all packages in background and emits results."""

    updates_ready = pyqtSignal(list)  # list[ReleaseInfo]

    def run(self):
        cache = _load_cache()
        results = []

        for check_fn, name in [
            (_check_scd_edition, "scd-edition"),
            (_check_openhdemg,   "openhdemg"),
        ]:
            try:
                info = check_fn()
                if info:
                    results.append(info)
            except Exception as exc:
                logger.warning(f"[update_checker] {name} check error: {exc}")

        try:
            muedit_info = _check_muedit(cache)
            if muedit_info:
                results.append(muedit_info)
        except Exception as exc:
            logger.warning(f"[update_checker] MUedit check error: {exc}")

        if results:
            self.updates_ready.emit(results)


# ---------------------------------------------------------------------------
# scd-edition upgrade dialog
# ---------------------------------------------------------------------------

class ScdEditionUpdateDialog(QDialog):
    """
    Dialog shown when scd-edition has a newer main-branch commit.
    Lets the user choose between installing latest main or keeping the
    current install (or the latest stable release, if one exists).
    """

    def __init__(self, info: ReleaseInfo, parent=None):
        super().__init__(parent)
        self.info = info
        self.setWindowTitle("scd-edition update available")
        self.setMinimumWidth(480)
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(Spacing.LG)
        layout.setContentsMargins(Spacing.XL, Spacing.XL, Spacing.XL, Spacing.XL)

        title = QLabel("scd-edition update available")
        title.setStyleSheet(f"font-size: {Fonts.SIZE_LG}; font-weight: bold; color: {Colors.TEXT_PRIMARY};")
        layout.addWidget(title)

        body = QLabel(
            f"<b>Installed:</b> {self.info.installed}<br>"
            f"<b>Latest main:</b> {self.info.latest}"
            + (
                f"<br><b>Latest stable release:</b> {self.info.latest_stable}"
                if self.info.has_stable_release else
                "<br><i>No stable release yet — only main branch available.</i>"
            )
        )
        body.setWordWrap(True)
        body.setStyleSheet(f"color: {Colors.TEXT_SECONDARY}; font-size: {Fonts.SIZE_SM};")
        layout.addWidget(body)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(Spacing.MD)

        btn_main = QPushButton("Install latest main")
        btn_main.setStyleSheet(Styles.button_primary())
        btn_main.clicked.connect(self._install_main)
        btn_row.addWidget(btn_main)

        if self.info.has_stable_release:
            btn_stable = QPushButton(f"Install stable ({self.info.latest_stable})")
            btn_stable.setStyleSheet(Styles.button_secondary())
            btn_stable.clicked.connect(self._install_stable)
            btn_row.addWidget(btn_stable)

        btn_skip = QPushButton("Skip")
        btn_skip.setStyleSheet(Styles.button_secondary())
        btn_skip.clicked.connect(self.reject)
        btn_row.addWidget(btn_skip)

        layout.addLayout(btn_row)

    def _install_main(self):
        self._run_install(f"git+https://github.com/{_SCD_EDITION_OWNER}/{_SCD_EDITION_REPO}.git")

    def _install_stable(self):
        tag = self.info.latest_stable
        self._run_install(
            f"git+https://github.com/{_SCD_EDITION_OWNER}/{_SCD_EDITION_REPO}.git@{tag}"
        )

    def _run_install(self, pip_spec: str):
        from PyQt5.QtWidgets import QMessageBox
        self.accept()
        try:
            result = subprocess.run(
                [sys.executable, "-m", "pip", "install", "--upgrade", pip_spec],
                capture_output=True, text=True, timeout=120,
            )
            if result.returncode == 0:
                QMessageBox.information(
                    self.parent(), "Update successful",
                    "scd-edition has been updated.\nPlease restart hdsemg-pipe.",
                )
            else:
                QMessageBox.warning(
                    self.parent(), "Update failed",
                    f"pip install failed:\n{result.stderr[-800:]}",
                )
        except Exception as exc:
            QMessageBox.critical(self.parent(), "Update error", str(exc))


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def start_update_check(parent_window) -> UpdateCheckerThread:
    """
    Start the background update check.  Attach the returned thread object to
    a long-lived parent so it is not garbage-collected.

    Usage (in WizardMainWindow.__init__ or after showMaximized):
        self._update_thread = start_update_check(self)
    """
    thread = UpdateCheckerThread(parent=parent_window)
    thread.updates_ready.connect(
        lambda results: _handle_results(results, parent_window)
    )
    thread.start()
    return thread


def _handle_results(results: list[ReleaseInfo], parent_window) -> None:
    from hdsemg_pipe.ui_elements.toast import toast_manager
    from PyQt5.QtCore import QTimer

    cache = _load_cache()
    delay_ms = 1500  # stagger toasts so they don't all appear at once

    for info in results:
        if info.package == "scd-edition":
            # Show interactive dialog after a short delay
            QTimer.singleShot(
                delay_ms,
                lambda i=info: ScdEditionUpdateDialog(i, parent_window).exec_(),
            )
            delay_ms += 400
        elif info.package == "MUedit":
            toast_manager.show_toast(
                f"MUedit update available ({info.latest}) — "
                f"visit GitHub to download the latest devHP branch.",
                toast_type="info",
                duration=12000,
            )
            # Remember that we've shown this commit so we don't nag every launch
            if info.latest_sha:
                cache["muedit_seen_commit"] = info.latest_sha
                _save_cache(cache)
            delay_ms += 400
        else:
            toast_manager.show_toast(
                f"{info.package} {info.latest} available "
                f"(installed: {info.installed})",
                toast_type="info",
                duration=10000,
            )
            delay_ms += 400

"""
Background update checker for external tools used by hdsemg-pipe.

Architecture
------------
Each tracked tool is described by a ``ToolSpec`` dataclass registered in
``REGISTERED_TOOLS``.  Adding a new tool = appending one ``ToolSpec`` to that
list; no other code needs to change.

``UpdateCheckerThread`` iterates the registry, resolves any user-configured
fork override from the app config, calls the appropriate check function, and
emits ``updates_ready`` with the results.

``_handle_results`` dispatches each result to the right UI response:
  - scd-edition  → interactive dialog (pip-installable, choose main vs stable)
  - openhdemg    → info toast
  - MUedit       → info toast + mark commit as seen in cache

To register a new tool
----------------------
1. Define its default GitHub coordinates (owner, repo, branch) or PyPI package.
2. Append a ``ToolSpec`` to ``REGISTERED_TOOLS`` at the bottom of this file.
3. If the tool needs custom UI on update (like scd-edition), add a branch in
   ``_handle_results``.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from dataclasses import dataclass, field
from importlib.metadata import version as pkg_version
from pathlib import Path
from typing import Callable, Optional

import requests
from PyQt5.QtCore import Qt, QThread, pyqtSignal
from PyQt5.QtWidgets import (
    QDialog, QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget,
)

from hdsemg_pipe._log.log_config import logger
from hdsemg_pipe.ui_elements.theme import Colors, Styles, Fonts, Spacing

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_TIMEOUT = 6  # seconds per HTTP request
_CACHE_FILE = Path.home() / ".hdsemg_pipe" / "update_cache.json"


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class ReleaseInfo:
    """One available update returned by a check function."""
    tool_key: str              # matches ToolSpec.key
    display_name: str
    installed: str             # human-readable installed version/commit
    latest: str                # human-readable latest version/commit
    latest_sha: Optional[str]  # full SHA (commit-based tools), for cache
    url: str                   # link to changelog / repo
    # scd-edition specific
    has_stable_release: bool = False
    latest_stable: Optional[str] = None
    latest_stable_url: Optional[str] = None


@dataclass
class ToolSpec:
    """
    Describes how to check updates for one external tool.

    Fields
    ------
    key             Unique ID used as config dict key and cache key prefix.
    display_name    Shown in settings UI and notifications.
    default_owner   GitHub owner of the canonical upstream repo.
    default_repo    GitHub repo name of the canonical upstream repo.
    default_branch  Branch to track (None → use PyPI instead).
    pypi_package    If set, check PyPI for the installed version and latest
                    release.  Used as the primary check when default_branch
                    is None; used as a fallback display version otherwise.
    allows_fork     Whether the settings UI shows a "use fork" section.
    check_fn        Injected at construction time; accepts (fork_cfg: dict)
                    and returns Optional[ReleaseInfo].  Leave None here —
                    it is set automatically by ``_build_check_fn``.
    """
    key: str
    display_name: str
    default_owner: str
    default_repo: str
    default_branch: Optional[str]   # None = PyPI-only check
    pypi_package: Optional[str] = None
    allows_fork: bool = True
    check_fn: Optional[Callable] = field(default=None, repr=False)

    @property
    def default_github_url(self) -> Optional[str]:
        if not self.default_owner or not self.default_repo:
            return None
        return f"https://github.com/{self.default_owner}/{self.default_repo}"


# ---------------------------------------------------------------------------
# Cache helpers
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

def _installed_pkg_version(package: str) -> Optional[str]:
    try:
        return pkg_version(package)
    except Exception:
        return None


def _installed_git_commit(package_dist_name: str) -> Optional[str]:
    """Read the installed git commit from a package's dist-info/direct_url.json."""
    try:
        import importlib.metadata as meta
        dist = meta.distribution(package_dist_name)
        text = dist.read_text("direct_url.json")
        if text:
            return json.loads(text).get("vcs_info", {}).get("commit_id")
    except Exception:
        pass
    return None


# ---------------------------------------------------------------------------
# Remote-data helpers
# ---------------------------------------------------------------------------

def _github_latest_commit(owner: str, repo: str, branch: str) -> Optional[dict]:
    """Returns {'sha', 'sha_short', 'message', 'date'} or None."""
    url = f"https://api.github.com/repos/{owner}/{repo}/commits/{branch}"
    try:
        r = requests.get(url, timeout=_TIMEOUT,
                         headers={"Accept": "application/vnd.github+json"})
        r.raise_for_status()
        data = r.json()
        return {
            "sha":       data["sha"],
            "sha_short": data["sha"][:7],
            "message":   data["commit"]["message"].splitlines()[0],
            "date":      data["commit"]["committer"]["date"][:10],
        }
    except Exception as exc:
        logger.debug(f"[update_checker] GitHub commit check failed ({owner}/{repo}@{branch}): {exc}")
        return None


def _github_latest_release(owner: str, repo: str) -> Optional[dict]:
    """Returns {'tag', 'url', 'date'} or None (including when no releases exist)."""
    url = f"https://api.github.com/repos/{owner}/{repo}/releases/latest"
    try:
        r = requests.get(url, timeout=_TIMEOUT,
                         headers={"Accept": "application/vnd.github+json"})
        if r.status_code == 404:
            return None
        r.raise_for_status()
        data = r.json()
        return {
            "tag":  data["tag_name"],
            "url":  data["html_url"],
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


def _version_tuple(v: str) -> tuple:
    try:
        return tuple(int(x) for x in re.findall(r"\d+", v))
    except Exception:
        return (0,)


def _parse_github_url(url: str) -> tuple[str, str] | None:
    """Extract (owner, repo) from a GitHub URL. Returns None on failure."""
    m = re.search(r"github\.com/([^/]+)/([^/\s]+?)(?:\.git)?$", url.strip().rstrip("/"))
    if m:
        return m.group(1), m.group(2)
    return None


# ---------------------------------------------------------------------------
# Generic check builders — injected into ToolSpec.check_fn
# ---------------------------------------------------------------------------

def _make_github_commit_check(spec: ToolSpec) -> Callable:
    """
    Returns a check function for a GitHub-commit-tracked tool.
    The last seen commit is stored in the cache under key
    ``{spec.key}_seen_commit``.
    """
    def _check(fork_cfg: dict) -> Optional[ReleaseInfo]:
        cache = _load_cache()

        # Resolve coordinates: fork override > defaults
        owner, repo = spec.default_owner, spec.default_repo
        branch = spec.default_branch
        if fork_cfg.get("github_url") and fork_cfg.get("branch"):
            parsed = _parse_github_url(fork_cfg["github_url"])
            if parsed:
                owner, repo = parsed
                branch = fork_cfg["branch"]

        latest = _github_latest_commit(owner, repo, branch)
        if not latest:
            return None

        seen_sha = cache.get(f"{spec.key}_seen_commit")
        if seen_sha and seen_sha == latest["sha"]:
            return None

        installed_display = seen_sha[:7] if seen_sha else "unknown"
        latest_display = f"{latest['sha_short']} ({latest['date']}: {latest['message'][:60]})"
        repo_url = f"https://github.com/{owner}/{repo}/tree/{branch}"

        return ReleaseInfo(
            tool_key=spec.key,
            display_name=spec.display_name,
            installed=installed_display,
            latest=latest_display,
            latest_sha=latest["sha"],
            url=repo_url,
        )

    return _check


def _make_pypi_check(spec: ToolSpec) -> Callable:
    """Returns a check function for a PyPI-versioned tool."""
    def _check(fork_cfg: dict) -> Optional[ReleaseInfo]:
        # If user configured a GitHub fork, switch to commit-based check
        if fork_cfg.get("github_url") and fork_cfg.get("branch"):
            commit_check = _make_github_commit_check(spec)
            return commit_check(fork_cfg)

        installed = _installed_pkg_version(spec.pypi_package)
        if not installed:
            return None
        latest = _pypi_latest_version(spec.pypi_package)
        if not latest:
            return None
        if _version_tuple(latest) <= _version_tuple(installed):
            return None

        return ReleaseInfo(
            tool_key=spec.key,
            display_name=spec.display_name,
            installed=installed,
            latest=latest,
            latest_sha=None,
            url=f"https://pypi.org/project/{spec.pypi_package}/{latest}/",
        )

    return _check


def _make_scd_edition_check(spec: ToolSpec) -> Callable:
    """
    scd-edition specific check: compares installed git commit,
    also fetches latest stable release (if any) for the upgrade dialog.
    """
    def _check(fork_cfg: dict) -> Optional[ReleaseInfo]:
        owner, repo = spec.default_owner, spec.default_repo
        branch = spec.default_branch
        if fork_cfg.get("github_url") and fork_cfg.get("branch"):
            parsed = _parse_github_url(fork_cfg["github_url"])
            if parsed:
                owner, repo = parsed
                branch = fork_cfg["branch"]

        installed_commit = _installed_git_commit("scd-edition")
        latest = _github_latest_commit(owner, repo, branch)
        if not latest:
            return None

        # Suppress if the installed commit matches, OR if the user already
        # installed this exact SHA via the update dialog (cache fallback for
        # environments where direct_url.json is not populated).
        cache = _load_cache()
        seen_sha = cache.get("scd_edition_seen_commit")
        if (installed_commit and installed_commit == latest["sha"]) or seen_sha == latest["sha"]:
            return None

        latest_release = _github_latest_release(owner, repo)
        installed_display = installed_commit[:7] if installed_commit else "unknown"
        latest_display = f"{latest['sha_short']} ({latest['date']})"

        return ReleaseInfo(
            tool_key=spec.key,
            display_name=spec.display_name,
            installed=installed_display,
            latest=latest_display,
            latest_sha=latest["sha"],
            url=f"https://github.com/{owner}/{repo}/commits/{branch}",
            has_stable_release=latest_release is not None,
            latest_stable=latest_release["tag"] if latest_release else None,
            latest_stable_url=latest_release["url"] if latest_release else None,
        )

    return _check


# ---------------------------------------------------------------------------
# Tool registry — add new tools here
# ---------------------------------------------------------------------------

REGISTERED_TOOLS: list[ToolSpec] = [
    ToolSpec(
        key="scd_edition",
        display_name="scd-edition",
        default_owner="AgneGris",
        default_repo="scd-edition",
        default_branch="main",
        pypi_package=None,
        allows_fork=True,
    ),
    ToolSpec(
        key="openhdemg",
        display_name="openhdemg",
        default_owner="GiacomoValliPhD",
        default_repo="openhdemg",
        default_branch=None,       # PyPI by default; GitHub when fork is set
        pypi_package="openhdemg",
        allows_fork=True,
    ),
    ToolSpec(
        key="muedit",
        display_name="MUedit",
        default_owner="simonavrillon",
        default_repo="MUedit",
        default_branch="main",
        pypi_package=None,
        allows_fork=True,
    ),
    ToolSpec(
        key="hdsemg_select",
        display_name="hdsemg-select",
        default_owner="",
        default_repo="",
        default_branch=None,   # PyPI-only
        pypi_package="hdsemg-select",
        allows_fork=False,
    ),
]

# Inject check functions
for _spec in REGISTERED_TOOLS:
    if _spec.key == "scd_edition":
        _spec.check_fn = _make_scd_edition_check(_spec)
    elif _spec.default_branch is None and _spec.pypi_package:
        _spec.check_fn = _make_pypi_check(_spec)
    else:
        _spec.check_fn = _make_github_commit_check(_spec)


def get_tool_spec(key: str) -> Optional[ToolSpec]:
    return next((s for s in REGISTERED_TOOLS if s.key == key), None)


# ---------------------------------------------------------------------------
# Fork config accessor
# ---------------------------------------------------------------------------

def get_fork_config(tool_key: str) -> dict:
    """Return the user-configured fork dict for a tool, or {}."""
    try:
        from hdsemg_pipe.config.config_manager import config
        from hdsemg_pipe.config.config_enums import Settings
        all_forks = config.get(Settings.UPDATE_FORK_CONFIG) or {}
        return all_forks.get(tool_key, {})
    except Exception:
        return {}


def save_fork_config(tool_key: str, github_url: str, branch: str) -> None:
    """Persist fork config for one tool. Pass empty strings to reset to default."""
    from hdsemg_pipe.config.config_manager import config
    from hdsemg_pipe.config.config_enums import Settings
    all_forks = dict(config.get(Settings.UPDATE_FORK_CONFIG) or {})
    if github_url.strip() and branch.strip():
        all_forks[tool_key] = {"github_url": github_url.strip(), "branch": branch.strip()}
    else:
        all_forks.pop(tool_key, None)
    config.set(Settings.UPDATE_FORK_CONFIG, all_forks)


# ---------------------------------------------------------------------------
# QThread worker
# ---------------------------------------------------------------------------

class UpdateCheckerThread(QThread):
    updates_ready = pyqtSignal(list)  # list[ReleaseInfo]

    def run(self):
        results = []
        for spec in REGISTERED_TOOLS:
            try:
                fork_cfg = get_fork_config(spec.key)
                info = spec.check_fn(fork_cfg)
                if info:
                    results.append(info)
            except Exception as exc:
                logger.warning(f"[update_checker] {spec.display_name} check error: {exc}")

        if results:
            self.updates_ready.emit(results)


# ---------------------------------------------------------------------------
# Combined update dialog (scd-edition + hdsemg-select, stacked)
# ---------------------------------------------------------------------------

class CombinedUpdateDialog(QDialog):
    """Single dialog showing all pip-installable updates, one section per tool."""

    _DIALOG_KEYS = {"scd_edition", "hdsemg_select"}

    def __init__(self, infos: list[ReleaseInfo], parent=None):
        super().__init__(parent)
        self.infos = infos
        self.setWindowTitle("Updates available")
        self.setMinimumWidth(500)
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(Spacing.LG)
        layout.setContentsMargins(Spacing.XL, Spacing.XL, Spacing.XL, Spacing.XL)

        title = QLabel("Software updates available")
        title.setStyleSheet(
            f"font-size: {Fonts.SIZE_LG}; font-weight: bold; color: {Colors.TEXT_PRIMARY};"
        )
        layout.addWidget(title)

        for i, info in enumerate(self.infos):
            if i > 0:
                sep = QFrame()
                sep.setFrameShape(QFrame.HLine)
                sep.setStyleSheet(f"color: {Colors.BORDER_DEFAULT};")
                layout.addWidget(sep)

            if info.tool_key == "scd_edition":
                layout.addWidget(self._build_scd_section(info))
            elif info.tool_key == "hdsemg_select":
                layout.addWidget(self._build_hdsemg_select_section(info))

        close_btn = QPushButton("Close")
        close_btn.setStyleSheet(Styles.button_secondary())
        close_btn.clicked.connect(self.reject)
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        btn_row.addWidget(close_btn)
        layout.addLayout(btn_row)

    # -- Section builders ----------------------------------------------------

    def _build_scd_section(self, info: ReleaseInfo) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        v.setSpacing(Spacing.SM)
        v.setContentsMargins(0, 0, 0, 0)

        name = QLabel("<b>scd-edition</b>")
        name.setStyleSheet(f"font-size: {Fonts.SIZE_BASE}; color: {Colors.TEXT_PRIMARY};")
        v.addWidget(name)

        stable_line = (
            f"<br><b>Latest stable:</b> {info.latest_stable}"
            if info.has_stable_release
            else "<br><i>No stable release yet — only main branch available.</i>"
        )
        body = QLabel(
            f"<b>Installed:</b> {info.installed}<br>"
            f"<b>Latest main:</b> {info.latest}" + stable_line
        )
        body.setWordWrap(True)
        body.setStyleSheet(f"color: {Colors.TEXT_SECONDARY}; font-size: {Fonts.SIZE_SM};")
        v.addWidget(body)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(Spacing.MD)

        btn_main = QPushButton("Install latest main")
        btn_main.setStyleSheet(Styles.button_primary())
        btn_main.clicked.connect(lambda: self._install_scd_main(info))
        btn_row.addWidget(btn_main)

        if info.has_stable_release:
            btn_stable = QPushButton(f"Install stable ({info.latest_stable})")
            btn_stable.setStyleSheet(Styles.button_secondary())
            btn_stable.clicked.connect(lambda: self._install_scd_stable(info))
            btn_row.addWidget(btn_stable)

        btn_row.addStretch()
        v.addLayout(btn_row)
        return w

    def _build_hdsemg_select_section(self, info: ReleaseInfo) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        v.setSpacing(Spacing.SM)
        v.setContentsMargins(0, 0, 0, 0)

        name = QLabel("<b>hdsemg-select</b>")
        name.setStyleSheet(f"font-size: {Fonts.SIZE_BASE}; color: {Colors.TEXT_PRIMARY};")
        v.addWidget(name)

        body = QLabel(
            f"<b>Installed:</b> {info.installed}<br>"
            f"<b>Latest (PyPI):</b> {info.latest}"
        )
        body.setWordWrap(True)
        body.setStyleSheet(f"color: {Colors.TEXT_SECONDARY}; font-size: {Fonts.SIZE_SM};")
        v.addWidget(body)

        btn_row = QHBoxLayout()
        btn_install = QPushButton(f"Install {info.latest}")
        btn_install.setStyleSheet(Styles.button_primary())
        btn_install.clicked.connect(lambda: self._install_hdsemg_select(info))
        btn_row.addWidget(btn_install)
        btn_row.addStretch()
        v.addLayout(btn_row)
        return w

    # -- Install actions -----------------------------------------------------

    def _install_scd_main(self, info: ReleaseInfo):
        spec = get_tool_spec("scd_edition")
        fork_cfg = get_fork_config("scd_edition")
        if fork_cfg.get("github_url") and fork_cfg.get("branch"):
            pip_spec = f"git+{fork_cfg['github_url'].rstrip('/')}.git@{fork_cfg['branch']}"
        else:
            pip_spec = (
                f"git+https://github.com/{spec.default_owner}/{spec.default_repo}.git"
                f"@{spec.default_branch}"
            )
        self._run_install("scd-edition", pip_spec, scd_sha=info.latest_sha)

    def _install_scd_stable(self, info: ReleaseInfo):
        spec = get_tool_spec("scd_edition")
        fork_cfg = get_fork_config("scd_edition")
        owner, repo = spec.default_owner, spec.default_repo
        if fork_cfg.get("github_url"):
            parsed = _parse_github_url(fork_cfg["github_url"])
            if parsed:
                owner, repo = parsed
        self._run_install(
            "scd-edition",
            f"git+https://github.com/{owner}/{repo}.git@{info.latest_stable}",
            scd_sha=info.latest_sha,
        )

    def _install_hdsemg_select(self, info: ReleaseInfo):
        spec = get_tool_spec("hdsemg_select")
        self._run_install("hdsemg-select", spec.pypi_package, scd_sha=None)

    def _run_install(self, display_name: str, pip_spec: str, *, scd_sha: Optional[str]):
        from PyQt5.QtWidgets import QMessageBox
        self.accept()
        try:
            result = subprocess.run(
                [sys.executable, "-m", "pip", "install", "--upgrade", pip_spec],
                capture_output=True, text=True, timeout=120,
            )
            if result.returncode == 0:
                if scd_sha:
                    cache = _load_cache()
                    cache["scd_edition_seen_commit"] = scd_sha
                    _save_cache(cache)
                QMessageBox.information(
                    self.parent(), "Update successful",
                    f"{display_name} has been updated.\nPlease restart hdsemg-pipe.",
                )
            else:
                QMessageBox.warning(
                    self.parent(), "Update failed",
                    f"pip install failed:\n{result.stderr[-800:]}",
                )
        except Exception as exc:
            QMessageBox.critical(self.parent(), "Update error", str(exc))


# ---------------------------------------------------------------------------
# Result dispatcher
# ---------------------------------------------------------------------------

def _handle_results(results: list[ReleaseInfo], parent_window) -> None:
    from hdsemg_pipe.ui_elements.toast import toast_manager
    from PyQt5.QtCore import QTimer

    cache = _load_cache()
    toast_delay_ms = 1500
    dialog_infos: list[ReleaseInfo] = []

    for info in results:
        if info.tool_key in CombinedUpdateDialog._DIALOG_KEYS:
            dialog_infos.append(info)
        elif info.latest_sha:
            # Commit-based tool (MUedit or any future GitHub-commit tool)
            toast_manager.show_toast(
                f"{info.display_name} update available — {info.latest}\n"
                f"Visit {info.url} to update.",
                toast_type="info",
                duration=12000,
            )
            cache[f"{info.tool_key}_seen_commit"] = info.latest_sha
            _save_cache(cache)
            toast_delay_ms += 400
        else:
            # Version-based tool (openhdemg / PyPI)
            toast_manager.show_toast(
                f"{info.display_name} {info.latest} available "
                f"(installed: {info.installed})",
                toast_type="info",
                duration=10000,
            )
            toast_delay_ms += 400

    if dialog_infos:
        QTimer.singleShot(
            1500,
            lambda: CombinedUpdateDialog(dialog_infos, parent_window).exec_(),
        )


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def start_update_check(parent_window) -> UpdateCheckerThread:
    """
    Start the background update check.  Attach the returned thread to a
    long-lived parent so it is not garbage-collected before it finishes.

    Usage (after window.showMaximized()):
        self._update_thread = start_update_check(self)
    """
    thread = UpdateCheckerThread(parent=parent_window)
    thread.updates_ready.connect(
        lambda results: _handle_results(results, parent_window)
    )
    thread.start()
    return thread

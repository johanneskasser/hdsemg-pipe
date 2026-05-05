"""
Updates & Fork Configuration Settings Tab.

Shows all registered update-tracked tools. For each tool the user can:
  - See the default upstream repo
  - Optionally enter a custom GitHub fork URL + branch
  - Save the fork config (persisted to config.json)

The update checker picks up these overrides on the next app start.
"""

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QLineEdit, QGroupBox, QFrame,
)
from PyQt5.QtCore import Qt

from hdsemg_pipe.ui_elements.theme import Styles, Colors, Fonts, Spacing, BorderRadius
from hdsemg_pipe.updates.update_checker import (
    REGISTERED_TOOLS, save_fork_config, get_fork_config,
    _installed_pkg_version, _pypi_latest_version, _version_tuple,
)


def init(parent) -> QVBoxLayout:
    """Build the Updates settings tab content and return its layout."""
    layout = QVBoxLayout()
    layout.setSpacing(Spacing.LG)
    layout.setContentsMargins(Spacing.LG, Spacing.LG, Spacing.LG, Spacing.LG)

    # ── Header ────────────────────────────────────────────────────────────
    header = QLabel(
        "<h2>Updates &amp; Fork Configuration</h2>"
        "hdsemg-pipe checks for updates of external tools on startup. "
        "By default the canonical upstream repositories are tracked. "
        "If you work with a custom fork you can configure it here."
    )
    header.setWordWrap(True)
    header.setStyleSheet(f"color: {Colors.TEXT_PRIMARY}; padding-bottom: 4px;")
    layout.addWidget(header)

    # ── One group per registered tool ────────────────────────────────────
    for spec in REGISTERED_TOOLS:
        if spec.allows_fork:
            group = _build_tool_group(spec, parent)
        else:
            group = _build_pypi_only_group(spec)
        layout.addWidget(group)

    layout.addStretch()
    return layout


# ---------------------------------------------------------------------------
# Per-tool group builder
# ---------------------------------------------------------------------------

def _build_tool_group(spec, parent) -> QGroupBox:
    fork_cfg = get_fork_config(spec.key)

    group = QGroupBox(spec.display_name)
    group.setStyleSheet(f"""
        QGroupBox {{
            font-size: {Fonts.SIZE_BASE};
            font-weight: bold;
            color: {Colors.TEXT_PRIMARY};
            border: 1px solid {Colors.BORDER_DEFAULT};
            border-radius: {BorderRadius.MD};
            margin-top: 6px;
            padding-top: 10px;
        }}
        QGroupBox::title {{
            subcontrol-origin: margin;
            left: 10px;
            padding: 0 4px;
        }}
    """)

    v = QVBoxLayout(group)
    v.setSpacing(Spacing.MD)
    v.setContentsMargins(Spacing.LG, Spacing.LG, Spacing.LG, Spacing.LG)

    # Default repo info
    default_label = QLabel(
        f"<b>Default upstream:</b> "
        f"<a href='{spec.default_github_url}'>{spec.default_github_url}</a>"
        + (f"  (branch: <code>{spec.default_branch}</code>)" if spec.default_branch else "  (PyPI)")
    )
    default_label.setOpenExternalLinks(True)
    default_label.setStyleSheet(f"color: {Colors.TEXT_SECONDARY}; font-size: {Fonts.SIZE_SM};")
    v.addWidget(default_label)

    # Separator
    sep = QFrame()
    sep.setFrameShape(QFrame.HLine)
    sep.setStyleSheet(f"color: {Colors.BORDER_DEFAULT};")
    v.addWidget(sep)

    fork_header = QLabel("Custom fork (optional)")
    fork_header.setStyleSheet(
        f"font-size: {Fonts.SIZE_SM}; font-weight: bold; color: {Colors.TEXT_PRIMARY};"
    )
    v.addWidget(fork_header)

    fork_desc = QLabel(
        "Enter a GitHub repository URL and branch to track a fork instead of "
        "the upstream. Leave both fields empty to revert to the default."
    )
    fork_desc.setWordWrap(True)
    fork_desc.setStyleSheet(f"color: {Colors.TEXT_SECONDARY}; font-size: {Fonts.SIZE_SM};")
    v.addWidget(fork_desc)

    # URL row
    url_row = QHBoxLayout()
    url_label = QLabel("Repository URL:")
    url_label.setFixedWidth(120)
    url_label.setStyleSheet(f"color: {Colors.TEXT_PRIMARY}; font-size: {Fonts.SIZE_SM};")
    url_input = QLineEdit()
    url_input.setPlaceholderText(f"https://github.com/username/{spec.default_repo}")
    url_input.setText(fork_cfg.get("github_url", ""))
    url_input.setStyleSheet(Styles.input_field())
    url_row.addWidget(url_label)
    url_row.addWidget(url_input)
    v.addLayout(url_row)

    # Branch row
    branch_row = QHBoxLayout()
    branch_label = QLabel("Branch:")
    branch_label.setFixedWidth(120)
    branch_label.setStyleSheet(f"color: {Colors.TEXT_PRIMARY}; font-size: {Fonts.SIZE_SM};")
    branch_input = QLineEdit()
    branch_input.setPlaceholderText(spec.default_branch or "main")
    branch_input.setText(fork_cfg.get("branch", ""))
    branch_input.setStyleSheet(Styles.input_field())
    branch_row.addWidget(branch_label)
    branch_row.addWidget(branch_input)
    v.addLayout(branch_row)

    # Status + Save row
    status_row = QHBoxLayout()
    status_label = QLabel("")
    status_label.setStyleSheet(f"color: {Colors.GREEN_600}; font-size: {Fonts.SIZE_SM};")
    status_row.addWidget(status_label, stretch=1)

    save_btn = QPushButton("Save")
    save_btn.setFixedWidth(80)
    save_btn.setStyleSheet(Styles.button_primary())
    save_btn.clicked.connect(
        lambda _checked, k=spec.key, u=url_input, b=branch_input, s=status_label:
            _on_save(k, u, b, s)
    )
    status_row.addWidget(save_btn)
    v.addLayout(status_row)

    # Show active fork hint if one is already configured
    if fork_cfg.get("github_url"):
        status_label.setText(
            f"Active fork: {fork_cfg['github_url']} @ {fork_cfg.get('branch', '?')}"
        )
        status_label.setStyleSheet(f"color: {Colors.BLUE_600}; font-size: {Fonts.SIZE_SM};")

    return group


def _build_pypi_only_group(spec) -> QGroupBox:
    installed = _installed_pkg_version(spec.pypi_package) or "not installed"

    group = QGroupBox(spec.display_name)
    group.setStyleSheet(f"""
        QGroupBox {{
            font-size: {Fonts.SIZE_BASE};
            font-weight: bold;
            color: {Colors.TEXT_PRIMARY};
            border: 1px solid {Colors.BORDER_DEFAULT};
            border-radius: {BorderRadius.MD};
            margin-top: 6px;
            padding-top: 10px;
        }}
        QGroupBox::title {{
            subcontrol-origin: margin;
            left: 10px;
            padding: 0 4px;
        }}
    """)

    v = QVBoxLayout(group)
    v.setSpacing(Spacing.MD)
    v.setContentsMargins(Spacing.LG, Spacing.LG, Spacing.LG, Spacing.LG)

    info_label = QLabel(
        f"<b>Source:</b> PyPI &mdash; "
        f"<a href='https://pypi.org/project/{spec.pypi_package}/'>"
        f"pypi.org/project/{spec.pypi_package}</a><br>"
        f"<b>Installed version:</b> {installed}"
    )
    info_label.setOpenExternalLinks(True)
    info_label.setWordWrap(True)
    info_label.setStyleSheet(f"color: {Colors.TEXT_SECONDARY}; font-size: {Fonts.SIZE_SM};")
    v.addWidget(info_label)

    btn_row = QHBoxLayout()
    btn_row.setSpacing(Spacing.MD)

    status_label = QLabel("")
    status_label.setStyleSheet(f"color: {Colors.TEXT_SECONDARY}; font-size: {Fonts.SIZE_SM};")
    btn_row.addWidget(status_label, stretch=1)

    update_btn = QPushButton("Update to latest")
    update_btn.setFixedWidth(140)
    update_btn.setStyleSheet(Styles.button_primary())
    update_btn.clicked.connect(
        lambda _checked, s=spec, sl=status_label, btn=update_btn:
            _on_pypi_update(s, sl, btn)
    )
    btn_row.addWidget(update_btn)

    v.addLayout(btn_row)

    return group


def _on_pypi_update(spec, status_label: QLabel, btn: QPushButton) -> None:
    import subprocess
    import sys
    from PyQt5.QtWidgets import QApplication, QMessageBox

    btn.setEnabled(False)
    status_label.setText("Checking PyPI…")
    status_label.setStyleSheet(f"color: {Colors.TEXT_SECONDARY}; font-size: {Fonts.SIZE_SM};")
    QApplication.processEvents()

    installed = _installed_pkg_version(spec.pypi_package)
    latest = _pypi_latest_version(spec.pypi_package)

    if not latest:
        status_label.setText("Could not reach PyPI.")
        status_label.setStyleSheet(f"color: {Colors.RED_600}; font-size: {Fonts.SIZE_SM};")
        btn.setEnabled(True)
        return

    if not installed or _version_tuple(latest) <= _version_tuple(installed):
        status_label.setText(f"Already up to date ({installed}).")
        status_label.setStyleSheet(f"color: {Colors.GREEN_600}; font-size: {Fonts.SIZE_SM};")
        btn.setEnabled(True)
        return

    status_label.setText(f"Installing {spec.pypi_package} {latest}…")
    QApplication.processEvents()

    try:
        result = subprocess.run(
            [sys.executable, "-m", "pip", "install", "--upgrade", spec.pypi_package],
            capture_output=True, text=True, timeout=120,
        )
        if result.returncode == 0:
            status_label.setText(f"Updated to {latest}. Please restart hdsemg-pipe.")
            status_label.setStyleSheet(f"color: {Colors.GREEN_600}; font-size: {Fonts.SIZE_SM};")
        else:
            status_label.setText("Update failed — see error dialog.")
            status_label.setStyleSheet(f"color: {Colors.RED_600}; font-size: {Fonts.SIZE_SM};")
            QMessageBox.warning(
                None, "Update failed",
                f"pip install failed:\n{result.stderr[-800:]}",
            )
    except Exception as exc:
        status_label.setText("Update error — see error dialog.")
        status_label.setStyleSheet(f"color: {Colors.RED_600}; font-size: {Fonts.SIZE_SM};")
        QMessageBox.critical(None, "Update error", str(exc))

    btn.setEnabled(True)


def _on_save(tool_key: str, url_input: QLineEdit, branch_input: QLineEdit,
             status_label: QLabel) -> None:
    url = url_input.text().strip()
    branch = branch_input.text().strip()

    # Validate: both empty = reset, both filled = ok, mixed = error
    if bool(url) != bool(branch):
        status_label.setText("Please fill in both URL and branch (or leave both empty).")
        status_label.setStyleSheet(f"color: {Colors.RED_600}; font-size: {Fonts.SIZE_SM};")
        return

    save_fork_config(tool_key, url, branch)

    if url and branch:
        status_label.setText(f"Saved — will use fork on next start: {url} @ {branch}")
        status_label.setStyleSheet(f"color: {Colors.GREEN_600}; font-size: {Fonts.SIZE_SM};")
    else:
        status_label.setText("Saved — reverted to default upstream.")
        status_label.setStyleSheet(f"color: {Colors.GREEN_600}; font-size: {Fonts.SIZE_SM};")

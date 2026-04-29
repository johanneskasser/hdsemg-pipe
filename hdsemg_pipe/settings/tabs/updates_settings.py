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
from hdsemg_pipe.updates.update_checker import REGISTERED_TOOLS, save_fork_config, get_fork_config


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
        if not spec.allows_fork:
            continue
        group = _build_tool_group(spec, parent)
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

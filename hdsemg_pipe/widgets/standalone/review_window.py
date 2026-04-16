# hdsemg_pipe/widgets/standalone/review_window.py
"""Top-level QMainWindow for the standalone MU Quality Review entry point."""
from __future__ import annotations

from pathlib import Path

from PyQt5.QtWidgets import QMainWindow

from hdsemg_pipe.ui_elements.toast import toast_manager
from hdsemg_pipe.widgets.standalone.review_panel import StandaloneMUReviewPanel


class StandaloneReviewWindow(QMainWindow):
    """A minimal main window that hosts the standalone MU Quality Review panel."""

    def __init__(self, folder_path: Path) -> None:
        super().__init__()
        self.setWindowTitle(f"MU Quality Review — {folder_path.name}")

        panel = StandaloneMUReviewPanel(folder_path=folder_path, parent=self)
        self.setCentralWidget(panel)

        # Wire up toast notifications to the panel widget
        toast_manager.set_parent(panel)

# hdsemg_pipe/widgets/standalone/review_panel.py
"""Standalone wrapper panel that composes MUQualityReviewWizardWidget."""
from __future__ import annotations

from pathlib import Path
from typing import List, Set

from PyQt5.QtWidgets import QDialog, QMessageBox, QVBoxLayout, QWidget

from hdsemg_pipe._log.log_config import logger
from hdsemg_pipe.ui_elements.toast import toast_manager
from hdsemg_pipe.widgets.standalone.filter_worker import StandaloneFilterWorker
from hdsemg_pipe.widgets.standalone.output_options_dialog import OutputOptionsDialog
from hdsemg_pipe.widgets.wizard.MUQualityReviewWizardWidget import MUQualityReviewWizardWidget


# Same list used in MUQualityReviewWizardWidget.check()
_EXCLUDED_PREFIXES = (
    "algorithm_params",
    "decomposition_mapping",
    "multigrid_groupings",
    "status_test",
)


class StandaloneMUReviewPanel(QWidget):
    """Embeds MUQualityReviewWizardWidget for standalone use on an arbitrary folder.

    Bypasses global_state and wizard step sequencing entirely.  The "Proceed"
    button is replaced with a "Filter" button that shows an OutputOptionsDialog
    before writing filtered files.
    """

    def __init__(self, folder_path: Path, parent: QWidget = None) -> None:
        super().__init__(parent)
        self._folder_path = folder_path
        self._filter_worker: StandaloneFilterWorker | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Instantiate the review widget without registering in global_state
        self._review = MUQualityReviewWizardWidget(parent=self)
        layout.addWidget(self._review)

        # Update header to reflect standalone context
        self._review.step_number_label.setText("Standalone Mode")

        # Swap the Proceed button for a Filter button
        self._review._proceed_btn.setText("Filter")
        self._review._proceed_btn.clicked.disconnect()
        self._review._proceed_btn.clicked.connect(self._on_filter_clicked)

        # Populate the file list directly (bypasses check() and global_state)
        filepaths = self._scan_folder(folder_path)
        self._detected_siblings = self._detect_siblings(folder_path, filepaths)
        if filepaths:
            self._review._populate_file_list(filepaths)
        else:
            logger.warning("StandaloneMUReviewPanel: no JSON files found in %s", folder_path)

    # ------------------------------------------------------------------
    # Folder scanning
    # ------------------------------------------------------------------

    def _scan_folder(self, folder: Path) -> List[str]:
        return sorted(
            str(p)
            for p in folder.iterdir()
            if p.suffix.lower() == ".json"
            and not any(p.name.startswith(ex) for ex in _EXCLUDED_PREFIXES)
        )

    @staticmethod
    def _detect_siblings(folder: Path, filepaths: List[str]) -> Set[str]:
        """Return which sibling types exist for any of the JSON files."""
        detected: Set[str] = set()
        for fp in filepaths:
            stem = Path(fp).stem
            if (folder / (stem + ".pkl")).exists():
                detected.add("pkl")
            if (folder / (stem + "_muedit.mat")).exists():
                detected.add("mat")
            if len(detected) == 2:
                break  # no point scanning further
        return detected

    # ------------------------------------------------------------------
    # Filter action
    # ------------------------------------------------------------------

    def _on_filter_clicked(self) -> None:
        dialog = OutputOptionsDialog(
            self._folder_path,
            detected_siblings=self._detected_siblings,
            parent=self,
        )
        if dialog.exec_() != QDialog.Accepted:
            return

        config = dialog.get_config()

        # Confirm in-place destructive action
        if config.mode == "in_place":
            reply = QMessageBox.warning(
                self,
                "Confirm In-Place Filter",
                "This will permanently overwrite the original files and delete any "
                "unchecked recordings from the source folder.\n\nContinue?",
                QMessageBox.Yes | QMessageBox.Cancel,
                QMessageBox.Cancel,
            )
            if reply != QMessageBox.Yes:
                return

        kept_files = [
            Path(fp).name
            for fp, checked in self._review._checked.items()
            if checked
        ]
        all_files = [Path(fp).name for fp in self._review._all_filepaths]

        self._review._proceed_btn.setEnabled(False)
        self._review._proceed_btn.setText("Filtering…")

        self._filter_worker = StandaloneFilterWorker(
            kept_files=kept_files,
            all_files=all_files,
            thresholds=self._review._build_thresholds(),
            overrides=self._review._overrides,
            config=config,
        )
        self._filter_worker.progress.connect(
            lambda cur, tot: self._review._proceed_btn.setText(f"Filtering {cur}/{tot}…")
        )
        self._filter_worker.finished.connect(self._on_filter_done)
        self._filter_worker.error.connect(self._on_filter_error)
        self._filter_worker.start()

    def _on_filter_done(self, n_written: int) -> None:
        self._review._proceed_btn.setEnabled(True)
        self._review._proceed_btn.setText("Filter")
        toast_manager.show_toast(
            f"Done — {n_written} file(s) written.", "success"
        )

    def _on_filter_error(self, error: str) -> None:
        self._review._proceed_btn.setEnabled(True)
        self._review._proceed_btn.setText("Filter")
        toast_manager.show_toast(f"Filter failed: {error}", "error", duration=8000)

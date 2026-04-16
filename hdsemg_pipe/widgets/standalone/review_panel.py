# hdsemg_pipe/widgets/standalone/review_panel.py
"""Standalone wrapper panel that composes MUQualityReviewWizardWidget."""
from __future__ import annotations

from pathlib import Path
from typing import List, Set

from PyQt5.QtWidgets import (
    QButtonGroup,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QRadioButton,
    QVBoxLayout,
    QWidget,
)

from hdsemg_pipe._log.log_config import logger
from hdsemg_pipe.ui_elements.theme import Colors, Spacing, Styles
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


class _MatVersionDialog(QDialog):
    """Ask the user which MAT version to use when both pre- and post-edit exist."""

    EDITED = "edited"
    UNEDITED = "unedited"
    BOTH = "both"

    def __init__(self, n_conflicts: int, parent: QWidget = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("MAT File Version")
        self.setMinimumWidth(420)

        layout = QVBoxLayout(self)
        layout.setSpacing(Spacing.MD)
        layout.setContentsMargins(Spacing.LG, Spacing.LG, Spacing.LG, Spacing.LG)

        msg = QLabel(
            f"For {n_conflicts} recording(s) both the unedited "
            f"(<code>_muedit.mat</code>) and the edited "
            f"(<code>_muedit.mat_edited.mat</code>) version exist.\n\n"
            "Which version should be loaded for review?"
        )
        msg.setWordWrap(True)
        msg.setTextFormat(1)  # Qt.RichText
        layout.addWidget(msg)

        self._group = QButtonGroup(self)

        self._rb_edited = QRadioButton("Edited version  (post-MUedit, edition.*)")
        self._rb_edited.setChecked(True)
        self._rb_unedited = QRadioButton("Unedited version  (pre-MUedit, signal.*)")
        self._rb_both = QRadioButton("Both  (show as separate entries)")

        for rb in (self._rb_edited, self._rb_unedited, self._rb_both):
            self._group.addButton(rb)
            layout.addWidget(rb)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok)
        buttons.accepted.connect(self.accept)
        layout.addWidget(buttons)

    def choice(self) -> str:
        if self._rb_unedited.isChecked():
            return self.UNEDITED
        if self._rb_both.isChecked():
            return self.BOTH
        return self.EDITED


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
        filepaths = self._resolve_files(folder_path, parent=self)
        self._detected_siblings = self._detect_siblings(folder_path, filepaths)
        if filepaths:
            self._review._populate_file_list(filepaths)
        else:
            logger.warning("StandaloneMUReviewPanel: no decomposition files found in %s", folder_path)

    # ------------------------------------------------------------------
    # Folder scanning
    # ------------------------------------------------------------------

    @staticmethod
    def _mat_base_stem(mat_name: str) -> str:
        """Strip MUedit suffixes to get the recording base stem."""
        return (mat_name
                .replace("_muedit.mat_edited.mat", "")
                .replace("_muedit.mat", ""))

    def _scan_folder(self, folder: Path) -> tuple:
        """Collect decomposition files from *folder*.

        Returns ``(json_files, mat_unedited, mat_edited, json_stems)`` where
        each entry is a list of absolute path strings and ``json_stems`` is a
        set of JSON base stems (for sibling detection).

        MAT files are split into unedited (``signal.*``) and edited
        (``edition.*``) groups so the caller can resolve conflicts.
        """
        json_stems: set = set()
        json_files: List[str] = []
        mat_unedited: List[str] = []  # *_muedit.mat
        mat_edited: List[str] = []    # *_muedit.mat_edited.mat

        for p in sorted(folder.iterdir()):
            if any(p.name.startswith(ex) for ex in _EXCLUDED_PREFIXES):
                continue
            name = p.name
            if p.suffix.lower() == ".json":
                json_files.append(str(p))
                json_stems.add(p.stem)
            elif name.endswith("_muedit.mat_edited.mat"):
                mat_edited.append(str(p))
            elif name.endswith("_muedit.mat"):
                mat_unedited.append(str(p))

        return json_files, mat_unedited, mat_edited, json_stems

    def _resolve_files(self, folder: Path, parent: QWidget) -> List[str]:
        """Return the final list of primary files for the review panel.

        Resolution rules
        ----------------
        1. JSON always wins over any MAT with the same base stem.
        2. For standalone MAT (no companion JSON): if both unedited AND edited
           versions exist for the same recording, ask the user which to use.
        """
        json_files, mat_unedited, mat_edited, json_stems = self._scan_folder(folder)

        # Filter out MATs that have a companion JSON
        def no_json(paths: List[str]) -> List[str]:
            return [p for p in paths
                    if self._mat_base_stem(Path(p).name) not in json_stems]

        standalone_unedited = no_json(mat_unedited)
        standalone_edited = no_json(mat_edited)

        # Find conflicts: same base stem appears in both lists
        unedited_by_base = {self._mat_base_stem(Path(p).name): p for p in standalone_unedited}
        edited_by_base   = {self._mat_base_stem(Path(p).name): p for p in standalone_edited}
        conflict_bases   = set(unedited_by_base) & set(edited_by_base)

        chosen_mats: List[str] = []

        if conflict_bases:
            dlg = _MatVersionDialog(len(conflict_bases), parent=parent)
            dlg.exec_()
            choice = dlg.choice()

            for base, upath in unedited_by_base.items():
                if base in conflict_bases:
                    if choice == _MatVersionDialog.UNEDITED:
                        chosen_mats.append(upath)
                    elif choice == _MatVersionDialog.BOTH:
                        chosen_mats.append(upath)
                else:
                    chosen_mats.append(upath)

            for base, epath in edited_by_base.items():
                if base in conflict_bases:
                    if choice == _MatVersionDialog.EDITED:
                        chosen_mats.append(epath)
                    elif choice == _MatVersionDialog.BOTH:
                        chosen_mats.append(epath)
                else:
                    chosen_mats.append(epath)
        else:
            chosen_mats = standalone_unedited + standalone_edited

        return sorted(json_files + chosen_mats)

    @staticmethod
    def _detect_siblings(folder: Path, filepaths: List[str]) -> Set[str]:
        """Return which sibling types exist alongside any JSON primary file."""
        detected: Set[str] = set()
        for fp in filepaths:
            p = Path(fp)
            if p.suffix.lower() != ".json":
                continue  # MAT files are primary, not JSON-siblings
            stem = p.stem
            if (folder / (stem + ".pkl")).exists():
                detected.add("pkl")
            if (folder / (stem + "_muedit.mat")).exists():
                detected.add("mat")
            if len(detected) == 2:
                break
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

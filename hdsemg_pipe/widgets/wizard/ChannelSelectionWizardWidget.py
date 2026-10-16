import os
from typing import List

from PyQt5.QtCore import QThread, pyqtSignal
from PyQt5.QtWidgets import QMessageBox

from hdsemg_pipe.actions.channel_selection_summary import (
    FileSummary, collect_channel_selection_summary,
)
from hdsemg_pipe.actions.file_manager import start_file_processing, get_channel_selection_status
from hdsemg_pipe.actions.workers import ChannelSelectionWorker
from hdsemg_pipe.ui_elements.loading_overlay import LoadingOverlay
from hdsemg_pipe.widgets.channel_selection_view import ChannelSelectionSummaryView
from hdsemg_pipe.config.config_enums import Settings
from hdsemg_pipe.config.config_manager import config
from hdsemg_pipe._log.log_config import logger
from hdsemg_pipe.state.global_state import global_state
from hdsemg_pipe.ui_elements.loadingbutton import LoadingButton
from hdsemg_pipe.widgets.WizardStepWidget import WizardStepWidget
from hdsemg_pipe.ui_elements.theme import Styles


class _SummaryWorker(QThread):
    """Reads the hdsemg-select sidecar JSONs off the UI thread."""
    loaded = pyqtSignal(object)  # List[FileSummary]

    def __init__(self, cropped_files: List[str], channel_sel_dir: str):
        super().__init__()
        self._cropped_files = list(cropped_files)
        self._dir = channel_sel_dir

    def run(self):
        self.loaded.emit(collect_channel_selection_summary(self._cropped_files, self._dir))


class ChannelSelectionWizardWidget(WizardStepWidget):
    def __init__(self):
        """Step 7: Channel selection from the loaded .mat files."""
        super().__init__(
            step_index=7,
            step_name="Channel Selection",
            description="Select the channels to be processed using the hdsemg-select tool."
        )
        self.processed_files = 0
        self.total_files = 0
        self._summary_worker = None
        self._edit_worker = None
        self._overlay = None
        self._summary_key = None
        self._build_summary_ui()

    def _build_summary_ui(self):
        """Overview of a previous/partial run (kept/dropped per file and grid)."""
        self.summary_view = ChannelSelectionSummaryView()
        self.summary_view.edit_requested.connect(self._edit_file)
        self.summary_view.setVisible(False)
        # Insert above the button row (index 0 is the info label, 1 the buttons).
        self.content_layout.insertWidget(1, self.summary_view)

    # ------------------------------------------------------------------
    # Lazy, asynchronous summary of an existing run
    # ------------------------------------------------------------------

    def on_shown(self):
        self.check()
        self._refresh_summary()

    def _refresh_summary(self, force: bool = False):
        if not global_state.workfolder or not global_state.cropped_files:
            return
        chan_dir = global_state.get_channel_selection_path()
        if not os.path.isdir(chan_dir):
            return
        # mtime changes when files are added/removed, so a newer run re-triggers the load.
        key = (chan_dir, len(global_state.cropped_files), os.stat(chan_dir).st_mtime)
        if not force and key == self._summary_key:
            return  # already shown for this folder
        if self._summary_worker is not None and self._summary_worker.isRunning():
            return
        if self._overlay is None:
            self._overlay = LoadingOverlay.show_over(self.content_card, "Loading channel selection…")
        worker = _SummaryWorker(global_state.cropped_files, chan_dir)
        worker.loaded.connect(lambda res, k=key: self._on_summary_loaded(res, k))
        self._summary_worker = worker
        worker.start()

    def _on_summary_loaded(self, summaries: List[FileSummary], key):
        if self._overlay is not None:
            self._overlay.hide()
            self._overlay.deleteLater()
            self._overlay = None
        self._summary_key = key
        self.summary_view.set_summaries(summaries)
        self.summary_view.setVisible(bool(summaries))

    def _edit_file(self, mat_path: str):
        if self._edit_worker is not None and self._edit_worker.isRunning():
            return
        # Input and output are the same cleaned file: hdsemg-select overwrites it
        # (and its sidecar JSON) when the user saves.
        worker = ChannelSelectionWorker(mat_path, output_path=mat_path)
        worker.finished.connect(self._on_edit_done)
        worker.failed.connect(self._on_edit_failed)
        self._edit_worker = worker
        self.summary_view.set_editing(True)  # one external editor at a time
        self.info("Editing in hdsemg-select — close it to continue.")
        worker.start()

    def _on_edit_done(self):
        self.summary_view.set_editing(False)
        self._refresh_summary(force=True)

    def _on_edit_failed(self, msg: str):
        self.summary_view.set_editing(False)
        self.warn(f"Could not start hdsemg-select: {msg}")
        self._refresh_summary(force=True)

    def create_buttons(self):
        """Creates the button for channel selection."""
        self.btn_select_channels = LoadingButton("Select Channels")
        self.btn_select_channels.setStyleSheet(Styles.button_primary())
        self.btn_select_channels.clicked.connect(self.start_processing)
        self.buttons.append(self.btn_select_channels)

    def start_processing(self):
        """Starts (or resumes) file processing and updates progress dynamically."""
        if not global_state.cropped_files:
            logger.warning("No files found for channel selection.")
            return
        if not config.get(Settings.HDSEMG_SELECT_INSTALLED):
            QMessageBox.information(
                self, "Warning",
                "hdsemg-select is not installed. Please install it in settings first.",
                QMessageBox.Ok
            )
            self.setActionButtonsEnabled(False)
            return
        logger.debug("Starting channel selection processing.")
        self.btn_select_channels.setEnabled(False)
        self.btn_select_channels.start_loading()

        start_file_processing(self)

    def update(self, path):
        """Updates the label when a file or folder is selected."""
        self.total_files = len(global_state.cropped_files)
        self.update_progress(self.processed_files, self.total_files)
        if self.total_files != 0:
            self.setActionButtonsEnabled(True)

    def update_progress(self, processed, total):
        """Updates the progress display dynamically."""
        self.additional_information_label.setText(f"{processed}/{total}")

        if processed >= total > 0:
            self.btn_select_channels.stop_loading()
            self.complete_step()

    def check(self):
        if config.get(Settings.HDSEMG_SELECT_INSTALLED) is False:
            self.warn("hdsemg-select is not installed. Please install it to proceed (see Settings).")
            self.setActionButtonsEnabled(False)
            return

        self.clear_status()

        # Detect whether a partial or complete run already exists on disk
        if not global_state.workfolder:
            self.setActionButtonsEnabled(True)
            return

        channel_sel_dir = global_state.get_channel_selection_path()
        if (
            global_state.cropped_files
            and os.path.isdir(channel_sel_dir)
        ):
            status = get_channel_selection_status(global_state.cropped_files, channel_sel_dir)
            n_done = status["n_done"]
            n_total = status["n_total"]

            if n_done > 0 and n_done < n_total:
                # Partial run – offer to continue
                self.btn_select_channels.setText("Continue Channel Selection")
                self.additional_information_label.setText(f"{n_done}/{n_total}")
                self.info(
                    f"{n_done} of {n_total} files already processed. "
                    "Click to continue where you left off."
                )
            else:
                self.btn_select_channels.setText("Select Channels")

        self.setActionButtonsEnabled(True)

    def complete_step(self, processed_files: int | None = None):
        # refresh counts
        self.total_files = len(global_state.channel_selection_files)
        self.processed_files = processed_files if processed_files is not None else self.total_files

        # update the label *inline*
        self.additional_information_label.setText(f"{self.processed_files}/{self.total_files}")

        # reset button label in case it was changed to "Continue"
        self.btn_select_channels.setText("Select Channels")

        # make sure the loading spinner is off
        self.btn_select_channels.stop_loading()

        # mark the step as complete (signals, styling, etc.)
        super().complete_step()

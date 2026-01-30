"""
RMS Quality Analysis Wizard Widget

Pipeline step for analyzing RMS noise quality across EMG recordings.
"""

from PyQt5.QtWidgets import QPushButton

from hdsemg_pipe.actions.rms_quality_analysis import RMSQualityDialog
from hdsemg_pipe.actions.skip_marker import save_skip_marker
from hdsemg_pipe.config.config_enums import Settings
from hdsemg_pipe.config.config_manager import config
from hdsemg_pipe.state.global_state import global_state
from hdsemg_pipe.widgets.WizardStepWidget import WizardStepWidget
from hdsemg_pipe._log.log_config import logger
from hdsemg_pipe.ui_elements.theme import Styles


class RMSQualityWizardWidget(WizardStepWidget):
    """Wizard step for RMS quality analysis."""

    def __init__(self):
        super().__init__(
            step_index=4,
            step_name="RMS Quality Analysis",
            description=(
                "Analyze signal quality across all files. Select a quiet region "
                "(e.g., rest period) to assess baseline noise levels. Results are "
                "saved to the analysis folder."
            )
        )
        self.rms_dialog = None

    def create_buttons(self):
        """Create the step action buttons."""
        btn_skip = QPushButton("Skip")
        btn_skip.setStyleSheet(Styles.button_secondary())
        btn_skip.clicked.connect(self.skip_step)
        self.buttons.append(btn_skip)

        btn_start = QPushButton("Start Analysis")
        btn_start.setStyleSheet(Styles.button_primary())
        btn_start.clicked.connect(self.start_analysis)
        self.buttons.append(btn_start)

    def skip_step(self):
        """Skip the RMS analysis step."""
        logger.debug("Skipping RMS Quality Analysis step.")
        # Save skip marker for state reconstruction
        analysis_folder = global_state.get_analysis_path()
        save_skip_marker(analysis_folder, "RMS quality analysis skipped")
        # Call parent skip_step to mark as skipped in GlobalState
        super().skip_step("RMS quality analysis skipped - proceeding to next step")

    def start_analysis(self):
        """Start the RMS quality analysis dialog."""
        logger.debug("Starting RMS Quality Analysis.")

        files = global_state.line_noise_cleaned_files
        if not files:
            self.warn("No files available for analysis. Complete the Line Noise Removal step first.")
            return

        self.rms_dialog = RMSQualityDialog(files, self)
        result = self.rms_dialog.exec_()

        if result == self.rms_dialog.Accepted:
            # Analysis completed and saved
            if self.rms_dialog.analysis_results:
                results = self.rms_dialog.analysis_results
                self.success(
                    f"RMS analysis complete! Mean: {results.grand_mean:.2f} ± "
                    f"{results.grand_std:.2f} µV across {results.total_channels} channels."
                )
                self.additional_information_label.setText(
                    f"Analysis saved to: {global_state.get_analysis_path()}"
                )
            self.complete_step()
        else:
            logger.info("RMS analysis canceled by user.")
            self.info("RMS analysis was canceled.")

    def check(self):
        """Check if this step can be executed."""
        if config.get(Settings.WORKFOLDER_PATH) is None:
            self.warn("Workfolder path is not set. Please configure it in Settings.")
            self.setActionButtonsEnabled(False)
        elif not global_state.line_noise_cleaned_files:
            self.additional_information_label.setText(
                "Complete the Line Noise Removal step first."
            )
            self.setActionButtonsEnabled(False)
        else:
            self.clear_status()
            self.additional_information_label.setText(
                f"{len(global_state.line_noise_cleaned_files)} file(s) available for analysis."
            )
            self.setActionButtonsEnabled(True)

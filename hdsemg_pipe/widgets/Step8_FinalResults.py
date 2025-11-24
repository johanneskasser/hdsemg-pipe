"""
Step 8: Final Results

This step converts edited MUEdit files back to JSON format and displays results.
"""
import os
import subprocess
from pathlib import Path
from PyQt5.QtCore import QThread, pyqtSignal
from PyQt5.QtWidgets import QPushButton, QLabel, QVBoxLayout, QFrame, QProgressBar

from hdsemg_pipe._log.log_config import logger
from hdsemg_pipe.state.global_state import global_state
from hdsemg_pipe.widgets.BaseStepWidget import BaseStepWidget
from hdsemg_pipe.actions.decomposition_export import apply_muedit_edits_to_json
from hdsemg_pipe.ui_elements.theme import Styles, Colors, Spacing, BorderRadius, Fonts


class JSONConversionWorker(QThread):
    """Worker thread for converting edited MUEdit files back to JSON."""

    progress = pyqtSignal(int, int, str)  # current, total, message
    finished = pyqtSignal(int, int, list)  # success_count, error_count, error_messages
    error = pyqtSignal(str)

    def __init__(self, edited_files, decomp_folder, results_folder, parent=None):
        super().__init__(parent)
        self.edited_files = edited_files
        self.decomp_folder = decomp_folder
        self.results_folder = results_folder

    def run(self):
        """Run the conversion process."""
        try:
            success_count = 0
            error_count = 0
            error_messages = []

            total = len(self.edited_files)

            for idx, edited_mat in enumerate(self.edited_files):
                try:
                    filename = os.path.basename(edited_mat)
                    self.progress.emit(idx, total, f"Converting {filename}...")

                    # Find original JSON file
                    # edited_mat could be: "file_muedit_edited.mat" or "Group_multigrid_muedit_edited.mat"
                    base_name = filename.replace('_muedit_edited.mat', '').replace('_multigrid_muedit_edited.mat', '')

                    # Try to find corresponding JSON
                    json_candidates = [
                        os.path.join(self.decomp_folder, f"{base_name}.json"),
                        # For multi-grid, we need to find the first JSON file that was in the group
                        # For now, use a simple heuristic: look for any JSON with similar name
                    ]

                    original_json = None
                    for candidate in json_candidates:
                        if os.path.exists(candidate):
                            original_json = candidate
                            break

                    # If not found, try finding any JSON in folder (fallback for multi-grid)
                    if not original_json:
                        json_files = [f for f in os.listdir(self.decomp_folder) if f.endswith('.json')]
                        if json_files:
                            # Use first JSON as reference (multi-grid case)
                            original_json = os.path.join(self.decomp_folder, json_files[0])
                            logger.info(f"Using {json_files[0]} as reference for multi-grid file")

                    if not original_json:
                        raise FileNotFoundError(f"No original JSON found for {filename}")

                    # Output path in results folder
                    output_json = os.path.join(self.results_folder, f"{base_name}_cleaned.json")

                    # Convert
                    apply_muedit_edits_to_json(original_json, edited_mat, output_json)

                    success_count += 1
                    logger.info(f"Successfully converted: {filename}")

                except Exception as e:
                    error_count += 1
                    error_msg = f"Failed to convert {filename}: {str(e)}"
                    error_messages.append(error_msg)
                    logger.error(error_msg)

            self.finished.emit(success_count, error_count, error_messages)

        except Exception as e:
            self.error.emit(f"Conversion worker failed: {str(e)}")


class Step8_FinalResults(BaseStepWidget):
    """
    Step 8: Convert edited files and show final results.

    This step:
    - Converts edited MUEdit files back to JSON
    - Exports to decomposition_results folder
    - Provides button to view results in OpenHD-EMG
    - Completes when all files are converted
    """

    def __init__(self, step_index, step_name, tooltip, parent=None):
        super().__init__(step_index, step_name, tooltip, parent)

        self.decomp_folder = None
        self.results_folder = None
        self.edited_files = []
        self.exported_files = []
        self.conversion_worker = None

        # Create status UI
        self.create_status_ui()
        self.col_additional.addWidget(self.status_container)

        # Perform initial check
        self.check()

    def create_status_ui(self):
        """Create compact status UI."""
        self.status_container = QFrame()
        status_layout = QVBoxLayout(self.status_container)
        status_layout.setSpacing(Spacing.SM)
        status_layout.setContentsMargins(0, 0, 0, 0)

        # Status label
        self.status_label = QLabel("")
        self.status_label.setWordWrap(True)
        self.status_label.setStyleSheet(f"""
            QLabel {{
                color: {Colors.TEXT_SECONDARY};
                font-size: {Fonts.SIZE_SM};
                padding: {Spacing.SM}px;
            }}
        """)
        status_layout.addWidget(self.status_label)

        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setStyleSheet(f"""
            QProgressBar {{
                border: 1px solid {Colors.BORDER_DEFAULT};
                border-radius: {BorderRadius.SM};
                text-align: center;
                height: 24px;
                background-color: {Colors.BG_SECONDARY};
            }}
            QProgressBar::chunk {{
                background-color: {Colors.GREEN_600};
                border-radius: {BorderRadius.SM};
            }}
        """)
        self.progress_bar.setVisible(False)
        status_layout.addWidget(self.progress_bar)

    def create_buttons(self):
        """Create buttons for this step."""
        self.btn_convert = QPushButton("Convert to JSON")
        self.btn_convert.setStyleSheet(Styles.button_primary())
        self.btn_convert.setToolTip("Convert edited MUEdit files to JSON format")
        self.btn_convert.clicked.connect(self.start_conversion)
        self.btn_convert.setEnabled(False)
        self.buttons.append(self.btn_convert)

        self.btn_show_results = QPushButton("Show Decomposition Results")
        self.btn_show_results.setStyleSheet(Styles.button_primary())
        self.btn_show_results.setToolTip("View cleaned results in OpenHD-EMG")
        self.btn_show_results.clicked.connect(self.display_results)
        self.btn_show_results.setEnabled(False)
        self.buttons.append(self.btn_show_results)

    def check(self):
        """Check if this step can be activated."""
        workfolder = global_state.workfolder
        if not workfolder:
            return False

        self.decomp_folder = global_state.get_decomposition_path()
        self.results_folder = global_state.get_decomposition_results_path()

        # Create results folder if needed
        if not os.path.exists(self.results_folder):
            os.makedirs(self.results_folder)
            logger.info(f"Created results folder: {self.results_folder}")

        # Always scan for edited files to show status, even if step is not yet activated
        self.scan_files()

        # Check if previous step is completed
        if not self.is_previous_step_completed():
            return False

        return True

    def scan_files(self):
        """Scan for edited MUEdit files and exported JSON files."""
        if not os.path.exists(self.decomp_folder):
            return

        # Find edited MUEdit files
        self.edited_files = []
        for file in os.listdir(self.decomp_folder):
            if file.endswith('_muedit_edited.mat') or file.endswith('_multigrid_muedit_edited.mat'):
                full_path = os.path.join(self.decomp_folder, file)
                self.edited_files.append(full_path)

        # Find exported JSON files in results folder
        self.exported_files = []
        if os.path.exists(self.results_folder):
            self.exported_files = [
                os.path.join(self.results_folder, f)
                for f in os.listdir(self.results_folder)
                if f.endswith('.json')
            ]

        # Update UI
        if self.edited_files:
            self.status_label.setText(f"Found {len(self.edited_files)} edited file(s) ready for conversion")
            self.btn_convert.setEnabled(True)
        else:
            self.status_label.setText("Waiting for edited MUEdit files...")
            self.btn_convert.setEnabled(False)

        if self.exported_files:
            self.btn_show_results.setEnabled(True)

    def start_conversion(self):
        """Start the conversion process."""
        if not self.edited_files:
            self.warn("No edited files to convert.")
            return

        # Disable buttons during conversion
        self.btn_convert.setEnabled(False)
        self.btn_show_results.setEnabled(False)

        # Show progress bar
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        self.progress_bar.setMaximum(len(self.edited_files))

        # Start worker
        self.conversion_worker = JSONConversionWorker(
            self.edited_files,
            self.decomp_folder,
            self.results_folder
        )
        self.conversion_worker.progress.connect(self.on_conversion_progress)
        self.conversion_worker.finished.connect(self.on_conversion_finished)
        self.conversion_worker.error.connect(self.on_conversion_error)
        self.conversion_worker.start()

        logger.info(f"Starting conversion of {len(self.edited_files)} file(s)...")

    def on_conversion_progress(self, current, total, message):
        """Handle conversion progress updates."""
        self.progress_bar.setValue(current)
        self.status_label.setText(message)

    def on_conversion_finished(self, success_count, error_count, error_messages):
        """Handle conversion completion."""
        self.progress_bar.setVisible(False)

        # Re-enable buttons
        self.btn_convert.setEnabled(True)

        # Rescan files
        self.scan_files()

        # Show summary
        if success_count > 0 and error_count == 0:
            self.success(f"Successfully converted {success_count} file(s) to JSON format!")
            self.status_label.setText(f"✓ Conversion complete: {success_count} file(s) in results folder")

            # Mark step as completed
            self.complete_step()

        elif success_count > 0 and error_count > 0:
            self.warn(f"Converted {success_count} file(s), but {error_count} failed:\n" + "\n".join(error_messages))
        else:
            self.error(f"Conversion failed:\n" + "\n".join(error_messages))

    def on_conversion_error(self, error_msg):
        """Handle conversion worker error."""
        self.progress_bar.setVisible(False)
        self.btn_convert.setEnabled(True)
        self.error(f"Conversion failed: {error_msg}")

    def display_results(self):
        """Display cleaned results in OpenHD-EMG."""
        if not os.path.exists(self.results_folder) or not self.exported_files:
            self.warn("No results found to display.")
            return

        try:
            import openhdemg.gui as gui

            logger.info(f"Opening OpenHD-EMG GUI with results from: {self.results_folder}")

            # Find first JSON file to open
            first_json = self.exported_files[0]

            # Launch OpenHD-EMG GUI
            gui.openhdemg_gui(str(first_json))

            self.success("OpenHD-EMG GUI opened successfully!")

        except ImportError:
            self.error(
                "OpenHD-EMG GUI not available.\n\n"
                "Please install: pip install openhdemg\n\n"
                f"Results are saved in: {self.results_folder}"
            )
        except Exception as e:
            self.error(f"Failed to launch OpenHD-EMG GUI: {str(e)}\n\nResults are saved in: {self.results_folder}")

    def is_completed(self):
        """Check if this step is completed."""
        # Step is completed when JSON files exist in results folder
        return len(self.exported_files) > 0

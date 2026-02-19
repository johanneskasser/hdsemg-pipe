"""
Step 12: Final Results (Wizard Version)

This step converts edited MUEdit files back to JSON format and displays results.
"""
import os
import subprocess
from pathlib import Path
from PyQt5.QtCore import QThread, pyqtSignal
from PyQt5.QtWidgets import QPushButton, QLabel, QVBoxLayout, QFrame, QProgressBar

from hdsemg_pipe._log.log_config import logger
from hdsemg_pipe.state.global_state import global_state
from hdsemg_pipe.widgets.WizardStepWidget import WizardStepWidget
from hdsemg_pipe.actions.decomposition_export import (
    apply_muedit_edits_to_json,
    apply_muedit_edits_multigrid_to_json
)
from hdsemg_pipe.ui_elements.theme import Styles, Colors, Spacing, BorderRadius, Fonts
import json


class JSONConversionWorker(QThread):
    """Worker thread for converting edited MUEdit files back to JSON."""

    progress = pyqtSignal(int, int, str)  # current, total, message
    finished = pyqtSignal(int, int, list)  # success_count, error_count, error_messages
    error = pyqtSignal(str)

    def __init__(self, edited_files, decomp_folder, json_source_folder, results_folder,
                 multigrid_groupings=None, parent=None):
        super().__init__(parent)
        self.edited_files = edited_files
        self.decomp_folder = decomp_folder  # decomposition_auto/ (for state files)
        self.json_source_folder = json_source_folder  # where source JSONs live (covisi_filtered or auto)
        self.results_folder = results_folder
        self.multigrid_groupings = multigrid_groupings or {}  # group_name -> [json_filenames]

    def _resolve_json_path(self, json_filename):
        """Resolve the actual path for a JSON filename, checking both covisi_filtered and auto folders."""
        stem = Path(json_filename).stem

        # Try covisi_filtered version first
        covisi_path = os.path.join(self.json_source_folder, f"{stem}_covisi_filtered.json")
        if os.path.exists(covisi_path):
            return covisi_path

        # Try with .json extension
        json_path = os.path.join(self.json_source_folder, json_filename)
        if os.path.exists(json_path):
            return json_path

        # Try in decomp_auto folder as fallback
        auto_path = os.path.join(self.decomp_folder, json_filename)
        if os.path.exists(auto_path):
            return auto_path

        return None

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

                    # Check if this is a multi-grid file
                    is_multigrid = '_multigrid_muedit.mat' in filename

                    if is_multigrid:
                        # Extract group name from filename (e.g., "GroupName_multigrid_muedit.mat_edited.mat")
                        group_name = filename.replace('_multigrid_muedit.mat_edited.mat', '')

                        # Find the original JSON file paths for this group
                        if group_name not in self.multigrid_groupings:
                            # Try to find a matching group by sanitizing the name
                            found_group = None
                            for grp_name in self.multigrid_groupings.keys():
                                safe_grp_name = "".join(c for c in grp_name if c.isalnum() or c in (' ', '_', '-')).strip()
                                safe_grp_name = safe_grp_name.replace(' ', '_')
                                if safe_grp_name == group_name:
                                    found_group = grp_name
                                    break

                            if found_group:
                                group_name = found_group
                            else:
                                raise ValueError(
                                    f"Multi-grid group '{group_name}' not found in groupings. "
                                    f"Available groups: {list(self.multigrid_groupings.keys())}"
                                )

                        json_filenames = self.multigrid_groupings[group_name]
                        logger.info(f"Converting multi-grid file '{filename}' from {len(json_filenames)} source JSONs")

                        # Resolve all JSON paths
                        json_paths = []
                        for json_fn in json_filenames:
                            resolved_path = self._resolve_json_path(json_fn)
                            if not resolved_path:
                                raise FileNotFoundError(f"Could not find JSON file: {json_fn}")
                            json_paths.append(resolved_path)

                        # Output: consolidated JSON file
                        output_json = os.path.join(self.results_folder, f"{group_name}_multigrid_cleaned.json")

                        # Convert multi-grid to consolidated JSON
                        apply_muedit_edits_multigrid_to_json(json_paths, edited_mat, output_json)

                        success_count += 1
                        logger.info(f"Successfully converted multi-grid file: {filename} → {os.path.basename(output_json)}")

                    else:
                        # Single-grid file conversion (original logic)
                        # Find original JSON file
                        # edited_mat is like: "file_muedit.mat_edited.mat" or "file_covisi_filtered_muedit.mat_edited.mat"
                        # Remove the "_edited.mat" suffix to get the original MAT filename
                        base_name = filename.replace('.mat_edited.mat', '')

                        # Then remove the MUEdit suffix to get the base name for JSON lookup
                        base_name = base_name.replace('_muedit', '')

                        # Try to find corresponding JSON in source folder
                        # If CoVISI was applied: look for *_covisi_filtered.json
                        # Otherwise: look for *.json
                        json_candidates = []

                        # Check if this file came from CoVISI filtering (has _covisi_filtered in name)
                        if '_covisi_filtered' in base_name:
                            # Look for the covisi_filtered JSON
                            json_candidates.append(os.path.join(self.json_source_folder, f"{base_name}.json"))
                        else:
                            # Look for the original JSON
                            json_candidates.append(os.path.join(self.json_source_folder, f"{base_name}.json"))

                        original_json = None
                        for candidate in json_candidates:
                            if os.path.exists(candidate):
                                original_json = candidate
                                break

                        if not original_json:
                            raise FileNotFoundError(
                                f"No original JSON found for {filename}. "
                                f"Searched in: {self.json_source_folder}"
                            )

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


class NotebookExportWorker(QThread):
    """Worker thread for exporting analysis notebook."""

    finished = pyqtSignal(dict)
    error = pyqtSignal(str)

    def __init__(self, workfolder, parent=None):
        super().__init__(parent)
        self.workfolder = workfolder

    def run(self):
        """Run the notebook export process."""
        from hdsemg_pipe.actions.notebook_export import export_analysis_notebook
        try:
            result = export_analysis_notebook(self.workfolder)
            if 'error' in result:
                self.error.emit(result['error'])
            else:
                self.finished.emit(result)
        except Exception as e:
            self.error.emit(f"Notebook export failed: {str(e)}")


class FinalResultsWizardWidget(WizardStepWidget):
    """
    Step 12: Convert edited files and show final results.

    This step:
    - Converts edited MUEdit files back to JSON
    - Exports to decomposition_results folder
    - Provides button to view results in openhdemg
    - Completes when all files are converted
    """

    def __init__(self, parent=None):
        # Hardcoded step configuration
        step_index = 13
        step_name = "Final Results"
        description = "Convert edited MUEdit files back to JSON format and view cleaned results in openhdemg."

        super().__init__(step_index, step_name, description, parent)

        self.decomp_folder = None  # decomposition_auto/ (for state files)
        self.json_source_folder = None  # where source JSONs live (covisi_filtered or auto)
        self.results_folder = None
        self.edited_files = []
        self.exported_files = []
        self.conversion_worker = None
        self.notebook_worker = None
        self.multigrid_groupings = {}  # group_name -> [json_filenames]

        # Create status UI
        self.create_status_ui()
        self.content_layout.addWidget(self.status_container)

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
        self.btn_show_results.setToolTip("View cleaned results in openhdemg")
        self.btn_show_results.clicked.connect(self.display_results)
        self.btn_show_results.setEnabled(False)
        self.buttons.append(self.btn_show_results)

        self.btn_export_notebook = QPushButton("Export Analysis Notebook")
        self.btn_export_notebook.setStyleSheet(Styles.button_secondary())
        self.btn_export_notebook.setToolTip("Export Jupyter notebook for custom analysis")
        self.btn_export_notebook.clicked.connect(self.start_notebook_export)
        self.btn_export_notebook.setEnabled(False)
        self.buttons.append(self.btn_export_notebook)

    def check(self):
        """Check if this step can be activated."""
        workfolder = global_state.workfolder
        if not workfolder:
            return False

        self.decomp_folder = global_state.get_decomposition_path()  # decomposition_auto/
        self._update_json_source_folder()
        self.results_folder = global_state.get_decomposition_results_path()

        # Load multi-grid groupings (needed for converting multi-grid files back to JSON)
        self._load_multigrid_groupings()

        # Create results folder if needed
        if not os.path.exists(self.results_folder):
            os.makedirs(self.results_folder)
            logger.info(f"Created results folder: {self.results_folder}")

        # Always scan for edited files to show status, even if step is not yet activated
        self.scan_files()

        # Check if previous step is completed
        if not global_state.is_widget_completed(f"step{self.step_index - 1}"):
            return False

        return True

    def _update_json_source_folder(self):
        """Determine whether to read JSONs from covisi_filtered or decomposition_auto."""
        covisi_folder = global_state.get_decomposition_covisi_filtered_path()

        # Primary check: step state
        covisi_applied_by_state = (
            global_state.is_widget_completed("step9")
            and not global_state.is_widget_skipped("step9")
        )

        # Fallback check: physical folder evidence.
        # Handles backwards-compat workfolders where step9 wasn't recorded in the
        # process log (e.g. CoVISI was run before process-log support or the log
        # entry was lost during a reconstruction cycle).
        covisi_applied_by_folder = os.path.exists(covisi_folder) and any(
            f.endswith('_covisi_filtered.json') for f in os.listdir(covisi_folder)
        )

        if (covisi_applied_by_state or covisi_applied_by_folder) and os.path.exists(covisi_folder):
            self.json_source_folder = covisi_folder
        else:
            self.json_source_folder = self.decomp_folder

    def _load_multigrid_groupings(self):
        """Load multi-grid groupings from JSON file."""
        groupings_file = os.path.join(self.decomp_folder, "multigrid_groupings.json")

        if not os.path.exists(groupings_file):
            self.multigrid_groupings = {}
            return

        try:
            with open(groupings_file, 'r') as f:
                self.multigrid_groupings = json.load(f)
            logger.info(f"Loaded {len(self.multigrid_groupings)} multi-grid group(s) from state file")
        except Exception as e:
            logger.warning(f"Could not load multi-grid groupings: {e}")
            self.multigrid_groupings = {}

    def scan_files(self):
        """Scan for edited MUEdit files and exported JSON files."""
        if not os.path.exists(self.decomp_folder):
            return

        # Find edited MUEdit files from both decomposition_auto and decomposition_multigrid
        # MUEdit creates files by appending "_edited.mat" to the entire filename
        # e.g., "file_muedit.mat" -> "file_muedit.mat_edited.mat"
        edited_from_decomp = [
            os.path.join(self.decomp_folder, file)
            for file in os.listdir(self.decomp_folder)
            if file.endswith('.mat_edited.mat')
        ] if os.path.exists(self.decomp_folder) else []

        multigrid_folder = global_state.get_decomposition_multigrid_path()
        edited_from_multigrid = [
            os.path.join(multigrid_folder, file)
            for file in os.listdir(multigrid_folder)
            if file.endswith('.mat_edited.mat')
        ] if os.path.exists(multigrid_folder) else []

        self.edited_files = edited_from_decomp + edited_from_multigrid

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
            self.btn_export_notebook.setEnabled(True)

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
            self.json_source_folder,
            self.results_folder,
            multigrid_groupings=self.multigrid_groupings
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
        """Display cleaned results in openhdemg."""
        if not os.path.exists(self.results_folder) or not self.exported_files:
            self.warn("No results found to display.")
            return

        try:
            import openhdemg.gui as gui

            logger.info(f"Opening openhdemg GUI with results from: {self.results_folder}")

            # Find first JSON file to open
            first_json = self.exported_files[0]

            # Launch openhdemg GUI
            gui.openhdemg_gui(str(first_json))

            self.success("openhdemg GUI opened successfully!")

        except ImportError:
            self.error(
                "openhdemg GUI not available.\n\n"
                "Please install: pip install openhdemg\n\n"
                f"Results are saved in: {self.results_folder}"
            )
        except Exception as e:
            self.error(f"Failed to launch openhdemg GUI: {str(e)}\n\nResults are saved in: {self.results_folder}")

    def start_notebook_export(self):
        """Start notebook export in background thread."""
        try:
            import nbformat
        except ImportError:
            self.error(
                "Jupyter notebook export requires 'nbformat' library.\n\n"
                "Install with: pip install nbformat"
            )
            return

        if not self.exported_files:
            self.warn("No cleaned JSON files available. Please convert files first.")
            return

        # Disable button during export
        self.btn_export_notebook.setEnabled(False)
        self.status_label.setText("Generating analysis notebook...")

        # Start worker
        self.notebook_worker = NotebookExportWorker(global_state.workfolder)
        self.notebook_worker.finished.connect(self.on_notebook_export_finished)
        self.notebook_worker.error.connect(self.on_notebook_export_error)
        self.notebook_worker.start()

        logger.info("Starting notebook export...")

    def on_notebook_export_finished(self, result):
        """Handle notebook export completion."""
        self.btn_export_notebook.setEnabled(True)
        self.status_label.setText("")

        helper_path = result.get('helper_path', '')
        notebook_path = result.get('notebook_path', '')

        self.success(
            f"Analysis notebook exported successfully!\n\n"
            f"Files created:\n"
            f"  - {Path(helper_path).name}\n"
            f"  - {Path(notebook_path).name}\n\n"
            f"Open the notebook in Jupyter to begin analysis."
        )

        logger.info(f"Notebook exported: {notebook_path}")

    def on_notebook_export_error(self, error_msg):
        """Handle notebook export error."""
        self.btn_export_notebook.setEnabled(True)
        self.status_label.setText("")
        self.error(f"Notebook export failed:\n{error_msg}")
        logger.error(f"Notebook export error: {error_msg}")

    def is_completed(self):
        """Check if this step is completed."""
        # Step is completed when JSON files exist in results folder
        return len(self.exported_files) > 0

    def init_file_checking(self):
        """Initialize file checking for state reconstruction."""
        self.decomp_folder = global_state.get_decomposition_path()
        self._update_json_source_folder()
        self._load_multigrid_groupings()
        self.results_folder = global_state.get_decomposition_results_path()

        # Create results folder if needed
        if not os.path.exists(self.results_folder):
            os.makedirs(self.results_folder)
            logger.info(f"Created results folder: {self.results_folder}")

        # Scan for files
        self.scan_files()
        logger.info(f"File checking initialized for folders: {self.json_source_folder}, {self.results_folder}")

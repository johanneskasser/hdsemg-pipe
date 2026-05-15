import json
import os
from dataclasses import dataclass, field

from PyQt5.QtCore import QTimer, QThread, pyqtSignal
from PyQt5.QtWidgets import QFileDialog, QMessageBox

from hdsemg_pipe._log.log_config import logger
from hdsemg_pipe.actions.enum.FolderNames import FolderNames, FOLDER_NAME_MIGRATIONS
from hdsemg_pipe.actions.file_manager import get_channel_selection_status
from hdsemg_pipe.actions.process_log import read_process_log
from hdsemg_pipe.actions.skip_marker import check_skip_marker
from hdsemg_pipe.config.config_enums import Settings
from hdsemg_pipe.config.config_manager import config
from hdsemg_pipe.state.global_state import global_state
from hdsemg_pipe.ui_elements.loading_overlay import LoadingOverlay


# ---------------------------------------------------------------------------
# Data container produced by the background worker
# ---------------------------------------------------------------------------

@dataclass
class ReconstructionData:
    """Plain-Python snapshot of what the worker found on disk.

    No Qt objects — safe to emit across threads.
    """
    folderpath: str

    # Step 1
    original_files: list = field(default_factory=list)

    # Step 2
    associated_files: list = field(default_factory=list)
    associated_skip: bool = False

    # Step 3
    line_noise_files: list = field(default_factory=list)
    line_noise_skip: bool = False

    # Step 4 (True = folder exists and has content or a skip marker)
    analysis_valid: bool = False
    analysis_skip: bool = False

    # Step 5 (None = step not done / skip; list = selected files)
    file_quality_selected: list | None = None

    # Step 6
    cropped_files: list = field(default_factory=list)
    cropped_skip: bool = False

    # Step 7
    channel_selection_files: list = field(default_factory=list)
    channel_n_done: int = 0
    channel_n_total: int = 0

    # Step 9
    covisi_has_filtered: bool = False
    mu_quality_manifest: dict | None = None

    # Process log (used by _apply_process_log_overrides)
    process_log: dict = field(default_factory=dict)

    # Per-step error messages; key = "step2" … "step9"
    step_errors: dict = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Background worker
# ---------------------------------------------------------------------------

class ReconstructionWorker(QThread):
    """Runs all file-I/O reconstruction in a background thread."""

    finished = pyqtSignal(object)   # ReconstructionData
    error = pyqtSignal(str)

    def __init__(self, folderpath: str) -> None:
        super().__init__()
        self.folderpath = folderpath

    def run(self) -> None:
        try:
            data = _collect_reconstruction_data(self.folderpath)
            self.finished.emit(data)
        except Exception as exc:
            self.error.emit(str(exc))


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def start_reconstruction_workflow(parent) -> None:
    workfolder_path = config.get(Settings.WORKFOLDER_PATH)
    if workfolder_path is None:
        workfolder_path = os.getcwd()

    if global_state.workfolder is not None:
        QMessageBox.warning(parent, "Error", "A pipeline folder is already selected.")
        return

    selected_folder = QFileDialog.getExistingDirectory(
        parent, "Select existing pipeline folder", directory=workfolder_path
    )
    if not selected_folder:
        return

    main_window = _find_main_window(parent)
    overlay_parent = main_window.centralWidget() if main_window else parent
    overlay = LoadingOverlay.show_over(overlay_parent)

    worker = ReconstructionWorker(selected_folder)

    def on_finished(data: ReconstructionData) -> None:
        try:
            next_step = _apply_reconstruction_plan(data)

            # Show success dialog (fast — user dismissal is the only delay here)
            _show_restore_success(data.folderpath).exec_()

            if main_window and hasattr(main_window, "navigateToStep"):
                logger.info(f"Navigating to step {next_step} after reconstruction")
                main_window.navigateToStep(next_step)
            else:
                logger.warning("Could not find main window with navigateToStep method")
        except Exception as exc:
            global_state.reset()
            logger.warning(f"Failed to apply reconstruction plan: {exc}")
            QMessageBox.warning(parent, "Error", f"Failed to reconstruct folder state:\n{exc}")
        finally:
            overlay.hide()
            worker.deleteLater()

        # Defer the folder-tree refresh so it runs after the overlay is hidden
        # and the event loop has processed the navigation.  The call may be slow
        # on network-mounted workfolders; deferring keeps the UI responsive.
        folder_content_widget = global_state.get_widget("folder_content")
        if folder_content_widget:
            QTimer.singleShot(0, folder_content_widget.update_folder_content)

    def on_error(msg: str) -> None:
        global_state.reset()
        logger.warning(f"Reconstruction worker error: {msg}")
        overlay.hide()
        QMessageBox.warning(parent, "Error", f"Failed to reconstruct folder state:\n{msg}")
        worker.deleteLater()

    worker.finished.connect(on_finished)
    worker.error.connect(on_error)
    worker.start()


# ---------------------------------------------------------------------------
# Phase 1: collect data in background thread (no Qt / widget calls)
# ---------------------------------------------------------------------------

def _collect_reconstruction_data(folderpath: str) -> ReconstructionData:
    data = ReconstructionData(folderpath=folderpath)

    # These raise on hard failures — propagated to ReconstructionWorker.error
    _check_folder_existence(folderpath)
    _migrate_old_folder_names(folderpath)
    _check_pipe_folder_structure(folderpath)

    # --- Step 1: original files (mandatory) ---
    orig_path = os.path.join(folderpath, str(FolderNames.ORIGINAL_FILES.value))
    for f in os.listdir(orig_path):
        if f.endswith(".mat"):
            data.original_files.append(os.path.join(orig_path, f))
    if not data.original_files:
        raise FileNotFoundError(f"No original files found in: {orig_path}")

    # --- Step 2: associated grid files ---
    try:
        assoc_path = os.path.join(folderpath, str(FolderNames.ASSOCIATED_GRIDS.value))
        for f in os.listdir(assoc_path):
            if f.endswith(".mat"):
                data.associated_files.append(os.path.join(assoc_path, f))
        if not data.associated_files:
            raise FileNotFoundError(f"No associated grid files found in: {assoc_path}")
        data.associated_skip = check_skip_marker(assoc_path)
    except FileNotFoundError as exc:
        data.step_errors["step2"] = str(exc)

    # --- Step 3: line noise cleaned files ---
    try:
        lnc_path = os.path.join(folderpath, str(FolderNames.LINE_NOISE_CLEANED.value))
        for f in os.listdir(lnc_path):
            if f.endswith(".mat"):
                data.line_noise_files.append(os.path.join(lnc_path, f))
        if not data.line_noise_files:
            raise FileNotFoundError(f"No line noise cleaned files found in: {lnc_path}")
        data.line_noise_skip = check_skip_marker(lnc_path)
    except FileNotFoundError as exc:
        data.step_errors["step3"] = str(exc)

    # --- Step 4: analysis files ---
    try:
        analysis_path = os.path.join(folderpath, str(FolderNames.ANALYSIS.value))
        if not os.path.exists(analysis_path):
            raise FileNotFoundError(f"Analysis folder not found: {analysis_path}")
        files = os.listdir(analysis_path)
        data.analysis_skip = check_skip_marker(analysis_path)
        has_output = any(f.endswith((".png", ".csv", ".txt")) for f in files)
        if not data.analysis_skip and not has_output:
            raise FileNotFoundError(f"No analysis output files found in: {analysis_path}")
        data.analysis_valid = True
    except FileNotFoundError as exc:
        data.step_errors["step4"] = str(exc)

    # --- Step 5: file quality selection ---
    try:
        analysis_path = os.path.join(folderpath, str(FolderNames.ANALYSIS.value))
        sel_path = os.path.join(analysis_path, "file_quality_selection.json")
        if os.path.exists(sel_path):
            with open(sel_path, "r") as fh:
                sel_data = json.load(fh)
            selected = sel_data.get("selected", [])
            if selected:
                data.file_quality_selected = selected
        # No file or empty list → file_quality_selected stays None → mark as skipped later
    except Exception as exc:
        data.step_errors["step5"] = str(exc)

    # --- Step 6: ROI (cropped) files ---
    try:
        roi_path = os.path.join(folderpath, str(FolderNames.CROPPED_SIGNAL.value))
        for f in os.listdir(roi_path):
            if f.endswith(".mat"):
                data.cropped_files.append(os.path.join(roi_path, f))
        if not data.cropped_files:
            raise FileNotFoundError(f"No ROI files found in: {roi_path}")
        data.cropped_skip = check_skip_marker(roi_path)
    except FileNotFoundError as exc:
        data.step_errors["step6"] = str(exc)

    # --- Step 7: channel selection ---
    try:
        chan_dir = os.path.join(folderpath, str(FolderNames.CHANNELSELECTION.value))
        if os.path.isdir(chan_dir):
            for f in os.listdir(chan_dir):
                if f.endswith(".mat") and not os.path.isdir(os.path.join(chan_dir, f)):
                    data.channel_selection_files.append(os.path.join(chan_dir, f))

        if not data.channel_selection_files:
            discarded_dir = os.path.join(chan_dir, "discarded")
            n_discarded = 0
            if os.path.isdir(discarded_dir):
                n_discarded = sum(
                    1 for f in os.listdir(discarded_dir)
                    if not os.path.isdir(os.path.join(discarded_dir, f))
                )
            if n_discarded == 0:
                raise FileNotFoundError(f"No channel selection files found in: {chan_dir}")

        status = get_channel_selection_status(data.cropped_files, chan_dir)
        data.channel_n_done = status["n_done"]
        data.channel_n_total = status["n_total"]
    except FileNotFoundError as exc:
        data.step_errors["step7"] = str(exc)

    # --- Step 9: MU Quality Review ---
    try:
        filtered_dir = os.path.join(folderpath, FolderNames.DECOMPOSITION_COVISI_FILTERED.value)
        if os.path.isdir(filtered_dir) and os.listdir(filtered_dir):
            data.covisi_has_filtered = True
            analysis_path = os.path.join(folderpath, str(FolderNames.ANALYSIS.value))
            manifest_path = os.path.join(analysis_path, "mu_quality_selection.json")
            if os.path.exists(manifest_path):
                with open(manifest_path, "r", encoding="utf-8") as fh:
                    data.mu_quality_manifest = json.load(fh)
    except Exception as exc:
        data.step_errors["step9"] = str(exc)

    # --- Process log ---
    log = read_process_log(folderpath)
    data.process_log = log

    return data


# ---------------------------------------------------------------------------
# Phase 2: apply collected data on the main thread
# ---------------------------------------------------------------------------

def _apply_reconstruction_plan(data: ReconstructionData) -> int:
    logger.info(f"Reconstructing folder state for: {data.folderpath}")
    global_state.reset()
    global_state.workfolder = data.folderpath

    # Step 1 — mandatory
    for f in data.original_files:
        global_state.add_original_file(f)

    widget1 = global_state.get_widget("step1")
    if not widget1:
        raise ValueError("Original files widget not found in global state.")
    widget1.check()
    logger.info("Step 1 state reconstructed: Original files loaded")
    global_state.complete_widget("step1")
    widget1.fileSelected.emit(data.folderpath)

    # Step 2
    if "step2" not in data.step_errors:
        for f in data.associated_files:
            global_state.associated_files.append(f)
        widget2 = global_state.get_widget("step2")
        if widget2:
            widget2.check()
            if data.associated_skip:
                logger.info("Step 2 state reconstructed: Grid association skipped")
                global_state.skip_widget("step2")
            else:
                logger.info("Step 2 state reconstructed: Grid association completed")
                global_state.complete_widget("step2")
        else:
            data.step_errors["step2"] = "Widget not found"

    if "step2" in data.step_errors:
        logger.info(f"Skipping grid association reconstruction: {data.step_errors['step2']}")
        global_state.skip_widget("step2")

    # Step 3
    if "step3" not in data.step_errors:
        for f in data.line_noise_files:
            global_state.line_noise_cleaned_files.append(f)
        widget3 = global_state.get_widget("step3")
        if widget3:
            widget3.check()
            if data.line_noise_skip:
                logger.info("Step 3 state reconstructed: Line noise removal skipped")
                global_state.skip_widget("step3")
            else:
                logger.info("Step 3 state reconstructed: Line noise removal completed")
                global_state.complete_widget("step3")
        else:
            data.step_errors["step3"] = "Widget not found"

    if "step3" in data.step_errors:
        logger.info(f"Skipping line noise cleaned reconstruction: {data.step_errors['step3']}")
        global_state.skip_widget("step3")

    # Step 4
    if "step4" not in data.step_errors:
        widget4 = global_state.get_widget("step4")
        if widget4:
            widget4.check()
            if data.analysis_skip:
                logger.info("Step 4 state reconstructed: RMS quality analysis skipped")
                global_state.skip_widget("step4")
            else:
                logger.info("Step 4 state reconstructed: RMS quality analysis completed")
                global_state.complete_widget("step4")
        else:
            data.step_errors["step4"] = "Widget not found"

    if "step4" in data.step_errors:
        logger.info(f"Skipping RMS analysis reconstruction: {data.step_errors['step4']}")
        global_state.skip_widget("step4")

    # Step 5
    try:
        widget5 = global_state.get_widget("step5")
        if not widget5:
            raise ValueError("File quality selection widget not found in global state.")
        if "step5" not in data.step_errors and data.file_quality_selected is not None:
            global_state.line_noise_cleaned_files = data.file_quality_selected
            logger.info(f"Step 5 state reconstructed: {len(data.file_quality_selected)} files selected")
            global_state.complete_widget("step5")
        else:
            logger.info("Step 5: no selection file found — marking as skipped")
            global_state.skip_widget("step5")
    except Exception as exc:
        logger.info(f"Skipping file quality selection reconstruction: {exc}")
        global_state.skip_widget("step5")

    # Step 6
    if "step6" not in data.step_errors:
        for f in data.cropped_files:
            global_state.cropped_files.append(f)
        widget6 = global_state.get_widget("step6")
        if widget6:
            widget6.check()
            if data.cropped_skip:
                logger.info("Step 6 state reconstructed: ROI cropping skipped")
                global_state.skip_widget("step6")
            else:
                logger.info("Step 6 state reconstructed: ROI cropping completed")
                global_state.complete_widget("step6")
        else:
            data.step_errors["step6"] = "Widget not found"

    if "step6" in data.step_errors:
        logger.info(f"Skipping ROI reconstruction: {data.step_errors['step6']}")
        global_state.skip_widget("step6")

    # Step 7
    if "step7" not in data.step_errors:
        for f in data.channel_selection_files:
            global_state.channel_selection_files.append(f)
        widget7 = global_state.get_widget("step7")
        if widget7:
            widget7.check()
            if data.channel_n_total > 0 and data.channel_n_done >= data.channel_n_total:
                logger.info("Step 7 state reconstructed: Channel selection fully completed")
                global_state.complete_widget("step7")
            else:
                logger.info(
                    f"Step 7 state reconstructed: {data.channel_n_done}/{data.channel_n_total} "
                    "files done – step pending (resume available)"
                )
        else:
            data.step_errors["step7"] = "Widget not found"

    if "step7" in data.step_errors:
        logger.info(f"Skipping channel selection reconstruction: {data.step_errors['step7']}")
        global_state.skip_widget("step7")

    # Steps 8–13: widget-driven (init_file_checking), fast on main thread
    try:
        _decomposition_results_init()
    except Exception as exc:
        logger.info(f"Skipping decomposition results reconstruction: {exc}")
        global_state.skip_widget("step8")

    try:
        _mu_quality_review_from_data(data)
    except Exception as exc:
        logger.info(f"Skipping MU Quality Review reconstruction: {exc}")
        global_state.skip_widget("step9")

    try:
        _multigrid_config()
    except Exception as exc:
        logger.info(f"Skipping multi-grid configuration reconstruction: {exc}")
        global_state.skip_widget("step10")

    try:
        _muedit_cleaning()
    except Exception as exc:
        logger.info(f"Skipping MUEdit cleaning reconstruction: {exc}")

    try:
        _covisi_post_validation()
    except Exception as exc:
        logger.info(f"Skipping CoVISI post-validation reconstruction: {exc}")
        global_state.skip_widget("step12")

    try:
        _final_results()
    except Exception as exc:
        logger.info(f"Skipping final results reconstruction: {exc}")

    _apply_process_log_overrides(data.folderpath)

    # Log step completion status
    logger.info("=" * 50)
    logger.info("Step completion status after reconstruction:")
    for step_num in range(1, 14):
        step_name = f"step{step_num}"
        is_completed = global_state.is_widget_completed(step_name)
        is_skipped = global_state.is_widget_skipped(step_name)
        status = "✓ Completed" if is_completed and not is_skipped else "⏭ Skipped" if is_skipped else "○ Pending"
        logger.info(f"  Step {step_num:2d}: {status}")
    logger.info("=" * 50)

    # Refresh progress indicator (fast — pure UI, no I/O)
    parent_widget = global_state.get_widget("step1")
    if parent_widget and hasattr(parent_widget, "parent") and parent_widget.parent():
        main_window = parent_widget.parent()
        while main_window and not hasattr(main_window, "progress_indicator"):
            main_window = main_window.parent()
        if main_window and hasattr(main_window, "progress_indicator"):
            main_window.progress_indicator.refreshStates()
            logger.info("Progress indicator refreshed after reconstruction")

    return _get_next_incomplete_step()


# ---------------------------------------------------------------------------
# Step-level helpers (widget-driven, main thread only)
# ---------------------------------------------------------------------------

def _decomposition_results_init() -> None:
    decomposition_widget = global_state.get_widget("step8")
    if decomposition_widget:
        decomposition_widget.init_file_checking()
        if decomposition_widget.decomp_mapping is not None and decomposition_widget.resultfiles:
            logger.info("Step 8 state reconstructed: mapping loaded and files found")
            global_state.complete_widget("step8")
    else:
        logger.warning("decomposition widget not found in global state.")
        raise ValueError("decomposition widget not found in global state.")


def _mu_quality_review_from_data(data: ReconstructionData) -> None:
    if not data.covisi_has_filtered:
        return

    widget = global_state.get_widget("step9")
    if data.mu_quality_manifest is not None and widget is not None:
        try:
            widget.restore_from_manifest(data.mu_quality_manifest)
        except Exception as exc:
            logger.warning("Could not restore mu_quality_selection.json: %s", exc)

    # Mark complete regardless (backwards compatibility with old workfolders)
    global_state.complete_widget("step9")


def _multigrid_config() -> None:
    multigrid_widget = global_state.get_widget("step10")
    if multigrid_widget:
        multigrid_widget.init_file_checking()
        if multigrid_widget.grid_groupings is not None and multigrid_widget.is_completed():
            if len(multigrid_widget.grid_groupings) > 0:
                logger.info("Step 10 state reconstructed: groupings loaded and MUEdit files found")
            else:
                logger.info("Step 10 state reconstructed: no multi-grid groups (single grids only)")
            global_state.complete_widget("step10")
        elif multigrid_widget.grid_groupings == {} and multigrid_widget.is_completed():
            logger.info("Step 10 state reconstructed: no groupings JSON but MUEdit files exist (backwards compat)")
            multigrid_widget.save_groupings_to_json()
            global_state.complete_widget("step10")
        else:
            logger.info("Step 10 not completed: no MUEdit files found or step not yet processed")
    else:
        logger.warning("Multi-grid configuration widget not found in global state.")
        raise ValueError("Multi-grid configuration widget not found in global state.")


def _muedit_cleaning() -> None:
    muedit_cleaning_widget = global_state.get_widget("step11")
    if muedit_cleaning_widget:
        muedit_cleaning_widget.init_file_checking()
        if muedit_cleaning_widget.is_completed():
            logger.info("Step 11 state reconstructed: edited MUEdit files found")
            global_state.complete_widget("step11")
    else:
        logger.warning("MUEdit cleaning widget not found in global state.")
        raise ValueError("MUEdit cleaning widget not found in global state.")


def _covisi_post_validation() -> None:
    covisi_post_validation_widget = global_state.get_widget("step12")
    if covisi_post_validation_widget:
        covisi_post_validation_widget.init_file_checking()
        if covisi_post_validation_widget.is_completed():
            logger.info("Step 12 state reconstructed: CoVISI post-validation report found")
            global_state.complete_widget("step12")
    else:
        logger.warning("CoVISI post-validation widget not found in global state.")
        raise ValueError("CoVISI post-validation widget not found in global state.")


def _final_results() -> None:
    final_results_widget = global_state.get_widget("step13")
    if final_results_widget:
        final_results_widget.init_file_checking()
        if final_results_widget.is_completed():
            logger.info("Step 13 state reconstructed: cleaned JSON files found in decomposition_results")
            global_state.complete_widget("step13")
    else:
        logger.warning("Final results widget not found in global state.")
        raise ValueError("Final results widget not found in global state.")


# ---------------------------------------------------------------------------
# Shared utilities
# ---------------------------------------------------------------------------

def _find_main_window(widget):
    main_window = widget
    while main_window and not hasattr(main_window, "navigateToStep"):
        main_window = main_window.parent() if hasattr(main_window, "parent") else None
    return main_window


def _get_next_incomplete_step() -> int:
    for step_index in range(1, 14):
        if not global_state.is_widget_completed(f"step{step_index}"):
            return step_index
    return 13


def _show_restore_success(folderpath: str):
    msg_box = QMessageBox()
    msg_box.setIcon(QMessageBox.Information)
    msg_box.setWindowTitle("State restored")
    msg_box.setText(f"The state of folder {folderpath} has been restored.")
    return msg_box


def _migrate_old_folder_names(folderpath: str) -> None:
    for old_name, new_name in FOLDER_NAME_MIGRATIONS.items():
        old_path = os.path.join(folderpath, old_name)
        new_path = os.path.join(folderpath, new_name)
        if not os.path.exists(old_path):
            continue
        if not os.path.isdir(old_path):
            logger.warning(f"Migration skipped: {old_path} exists but is not a directory")
            continue
        if os.path.exists(new_path):
            logger.debug(f"Migration skipped: target {new_path} already exists")
            continue
        try:
            os.rename(old_path, new_path)
            logger.info(f"Migrated folder: {old_name!r} → {new_name!r}")
        except Exception as exc:
            logger.warning(f"Failed to migrate folder {old_path} → {new_path}: {exc}")


def _check_folder_existence(folderpath: str) -> None:
    logger.debug(f"Checking if folder exists: {folderpath}")
    if not os.path.exists(folderpath):
        logger.warning(f"The specified path does not exist: {folderpath}")
        raise FileNotFoundError(f"The specified path does not exist: {folderpath}")
    if not os.path.isdir(folderpath):
        logger.warning(f"The specified path is not a directory: {folderpath}")
        raise NotADirectoryError(f"The specified path is not a directory: {folderpath}")


def _check_pipe_folder_structure(folderpath: str) -> None:
    logger.debug(f"Checking folder structure for: {folderpath}")
    expected_subfolders = FolderNames.list_values()
    optional_folders = [
        FolderNames.DECOMPOSITION_RESULTS.value,
        FolderNames.ANALYSIS.value,
        FolderNames.DECOMPOSITION_COVISI_FILTERED.value,
        FolderNames.DECOMPOSITION_REMOVED_DUPLICATES.value,
        FolderNames.DECOMPOSITION_MUEDIT.value,
        FolderNames.DECOMPOSITION_SCD_EDITION.value,
    ]

    for subfolder in expected_subfolders:
        subfolder_path = os.path.join(folderpath, subfolder)
        logger.debug(f"Checking for subfolder: {subfolder_path}")
        if not os.path.exists(subfolder_path):
            if subfolder in optional_folders:
                logger.info(f"Optional subfolder not found (will be created): {subfolder_path}")
                try:
                    os.makedirs(subfolder_path, exist_ok=True)
                    logger.info(f"Created optional subfolder: {subfolder_path}")
                except Exception as exc:
                    logger.warning(f"Failed to create optional subfolder {subfolder_path}: {exc}")
            else:
                logger.warning(f"Missing expected subfolder: {subfolder_path}")
                raise FileNotFoundError(f"Missing expected subfolder: {subfolder_path}")

    logger.info(f"Folder structure is valid for: {folderpath}")


def _apply_process_log_overrides(folderpath: str) -> None:
    log = read_process_log(folderpath)
    steps = log.get("steps", {})

    if not steps:
        logger.info("Process log: no entries found — keeping file-based reconstruction results")
        return

    logger.info("Process log: applying overrides (%d recorded steps)", len(steps))

    for step_num in range(1, 14):
        step_key = f"step{step_num}"
        if step_key not in global_state.widgets:
            continue

        step_data = steps.get(step_key)
        log_status = step_data.get("status") if step_data else None

        is_completed = global_state.is_widget_completed(step_key)
        is_skipped = global_state.is_widget_skipped(step_key)

        if log_status == "completed":
            if not (is_completed and not is_skipped):
                global_state.widgets[step_key]["completed_step"] = True
                global_state.widgets[step_key]["skipped"] = False
                logger.info("Process log override: %s → completed", step_key)

        elif log_status == "skipped":
            if not (is_completed and is_skipped):
                global_state.widgets[step_key]["completed_step"] = True
                global_state.widgets[step_key]["skipped"] = True
                logger.info("Process log override: %s → skipped", step_key)

        else:
            if is_completed:
                global_state.widgets[step_key]["completed_step"] = False
                global_state.widgets[step_key]["skipped"] = False
                logger.info("Process log override: %s → pending (not in log)", step_key)

    # Backwards compatibility for step9
    if "step9" in global_state.widgets and not steps.get("step9"):
        covisi_folder = os.path.join(folderpath, FolderNames.DECOMPOSITION_COVISI_FILTERED.value)
        if os.path.exists(covisi_folder) and any(
            f.endswith("_covisi_filtered.json") for f in os.listdir(covisi_folder)
        ):
            global_state.widgets["step9"]["completed_step"] = True
            global_state.widgets["step9"]["skipped"] = False
            logger.info(
                "Process log override: step9 → completed "
                "(covisi_filtered folder evidence, backwards compat)"
            )

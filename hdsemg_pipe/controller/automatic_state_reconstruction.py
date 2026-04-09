import os

from hdsemg_pipe._log.log_config import logger
from hdsemg_pipe.actions.enum.FolderNames import FolderNames, FOLDER_NAME_MIGRATIONS
from hdsemg_pipe.actions.process_log import read_process_log
from hdsemg_pipe.actions.skip_marker import check_skip_marker
from hdsemg_pipe.state.global_state import global_state
from PyQt5.QtWidgets import QMessageBox, QFileDialog
from hdsemg_pipe.config.config_manager import config
from hdsemg_pipe.config.config_enums import Settings


def start_reconstruction_workflow(parent):
    workfolder_path = config.get(Settings.WORKFOLDER_PATH)
    if workfolder_path is None:
        workfolder_path = os.getcwd()

    if global_state.workfolder is None:
        selected_folder = QFileDialog.getExistingDirectory(parent, "Select existing pipeline folder", directory=workfolder_path)
        if selected_folder:
            try:
                next_step = reconstruct_folder_state(folderpath=selected_folder)
                # Navigate to the next incomplete step - find the main window first
                main_window = parent
                while main_window and not hasattr(main_window, 'navigateToStep'):
                    main_window = main_window.parent() if hasattr(main_window, 'parent') else None

                if main_window and hasattr(main_window, 'navigateToStep'):
                    logger.info(f"Navigating to step {next_step} after reconstruction")
                    main_window.navigateToStep(next_step)
                else:
                    logger.warning("Could not find main window with navigateToStep method")
            except Exception as e:
                global_state.reset()
                logger.warning(f"Failed to reconstruct folder state: {e}")
                QMessageBox.warning(parent, "Error", f"Failed to reconstruct folder state: \n{str(e)}")
    else:
        QMessageBox.warning(parent, "Error", "A pipeline folder is already selected.")

def reconstruct_folder_state(folderpath):
    logger.info(f"Reconstructing folder state for: {folderpath}")
    folder_content_widget = global_state.get_widget("folder_content")
    global_state.reset()


    # initial checks
    _check_folder_existence(folderpath)
    _migrate_old_folder_names(folderpath)
    _check_pipe_folder_structure(folderpath)

    global_state.workfolder = folderpath

    # Reconstruct each step independently to handle optional/skipped steps
    # Original files are mandatory - fail if missing
    try:
        _original_files(folderpath)
    except FileNotFoundError as e:
        logger.error(f"Cannot reconstruct state: {e}")
        raise

    # All subsequent steps are optional - continue even if they fail
    try:
        _associated_grid_files(folderpath)
    except FileNotFoundError as e:
        logger.info(f"Skipping grid association reconstruction: {e}")
        global_state.skip_widget("step2")

    try:
        _line_noise_cleaned_files(folderpath)
    except FileNotFoundError as e:
        logger.info(f"Skipping line noise cleaned reconstruction: {e}")
        global_state.skip_widget("step3")

    try:
        _analysis_files(folderpath)
    except FileNotFoundError as e:
        logger.info(f"Skipping RMS analysis reconstruction: {e}")
        global_state.skip_widget("step4")

    try:
        _file_quality_selection(folderpath)
    except Exception as e:
        logger.info(f"Skipping file quality selection reconstruction: {e}")
        global_state.skip_widget("step5")

    try:
        _roi_files(folderpath)
    except FileNotFoundError as e:
        logger.info(f"Skipping ROI reconstruction: {e}")
        global_state.skip_widget("step6")

    try:
        _channel_selection_files(folderpath)
    except FileNotFoundError as e:
        logger.info(f"Skipping channel selection reconstruction: {e}")
        global_state.skip_widget("step7")

    # Always initialize decomposition results (Step 8)
    try:
        _decomposition_results_init()
    except Exception as e:
        logger.info(f"Skipping decomposition results reconstruction: {e}")
        global_state.skip_widget("step8")

    # Try to reconstruct MU Quality Review (Step 9)
    try:
        _mu_quality_review()
    except Exception as e:
        logger.info(f"Skipping MU Quality Review reconstruction: {e}")
        global_state.skip_widget("step9")

    # Try to reconstruct multi-grid configuration (Step 10)
    try:
        _multigrid_config()
    except Exception as e:
        logger.info(f"Skipping multi-grid configuration reconstruction: {e}")
        global_state.skip_widget("step10")

    # Try to reconstruct MUEdit cleaning (Step 11)
    try:
        _muedit_cleaning()
    except Exception as e:
        logger.info(f"Skipping MUEdit cleaning reconstruction: {e}")

    # Try to reconstruct CoVISI post-validation (Step 12)
    try:
        _covisi_post_validation()
    except Exception as e:
        logger.info(f"Skipping CoVISI post-validation reconstruction: {e}")
        global_state.skip_widget("step12")

    # Try to reconstruct final results (Step 13)
    try:
        _final_results()
    except Exception as e:
        logger.info(f"Skipping final results reconstruction: {e}")

    # Apply process log overrides: use the recorded statuses as the authoritative
    # source of truth, correcting any mis-detected statuses from file-based checks.
    _apply_process_log_overrides(folderpath)

    msg_box = _show_restore_success(folderpath)
    msg_box.exec_()
    folder_content_widget.update_folder_content()

    # Log completion status for all steps (for debugging)
    logger.info("=" * 50)
    logger.info("Step completion status after reconstruction:")
    for step_num in range(1, 14):
        step_name = f"step{step_num}"
        is_completed = global_state.is_widget_completed(step_name)
        is_skipped = global_state.is_widget_skipped(step_name)
        status = "✓ Completed" if is_completed and not is_skipped else "⏭ Skipped" if is_skipped else "○ Pending"
        logger.info(f"  Step {step_num:2d}: {status}")
    logger.info("=" * 50)

    # Navigate wizard to the next incomplete step (or last step if all complete)
    next_step = _get_next_incomplete_step()
    logger.info(f"Next incomplete step: {next_step}")

    # Refresh progress indicator to show correct visual states
    # (completion status was updated via global_state without triggering UI updates)
    parent_widget = global_state.get_widget("step1")
    if parent_widget and hasattr(parent_widget, 'parent') and parent_widget.parent():
        main_window = parent_widget.parent()
        while main_window and not hasattr(main_window, 'progress_indicator'):
            main_window = main_window.parent()
        if main_window and hasattr(main_window, 'progress_indicator'):
            main_window.progress_indicator.refreshStates()
            logger.info("Progress indicator refreshed after reconstruction")

        # Re-run check() on every step so their UIs reflect the restored state.
        # This is equivalent to checkAllSteps() and ensures steps like
        # FileQualitySelection populate their file lists after reconstruction.
        if main_window and hasattr(main_window, 'checkAllSteps'):
            main_window.checkAllSteps()
            logger.info("All step UIs refreshed after reconstruction")

    return next_step


def _get_next_incomplete_step():
    """Get the index of the next incomplete step (first step that is not completed).

    Returns:
        int: Step index (1-13) of the next incomplete step, or 13 if all steps are completed.
    """
    # Find first incomplete step
    for step_index in range(1, 14):  # Check from step 1 to 13
        if not global_state.is_widget_completed(f"step{step_index}"):
            return step_index
    # All steps completed - return last step
    return 13


def _show_restore_success(folderpath):
    msg_box = QMessageBox()
    msg_box.setIcon(QMessageBox.Information)
    msg_box.setWindowTitle("State restored")
    msg_box.setText(f"The state of folder {folderpath} has been restored.")
    return msg_box


def _migrate_old_folder_names(folderpath: str) -> None:
    """Rename old (un-numbered) pipe folders to their new numbered equivalents.

    Only renames; never deletes.  Safe to call repeatedly — skips any pair
    where the old folder is absent, the new folder already exists, or the old
    path is a file rather than a directory.
    """
    for old_name, new_name in FOLDER_NAME_MIGRATIONS.items():
        old_path = os.path.join(folderpath, old_name)
        new_path = os.path.join(folderpath, new_name)

        if not os.path.exists(old_path):
            continue  # nothing to rename
        if not os.path.isdir(old_path):
            logger.warning(f"Migration skipped: {old_path} exists but is not a directory")
            continue
        if os.path.exists(new_path):
            logger.debug(f"Migration skipped: target {new_path} already exists")
            continue

        try:
            os.rename(old_path, new_path)
            logger.info(f"Migrated folder: {old_name!r} → {new_name!r}")
        except Exception as e:
            logger.warning(f"Failed to migrate folder {old_path} → {new_path}: {e}")


def _check_folder_existence(folderpath):
    """Check if the folder exists and is a directory."""
    logger.debug(f"Checking if folder exists: {folderpath}")
    if not os.path.exists(folderpath):
        logger.warning(f"The specified path does not exist: {folderpath}")
        raise FileNotFoundError(f"The specified path does not exist: {folderpath}")
    if not os.path.isdir(folderpath):
        logger.warning(f"The specified path is not a directory: {folderpath}")
        raise NotADirectoryError(f"The specified path is not a directory: {folderpath}")


def _check_pipe_folder_structure(folderpath):
    """Check if the folder structure is valid for the application."""
    logger.debug(f"Checking folder structure for: {folderpath}")
    # Define the expected subfolders (some are optional for backwards compatibility)
    expected_subfolders = FolderNames.list_values()
    optional_folders = [
        FolderNames.DECOMPOSITION_RESULTS.value,
        FolderNames.ANALYSIS.value,
        # These folders are created on-demand (CoVISI / duplicate removal / MUEdit / SCD may never run)
        FolderNames.DECOMPOSITION_COVISI_FILTERED.value,
        FolderNames.DECOMPOSITION_REMOVED_DUPLICATES.value,
        FolderNames.DECOMPOSITION_MUEDIT.value,
        FolderNames.DECOMPOSITION_SCD_EDITION.value,
    ]

    # Check if each expected subfolder exists
    for subfolder in expected_subfolders:
        subfolder_path = os.path.join(folderpath, subfolder)
        logger.debug(f"Checking for subfolder: {subfolder_path}")
        if not os.path.exists(subfolder_path):
            if subfolder in optional_folders:
                logger.info(f"Optional subfolder not found (will be created): {subfolder_path}")
                # Create optional folders if they don't exist
                try:
                    os.makedirs(subfolder_path, exist_ok=True)
                    logger.info(f"Created optional subfolder: {subfolder_path}")
                except Exception as e:
                    logger.warning(f"Failed to create optional subfolder {subfolder_path}: {e}")
            else:
                logger.warning(f"Missing expected subfolder: {subfolder_path}")
                raise FileNotFoundError(f"Missing expected subfolder: {subfolder_path}")

    logger.info(f"Folder structure is valid for: {folderpath}")


def _original_files(folderpath):
    """Check if the original files folder exists."""
    original_files_path = os.path.join(folderpath, str(FolderNames.ORIGINAL_FILES.value))
    files = os.listdir(original_files_path)

    for file in files:
        if file.endswith(".mat"):
            file_path = os.path.join(original_files_path, file)
            global_state.add_original_file(file_path)

    orig_files = global_state.get_original_files()
    if not orig_files or len(orig_files) == 0:
        logger.warning(f"No original files found in: {original_files_path}")
        raise FileNotFoundError(f"No original files found in: {original_files_path}")

    logger.debug(f"Original files added to global state: {orig_files}")

    original_files_widget = global_state.get_widget("step1")
    if original_files_widget:
        original_files_widget.check()
        # Mark directly in GlobalState without triggering navigation
        logger.info("Step 1 state reconstructed: Original files loaded")
        global_state.complete_widget("step1")
        original_files_widget.fileSelected.emit(folderpath)
    else:
        logger.warning("Original files widget not found in global state.")
        raise ValueError("Original files widget not found in global state.")

    return original_files_path

def _associated_grid_files(folderpath):
    """Check if the associated grid files folder exists."""
    associated_grids_path = os.path.join(folderpath, str(FolderNames.ASSOCIATED_GRIDS.value))
    files = os.listdir(associated_grids_path)

    for file in files:
        if file.endswith(".mat"):
            file_path = os.path.join(associated_grids_path, file)
            global_state.associated_files.append(file_path)

    associated_files = global_state.associated_files.copy()
    if not associated_files or len(associated_files) == 0:
        logger.warning(f"No associated grid files found in: {associated_grids_path}")
        raise FileNotFoundError(f"No associated grid found in: {associated_grids_path}")

    logger.debug(f"associated grid added to global state: {associated_files}")

    associated_grids_widget = global_state.get_widget("step2")
    if associated_grids_widget:
        associated_grids_widget.check()
        # Check if step was skipped
        if check_skip_marker(associated_grids_path):
            logger.info("Step 2 state reconstructed: Grid association was skipped")
            # Mark directly in GlobalState without triggering navigation
            global_state.skip_widget("step2")
        else:
            logger.info("Step 2 state reconstructed: Grid association completed normally")
            # Mark directly in GlobalState without triggering navigation
            global_state.complete_widget("step2")
    else:
        logger.warning("associated grid widget not found in global state.")
        raise ValueError("associated grid widget not found in global state.")

    return associated_grids_path

def _line_noise_cleaned_files(folderpath):
    """Check if the line noise cleaned files folder exists."""
    line_noise_cleaned_path = os.path.join(folderpath, str(FolderNames.LINE_NOISE_CLEANED.value))
    files = os.listdir(line_noise_cleaned_path)

    for file in files:
        if file.endswith(".mat"):
            file_path = os.path.join(line_noise_cleaned_path, file)
            global_state.line_noise_cleaned_files.append(file_path)

    line_noise_cleaned_files = global_state.line_noise_cleaned_files.copy()
    if not line_noise_cleaned_files or len(line_noise_cleaned_files) == 0:
        logger.warning(f"No line noise cleaned files found in: {line_noise_cleaned_path}")
        raise FileNotFoundError(f"No line noise cleaned files found in: {line_noise_cleaned_path}")

    logger.debug(f"Line noise cleaned files added to global state: {line_noise_cleaned_files}")

    line_noise_cleaned_widget = global_state.get_widget("step3")
    if line_noise_cleaned_widget:
        line_noise_cleaned_widget.check()
        # Check if step was skipped
        if check_skip_marker(line_noise_cleaned_path):
            logger.info("Step 3 state reconstructed: Line noise removal was skipped")
            # Mark directly in GlobalState without triggering navigation
            global_state.skip_widget("step3")
        else:
            logger.info("Step 3 state reconstructed: Line noise removal completed normally")
            # Mark directly in GlobalState without triggering navigation
            global_state.complete_widget("step3")
    else:
        logger.warning("Line noise removal widget not found in global state.")
        raise ValueError("Line noise removal widget not found in global state.")

    return line_noise_cleaned_path

def _analysis_files(folderpath):
    """Check if the analysis folder exists and contains results."""
    analysis_path = os.path.join(folderpath, str(FolderNames.ANALYSIS.value))

    if not os.path.exists(analysis_path):
        logger.warning(f"Analysis folder not found: {analysis_path}")
        raise FileNotFoundError(f"Analysis folder not found: {analysis_path}")

    files = os.listdir(analysis_path)

    # Check for skip marker (skip marker is sufficient even without analysis files)
    has_skip_marker = check_skip_marker(analysis_path)

    # Check for analysis output files (PNG, CSV, or TXT)
    analysis_files = [f for f in files if f.endswith(('.png', '.csv', '.txt'))]

    if not has_skip_marker and (not analysis_files or len(analysis_files) == 0):
        logger.warning(f"No analysis files or skip marker found in: {analysis_path}")
        raise FileNotFoundError(f"No analysis files found in: {analysis_path}")

    logger.debug(f"Analysis files found: {analysis_files}")

    rms_quality_widget = global_state.get_widget("step4")
    if rms_quality_widget:
        rms_quality_widget.check()
        # Check if step was skipped
        if has_skip_marker:
            logger.info("Step 4 state reconstructed: RMS quality analysis was skipped")
            # Mark directly in GlobalState without triggering navigation
            global_state.skip_widget("step4")
        else:
            logger.info("Step 4 state reconstructed: RMS quality analysis completed normally")
            # Mark directly in GlobalState without triggering navigation
            global_state.complete_widget("step4")
    else:
        logger.warning("RMS Quality Analysis widget not found in global state.")
        raise ValueError("RMS Quality Analysis widget not found in global state.")

    return analysis_path

def _file_quality_selection(folderpath):
    """Reconstruct Step 5: File Quality Selection state."""
    analysis_path = os.path.join(folderpath, str(FolderNames.ANALYSIS.value))
    sel_path = os.path.join(analysis_path, "file_quality_selection.json")

    file_quality_widget = global_state.get_widget("step5")
    if not file_quality_widget:
        logger.warning("File quality selection widget not found in global state.")
        raise ValueError("File quality selection widget not found in global state.")

    if os.path.exists(sel_path):
        try:
            import json
            with open(sel_path, 'r') as f:
                data = json.load(f)
            selected = data.get("selected", [])
            if selected:
                global_state.line_noise_cleaned_files = selected
                logger.info(f"Step 5 state reconstructed: {len(selected)} files selected")
                global_state.complete_widget("step5")
                return
        except Exception as e:
            logger.warning(f"Could not read file_quality_selection.json: {e}")

    # No selection file found — treat as skipped (all files pass through)
    logger.info("Step 5: no file_quality_selection.json found — marking as skipped")
    global_state.skip_widget("step5")


def _roi_files(folderpath):
    """Check if the roi files folder exists."""
    roi_file_path = os.path.join(folderpath, str(FolderNames.CROPPED_SIGNAL.value))
    files = os.listdir(roi_file_path)

    for file in files:
        if file.endswith(".mat"):
            file_path = os.path.join(roi_file_path, file)
            global_state.cropped_files.append(file_path)

    roi_files = global_state.cropped_files.copy()
    if not roi_files or len(roi_files) == 0:
        logger.warning(f"No roi files found in: {roi_file_path}")
        raise FileNotFoundError(f"No roi found in: {roi_file_path}")

    logger.debug(f"roi added to global state: {roi_files}")

    roi_file_widget = global_state.get_widget("step6")
    if roi_file_widget:
        roi_file_widget.check()
        # Check if step was skipped
        if check_skip_marker(roi_file_path):
            logger.info("Step 6 state reconstructed: ROI cropping was skipped")
            global_state.skip_widget("step6")
        else:
            logger.info("Step 6 state reconstructed: ROI cropping completed normally")
            global_state.complete_widget("step6")
    else:
        logger.warning("roi widget not found in global state.")
        raise ValueError("roi widget not found in global state.")

    return roi_file_path

def _channel_selection_files(folderpath):
    """Reconstruct Step 7: Channel Selection state.

    Handles three cases:
    - All cropped files processed  → mark step complete
    - Some files processed         → keep step pending so the user can resume
    - No files processed at all    → raise FileNotFoundError (step not started)
    """
    from hdsemg_pipe.actions.file_manager import get_channel_selection_status

    channel_sel_dir = os.path.join(folderpath, str(FolderNames.CHANNELSELECTION.value))

    # Populate channel_selection_files with the kept MAT files
    if os.path.isdir(channel_sel_dir):
        for f in os.listdir(channel_sel_dir):
            if f.endswith(".mat") and not os.path.isdir(os.path.join(channel_sel_dir, f)):
                global_state.channel_selection_files.append(
                    os.path.join(channel_sel_dir, f)
                )

    if not global_state.channel_selection_files:
        # Check whether there are any discarded files – if so the step was
        # started but every file was discarded (partial or complete run).
        discarded_dir = os.path.join(channel_sel_dir, "discarded")
        n_discarded = 0
        if os.path.isdir(discarded_dir):
            n_discarded = sum(
                1 for f in os.listdir(discarded_dir)
                if not os.path.isdir(os.path.join(discarded_dir, f))
            )
        if n_discarded == 0:
            logger.warning(f"No channel selection files found in: {channel_sel_dir}")
            raise FileNotFoundError(f"No channel selection files found in: {channel_sel_dir}")

    status = get_channel_selection_status(global_state.cropped_files, channel_sel_dir)
    n_done = status["n_done"]
    n_total = status["n_total"]

    widget = global_state.get_widget("step7")
    if not widget:
        logger.warning("Channel selection widget not found in global state.")
        raise ValueError("Channel selection widget not found in global state.")

    widget.check()

    if n_total > 0 and n_done >= n_total:
        logger.info("Step 7 state reconstructed: Channel selection fully completed")
        global_state.complete_widget("step7")
    else:
        # Partial – leave step pending so the user can resume
        logger.info(
            f"Step 7 state reconstructed: {n_done}/{n_total} files done – step pending (resume available)"
        )

    return channel_sel_dir

def _decomposition_results_init():
    """Initialize Step 8: Decomposition Results monitoring and load mapping state."""
    decomposition_widget = global_state.get_widget("step8")
    if decomposition_widget:
        decomposition_widget.init_file_checking()

        # Check if mapping was completed (JSON file exists and files present)
        if decomposition_widget.decomp_mapping is not None and decomposition_widget.resultfiles:
            logger.info("Step 8 state reconstructed: mapping loaded and files found")
            global_state.complete_widget("step8")
    else:
        logger.warning("decomposition widget not found in global state.")
        raise ValueError("decomposition widget not found in global state.")

def _multigrid_config():
    """Reconstruct Step 10: Multi-Grid Configuration from JSON state."""
    multigrid_widget = global_state.get_widget("step10")
    if multigrid_widget:
        multigrid_widget.init_file_checking()

        # Case 1: groupings JSON exists (empty or with groups) and all required MUEdit files exist
        if multigrid_widget.grid_groupings is not None and multigrid_widget.is_completed():
            if len(multigrid_widget.grid_groupings) > 0:
                logger.info("Step 10 state reconstructed: groupings loaded and MUEdit files found")
            else:
                logger.info("Step 10 state reconstructed: no multi-grid groups (single grids only)")
            global_state.complete_widget("step10")
        # Case 2: No groupings JSON but MUEdit files exist (backwards compatibility)
        elif multigrid_widget.grid_groupings == {} and multigrid_widget.is_completed():
            logger.info("Step 10 state reconstructed: no groupings JSON but MUEdit files exist (backwards compat)")
            multigrid_widget.save_groupings_to_json()
            global_state.complete_widget("step10")
        else:
            logger.info("Step 10 not completed: no MUEdit files found or step not yet processed")
    else:
        logger.warning("Multi-grid configuration widget not found in global state.")
        raise ValueError("Multi-grid configuration widget not found in global state.")

def _mu_quality_review():
    """Reconstruct Step 9: MU Quality Review state."""
    from pathlib import Path
    filtered_dir = Path(global_state.get_folder(FolderNames.DECOMPOSITION_COVISI_FILTERED))
    if not filtered_dir.exists() or not any(filtered_dir.iterdir()):
        return  # step 9 not yet completed

    # Look for manifest
    analysis_dir = Path(global_state.get_workfolder()) / "analysis"
    manifest_path = analysis_dir / "mu_quality_selection.json"

    widget = global_state.get_widget("step9")

    if manifest_path.exists():
        import json
        try:
            with open(manifest_path, "r", encoding="utf-8") as fh:
                manifest = json.load(fh)
            if widget is not None:
                widget.restore_from_manifest(manifest)
        except Exception as exc:
            logger.warning("Could not restore mu_quality_selection.json: %s", exc)
    # Mark step complete regardless (backward compat with old workfolders)
    global_state.complete_widget("step9")

def _muedit_cleaning():
    """Reconstruct Step 11: MUEdit Cleaning state."""
    muedit_cleaning_widget = global_state.get_widget("step11")
    if muedit_cleaning_widget:
        muedit_cleaning_widget.init_file_checking()

        if muedit_cleaning_widget.is_completed():
            logger.info("Step 11 state reconstructed: edited MUEdit files found")
            global_state.complete_widget("step11")
    else:
        logger.warning("MUEdit cleaning widget not found in global state.")
        raise ValueError("MUEdit cleaning widget not found in global state.")

def _covisi_post_validation():
    """Reconstruct Step 12: CoVISI Post-Validation state."""
    covisi_post_validation_widget = global_state.get_widget("step12")
    if covisi_post_validation_widget:
        covisi_post_validation_widget.init_file_checking()

        if covisi_post_validation_widget.is_completed():
            logger.info("Step 12 state reconstructed: CoVISI post-validation report found")
            global_state.complete_widget("step12")
    else:
        logger.warning("CoVISI post-validation widget not found in global state.")
        raise ValueError("CoVISI post-validation widget not found in global state.")

def _final_results():
    """Reconstruct Step 13: Final Results state."""
    final_results_widget = global_state.get_widget("step13")
    if final_results_widget:
        final_results_widget.init_file_checking()

        if final_results_widget.is_completed():
            logger.info("Step 13 state reconstructed: cleaned JSON files found in decomposition_results")
            global_state.complete_widget("step13")
    else:
        logger.warning("Final results widget not found in global state.")
        raise ValueError("Final results widget not found in global state.")


def _apply_process_log_overrides(folderpath: str) -> None:
    """Override step statuses with the values recorded in the process log.

    The process log (``hdsemg-pipe-process.log``) is written by
    ``WizardStepWidget.complete_step()`` / ``skip_step()`` and is the
    authoritative record of what the user actually did.  When the log exists,
    it is used for ALL steps:

    * Steps **in** the log → status from log (completed / skipped).
    * Steps **absent** from the log → revert to pending.  The file-based
      reconstruction may have incorrectly marked them as "skipped" (e.g. when
      the user stopped partway through and the destination folder is empty).

    For workfolders without a process log the function returns early and the
    file-based reconstruction result is kept as-is (backwards compatibility).
    """
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
            # Step not recorded in log → was never done; revert to pending.
            if is_completed:
                global_state.widgets[step_key]["completed_step"] = False
                global_state.widgets[step_key]["skipped"] = False
                logger.info("Process log override: %s → pending (not in log)", step_key)

    # Backwards compatibility for step9 (CoVISI pre-filter):
    # The step may have been run before process-log support for this step was
    # added, or the log entry was lost during a reconstruction cycle.  Use
    # physical folder evidence as the authoritative signal in that case.
    if "step9" in global_state.widgets and not steps.get("step9"):
        covisi_folder = os.path.join(folderpath, FolderNames.DECOMPOSITION_COVISI_FILTERED.value)
        if os.path.exists(covisi_folder) and any(
            f.endswith('_covisi_filtered.json') for f in os.listdir(covisi_folder)
        ):
            global_state.widgets["step9"]["completed_step"] = True
            global_state.widgets["step9"]["skipped"] = False
            logger.info(
                "Process log override: step9 → completed "
                "(covisi_filtered folder evidence, backwards compat)"
            )



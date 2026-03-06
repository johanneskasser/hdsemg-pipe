import json
import os
import shutil
from datetime import datetime

from PyQt5.QtWidgets import QDialog

from hdsemg_pipe._log.log_config import logger
from hdsemg_pipe.state.global_state import global_state
from hdsemg_pipe.actions.workers import ChannelSelectionWorker
from hdsemg_pipe.widgets.dialogs.FileReviewDialog import FileReviewDialog


def start_file_processing(step):
    """Starts processing .mat files and updates the StepWidget dynamically."""
    if not global_state.cropped_files:
        logger.warning("No .mat files found.")
        return

    step.processed_files = 0
    step.total_files = len(global_state.cropped_files)
    step.update_progress(step.processed_files, step.total_files)
    step._review_entries = []  # accumulate per-file review data across the whole step
    folder_content_widget = global_state.get_widget("folder_content")

    process_next_file(step, folder_content_widget)

def process_next_file(step, folder_content_widget):
    """Processes the next file in the list."""
    if step.processed_files < step.total_files:
        file_path = global_state.cropped_files[step.processed_files]
        logger.info(f"Processing file: {file_path}")

        step.worker = ChannelSelectionWorker(file_path)
        step.worker.finished.connect(lambda: file_processed(step, folder_content_widget, file_path))
        step.worker.start()
    else:
        step.complete_step()

def file_processed(step, folder_content_widget, file_path):
    """Updates progress after a file is processed and moves to the next."""
    channel_sel_dir = global_state.get_channel_selection_path()
    basename = os.path.basename(file_path)
    stem = os.path.splitext(basename)[0]

    # Paths hdsemg-select wrote into channelselection/
    out_json = os.path.join(channel_sel_dir, basename)
    out_mat  = os.path.join(channel_sel_dir, stem + ".mat")

    # Show review dialog
    dialog = FileReviewDialog(file_path, parent=step)
    result = dialog.exec_()

    kept = result == QDialog.Accepted

    step._review_entries.append({
        "file": basename,
        "decision": "keep" if kept else "discard",
        "notes": dialog.notes,
        "reason": dialog.reason,
        "timestamp": datetime.now().isoformat(),
    })

    if kept:
        logger.info(f"File kept: {basename} | notes: {dialog.notes!r}")
        global_state.channel_selection_files.append(file_path)
    else:
        logger.info(f"File discarded: {basename} | reason: {dialog.reason!r} | notes: {dialog.notes!r}")
        _move_to_discarded(channel_sel_dir, out_json, out_mat)

    step.processed_files += 1
    step.update_progress(step.processed_files, step.total_files)
    folder_content_widget.update_folder_content()
    channel_selection_widget = global_state.get_widget("step3")

    if step.processed_files < step.total_files:
        process_next_file(step, folder_content_widget)
    else:
        _save_summary_json(channel_sel_dir, step._review_entries)
        n_kept = len(global_state.channel_selection_files)
        if n_kept > 0:
            step.complete_step(processed_files=n_kept)
        else:
            error_msg = "All files were discarded. No files available for the next step."
            logger.error(error_msg)
            channel_selection_widget.warn(error_msg)


def _save_summary_json(channel_sel_dir: str, entries: list):
    """Write a single channel_selection_review.json summarising all file decisions."""
    summary = {
        "created": datetime.now().isoformat(),
        "total": len(entries),
        "kept": sum(1 for e in entries if e["decision"] == "keep"),
        "discarded": sum(1 for e in entries if e["decision"] == "discard"),
        "files": entries,
    }
    out_path = os.path.join(channel_sel_dir, "channel_selection_review.json")
    try:
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(summary, f, indent=2, ensure_ascii=False)
        logger.info(f"Channel selection review saved: {out_path}")
    except OSError as e:
        logger.error(f"Could not write review summary {out_path}: {e}")


def _move_to_discarded(channel_sel_dir: str, *file_paths: str):
    """Move files that exist into <channel_sel_dir>/discarded/."""
    discarded_dir = os.path.join(channel_sel_dir, "discarded")
    os.makedirs(discarded_dir, exist_ok=True)
    for src in file_paths:
        if os.path.exists(src):
            dst = os.path.join(discarded_dir, os.path.basename(src))
            shutil.move(src, dst)
            logger.info(f"Moved discarded file: {src} → {dst}")
        else:
            logger.debug(f"Discarded path not found (skipped): {src}")

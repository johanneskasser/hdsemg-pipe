import json
import os
import shutil
from datetime import datetime

from PyQt5.QtWidgets import QDialog

from hdsemg_pipe._log.log_config import logger
from hdsemg_pipe.state.global_state import global_state
from hdsemg_pipe.actions.workers import ChannelSelectionWorker
from hdsemg_pipe.widgets.dialogs.FileReviewDialog import FileReviewDialog


# ---------------------------------------------------------------------------
# Public helper – used by the widget and by reconstruction
# ---------------------------------------------------------------------------

def get_channel_selection_status(cropped_files: list, channel_sel_dir: str) -> dict:
    """Return how many cropped files have already been processed and which remain.

    A file is considered "already processed" when its basename is present in
    *channel_sel_dir* (kept) **or** in *channel_sel_dir/discarded/* (discarded).

    Returns a dict with:
        n_done       – number of already-processed files
        n_total      – total number of cropped files
        remaining    – list of cropped file paths still to be processed
    """
    discarded_dir = os.path.join(channel_sel_dir, "discarded")
    done_basenames: set[str] = set()

    if os.path.isdir(channel_sel_dir):
        for f in os.listdir(channel_sel_dir):
            # Ignore the review summary JSON and sub-directories
            if f == "channel_selection_review.json" or os.path.isdir(os.path.join(channel_sel_dir, f)):
                continue
            done_basenames.add(f)

    if os.path.isdir(discarded_dir):
        for f in os.listdir(discarded_dir):
            done_basenames.add(f)

    remaining = [f for f in cropped_files if os.path.basename(f) not in done_basenames]
    return {
        "n_done": len(cropped_files) - len(remaining),
        "n_total": len(cropped_files),
        "remaining": remaining,
    }


# ---------------------------------------------------------------------------
# Processing flow
# ---------------------------------------------------------------------------

def start_file_processing(step):
    """Start (or resume) channel selection for all unprocessed cropped files."""
    if not global_state.cropped_files:
        logger.warning("No files found for channel selection.")
        return

    channel_sel_dir = global_state.get_channel_selection_path()
    status = get_channel_selection_status(global_state.cropped_files, channel_sel_dir)

    step._remaining_files = status["remaining"]
    step._file_index = 0                          # index into _remaining_files
    step.processed_files = status["n_done"]       # already-done count (for progress display)
    step.total_files = status["n_total"]
    step.update_progress(step.processed_files, step.total_files)

    # Load existing review entries so the final summary stays complete
    step._review_entries = _load_existing_review_entries(channel_sel_dir)

    folder_content_widget = global_state.get_widget("folder_content")

    if not step._remaining_files:
        logger.info("All files already processed – completing step.")
        step.complete_step()
        return

    logger.info(
        f"Channel selection: {status['n_done']} done, "
        f"{len(step._remaining_files)} remaining."
    )
    _process_next_remaining(step, folder_content_widget)


def _process_next_remaining(step, folder_content_widget):
    """Launch hdsemg-select for the next unprocessed file."""
    if step._file_index < len(step._remaining_files):
        file_path = step._remaining_files[step._file_index]
        logger.info(f"Processing file: {file_path}")

        step.worker = ChannelSelectionWorker(file_path)
        step.worker.finished.connect(
            lambda: _file_processed(step, folder_content_widget, file_path)
        )
        step.worker.start()
    else:
        # All remaining files done
        _save_summary_json(global_state.get_channel_selection_path(), step._review_entries)
        n_kept = len(global_state.channel_selection_files)
        if n_kept > 0:
            step.complete_step(processed_files=n_kept)
        else:
            error_msg = "All files were discarded. No files available for the next step."
            logger.error(error_msg)
            channel_selection_widget = global_state.get_widget("step7")
            if channel_selection_widget:
                channel_selection_widget.warn(error_msg)


def _file_processed(step, folder_content_widget, file_path):
    """Show review dialog, record decision, advance to next file."""
    channel_sel_dir = global_state.get_channel_selection_path()
    basename = os.path.basename(file_path)
    stem = os.path.splitext(basename)[0]

    # Paths hdsemg-select may have written into channelselection/
    out_primary = os.path.join(channel_sel_dir, basename)
    out_mat = os.path.join(channel_sel_dir, stem + ".mat")

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
        logger.info(
            f"File discarded: {basename} | reason: {dialog.reason!r} | notes: {dialog.notes!r}"
        )
        _move_to_discarded(channel_sel_dir, out_primary, out_mat)

    step._file_index += 1
    step.processed_files += 1
    step.update_progress(step.processed_files, step.total_files)
    folder_content_widget.update_folder_content()

    _process_next_remaining(step, folder_content_widget)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load_existing_review_entries(channel_sel_dir: str) -> list:
    """Read the existing review JSON so a resumed session keeps all entries."""
    review_path = os.path.join(channel_sel_dir, "channel_selection_review.json")
    if os.path.exists(review_path):
        try:
            with open(review_path, encoding="utf-8") as f:
                data = json.load(f)
            entries = data.get("files", [])
            logger.debug(f"Loaded {len(entries)} existing review entries from {review_path}")
            return entries
        except Exception as e:
            logger.warning(f"Could not read existing review JSON: {e}")
    return []


def _save_summary_json(channel_sel_dir: str, entries: list):
    """Write (or overwrite) channel_selection_review.json with all decisions."""
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

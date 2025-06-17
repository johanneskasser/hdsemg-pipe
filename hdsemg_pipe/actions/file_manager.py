import os

from hdsemg_pipe.actions.openfile import count_mat_files
from hdsemg_pipe._log.log_config import logger
from hdsemg_pipe.state.global_state import global_state
from hdsemg_pipe.actions.workers import ChannelSelectionWorker


def start_file_processing(step):
    """Starts processing .mat files and updates the StepWidget dynamically."""
    if not global_state.cropped_files:
        logger.warning("No .mat files found.")
        return

    step.processed_files = 0
    step.total_files = len(global_state.cropped_files)
    step.update_progress(step.processed_files, step.total_files)
    folder_content_widget = global_state.get_widget("folder_content")

    process_next_file(step, folder_content_widget)

def process_next_file(step, folder_content_widget):
    """Processes the next .mat file in the list."""

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
    step.processed_files += 1
    global_state.channel_selection_files.append(file_path)
    step.update_progress(step.processed_files, step.total_files)
    folder_content_widget.update_folder_content()
    channel_selection_widget = global_state.get_widget("step3")

    if step.processed_files < step.total_files:
        process_next_file(step, folder_content_widget)
    else:
        channelselection_dest_path = global_state.get_channel_selection_path()
        mat_files = count_mat_files(channelselection_dest_path)
        if mat_files == step.total_files:
            step.complete_step()
        else:
            error_msg = f"Not all {step.total_files} have been processed and are located {channelselection_dest_path}."
            logger.error(error_msg)
            channel_selection_widget.warn(error_msg)

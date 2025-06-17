# state/global_state.py
import os
from hdsemg_pipe._log.log_config import logger
from hdsemg_pipe.actions.enum.FolderNames import FolderNames


class GlobalState:
    _instance = None  # Singleton instance

    def __init__(self):
        self._widget_counter = 0
        self._original_files = []
        self.associated_files = []
        self.cropped_files = []
        self.channel_selection_files = []
        self.workfolder = None
        self.widgets = {}

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(GlobalState, cls).__new__(cls)
            cls._instance.reset()  # Initialize state variables
        return cls._instance

    def reset(self):
        """Reset state variables to initial values."""
        self._original_files = []
        self.associated_files = []
        self.workfolder = None
        self._widget_counter = 0
        self.cropped_files = []
        self.channel_selection_files = []
        # Store widgets as a dictionary where each value is a dictionary
        # with two keys: "widget" and "completed_step".
        if not hasattr(self, "widgets"):
            self.widgets = {}
        for widget_data in self.widgets.values():
            widget_data["completed_step"] = False

    def register_widget(self, widget, name=None):
        """Register a widget globally with an auto-generated name and a completion flag."""
        if name is None:
            name = f"step{self._widget_counter}"
            self._widget_counter += 1

        self.widgets[name] = {"widget": widget, "completed_step": False}

    def update_widget(self, name, widget):
        if name in self.widgets:
            # Optionally update the widget object while preserving the flag.
            self.widgets[name]["widget"] = widget
        else:
            errormsg = f"Widget '{name}' not found. Register it first before updating."
            logger.warning(errormsg)
            # raise KeyError(errormsg)

    def get_widget(self, name):
        """Retrieve the registered widget object."""
        entry = self.widgets.get(name, None)
        if entry:
            return entry["widget"]
        return None

    def complete_widget(self, name):
        """
        Mark a widget as completed.
        For widgets with names following the convention "stepN" (N is an integer),
        this method only allows setting a widget as complete if the previous step is already completed.
        """
        # Check if widget exists
        if name not in self.widgets:
            logger.warning(f"Widget '{name}' not registered.")
            return

        # If the name follows the 'stepN' format, extract the step number.
        if name.startswith("step"):
            try:
                step_num = int(name[4:])
            except ValueError:
                logger.warning(f"Widget name '{name}' does not contain a valid step number.")
                return

            # For steps beyond the first, check the previous step.
            if step_num > 1:
                prev_name = f"step{step_num - 1}"
                prev_entry = self.widgets.get(prev_name)
                if not prev_entry or not prev_entry.get("completed_step", False):
                    logger.warning(f"Cannot complete '{name}' because previous widget '{prev_name}' is not completed.")
                    return

        # Mark this widget as completed.
        self.widgets[name]["completed_step"] = True
        logger.info(f"Widget '{name}' marked as completed.")

    def is_widget_completed(self, name):
        """Return True if the widget is registered and its completed_step flag is True."""
        entry = self.widgets.get(name)
        if entry:
            return entry.get("completed_step", False)
        return False

    def get_associated_grids_path(self):
        if not self.workfolder:
            raise ValueError("Workfolder is not set.")
        path = os.path.join(self.workfolder, FolderNames.ASSOCIATED_GRIDS.value)
        return os.path.normpath(path)

    def get_channel_selection_path(self):
        if not self.workfolder:
            raise ValueError("Workfolder is not set.")
        path = os.path.join(self.workfolder, FolderNames.CHANNELSELECTION.value)
        return os.path.normpath(path)

    def get_decomposition_path(self):
        if not self.workfolder:
            raise ValueError("Workfolder is not set.")
        path = os.path.join(self.workfolder, FolderNames.DECOMPOSITION.value)
        return os.path.normpath(path)

    def get_cropped_signal_path(self):
        if not self.workfolder:
            raise ValueError("Workfolder is not set.")
        path = os.path.join(self.workfolder, FolderNames.CROPPED_SIGNAL.value)
        return os.path.normpath(path)

    def get_original_files_path(self):
        if not self.workfolder:
            raise ValueError("Workfolder is not set.")
        path = os.path.join(self.workfolder, FolderNames.ORIGINAL_FILES.value)
        return os.path.normpath(path)

    def get_original_files(self):
        """Get a copy of the original files list"""
        return self._original_files.copy()

    def add_original_file(self, file_path):
        """Add a file to the original files list"""
        if not isinstance(file_path, str):
            raise ValueError("File path must be a string")
        self._original_files.append(file_path)

    def clear_original_files(self):
        """Clear the original files list"""
        self._original_files.clear()


# Access the singleton instance anywhere in the application
global_state = GlobalState()

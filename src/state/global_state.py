# state/global_state.py
import os
from _log.log_config import logger



class GlobalState:
    _instance = None  # Singleton instance

    def __init__(self):
        self.mat_files = []
        self.associated_files = []
        self.workfolder = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(GlobalState, cls).__new__(cls)
            cls._instance.reset()  # Initialize state variables
        return cls._instance

    def reset(self):
        """Reset state variables to initial values."""
        self.mat_files = []
        self.associated_files = []
        self.workfolder = None
        # Store widgets as a dictionary where each value is a dictionary
        # with two keys: "widget" and "completed_step".
        self.widgets = {}

    def register_widget(self, name, widget):
        """Register a widget globally along with its completion flag (False by default)."""
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
        path = os.path.join(self.workfolder, 'associated_grids')
        return os.path.normpath(path)

    def get_channel_selection_path(self):
        if not self.workfolder:
            raise ValueError("Workfolder is not set.")
        path = os.path.join(self.workfolder, 'channelselection')
        return os.path.normpath(path)

    def get_decomposition_path(self):
        if not self.workfolder:
            raise ValueError("Workfolder is not set.")
        path = os.path.join(self.workfolder, 'decomposition')
        return os.path.normpath(path)


# Access the singleton instance anywhere in the application
global_state = GlobalState()

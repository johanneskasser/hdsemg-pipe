# state/global_state.py
import os

from openpyxl.styles.builtins import output


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
        self.widgets = {}

    def register_widget(self, name, widget):
        """Register a widget globally."""
        self.widgets[name] = widget

    def get_widget(self, name):
        """Retrieve a registered widget."""
        return self.widgets.get(name, None)

    def get_associated_grids_path(self):
        if not self.workfolder:
            raise ValueError

        path = os.path.join(self.workfolder, 'associated_grids')
        path = os.path.normpath(path)
        return path

    def get_channel_selection_path(self):
        if not self.workfolder:
            raise ValueError

        path = os.path.join(self.workfolder, 'channelselection')
        path = os.path.normpath(path)
        return path

    def get_decomposition_path(self):
        if not self.workfolder:
            raise ValueError

        path = os.path.join(self.workfolder, 'decomposition')
        path = os.path.normpath(path)
        return path

# Access the singleton instance anywhere in the application
global_state = GlobalState()

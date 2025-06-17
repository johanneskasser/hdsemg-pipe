from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QHBoxLayout,
    QPushButton, QComboBox
)
from hdsemg_pipe._log.log_config import logger
import logging

from hdsemg_pipe.config.config_enums import Settings
from hdsemg_pipe.config.config_manager import config

def init(parent):
    """
    Initialize the OpenHD-EMG settings tab.
    """
    layout = QVBoxLayout()

    info_label = QLabel("Set the logging level of the application.")
    layout.addWidget(info_label)

    # Horizontal layout row for the log level selection
    h_layout = QHBoxLayout()
    label = QLabel("Log Level:")
    h_layout.addWidget(label)

    # Dropdown for selecting the log level
    log_level_dropdown = QComboBox()
    log_level_dropdown.addItems(["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"])
    h_layout.addWidget(log_level_dropdown)

    # Button to confirm the new log level
    set_level_button = QPushButton("Apply")
    h_layout.addWidget(set_level_button)

    # Label to display the current log level
    current_log_level_label = QLabel()
    current_log_level_label.setText(f"Current: <b>{logging.getLevelName(logger.getEffectiveLevel())}</b>")
    layout.addWidget(current_log_level_label)

    layout.addLayout(h_layout)

    # Function to set the new log level
    def set_log_level(selected_text=None):
        if selected_text is None or type(selected_text) != str:
            # Retrieve text (like "DEBUG") from combo box
            selected_text = log_level_dropdown.currentText()
            # Convert it to the numeric log level

        new_level = getattr(logging, selected_text)

        # Set the logger's level
        logger.setLevel(new_level)
        # Optionally update handlers
        for handler in logger.handlers:
            handler.setLevel(new_level)

        # Update the label to reflect new level
        current_log_level_label.setText(f"Current: <b>{selected_text}</b>")
        log_level_dropdown.setCurrentText(selected_text)
        config.set(Settings.LOG_LEVEL, selected_text)

    # Connect button click to set_log_level function
    set_level_button.clicked.connect(set_log_level)

    settings_level = config.get(Settings.LOG_LEVEL)
    if settings_level is not None and type(settings_level) is not bool:
        set_log_level(settings_level)

    return layout

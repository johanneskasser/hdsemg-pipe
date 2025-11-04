from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QHBoxLayout,
    QPushButton, QComboBox, QFrame
)
from hdsemg_pipe._log.log_config import logger
import logging

from hdsemg_pipe.config.config_enums import Settings
from hdsemg_pipe.config.config_manager import config
from hdsemg_pipe.ui_elements.theme import Colors, Spacing, BorderRadius, Fonts, Styles

def init(parent):
    """Initialize the Logging settings tab with modern styling."""
    layout = QVBoxLayout()
    layout.setSpacing(Spacing.LG)
    layout.setContentsMargins(0, 0, 0, 0)

    # Header section
    header = QLabel("Logging Configuration")
    header.setStyleSheet(f"""
        QLabel {{
            color: {Colors.TEXT_PRIMARY};
            font-size: {Fonts.SIZE_XL};
            font-weight: {Fonts.WEIGHT_BOLD};
            margin-bottom: {Spacing.SM}px;
        }}
    """)
    layout.addWidget(header)

    # Info section
    info_frame = QFrame()
    info_frame.setStyleSheet(f"""
        QFrame {{
            background-color: {Colors.BLUE_50};
            border: 1px solid {Colors.BLUE_500};
            border-radius: {BorderRadius.MD};
            padding: {Spacing.MD}px;
        }}
    """)
    info_layout = QVBoxLayout(info_frame)
    info_layout.setSpacing(Spacing.SM)

    info_label = QLabel(
        '<b>About Logging Levels:</b><br>'
        'The logging level determines which messages are recorded in the application logs. '
        'Higher levels show fewer messages.'
    )
    info_label.setWordWrap(True)
    info_label.setStyleSheet(f"""
        QLabel {{
            color: {Colors.BLUE_900};
            font-size: {Fonts.SIZE_BASE};
            background: transparent;
            border: none;
        }}
    """)
    info_layout.addWidget(info_label)

    levels_explanation = QLabel(
        '• <b>DEBUG</b>: Detailed information for diagnosing problems<br>'
        '• <b>INFO</b>: General informational messages (recommended)<br>'
        '• <b>WARNING</b>: Warning messages for potentially harmful situations<br>'
        '• <b>ERROR</b>: Error messages for serious problems<br>'
        '• <b>CRITICAL</b>: Critical messages for very serious errors'
    )
    levels_explanation.setWordWrap(True)
    levels_explanation.setStyleSheet(f"""
        QLabel {{
            color: {Colors.BLUE_100};
            font-size: {Fonts.SIZE_SM};
            background: transparent;
            border: none;
            margin-top: {Spacing.SM}px;
        }}
    """)
    info_layout.addWidget(levels_explanation)

    layout.addWidget(info_frame)

    # Settings section
    settings_frame = QFrame()
    settings_frame.setStyleSheet(Styles.card())
    settings_layout = QVBoxLayout(settings_frame)
    settings_layout.setSpacing(Spacing.MD)

    settings_header = QLabel("Current Configuration")
    settings_header.setStyleSheet(f"""
        QLabel {{
            color: {Colors.TEXT_PRIMARY};
            font-size: {Fonts.SIZE_LG};
            font-weight: {Fonts.WEIGHT_SEMIBOLD};
        }}
    """)
    settings_layout.addWidget(settings_header)

    # Label to display the current log level
    current_log_level_label = QLabel()
    current_log_level_label.setText(f"Current Level: <b>{logging.getLevelName(logger.getEffectiveLevel())}</b>")
    current_log_level_label.setStyleSheet(f"""
        QLabel {{
            color: {Colors.TEXT_SECONDARY};
            font-size: {Fonts.SIZE_BASE};
            padding: {Spacing.SM}px;
            background-color: {Colors.GRAY_100};
            border-radius: {BorderRadius.SM};
        }}
    """)
    settings_layout.addWidget(current_log_level_label)

    # Control section
    control_layout = QHBoxLayout()
    control_layout.setSpacing(Spacing.MD)

    label = QLabel("New Log Level:")
    label.setStyleSheet(f"""
        QLabel {{
            color: {Colors.TEXT_PRIMARY};
            font-size: {Fonts.SIZE_BASE};
            font-weight: {Fonts.WEIGHT_MEDIUM};
        }}
    """)
    control_layout.addWidget(label)

    # Dropdown for selecting the log level
    log_level_dropdown = QComboBox()
    log_level_dropdown.addItems(["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"])
    log_level_dropdown.setStyleSheet(Styles.combobox())
    control_layout.addWidget(log_level_dropdown, 1)

    # Button to confirm the new log level
    set_level_button = QPushButton("Apply")
    set_level_button.setStyleSheet(Styles.button_primary())
    control_layout.addWidget(set_level_button)

    settings_layout.addLayout(control_layout)
    layout.addWidget(settings_frame)

    layout.addStretch()

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
        current_log_level_label.setText(f"Current Level: <b>{selected_text}</b>")
        log_level_dropdown.setCurrentText(selected_text)
        config.set(Settings.LOG_LEVEL, selected_text)
        logger.info(f"Log level changed to: {selected_text}")

    # Connect button click to set_log_level function
    set_level_button.clicked.connect(set_log_level)

    settings_level = config.get(Settings.LOG_LEVEL)
    if settings_level is not None and type(settings_level) is not bool:
        set_log_level(settings_level)

    return layout

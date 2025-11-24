"""
Dialog for grouping grids with common motor unit inputs.

This dialog allows users to group multiple grids from the same muscle together,
enabling MUEdit to detect common motor units across grids (duplicate detection).
"""
import os
from pathlib import Path
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QListWidget, QListWidgetItem, QLineEdit, QGroupBox,
    QScrollArea, QWidget, QMessageBox, QFrame, QSplitter
)
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QFont

from hdsemg_pipe._log.log_config import logger
from hdsemg_pipe.ui_elements.theme import Colors, Spacing, BorderRadius, Fonts, Styles


class GridGroup(QGroupBox):
    """Widget representing a single group of grids from the same muscle."""

    remove_requested = pyqtSignal(object)  # Emits self when remove is clicked

    def __init__(self, group_name="New Group", parent=None):
        super().__init__(parent)
        self.group_name = group_name
        self.init_ui()

    def init_ui(self):
        """Initialize the group UI."""
        self.setTitle(self.group_name)
        self.setStyleSheet(f"""
            QGroupBox {{
                font-weight: bold;
                border: 2px solid {Colors.BLUE_500};
                border-radius: {BorderRadius.MD};
                margin-top: 10px;
                padding: 15px;
                background-color: {Colors.BLUE_50};
            }}
            QGroupBox::title {{
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px;
                color: {Colors.BLUE_700};
            }}
        """)

        layout = QVBoxLayout(self)

        # Header with name edit and remove button
        header_layout = QHBoxLayout()

        self.name_label = QLabel("Muscle/Group Name:")
        self.name_label.setStyleSheet(f"color: {Colors.TEXT_PRIMARY}; font-weight: normal; font-size: {Fonts.SIZE_SM};")
        header_layout.addWidget(self.name_label)

        self.name_input = QLineEdit(self.group_name)
        self.name_input.setPlaceholderText("e.g., Biceps, Triceps, VL, VM...")
        self.name_input.setStyleSheet(Styles.input())
        self.name_input.textChanged.connect(self.on_name_changed)
        header_layout.addWidget(self.name_input, 1)

        self.remove_btn = QPushButton("✕ Remove Group")
        self.remove_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {Colors.RED_600};
                color: white;
                border: none;
                border-radius: {BorderRadius.SM};
                padding: {Spacing.SM}px {Spacing.MD}px;
                font-size: {Fonts.SIZE_SM};
            }}
            QPushButton:hover {{
                background-color: {Colors.RED_700};
            }}
        """)
        self.remove_btn.clicked.connect(lambda: self.remove_requested.emit(self))
        header_layout.addWidget(self.remove_btn)

        layout.addLayout(header_layout)

        # Info label
        info_label = QLabel(
            "Drag JSON files from the left panel into this group. "
            "Files in the same group will be combined into one multi-grid MUEdit file."
        )
        info_label.setWordWrap(True)
        info_label.setStyleSheet(f"color: {Colors.TEXT_SECONDARY}; font-size: {Fonts.SIZE_XS}; padding: {Spacing.SM}px 0;")
        layout.addWidget(info_label)

        # List of grids in this group
        self.grid_list = QListWidget()
        self.grid_list.setStyleSheet(f"""
            QListWidget {{
                border: 1px solid {Colors.BORDER_DEFAULT};
                border-radius: {BorderRadius.SM};
                background-color: white;
                padding: {Spacing.SM}px;
                min-height: 100px;
            }}
            QListWidget::item {{
                padding: {Spacing.SM}px;
                border-bottom: 1px solid {Colors.BORDER_MUTED};
            }}
            QListWidget::item:selected {{
                background-color: {Colors.BLUE_100};
                color: {Colors.TEXT_PRIMARY};
            }}
        """)
        self.grid_list.setAcceptDrops(True)
        self.grid_list.setDragDropMode(QListWidget.DragDrop)
        self.grid_list.setDefaultDropAction(Qt.MoveAction)
        layout.addWidget(self.grid_list)

        # Stats label
        self.stats_label = QLabel("0 grids")
        self.stats_label.setStyleSheet(f"color: {Colors.TEXT_MUTED}; font-size: {Fonts.SIZE_XS};")
        layout.addWidget(self.stats_label)

        self.update_stats()

    def on_name_changed(self, text):
        """Update group name when text changes."""
        self.group_name = text
        self.setTitle(text if text else "New Group")

    def add_grid(self, grid_filename):
        """Add a grid to this group."""
        # Check if already exists
        for i in range(self.grid_list.count()):
            if self.grid_list.item(i).text() == grid_filename:
                return False

        item = QListWidgetItem(grid_filename)
        self.grid_list.addItem(item)
        self.update_stats()
        return True

    def remove_grid(self, grid_filename):
        """Remove a grid from this group."""
        for i in range(self.grid_list.count()):
            if self.grid_list.item(i).text() == grid_filename:
                self.grid_list.takeItem(i)
                break
        self.update_stats()

    def get_grids(self):
        """Get list of grid filenames in this group."""
        return [self.grid_list.item(i).text() for i in range(self.grid_list.count())]

    def update_stats(self):
        """Update statistics label."""
        count = self.grid_list.count()
        self.stats_label.setText(f"{count} grid{'s' if count != 1 else ''}")

    def is_empty(self):
        """Check if group has no grids."""
        return self.grid_list.count() == 0


class GridGroupingDialog(QDialog):
    """
    Dialog for grouping grids with common motor unit inputs.

    Allows users to create groups of grids from the same muscle,
    which will be exported together as multi-grid MUEdit files.
    """

    def __init__(self, json_files, current_groupings=None, parent=None):
        """
        Initialize the grid grouping dialog.

        Args:
            json_files (list): List of paths to JSON decomposition files
            current_groupings (dict, optional): Existing groupings {group_name: [file1, file2, ...]}
            parent (QWidget, optional): Parent widget
        """
        super().__init__(parent)
        self.json_files = [Path(f) for f in json_files]
        self.current_groupings = current_groupings or {}
        self.groups = []  # List of GridGroup widgets
        self.result_groupings = {}  # Result to return

        self.setWindowTitle("Configure Multi-Grid Groups for MUEdit")
        self.resize(1000, 700)
        self.init_ui()
        self.load_existing_groupings()

    def init_ui(self):
        """Initialize the dialog UI."""
        layout = QVBoxLayout(self)
        layout.setSpacing(Spacing.LG)

        # Header
        header = QLabel(
            "<h2>Configure Multi-Grid Groups</h2>"
            "Group grids from the same muscle together for MUEdit's duplicate detection."
        )
        header.setWordWrap(True)
        header.setStyleSheet(f"color: {Colors.TEXT_PRIMARY}; padding-bottom: {Spacing.MD}px;")
        layout.addWidget(header)

        # Info box
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

        info_text = QLabel(
            "<b>How it works:</b><br>"
            "• Drag JSON files from the left panel into groups on the right<br>"
            "• Each group represents grids from the <b>same muscle</b> with common motor units<br>"
            "• Files in a group will be combined into one multi-grid MUEdit file<br>"
            "• This enables MUEdit to detect duplicate motor units across grids<br>"
            "• Files not in any group will be exported as single-grid files"
        )
        info_text.setWordWrap(True)
        info_text.setStyleSheet(f"color: {Colors.TEXT_PRIMARY}; font-size: {Fonts.SIZE_SM};")
        info_layout.addWidget(info_text)
        layout.addWidget(info_frame)

        # Main content: Splitter with available files on left and groups on right
        splitter = QSplitter(Qt.Horizontal)
        splitter.setStyleSheet(f"""
            QSplitter::handle {{
                background-color: {Colors.BORDER_DEFAULT};
                width: 2px;
            }}
        """)

        # Left panel: Available files
        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(0, 0, Spacing.MD, 0)

        left_header = QLabel("<b>Available Grids (Decomposition Files)</b>")
        left_header.setStyleSheet(f"color: {Colors.TEXT_PRIMARY}; font-size: {Fonts.SIZE_LG}; padding-bottom: {Spacing.SM}px;")
        left_layout.addWidget(left_header)

        left_info = QLabel("Drag files to groups on the right →")
        left_info.setStyleSheet(f"color: {Colors.TEXT_SECONDARY}; font-size: {Fonts.SIZE_SM}; padding-bottom: {Spacing.SM}px;")
        left_layout.addWidget(left_info)

        self.available_list = QListWidget()
        self.available_list.setStyleSheet(f"""
            QListWidget {{
                border: 2px solid {Colors.BORDER_DEFAULT};
                border-radius: {BorderRadius.MD};
                background-color: white;
                padding: {Spacing.SM}px;
            }}
            QListWidget::item {{
                padding: {Spacing.MD}px;
                border-bottom: 1px solid {Colors.BORDER_MUTED};
                background-color: white;
            }}
            QListWidget::item:hover {{
                background-color: {Colors.GRAY_50};
            }}
            QListWidget::item:selected {{
                background-color: {Colors.BLUE_100};
                color: {Colors.TEXT_PRIMARY};
            }}
        """)
        self.available_list.setDragEnabled(True)
        self.available_list.setDefaultDropAction(Qt.MoveAction)

        # Populate available files
        for json_file in self.json_files:
            item = QListWidgetItem(json_file.name)
            item.setData(Qt.UserRole, str(json_file))  # Store full path
            self.available_list.addItem(item)

        left_layout.addWidget(self.available_list)

        file_count = QLabel(f"{len(self.json_files)} file(s) available")
        file_count.setStyleSheet(f"color: {Colors.TEXT_MUTED}; font-size: {Fonts.SIZE_SM}; padding-top: {Spacing.SM}px;")
        left_layout.addWidget(file_count)

        splitter.addWidget(left_panel)

        # Right panel: Groups
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(Spacing.MD, 0, 0, 0)

        right_header_layout = QHBoxLayout()
        right_header = QLabel("<b>Multi-Grid Groups</b>")
        right_header.setStyleSheet(f"color: {Colors.TEXT_PRIMARY}; font-size: {Fonts.SIZE_LG};")
        right_header_layout.addWidget(right_header)

        add_group_btn = QPushButton("+ Add Group")
        add_group_btn.setStyleSheet(Styles.button_primary())
        add_group_btn.clicked.connect(self.add_group)
        right_header_layout.addWidget(add_group_btn)
        right_layout.addLayout(right_header_layout)

        # Scrollable groups container
        self.groups_scroll = QScrollArea()
        self.groups_scroll.setWidgetResizable(True)
        self.groups_scroll.setStyleSheet(f"""
            QScrollArea {{
                border: 2px solid {Colors.BORDER_DEFAULT};
                border-radius: {BorderRadius.MD};
                background-color: {Colors.BG_SECONDARY};
            }}
        """)

        self.groups_container = QWidget()
        self.groups_layout = QVBoxLayout(self.groups_container)
        self.groups_layout.setSpacing(Spacing.MD)
        self.groups_layout.addStretch()

        self.groups_scroll.setWidget(self.groups_container)
        right_layout.addWidget(self.groups_scroll)

        splitter.addWidget(right_panel)
        splitter.setSizes([400, 600])

        layout.addWidget(splitter, 1)

        # Button box
        button_layout = QHBoxLayout()
        button_layout.addStretch()

        cancel_btn = QPushButton("Cancel")
        cancel_btn.setStyleSheet(Styles.button_secondary())
        cancel_btn.clicked.connect(self.reject)
        button_layout.addWidget(cancel_btn)

        ok_btn = QPushButton("OK - Apply Groupings")
        ok_btn.setStyleSheet(Styles.button_primary())
        ok_btn.clicked.connect(self.accept_groupings)
        button_layout.addWidget(ok_btn)

        layout.addLayout(button_layout)

    def add_group(self):
        """Add a new grid group."""
        group_num = len(self.groups) + 1
        group = GridGroup(f"Group {group_num}")
        group.remove_requested.connect(self.remove_group)

        self.groups.append(group)
        # Insert before stretch
        self.groups_layout.insertWidget(self.groups_layout.count() - 1, group)

        logger.info(f"Added new group: Group {group_num}")

    def remove_group(self, group):
        """Remove a grid group."""
        if group in self.groups:
            # Return grids to available list
            for grid_file in group.get_grids():
                item = QListWidgetItem(grid_file)
                self.available_list.addItem(item)

            self.groups.remove(group)
            group.deleteLater()
            logger.info(f"Removed group: {group.group_name}")

    def load_existing_groupings(self):
        """Load existing groupings into the UI."""
        for group_name, file_list in self.current_groupings.items():
            group = GridGroup(group_name)
            group.remove_requested.connect(self.remove_group)

            # Add files to group and remove from available list
            for filename in file_list:
                group.add_grid(filename)

                # Remove from available list
                for i in range(self.available_list.count()):
                    item = self.available_list.item(i)
                    if item and item.text() == filename:
                        self.available_list.takeItem(i)
                        break

            self.groups.append(group)
            self.groups_layout.insertWidget(self.groups_layout.count() - 1, group)

    def accept_groupings(self):
        """Validate and accept the groupings."""
        # Build result groupings
        self.result_groupings = {}

        for group in self.groups:
            grids = group.get_grids()
            if not grids:
                continue  # Skip empty groups

            group_name = group.group_name.strip()
            if not group_name:
                QMessageBox.warning(
                    self,
                    "Invalid Group Name",
                    "All groups must have a name. Please name all groups or remove empty groups."
                )
                return

            # Check for single-grid groups
            if len(grids) == 1:
                response = QMessageBox.question(
                    self,
                    "Single-Grid Group",
                    f"Group '{group_name}' contains only one grid.\n\n"
                    f"Single-grid groups don't benefit from multi-grid duplicate detection.\n"
                    f"Do you want to keep this group?",
                    QMessageBox.Yes | QMessageBox.No,
                    QMessageBox.No
                )

                if response == QMessageBox.No:
                    continue

            self.result_groupings[group_name] = grids

        # Show summary
        if self.result_groupings:
            summary = "Multi-grid groups configured:\n\n"
            for name, grids in self.result_groupings.items():
                summary += f"• {name}: {len(grids)} grid(s)\n"

            ungrouped = self.available_list.count()
            if ungrouped > 0:
                summary += f"\n{ungrouped} file(s) will be exported as single-grid files."

            QMessageBox.information(self, "Groupings Configured", summary)
        else:
            # No groups defined
            response = QMessageBox.question(
                self,
                "No Groups Defined",
                "No multi-grid groups have been defined.\n\n"
                "All files will be exported as single-grid files.\n\n"
                "Continue?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No
            )

            if response == QMessageBox.No:
                return

        logger.info(f"Accepted groupings: {self.result_groupings}")
        self.accept()

    def get_groupings(self):
        """
        Get the configured groupings.

        Returns:
            dict: Dictionary mapping group names to lists of filenames
        """
        return self.result_groupings

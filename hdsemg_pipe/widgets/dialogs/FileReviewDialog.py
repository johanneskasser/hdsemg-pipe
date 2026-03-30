import os

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QTextEdit,
    QLineEdit, QPushButton, QSizePolicy, QFrame
)

from hdsemg_pipe.ui_elements.theme import Colors, Fonts, Spacing, BorderRadius


class FileReviewDialog(QDialog):
    """Dialog shown after channel selection to review and annotate a file.

    The user can mark the file as Keep (default) or Discard. When Discard is
    chosen a mandatory reason must be entered before confirming.

    Returns via exec_():
        QDialog.Accepted – file should be kept
        QDialog.Rejected – file should be discarded
    After exec_() the caller can read:
        .notes  – optional notes string (always)
        .reason – discard reason string (non-empty only when rejected)
    """

    def __init__(self, file_path: str, parent=None):
        super().__init__(parent)
        self.file_path = file_path
        self.notes: str = ""
        self.reason: str = ""
        self._discard_mode = False

        self.setWindowTitle("Review File")
        self.setModal(True)
        self.setMinimumWidth(520)
        self.setStyleSheet(f"""
            QDialog {{
                background-color: {Colors.BG_PRIMARY};
            }}
        """)

        self._build_ui()
        self._keep_btn.setDefault(True)
        self._keep_btn.setFocus()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(Spacing.XL, Spacing.XL, Spacing.XL, Spacing.XL)
        root.setSpacing(Spacing.LG)

        # File name header
        filename = os.path.basename(self.file_path)
        header = QLabel(f"<b>File saved:</b> {filename}")
        header.setStyleSheet(f"""
            QLabel {{
                font-size: {Fonts.SIZE_LG};
                color: {Colors.TEXT_PRIMARY};
            }}
        """)
        header.setWordWrap(True)
        root.addWidget(header)

        # Divider
        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setFrameShadow(QFrame.Sunken)
        line.setStyleSheet(f"border-color: {Colors.BORDER_MUTED};")
        root.addWidget(line)

        # Notes area
        notes_label = QLabel("Notes (optional):")
        notes_label.setStyleSheet(f"""
            QLabel {{
                font-size: {Fonts.SIZE_BASE};
                font-weight: {Fonts.WEIGHT_MEDIUM};
                color: {Colors.TEXT_PRIMARY};
            }}
        """)
        root.addWidget(notes_label)

        self._notes_edit = QTextEdit()
        self._notes_edit.setPlaceholderText("Add any observations about this file…")
        self._notes_edit.setFixedHeight(80)
        self._notes_edit.setStyleSheet(self._input_style())
        self._notes_edit.installEventFilter(self)
        root.addWidget(self._notes_edit)

        # Decision buttons
        btn_row = QHBoxLayout()
        btn_row.setSpacing(Spacing.MD)

        self._keep_btn = QPushButton("✓  Keep")
        self._keep_btn.setFixedHeight(48)
        self._keep_btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self._keep_btn.setStyleSheet(self._keep_style())
        self._keep_btn.clicked.connect(self._on_keep)
        btn_row.addWidget(self._keep_btn)

        self._discard_btn = QPushButton("✕  Discard")
        self._discard_btn.setFixedHeight(48)
        self._discard_btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self._discard_btn.setStyleSheet(self._discard_style())
        self._discard_btn.clicked.connect(self._on_discard_clicked)
        btn_row.addWidget(self._discard_btn)

        root.addLayout(btn_row)

        # Reason area (hidden until Discard is selected)
        self._reason_widget = self._build_reason_widget()
        self._reason_widget.setVisible(False)
        root.addWidget(self._reason_widget)

    def _build_reason_widget(self) -> QFrame:
        frame = QFrame()
        frame.setStyleSheet(f"""
            QFrame {{
                background-color: {Colors.RED_50};
                border: 1px solid {Colors.RED_500};
                border-radius: {BorderRadius.MD};
                padding: {Spacing.SM}px;
            }}
        """)
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(Spacing.MD, Spacing.MD, Spacing.MD, Spacing.MD)
        layout.setSpacing(Spacing.SM)

        reason_label = QLabel("Reason for discarding (required):")
        reason_label.setStyleSheet(f"""
            QLabel {{
                font-size: {Fonts.SIZE_BASE};
                font-weight: {Fonts.WEIGHT_MEDIUM};
                color: {Colors.RED_700};
                background: transparent;
                border: none;
            }}
        """)
        layout.addWidget(reason_label)

        self._reason_edit = QLineEdit()
        self._reason_edit.setPlaceholderText("Describe why this file is being discarded…")
        self._reason_edit.setStyleSheet(self._input_style())
        self._reason_edit.returnPressed.connect(self._confirm_discard)
        layout.addWidget(self._reason_edit)

        self._confirm_discard_btn = QPushButton("Confirm Discard")
        self._confirm_discard_btn.setFixedHeight(36)
        self._confirm_discard_btn.setStyleSheet(self._discard_style())
        self._confirm_discard_btn.clicked.connect(self._confirm_discard)
        layout.addWidget(self._confirm_discard_btn)

        return frame

    # ------------------------------------------------------------------
    # Event handling
    # ------------------------------------------------------------------

    def eventFilter(self, obj, event):
        """Allow Ctrl+Enter in notes area to submit; Escape closes as Keep."""
        from PyQt5.QtCore import QEvent
        from PyQt5.QtGui import QKeyEvent
        if obj is self._notes_edit and event.type() == QEvent.KeyPress:
            key_event: QKeyEvent = event
            if key_event.key() in (Qt.Key_Return, Qt.Key_Enter):
                modifiers = key_event.modifiers()
                if modifiers & Qt.ControlModifier:
                    self._on_keep()
                    return True
        return super().eventFilter(obj, event)

    def keyPressEvent(self, event):
        """Enter confirms Keep; Escape does nothing (force explicit choice)."""
        if event.key() in (Qt.Key_Return, Qt.Key_Enter):
            if not self._discard_mode:
                self._on_keep()
            return
        if event.key() == Qt.Key_Escape:
            # Do not close on Escape – force an explicit decision
            return
        super().keyPressEvent(event)

    # ------------------------------------------------------------------
    # Button actions
    # ------------------------------------------------------------------

    def _on_keep(self):
        self.notes = self._notes_edit.toPlainText().strip()
        self.accept()

    def _on_discard_clicked(self):
        """Switch UI into discard mode – show reason area."""
        self._discard_mode = True
        self._reason_widget.setVisible(True)
        self._keep_btn.setDefault(False)
        self._confirm_discard_btn.setDefault(True)
        self._reason_edit.setFocus()
        self.adjustSize()

    def _confirm_discard(self):
        reason = self._reason_edit.text().strip()
        if not reason:
            self._reason_edit.setStyleSheet(
                self._input_style() + f"border-color: {Colors.RED_500};"
            )
            self._reason_edit.setPlaceholderText("Please enter a reason before confirming.")
            self._reason_edit.setFocus()
            return
        self.notes = self._notes_edit.toPlainText().strip()
        self.reason = reason
        self.reject()

    # ------------------------------------------------------------------
    # Styles
    # ------------------------------------------------------------------

    @staticmethod
    def _keep_style() -> str:
        return f"""
            QPushButton {{
                background-color: {Colors.GREEN_600};
                color: white;
                border: none;
                border-radius: {BorderRadius.MD};
                font-size: {Fonts.SIZE_LG};
                font-weight: {Fonts.WEIGHT_SEMIBOLD};
            }}
            QPushButton:hover {{
                background-color: {Colors.GREEN_700};
            }}
            QPushButton:pressed {{
                background-color: {Colors.GREEN_500};
            }}
        """

    @staticmethod
    def _discard_style() -> str:
        return f"""
            QPushButton {{
                background-color: {Colors.RED_600};
                color: white;
                border: none;
                border-radius: {BorderRadius.MD};
                font-size: {Fonts.SIZE_LG};
                font-weight: {Fonts.WEIGHT_SEMIBOLD};
            }}
            QPushButton:hover {{
                background-color: {Colors.RED_700};
            }}
            QPushButton:pressed {{
                background-color: {Colors.RED_500};
            }}
        """

    @staticmethod
    def _input_style() -> str:
        return f"""
            QTextEdit, QLineEdit {{
                background-color: {Colors.BG_PRIMARY};
                border: 1px solid {Colors.BORDER_DEFAULT};
                border-radius: {BorderRadius.SM};
                padding: {Spacing.SM}px;
                font-size: {Fonts.SIZE_BASE};
                color: {Colors.TEXT_PRIMARY};
            }}
            QTextEdit:focus, QLineEdit:focus {{
                border-color: {Colors.BLUE_500};
            }}
        """

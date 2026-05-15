from PyQt5.QtCore import Qt, QSize
from PyQt5.QtGui import QColor, QMovie, QPainter
from PyQt5.QtWidgets import QFrame, QLabel, QVBoxLayout, QWidget

import hdsemg_pipe.resources_rc  # noqa: F401 – registers Qt resources
from hdsemg_pipe.ui_elements.theme import BorderRadius, Colors, Fonts, Spacing


class LoadingOverlay(QWidget):
    """Full-screen overlay widget with a centred spinner card.

    The overlay is a child of *parent*, so it resizes automatically with it.
    Use :meth:`show_over` to display and :meth:`hide` to remove.
    """

    def __init__(self, parent: QWidget, text: str = "Restoring folder state…") -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setGeometry(parent.rect())
        self._build_ui(text)
        self.raise_()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @classmethod
    def show_over(cls, parent: QWidget, text: str = "Restoring folder state…") -> "LoadingOverlay":
        overlay = cls(parent, text)
        overlay.show()
        # Force a paint pass so the overlay is visible before heavy work starts.
        parent.repaint()
        return overlay

    # ------------------------------------------------------------------
    # Qt overrides
    # ------------------------------------------------------------------

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(0, 0, 0, 140))

    def resizeEvent(self, event) -> None:
        if self.parent():
            self.setGeometry(self.parent().rect())
        super().resizeEvent(event)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _build_ui(self, text: str) -> None:
        outer = QVBoxLayout(self)
        outer.setAlignment(Qt.AlignCenter)
        outer.setContentsMargins(0, 0, 0, 0)

        card = QFrame()
        card.setFixedSize(200, 160)
        card.setStyleSheet(f"""
            QFrame {{
                background-color: {Colors.BG_PRIMARY};
                border-radius: {BorderRadius.XL};
                border: 1px solid {Colors.BORDER_DEFAULT};
            }}
        """)

        card_layout = QVBoxLayout(card)
        card_layout.setAlignment(Qt.AlignCenter)
        card_layout.setSpacing(Spacing.MD)
        card_layout.setContentsMargins(Spacing.XL, Spacing.XL, Spacing.XL, Spacing.XL)

        # Spinner
        self._movie = QMovie(":/resources/loading.gif")
        self._movie.setScaledSize(QSize(48, 48))

        spinner = QLabel()
        spinner.setMovie(self._movie)
        spinner.setAlignment(Qt.AlignCenter)
        spinner.setFixedSize(48, 48)
        spinner.setStyleSheet("background: transparent; border: none;")
        self._movie.start()
        card_layout.addWidget(spinner)

        # Status label
        label = QLabel(text)
        label.setAlignment(Qt.AlignCenter)
        label.setWordWrap(True)
        label.setStyleSheet(f"""
            QLabel {{
                color: {Colors.TEXT_SECONDARY};
                font-size: {Fonts.SIZE_SM};
                background: transparent;
                border: none;
            }}
        """)
        card_layout.addWidget(label)

        outer.addWidget(card)

from PyQt5.QtCore import QSize, Qt
from PyQt5.QtGui import QColor, QFontMetrics, QPainter
from PyQt5.QtWidgets import QLabel, QSizePolicy


class ElidedLabel(QLabel):
    """Single-line label that elides in the middle instead of forcing its parent wider.

    The full text is available as tooltip. Opts out of any inherited QFrame
    border/padding from parent stylesheets.
    """

    def __init__(self, text: str, size: str, weight: str, color: str, parent=None):
        super().__init__(parent)
        self._full = text
        self._color = color
        self.setToolTip(text)
        self.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self.setStyleSheet(
            f"QLabel {{ color: {color}; font-size: {size}; font-weight: {weight};"
            " border: none; padding: 0; background: transparent; }"
        )

    def setFullText(self, text: str):
        self._full = text
        self.update()

    def sizeHint(self):
        return QSize(0, QFontMetrics(self.font()).height() + 2)

    def paintEvent(self, _event):
        painter = QPainter(self)
        painter.setFont(self.font())
        painter.setPen(QColor(self._color))
        text = QFontMetrics(self.font()).elidedText(self._full, Qt.ElideMiddle, self.width())
        painter.drawText(self.rect(), Qt.AlignVCenter | Qt.AlignLeft, text)

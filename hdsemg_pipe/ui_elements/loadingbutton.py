from PyQt5.QtGui import QMovie, QIcon
from PyQt5.QtWidgets import QPushButton

import hdsemg_pipe.resources_rc

class LoadingButton(QPushButton):
    """
    A QPushButton subclass that displays a loading animation when an action is in progress.

    Attributes:
        default_text (str): The default text displayed on the button.
        loading_movie (QMovie): The QMovie object for the loading animation.
        _is_loading (bool): A flag indicating whether the loading animation is active.
    """

    def __init__(self, text, parent=None):
        """
        Initializes the LoadingButton with the given text and optional parent widget.

        Args:
            text (str): The text to display on the button.
            parent (QWidget, optional): The parent widget of the button. Defaults to None.
        """
        super().__init__(text, parent)
        self.default_text = text
        self.loading_movie = QMovie(":/resources/loading.gif")
        self.loading_movie.frameChanged.connect(self.update_icon)
        self._is_loading = False

    def update_icon(self):
        """
        Updates the button's icon with the current frame of the loading animation.
        """
        pixmap = self.loading_movie.currentPixmap()
        self.setIcon(QIcon(pixmap))

    def start_loading(self):
        """
        Starts the loading animation and disables the button.
        """
        self._is_loading = True
        self.setDisabled(True)
        self.setText("")
        self.loading_movie.start()

    def stop_loading(self):
        """
        Stops the loading animation and reverts the button to its default state.
        """
        self._is_loading = False
        self.loading_movie.stop()
        self.setIcon(QIcon())  # Remove icon
        self.setText(self.default_text)
        self.setDisabled(False)
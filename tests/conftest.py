# matplotlib binds to the first Qt binding that is already imported; hdsemg_shared pulls in
# PySide6, which would break widgets built on PyQt5 canvases. Import PyQt5's backend first.
import PyQt5.QtCore  # noqa: F401
import matplotlib.backends.backend_qt5agg  # noqa: F401

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtWidgets import QApplication

import hdsemg_pipe.widgets.wizard.FileQualitySelectionWizardWidget  # noqa: F401  (binds matplotlib to PyQt5 first)
from hdsemg_pipe.widgets.wizard.CoVISIPostValidationWizardWidget import _FileNameDelegate


def test_file_name_delegate_strips_processing_suffix_only_for_display():
    app = QApplication.instance() or QApplication([])
    d = _FileNameDelegate()
    full = "641_FT_Block1_Pyramid_2_10mm_4x8_2_VastusMedialisRight_covisi_filtered_muedit.mat_edited.mat"
    assert d.displayText(full, None) == "641_FT_Block1_Pyramid_2_10mm_4x8_2_VastusMedialisRight"
    assert d.displayText("plain_name.mat", None) == "plain_name"

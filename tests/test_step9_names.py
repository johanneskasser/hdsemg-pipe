import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import hdsemg_pipe.widgets.wizard.FileQualitySelectionWizardWidget  # noqa: F401  (binds matplotlib to PyQt5 first)
from hdsemg_pipe.widgets.wizard.MUQualityReviewWizardWidget import _name_within_group


def test_name_within_group_strips_group_prefix():
    assert _name_within_group("/d/A_1_10mm_4x8_1_Muscle.json", "A_1") == "10mm_4x8_1_Muscle.json"


def test_name_within_group_keeps_full_name_when_nothing_would_remain():
    assert _name_within_group("/d/A_1.json", "A_1") == "A_1.json"
    assert _name_within_group("/d/B_2.json", "A_1") == "B_2.json"

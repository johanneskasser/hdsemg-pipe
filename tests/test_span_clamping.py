from types import SimpleNamespace

from hdsemg_pipe.actions.crop_roi import CropRoiDialog
from hdsemg_pipe.actions.rms_quality_analysis import RMSQualityDialog
from hdsemg_pipe.actions.span_utils import clamp_to_range


def test_clamp_to_range():
    assert clamp_to_range(-0.6, 0.0, 10.0) == 0.0
    assert clamp_to_range(12.0, 0.0, 10.0) == 10.0
    assert clamp_to_range(3.0, 0.0, 10.0) == 3.0
    assert clamp_to_range(None, 0.0, 10.0) is None


def _rms_stub(duration=10.0):
    stub = SimpleNamespace(
        first_click_pos=None, selected_region=None, span_selector=None,
        selection_ax="ax", toolbar=SimpleNamespace(mode=""),
        btn_calculate=SimpleNamespace(setEnabled=lambda _: None),
        _signal_duration_s=lambda: duration,
        _update_roi_display=lambda: None, _draw_selection_lines=lambda: None,
    )
    return stub


def test_rms_span_select_clamps_negative_start():
    stub = _rms_stub()
    RMSQualityDialog._on_span_select(stub, -0.59, 4.0)
    assert stub.selected_region == (0.0, 4.0)


def test_rms_span_select_ignores_drag_in_margin():
    stub = _rms_stub()
    RMSQualityDialog._on_span_select(stub, -1.0, -0.2)
    assert stub.selected_region is None


def test_rms_click_ignores_none_and_clamps():
    stub = _rms_stub()
    RMSQualityDialog._on_click(stub, SimpleNamespace(inaxes="ax", button=1, xdata=None))
    assert stub.first_click_pos is None
    RMSQualityDialog._on_click(stub, SimpleNamespace(inaxes="ax", button=1, xdata=-0.3))
    assert stub.first_click_pos == 0.0


def test_crop_span_select_clamps():
    stub = SimpleNamespace(
        first_click_pos=None, span_selector=None, lower_threshold=0, upper_threshold=0,
        compute_data_xrange=lambda: (0, 999),
        update_roi_info=lambda: None, draw_threshold_lines=lambda: None,
    )
    CropRoiDialog.on_span_select(stub, -1200.7, 5000.2)
    assert (stub.lower_threshold, stub.upper_threshold) == (0, 999)

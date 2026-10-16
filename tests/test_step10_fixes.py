import json

from hdsemg_pipe.actions.process_log import STEP_NAMES
from hdsemg_pipe.controller import automatic_state_reconstruction as asr
from hdsemg_pipe.widgets.wizard.RemoveDuplicateMUsWizardWidget import _fmt


def test_fmt_handles_nan_none_and_numbers():
    assert _fmt(0.91234, ".3f") == "0.912"
    assert _fmt(12, ".1f") == "12.0"
    assert _fmt(float("nan"), ".3f") == "—"
    assert _fmt(None, ".1f") == "—"


def test_step10_name_matches_registered_widget():
    assert STEP_NAMES["step10"] == "Remove Duplicate MUs"


class _FakeState:
    def __init__(self, folder):
        self.folder, self.calls = folder, []

    def get_widget(self, name):
        return object()

    def get_decomposition_removed_duplicates_path(self):
        return self.folder

    def complete_widget(self, name):
        self.calls.append(("complete", name))

    def skip_widget(self, name):
        self.calls.append(("skip", name))


def _restore(monkeypatch, folder):
    fake = _FakeState(str(folder))
    monkeypatch.setattr(asr, "global_state", fake)
    asr._duplicate_removal_restore()
    return fake.calls


def test_restore_step10_pending_without_files(tmp_path, monkeypatch):
    assert _restore(monkeypatch, tmp_path) == []


def test_restore_step10_completed_with_files(tmp_path, monkeypatch):
    (tmp_path / "a.json").write_text("{}")
    assert _restore(monkeypatch, tmp_path) == [("complete", "step10")]


def test_restore_step10_skipped_with_marker(tmp_path, monkeypatch):
    (tmp_path / "a.json").write_text("{}")
    (tmp_path / ".skip_marker.json").write_text(json.dumps({"skipped": True}))
    assert _restore(monkeypatch, tmp_path) == [("skip", "step10")]

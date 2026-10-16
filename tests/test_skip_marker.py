import json

from hdsemg_pipe.actions.skip_marker import check_skip_marker, save_skip_marker


def _read(folder):
    return json.loads((folder / ".skip_marker.json").read_text())


def test_user_note_is_stored(tmp_path):
    assert save_skip_marker(str(tmp_path), "User skipped duplicate detection", "handled in scd-edition")
    data = _read(tmp_path)
    assert data["reason"] == "User skipped duplicate detection"
    assert data["user_note"] == "handled in scd-edition"
    assert check_skip_marker(str(tmp_path))


def test_empty_note_is_omitted_and_old_markers_stay_readable(tmp_path):
    save_skip_marker(str(tmp_path), "r", "")
    assert "user_note" not in _read(tmp_path)
    (tmp_path / ".skip_marker.json").write_text('{"skipped": true, "reason": "old"}')
    assert check_skip_marker(str(tmp_path))

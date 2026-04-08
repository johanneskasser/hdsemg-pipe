import math
import pytest
from hdsemg_pipe.actions.decomposition_file import ReliabilityThresholds


def test_defaults():
    t = ReliabilityThresholds()
    assert t.sil_min == 0.9
    assert t.pnr_min == 30.0
    assert t.covisi_max == 30.0
    assert t.sil_enabled is True
    assert t.pnr_enabled is True
    assert t.covisi_enabled is True


def test_is_reliable_all_pass():
    t = ReliabilityThresholds()
    assert t.is_reliable(sil=0.95, pnr=35.0, covisi=20.0) is True


def test_is_reliable_sil_fails():
    t = ReliabilityThresholds()
    assert t.is_reliable(sil=0.85, pnr=35.0, covisi=20.0) is False


def test_is_reliable_pnr_fails():
    t = ReliabilityThresholds()
    assert t.is_reliable(sil=0.95, pnr=25.0, covisi=20.0) is False


def test_is_reliable_covisi_fails():
    t = ReliabilityThresholds()
    assert t.is_reliable(sil=0.95, pnr=35.0, covisi=35.0) is False


def test_is_reliable_disabled_criterion_ignored():
    t = ReliabilityThresholds(sil_enabled=False)
    # sil fails but sil_enabled=False → still reliable
    assert t.is_reliable(sil=0.5, pnr=35.0, covisi=20.0) is True


def test_is_reliable_nan_disabled():
    t = ReliabilityThresholds(pnr_enabled=False)
    assert t.is_reliable(sil=0.95, pnr=float("nan"), covisi=20.0) is True


def test_is_reliable_nan_enabled_fails():
    t = ReliabilityThresholds()
    assert t.is_reliable(sil=float("nan"), pnr=35.0, covisi=20.0) is False


def test_round_trip_dict():
    t = ReliabilityThresholds(sil_min=0.85, pnr_min=25.0, covisi_max=40.0)
    d = t.to_dict()
    t2 = ReliabilityThresholds.from_dict(d)
    assert t2.sil_min == 0.85
    assert t2.pnr_min == 25.0
    assert t2.covisi_max == 40.0

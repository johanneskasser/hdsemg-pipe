import numpy as np

from hdsemg_pipe.actions.cross_grid_duplicates import best_lag, find_cross_grid_duplicates

FS = 2048.0
N = int(20 * FS)
LAG = 5  # samples, ~2.4 ms


def _train(rng, rate=10):
    t = np.cumsum(rng.integers(int(FS / rate * 0.7), int(FS / rate * 1.3), size=rate * 20))
    return t[t < N - 100]


def _emgfile(rng, trains, templates):
    raw = rng.normal(0, 0.05, size=(N, 4))
    for tr, tpl in zip(trains, templates):
        for s in tr:
            raw[s:s + len(tpl)] += tpl
    return {"FSAMP": FS, "MUPULSES": trains, "NUMBER_OF_MUS": len(trains), "RAW_SIGNAL": raw}


def _setup():
    rng = np.random.default_rng(1)
    a, other = _train(rng), _train(rng)
    b = a + LAG + rng.integers(-1, 2, size=len(a))  # constant offset + 0.5 ms jitter
    tpl_a = np.outer(np.hanning(20), [1.0, -0.5, 0.3, 0.8])
    tpl_other = np.outer(np.hanning(20), [-0.7, 1.0, 0.9, -0.2])
    ef1 = _emgfile(rng, [a, other], [tpl_a, tpl_other])
    ef2 = _emgfile(rng, [b], [tpl_a])  # b has tpl_a in grid 2's channels, as unit A's copy
    return ef1, ef2, a, b


def test_lag_search_finds_offset_that_zero_lag_misses():
    _, _, a, b = _setup()
    assert best_lag(a, b, FS, max_lag_ms=0)[1] < 0.3  # zero-lag comparison misses it
    lag, coincidence, _ = best_lag(a, b, FS)
    assert abs(lag - LAG) <= 1 and coincidence > 0.9


def test_cross_grid_pairs_confirmed_by_muap():
    ef1, ef2, _, _ = _setup()
    pairs = find_cross_grid_duplicates([ef1, ef2])
    assert len(pairs) == 1  # unrelated unit is not a candidate
    p = pairs[0]
    assert (p["file_a"], p["mu_a"], p["file_b"], p["mu_b"]) == (0, 0, 1, 0)
    assert p["decision"] == "duplicate" and p["muap_r"] > 0.9
    assert abs(p["lag_ms"] - LAG * 1000 / FS) < 0.6


def test_synchronised_but_different_muap_is_ambiguous():
    ef1, ef2, _, _ = _setup()
    rng = np.random.default_rng(2)
    ef2["RAW_SIGNAL"] = rng.normal(0, 0.05, size=(N, 4))  # no MUAP from these discharges
    assert find_cross_grid_duplicates([ef1, ef2])[0]["decision"] == "ambiguous"


def test_group_detection_removes_offset_duplicate_and_records_decision(monkeypatch):
    import pandas as pd
    from hdsemg_pipe.actions import duplicate_detection_openhdemg as dd

    monkeypatch.setattr(dd, "detect_duplicates_between_files",
                        lambda *a, **k: pd.DataFrame(columns=["MU_file1", "MU_file2", "XCC"]))
    ef1, ef2, _, _ = _setup()
    res = dd.detect_duplicates_in_group([ef1, ef2], reliability_per_file=[None, None])
    assert len(res["duplicate_groups"]) == 1
    group = res["duplicate_groups"][0]
    assert sorted(group["mus"]) == [(0, 0), (1, 0)]
    pair = res["cross_grid_pairs"][0]
    assert pair["decision"] == "duplicate"
    assert pair["kept"] == list(group["survivor"]) and len(pair["removed"]) == 1

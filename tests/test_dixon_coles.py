import pytest

from sssm.model import DixonColes


def test_fit_recovers_structure(synthetic_league):
    m = DixonColes(xi=0.0).fit(synthetic_league)
    assert m.home_adv_ == pytest.approx(0.25, abs=0.1)
    r = m.ratings()
    assert r.iloc[0]["team"] in {"T0", "T1"}
    assert r.iloc[-1]["team"] in {"T8", "T9"}


def test_predictions_are_probabilities(synthetic_league):
    m = DixonColes().fit(synthetic_league)
    p = m.predict("T0", "T9")
    for market in p.values():
        assert sum(market.values()) == pytest.approx(1.0, abs=1e-9)
    assert p["1X2"]["home"] > 0.5
    assert m.predict("T0", "Nobody") is None


def test_as_of_excludes_future(synthetic_league):
    cutoff = synthetic_league["date"].iloc[200]
    m = DixonColes().fit(synthetic_league, as_of=cutoff)
    m2 = DixonColes().fit(synthetic_league[synthetic_league["date"] < cutoff], as_of=cutoff)
    assert m.home_adv_ == pytest.approx(m2.home_adv_)


def test_too_few_matches():
    import pandas as pd

    with pytest.raises(ValueError):
        DixonColes().fit(pd.DataFrame({"date": ["2024-01-01"], "home": ["A"], "away": ["B"], "hg": [1], "ag": [0]}))

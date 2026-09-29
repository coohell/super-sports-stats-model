import numpy as np
import pytest

from sssm.odds import devig, ev, kelly, log_growth, overround


@pytest.mark.parametrize("method", ["proportional", "power", "shin"])
def test_devig_sums_to_one(method):
    p = devig([1.50, 4.20, 7.00], method)
    assert p.sum() == pytest.approx(1.0)
    assert np.all(p > 0)


def test_power_devig_shades_longshots_more_than_proportional():
    odds = [1.30, 5.50, 11.0]
    prop, power = devig(odds, "proportional"), devig(odds, "power")
    assert power[0] > prop[0]  # 인기팀 확률은 더 높게
    assert power[2] < prop[2]  # 롱샷 확률은 더 낮게


def test_no_margin_is_identity():
    assert devig([2.0, 2.0], "power") == pytest.approx([0.5, 0.5])


def test_overround():
    assert overround([1.90, 1.90]) == pytest.approx(2 / 1.9 - 1)


def test_ev_and_kelly():
    assert ev(0.55, 2.0) == pytest.approx(0.10)
    assert kelly(0.55, 2.0) == pytest.approx(0.10)  # (0.55*2-1)/(2-1)
    assert kelly(0.55, 2.0, 0.25) == pytest.approx(0.025)
    assert kelly(0.40, 2.0) == 0.0


def test_log_growth_is_maximised_at_kelly():
    p, o = 0.55, 2.0
    f = kelly(p, o)
    assert log_growth(p, o, f) > log_growth(p, o, f * 0.5)
    assert log_growth(p, o, f) > log_growth(p, o, f * 1.5)


def test_rejects_bad_odds():
    with pytest.raises(ValueError):
        devig([1.0, 3.0])

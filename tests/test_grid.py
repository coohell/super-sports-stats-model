import numpy as np
import pytest

from sssm import grid
from sssm.markets import Fixture


def _odds_from(g, market, outs, margin=1.0):
    return {o: margin / grid.prob(g, market, o) for o in outs}


def test_fit_recovers_rates_from_1x2_and_total():
    truth = grid.dc_grid(1.7, 0.9)
    fx = Fixture("1", "", "", "H", "A", {"pinnacle": {
        "1X2": _odds_from(truth, "1X2", ("home", "draw", "away")),
        "OU:2.5": _odds_from(truth, "OU:2.5", ("over", "under")),
    }})
    parts = grid.partition_markets(fx, "pinnacle")
    g = grid.fit_grid(parts)
    s, t = grid.summary(g), grid.summary(truth)
    assert s["xg_home"] == pytest.approx(t["xg_home"], abs=0.02)
    assert s["xg_away"] == pytest.approx(t["xg_away"], abs=0.02)
    # 샤프가 내지 않은 마켓도 거의 정확히 끌어낸다
    assert grid.prob(g, "BTTS", "yes") == pytest.approx(grid.prob(truth, "BTTS", "yes"), abs=0.005)


def test_rake_matches_market_exactly_and_margin_is_removed():
    truth = grid.dc_grid(1.4, 1.2)
    odds = _odds_from(truth, "1X2", ("home", "draw", "away"), margin=0.95)  # 5% 마진
    # 모형과 다른 무승부 확률: 격자는 시장 값에 정확히 맞춰져야 한다
    odds["draw"] *= 0.9
    fx = Fixture("1", "", "", "H", "A", {"pinnacle": {"1X2": odds}})
    parts = grid.partition_markets(fx, "pinnacle")
    target = parts[0][1]
    g = grid.fit_grid(parts)
    assert g.sum() == pytest.approx(1.0)
    for o, p in target.items():
        assert grid.prob(g, "1X2", o) == pytest.approx(p, abs=1e-6)


def test_push_markets_are_not_used_for_fitting():
    fx = Fixture("1", "", "", "H", "A", {"pinnacle": {"AH:-1": {"home": 2.0, "away": 1.9}, "OU:2.25": {"over": 1.9, "under": 1.9}}})
    assert grid.partition_markets(fx, "pinnacle") == []


def test_pool_weights():
    a, b = grid.dc_grid(2.0, 0.8), grid.dc_grid(0.8, 2.0)
    assert np.allclose(grid.pool([(a, 1.0), (b, 0.0)]), a)
    mid = grid.pool([(a, 0.5), (b, 0.5)])
    assert grid.prob(mid, "1X2", "home") == pytest.approx(grid.prob(mid, "1X2", "away"), abs=1e-9)

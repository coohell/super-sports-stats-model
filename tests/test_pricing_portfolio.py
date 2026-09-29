import numpy as np
import pytest

from sssm import grid
from sssm.markets import Fixture
from sssm.portfolio import BET365_ACCA_BOOST_EXAMPLE, PortfolioConfig, joint_prob, make_bet, optimize
from sssm.pricing import PricingConfig, ValueFilter, price_all, price_fixture, selections, value_bets

FAIR = {"home": 0.5, "draw": 0.25, "away": 0.25}


def fx(fid, b365, pin, extra_b365=None):
    odds = {"bet365": {"1X2": b365, **(extra_b365 or {})}}
    if pin:
        odds["pinnacle"] = {"1X2": pin}
    return Fixture(fid, "2026-10-01T15:00:00Z", "EPL", f"H{fid}", f"A{fid}", odds)


PIN = {o: 1 / p for o, p in FAIR.items()}  # 마진 없는 샤프 가격


def test_sharp_prices_become_fair_probabilities():
    f = fx("1", {"home": 2.2, "draw": 3.6, "away": 3.6}, PIN)
    sels = {s.outcome: s for s in selections(price_fixture(f))}
    assert sels["home"].fair_prob == pytest.approx(0.5, abs=1e-6)
    assert sels["home"].ev == pytest.approx(0.10, abs=1e-5)
    assert sels["home"].source == "sharp" and sels["home"].sharp_prob == pytest.approx(0.5)
    assert sels["draw"].ev < 0


def test_shrink_controls_edge():
    f = fx("1", {"home": 2.2, "draw": 3.4, "away": 3.4}, PIN)
    full = {s.outcome: s for s in selections(price_fixture(f, cfg=PricingConfig(shrink=1.0)), PricingConfig(shrink=1.0))}
    none = {s.outcome: s for s in selections(price_fixture(f, cfg=PricingConfig(shrink=0.0)), PricingConfig(shrink=0.0))}
    half = {s.outcome: s for s in selections(price_fixture(f, cfg=PricingConfig(shrink=0.5)), PricingConfig(shrink=0.5))}
    assert full["home"].edge == pytest.approx(full["home"].ev)
    assert none["home"].edge < 0  # bet365 만 믿으면 마진 때문에 음수
    assert none["home"].edge < half["home"].edge < full["home"].edge


def test_derived_markets_come_from_the_grid():
    f = fx("1", {"home": 2.0, "draw": 4.0, "away": 4.0}, PIN, {"BTTS": {"yes": 1.9, "no": 1.9}, "AH:-0.75": {"home": 2.4, "away": 1.6}})
    fp = price_fixture(f)
    sels = {(s.market, s.outcome): s for s in selections(fp)}
    btts = sels[("BTTS", "yes")]
    assert btts.source == "derived" and btts.sharp_prob is None
    assert btts.fair_prob == pytest.approx(grid.prob(fp.fair.reshape(11, 11), "BTTS", "yes"))
    ah = sels[("AH:-0.75", "home")]
    # -0.75: 2골 차 이상 승이면 전승, 1골 차 승이면 반승
    assert 0 < ah.fair_prob < sels[("1X2", "home")].fair_prob


def test_no_bet365_or_no_evidence_gives_nothing():
    assert price_fixture(Fixture("1", "", "", "H", "A", {"pinnacle": {"1X2": PIN}})) is None
    assert price_fixture(fx("1", {"home": 2.0, "draw": 4.0, "away": 4.0}, None)) is None


def test_value_filter_uses_conservative_edge():
    f = fx("1", {"home": 2.2, "draw": 3.4, "away": 3.4}, PIN)
    fp = price_fixture(f)
    sels = selections(fp)
    v = value_bets(sels, ValueFilter(min_edge=0.0))
    assert [s.outcome for s in v] == ["home"]
    assert value_bets(sels, ValueFilter(min_edge=0.5)) == []


def _slate(n=4, odds=2.2, cfg=None):
    fixtures = [fx(str(i), {"home": odds, "draw": 3.4, "away": 3.4}, PIN) for i in range(n)]
    fps, sels = price_all(fixtures, None, cfg)
    return {fp.fixture_id: fp for fp in fps}, value_bets(sels, ValueFilter(min_edge=0.0))


def test_multi_math_is_product_of_independent_legs():
    pr, v = _slate(2, cfg=PricingConfig(shrink=1.0))
    b = make_bet(v, pr, PortfolioConfig())
    assert b.odds == pytest.approx(2.2 ** 2)
    assert b.win_prob == pytest.approx(0.25, abs=1e-6)
    assert b.ev == pytest.approx(1.1 ** 2 - 1, abs=1e-5)
    boosted = make_bet(v, pr, PortfolioConfig(acca_bonus=BET365_ACCA_BOOST_EXAMPLE))
    assert boosted.bonus == 0.05 and boosted.ev == pytest.approx(b.ev + 0.05 * (2.2 ** 2 - 1) * 0.25, abs=1e-5)


def test_single_bet_kelly_matches_closed_form():
    pr, v = _slate(1, cfg=PricingConfig(shrink=1.0))
    cfg = PortfolioConfig(kelly_fraction=1.0, max_bet=1.0, max_total=1.0, n_scenarios=40000)
    pf = optimize(v, pr, cfg)
    assert len(pf.bets) == 1
    assert pf.bets[0].stake == pytest.approx((0.5 * 2.2 - 1) / 1.2, abs=0.01)


def test_portfolio_respects_caps_and_one_leg_per_fixture():
    pr, v = _slate(5, cfg=PricingConfig(shrink=1.0))
    cfg = PortfolioConfig(max_legs=3, max_bet=0.02, max_total=0.06, kelly_fraction=0.5, max_bets=6)
    pf = optimize(v, pr, cfg)
    assert pf.bets and len(pf.bets) <= 6
    assert pf.total_stake <= 0.06 + 1e-6
    assert all(b.stake <= 0.02 + 1e-6 for b in pf.bets)
    for b in pf.candidates:
        ids = [s.fixture_id for s in b.legs]
        assert len(ids) == len(set(ids))
    assert any(b.n_legs > 1 for b in pf.candidates)
    assert pf.growth > 0


def test_no_value_no_bets():
    pr, v = _slate(3, odds=1.9)
    assert v == []
    pf = optimize(v, pr)
    assert pf.bets == [] and pf.total_stake == 0


def test_same_game_correlation():
    f = fx("1", {"home": 2.0, "draw": 4.0, "away": 4.0}, PIN, {"OU:2.5": {"over": 1.9, "under": 1.9}})
    fp = price_fixture(f)
    sels = {(s.market, s.outcome): s for s in selections(fp)}
    home, over, under = sels[("1X2", "home")], sels[("OU:2.5", "over")], sels[("OU:2.5", "under")]
    both = joint_prob([home, over], fp)
    indep = home.fair_prob * over.fair_prob
    assert both > indep  # 홈승과 오버는 같이 일어나는 경향
    assert joint_prob([over, under], fp) == 0.0


def test_two_way_sport_uses_h2h_only():
    f = Fixture("1", "", "AFL", "H", "A", {"bet365": {"H2H": {"home": 2.1, "away": 1.8}, "AH:-5.5": {"home": 1.9, "away": 1.9}},
                                          "pinnacle": {"H2H": {"home": 2.0, "away": 2.0}}}, sport="aussierules_afl")
    fp = price_fixture(f)
    sels = selections(fp)
    assert fp.states == "h2h" and {s.market for s in sels} == {"H2H"}
    home = next(s for s in sels if s.outcome == "home")
    assert home.ev == pytest.approx(0.05)
    pf = optimize(value_bets(sels, ValueFilter(min_edge=0.0)), {"1": fp})
    assert np.isfinite(pf.growth)

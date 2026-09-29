import pytest

from sssm.markets import Fixture
from sssm.parlay import Parlay, best_parlays
from sssm.pricing import PricingConfig, ValueFilter, price_fixture, value_bets


class FixedModel:
    def __init__(self, probs):
        self.probs = probs

    def predict(self, home, away):
        return self.probs


def fx(fid="1", b365=None, pin=None):
    odds = {}
    if b365:
        odds["bet365"] = {"1X2": b365}
    if pin:
        odds["pinnacle"] = {"1X2": pin}
    return Fixture(fid, "2026-10-01T15:00:00Z", "EPL", f"H{fid}", f"A{fid}", odds)


FAIR = {"home": 0.5, "draw": 0.25, "away": 0.25}


def test_sharp_only_uses_devigged_pinnacle():
    sels = price_fixture(fx(b365={"home": 2.2, "draw": 3.5, "away": 3.5}, pin={"home": 1.96, "draw": 3.9, "away": 3.9}))
    assert {s.source for s in sels} == {"sharp"}
    assert sum(s.fair_prob for s in sels) == pytest.approx(1.0)
    home = next(s for s in sels if s.outcome == "home")
    assert home.ev > 0.05


def test_blend_weights():
    f = fx(b365={"home": 2.0, "draw": 4.0, "away": 4.0}, pin={"home": 2.0, "draw": 4.0, "away": 4.0})
    model = FixedModel({"1X2": {"home": 0.6, "draw": 0.2, "away": 0.2}})
    sels = price_fixture(f, model, PricingConfig(sharp_weight=0.5))
    home = next(s for s in sels if s.outcome == "home")
    assert home.source == "sharp+model"
    assert home.fair_prob == pytest.approx(0.55)


def test_model_only_needs_higher_edge():
    f = fx(b365={"home": 2.1, "draw": 4.0, "away": 4.0})
    sels = price_fixture(f, FixedModel({"1X2": FAIR}))
    assert value_bets(sels, ValueFilter(min_ev=0.02, model_only_min_ev=0.10)) == []  # EV 5% < 10%
    assert len(value_bets(sels, ValueFilter(min_ev=0.02, model_only_min_ev=0.04))) == 1


def test_no_bet365_no_selection():
    assert price_fixture(fx(pin={"home": 2.0, "draw": 4.0, "away": 4.0})) == []


def _value(fid, odds, p):
    f = fx(fid, b365={"home": odds, "draw": 10.0, "away": 10.0})
    s = [x for x in price_fixture(f, FixedModel({"1X2": {"home": p, "draw": (1 - p) / 2, "away": (1 - p) / 2}}))
         if x.outcome == "home"][0]
    return s


def test_parlay_math():
    a, b = _value("1", 2.0, 0.6), _value("2", 3.0, 0.4)
    p = Parlay([a, b])
    assert p.odds == pytest.approx(6.0)
    assert p.prob == pytest.approx(0.24)
    assert p.ev == pytest.approx((1 + a.ev) * (1 + b.ev) - 1)


def test_best_parlays_one_leg_per_fixture_and_sorted():
    a, b, c = _value("1", 2.0, 0.6), _value("2", 3.0, 0.4), _value("3", 1.8, 0.62)
    dup = _value("1", 2.1, 0.6)
    res = best_parlays([a, b, c, dup], max_legs=3)
    for p in res:
        ids = [s.fixture_id for s in p.legs]
        assert len(ids) == len(set(ids))
    growth = [p.growth for p in res]
    assert growth == sorted(growth, reverse=True)
    by_ev = best_parlays([a, b, c], max_legs=3, sort_by="ev")
    assert len(by_ev[0].legs) == 3  # EV 로만 보면 다리가 많을수록 커 보인다

import numpy as np
import pytest

from sssm import markets as mk
from sssm.model import DixonColes, market_prob


def test_market_keys():
    assert mk.make("OU", 2.5) == "OU:2.5"
    assert mk.split("AH:-1.5") == ("AH", -1.5)
    assert mk.split("1X2") == ("1X2", None)
    assert mk.canonical("OU2.5") == "OU:2.5"  # 옛 표기
    assert mk.outcomes("OU:3.5") == ("over", "under")
    for m in ("OU:2.5", "AH:-0.5", "BTTS", "OU:2.75", "AH:1", "DNB", "TTH:1.5", "CS"):
        assert mk.is_supported(m), m
    assert not mk.is_supported("OU")  # 라인 없음
    assert not mk.is_supported("OU:2.6")
    assert not mk.is_supported("corners:9.5")


def test_labels():
    assert mk.label("OU:2.5", "over") == "오버 2.5"
    assert mk.label("AH:-1.5", "home") == "홈 -1.5"
    assert mk.label("AH:-1.5", "away") == "원정 +1.5"
    assert mk.label("1X2", "draw") == "무"


def _payout(market, outcome, h, a, odds=2.0):
    W, R = mk.settle(market, outcome)
    return W[h, a] * odds + R[h, a]


def test_asian_settlement_rules():
    # 홈 -0.25: 이기면 승, 비기면 반패
    assert _payout("AH:-0.25", "home", 1, 0) == 2.0
    assert _payout("AH:-0.25", "home", 1, 1) == 0.5
    # 원정 +0.25 (같은 마켓 반대쪽): 비기면 반승
    assert _payout("AH:-0.25", "away", 1, 1) == pytest.approx(1.5)
    # 홈 -1: 한 골 차 승은 적특
    assert _payout("AH:-1", "home", 2, 1) == 1.0
    assert _payout("AH:-1", "home", 3, 1) == 2.0
    # 오버 2.75: 3골이면 반승, 2골이면 패
    assert _payout("OU:2.75", "over", 2, 1) == pytest.approx(1.5)
    assert _payout("OU:2.75", "over", 1, 1) == 0.0
    assert _payout("OU:3", "under", 2, 1) == 1.0
    assert _payout("DNB", "away", 0, 0) == 1.0
    assert _payout("TTA:0.5", "over", 0, 1) == 2.0
    assert _payout("CS", "2-1", 2, 1) == 2.0 and _payout("CS", "2-1", 1, 2) == 0.0


def test_outcomes_of_a_market_partition_every_score():
    for m in ("1X2", "OU:2.5", "AH:-1.5", "BTTS", "DC"):
        total = sum(mk.settle(m, o)[0] + mk.settle(m, o)[1] for o in mk.outcomes(m))
        if m == "DC":
            assert (total == 2).all()  # 더블찬스는 결과가 겹친다
        else:
            assert np.allclose(total, 1.0)


def test_score_matrix_market_probabilities_are_consistent(synthetic_league):
    m = DixonColes().fit(synthetic_league)
    s = m.score_matrix("T2", "T7")
    p1 = market_prob(s, "1X2")
    assert sum(p1.values()) == pytest.approx(1.0)
    assert market_prob(s, "AH:-0.5")["home"] == pytest.approx(p1["home"])
    assert market_prob(s, "AH:0.5")["home"] == pytest.approx(p1["home"] + p1["draw"])
    n = s.shape[0]
    h, a = np.indices((n, n))
    assert market_prob(s, "AH:-1.5")["home"] == pytest.approx(s[(h - a) >= 2].sum())
    overs = [market_prob(s, f"OU:{x}")["over"] for x in (0.5, 1.5, 2.5, 3.5, 4.5)]
    assert overs == sorted(overs, reverse=True)
    assert market_prob(s, "OU:0.5")["over"] == pytest.approx(1 - s[0, 0])
    assert market_prob(s, "corners:9.5") is None


def test_predict_only_returns_requested_markets(synthetic_league):
    m = DixonColes().fit(synthetic_league)
    assert set(m.predict("T0", "T1", ["OU:3.5", "AH:-0.5"])) == {"OU:3.5", "AH:-0.5"}
    assert set(m.predict("T0", "T1")) == {"1X2", "OU:2.5", "BTTS"}

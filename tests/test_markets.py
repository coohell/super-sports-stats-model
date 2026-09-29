import numpy as np
import pytest

from sssm import markets as mk
from sssm.model import DixonColes, market_prob


def test_market_keys():
    assert mk.make("OU", 2.5) == "OU:2.5"
    assert mk.split("AH:-1.5") == ("AH", -1.5)
    assert mk.split("1X2") == ("1X2", None)
    assert mk.outcomes("OU:3.5") == ("over", "under")
    assert mk.is_supported("OU:2.5") and mk.is_supported("AH:-0.5") and mk.is_supported("BTTS")
    assert not mk.is_supported("OU:2.75")  # 쿼터 라인
    assert not mk.is_supported("AH:1")  # 푸시가 생기는 정수 라인
    assert not mk.is_supported("OU")  # 라인 없음
    assert not mk.is_supported("corners:9.5")


def test_labels():
    assert mk.label("OU:2.5", "over") == "오버 2.5"
    assert mk.label("AH:-1.5", "home") == "홈 -1.5"
    assert mk.label("AH:-1.5", "away") == "원정 +1.5"
    assert mk.label("1X2", "draw") == "무"


def test_score_matrix_market_probabilities_are_consistent(synthetic_league):
    m = DixonColes().fit(synthetic_league)
    s = m.score_matrix("T2", "T7")
    p1 = market_prob(s, "1X2")
    assert sum(p1.values()) == pytest.approx(1.0)
    # 핸디캡 -0.5 는 홈 승, +0.5 는 홈 승 + 무 와 같다
    assert market_prob(s, "AH:-0.5")["home"] == pytest.approx(p1["home"])
    assert market_prob(s, "AH:0.5")["home"] == pytest.approx(p1["home"] + p1["draw"])
    # 1.5 골 핸디캡은 홈이 2골 차 이상으로 이겨야 한다
    n = s.shape[0]
    h, a = np.indices((n, n))
    assert market_prob(s, "AH:-1.5")["home"] == pytest.approx(s[(h - a) >= 2].sum())
    # 오버 라인이 높을수록 확률은 줄어든다
    overs = [market_prob(s, f"OU:{x}")["over"] for x in (0.5, 1.5, 2.5, 3.5, 4.5)]
    assert overs == sorted(overs, reverse=True)
    assert market_prob(s, "OU:0.5")["over"] == pytest.approx(1 - s[0, 0])
    assert market_prob(s, "OU:2.75") is None and market_prob(s, "corners:9.5") is None


def test_predict_only_returns_requested_markets(synthetic_league):
    m = DixonColes().fit(synthetic_league)
    assert set(m.predict("T0", "T1", ["OU:3.5", "AH:-0.5"])) == {"OU:3.5", "AH:-0.5"}
    assert set(m.predict("T0", "T1")) == {"1X2", "OU:2.5", "BTTS"}

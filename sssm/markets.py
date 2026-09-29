"""마켓 정의와 정산(settlement).

모든 축구 마켓은 최종 스코어 (h, a) 의 함수로 정산된다. 그래서 선택지 하나를
스코어 격자 위의 두 배열로 표현한다.

  W[h, a] = 이 스코어에서 배당만큼 이기는 비율 (0, 0.5, 1)
  R[h, a] = 이 스코어에서 원금이 돌아오는 비율 (적특/반환, 0, 0.5, 1)

배당 o 에 1원 걸었을 때 돌려받는 금액은 W*o + R 이다. 아시안 쿼터 라인
(예: -0.75)은 두 라인에 절반씩 건 것과 같다. bet365 멀티(조합)의 규칙도 같은
식으로 표현된다: 적특 폴은 배당 1, 반승은 (o+1)/2, 반패는 0.5 로 계산되므로
조합의 돌려받는 금액은 폴별 (W*o + R) 의 곱이다.

마켓 키
  1X2           home / draw / away
  DC            1X / 12 / X2          (더블 찬스)
  DNB           home / away           (무승부 적특)
  OU:{line}     over / under          예: OU:2.5, OU:2.25(쿼터), OU:3(정수, 적특 있음)
  AH:{line}     home / away           홈 기준 핸디캡, 예: AH:-0.5, AH:0.25
  BTTS          yes / no
  TTH:{line}    over / under          홈팀 득점 오버/언더
  TTA:{line}    over / under          원정팀 득점 오버/언더
  CS            "2-1" 같은 정확한 스코어
  H2H           home / away           무승부 없는 종목(격자 없이 2가지 결과)
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Dict, Optional, Tuple

import numpy as np

MAX_GOALS = 10
N = MAX_GOALS + 1
_H, _A = np.indices((N, N))

OUTCOMES = {
    "1X2": ("home", "draw", "away"),
    "DC": ("1X", "12", "X2"),
    "DNB": ("home", "away"),
    "OU": ("over", "under"),
    "AH": ("home", "away"),
    "BTTS": ("yes", "no"),
    "TTH": ("over", "under"),
    "TTA": ("over", "under"),
    "H2H": ("home", "away"),
}

_KEY = re.compile(r"^(OU|AH|TTH|TTA):?([+-]?\d+(?:\.\d+)?)$")  # "OU2.5" 옛 표기도 읽는다
LINE_KINDS = ("OU", "AH", "TTH", "TTA")


def make(kind: str, line: Optional[float] = None) -> str:
    return kind if line is None else f"{kind}:{line:g}"


def parse(market: str) -> Tuple[str, Optional[float]]:
    """"OU:2.5" -> ("OU", 2.5), "1X2" -> ("1X2", None)."""
    m = _KEY.match(market)
    if m:
        return m.group(1), float(m.group(2))
    if market in OUTCOMES or market == "CS":
        return market, None
    raise ValueError(f"알 수 없는 마켓: {market}")


split = parse


def canonical(market: str) -> str:
    """"OU2.5" 같은 옛 표기를 "OU:2.5" 로 바꾼다."""
    kind, line = parse(market)
    return make(kind, line)


def is_quarter_or_half(line: float) -> bool:
    return abs(line * 4 - round(line * 4)) < 1e-9


def is_supported(market: str) -> bool:
    try:
        kind, line = parse(market)
    except ValueError:
        return False
    if kind in LINE_KINDS:
        return line is not None and is_quarter_or_half(line)
    return True


def outcomes(market: str) -> Tuple[str, ...]:
    kind, _ = parse(market)
    if kind == "CS":
        raise ValueError("CS 는 결과가 스코어별로 따로 있다")
    return OUTCOMES[kind]


def is_grid_market(market: str) -> bool:
    return parse(market)[0] != "H2H"


def _half_lines(line: float) -> Tuple[float, ...]:
    """쿼터 라인은 두 개의 반 라인으로 쪼갠다 (2.25 -> 2.0, 2.5)."""
    frac = round((line * 4) % 2)  # 0: 정수 또는 .5, 1: 쿼터
    if frac == 1:
        return (line - 0.25, line + 0.25)
    return (line,)


def _line_settle(margin: np.ndarray, line: float) -> Tuple[np.ndarray, np.ndarray]:
    """margin + line 이 양수면 승, 0 이면 적특 (쿼터 라인은 절반씩)."""
    halves = _half_lines(line)
    W = np.zeros(margin.shape)
    R = np.zeros(margin.shape)
    for l in halves:
        x = margin + l
        W += (x > 1e-9) / len(halves)
        R += (np.abs(x) <= 1e-9) / len(halves)
    return W, R


@lru_cache(maxsize=None)
def settle(market: str, outcome: str) -> Tuple[np.ndarray, np.ndarray]:
    """(W, R) 격자를 돌려준다. 읽기 전용으로 캐시한다."""
    kind, line = parse(market)
    h, a = _H, _A
    zero = np.zeros((N, N))
    if kind == "1X2":
        W = {"home": h > a, "draw": h == a, "away": h < a}[outcome].astype(float)
        R = zero
    elif kind == "DC":
        W = {"1X": h >= a, "12": h != a, "X2": h <= a}[outcome].astype(float)
        R = zero
    elif kind == "DNB":
        W = ((h > a) if outcome == "home" else (h < a)).astype(float)
        R = (h == a).astype(float)
    elif kind in ("OU", "TTH", "TTA"):
        goals = {"OU": h + a, "TTH": h, "TTA": a}[kind].astype(float)
        # 오버: goals - line > 0 이면 승. 언더: line - goals > 0 이면 승.
        if outcome == "over":
            W, R = _line_settle(goals, -line)
        else:
            W, R = _line_settle(-goals, line)
    elif kind == "AH":
        # 핸디캡은 홈 기준. 원정 쪽은 부호를 뒤집는다 (AH-0.5 원정 = 원정 +0.5).
        margin = (h - a) if outcome == "home" else (a - h)
        W, R = _line_settle(margin.astype(float), line if outcome == "home" else -line)
    elif kind == "BTTS":
        both = (h > 0) & (a > 0)
        W = (both if outcome == "yes" else ~both).astype(float)
        R = zero
    elif kind == "CS":
        hs, as_ = (int(x) for x in outcome.split("-"))
        W = ((h == hs) & (a == as_)).astype(float)
        R = zero
    else:
        raise ValueError(f"격자로 정산할 수 없는 마켓: {market}")
    W = np.asarray(W, dtype=float)
    R = np.asarray(R, dtype=float)
    W.setflags(write=False)
    R.setflags(write=False)
    return W, R


def label(market: str, outcome: str) -> str:
    kind, line = parse(market)
    names = {"home": "홈", "away": "원정", "draw": "무"}
    if kind == "1X2":
        return {"home": "홈승", "draw": "무", "away": "원정승"}[outcome]
    if kind == "H2H":
        return {"home": "홈승", "away": "원정승"}[outcome]
    if kind == "DC":
        return f"더블찬스 {outcome}"
    if kind == "DNB":
        return f"무승부환불 {names[outcome]}"
    if kind == "OU":
        return f"{'오버' if outcome == 'over' else '언더'} {line:g}"
    if kind in ("TTH", "TTA"):
        who = "홈" if kind == "TTH" else "원정"
        return f"{who}득점 {'오버' if outcome == 'over' else '언더'} {line:g}"
    if kind == "AH":
        l = line if outcome == "home" else -line
        return f"{names[outcome]} {l:+g}"
    if kind == "BTTS":
        return "양팀득점 O" if outcome == "yes" else "양팀득점 X"
    if kind == "CS":
        return f"스코어 {outcome}"
    return f"{market} {outcome}"


@dataclass
class Fixture:
    """한 경기와 북메이커별 배당.

    odds[book][market][outcome] = 소수 배당. book 은 "bet365", "pinnacle" 등.
    """

    fixture_id: str
    kickoff: str
    league: str
    home: str
    away: str
    odds: Dict[str, Dict[str, Dict[str, float]]] = field(default_factory=dict)
    sport: str = "football"

    def market(self, book: str, market: str) -> Optional[Dict[str, float]]:
        """한 북의 한 마켓 배당. 결과가 모두 있고 유효할 때만 돌려준다."""
        m = self.odds.get(book, {}).get(market)
        if not m or not is_supported(market):
            return None
        kind, _ = parse(market)
        if kind != "CS" and set(m) != set(OUTCOMES[kind]):
            return None
        if any(v is None or not np.isfinite(v) or v <= 1.0 for v in m.values()):
            return None
        return {k: float(v) for k, v in m.items()}

    @property
    def match(self) -> str:
        return f"{self.home} vs {self.away}"

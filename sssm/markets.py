"""마켓/선택지 공통 자료형.

마켓 키 규칙 (라인이 있는 마켓은 "종류:라인"):
  1X2      승무패 (home/draw/away)
  H2H      무승부 없는 종목의 승패 (home/away)
  BTTS     양팀 득점 (yes/no)
  OU:2.5   총득점 오버/언더 (over/under). 라인은 x.5 만 지원(푸시가 없어야 함)
  AH:-1.5  홈 기준 아시안 핸디캡 (home/away). 라인은 x.5 만 지원
한 마켓의 결과들은 서로 배타적이며 확률의 합이 1이다.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Optional, Tuple

OUTCOMES: Dict[str, Tuple[str, ...]] = {
    "1X2": ("home", "draw", "away"),
    "H2H": ("home", "away"),
    "BTTS": ("yes", "no"),
    "OU": ("over", "under"),
    "AH": ("home", "away"),
}
LINE_KINDS = ("OU", "AH")

_LABELS = {
    "1X2": {"home": "홈승", "draw": "무", "away": "원정승"},
    "H2H": {"home": "홈승", "away": "원정승"},
    "BTTS": {"yes": "양팀득점 O", "no": "양팀득점 X"},
}


def is_half_line(line: float) -> bool:
    return abs((line * 2) % 2 - 1) < 1e-9


def make(kind: str, line: Optional[float] = None) -> str:
    return kind if line is None else f"{kind}:{line:g}"


def split(market: str) -> Tuple[str, Optional[float]]:
    kind, _, rest = market.partition(":")
    return kind, (float(rest) if rest else None)


def is_supported(market: str) -> bool:
    try:
        kind, line = split(market)
    except ValueError:
        return False
    if kind not in OUTCOMES:
        return False
    if kind in LINE_KINDS:
        return line is not None and is_half_line(line)
    return line is None


def outcomes(market: str) -> Tuple[str, ...]:
    return OUTCOMES[split(market)[0]]


def label(market: str, outcome: str) -> str:
    kind, line = split(market)
    if kind == "OU":
        return f"{'오버' if outcome == 'over' else '언더'} {line:g}"
    if kind == "AH":
        h = line if outcome == "home" else -line
        return f"{'홈' if outcome == 'home' else '원정'} {h:+g}"
    return _LABELS[kind][outcome]


@dataclass
class Fixture:
    """한 경기와 북메이커별 배당.

    odds[book][market][outcome] = 소수 배당. book 은 "bet365", "pinnacle".
    """

    fixture_id: str
    kickoff: str
    league: str
    home: str
    away: str
    odds: Dict[str, Dict[str, Dict[str, float]]] = field(default_factory=dict)

    def market(self, book: str, market: str) -> Optional[Dict[str, float]]:
        m = self.odds.get(book, {}).get(market)
        if not m or set(m) != set(outcomes(market)):
            return None
        if any(v is None or v <= 1.0 for v in m.values()):
            return None
        return m


@dataclass
class Selection:
    """bet365 에서 걸 수 있는 하나의 선택지와 그 공정 확률 추정."""

    fixture_id: str
    kickoff: str
    league: str
    home: str
    away: str
    market: str
    outcome: str
    odds: float  # bet365 배당
    fair_prob: float  # 최종 공정 확률 추정
    sharp_prob: Optional[float] = None  # Pinnacle 마진 제거 확률
    model_prob: Optional[float] = None  # Dixon-Coles 모델 확률
    source: str = ""  # fair_prob 를 만든 근거: "sharp+model", "sharp", "model"

    @property
    def ev(self) -> float:
        return self.fair_prob * self.odds - 1.0

    @property
    def label(self) -> str:
        return label(self.market, self.outcome)

    @property
    def match(self) -> str:
        return f"{self.home} vs {self.away}"

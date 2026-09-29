"""마켓/선택지 공통 자료형."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Optional

# 지원 마켓과 그 결과들. 한 마켓의 결과들은 서로 배타적이며 합이 1이다.
MARKETS: Dict[str, tuple] = {
    "1X2": ("home", "draw", "away"),
    "H2H": ("home", "away"),  # 무승부 없는 종목의 승패
    "OU2.5": ("over", "under"),
    "BTTS": ("yes", "no"),
}

LABELS = {
    ("1X2", "home"): "홈승",
    ("1X2", "draw"): "무",
    ("1X2", "away"): "원정승",
    ("H2H", "home"): "홈승",
    ("H2H", "away"): "원정승",
    ("OU2.5", "over"): "오버 2.5",
    ("OU2.5", "under"): "언더 2.5",
    ("BTTS", "yes"): "양팀득점 O",
    ("BTTS", "no"): "양팀득점 X",
}


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
        if not m or set(m) != set(MARKETS[market]):
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
        return LABELS.get((self.market, self.outcome), f"{self.market} {self.outcome}")

    @property
    def match(self) -> str:
        return f"{self.home} vs {self.away}"

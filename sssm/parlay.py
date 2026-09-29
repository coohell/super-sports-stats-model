"""+EV 선택지로 만들 수 있는 조합(멀티) 중 가장 강한 것을 고른다.

"가장 강한 조합"의 기준은 EV 가 아니라 기대 로그 성장률(켈리 기준)이다.
조합 EV 는 다리 수가 늘수록 (1+e1)(1+e2)... − 1 로 커 보이지만, 적중 확률이
곱으로 줄어 자금 성장에는 오히려 불리할 수 있다. 로그 성장률은 이 둘을
함께 반영하므로 단식과 조합을 같은 잣대로 비교할 수 있다.

가정: 서로 다른 경기의 결과는 독립. 같은 경기에서 두 다리를 고르지 않는다
(bet365 일반 멀티는 같은 경기 중복을 허용하지 않고, 상관관계도 크다).
"""
from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations
from math import prod
from typing import List, Sequence

from .markets import Selection
from .odds import kelly, log_growth


@dataclass
class Parlay:
    legs: Sequence[Selection]
    kelly_fraction: float = 0.25

    @property
    def odds(self) -> float:
        return prod(s.odds for s in self.legs)

    @property
    def prob(self) -> float:
        return prod(s.fair_prob for s in self.legs)

    @property
    def ev(self) -> float:
        return self.prob * self.odds - 1.0

    @property
    def stake(self) -> float:
        """자본 대비 권장 배팅 비율 (분수 켈리)."""
        return kelly(self.prob, self.odds, self.kelly_fraction)

    @property
    def growth(self) -> float:
        """권장 비율로 걸었을 때 기대 로그 성장률."""
        return float(log_growth(self.prob, self.odds, self.stake))

    def to_dict(self) -> dict:
        return {
            "legs": [
                {"match": s.match, "kickoff": s.kickoff, "pick": s.label, "odds": round(s.odds, 3),
                 "fair_prob": round(s.fair_prob, 4), "ev": round(s.ev, 4), "source": s.source}
                for s in self.legs
            ],
            "odds": round(self.odds, 3),
            "prob": round(self.prob, 5),
            "ev": round(self.ev, 4),
            "stake": round(self.stake, 5),
            "growth": round(self.growth, 7),
        }


def best_parlays(
    value: List[Selection],
    max_legs: int = 3,
    min_legs: int = 1,
    top: int = 10,
    pool: int = 15,
    kelly_fraction: float = 0.25,
    sort_by: str = "growth",
) -> List[Parlay]:
    """value 선택지로 가능한 조합을 만들어 sort_by 기준 상위 top 개를 돌려준다.

    pool: EV 상위 몇 개 선택지만 조합에 쓸지 (조합 폭발 방지).
    min_legs=1 이면 단식도 함께 비교한다.
    """
    cands = sorted(value, key=lambda s: s.ev, reverse=True)[:pool]
    out: List[Parlay] = []
    for k in range(max(1, min_legs), max_legs + 1):
        for legs in combinations(cands, k):
            if len({s.fixture_id for s in legs}) < k:
                continue
            p = Parlay(legs, kelly_fraction)
            if p.ev > 0:
                out.append(p)
    key = {"growth": lambda p: p.growth, "ev": lambda p: p.ev}[sort_by]
    return sorted(out, key=key, reverse=True)[:top]

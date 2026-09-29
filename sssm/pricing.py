"""공정 확률 추정과 bet365 선택지 가격 매기기.

원칙: 시장이 가장 정확하다. 과거 EPL 검증에서 자체 팀 전력 모델은 bet365 시가보다도
부정확했고(docs/backtest_epl_2021_2026.md), Pinnacle 에 섞으면 오히려 나빠졌다. 그래서

1. 공정 확률은 샤프 북(Pinnacle) 배당의 마진을 빼서 만든 스코어 격자에서 온다
   (sssm/grid.py). 샤프 북이 안 낸 마켓(BTTS, 팀 득점, 다른 핸디캡 라인)과
   같은 경기 안 상관관계도 이 격자에서 일관되게 나온다.
2. 자체 모델은 model_weight 만큼만 로그 풀링으로 섞는다. 기본값 0 이며
   백테스트에서 가중치를 벌어야 올린다.
3. 샤프 가격과 bet365 가격이 다를 때 그 차이를 전부 믿지 않는다. 과거 데이터에서
   예측 EV 중 실제로 마감까지 살아남은 비율(shrink)만큼만 믿고, 나머지는 bet365 쪽으로
   당긴 "보수적 격자"로 배팅 크기를 정한다 (sssm/calibrate.py).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Sequence

import numpy as np

from . import grid as gridlib
from . import markets as mk
from .markets import Fixture
from .odds import devig


@dataclass
class PricingConfig:
    soft_book: str = "bet365"
    sharp_books: Sequence[str] = ("pinnacle",)  # 앞에 있을수록 우선
    shrink: float = 0.75  # 샤프-소프트 차이 중 믿는 비율. EPL 2012-26 0.76, 챔피언십 2010-20 0.74 (python -m sssm calibrate)
    model_weight: float = 0.0  # 자체 모델 로그 풀링 가중치
    model_only_shrink: float = 0.2  # 샤프 가격이 없고 모델만 있을 때 믿는 비율
    markets: Optional[Sequence[str]] = None  # None 이면 bet365 가 낸 지원 마켓 전부


@dataclass
class Selection:
    """bet365 에서 걸 수 있는 선택지 하나.

    W, R: 결과 상태별 승/적특 비율 (축구는 121칸 스코어 격자를 편 벡터).
    fair_prob: 공정 확률 기준 적중 확률 (반승은 0.5 로 셈).
    ev: 공정 확률 기준 기대값. edge: 보수적(shrink) 기준 기대값 — 배팅 판단은 edge 로 한다.
    """

    fixture_id: str
    kickoff: str
    league: str
    home: str
    away: str
    market: str
    outcome: str
    odds: float
    fair_prob: float
    ev: float
    edge: float
    source: str  # sharp | sharp+model | derived | model
    sharp_prob: Optional[float] = None  # 샤프 북이 이 마켓을 직접 냈을 때 마진 뺀 확률
    model_prob: Optional[float] = None
    W: np.ndarray = field(default=None, repr=False)
    R: np.ndarray = field(default=None, repr=False)

    @property
    def label(self) -> str:
        return mk.label(self.market, self.outcome)

    @property
    def match(self) -> str:
        return f"{self.home} vs {self.away}"

    push_prob: float = 0.0  # 공정 확률 기준 적특(반환) 비율

    @property
    def fair_odds(self) -> float:
        """이 배당이면 EV 가 0 이다: E[W]·o + E[R] = 1."""
        return float("inf") if self.fair_prob <= 0 else (1.0 - self.push_prob) / self.fair_prob

    def payoff(self) -> np.ndarray:
        """상태별 1원당 돌려받는 금액."""
        return self.W * self.odds + self.R

    def to_dict(self) -> dict:
        r = lambda x: None if x is None else round(float(x), 4)  # noqa: E731
        return {
            "fixture_id": self.fixture_id, "kickoff": self.kickoff, "league": self.league, "match": self.match,
            "market": self.market, "outcome": self.outcome, "pick": self.label, "odds": self.odds,
            "fair_prob": r(self.fair_prob), "sharp_prob": r(self.sharp_prob), "model_prob": r(self.model_prob),
            "ev": r(self.ev), "edge": r(self.edge), "source": self.source,
        }


@dataclass
class FixturePricing:
    """한 경기의 확률 분포들. 모두 같은 상태 공간(스코어 격자 또는 2결과) 위에 있다."""

    fixture: Fixture
    fair: np.ndarray  # 공정 확률 (평평한 벡터)
    conservative: np.ndarray  # 배팅 크기용 보수적 확률
    source: str
    sharp_markets: List[str]
    states: str  # "grid" | "h2h"

    @property
    def fixture_id(self) -> str:
        return self.fixture.fixture_id


def _h2h_probs(fx: Fixture, book: str) -> Optional[np.ndarray]:
    o = fx.market(book, "H2H")
    return None if not o else devig([o["home"], o["away"]])


def _h2h_WR(outcome: str):
    W = np.array([1.0, 0.0]) if outcome == "home" else np.array([0.0, 1.0])
    return W, np.zeros(2)


def price_fixture(fx: Fixture, model=None, cfg: Optional[PricingConfig] = None) -> Optional[FixturePricing]:
    """경기 하나의 공정/보수적 확률 분포를 만든다. 근거가 없으면 None."""
    cfg = cfg or PricingConfig()
    soft = fx.odds.get(cfg.soft_book)
    if not soft:
        return None

    if fx.sport != "football" or ("H2H" in soft and "1X2" not in soft):
        # 무승부 없는 종목: 2결과 상태
        soft_p = _h2h_probs(fx, cfg.soft_book)
        sharp_p = next((p for b in cfg.sharp_books if (p := _h2h_probs(fx, b)) is not None), None)
        if soft_p is None or sharp_p is None:
            return None
        cons = cfg.shrink * np.log(sharp_p) + (1 - cfg.shrink) * np.log(soft_p)
        cons = np.exp(cons) / np.exp(cons).sum()
        return FixturePricing(fx, sharp_p, cons, "sharp", ["H2H"], "h2h")

    soft_parts = gridlib.partition_markets(fx, cfg.soft_book)
    soft_grid = gridlib.fit_grid(soft_parts) if soft_parts else None
    sharp_grid, sharp_markets = None, []
    for book in cfg.sharp_books:
        parts = gridlib.partition_markets(fx, book)
        if parts:
            # 샤프 북에 총득점 마켓이 없으면 bet365 총득점을 약하게 참고해 격자 모양을 잡는다
            extra = [p for p in soft_parts if gridlib.parse(p[0])[0] in gridlib.TOTAL_KINDS] \
                if not gridlib.has_totals(parts) else None
            sharp_grid, sharp_markets = gridlib.fit_grid(parts, extra=extra), [m for m, _ in parts]
            break

    model_grid = None
    if model is not None and getattr(model, "knows", lambda t: False)(fx.home) and model.knows(fx.away):
        model_grid = model.score_matrix(fx.home, fx.away)

    if sharp_grid is not None:
        if model_grid is not None and cfg.model_weight > 0:
            fair = gridlib.pool([(sharp_grid, 1 - cfg.model_weight), (model_grid, cfg.model_weight)])
            source = "sharp+model"
        else:
            fair, source = sharp_grid, "sharp"
        shrink = cfg.shrink
    elif model_grid is not None:
        fair, source, shrink = model_grid, "model", cfg.model_only_shrink
    else:
        return None

    cons = fair if soft_grid is None else gridlib.pool([(fair, shrink), (soft_grid, 1 - shrink)])
    return FixturePricing(fx, fair.ravel(), cons.ravel(), source, sharp_markets, "grid")


def selections(fp: FixturePricing, cfg: Optional[PricingConfig] = None) -> List[Selection]:
    """bet365 가 낸 모든 선택지에 공정 확률과 EV 를 붙인다."""
    cfg = cfg or PricingConfig()
    fx = fp.fixture
    out: List[Selection] = []
    for market in fx.odds.get(cfg.soft_book, {}):
        if not mk.is_supported(market):
            continue
        if cfg.markets is not None and mk.canonical(market) not in {mk.canonical(m) for m in cfg.markets}:
            continue
        kind, _ = mk.parse(market)
        if (kind == "H2H") != (fp.states == "h2h"):
            continue  # 2결과 종목은 승패만, 축구는 격자 마켓만
        prices = fx.market(cfg.soft_book, market)
        if not prices:
            continue
        sharp_direct = None
        for book in cfg.sharp_books:
            so = fx.market(book, market)
            if so and kind != "CS":
                outs = list(so)
                sharp_direct = dict(zip(outs, devig([so[o] for o in outs])))
                break
        for outcome, odds in prices.items():
            if kind == "H2H":
                W, R = _h2h_WR(outcome)
            else:
                W, R = (x.ravel() for x in mk.settle(market, outcome))
            fair_ret = float(fp.fair @ (W * odds + R))
            cons_ret = float(fp.conservative @ (W * odds + R))
            src = fp.source
            if src.startswith("sharp") and mk.canonical(market) not in {mk.canonical(m) for m in fp.sharp_markets}:
                src = "derived"  # 샤프 북이 이 마켓을 직접 내지 않아 격자에서 끌어낸 확률
            out.append(Selection(
                fixture_id=fx.fixture_id, kickoff=fx.kickoff, league=fx.league, home=fx.home, away=fx.away,
                market=mk.canonical(market), outcome=outcome, odds=float(odds),
                fair_prob=float(fp.fair @ W), ev=fair_ret - 1.0, edge=cons_ret - 1.0, source=src,
                sharp_prob=None if sharp_direct is None else float(sharp_direct.get(outcome, np.nan)),
                W=W, R=R, push_prob=float(fp.fair @ R),
            ))
    return out


@dataclass
class ValueFilter:
    min_edge: float = 0.005  # 보수적 기대값 문턱
    min_prob: float = 0.05
    max_odds: float = 15.0
    allow_derived: bool = True  # 샤프가 직접 안 낸 마켓(격자에서 끌어낸 가격)도 쓸지
    derived_extra_edge: float = 0.01  # 끌어낸 가격은 모형 오차가 있어 이만큼 더 요구한다


def value_bets(sels: Iterable[Selection], flt: Optional[ValueFilter] = None) -> List[Selection]:
    flt = flt or ValueFilter()
    keep = [s for s in sels
            if s.edge >= flt.min_edge + (flt.derived_extra_edge if s.source == "derived" else 0.0)
            and s.fair_prob >= flt.min_prob and s.odds <= flt.max_odds
            and (flt.allow_derived or s.source != "derived")]
    return sorted(keep, key=lambda s: s.edge, reverse=True)


def price_all(fixtures: Iterable[Fixture], model=None, cfg: Optional[PricingConfig] = None):
    """(경기별 가격, 모든 선택지) 를 돌려준다."""
    fps, sels = [], []
    for fx in fixtures:
        fp = price_fixture(fx, model, cfg)
        if fp is None:
            continue
        fps.append(fp)
        sels.extend(selections(fp, cfg))
    return fps, sels

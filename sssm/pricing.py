"""공정 확률 추정과 bet365 가치(value) 선택지 찾기.

공정 확률 = sharp_weight × Pinnacle(마진 제거) + (1 − sharp_weight) × Dixon-Coles
- Pinnacle 은 세계에서 가장 정확한 배당으로 알려져 있어 기본 가중치가 높다.
- Pinnacle 배당이 없으면 모델만 쓰되, 더 높은 EV 문턱을 요구한다.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, List, Optional

from . import markets as mk
from .markets import Fixture, Selection
from .odds import devig


@dataclass
class PricingConfig:
    sharp_weight: float = 0.8
    devig_method: str = "power"
    markets: Optional[tuple] = None  # None 이면 bet365 가 제공하는 지원 마켓 전부


@dataclass
class ValueFilter:
    min_ev: float = 0.02  # Pinnacle 근거가 있을 때 최소 EV
    model_only_min_ev: float = 0.10  # 모델만 근거일 때 최소 EV
    min_prob: float = 0.05
    max_odds: float = 15.0


def price_fixture(fx: Fixture, model=None, cfg: Optional[PricingConfig] = None) -> List[Selection]:
    cfg = cfg or PricingConfig()
    offered = [m for m in fx.odds.get("bet365", {}) if mk.is_supported(m)]
    if cfg.markets is not None:
        offered = [m for m in offered if m in cfg.markets]
    model_probs = model.predict(fx.home, fx.away, offered) if model is not None and offered else None
    out: List[Selection] = []
    for market in offered:
        b365 = fx.market("bet365", market)
        if not b365:
            continue
        outcomes = mk.outcomes(market)
        sharp_odds = fx.market("pinnacle", market)
        sharp = dict(zip(outcomes, devig([sharp_odds[o] for o in outcomes], cfg.devig_method))) if sharp_odds else None
        mp = model_probs.get(market) if model_probs else None

        if sharp and mp:
            w = cfg.sharp_weight
            fair = {o: w * sharp[o] + (1 - w) * mp[o] for o in outcomes}
            source = "sharp+model"
        elif sharp:
            fair, source = sharp, "sharp"
        elif mp:
            fair, source = mp, "model"
        else:
            continue

        for o in outcomes:
            out.append(
                Selection(
                    fixture_id=fx.fixture_id, kickoff=fx.kickoff, league=fx.league,
                    home=fx.home, away=fx.away, market=market, outcome=o,
                    odds=float(b365[o]), fair_prob=float(fair[o]),
                    sharp_prob=float(sharp[o]) if sharp else None,
                    model_prob=float(mp[o]) if mp else None,
                    source=source,
                )
            )
    return out


def price_all(fixtures: Iterable[Fixture], model=None, cfg: Optional[PricingConfig] = None) -> List[Selection]:
    return [s for fx in fixtures for s in price_fixture(fx, model, cfg)]


def value_bets(selections: Iterable[Selection], flt: Optional[ValueFilter] = None) -> List[Selection]:
    flt = flt or ValueFilter()
    keep = []
    for s in selections:
        threshold = flt.model_only_min_ev if s.source == "model" else flt.min_ev
        if s.ev >= threshold and s.fair_prob >= flt.min_prob and s.odds <= flt.max_odds:
            keep.append(s)
    return sorted(keep, key=lambda s: s.ev, reverse=True)

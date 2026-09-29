"""최강 조합: 단식과 멀티를 한꺼번에 놓고 자금 성장률이 가장 큰 배팅 묶음을 고른다.

왜 "최강 조합 하나"가 아니라 포트폴리오인가
  같은 날 여러 +EV 선택지가 있으면, 켈리 이론상 성장률이 가장 큰 방법은 단식과
  그 선택지들로 만든 멀티를 적절한 비율로 "함께" 거는 것이다. 멀티 하나에 몰면
  적중 확률이 곱으로 줄어 파산 위험이 커지고, 단식만 걸면 엣지가 복리로 붙는
  효과를 놓친다. 그래서 후보(단식 + 2~N폴 멀티)를 만들고, 기대 로그 자산
  E[log(1 + Σ f_j (G_j − 1))] 을 최대화하는 비율 f 를 한 번에 푼다.

상관관계
  서로 다른 경기는 독립으로 본다. 같은 경기 안의 선택지들은 같은 스코어 격자에서
  함께 뽑히므로 상관이 자동으로 반영된다(예: 같은 날 A 경기 홈승 단식과 A 홈승이
  들어간 멀티는 같이 맞고 같이 틀린다). bet365 일반 멀티는 같은 경기 두 폴을 허용하지
  않으므로 멀티 후보는 경기당 한 폴만 쓴다. 같은 경기 조합(Bet Builder) 가격을
  평가하려면 joint_prob() 를 쓴다.

위험 관리
  켈리 분수(기본 1/4), 배팅 하나 상한, 하루 총액 상한을 둔다. 확률은 보수적 격자
  (샤프-소프트 차이를 shrink 만큼만 믿은 것)에서 뽑는다.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from itertools import combinations
from math import prod
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np
from scipy.optimize import minimize

from .pricing import FixturePricing, Selection

# bet365 의 축구 "Acca Boost" 는 지역·시기마다 조건이 달라 기본값은 끈다.
# 예시(영국, 폴당 최소 배당 1.2): 2폴 5%, 3폴 10%, 4폴 15%, 5폴 20% ... 14폴 이상 70%.
BET365_ACCA_BOOST_EXAMPLE = {2: 0.05, 3: 0.10, 4: 0.15, 5: 0.20, 6: 0.25, 7: 0.30, 8: 0.35, 9: 0.40,
                             10: 0.45, 11: 0.50, 12: 0.55, 13: 0.60, 14: 0.70}


@dataclass
class PortfolioConfig:
    kelly_fraction: float = 0.25
    max_legs: int = 3
    pool: int = 10  # 멀티에 쓸 상위 단식 수 (후보 폭발 방지)
    max_bet: float = 0.03  # 배팅 하나 최대 (자본 대비)
    max_total: float = 0.15  # 하루 총 배팅 최대
    min_stake: float = 0.001  # 이보다 작은 배팅은 버린다 (자본 대비)
    max_bets: int = 8  # 실제로 걸 수 있게 배팅 수를 제한한다 (비중 큰 순으로 남기고 다시 푼다)
    n_scenarios: int = 20000
    seed: int = 7
    singles: bool = True
    acca_bonus: Dict[int, float] = field(default_factory=dict)
    bonus_min_leg_odds: float = 1.2


@dataclass
class Bet:
    legs: Tuple[Selection, ...]
    bonus: float = 0.0  # 모든 폴이 완전히 맞았을 때 순이익에 더해 주는 비율
    stake: float = 0.0  # 자본 대비 배팅 비율 (최적화 후)
    fair_ret: float = 0.0  # 공정 확률 기준 1원당 기대 돌려받는 금액
    cons_ret: float = 0.0  # 보수적 확률 기준
    win_prob: float = 0.0  # 공정 확률 기준 모든 폴이 (적어도 반 이상) 맞을 확률

    @property
    def n_legs(self) -> int:
        return len(self.legs)

    @property
    def odds(self) -> float:
        return prod(s.odds for s in self.legs)

    @property
    def ev(self) -> float:
        return self.fair_ret - 1.0

    @property
    def edge(self) -> float:
        return self.cons_ret - 1.0

    @property
    def kind(self) -> str:
        return "단식" if self.n_legs == 1 else f"{self.n_legs}폴 멀티"

    def to_dict(self, bankroll: Optional[float] = None) -> dict:
        d = {
            "kind": self.kind,
            "legs": [{"match": s.match, "kickoff": s.kickoff, "pick": s.label, "market": s.market,
                      "outcome": s.outcome, "odds": s.odds, "fair_prob": round(s.fair_prob, 4),
                      "ev": round(s.ev, 4), "edge": round(s.edge, 4), "source": s.source} for s in self.legs],
            "odds": round(self.odds, 3), "win_prob": round(self.win_prob, 4),
            "ev": round(self.ev, 4), "edge": round(self.edge, 4), "bonus": self.bonus,
            "stake": round(self.stake, 5),
        }
        if bankroll:
            d["amount"] = round(bankroll * self.stake)
        return d


@dataclass
class Portfolio:
    bets: List[Bet]
    candidates: List[Bet]
    growth: float  # 보수적 확률 기준 기대 로그 성장률 (하루)
    exp_return: float  # 보수적 기준 기대 수익률 (자본 대비)
    p_loss: float  # 그날 자본이 줄어들 확률
    q05: float  # 수익률 하위 5% 분위

    @property
    def total_stake(self) -> float:
        return float(sum(b.stake for b in self.bets))

    def to_dict(self, bankroll: Optional[float] = None) -> dict:
        return {
            "total_stake": round(self.total_stake, 5), "growth": round(self.growth, 6),
            "exp_return": round(self.exp_return, 5), "p_loss": round(self.p_loss, 4), "q05": round(self.q05, 5),
            "bets": [b.to_dict(bankroll) for b in self.bets],
        }


def _bonus(legs: Sequence[Selection], cfg: PortfolioConfig) -> float:
    if len(legs) < 2 or not cfg.acca_bonus:
        return 0.0
    if any(s.odds < cfg.bonus_min_leg_odds for s in legs):
        return 0.0
    n = min(len(legs), max(cfg.acca_bonus))
    return float(cfg.acca_bonus.get(n, 0.0))


def _expected(legs: Sequence[Selection], bonus: float, probs: Dict[str, np.ndarray]) -> Tuple[float, float]:
    """서로 다른 경기 폴들의 기대 돌려받는 금액과 전부 맞을 확률 (독립 가정)."""
    ret, full, hit = 1.0, 1.0, 1.0
    for s in legs:
        p = probs[s.fixture_id]
        ret *= float(p @ s.payoff())
        full *= float(p @ (s.W >= 1.0 - 1e-9))
        hit *= float(p @ (s.W > 0))
    odds = prod(s.odds for s in legs)
    return ret + bonus * (odds - 1.0) * full, hit


def make_bet(legs: Sequence[Selection], pricings: Dict[str, FixturePricing], cfg: PortfolioConfig) -> Bet:
    legs = tuple(legs)
    b = _bonus(legs, cfg)
    fair = {k: v.fair for k, v in pricings.items()}
    cons = {k: v.conservative for k, v in pricings.items()}
    fr, hit = _expected(legs, b, fair)
    cr, _ = _expected(legs, b, cons)
    return Bet(legs, bonus=b, fair_ret=fr, cons_ret=cr, win_prob=hit)


def candidates(value: Sequence[Selection], pricings: Dict[str, FixturePricing], cfg: PortfolioConfig) -> List[Bet]:
    """단식 + 서로 다른 경기 폴로 만든 멀티 후보."""
    ranked = sorted(value, key=lambda s: s.edge, reverse=True)
    out: List[Bet] = []
    if cfg.singles:
        out += [make_bet([s], pricings, cfg) for s in ranked]
    pool = ranked[: cfg.pool]
    for k in range(2, cfg.max_legs + 1):
        for legs in combinations(pool, k):
            if len({s.fixture_id for s in legs}) < k:
                continue
            bet = make_bet(legs, pricings, cfg)
            if bet.edge > 0:
                out.append(bet)
    return out


def _scenario_returns(bets: Sequence[Bet], pricings: Dict[str, FixturePricing], n: int, seed: int,
                      which: str = "conservative") -> np.ndarray:
    """G[j, s]: 시나리오 s 에서 배팅 j 의 1원당 돌려받는 금액."""
    rng = np.random.default_rng(seed)
    fids = sorted({s.fixture_id for b in bets for s in b.legs})
    states = {}
    for fid in fids:
        p = getattr(pricings[fid], which)
        states[fid] = rng.choice(len(p), size=n, p=p / p.sum())
    G = np.empty((len(bets), n))
    for j, b in enumerate(bets):
        g = np.ones(n)
        full = np.ones(n, dtype=bool)
        for s in b.legs:
            st = states[s.fixture_id]
            g *= s.payoff()[st]
            full &= s.W[st] >= 1.0 - 1e-9
        if b.bonus:
            g = np.where(full, 1.0 + (g - 1.0) * (1.0 + b.bonus), g)
        G[j] = g
    return G


def kelly_weights(G: np.ndarray, max_each: float, max_total: float) -> np.ndarray:
    """E[log(1 + f·(G−1))] 를 최대화하는 f (0 ≤ f_j ≤ max_each, Σf ≤ max_total)."""
    X = G - 1.0
    J = X.shape[0]
    if J == 0:
        return np.zeros(0)
    max_total = min(max_total, 0.99)

    def obj(f):
        w = 1.0 + f @ X
        w = np.maximum(w, 1e-9)
        return -np.mean(np.log(w)), -(X / w).mean(axis=1)

    f0 = np.full(J, min(max_each, max_total / J) * 0.1)
    res = minimize(obj, f0, jac=True, method="SLSQP", bounds=[(0.0, max_each)] * J,
                   constraints=[{"type": "ineq", "fun": lambda f: max_total - f.sum(), "jac": lambda f: -np.ones(J)}],
                   options={"maxiter": 300, "ftol": 1e-12})
    f = np.clip(res.x, 0.0, max_each)
    if f.sum() > max_total:
        f *= max_total / f.sum()
    return f


def optimize(value: Sequence[Selection], pricings: Dict[str, FixturePricing],
             cfg: Optional[PortfolioConfig] = None) -> Portfolio:
    cfg = cfg or PortfolioConfig()
    cands = candidates(value, pricings, cfg)
    if not cands:
        return Portfolio([], [], 0.0, 0.0, 0.0, 0.0)
    G = _scenario_returns(cands, pricings, cfg.n_scenarios, cfg.seed)
    kf = cfg.kelly_fraction
    f = kelly_weights(G, cfg.max_bet / kf, cfg.max_total / kf) * kf
    keep = np.argsort(-f)[: cfg.max_bets]
    keep = keep[f[keep] >= cfg.min_stake]
    f = np.zeros(len(cands))
    if len(keep):
        f[keep] = kelly_weights(G[keep], cfg.max_bet / kf, cfg.max_total / kf) * kf
        f[f < cfg.min_stake] = 0.0
    for b, x in zip(cands, f):
        b.stake = float(x)
    r = f @ (G - 1.0)
    chosen = sorted([b for b in cands if b.stake > 0], key=lambda b: b.stake, reverse=True)
    return Portfolio(
        bets=chosen, candidates=sorted(cands, key=lambda b: b.edge, reverse=True),
        growth=float(np.mean(np.log1p(r))), exp_return=float(np.mean(r)),
        p_loss=float(np.mean(r < -1e-12)), q05=float(np.quantile(r, 0.05)),
    )


def joint_prob(legs: Sequence[Selection], pricing: FixturePricing, which: str = "fair") -> float:
    """같은 경기 선택지들이 모두 맞을 확률 (Bet Builder 가격 평가용)."""
    p = getattr(pricing, which)
    mask = np.ones_like(p, dtype=bool)
    for s in legs:
        mask &= s.W >= 1.0 - 1e-9
    return float(p[mask].sum())


@dataclass
class ComboPick:
    """3폴 이상 같은 '한 장짜리' 조합을 원할 때: 조합 하나만 걸 경우 가장 빠르게 자본을 키우는 것."""
    bet: Optional[Bet]
    growth: float  # 이 조합 하나만 켈리 비율로 걸 때 기대 로그 성장 (보수적 확률)
    best_single: Optional[Bet]
    single_growth: float
    n_value_fixtures: int  # +엣지 선택지가 있는 경기 수
    min_legs: int


def _single_bet_growth(g: np.ndarray, max_each: float, kf: float) -> Tuple[float, float]:
    """배팅 하나(시나리오 수익 g)를 분수 켈리로 걸 때의 비율과 기대 로그 성장."""
    f = float(kelly_weights(g[None, :], max_each / kf, max_each / kf)[0]) * kf
    return f, float(np.mean(np.log1p(f * (g - 1.0))))


def best_combo(value: Sequence[Selection], pricings: Dict[str, FixturePricing],
               cfg: Optional[PortfolioConfig] = None, min_legs: int = 3, max_legs: int = 5) -> ComboPick:
    """+엣지 선택지만으로(경기당 한 폴) min_legs~max_legs 폴 조합을 만들어, 그 하나만 걸 때 기대 로그 성장이
    가장 큰 조합을 고른다. 같은 기준으로 가장 좋은 단식도 함께 돌려준다(비교용)."""
    cfg = cfg or PortfolioConfig()
    kf = cfg.kelly_fraction
    best_per_fixture: Dict[str, Selection] = {}
    for s in value:
        if s.edge > 0 and (s.fixture_id not in best_per_fixture or s.edge > best_per_fixture[s.fixture_id].edge):
            best_per_fixture[s.fixture_id] = s
    pool = sorted(best_per_fixture.values(), key=lambda s: s.edge, reverse=True)[: cfg.pool]
    singles = [make_bet([s], pricings, cfg) for s in pool]
    combos = [make_bet(legs, pricings, cfg) for k in range(min_legs, max_legs + 1) for legs in combinations(pool, k)]
    combos = [b for b in combos if b.edge > 0]
    empty = ComboPick(None, 0.0, None, 0.0, len(best_per_fixture), min_legs)
    if not singles:
        return empty
    G = _scenario_returns(singles + combos, pricings, cfg.n_scenarios, cfg.seed)
    scored = []
    for b, g in zip(singles + combos, G):
        b.stake, gr = _single_bet_growth(g, cfg.max_bet, kf)
        scored.append((gr, b))
    single_gr, single = max(scored[: len(singles)], key=lambda t: t[0])
    if not combos:
        return ComboPick(None, 0.0, single, single_gr, len(best_per_fixture), min_legs)
    combo_gr, combo = max(scored[len(singles):], key=lambda t: t[0])
    return ComboPick(combo, combo_gr, single, single_gr, len(best_per_fixture), min_legs)

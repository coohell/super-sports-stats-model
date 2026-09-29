"""스코어 확률 격자: 배당에서 경기 전체의 확률 분포를 복원한다.

북메이커 배당은 마켓마다 따로 있지만 모두 같은 최종 스코어로 정산된다.
그래서 마진을 뺀 확률들에 가장 잘 맞는 Dixon-Coles 스코어 분포
P[h, a] 를 찾으면,
  - 샤프 북이 배당을 안 낸 마켓(BTTS, 팀 득점, 핸디캡)의 공정 확률과
  - 같은 경기 안 선택지들의 상관관계(예: 홈승 + 오버 2.5)
를 일관되게 계산할 수 있다.

1단계: (λ, μ, ρ) 를 KL 발산 최소화로 맞춘다.
2단계: 반복 비례 맞춤(IPF)으로 격자를 조금씩 고쳐 샤프 마켓 확률과 정확히
       일치시킨다. 모수 모형의 한계(예: 무승부 과소평가)를 시장이 바로잡는다.
"""
from __future__ import annotations

from typing import Dict, Iterable, List, Optional, Tuple

import numpy as np
from scipy.optimize import minimize
from scipy.special import gammaln

from .markets import MAX_GOALS, N, Fixture, OUTCOMES, parse, settle
from .odds import devig

DEFAULT_RHO = -0.08
_G = np.arange(N)
_LOGFACT = gammaln(_G + 1)


def _pmf(rate: float) -> np.ndarray:
    return np.exp(_G * np.log(rate) - rate - _LOGFACT)


def dc_grid(lam: float, mu: float, rho: float = DEFAULT_RHO) -> np.ndarray:
    """Dixon-Coles 스코어 분포 (저득점 보정 포함)."""
    m = np.outer(_pmf(lam), _pmf(mu))
    m[0, 0] *= 1 - lam * mu * rho
    m[0, 1] *= 1 + lam * rho
    m[1, 0] *= 1 + mu * rho
    m[1, 1] *= 1 - rho
    m = np.clip(m, 1e-15, None)
    return m / m.sum()


def partition_markets(fx: Fixture, book: str) -> List[Tuple[str, Dict[str, float]]]:
    """적특이 없는(결과들이 스코어를 겹치지 않게 나누는) 마켓만 골라 마진을 뺀다.

    정수 라인처럼 적특이 있는 마켓은 두 결과의 합이 1이 아니라서 제외한다.
    """
    out = []
    for market in fx.odds.get(book, {}):
        try:
            kind, _ = parse(market)
        except ValueError:
            continue
        if kind in ("H2H", "CS", "DC"):
            continue
        odds = fx.market(book, market)
        if not odds:
            continue
        outs = OUTCOMES[kind]
        Ws = [settle(market, o) for o in outs]
        if any(R.any() for _, R in Ws):
            continue
        if not np.allclose(sum(W for W, _ in Ws), 1.0):
            continue
        p = devig([odds[o] for o in outs])
        out.append((market, dict(zip(outs, p))))
    return out


TOTAL_KINDS = ("OU", "TTH", "TTA", "BTTS")


def has_totals(markets: List[Tuple[str, Dict[str, float]]]) -> bool:
    return any(parse(m)[0] in TOTAL_KINDS for m, _ in markets)


def _targets(markets, weights: Optional[Dict[str, float]] = None) -> List[Tuple[np.ndarray, float, float]]:
    """(W 격자, 목표 확률, 가중치) 목록. 1X2 에 가장 큰 가중치를 준다."""
    t = []
    for market, probs in markets:
        w = (weights or {}).get(market, 2.0 if market == "1X2" else 1.0)
        for o, p in probs.items():
            t.append((settle(market, o)[0], float(p), w))
    return t


def fit_grid(markets: List[Tuple[str, Dict[str, float]]], rho: float = DEFAULT_RHO,
             prior_total: Optional[float] = None, rake: bool = True,
             extra: Optional[List[Tuple[str, Dict[str, float]]]] = None, extra_weight: float = 0.5) -> Optional[np.ndarray]:
    """마진 뺀 마켓 확률들에 맞는 스코어 격자.

    1X2 만 있으면 자유도가 2라 (λ, μ) 가 정확히 정해진다. 하지만 1X2 만으로 정한
    총득점은 실력 차가 큰 경기에서 크게 틀린다(과거 EPL 에서 강팀 홈 경기 오버 2.5 를
    10%p 넘게 과대평가). 그래서 샤프 북에 총득점 마켓이 없으면 extra(보통 bet365 자신의
    오버/언더를 마진 뺀 것)를 약한 가중치로 함께 맞춘다. extra 는 모양 맞추기에만 쓰고
    IPF 로 강제하지는 않는다. prior_total 은 그것마저 없을 때 쓰는 리그 평균 득점이다.
    """
    if not markets:
        return None
    extra = [(m, p) for m, p in (extra or []) if m not in {k for k, _ in markets}]
    weights = {m: extra_weight for m, _ in extra}
    targets = _targets(list(markets) + extra, weights)
    T = np.array([W.ravel() for W, _, _ in targets])
    P = np.array([p for _, p, _ in targets])
    Wt = np.array([w for _, _, w in targets])
    pos = P > 0
    has_total = has_totals(list(markets) + extra)

    def loss(x):
        lam, mu = np.exp(x)
        q = np.clip(T @ dc_grid(lam, mu, rho).ravel(), 1e-9, 1 - 1e-9)
        l = float(np.sum(Wt[pos] * P[pos] * np.log(P[pos] / q[pos])))
        if prior_total and not has_total:
            l += 0.02 * (np.log(lam + mu) - np.log(prior_total)) ** 2
        return l

    res = minimize(loss, np.log([1.45, 1.15]), method="Nelder-Mead",
                   options={"xatol": 1e-5, "fatol": 1e-10, "maxiter": 400})
    lam, mu = np.exp(res.x)
    g = dc_grid(lam, mu, rho)
    return rake_grid(g, markets) if rake else g


def rake_grid(g: np.ndarray, markets: List[Tuple[str, Dict[str, float]]], iters: int = 60, tol: float = 1e-9) -> np.ndarray:
    """IPF: 각 마켓의 결과 확률이 목표와 같아지도록 격자를 비례 조정한다."""
    g = g.copy()
    groups = [[(settle(m, o)[0] > 0.5, p) for o, p in probs.items()] for m, probs in markets]
    for _ in range(iters):
        worst = 0.0
        for grp in groups:
            for mask, p in grp:
                cur = g[mask].sum()
                if cur <= 0:
                    continue
                worst = max(worst, abs(cur - p))
                g[mask] *= p / cur
        g /= g.sum()
        if worst < tol:
            break
    return g


def pool(grids: Iterable[Tuple[np.ndarray, float]]) -> np.ndarray:
    """로그 선형 풀링: P ∝ Π P_i^w_i. 전문가 의견을 섞는 표준 방식이다."""
    log = None
    for g, w in grids:
        if w == 0:
            continue
        term = w * np.log(np.clip(g, 1e-15, None))
        log = term if log is None else log + term
    p = np.exp(log - log.max())
    return p / p.sum()


def prob(g: np.ndarray, market: str, outcome: str) -> float:
    """적중 확률 (반승은 0.5 로 센다)."""
    W, _ = settle(market, outcome)
    return float((g * W).sum())


def expected_return(g: np.ndarray, market: str, outcome: str, odds: float) -> float:
    """1원 걸었을 때 기대 돌려받는 금액. EV = 이 값 − 1."""
    W, R = settle(market, outcome)
    return float((g * (W * odds + R)).sum())


def summary(g: np.ndarray) -> Dict[str, float]:
    h, a = np.indices(g.shape)
    return {
        "xg_home": float((g * h).sum()), "xg_away": float((g * a).sum()),
        "home": float(g[h > a].sum()), "draw": float(np.trace(g)), "away": float(g[h < a].sum()),
    }

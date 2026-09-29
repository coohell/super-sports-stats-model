"""배당 수학: 마진 제거(devig), 기대값(EV), 켈리.

모든 배당은 소수 배당(decimal odds, 예: 2.10)이다.
"""
from __future__ import annotations

from typing import Sequence

import numpy as np
from scipy.optimize import brentq


def implied(odds: Sequence[float]) -> np.ndarray:
    o = np.asarray(odds, dtype=float)
    if np.any(o <= 1.0):
        raise ValueError(f"배당은 1보다 커야 합니다: {odds}")
    return 1.0 / o


def overround(odds: Sequence[float]) -> float:
    """북메이커 마진. 0.05 = 5%."""
    return float(implied(odds).sum() - 1.0)


def devig(odds: Sequence[float], method: str = "power") -> np.ndarray:
    """한 마켓의 모든 결과 배당에서 마진을 제거한 공정 확률을 돌려준다.

    - proportional: 1/o 를 합이 1이 되게 나눈다 (가장 단순, 롱샷 편향 무시).
    - power: p_i = (1/o_i)^k, 합이 1이 되는 k 를 찾는다. 롱샷에 마진이 더
      붙는 현실을 반영하므로 기본값이다.
    - shin: Shin(1993) 내부자 거래 모형.
    """
    q = implied(odds)
    if method == "proportional":
        return q / q.sum()
    if method == "power":
        if abs(q.sum() - 1.0) < 1e-12:
            return q
        k = brentq(lambda k: np.sum(q**k) - 1.0, 1e-6, 50.0)
        p = q**k
        return p / p.sum()
    if method == "shin":
        s = q.sum()
        if abs(s - 1.0) < 1e-12:
            return q

        def probs(z: float) -> np.ndarray:
            return (np.sqrt(z**2 + 4 * (1 - z) * q**2 / s) - z) / (2 * (1 - z))

        z = brentq(lambda z: probs(z).sum() - 1.0, 0.0, 0.999)
        p = probs(z)
        return p / p.sum()
    raise ValueError(f"알 수 없는 devig 방식: {method}")


def ev(prob: float, odds: float) -> float:
    """1원 걸었을 때 기대 수익. 0.03 = +3%."""
    return prob * odds - 1.0


def kelly(prob: float, odds: float, fraction: float = 1.0) -> float:
    """켈리 비율 f* = (p*o - 1) / (o - 1). 음수면 0."""
    if odds <= 1.0:
        return 0.0
    f = (prob * odds - 1.0) / (odds - 1.0)
    return max(0.0, f * fraction)


def log_growth(prob: float, odds: float, stake: float) -> float:
    """자본 대비 stake 비율로 걸었을 때 기대 로그 성장률 (한 번 배팅)."""
    if stake <= 0:
        return 0.0
    return prob * np.log1p(stake * (odds - 1.0)) + (1 - prob) * np.log1p(-stake)

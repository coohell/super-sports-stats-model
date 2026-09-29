"""Dixon-Coles(1997) 팀 전력 모델.

홈 득점 ~ Poisson(λ), 원정 득점 ~ Poisson(μ)
  log λ = attack[home] + defence[away] + home_adv
  log μ = attack[away] + defence[home]
저득점(0-0, 1-0, 0-1, 1-1) 보정 계수 ρ, 최근 경기에 더 큰 가중치(시간 감쇠 ξ).
defence 는 "실점 경향"이라 클수록 수비가 약하다.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, Optional

import numpy as np
import pandas as pd
from scipy.optimize import minimize
from scipy.stats import poisson

MAX_GOALS = 10


def _tau_matrix(lam: float, mu: float, rho: float, n: int = MAX_GOALS + 1) -> np.ndarray:
    t = np.ones((n, n))
    t[0, 0] = 1 - lam * mu * rho
    t[0, 1] = 1 + lam * rho
    t[1, 0] = 1 + mu * rho
    t[1, 1] = 1 - rho
    return t


def market_probs(score: np.ndarray) -> Dict[str, Dict[str, float]]:
    """득점 확률 행렬 score[h, a] 에서 마켓별 확률을 뽑는다."""
    n = score.shape[0]
    h, a = np.indices((n, n))
    total = h + a
    home = float(score[h > a].sum())
    draw = float(np.trace(score))
    away = float(score[h < a].sum())
    over = float(score[total > 2.5].sum())
    btts = float(score[(h > 0) & (a > 0)].sum())
    return {
        "1X2": {"home": home, "draw": draw, "away": away},
        "OU2.5": {"over": over, "under": 1.0 - over},
        "BTTS": {"yes": btts, "no": 1.0 - btts},
    }


@dataclass
class DixonColes:
    xi: float = 0.0019  # 일 단위 시간 감쇠. 0.0019 ≈ 반감기 1년
    ridge: float = 0.01  # 경기 수가 적은 팀(승격팀)의 과적합 방지

    teams_: Optional[list] = None
    attack_: Optional[np.ndarray] = None
    defence_: Optional[np.ndarray] = None
    home_adv_: float = 0.0
    rho_: float = 0.0

    def fit(self, matches: pd.DataFrame, as_of: Optional[pd.Timestamp] = None) -> "DixonColes":
        """matches: date, home, away, hg, ag 컬럼. as_of 이전 경기만 쓴다."""
        df = matches.dropna(subset=["hg", "ag"]).copy()
        df["date"] = pd.to_datetime(df["date"])
        if as_of is not None:
            df = df[df["date"] < pd.Timestamp(as_of)]
        if len(df) < 20:
            raise ValueError(f"학습 경기가 너무 적습니다: {len(df)}")
        ref = pd.Timestamp(as_of) if as_of is not None else df["date"].max()
        days = (ref - df["date"]).dt.days.to_numpy(dtype=float)
        w = np.exp(-self.xi * days)

        teams = sorted(set(df["home"]) | set(df["away"]))
        idx = {t: i for i, t in enumerate(teams)}
        hi = df["home"].map(idx).to_numpy()
        ai = df["away"].map(idx).to_numpy()
        x = df["hg"].to_numpy(dtype=float)
        y = df["ag"].to_numpy(dtype=float)
        n = len(teams)

        m00 = (x == 0) & (y == 0)
        m01 = (x == 0) & (y == 1)
        m10 = (x == 1) & (y == 0)
        m11 = (x == 1) & (y == 1)

        def unpack(p):
            a = p[:n] - p[:n].mean()
            return a, p[n : 2 * n], p[2 * n], p[2 * n + 1]

        def nll(p):
            a, d, home, rho = unpack(p)
            ll_ = a[hi] + d[ai] + home
            lm_ = a[ai] + d[hi]
            lam, mu = np.exp(ll_), np.exp(lm_)
            tau = np.ones_like(lam)
            tau[m00] = 1 - lam[m00] * mu[m00] * rho
            tau[m01] = 1 + lam[m01] * rho
            tau[m10] = 1 + mu[m10] * rho
            tau[m11] = 1 - rho
            tau = np.clip(tau, 1e-10, None)
            ll = w * (np.log(tau) + x * ll_ - lam + y * lm_ - mu)

            g_l = x - lam
            g_m = y - mu
            g_rho = np.zeros_like(lam)
            g_l[m00] += -lam[m00] * mu[m00] * rho / tau[m00]
            g_m[m00] += -lam[m00] * mu[m00] * rho / tau[m00]
            g_rho[m00] = -lam[m00] * mu[m00] / tau[m00]
            g_l[m01] += lam[m01] * rho / tau[m01]
            g_rho[m01] = lam[m01] / tau[m01]
            g_m[m10] += mu[m10] * rho / tau[m10]
            g_rho[m10] = mu[m10] / tau[m10]
            g_rho[m11] = -1 / tau[m11]
            g_l, g_m, g_rho = w * g_l, w * g_m, w * g_rho

            ga = np.bincount(hi, g_l, n) + np.bincount(ai, g_m, n)
            gd = np.bincount(ai, g_l, n) + np.bincount(hi, g_m, n)
            ga = ga - ga.mean()
            dc = d - d.mean()  # 평균 실점 수준(절편)은 벌점에서 뺀다
            pen = self.ridge * (np.sum(a**2) + np.sum(dc**2))
            grad = np.concatenate([ga - 2 * self.ridge * a, gd - 2 * self.ridge * dc, [g_l.sum(), g_rho.sum()]])
            return -(ll.sum() - pen), -grad

        p0 = np.concatenate([np.zeros(n), np.zeros(n), [0.25, -0.05]])
        bounds = [(None, None)] * (2 * n) + [(-1, 1), (-0.2, 0.2)]
        res = minimize(nll, p0, jac=True, method="L-BFGS-B", bounds=bounds)
        if not res.success:
            raise RuntimeError(f"Dixon-Coles 최적화 실패: {res.message}")
        a, d, home, rho = unpack(res.x)
        self.teams_, self.attack_, self.defence_ = teams, a, d
        self.home_adv_, self.rho_ = float(home), float(rho)
        self._idx = idx
        return self

    def knows(self, team: str) -> bool:
        return self.teams_ is not None and team in self._idx

    def rates(self, home: str, away: str) -> tuple:
        i, j = self._idx[home], self._idx[away]
        lam = np.exp(self.attack_[i] + self.defence_[j] + self.home_adv_)
        mu = np.exp(self.attack_[j] + self.defence_[i])
        return float(lam), float(mu)

    def score_matrix(self, home: str, away: str) -> np.ndarray:
        lam, mu = self.rates(home, away)
        g = np.arange(MAX_GOALS + 1)
        m = np.outer(poisson.pmf(g, lam), poisson.pmf(g, mu)) * _tau_matrix(lam, mu, self.rho_)
        return m / m.sum()

    def predict(self, home: str, away: str) -> Optional[Dict[str, Dict[str, float]]]:
        if not (self.knows(home) and self.knows(away)):
            return None
        return market_probs(self.score_matrix(home, away))

    def ratings(self) -> pd.DataFrame:
        return (
            pd.DataFrame({"team": self.teams_, "attack": self.attack_, "defence": self.defence_})
            .assign(strength=lambda d: d["attack"] - d["defence"])
            .sort_values("strength", ascending=False)
            .reset_index(drop=True)
        )

    @staticmethod
    def from_results(rows: Iterable[dict], **kw) -> "DixonColes":
        return DixonColes(**kw).fit(pd.DataFrame(list(rows)))

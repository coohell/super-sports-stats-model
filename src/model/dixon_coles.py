"""
Dixon-Coles 팀 전력 모델 (공격/수비/홈어드밴티지 + 저득점 보정 rho + 시간 감쇠)
"""
from typing import Dict, List, Optional

import numpy as np
import pandas as pd
from scipy.optimize import minimize
from scipy.stats import poisson


def _tau(x, y, lam, mu, rho):
    """저득점(0-0, 1-0, 0-1, 1-1) 상관 보정"""
    t = np.ones_like(lam)
    t = np.where((x == 0) & (y == 0), 1 - lam * mu * rho, t)
    t = np.where((x == 0) & (y == 1), 1 + lam * rho, t)
    t = np.where((x == 1) & (y == 0), 1 + mu * rho, t)
    t = np.where((x == 1) & (y == 1), 1 - rho, t)
    return t


class DixonColes:
    def __init__(self, xi: float = 0.0019, max_goals: int = 10):
        """xi: 일 단위 시간 감쇠율 (0.0019 ≈ 반감기 1년)"""
        self.xi = xi
        self.max_goals = max_goals
        self.teams: List[str] = []
        self.attack: Dict[str, float] = {}
        self.defence: Dict[str, float] = {}
        self.home_adv = 0.0
        self.rho = 0.0

    def fit(self, df: pd.DataFrame, ref_date: Optional[pd.Timestamp] = None):
        """df 컬럼: Date, HomeTeam, AwayTeam, FTHG, FTAG"""
        ref_date = ref_date or df["Date"].max()
        self.teams = sorted(set(df.HomeTeam) | set(df.AwayTeam))
        n = len(self.teams)
        idx = {t: i for i, t in enumerate(self.teams)}
        h = df.HomeTeam.map(idx).values
        a = df.AwayTeam.map(idx).values
        x = df.FTHG.values.astype(int)
        y = df.FTAG.values.astype(int)
        days = (ref_date - df.Date).dt.days.clip(lower=0).values
        w = np.exp(-self.xi * days)

        def unpack(p):
            att, dfn = p[:n], p[n:2 * n]
            return att - att.mean(), dfn - dfn.mean(), p[2 * n], p[2 * n + 1]

        def nll(p):
            att, dfn, ha, rho = unpack(p)
            lam = np.exp(att[h] + dfn[a] + ha)
            mu = np.exp(att[a] + dfn[h])
            tau = np.clip(_tau(x, y, lam, mu, rho), 1e-6, None)
            ll = np.log(tau) + poisson.logpmf(x, lam) + poisson.logpmf(y, mu)
            return -(w * ll).sum()

        p0 = np.concatenate([np.zeros(2 * n), [0.25, -0.05]])
        res = minimize(nll, p0, method="L-BFGS-B",
                       bounds=[(None, None)] * (2 * n) + [(None, None), (-0.3, 0.3)])
        att, dfn, ha, rho = unpack(res.x)
        self.attack = dict(zip(self.teams, att))
        self.defence = dict(zip(self.teams, dfn))  # 클수록 수비 약함(실점 증가)
        self.home_adv, self.rho = ha, rho
        return self

    def score_matrix(self, home: str, away: str) -> np.ndarray:
        lam = np.exp(self.attack[home] + self.defence[away] + self.home_adv)
        mu = np.exp(self.attack[away] + self.defence[home])
        g = np.arange(self.max_goals + 1)
        m = np.outer(poisson.pmf(g, lam), poisson.pmf(g, mu))
        m[0, 0] *= 1 - lam * mu * self.rho
        m[0, 1] *= 1 + lam * self.rho
        m[1, 0] *= 1 + mu * self.rho
        m[1, 1] *= 1 - self.rho
        return m / m.sum()

    def predict_1x2(self, home: str, away: str) -> Optional[Dict[str, float]]:
        """알 수 없는 팀(승격팀 등)은 None"""
        if home not in self.attack or away not in self.attack:
            return None
        m = self.score_matrix(home, away)
        return {"home": float(np.tril(m, -1).sum()),
                "draw": float(np.trace(m)),
                "away": float(np.triu(m, 1).sum())}

    def predict_ou(self, home: str, away: str, line: float = 2.5) -> Optional[Dict[str, float]]:
        if home not in self.attack or away not in self.attack:
            return None
        m = self.score_matrix(home, away)
        tot = np.add.outer(np.arange(m.shape[0]), np.arange(m.shape[1]))
        over = float(m[tot > line].sum())
        return {"over": over, "under": 1 - over}

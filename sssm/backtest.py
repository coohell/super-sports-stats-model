"""시장 백테스트: 실제 엔진(가격 → 가치 선택지 → 포트폴리오)을 과거 배당에 그대로 돌린다.

- 날짜 순서대로, 같은 날 경기들을 한 번에 놓고 포트폴리오를 짠 뒤 결과로 정산하고
  자금을 갱신한다. 그날 이전 정보만 쓴다.
- shrink 는 그 시점 이전 경기로만 다시 추정한다(시즌마다). 미래 정보 누수 없음.
- phase="open": bet365/Pinnacle 시가로 걸고 Pinnacle 마감으로 CLV 를 잰다.
  phase="close": 두 북 모두 마감 가격으로 건다 (경기 직전 bet365 가 Pinnacle 을
  못 따라간 순간을 잡는 전략의 근사). 이때 CLV 는 없다.
- 신뢰구간은 날짜 단위 블록 부트스트랩이다. 같은 날 배팅들은 서로 얽혀 있어서
  배팅 단위로 뽑으면 구간이 실제보다 좁게 나온다.
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

from . import grid as gridlib
from .calibrate import shrink_from_history
from .history import row_to_fixture
from .markets import N
from .portfolio import PortfolioConfig, optimize
from .pricing import PricingConfig, ValueFilter, price_fixture, selections, value_bets

PHASES = {
    "open": ({"bet365": "bet365", "pinnacle": "pinnacle"}, {"pinnacle_close": "pinnacle"}),
    "close": ({"bet365_close": "bet365", "pinnacle_close": "pinnacle"}, None),
}


@dataclass
class Strategy:
    name: str
    portfolio: PortfolioConfig
    value: ValueFilter = field(default_factory=ValueFilter)
    flat: bool = False  # True 면 켈리 대신 선택지마다 자본의 flat_stake 를 단식으로 건다
    flat_stake: float = 0.01


def default_strategies(acca_bonus: Optional[Dict[int, float]] = None) -> List[Strategy]:
    out = [
        Strategy("단식 균등 1%", PortfolioConfig(max_legs=1), flat=True),
        Strategy("단식 켈리", PortfolioConfig(max_legs=1)),
        Strategy("단식+멀티 켈리 (최강 조합)", PortfolioConfig(max_legs=3)),
    ]
    if acca_bonus:
        out.append(Strategy("단식+멀티 켈리 + 부스트", PortfolioConfig(max_legs=4, acca_bonus=dict(acca_bonus))))
    return out


@dataclass
class StrategyResult:
    name: str
    bets: pd.DataFrame  # 배팅 한 건당 한 줄
    days: pd.DataFrame  # 날짜별 자금

    def summary(self, n_boot: int = 2000, seed: int = 0) -> dict:
        b, d = self.bets, self.days
        if b.empty:
            return {"strategy": self.name, "bets": 0}
        turnover = b["stake_amt"].sum()
        profit = b["pnl"].sum()
        eq = d["bankroll"].to_numpy()
        peak = np.maximum.accumulate(np.concatenate([[1.0], eq]))
        mdd = float(np.max(1 - np.concatenate([[1.0], eq]) / peak))
        # 날짜 블록 부트스트랩
        rng = np.random.default_rng(seed)
        by_day = b.groupby("date").agg(stake=("stake_amt", "sum"), pnl=("pnl", "sum"))
        dg = np.log(d["bankroll"]).diff().fillna(np.log(d["bankroll"].iloc[0])).to_numpy()
        rois, growth = [], []
        for _ in range(n_boot):
            i = rng.integers(0, len(by_day), len(by_day))
            s = by_day["stake"].to_numpy()[i].sum()
            rois.append(by_day["pnl"].to_numpy()[i].sum() / s if s > 0 else 0.0)
            j = rng.integers(0, len(dg), len(dg))
            growth.append(dg[j].sum())
        clv = b["clv"].dropna()
        w = b.loc[clv.index, "stake_amt"]
        return {
            "strategy": self.name, "bets": int(len(b)), "days": int(len(by_day)),
            "singles": int((b["legs"] == 1).sum()), "multis": int((b["legs"] > 1).sum()),
            "hit": float((b["pnl"] > 0).mean()), "turnover": float(turnover),
            "roi": float(profit / turnover), "roi_lo": float(np.quantile(rois, 0.025)),
            "roi_hi": float(np.quantile(rois, 0.975)),
            "final": float(eq[-1]), "log_growth": float(np.log(eq[-1])),
            "growth_lo": float(np.quantile(growth, 0.025)), "growth_hi": float(np.quantile(growth, 0.975)),
            "max_dd": mdd, "pred_edge": float(np.average(b["edge"], weights=b["stake_amt"])),
            "pred_ev": float(np.average(b["ev"], weights=b["stake_amt"])),
            "clv": float(np.average(clv, weights=w)) if len(clv) and w.sum() > 0 else None,
        }


@dataclass
class BacktestResult:
    period: str
    n_matches: int
    phase: str
    shrink_used: List[tuple]
    results: List[StrategyResult]

    def table(self) -> pd.DataFrame:
        return pd.DataFrame([r.summary() for r in self.results])

    def to_text(self) -> str:
        lines = [f"시장 백테스트 ({self.phase}): {self.n_matches}경기, {self.period}"]
        if self.shrink_used:
            lines.append("shrink(그 시점까지 데이터로 추정): " + ", ".join(f"{d} {s:.2f}" for d, s in self.shrink_used))
        lines += ["", f"{'전략':<24}{'배팅':>6}{'멀티':>6}{'적중':>7}{'ROI':>9}  {'95% 구간':<20}{'자금':>8}"
                      f"{'로그성장 95%':>24}{'MDD':>7}{'예측엣지':>9}{'CLV':>8}"]
        for r in self.results:
            s = r.summary()
            if not s["bets"]:
                lines.append(f"{s['strategy']:<24}{0:>6}")
                continue
            clv = f"{s['clv']:+.2%}" if s["clv"] is not None else "-"
            roi_ci = f"[{s['roi_lo']:+.1%}, {s['roi_hi']:+.1%}]"
            g_ci = f"{s['log_growth']:+.2f} [{s['growth_lo']:+.2f}, {s['growth_hi']:+.2f}]"
            lines.append(f"{s['strategy']:<24}{s['bets']:>6}{s['multis']:>6}{s['hit']:>7.1%}{s['roi']:>+9.2%}  "
                         f"{roi_ci:<20}{s['final']:>8.3f}{g_ci:>24}{s['max_dd']:>7.1%}{s['pred_edge']:>+9.2%}{clv:>8}")
        lines += ["", "ROI = 순이익/총배팅액. 자금은 시작 1.0 기준. 구간은 날짜 블록 부트스트랩 95%.",
                  "CLV = Pinnacle 마감 공정확률 기준 기대값(배팅액 가중). 양수가 이기는 배터의 표시다."]
        return "\n".join(lines)


def _close_grid(row, books) -> Optional[np.ndarray]:
    fx = row_to_fixture(row, {**books, "bet365_close": "bet365"})
    parts = gridlib.partition_markets(fx, "pinnacle")
    if not parts:
        return None
    extra = None if gridlib.has_totals(parts) else [
        p for p in gridlib.partition_markets(fx, "bet365") if gridlib.parse(p[0])[0] in gridlib.TOTAL_KINDS]
    return gridlib.fit_grid(parts, extra=extra).ravel()


def run(df: pd.DataFrame, start: Optional[str] = None, phase: str = "open",
        pricing: Optional[PricingConfig] = None, strategies: Optional[List[Strategy]] = None,
        calibrate: bool = True, recalibrate_days: int = 180, min_calib: int = 300) -> BacktestResult:
    if phase not in PHASES:
        raise ValueError(f"phase 는 {list(PHASES)} 중 하나")
    pricing = pricing or PricingConfig()
    strategies = strategies or default_strategies()
    books, close_books = PHASES[phase]
    df = df.dropna(subset=["hg", "ag"]).sort_values("date", kind="mergesort").reset_index(drop=True)
    test = df[df["date"] >= pd.Timestamp(start)] if start else df
    if test.empty:
        raise ValueError("백테스트할 경기가 없습니다")

    # 날짜별로 가격을 한 번만 매기고 모든 전략이 공유한다
    state = {s.name: {"bankroll": 1.0, "bets": [], "days": []} for s in strategies}
    shrink_used: List[tuple] = []
    cur_pricing, next_calib = pricing, None
    n_matches = 0
    for date, day in test.groupby("date", sort=True):
        if calibrate and (next_calib is None or date >= next_calib):
            est = shrink_from_history(df[df["date"] < date])
            if est is not None and est.n_matches >= min_calib:
                cur_pricing = replace(pricing, shrink=est.shrink)
                shrink_used.append((f"{date:%Y-%m}", est.shrink))
            next_calib = date + pd.Timedelta(days=recalibrate_days)
        pricings, sels, closes, scores = {}, [], {}, {}
        for _, row in day.iterrows():
            fx = row_to_fixture(row, books)
            fp = price_fixture(fx, None, cur_pricing)
            if fp is None:
                continue
            n_matches += 1
            pricings[fx.fixture_id] = fp
            sels.extend(selections(fp, cur_pricing))
            scores[fx.fixture_id] = int(min(row["hg"], N - 1)) * N + int(min(row["ag"], N - 1))
            if close_books:
                closes[fx.fixture_id] = _close_grid(row, close_books)
        for strat in strategies:
            st = state[strat.name]
            value = value_bets(sels, strat.value)
            if not value:
                continue
            if strat.flat:
                picks = [(s,) for s in value]
                stakes = [strat.flat_stake] * len(picks)
                edges = [(s.edge, s.ev) for s in value]
            else:
                pf = optimize(value, pricings, strat.portfolio)
                picks = [b.legs for b in pf.bets]
                stakes = [b.stake for b in pf.bets]
                edges = [(b.edge, b.ev) for b in pf.bets]
            if not picks:
                continue
            bank = st["bankroll"]
            day_pnl = 0.0
            for legs, f, (edge, ev) in zip(picks, stakes, edges):
                amt = bank * f
                gross = 1.0
                clv = 1.0
                for s in legs:
                    k = scores[s.fixture_id]
                    gross *= s.W[k] * s.odds + s.R[k]
                    cg = closes.get(s.fixture_id)
                    clv = clv * float(cg @ s.payoff()) if (cg is not None and clv is not None) else None
                pnl = amt * (gross - 1.0)
                day_pnl += pnl
                st["bets"].append({
                    "date": date, "legs": len(legs), "odds": float(np.prod([s.odds for s in legs])),
                    "picks": " + ".join(f"{s.home}-{s.away} {s.label}" for s in legs),
                    "stake": f, "stake_amt": amt, "pnl": pnl, "edge": edge, "ev": ev,
                    "clv": None if clv is None else clv - 1.0,
                })
            st["bankroll"] = bank + day_pnl
            st["days"].append({"date": date, "bankroll": st["bankroll"]})
            if st["bankroll"] <= 1e-6:
                st["bankroll"] = 1e-6

    results = []
    for strat in strategies:
        st = state[strat.name]
        bets = pd.DataFrame(st["bets"], columns=["date", "legs", "odds", "picks", "stake", "stake_amt", "pnl",
                                                 "edge", "ev", "clv"])
        bets["clv"] = pd.to_numeric(bets["clv"])
        days = pd.DataFrame(st["days"], columns=["date", "bankroll"])
        results.append(StrategyResult(strat.name, bets, days))
    period = f"{test['date'].min():%Y-%m-%d} ~ {test['date'].max():%Y-%m-%d}"
    return BacktestResult(period, n_matches, phase, shrink_used, results)

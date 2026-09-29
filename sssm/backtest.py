"""Walk-forward 백테스트.

매주 그 주 이전 경기로만 Dixon-Coles 를 다시 학습하고 그 주 경기를 예측한다
(미래 정보 누수 없음).

1. 결과만 있는 CSV: 모델의 예측력(로그 손실)을 단순 기준선과 비교한다.
2. 배당 컬럼이 있는 CSV(football-data.co.uk): 실제로 bet365 에 걸었을 때의
   수익률(ROI), Pinnacle 마감 배당 대비 CLV, 최적 sharp_weight 도 계산한다.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

from .history import ODDS_COLUMNS, has_odds
from .markets import MARKETS
from .model import DixonColes
from .odds import devig

EVAL_MARKETS = ("1X2", "OU2.5", "BTTS")


def _outcome(market: str, hg: int, ag: int) -> str:
    if market == "1X2":
        return "home" if hg > ag else "draw" if hg == ag else "away"
    if market == "OU2.5":
        return "over" if hg + ag > 2.5 else "under"
    return "yes" if hg > 0 and ag > 0 else "no"


def walk_forward(df: pd.DataFrame, start: Optional[str] = None, min_train: int = 300, xi: float = 0.0019) -> pd.DataFrame:
    """각 경기에 대해 학습 시점 이전 데이터만 쓴 모델 확률을 붙여 돌려준다."""
    df = df.sort_values("date").reset_index(drop=True)
    start_ts = pd.Timestamp(start) if start else df["date"].iloc[min(min_train, len(df) - 1)]
    test = df[df["date"] >= start_ts].copy()
    test["week"] = test["date"].dt.to_period("W-MON")
    rows = []
    for _, chunk in test.groupby("week"):
        as_of = chunk["date"].min()
        train = df[df["date"] < as_of]
        if len(train) < min_train:
            continue
        model = DixonColes(xi=xi).fit(train, as_of=as_of)
        for i, m in chunk.iterrows():
            pred = model.predict(m["home"], m["away"])
            if pred is None:
                continue
            row = {"idx": i}
            for mk in EVAL_MARKETS:
                for o, p in pred[mk].items():
                    row[f"model_{mk}_{o}"] = p
            rows.append(row)
    if not rows:
        return test.iloc[0:0].drop(columns="week")
    preds = pd.DataFrame(rows).set_index("idx")
    return test.join(preds, how="inner").drop(columns="week")


def _log_loss(p: np.ndarray) -> float:
    return float(-np.mean(np.log(np.clip(p, 1e-12, 1))))


@dataclass
class BacktestReport:
    n_matches: int
    period: str
    log_loss: Dict[str, Dict[str, float]]  # market -> {model, baseline, pinnacle?}
    betting: List[dict] = field(default_factory=list)
    best_sharp_weight: Optional[float] = None

    def to_text(self) -> str:
        lines = [f"백테스트: {self.n_matches}경기 ({self.period})", "", "로그 손실 (낮을수록 좋음)"]
        for mk, d in self.log_loss.items():
            lines.append("  " + mk.ljust(6) + "  ".join(f"{k} {v:.4f}" for k, v in d.items()))
        if self.best_sharp_weight is not None:
            lines.append(f"\n1X2 로그 손실이 가장 낮은 sharp_weight: {self.best_sharp_weight:.1f}")
        if self.betting:
            lines += ["", "bet365 배팅 시뮬레이션 (1유닛 균등)"]
            lines.append("  전략                 배팅수   적중률    ROI     평균CLV")
            for b in self.betting:
                clv = f"{b['clv']:+.2%}" if b["clv"] is not None else "   -"
                lines.append(f"  {b['strategy']:<20} {b['bets']:>5}   {b['hit']:.1%}   {b['roi']:+.2%}   {clv}")
        return "\n".join(lines)


def _book_probs(row: pd.Series, book: str, market: str, method: str = "power") -> Optional[Dict[str, float]]:
    cols = {o: c for c, (b, mk, o) in ODDS_COLUMNS.items() if b == book and mk == market}
    if len(cols) != len(MARKETS[market]) or not all(c in row.index for c in cols.values()):
        return None
    odds = [row[cols[o]] for o in MARKETS[market]]
    if any(pd.isna(x) or x <= 1 for x in odds):
        return None
    return dict(zip(MARKETS[market], devig(odds, method)))


def _book_odds(row: pd.Series, book: str, market: str) -> Optional[Dict[str, float]]:
    cols = {o: c for c, (b, mk, o) in ODDS_COLUMNS.items() if b == book and mk == market}
    if not cols or not all(c in row.index and pd.notna(row[c]) for c in cols.values()):
        return None
    return {o: float(row[c]) for o, c in cols.items()}


def run(df: pd.DataFrame, start: Optional[str] = None, sharp_weight: float = 0.8, min_ev: float = 0.02,
        model_only_min_ev: float = 0.10, min_train: int = 300) -> BacktestReport:
    wf = walk_forward(df, start, min_train=min_train)
    if wf.empty:
        raise ValueError("백테스트할 경기가 없습니다 (학습 데이터가 부족함)")
    period = f"{wf['date'].min():%Y-%m-%d} ~ {wf['date'].max():%Y-%m-%d}"
    actual = {mk: [_outcome(mk, int(h), int(a)) for h, a in zip(wf["hg"], wf["ag"])] for mk in EVAL_MARKETS}

    # 기준선: 학습 구간 전체의 결과 빈도
    train = df[df["date"] < wf["date"].min()]
    ll: Dict[str, Dict[str, float]] = {}
    for mk in EVAL_MARKETS:
        base = pd.Series([_outcome(mk, int(h), int(a)) for h, a in zip(train["hg"], train["ag"])]).value_counts(normalize=True)
        p_model = np.array([wf.iloc[i][f"model_{mk}_{o}"] for i, o in enumerate(actual[mk])])
        p_base = np.array([base.get(o, 1e-6) for o in actual[mk]])
        ll[mk] = {"model": _log_loss(p_model), "baseline": _log_loss(p_base)}

    report = BacktestReport(n_matches=len(wf), period=period, log_loss=ll)
    if not has_odds(wf):
        return report

    # Pinnacle 과 블렌드 비교 (1X2)
    sharp_rows = [(i, _book_probs(r, "pinnacle", "1X2")) for i, (_, r) in enumerate(wf.iterrows())]
    sharp_rows = [(i, p) for i, p in sharp_rows if p]
    if sharp_rows:
        losses = {}
        for w in np.round(np.arange(0, 1.01, 0.1), 1):
            ps = []
            for i, sp in sharp_rows:
                o = actual["1X2"][i]
                ps.append(w * sp[o] + (1 - w) * wf.iloc[i][f"model_1X2_{o}"])
            losses[w] = _log_loss(np.array(ps))
        ll["1X2"]["pinnacle"] = losses[1.0]
        ll["1X2"][f"blend({sharp_weight})"] = losses.get(round(sharp_weight, 1), np.nan)
        report.best_sharp_weight = float(min(losses, key=losses.get))

    strategies = {"sharp+model": sharp_weight, "pinnacle only": 1.0, "model only": 0.0}
    for name, w in strategies.items():
        bets = []
        for i, (_, r) in enumerate(wf.iterrows()):
            for mk in ("1X2", "OU2.5"):
                b365 = _book_odds(r, "bet365", mk)
                if not b365 or len(b365) != len(MARKETS[mk]):
                    continue
                model = {o: r[f"model_{mk}_{o}"] for o in MARKETS[mk]}
                sharp = _book_probs(r, "pinnacle", mk)
                if w > 0 and not sharp:
                    continue
                fair = {o: w * (sharp[o] if sharp else 0) + (1 - w) * model[o] for o in MARKETS[mk]}
                thr = model_only_min_ev if w == 0 else min_ev
                close = _book_probs(r, "pinnacle_close", mk)
                for o in MARKETS[mk]:
                    if fair[o] * b365[o] - 1 >= thr:
                        win = actual[mk][i] == o
                        clv = close[o] * b365[o] - 1 if close else None
                        bets.append((b365[o] - 1 if win else -1.0, win, clv))
        if bets:
            clvs = [c for _, _, c in bets if c is not None]
            report.betting.append({
                "strategy": name, "bets": len(bets),
                "hit": float(np.mean([b[1] for b in bets])),
                "roi": float(np.mean([b[0] for b in bets])),
                "clv": float(np.mean(clvs)) if clvs else None,
            })
        else:
            report.betting.append({"strategy": name, "bets": 0, "hit": 0.0, "roi": 0.0, "clv": None})
    return report

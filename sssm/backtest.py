"""Walk-forward 백테스트.

매주 그 주 이전 경기로만 Dixon-Coles 를 다시 학습하고 그 주 경기를 예측한다
(미래 정보 누수 없음).

1. 결과만 있는 CSV: 모델의 예측력(로그 손실, 브라이어, 정확도)을 단순 기준선과 비교한다.
2. 배당 컬럼이 있는 CSV(football-data.co.uk): 시장 배당 자체의 로그 손실과 비교하고,
   bet365 시가(B365H 등, 경기 며칠 전 수집)에 +EV 단식·조합을 걸었을 때의
   수익률(ROI, 95% 신뢰구간), 마감 배당 대비 CLV, 최적 sharp_weight 를 계산한다.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

from . import markets as mkt
from .history import ODDS_COLUMNS, has_odds
from .model import DixonColes
from .markets import Selection
from .odds import devig
from .parlay import Parlay

EVAL_MARKETS = ("1X2", "OU:2.5", "BTTS")


def _outcome(market: str, hg: int, ag: int) -> str:
    if market == "1X2":
        return "home" if hg > ag else "draw" if hg == ag else "away"
    if market == "OU:2.5":
        return "over" if hg + ag > 2.5 else "under"
    return "yes" if hg > 0 and ag > 0 else "no"


def walk_forward(df: pd.DataFrame, start: Optional[str] = None, min_train: int = 300,
                 **model_kwargs) -> pd.DataFrame:
    """각 경기에 대해 학습 시점 이전 데이터만 쓴 모델 확률(model_<마켓>_<결과>)을 붙여 돌려준다.

    model_kwargs 는 DixonColes(xi=..., ridge=...) 로 전달된다.
    """
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
        model = DixonColes(**model_kwargs).fit(train, as_of=as_of)
        for i, m in chunk.iterrows():
            pred = model.predict(m["home"], m["away"], EVAL_MARKETS)
            if pred is None:
                continue
            row = {"idx": i}
            for market in EVAL_MARKETS:
                for o, p in pred[market].items():
                    row[f"model_{market}_{o}"] = p
            rows.append(row)
    if not rows:
        return test.iloc[0:0].drop(columns="week")
    preds = pd.DataFrame(rows).set_index("idx")
    return test.join(preds, how="inner").drop(columns="week")


def _log_loss(p: np.ndarray) -> float:
    return float(-np.mean(np.log(np.clip(p, 1e-12, 1))))


def _book_probs(row: pd.Series, book: str, market: str, method: str = "power") -> Optional[Dict[str, float]]:
    odds = _book_odds(row, book, market)
    if not odds or len(odds) != len(mkt.outcomes(market)):
        return None
    return dict(zip(mkt.outcomes(market), devig([odds[o] for o in mkt.outcomes(market)], method)))


def _book_odds(row: pd.Series, book: str, market: str) -> Optional[Dict[str, float]]:
    cols = {o: c for c, (b, mk, o) in ODDS_COLUMNS.items() if b == book and mk == market}
    if not cols or not all(c in row.index and pd.notna(row[c]) and row[c] > 1 for c in cols.values()):
        return None
    return {o: float(row[c]) for o, c in cols.items()}


def _summary(returns: List[float], wins: List[bool], clv_pin: List[Optional[float]],
             clv_b365: List[Optional[float]]) -> dict:
    r = np.asarray(returns, dtype=float)
    n = len(r)
    se = float(r.std(ddof=1) / np.sqrt(n)) if n > 1 else float("nan")
    cp = [c for c in clv_pin if c is not None]
    cb = [c for c in clv_b365 if c is not None]
    return {
        "bets": n,
        "hit": float(np.mean(wins)) if n else 0.0,
        "roi": float(r.mean()) if n else 0.0,
        "roi_lo": float(r.mean() - 1.96 * se) if n > 1 else None,
        "roi_hi": float(r.mean() + 1.96 * se) if n > 1 else None,
        "profit": float(r.sum()),
        "clv": float(np.mean(cp)) if cp else None,
        "clv_n": len(cp),
        "clv_b365": float(np.mean(cb)) if cb else None,
    }


@dataclass
class BacktestReport:
    n_matches: int
    period: str
    log_loss: Dict[str, Dict[str, float]]  # market -> {model, baseline, ...}
    betting: List[dict] = field(default_factory=list)  # 단식 (전략별)
    parlays: List[dict] = field(default_factory=list)  # 조합 (전략 x 방식)
    by_season: List[dict] = field(default_factory=list)  # 대표 전략 단식의 시즌별 성과
    market_loss: Dict[str, Dict[str, float]] = field(default_factory=dict)  # 배당이 모두 있는 경기에서 비교
    best_sharp_weight: Optional[float] = None
    brier_1x2: float = float("nan")
    accuracy_1x2: float = float("nan")

    def to_text(self) -> str:
        lines = [f"백테스트: {self.n_matches}경기 ({self.period})", "", "로그 손실 (낮을수록 좋음)"]
        for mk, d in self.log_loss.items():
            lines.append("  " + mk.ljust(7) + "  ".join(f"{k} {v:.4f}" for k, v in d.items()))
        lines.append(f"\n1X2 브라이어 {self.brier_1x2:.4f}  정확도 {self.accuracy_1x2:.1%}")
        if self.market_loss:
            lines += ["", "시장 배당과 비교 (배당이 모두 있는 경기만, 마진 제거)"]
            for mk, d in self.market_loss.items():
                lines.append("  " + mk.ljust(7) + "  ".join(
                    f"{k} {v:.4f}" if k != "n" else f"n={int(v)}" for k, v in d.items()))
        if self.best_sharp_weight is not None:
            lines.append(f"1X2 로그 손실이 가장 낮은 sharp_weight: {self.best_sharp_weight:.1f}")

        def fmt(b: dict, name: str) -> str:
            ci = f"[{b['roi_lo']:+.1%}, {b['roi_hi']:+.1%}]" if b.get("roi_lo") is not None else "      -"
            clv = f"{b['clv']:+.2%}" if b.get("clv") is not None else "   -"
            clvb = f"{b['clv_b365']:+.2%}" if b.get("clv_b365") is not None else "   -"
            return (f"  {name:<30} {b['bets']:>5}  {b['hit']:6.1%}  {b['roi']:+7.2%} {ci:<18} "
                    f"{b['profit']:+8.1f}  {clv:>7}  {clvb:>7}")

        header = f"  {'전략':<28} {'배팅':>6}  {'적중':>6}  {'ROI':>7} {'95% 구간':<17} {'손익(u)':>8}  {'CLV(P)':>7}  {'CLV(B)':>7}"
        if self.betting:
            lines += ["", "bet365 시가 단식 (1유닛 균등)", header]
            lines += [fmt(b, b["strategy"]) for b in self.betting]
        if self.parlays:
            lines += ["", "bet365 시가 조합 (1유닛 균등, 서로 다른 경기)", header]
            lines += [fmt(b, f"{b['strategy']} / {b['kind']}") for b in self.parlays]
        if self.by_season:
            lines += ["", f"시즌별 단식 ({self.by_season[0]['strategy']})", header]
            lines += [fmt(b, b["season"]) for b in self.by_season]
        if self.betting:
            lines += ["", "CLV(P): Pinnacle 마감 공정확률 x 건 배당 - 1, CLV(B): bet365 마감 공정확률 기준"]
        return "\n".join(lines)


def _season(ts: pd.Timestamp) -> str:
    y = ts.year if ts.month >= 7 else ts.year - 1
    return f"{y}-{str(y + 1)[2:]}"


def run(df: pd.DataFrame, start: Optional[str] = None, sharp_weight: float = 0.8, min_ev: float = 0.02,
        model_only_min_ev: float = 0.10, min_train: int = 300, max_odds: float = 15.0,
        **model_kwargs) -> BacktestReport:
    wf = walk_forward(df, start, min_train=min_train, **model_kwargs)
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

    outs = mkt.outcomes("1X2")
    P = wf[[f"model_1X2_{o}" for o in outs]].to_numpy()
    y = np.array([outs.index(o) for o in actual["1X2"]])
    report = BacktestReport(
        n_matches=len(wf), period=period, log_loss=ll,
        brier_1x2=float(((P - np.eye(3)[y]) ** 2).sum(axis=1).mean()),
        accuracy_1x2=float((P.argmax(axis=1) == y).mean()),
    )
    if not has_odds(wf):
        return report
    rows = [r for _, r in wf.iterrows()]

    # 시장 배당 자체의 예측력: 모델이 시장보다 정확한가?
    books = ("bet365", "bet365_close", "pinnacle", "pinnacle_close")
    for mk in ("1X2", "OU:2.5"):
        per = {b: [_book_probs(r, b, mk) for r in rows] for b in books}
        avail = [b for b in books if any(per[b])]
        common = [i for i in range(len(rows)) if all(per[b][i] for b in avail)]
        if not common or not avail:
            continue
        d = {"n": float(len(common)),
             "model": _log_loss(np.array([rows[i][f"model_{mk}_{actual[mk][i]}"] for i in common]))}
        for b in avail:
            d[b] = _log_loss(np.array([per[b][i][actual[mk][i]] for i in common]))
        report.market_loss[mk] = d

    # Pinnacle 과 블렌드 비교 (1X2)
    sharp_rows = [(i, _book_probs(r, "pinnacle", "1X2")) for i, r in enumerate(rows)]
    sharp_rows = [(i, p) for i, p in sharp_rows if p]
    if sharp_rows:
        losses = {}
        for w in np.round(np.arange(0, 1.01, 0.1), 1):
            ps = [w * sp[actual["1X2"][i]] + (1 - w) * rows[i][f"model_1X2_{actual['1X2'][i]}"] for i, sp in sharp_rows]
            losses[w] = _log_loss(np.array(ps))
        ll["1X2"]["pinnacle"] = losses[1.0]
        ll["1X2"][f"blend({sharp_weight})"] = losses.get(round(sharp_weight, 1), np.nan)
        report.best_sharp_weight = float(min(losses, key=losses.get))

    weeks = wf["date"].dt.to_period("W-MON").astype(str).tolist()
    strategies = {"sharp+model": sharp_weight, "pinnacle only": 1.0, "model only": 0.0}
    for name, w in strategies.items():
        singles = []  # (Selection, win, clv_pin, clv_b365, week, season)
        for i, r in enumerate(rows):
            for mk in ("1X2", "OU:2.5"):
                b365 = _book_odds(r, "bet365", mk)
                if not b365 or len(b365) != len(mkt.outcomes(mk)):
                    continue
                sharp = _book_probs(r, "pinnacle", mk)
                if w > 0 and not sharp:
                    continue
                model = {o: r[f"model_{mk}_{o}"] for o in mkt.outcomes(mk)}
                fair = {o: w * (sharp[o] if sharp else 0) + (1 - w) * model[o] for o in mkt.outcomes(mk)}
                thr = model_only_min_ev if w == 0 else min_ev
                close_p = _book_probs(r, "pinnacle_close", mk)
                close_b = _book_probs(r, "bet365_close", mk)
                for o in mkt.outcomes(mk):
                    if fair[o] * b365[o] - 1 < thr or b365[o] > max_odds:
                        continue
                    sel = Selection(fixture_id=str(i), kickoff=str(r["date"]), league="", home=r["home"], away=r["away"],
                                    market=mk, outcome=o, odds=b365[o], fair_prob=float(fair[o]))
                    singles.append((sel, actual[mk][i] == o,
                                    close_p[o] * b365[o] - 1 if close_p else None,
                                    close_b[o] * b365[o] - 1 if close_b else None,
                                    weeks[i], _season(r["date"])))

        report.betting.append({"strategy": name, **_summary(
            [s.odds - 1 if win else -1.0 for s, win, *_ in singles], [x[1] for x in singles],
            [x[2] for x in singles], [x[3] for x in singles])})
        if name == "sharp+model":
            for season in sorted({x[5] for x in singles}):
                g = [x for x in singles if x[5] == season]
                report.by_season.append({"strategy": name, "season": season, **_summary(
                    [s.odds - 1 if win else -1.0 for s, win, *_ in g], [x[1] for x in g],
                    [x[2] for x in g], [x[3] for x in g])})

        # 조합: 주마다 +EV 단식으로 만든 조합. 이 저장소가 추천하는 방식(켈리 로그 성장률 1위)과 전체 2폴 조합
        combos = {"주간 최강 2폴": [], "주간 최강 3폴": [], "전체 2폴": []}
        by_week: Dict[str, list] = {}
        for x in singles:
            by_week.setdefault(x[4], []).append(x)
        for wk, legs in by_week.items():
            info = {id(x[0]): x for x in legs}
            for k, kind in ((2, "주간 최강 2폴"), (3, "주간 최강 3폴")):
                best = None
                for p in _parlays_of(legs, k):
                    if best is None or p.growth > best.growth:
                        best = p
                if best is not None:
                    combos[kind].append([info[id(s)] for s in best.legs])
            for p in _parlays_of(legs, 2):
                combos["전체 2폴"].append([info[id(s)] for s in p.legs])
        for kind, plist in combos.items():
            rets, wins, cp, cb = [], [], [], []
            for legs in plist:
                win = all(x[1] for x in legs)
                odds = float(np.prod([x[0].odds for x in legs]))
                rets.append(odds - 1 if win else -1.0)
                wins.append(win)
                cp.append(float(np.prod([1 + x[2] for x in legs]) - 1) if all(x[2] is not None for x in legs) else None)
                cb.append(float(np.prod([1 + x[3] for x in legs]) - 1) if all(x[3] is not None for x in legs) else None)
            if rets:
                report.parlays.append({"strategy": name, "kind": kind, **_summary(rets, wins, cp, cb)})
    return report


def _parlays_of(legs: list, k: int, pool: int = 12):
    """legs 중 EV 상위 pool 개로 서로 다른 경기 k폴 조합을 만든다."""
    from itertools import combinations

    cands = sorted(legs, key=lambda x: x[0].ev, reverse=True)[:pool]
    for combo in combinations(cands, k):
        if len({x[0].fixture_id for x in combo}) < k:
            continue
        yield Parlay([x[0] for x in combo])

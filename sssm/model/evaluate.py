"""자체 팀 전력 모델 검증: 모델이 시장 확률에 섞일 자격(가중치)을 버는지 본다.

매주 그 주 이전 경기로만 Dixon-Coles 를 다시 학습해 그 주 경기를 예측한다(미래 정보
누수 없음). 로그 손실을 빈도 기준선, bet365, Pinnacle 과 비교하고, Pinnacle 확률에
모델을 로그 풀링으로 섞었을 때 로그 손실이 가장 낮은 가중치를 찾는다. 그 값이
PricingConfig.model_weight 의 근거다.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Optional

import numpy as np
import pandas as pd

from ..odds import devig
from .dixon_coles import DixonColes

EVAL_MARKETS = ("1X2", "OU:2.5", "BTTS")
_COLS = {
    "bet365": {"1X2": ("B365H", "B365D", "B365A"), "OU:2.5": ("B365>2.5", "B365<2.5")},
    "pinnacle": {"1X2": ("PSH", "PSD", "PSA"), "OU:2.5": ("P>2.5", "P<2.5")},
    "pinnacle_close": {"1X2": ("PSCH", "PSCD", "PSCA"), "OU:2.5": ("PC>2.5", "PC<2.5")},
}
_OUTS = {"1X2": ("home", "draw", "away"), "OU:2.5": ("over", "under"), "BTTS": ("yes", "no")}


def _outcome(market: str, hg: int, ag: int) -> int:
    if market == "1X2":
        return 0 if hg > ag else 1 if hg == ag else 2
    if market == "OU:2.5":
        return 0 if hg + ag > 2.5 else 1
    return 0 if hg > 0 and ag > 0 else 1


def walk_forward(df: pd.DataFrame, start: Optional[str] = None, min_train: int = 300, **model_kwargs) -> pd.DataFrame:
    """각 경기에 학습 시점 이전 데이터만 쓴 모델 확률 컬럼 model_<마켓>_<결과> 를 붙인다."""
    df = df.dropna(subset=["hg", "ag"]).sort_values("date").reset_index(drop=True)
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
            rows.append({"idx": i, **{f"model_{mk}_{o}": p for mk in EVAL_MARKETS for o, p in pred[mk].items()}})
    if not rows:
        return test.iloc[0:0].drop(columns="week")
    return test.join(pd.DataFrame(rows).set_index("idx"), how="inner").drop(columns="week")


def _ll(p: np.ndarray) -> float:
    return float(-np.mean(np.log(np.clip(p, 1e-12, 1))))


@dataclass
class ModelReport:
    n_matches: int
    period: str
    log_loss: Dict[str, Dict[str, float]] = field(default_factory=dict)
    n_compared: int = 0
    best_model_weight: Optional[float] = None
    weight_curve: Dict[float, float] = field(default_factory=dict)

    def to_text(self) -> str:
        lines = [f"모델 검증: {self.n_matches}경기 ({self.period})", "", "로그 손실 (낮을수록 좋음)"]
        for mk, d in self.log_loss.items():
            lines.append(f"  {mk:<7}" + "  ".join(f"{k} {v:.4f}" for k, v in d.items()))
        if self.best_model_weight is not None:
            lines.append(f"\nPinnacle 에 모델을 섞는 최적 가중치 (1X2, {self.n_compared}경기): {self.best_model_weight:.2f}")
            lines.append("  " + "  ".join(f"w={w:.2f}: {v:.4f}" for w, v in self.weight_curve.items()))
            lines.append("  -> PricingConfig.model_weight 의 근거. 0 이면 모델은 시장에 아무것도 더하지 못한다.")
        return "\n".join(lines)


def evaluate(df: pd.DataFrame, start: Optional[str] = None, min_train: int = 300, **model_kwargs) -> ModelReport:
    wf = walk_forward(df, start, min_train, **model_kwargs)
    if wf.empty:
        raise ValueError("검증할 경기가 없습니다 (학습 데이터 부족)")
    rep = ModelReport(len(wf), f"{wf['date'].min():%Y-%m-%d} ~ {wf['date'].max():%Y-%m-%d}")
    train = df[df["date"] < wf["date"].min()].dropna(subset=["hg", "ag"])
    for mk in EVAL_MARKETS:
        y = np.array([_outcome(mk, int(h), int(a)) for h, a in zip(wf["hg"], wf["ag"])])
        pm = wf[[f"model_{mk}_{o}" for o in _OUTS[mk]]].to_numpy()
        yb = np.array([_outcome(mk, int(h), int(a)) for h, a in zip(train["hg"], train["ag"])])
        base = np.bincount(yb, minlength=len(_OUTS[mk])) / max(len(yb), 1)
        d = {"model": _ll(pm[np.arange(len(y)), y]), "baseline": _ll(base[y])}
        for book, cols in _COLS.items():
            c = cols.get(mk)
            if not c or not set(c).issubset(wf.columns):
                continue
            ok = wf[list(c)].notna().all(axis=1).to_numpy() & (wf[list(c)] > 1).all(axis=1).to_numpy()
            if ok.sum() < 50:
                continue
            pb = np.array([devig(r) for r in wf.loc[ok, list(c)].to_numpy(dtype=float)])
            d[book] = _ll(pb[np.arange(ok.sum()), y[ok]])
            d[f"model(같은 {ok.sum()}경기)"] = _ll(pm[ok][np.arange(ok.sum()), y[ok]])
        rep.log_loss[mk] = d

    c = _COLS["pinnacle"]["1X2"]
    if set(c).issubset(wf.columns):
        ok = wf[list(c)].notna().all(axis=1).to_numpy()
        if ok.sum() >= 50:
            y = np.array([_outcome("1X2", int(h), int(a)) for h, a in zip(wf["hg"], wf["ag"])])[ok]
            ps = np.array([devig(r) for r in wf.loc[ok, list(c)].to_numpy(dtype=float)])
            pm = wf.loc[ok, [f"model_1X2_{o}" for o in _OUTS["1X2"]]].to_numpy()
            for w in np.round(np.arange(0, 0.51, 0.05), 2):
                p = np.exp((1 - w) * np.log(ps) + w * np.log(np.clip(pm, 1e-12, 1)))
                p /= p.sum(axis=1, keepdims=True)
                rep.weight_curve[float(w)] = _ll(p[np.arange(len(y)), y])
            rep.best_model_weight = min(rep.weight_curve, key=rep.weight_curve.get)
            rep.n_compared = int(ok.sum())
    return rep

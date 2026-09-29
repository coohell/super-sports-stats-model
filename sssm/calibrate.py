"""샤프-소프트 가격 차이 중 얼마를 믿을지(shrink) 과거 데이터로 정한다.

Pinnacle 시가가 bet365 시가와 다를 때, 진짜 확률(가장 좋은 추정치는 Pinnacle
마감)이 그 차이를 얼마나 따라가는지 본다.

  y = p(Pinnacle 마감) − p(bet365 시가)
  x = p(Pinnacle 시가) − p(bet365 시가)
  slope  = Σxy / Σx²          (전체 결과, 원점을 지나는 회귀 기울기)
  shrink = Σ(y·o) / Σ(x·o)     (샤프 기준 EV > 0 이라 실제로 걸게 되는 쪽만, o = bet365 배당)

shrink = 1 이면 Pinnacle 시가 차이가 전부 진짜, 0 이면 전부 잡음이다. 배팅할 쪽만
보는 이유는 선택 편향 때문이다. 차이가 커서 고른 곳일수록 일부는 Pinnacle 시가의
잡음이라 마감까지 덜 살아남는다(EPL: 전체 기울기 0.9, 배팅 쪽 0.75). 결과로 채점하는
ROI 보다 훨씬 잡음이 적어 수백 경기로도 안정적으로 추정된다.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np
import pandas as pd

from .odds import devig

SOFT = ("B365H", "B365D", "B365A")
SHARP = ("PSH", "PSD", "PSA")
CLOSE = ("PSCH", "PSCD", "PSCA")


def _devig_rows(df: pd.DataFrame, cols) -> np.ndarray:
    return np.array([devig(r) for r in df[list(cols)].to_numpy(dtype=float)])


@dataclass
class ShrinkEstimate:
    shrink: float  # 배팅 쪽 기준 (가격 결정에 쓰는 값)
    slope: float  # 전체 결과 기준
    n_matches: int
    n_value: int  # 샤프 기준 EV > 0 이었던 선택지 수
    pred_ev: float  # 그 선택지들의 샤프 시가 기준 평균 EV
    clv: float  # 같은 선택지들의 Pinnacle 마감 기준 평균 EV (실제로 살아남은 가치)

    def to_text(self) -> str:
        return (f"shrink {self.shrink:.2f} (전체 기울기 {self.slope:.2f}, {self.n_matches}경기) | "
                f"샤프 기준 +EV {self.n_value}건: 예측 EV {self.pred_ev:+.2%} -> 마감 CLV {self.clv:+.2%}")


def shrink_from_history(df: pd.DataFrame, soft=SOFT, sharp=SHARP, close=CLOSE, min_ev: float = 0.0,
                        min_value: int = 30) -> Optional[ShrinkEstimate]:
    need = list(soft) + list(sharp) + list(close)
    if not set(need).issubset(df.columns):
        return None
    d = df.dropna(subset=need)
    d = d[(d[need] > 1.0).all(axis=1)]
    if len(d) < 50:
        return None
    ps, pp, pc = _devig_rows(d, soft), _devig_rows(d, sharp), _devig_rows(d, close)
    o = d[list(soft)].to_numpy(dtype=float)
    x, y = pp - ps, pc - ps
    slope = float((x * y).sum() / (x * x).sum())
    ev = pp * o - 1
    m = ev > min_ev
    if m.sum() < min_value:
        return None
    shrink = float((y[m] * o[m]).sum() / (x[m] * o[m]).sum())
    return ShrinkEstimate(max(0.0, min(1.0, shrink)), slope, len(d), int(m.sum()),
                          float(ev[m].mean()), float((pc * o - 1)[m].mean()))

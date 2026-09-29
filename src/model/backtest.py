"""
Walk-forward 백테스트: 매 라운드 직전까지의 경기로만 학습 → 다음 경기 예측.
지표: 1X2 log-loss / Brier / 정확도 (기준선: 리그 평균 빈도)
배당 CSV(B365H/B365D/B365A 등 마감 배당 컬럼)가 있으면 시장 대비 log-loss와 EV 시뮬레이션 추가.
"""
import argparse
import glob

import numpy as np
import pandas as pd

from src.model.dixon_coles import DixonColes

OUTS = ["home", "draw", "away"]
# football-data.co.uk 컬럼 규칙: 마감 배당(...C*)이 있으면 우선, 없으면 시작 배당. bet365 우선, 다음 Pinnacle.
ODDS_CANDIDATES = [
    ("B365CH", "B365CD", "B365CA"),
    ("PSCH", "PSCD", "PSCA"),
    ("B365H", "B365D", "B365A"),
    ("PSH", "PSD", "PSA"),
]


def find_odds_cols(df):
    for cols in ODDS_CANDIDATES:
        if all(c in df.columns and df[c].notna().any() for c in cols):
            return dict(zip(OUTS, cols))
    return None


def load(paths):
    frames = [pd.read_csv(p) for p in paths]
    df = pd.concat(frames, ignore_index=True)
    raw = df["Date"].astype(str)
    iso = pd.to_datetime(raw, format="%Y-%m-%d", errors="coerce")  # datasets 계열
    dmy = pd.to_datetime(raw, dayfirst=True, errors="coerce", format="mixed")  # football-data.co.uk (dd/mm/yy[yy])
    df["Date"] = iso.fillna(dmy)
    df = df.dropna(subset=["Date", "FTHG", "FTAG"]).sort_values("Date").reset_index(drop=True)
    df["result"] = np.select([df.FTHG > df.FTAG, df.FTHG == df.FTAG], ["home", "draw"], "away")
    return df


def walk_forward(df, test_start, step_days=7, xi=0.0019, min_train=300):
    rows = []
    test_start = pd.Timestamp(test_start)
    cursor = test_start
    end = df.Date.max()
    while cursor <= end:
        nxt = cursor + pd.Timedelta(days=step_days)
        train = df[df.Date < cursor]
        block = df[(df.Date >= cursor) & (df.Date < nxt)]
        cursor = nxt
        if block.empty or len(train) < min_train:
            continue
        m = DixonColes(xi=xi).fit(train, ref_date=block.Date.min())
        for _, r in block.iterrows():
            p = m.predict_1x2(r.HomeTeam, r.AwayTeam)
            if p is None:
                continue
            rows.append({**r.to_dict(), **{f"p_{k}": v for k, v in p.items()}})
    return pd.DataFrame(rows)


def metrics(res, base_freq):
    y = res["result"].map({o: i for i, o in enumerate(OUTS)}).values
    P = res[[f"p_{o}" for o in OUTS]].values
    onehot = np.eye(3)[y]
    out = {
        "n": len(res),
        "logloss": float(-np.log(P[np.arange(len(y)), y]).mean()),
        "brier": float(((P - onehot) ** 2).sum(1).mean()),
        "acc": float((P.argmax(1) == y).mean()),
    }
    B = np.tile(base_freq, (len(y), 1))
    out["baseline_logloss"] = float(-np.log(B[np.arange(len(y)), y]).mean())
    return out


def vs_market(res, min_edge=0.03):
    """배당 컬럼이 있을 때: 마진 제거 시장 확률 대비 log-loss, edge>min_edge 배팅 ROI"""
    ODDS_COLS = find_odds_cols(res)
    if ODDS_COLS is None:
        return None
    r = res.dropna(subset=list(ODDS_COLS.values())).copy()
    if r.empty:
        return None
    inv = np.column_stack([1 / r[ODDS_COLS[o]] for o in OUTS])
    mkt = inv / inv.sum(1, keepdims=True)
    y = r["result"].map({o: i for i, o in enumerate(OUTS)}).values
    P = r[[f"p_{o}" for o in OUTS]].values
    odds = np.column_stack([r[ODDS_COLS[o]] for o in OUTS])
    edge = P * odds - 1
    stake = edge > min_edge
    win = np.eye(3)[y].astype(bool)
    pnl = np.where(stake, np.where(win, odds - 1, -1.0), 0.0)
    n_bets = int(stake.sum())
    return {
        "odds_cols": list(ODDS_COLS.values()),
        "n": len(r),
        "market_logloss": float(-np.log(mkt[np.arange(len(y)), y]).mean()),
        "model_logloss": float(-np.log(P[np.arange(len(y)), y]).mean()),
        "bets": n_bets,
        "roi": float(pnl.sum() / n_bets) if n_bets else None,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="data/history/*.csv")
    ap.add_argument("--test-start", default="2022-08-01")
    ap.add_argument("--xi", type=float, default=0.0019)
    ap.add_argument("--out", default="reports/backtest_results.csv")
    a = ap.parse_args()
    df = load(sorted(glob.glob(a.data)))
    train_part = df[df.Date < a.test_start]
    base = train_part.result.value_counts(normalize=True).reindex(OUTS).values
    res = walk_forward(df, a.test_start, xi=a.xi)
    print("model:", metrics(res, base))
    print("market:", vs_market(res) or "배당 컬럼 없음 - 마감 배당 CSV 필요")
    res.to_csv(a.out, index=False)


if __name__ == "__main__":
    main()

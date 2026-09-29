"""실시간 기록: 배당 스냅샷, 라인 움직임(bet365 지연) 감지, 내가 건 배팅의 CLV.

과거 데이터로는 ROI 를 증명할 만큼 배팅이 쌓이지 않는다(시즌당 수십 건). 그래서
실전에서 가장 빨리 믿을 수 있는 지표는 CLV 다: 내가 건 배당이 경기 직전 Pinnacle
공정 배당보다 좋았는가. 이 모듈은

1. picks 를 돌릴 때마다 배당을 data/snapshots/<날짜>.jsonl 에 쌓고,
2. 직전 스냅샷 대비 Pinnacle 이 움직였는데 bet365 가 그대로인 선택지를 표시하고
   (bet365 가 늦게 따라가는 순간이 남은 엣지의 원천이다),
3. 추천한 배팅을 data/ledger.jsonl 에 기록해 두었다가 `python -m sssm clv` 로
   킥오프 직전 스냅샷 기준 CLV 를 계산한다.
"""
from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Optional

import numpy as np

from .config import ROOT
from .markets import Fixture
from .pricing import PricingConfig, price_fixture, selections

SNAP_DIR = ROOT / "data" / "snapshots"
LEDGER = ROOT / "data" / "ledger.jsonl"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def record_snapshot(fixtures: Iterable[Fixture], directory: Path = SNAP_DIR, ts: Optional[str] = None) -> Path:
    ts = ts or _now()
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{ts[:10]}.jsonl"
    with path.open("a", encoding="utf-8") as f:
        for fx in fixtures:
            f.write(json.dumps({"ts": ts, **asdict(fx)}, ensure_ascii=False) + "\n")
    return path


def load_snapshots(directory: Path = SNAP_DIR) -> Dict[str, List[dict]]:
    """fixture_id -> 시간순 스냅샷 목록."""
    out: Dict[str, List[dict]] = {}
    for p in sorted(Path(directory).glob("*.jsonl")):
        for line in p.read_text(encoding="utf-8").splitlines():
            if line.strip():
                r = json.loads(line)
                out.setdefault(str(r["fixture_id"]), []).append(r)
    for v in out.values():
        v.sort(key=lambda r: r["ts"])
    return out


def _fixture(r: dict) -> Fixture:
    return Fixture(**{k: v for k, v in r.items() if k in Fixture.__dataclass_fields__})


def movements(fixtures: Iterable[Fixture], history: Dict[str, List[dict]], cfg: Optional[PricingConfig] = None,
              min_move: float = 0.01) -> Dict[tuple, dict]:
    """직전 스냅샷 대비 공정 확률 변화와 bet365 배당 변화.

    (fixture_id, market, outcome) -> {"fair_move", "odds_move", "stale"}.
    stale: 샤프 공정 확률이 min_move 이상 이 결과 쪽으로 움직였는데 bet365 배당은 그대로이거나 올랐다.
    """
    cfg = cfg or PricingConfig()
    out: Dict[tuple, dict] = {}
    for fx in fixtures:
        prev = [r for r in history.get(fx.fixture_id, [])]
        if not prev:
            continue
        old = _fixture(prev[-1])
        fp_new, fp_old = price_fixture(fx, None, cfg), price_fixture(old, None, cfg)
        if fp_new is None or fp_old is None:
            continue
        old_sel = {(s.market, s.outcome): s for s in selections(fp_old, cfg)}
        for s in selections(fp_new, cfg):
            o = old_sel.get((s.market, s.outcome))
            if o is None:
                continue
            fm, om = s.fair_prob - o.fair_prob, s.odds - o.odds
            out[(fx.fixture_id, s.market, s.outcome)] = {
                "fair_move": fm, "odds_move": om, "stale": bool(fm >= min_move and om >= 0), "since": prev[-1]["ts"],
            }
    return out


def log_bets(bets: Iterable, bankroll: Optional[float] = None, path: Path = LEDGER, ts: Optional[str] = None) -> Path:
    """추천(또는 실제로 건) 배팅을 기록한다. bets: portfolio.Bet 목록."""
    ts = ts or _now()
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        for b in bets:
            f.write(json.dumps({
                "ts": ts, "odds": b.odds, "stake": b.stake, "amount": (bankroll or 0) * b.stake, "edge": b.edge,
                "legs": [{"fixture_id": s.fixture_id, "kickoff": s.kickoff, "match": s.match, "market": s.market,
                          "outcome": s.outcome, "odds": s.odds} for s in b.legs],
            }, ensure_ascii=False) + "\n")
    return path


def clv_report(path: Path = LEDGER, directory: Path = SNAP_DIR, cfg: Optional[PricingConfig] = None) -> List[dict]:
    """기록된 배팅마다 킥오프 전 마지막 스냅샷의 샤프 공정 확률로 CLV 를 계산한다."""
    cfg = cfg or PricingConfig()
    path = Path(path)
    if not path.exists():
        return []
    snaps = load_snapshots(directory)
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        bet = json.loads(line)
        ret, last_ts = 1.0, None
        for leg in bet["legs"]:
            hist = [r for r in snaps.get(str(leg["fixture_id"]), []) if r["ts"] <= leg["kickoff"] and r["ts"] >= bet["ts"]]
            if not hist:
                ret = None
                break
            fp = price_fixture(_fixture(hist[-1]), None, cfg)
            sel = None if fp is None else next((s for s in selections(fp, cfg)
                                                if s.market == leg["market"] and s.outcome == leg["outcome"]), None)
            if fp is None or sel is None:
                ret = None
                break
            W, R = sel.W, sel.R
            ret *= float(fp.fair @ (W * leg["odds"] + R))
            last_ts = hist[-1]["ts"]
        rows.append({"ts": bet["ts"], "picks": " + ".join(f"{l['match']} {l['market']} {l['outcome']}" for l in bet["legs"]),
                     "odds": bet["odds"], "stake": bet["stake"], "edge": bet["edge"],
                     "clv": None if ret is None else ret - 1.0, "closing_snapshot": last_ts})
    return rows


def summarize_clv(rows: List[dict]) -> str:
    done = [r for r in rows if r["clv"] is not None]
    if not done:
        return f"기록된 배팅 {len(rows)}건, 킥오프 직전 스냅샷이 있는 배팅이 아직 없습니다."
    clv = np.array([r["clv"] for r in done])
    se = clv.std(ddof=1) / np.sqrt(len(clv)) if len(clv) > 1 else float("nan")
    return (f"CLV 계산 {len(done)}/{len(rows)}건: 평균 {clv.mean():+.2%} (95% 구간 ±{1.96 * se:.2%}), "
            f"양수 비율 {np.mean(clv > 0):.0%}, 예측 엣지 평균 {np.mean([r['edge'] for r in done]):+.2%}")

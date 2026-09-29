"""명령줄 진입점: python -m sssm <명령>

  picks     오늘의 +EV 선택지와 최강 조합
  backtest  과거 데이터로 모델/전략 검증
  ratings   팀 전력 순위
  fetch-history  시즌 CSV(결과+bet365/Pinnacle 시가·마감 배당) 내려받기
"""
from __future__ import annotations

import argparse
import logging
from pathlib import Path

from . import backtest, history, pipeline
from .config import ROOT
from .pricing import PricingConfig, ValueFilter


def _print_report(rep: pipeline.Report) -> None:
    print(f"소스: {rep.source}  경기 {len(rep.fixtures)}개  선택지 {len(rep.selections)}개  +EV {len(rep.value)}개")
    for n in rep.notes:
        print(f"  참고: {n}")
    print("\n+EV 단식 (EV 순)")
    for s in rep.value[:15]:
        print(f"  {s.match:<34} {s.label:<10} @{s.odds:<5.2f} 공정 {s.fair_prob:6.1%}  EV {s.ev:+6.1%}  [{s.source}]")
    print("\n최강 조합 (켈리 로그 성장률 순, 단식 포함)")
    for i, p in enumerate(rep.parlays, 1):
        legs = " + ".join(f"{s.home[:10]}-{s.away[:10]} {s.label}" for s in p.legs)
        print(f"  {i:>2}. {len(p.legs)}폴 @{p.odds:6.2f}  적중 {p.prob:6.1%}  EV {p.ev:+6.1%}  배팅 {p.stake:5.2%}  | {legs}")


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(prog="sssm", description="bet365 +EV 조합 탐색기")
    sub = ap.add_subparsers(dest="cmd", required=True)

    pk = sub.add_parser("picks", help="+EV 선택지와 최강 조합")
    pk.add_argument("--source", choices=["demo", "file", "apifootball", "theodds"], default="demo")
    pk.add_argument("--file", type=Path, help="--source file 일 때 경기/배당 JSON")
    pk.add_argument("--league", type=int, default=39, help="API-Football 리그 id (39=EPL)")
    pk.add_argument("--season", type=int, default=2025)
    pk.add_argument("--days", type=int, default=3)
    pk.add_argument("--sport", default="aussierules_afl", help="TheOddsAPI 종목 키")
    pk.add_argument("--markets", default="h2h,spreads,totals",
                    help="TheOddsAPI 마켓 (h2h,spreads,totals,btts). btts 는 경기당 크레딧을 씁니다")
    pk.add_argument("--min-ev", type=float, default=0.02)
    pk.add_argument("--sharp-weight", type=float, default=0.8)
    pk.add_argument("--max-legs", type=int, default=3)
    pk.add_argument("--kelly", type=float, default=0.25, help="켈리 분수 (0.25 = 1/4 켈리)")
    pk.add_argument("--out", type=Path, default=ROOT / "reports" / "latest.json")

    bt = sub.add_parser("backtest", help="walk-forward 백테스트")
    bt.add_argument("--csv", type=Path, nargs="*",
                    help="결과/배당 CSV (기본: data/history/ 에 받은 CSV, 없으면 내장 EPL 2015-25 결과)")
    bt.add_argument("--start", help="검증 시작일 (YYYY-MM-DD)")
    bt.add_argument("--sharp-weight", type=float, default=0.8)
    bt.add_argument("--min-ev", type=float, default=0.02)

    rt = sub.add_parser("ratings", help="팀 전력 순위")
    rt.add_argument("--csv", type=Path, nargs="*")

    fh = sub.add_parser("fetch-history", help="시즌 CSV 내려받기 (football-data.co.uk 또는 GitHub 미러)")
    fh.add_argument("--source", choices=["football-data", "mirror"], default="football-data",
                    help="mirror: football-data.co.uk 가 막혔을 때 GitHub 미러(EPL 만)에서 받기")
    fh.add_argument("--league", default="E0", help="E0=EPL, E1=챔피언십, SP1=라리가, D1=분데스, I1=세리에A, F1=리그1")
    fh.add_argument("--seasons", nargs="+", default=["2122", "2223", "2324", "2425"], help='"2425" = 2024/25')
    fh.add_argument("--out", type=Path, default=ROOT / "data" / "history")

    a = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    if a.cmd == "picks":
        st = pipeline.Settings(
            pricing=PricingConfig(sharp_weight=a.sharp_weight),
            value=ValueFilter(min_ev=a.min_ev),
            max_legs=a.max_legs, kelly_fraction=a.kelly,
        )
        if a.source == "demo":
            rep = pipeline.run_file(settings=st)
        elif a.source == "file":
            rep = pipeline.run_file(a.file, settings=st)
        elif a.source == "apifootball":
            rep = pipeline.run_apifootball(a.league, a.season, a.days, st)
        else:
            rep = pipeline.run_theoddsapi(a.sport, st, tuple(a.markets.split(",")))
        _print_report(rep)
        print(f"\n저장: {rep.save(a.out)}")
    elif a.cmd == "backtest":
        df = history.load(a.csv or history.history_files() or history.DEFAULT_RESULTS)
        print(backtest.run(df, a.start, sharp_weight=a.sharp_weight, min_ev=a.min_ev).to_text())
        if not history.has_odds(df):
            print("\n배당 컬럼이 없어 ROI 는 계산하지 않았습니다. `python -m sssm fetch-history` 로 배당을 받으면 계산합니다.")
    elif a.cmd == "fetch-history":
        if a.source == "mirror":
            if a.league != "E0":
                ap.error("미러는 EPL(E0)만 있습니다")
            paths = history.download_mirror(a.seasons, a.out)
        else:
            paths = history.download(a.league, a.seasons, a.out)
        for p in paths:
            print("저장:", p)
    elif a.cmd == "ratings":
        from .model import DixonColes

        m = DixonColes().fit(history.load(a.csv or history.DEFAULT_RESULTS))
        print(f"홈 이점 {m.home_adv_:+.3f}  rho {m.rho_:+.3f}\n")
        print(m.ratings().round(3).to_string(index=False))

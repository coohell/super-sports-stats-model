"""명령줄 진입점: python -m sssm <명령>

  picks       오늘의 최강 조합 (단식+멀티 포트폴리오)
  backtest    과거 배당으로 엔진 전체를 walk-forward 검증 (ROI, CLV, 신뢰구간)
  calibrate   샤프-bet365 차이 중 믿을 비율(shrink) 추정
  model-eval  자체 팀 전력 모델이 시장에 더할 게 있는지 검증
  sgp         같은 경기 조합(Bet Builder) 가격 평가
  clv         기록해 둔 추천 배팅의 CLV
  ratings     팀 전력 순위
  fetch-history  football-data.co.uk 시즌 CSV 받기
"""
from __future__ import annotations

import argparse
import logging
from pathlib import Path

from . import backtest, history, pipeline, tracking
from .calibrate import shrink_from_history
from .config import ROOT
from .portfolio import BET365_ACCA_BOOST_EXAMPLE, PortfolioConfig
from .pricing import PricingConfig, ValueFilter


def _print_report(rep: pipeline.Report) -> None:
    pf = rep.portfolio
    bank = rep.settings.bankroll
    print(f"소스: {rep.source}  경기 {len(rep.fixtures)}  선택지 {len(rep.selections)}  +엣지 {len(rep.value)}")
    for n in rep.notes:
        print(f"  참고: {n}")
    print(f"\n+엣지 선택지 (보정 엣지 순, shrink {rep.settings.pricing.shrink:.2f})")
    for s in rep.value[:15]:
        print(f"  {s.match:<32} {s.label:<14} @{s.odds:<5.2f} 공정 {s.fair_odds:5.2f} ({s.fair_prob:5.1%})  "
              f"EV {s.ev:+6.1%}  엣지 {s.edge:+6.2%}  [{s.source}]")
    print("\n최강 조합 (포트폴리오 켈리)")
    if not pf.bets:
        print("  오늘은 걸 만한 배팅이 없습니다.")
    for i, b in enumerate(pf.bets, 1):
        legs = " + ".join(f"{s.home[:12]}-{s.away[:12]} {s.label}" for s in b.legs)
        print(f"  {i:>2}. {b.kind:<7} @{b.odds:6.2f}  적중 {b.win_prob:5.1%}  EV {b.ev:+6.1%}  엣지 {b.edge:+6.2%}  "
              f"{bank * b.stake:>10,.0f}원  | {legs}")
    if pf.bets:
        print(f"\n  합계 {bank * pf.total_stake:,.0f}원 (자본의 {pf.total_stake:.2%}), 기대 {bank * pf.exp_return:+,.0f}원, "
              f"손실 확률 {pf.p_loss:.0%}")


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(prog="sssm", description="bet365 최강 조합 탐색기")
    sub = ap.add_subparsers(dest="cmd", required=True)

    def engine_args(p):
        p.add_argument("--shrink", type=float, default=PricingConfig.shrink,
                       help="샤프-bet365 차이 중 믿을 비율 (calibrate 로 추정)")
        p.add_argument("--min-edge", type=float, default=ValueFilter.min_edge, help="보정 엣지 문턱")
        p.add_argument("--max-legs", type=int, default=PortfolioConfig.max_legs)
        p.add_argument("--kelly", type=float, default=PortfolioConfig.kelly_fraction, help="켈리 분수")
        p.add_argument("--max-bet", type=float, default=PortfolioConfig.max_bet, help="배팅 하나 상한 (자본 대비)")
        p.add_argument("--max-total", type=float, default=PortfolioConfig.max_total, help="하루 총액 상한")
        p.add_argument("--acca-boost", action="store_true",
                       help="bet365 Acca Boost 예시 표(2폴 5%%~14폴 70%%)를 적용. 지역 조건을 먼저 확인하세요")

    pk = sub.add_parser("picks", help="오늘의 최강 조합")
    pk.add_argument("--source", choices=["demo", "file", "apifootball", "theodds"], default="demo")
    pk.add_argument("--file", type=Path, help="--source file 일 때 경기/배당 JSON")
    pk.add_argument("--league", type=int, default=39, help="API-Football 리그 id (39=EPL)")
    pk.add_argument("--season", type=int, default=2025)
    pk.add_argument("--days", type=int, default=3)
    pk.add_argument("--sport", default="aussierules_afl", help="TheOddsAPI 종목 키")
    pk.add_argument("--markets", default="h2h,spreads,totals", help="TheOddsAPI 마켓 (h2h,spreads,totals,btts)")
    pk.add_argument("--bankroll", type=float, default=1_000_000, help="자본 (원)")
    pk.add_argument("--model-weight", type=float, default=0.0, help="자체 모델 섞는 비율 (model-eval 로 근거 확인)")
    pk.add_argument("--record", action="store_true", help="배당 스냅샷과 추천 배팅을 data/ 에 기록 (CLV 추적)")
    pk.add_argument("--out", type=Path, default=ROOT / "reports" / "latest.json")
    engine_args(pk)

    bt = sub.add_parser("backtest", help="과거 배당으로 엔진 전체 검증")
    bt.add_argument("--csv", type=Path, nargs="+", help="football-data 형식 배당 CSV (기본: data/history/*.csv)")
    bt.add_argument("--start", help="검증 시작일 (YYYY-MM-DD)")
    bt.add_argument("--phase", choices=list(backtest.PHASES), default="open",
                    help="open: 시가로 걸고 마감으로 CLV. close: 마감 직전 가격으로 건다")
    bt.add_argument("--no-calibrate", action="store_true", help="shrink 를 과거로 다시 추정하지 않고 --shrink 고정")
    bt.add_argument("--bets-out", type=Path, help="배팅 내역 CSV 저장 경로")
    engine_args(bt)

    cb = sub.add_parser("calibrate", help="shrink 추정")
    cb.add_argument("--csv", type=Path, nargs="+")

    me = sub.add_parser("model-eval", help="자체 모델 walk-forward 검증")
    me.add_argument("--csv", type=Path, nargs="*")
    me.add_argument("--start")

    sg = sub.add_parser("sgp", help="같은 경기 조합(Bet Builder) 가격 평가")
    sg.add_argument("--file", type=Path, default=pipeline.SAMPLE_FIXTURES)
    sg.add_argument("--fixture", required=True, help="fixture_id")
    sg.add_argument("--legs", required=True, nargs="+", help='마켓=결과, 예: 1X2=home OU:2.5=over BTTS=yes')
    sg.add_argument("--odds", type=float, help="bet365 가 제시한 Bet Builder 배당")

    sub.add_parser("clv", help="기록한 추천 배팅의 CLV")

    rt = sub.add_parser("ratings", help="팀 전력 순위")
    rt.add_argument("--csv", type=Path, nargs="*")

    fh = sub.add_parser("fetch-history", help="football-data.co.uk 시즌 CSV 내려받기")
    fh.add_argument("--league", default="E0", help="E0=EPL, E1=챔피언십, SP1=라리가, D1=분데스, I1=세리에A, F1=리그1")
    fh.add_argument("--seasons", nargs="+", default=["2122", "2223", "2324", "2425"], help='"2425" = 2024/25')
    fh.add_argument("--out", type=Path, default=ROOT / "data" / "history")

    a = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    def configs():
        pricing = PricingConfig(shrink=a.shrink, model_weight=getattr(a, "model_weight", 0.0))
        port = PortfolioConfig(kelly_fraction=a.kelly, max_legs=a.max_legs, max_bet=a.max_bet, max_total=a.max_total,
                               acca_bonus=dict(BET365_ACCA_BOOST_EXAMPLE) if a.acca_boost else {})
        return pricing, ValueFilter(min_edge=a.min_edge), port

    def history_csvs(paths):
        paths = paths or sorted((ROOT / "data" / "history").glob("*.csv"))
        if not paths:
            raise SystemExit("배당 CSV 가 없습니다. --csv 로 넣거나 fetch-history 로 data/history/ 에 받으세요.")
        return history.load(paths)

    if a.cmd == "picks":
        pricing, value, port = configs()
        st = pipeline.Settings(pricing=pricing, value=value, portfolio=port, bankroll=a.bankroll, record=a.record)
        if a.source == "demo":
            rep = pipeline.run_file(settings=st)
        elif a.source == "file":
            rep = pipeline.run_file(a.file, settings=st)
        elif a.source == "apifootball":
            rep = pipeline.run_apifootball(a.league, a.season, a.days, st)
        else:
            rep = pipeline.run_theoddsapi(a.sport, st, tuple(a.markets.split(",")))
        _print_report(rep)
        out = rep.save(a.out)
        md = out.with_suffix(".md")
        md.write_text(rep.to_markdown(), encoding="utf-8")
        print(f"\n저장: {out}, {md}")
    elif a.cmd == "backtest":
        pricing, value, port = configs()
        df = history_csvs(a.csv)
        strategies = [
            backtest.Strategy("단식 균등 1%", PortfolioConfig(max_legs=1), value, flat=True),
            backtest.Strategy("단식 켈리", PortfolioConfig(**{**port.__dict__, "max_legs": 1, "acca_bonus": {}}), value),
            backtest.Strategy("최강 조합 (단식+멀티 켈리)", port, value),
        ]
        res = backtest.run(df, a.start, a.phase, pricing, strategies, calibrate=not a.no_calibrate)
        print(res.to_text())
        if a.bets_out:
            import pandas as pd

            pd.concat([r.bets.assign(strategy=r.name) for r in res.results]).to_csv(a.bets_out, index=False)
            print(f"배팅 내역: {a.bets_out}")
    elif a.cmd == "calibrate":
        est = shrink_from_history(history_csvs(a.csv))
        print(est.to_text() if est else "Pinnacle 시가·마감과 bet365 시가가 모두 있는 경기가 부족합니다.")
    elif a.cmd == "model-eval":
        from .model.evaluate import evaluate

        print(evaluate(history.load(a.csv or history.DEFAULT_RESULTS), a.start).to_text())
    elif a.cmd == "sgp":
        from .portfolio import joint_prob
        from .pricing import price_fixture, selections

        fx = next((f for f in pipeline.load_fixtures_json(a.file) if f.fixture_id == a.fixture), None)
        if fx is None:
            raise SystemExit(f"경기 {a.fixture} 가 {a.file} 에 없습니다")
        fp = price_fixture(fx)
        if fp is None:
            raise SystemExit("가격을 매길 배당이 없습니다")
        # 선택지 정산 격자만 필요하므로 bet365 가 그 마켓을 내지 않았어도 된다
        from . import markets as mk

        legs = []
        for spec in a.legs:
            market, _, outcome = spec.rpartition("=")
            W, R = mk.settle(mk.canonical(market), outcome)
            legs.append(type("Leg", (), {"W": W.ravel(), "R": R.ravel()}))
        p = joint_prob(legs, fp, "fair")
        pc = joint_prob(legs, fp, "conservative")
        indep = 1.0
        for leg in legs:
            indep *= float(fp.fair @ (leg.W >= 1 - 1e-9))
        print(f"{fx.match}: {' + '.join(a.legs)}")
        print(f"  공정 확률 {p:.2%} (독립 가정이면 {indep:.2%}, 상관 배수 {p / indep:.2f}) -> 공정 배당 {1 / p:.2f}")
        if a.odds:
            print(f"  bet365 {a.odds:.2f}: EV {p * a.odds - 1:+.1%}, 보정 엣지 {pc * a.odds - 1:+.1%}")
    elif a.cmd == "clv":
        rows = tracking.clv_report()
        for r in rows[-20:]:
            clv = "-" if r["clv"] is None else f"{r['clv']:+.2%}"
            print(f"  {r['ts'][:16]}  @{r['odds']:6.2f}  엣지 {r['edge']:+.2%}  CLV {clv:>7}  {r['picks']}")
        print(tracking.summarize_clv(rows))
    elif a.cmd == "fetch-history":
        for p in history.download(a.league, a.seasons, a.out):
            print("저장:", p)
    elif a.cmd == "ratings":
        from .model import DixonColes

        m = DixonColes().fit(history.load(a.csv or history.DEFAULT_RESULTS))
        print(f"홈 이점 {m.home_adv_:+.3f}  rho {m.rho_:+.3f}\n")
        print(m.ratings().round(3).to_string(index=False))

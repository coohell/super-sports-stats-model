"""Streamlit 대시보드: 오늘의 최강 조합 포트폴리오, +엣지 선택지, 같은 경기 조합 계산기, 백테스트."""
import sys
from pathlib import Path

import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sssm import backtest, history, markets as mk, pipeline  # noqa: E402
from sssm.config import ROOT, env  # noqa: E402
from sssm.portfolio import BET365_ACCA_BOOST_EXAMPLE, PortfolioConfig, joint_prob  # noqa: E402
from sssm.pricing import PricingConfig, ValueFilter  # noqa: E402

st.set_page_config(page_title="Super Sports Stats Model", page_icon="🎯", layout="wide")
st.title("🎯 bet365 최강 조합")
st.caption("Pinnacle 가격으로 만든 스코어 확률 격자로 bet365 의 모든 선택지를 가격 매기고, "
           "단식과 멀티를 한꺼번에 놓고 자금 성장률이 가장 큰 배팅 묶음을 고릅니다.")

with st.sidebar:
    st.header("설정")
    source = st.radio("데이터", ["예시 배당", "API-Football (실시간)"], help="실시간은 API_FOOTBALL_KEY 가 필요합니다.")
    bankroll = st.number_input("자본 (원)", 100_000, 1_000_000_000, 1_000_000, 100_000)
    shrink = st.slider("shrink (샤프 가격 차이를 믿는 비율)", 0.0, 1.0, PricingConfig.shrink, 0.05,
                       help="과거 EPL·챔피언십에서 0.74~0.76. `python -m sssm calibrate` 로 다시 잴 수 있습니다.")
    min_edge = st.slider("최소 보정 엣지", 0.0, 0.05, ValueFilter.min_edge, 0.0025, format="%.4f")
    kelly_frac = st.select_slider("켈리 분수", [0.1, 0.25, 0.5, 1.0], value=PortfolioConfig.kelly_fraction)
    max_legs = st.slider("멀티 최대 폴 수", 1, 5, PortfolioConfig.max_legs)
    max_total = st.slider("하루 총 배팅 상한 (자본 대비)", 0.01, 0.5, PortfolioConfig.max_total, 0.01)
    boost = st.checkbox("bet365 Acca Boost 예시 표 적용", help="2폴 5% ~ 14폴 70%. 지역·기간 조건을 먼저 확인하세요.")
    record = st.checkbox("배당 스냅샷·추천 기록 (CLV 추적)", help="data/snapshots, data/ledger.jsonl 에 쌓습니다.")

settings = pipeline.Settings(
    pricing=PricingConfig(shrink=shrink), value=ValueFilter(min_edge=min_edge),
    portfolio=PortfolioConfig(kelly_fraction=kelly_frac, max_legs=max_legs, max_total=max_total,
                              acca_bonus=dict(BET365_ACCA_BOOST_EXAMPLE) if boost else {}),
    bankroll=float(bankroll), record=record,
)

st.session_state.setdefault("live", None)
if source == "예시 배당":
    rep = pipeline.run_file(settings=settings)
else:
    if not env("API_FOOTBALL_KEY"):
        st.error("API_FOOTBALL_KEY 가 설정되지 않았습니다. `.env` 에 넣거나 예시 배당을 선택하세요.")
        st.stop()
    c1, c2, c3 = st.columns(3)
    league = c1.number_input("리그 id (39=EPL, 40=챔피언십)", value=39)
    season = c2.number_input("시즌", value=2025)
    days = c3.number_input("며칠 앞까지", 1, 7, 3)
    if st.button("배당 불러오기"):
        try:
            st.session_state.live = pipeline.run_apifootball(int(league), int(season), int(days), settings)
        except Exception as e:  # 네트워크/쿼터 오류를 화면에 그대로 보여준다
            st.error(f"불러오기 실패: {e}")
    if st.session_state.live is None:
        st.stop()
    live = st.session_state.live
    rep = pipeline.analyze(live.fixtures, None, live.source, settings, live.notes)

for n in rep.notes:
    st.info(n)

pf = rep.portfolio
tab1, tab2, tab3, tab4 = st.tabs(["🏆 최강 조합", "+엣지 선택지", "같은 경기 조합 계산기", "백테스트"])

with tab1:
    if not pf.bets:
        st.warning("오늘은 걸 만한 배팅이 없습니다. bet365 가 샤프 공정 가격보다 후한 곳이 없거나, 보정 후 엣지가 문턱보다 작습니다.")
    else:
        a, b, c, d = st.columns(4)
        a.metric("총 배팅", f"{bankroll * pf.total_stake:,.0f}원", f"자본의 {pf.total_stake:.2%}")
        b.metric("기대 수익 (보수적)", f"{bankroll * pf.exp_return:+,.0f}원")
        c.metric("손실 날 확률", f"{pf.p_loss:.0%}")
        d.metric("하위 5% 결과", f"{bankroll * pf.q05:+,.0f}원")
        for i, bet in enumerate(pf.bets, 1):
            with st.container(border=True):
                x, y, z, w = st.columns(4)
                x.metric(f"#{i} {bet.kind}", f"{bet.odds:.2f}배", f"부스트 {bet.bonus:.0%}" if bet.bonus else None)
                y.metric("적중 확률", f"{bet.win_prob:.1%}")
                z.metric("EV / 보정 엣지", f"{bet.ev:+.1%}", f"{bet.edge:+.2%}")
                w.metric("금액", f"{bankroll * bet.stake:,.0f}원", f"자본의 {bet.stake:.2%}")
                for s in bet.legs:
                    st.write(f"• **{s.match}** — {s.label} @ {s.odds:.2f} (공정 {s.fair_odds:.2f}, {s.source})")
    st.caption("단식과 멀티(서로 다른 경기)를 후보로 놓고 기대 로그 자산을 최대화하는 비율을 한 번에 풉니다. "
               "같은 경기 선택지의 상관은 스코어 격자에서 함께 반영됩니다. 금액은 보정 엣지 기준 분수 켈리입니다.")

with tab2:
    rows = []
    for s in rep.value:
        mv = rep.moves.get((s.fixture_id, s.market, s.outcome))
        rows.append({"경기": s.match, "킥오프": s.kickoff[:16], "선택": s.label, "bet365": s.odds,
                     "공정 배당": round(s.fair_odds, 3), "공정 확률": s.fair_prob * 100, "EV": s.ev * 100,
                     "보정 엣지": s.edge * 100, "근거": s.source,
                     "샤프 움직임": None if not mv else mv["fair_move"] * 100,
                     "bet365 지연": bool(mv and mv["stale"])})
    if rows:
        st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch", column_config={
            "공정 확률": st.column_config.NumberColumn(format="%.1f%%"),
            "EV": st.column_config.NumberColumn(format="%+.1f%%"),
            "보정 엣지": st.column_config.NumberColumn(format="%+.2f%%"),
            "샤프 움직임": st.column_config.NumberColumn(format="%+.1f%%p"),
        })
    else:
        st.write("+엣지 선택지가 없습니다.")
    st.caption("근거 sharp: Pinnacle 이 같은 마켓을 냄. derived: Pinnacle 이 내지 않은 마켓을 스코어 격자로 끌어냄 "
               "(모형 오차 때문에 엣지를 1%p 더 요구).")

with tab3:
    if not rep.pricings:
        st.write("가격을 매긴 경기가 없습니다.")
    else:
        fx_by = {fp.fixture.match: fp for fp in rep.pricings.values() if fp.states == "grid"}
        name = st.selectbox("경기", list(fx_by))
        fp = fx_by[name]
        choices = {mk.label(m, o): (m, o) for m in ("1X2", "OU:1.5", "OU:2.5", "OU:3.5", "BTTS", "AH:-1.5", "AH:-0.5",
                                                    "AH:0.5", "DC") for o in mk.outcomes(m)}
        picked = st.multiselect("선택 (Bet Builder)", list(choices), default=["홈승", "오버 2.5"])
        offered = st.number_input("bet365 Bet Builder 배당", 1.01, 1000.0, 3.0, 0.05)
        if picked:
            legs = []
            for lbl in picked:
                W, R = mk.settle(*choices[lbl])
                legs.append(type("Leg", (), {"W": W.ravel(), "R": R.ravel()}))
            p = joint_prob(legs, fp)
            indep = 1.0
            for leg in legs:
                indep *= float(fp.fair @ (leg.W >= 1 - 1e-9))
            a, b, c = st.columns(3)
            a.metric("공정 확률", f"{p:.2%}", f"독립 가정 {indep:.2%}")
            b.metric("공정 배당", f"{1 / p:.2f}" if p > 0 else "-")
            c.metric("EV", f"{p * offered - 1:+.1%}")
            st.caption("bet365 Bet Builder 는 상관을 반영해 배당을 줄입니다. 공정 배당보다 높을 때만 가치가 있습니다.")

with tab4:
    files = sorted((ROOT / "data" / "history").glob("*.csv"))
    if not files:
        st.write("`data/history/` 에 football-data 형식 배당 CSV 가 없습니다. `python -m sssm fetch-history` 로 받으세요.")
    else:
        st.write(f"배당 CSV {len(files)}개. 날짜 순서대로 그날 이전 정보만으로 포트폴리오를 짜고 결과로 정산합니다.")
        start = st.date_input("검증 시작일", pd.Timestamp("2021-08-01"))
        phase = st.radio("시점", ["open", "close"], horizontal=True,
                         help="open: 시가로 걸고 Pinnacle 마감으로 CLV. close: 마감 직전 가격으로 건다.")
        if st.button("백테스트 실행"):
            with st.spinner("실행 중…"):
                res = backtest.run(history.load(files), str(start), phase,
                                   PricingConfig(shrink=shrink),
                                   [backtest.Strategy("단식 켈리", PortfolioConfig(max_legs=1, kelly_fraction=kelly_frac)),
                                    backtest.Strategy("최강 조합", settings.portfolio, settings.value)])
            st.code(res.to_text())
            for r in res.results:
                if not r.days.empty:
                    st.line_chart(r.days.set_index("date")["bankroll"], height=180)
                    st.caption(r.name)

st.divider()
st.caption("⚠️ 분석 연구용 도구입니다. 자동 배팅 기능은 없고 수익을 보장하지 않습니다. "
           "bet365 는 이기는 계정의 한도를 줄일 수 있습니다. 감당 가능한 금액으로만 이용하세요.")

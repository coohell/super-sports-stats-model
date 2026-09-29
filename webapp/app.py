"""Streamlit 대시보드: 사이드바에서 기준을 바꾸면 +EV 선택지와 최강 조합이 다시 계산된다."""
import sys
from pathlib import Path

import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sssm import backtest, history, pipeline  # noqa: E402
from sssm.config import env  # noqa: E402
from sssm.pricing import PricingConfig, ValueFilter  # noqa: E402

st.set_page_config(page_title="Super Sports Stats Model", page_icon="🎯", layout="wide")
st.title("🎯 bet365 +EV 조합 탐색기")
st.caption("Pinnacle 공정 배당 + Dixon-Coles 팀 전력 모델로 bet365 배당의 기대값을 계산합니다.")


@st.cache_data(show_spinner="모델 학습 중…")
def load_model_and_results():
    df = history.load()
    return df, pipeline.fit_model(df)


with st.sidebar:
    st.header("설정")
    source = st.radio("데이터", ["예시 배당", "API-Football (실시간)"], help="실시간은 API_FOOTBALL_KEY 가 필요합니다.")
    sharp_w = st.slider("Pinnacle 가중치", 0.0, 1.0, 0.8, 0.1, help="1이면 Pinnacle 만, 0이면 모델만 믿습니다.")
    min_ev = st.slider("최소 EV", 0.0, 0.15, 0.02, 0.005, format="%.3f")
    max_legs = st.slider("최대 조합 폴 수", 1, 4, 3)
    kelly_frac = st.select_slider("켈리 분수", [0.1, 0.25, 0.5, 1.0], value=0.25)
    bankroll = st.number_input("자본 (원)", 100_000, 1_000_000_000, 1_000_000, 100_000)

st.session_state.setdefault("live", None)
settings = pipeline.Settings(
    pricing=PricingConfig(sharp_weight=sharp_w), value=ValueFilter(min_ev=min_ev),
    max_legs=max_legs, kelly_fraction=kelly_frac,
)
_, model = load_model_and_results()

if source == "예시 배당":
    rep = pipeline.run_file(settings=settings)
else:
    if not env("API_FOOTBALL_KEY"):
        st.error("API_FOOTBALL_KEY 가 설정되지 않았습니다. `.env` 에 넣거나 예시 배당을 선택하세요.")
        st.stop()
    c1, c2 = st.columns(2)
    league = c1.number_input("리그 id (39=EPL)", value=39)
    season = c2.number_input("시즌", value=2025)
    if st.button("배당 불러오기"):
        try:
            st.session_state.live = pipeline.run_apifootball(int(league), int(season), 3, settings)
        except Exception as e:  # 네트워크/쿼터 오류를 화면에 그대로 보여준다
            st.error(f"불러오기 실패: {e}")
    if st.session_state.live is None:
        st.stop()
    live = st.session_state.live
    rep = pipeline.analyze(live.fixtures, model, live.source, settings, live.notes)

for n in rep.notes:
    st.info(n)

tab1, tab2, tab3, tab4 = st.tabs(["🏆 최강 조합", "단식 +EV", "팀 전력", "백테스트"])

with tab1:
    if not rep.parlays:
        st.warning("조건을 만족하는 +EV 조합이 없습니다. 최소 EV 를 낮춰 보세요.")
    for i, p in enumerate(rep.parlays[:8], 1):
        with st.container(border=True):
            a, b, c, d = st.columns(4)
            a.metric(f"#{i} 조합 배당", f"{p.odds:.2f}x", f"{len(p.legs)}폴")
            b.metric("적중 확률", f"{p.prob:.1%}")
            c.metric("기대값 (EV)", f"{p.ev:+.1%}")
            d.metric("권장 배팅", f"{bankroll * p.stake:,.0f}원", f"자본의 {p.stake:.2%}")
            for s in p.legs:
                st.write(f"• **{s.match}** — {s.label} @ {s.odds:.2f} (공정 {s.fair_prob:.1%}, EV {s.ev:+.1%})")
    st.caption("정렬 기준은 기대 로그 성장률입니다. 조합 EV 는 폴이 늘수록 커 보이지만 적중 확률이 곱으로 줄기 때문에 성장률로 비교합니다. 경기 결과는 서로 독립이라고 가정합니다.")

with tab2:
    rows = [{"경기": s.match, "킥오프": s.kickoff[:16], "선택": s.label, "bet365": s.odds,
             "공정확률": s.fair_prob, "Pinnacle": s.sharp_prob, "모델": s.model_prob, "EV": s.ev, "근거": s.source}
            for s in rep.value]
    if rows:
        st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch", column_config={
            "공정확률": st.column_config.NumberColumn(format="%.1f%%"),
            "EV": st.column_config.NumberColumn(format="%+.1f%%"),
        })
    else:
        st.write("+EV 선택지가 없습니다.")

with tab3:
    if model:
        st.write(f"홈 이점 {model.home_adv_:+.3f} · ρ {model.rho_:+.3f} (공격력↑ 좋음, 수비력↓ 좋음, strength = 공격 − 수비)")
        st.dataframe(model.ratings().round(3), hide_index=True, width="stretch")

with tab4:
    st.write("매주 그 주 이전 경기만으로 다시 학습해 예측합니다 (미래 정보 누수 없음).")
    start = st.date_input("검증 시작일", pd.Timestamp("2022-08-01"))
    if st.button("백테스트 실행"):
        with st.spinner("실행 중… (수 초)"):
            st.code(backtest.run(history.load(), str(start), sharp_weight=sharp_w, min_ev=min_ev).to_text())
    st.caption("ROI 와 CLV 는 배당이 들어 있는 CSV(football-data.co.uk)가 있을 때만 계산됩니다. README 참고.")

st.divider()
st.caption("⚠️ 이 도구는 분석 연구용입니다. 자동 배팅 기능은 없으며 어떤 수익도 보장하지 않습니다. 소액으로, 감당 가능한 범위에서만 이용하세요.")

import streamlit as st
from pathlib import Path

st.set_page_config(page_title="보고서", page_icon="📄", layout="centered")

st.title("📄 분석 보고서")

report_path = Path(__file__).parent.parent.parent / "reports" / "SSSM_Report_2026-07-22.pdf"

if report_path.exists():
    st.success("✅ 보고서가 준비되었습니다!")
    
    with open(report_path, "rb") as f:
        st.download_button(
            label="📥 PDF 보고서 다운로드",
            data=f,
            file_name="SSSM_Bet365_Report_2026-07-22.pdf",
            mime="application/pdf",
            use_container_width=True
        )
    
    st.divider()
    
    st.subheader("📊 보고서 요약")
    
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Bet365 스포츠 종목", "35+")
    with col2:
        st.metric("월평균 마켓", "80,000+")
    with col3:
        st.metric("Allegretto 월 비용", "$39")
    
    st.divider()
    
    st.markdown("""
    ### 🏆 Bet365 시장 분석
    
    | 항목 | 수치 |
    |------|------|
    | 총 스포츠 종목 | 35+ 개 |
    | 축구 한 경기 마켓 | 120~300+ 개 |
    | 실시간 동시 이벤트 | 500~2,000+ 개 |
    | 모델 처리 가능 (이론) | 무제한 |
    
    ### 💰 Kimi Allegretto ROI 분석
    
    | 항목 | 수치 |
    |------|------|
    | 월 비용 | $39 |
    | 처리 가능 경기/월 | 300~500개 |
    | 1년 수익 확률 (+3% 엣지) | ~58% |
    | 시간당 환산 임금 | $0.1~$0.5 |
    
    **결론**: Allegretto는 학습용으로 적합. 수익 목적이라면 API only 전환 권장.
    """)
    
else:
    st.error("⚠️ 보고서 파일을 찾을 수 없습니다.")
    st.info("`scripts/generate_pdf.py`를 실행하여 보고서를 생성해주세요.")

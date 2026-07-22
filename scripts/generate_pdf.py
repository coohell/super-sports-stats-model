#!/usr/bin/env python3
"""보고서 2개를 하나의 PDF로 생성"""
import os
from fpdf import FPDF

class ReportPDF(FPDF):
    def header(self):
        self.set_font('NotoSans', '', 8)
        self.set_text_color(100, 100, 100)
        self.cell(0, 8, 'Super Sports Stats Model v1.0', align='R')
        self.ln(4)
    
    def footer(self):
        self.set_y(-12)
        self.set_font('NotoSans', '', 8)
        self.set_text_color(100, 100, 100)
        self.cell(0, 8, f'Page {self.page_no()}', align='C')

pdf = ReportPDF()
pdf.set_margins(10, 10, 10)
pdf.set_auto_page_break(auto=True, margin=15)

pdf.add_font('NotoSans', '', '/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc', uni=True)
pdf.add_font('NotoSans', 'B', '/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc', uni=True)

# 보고서 1: Bet365 시장 분석
pdf.add_page()
pdf.set_font('NotoSans', 'B', 18)
pdf.cell(0, 12, 'Bet365 시장 분석 보고서', new_x='LMARGIN', new_y='NEXT')
pdf.set_font('NotoSans', '', 10)
pdf.cell(0, 8, '작성일: 2026-07-22  |  Super Sports Stats Model', new_x='LMARGIN', new_y='NEXT')
pdf.ln(4)

sections1 = [
    ("1. Executive Summary", """
Bet365는 세계에서 가장 깊은 베팅 시장을 제공합니다.
- 총 스포츠 종목: 35+ 개
- 월평균 라이브+프리매치 마켓: 45,000 ~ 80,000+ 개
- 축구 단일 경기 평균 마켓: 120 ~ 300+ 개
- 모델 처리 가능 시장 (이론적): 제한 없음

핵심 결론: 수익성 있는 모델 운영은 극소수에게만 가능합니다.
"""),
    ("2. 스포츠 종목", """
인기 스포츠 (8개): 축구, 농구, 야구, 아이스하키, 테니스, 배구, 미식축구, 크리켓
라켓/네트 (4개): 배드민턴, 탁구, 스쿼시, 핸드볼
격투/개인 (6개): 복싱, UFC/MMA, 프로레슬링, 유도, 태권도, 펜싱
모터스포츠 (5개): F1, NASCAR, 모터사이클, 랠리, 스피드웨이
e스포츠 (4+개): LoL, CS2, Dota2, Valorant
이색 (8+개): 가상스포츠, 정치, 오락, 노벨상 등
"""),
    ("3. 모델별 수용 가능 시장", """
Poisson 기반: 1,000+ 시장 (난이도: 낮음)
Elo Rating: 5,000+ 시장 (난이도: 낮음)
XGBoost/LightGBM: 500+ 시장 (난이도: 높음)
Monte Carlo: 200+ 시장 (난이도: 중간)
Kelly Criterion: 무제한 (수학적)
Arbitrage: 50~200 시장 (실시간 의존)
Neural Network: 100+ (난이도: 매우 높음)
"""),
    ("4. 예상 수익 (현실 체크)", """
1년 시뮬레이션 (초기 자본 1,000만원, +3% 엣지 가정):
- 1년 후 자본 (평균): 1,430만원
- 하위 10%: 890만원 (손실)
- 상위 10%: 2,210만원
- 수익 확률: 58%

엣지가 있어도 단기 수익 확률은 60% 미만이며 상당한 변동성을 수반합니다.
"""),
    ("5. 결론", """
Bet365 시장 규모: 매우 큼 (80,000+ 마켓)
모델 적용 가능성: 기술적으로 가능
수익 가능성: 존재하나 확률 낮음 (60% 미만 / 1년)
장기 기대 수익: +1% ~ +5% (엣지 있을 경우)
실제 성공률: 5% 미만 (프로페셔널 제외)

권고: 데이터 수집 및 백테스팅 프레임워크 먼저 구축, 1,000+ 경기 이상 검증 필수.
""")
]

for title, body in sections1:
    pdf.set_font('NotoSans', 'B', 13)
    pdf.cell(0, 10, title, new_x='LMARGIN', new_y='NEXT')
    pdf.set_font('NotoSans', '', 9)
    for line in body.strip().split('\n'):
        pdf.multi_cell(180, 5, line)
    pdf.ln(2)

# 보고서 2: Allegretto 요금제 분석
pdf.add_page()
pdf.set_font('NotoSans', 'B', 18)
pdf.cell(0, 12, 'Bet365 x Kimi Allegretto 요금제 분석 보고서', new_x='LMARGIN', new_y='NEXT')
pdf.set_font('NotoSans', '', 10)
pdf.cell(0, 8, '작성일: 2026-07-22  |  Super Sports Stats Model', new_x='LMARGIN', new_y='NEXT')
pdf.ln(4)

sections2 = [
    ("1. Executive Summary", """
Allegretto 월 비용: $39 (연간 시 $31/월)
월 처리 가능 경기: 300~500개 (Agent Credits 150개 기준)
Bet365 전체 대비: 3~8% 커버 가능
월 예상 순이익: -$39 ~ +$111
시간당 환산 임금: $0.1 ~ $0.5/시간

결론: Allegretto로 Bet365 분석은 기술적으로 되나, 돈 벌기에는 안 됨.
"""),
    ("2. Allegretto 리소스", """
Agent Credits: 150개/월 (1회 분석 = 1~3 credits)
Kimi Code: 5x credits
Agent Swarm: 50 runs, 4 concurrent subtasks
Kimi Claw: 브라우저 자동화 포함

보수적 시나리오: 50경기/월
표준: 75경기/월
Swarm 최적화: 200경기/월
Kimi Code 자동화: 300~500경기/월
"""),
    ("3. 손익분기점 분석", """
월 운영비: $39
손익분기점: $39 / 배팅액 비율

총 배팅액 $5,000일 때: 필요 ROI = 0.78%
총 배팅액 $1,000일 때: 필요 ROI = 3.9%

소액 배팅 시 요금제 비용 회수 어려움.
"""),
    ("4. 최적 운영 전략", """
1. 캐싱: 동일 팀 데이터 재사용 -> credits 절약 30~50%
2. 배치 처리: Swarm concurrent 4개 활용
3. 자동화: Kimi Code로 스크립트화 -> 반복 작업 제로화
4. 선택적 LLM: 고밸류 경기만 LLM 분석

추천 집중 종목: 축구(1순위), 테니스(2순위), 농구(3순위)
"""),
    ("5. 대안 제안 (더 나은 ROI)", """
Phase 1 (1~2개월): Adagio(무료)로 프레임워크 개발
Phase 2 (3~4개월): Allegretto($39)로 자동화 + 캐싱 구축
Phase 3 (5~6개월): API only(K2.6, $0.95/1M tokens)로 전환
    -> 이 때부터 수익 가능성 생김

결론: Allegretto는 학습용으로는 괜찮음. $39면 데이터 분석 스킬 배우는 비용으로는 합리적.
하지만 이걸로 돈 벌겠다는 생각은 버려야 함.
""")
]

for title, body in sections2:
    pdf.set_font('NotoSans', 'B', 13)
    pdf.cell(0, 10, title, new_x='LMARGIN', new_y='NEXT')
    pdf.set_font('NotoSans', '', 9)
    for line in body.strip().split('\n'):
        pdf.multi_cell(180, 5, line)
    pdf.ln(2)

# 저장
out_path = '/root/.openclaw/workspace/super-sports-stats-model/reports/SSSM_Report_2026-07-22.pdf'
pdf.output(out_path)
print(f'PDF created: {out_path}')
print(f'Size: {os.path.getsize(out_path)} bytes')

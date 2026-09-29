# Super Sports Stats Model

bet365 에서 걸 수 있는 마켓 중 **기대값(EV)이 가장 높은 단식·조합**을 찾는 도구입니다.

지원 마켓: 승무패(1X2), 무승부 없는 승패(H2H), 양팀 득점(BTTS), 총득점 오버/언더(모든 x.5 라인), 아시안 핸디캡(x.5 라인, TheOddsAPI 소스). 정수·쿼터 라인은 푸시/반환이 생겨 확률 계산이 달라지므로 제외합니다.

## 어떻게 찾나

```
경기·배당 수집 ─┬─ bet365 배당 (걸 가격)
 (API-Football)  └─ Pinnacle 배당 → 마진 제거 → 샤프 공정 확률
과거 결과 ────────→ Dixon-Coles 팀 전력 모델 → 모델 확률
                        │
 공정 확률 = 0.8 × 샤프 + 0.2 × 모델
                        │
 bet365 배당 × 공정 확률 − 1 ≥ 문턱  →  +EV 선택지
                        │
 조합(서로 다른 경기) 전부 계산 → 켈리 로그 성장률 순 정렬 → 최강 조합
```

- **샤프 공정 확률**: Pinnacle 은 마진이 낮고 정확한 배당으로 알려져 있습니다. 마진은 롱샷 편향을 반영하는 power 방식으로 제거합니다(`sssm/odds.py`).
- **팀 전력 모델**: Dixon-Coles(공격/수비/홈 이점/저득점 보정, 최근 경기 가중)입니다(`sssm/model/`). Pinnacle 배당이 없는 경기는 모델만으로 평가하되 EV 10% 이상을 요구합니다.
- **최강 조합**: 조합 EV 는 폴이 늘수록 커 보이지만 적중 확률이 곱으로 줄어듭니다. 그래서 EV 가 아니라 **기대 로그 성장률**(켈리 기준)로 단식과 조합을 같은 잣대로 비교합니다. 같은 경기에서 두 폴을 고르지 않고, 경기끼리 독립을 가정합니다(`sssm/parlay.py`).

## 빠른 시작

```bash
pip install -r requirements-dev.txt
python -m pytest -q

python -m sssm picks                     # 내장 예시 배당으로 전체 파이프라인 체험
python -m sssm backtest --start 2022-08-01
python -m sssm ratings
streamlit run webapp/app.py              # 대시보드
```

`picks --source demo` 의 배당은 모델에서 만든 **예시**이며 실제 가격이 아닙니다.

### 실제 배당으로 돌리기

```bash
cp .env.example .env        # API_FOOTBALL_KEY 입력
python -m sssm picks --source apifootball --league 39 --season 2025 --days 3
```

API-Football 은 bet365 와 Pinnacle 배당을 모두 주고 BTTS 도 있습니다(무료 100회/일). 북메이커 id 는 이름으로 조회해서 씁니다. 아시안 핸디캡은 라인 표기 규칙을 실서버로 확인하지 못해 이 소스에서는 제외했습니다.

TheOddsAPI 의 bet365 는 **호주 지역 `bet365_au` 유료 플랜, AFL/NRL 만** 지원하므로 축구 bet365 에는 쓸 수 없습니다. 팀 전력 모델 없이 Pinnacle 대비 가격만 비교합니다.

```bash
python -m sssm picks --source theodds --sport aussierules_afl --markets h2h,spreads,totals
```

**bet365 가 Pinnacle 보다 얼마나 유리한지만 보고 싶다면** `--sharp-weight 1` 을 주세요. 모델을 섞지 않고 Pinnacle 마진 제거 확률만 씁니다.

## 검증 결과 (내장 EPL 2015-25, walk-forward)

매주 그 주 이전 경기만으로 다시 학습해 2022-08 이후 1,137경기를 예측했습니다(로그 손실, 낮을수록 좋음). 자세한 표(하이퍼파라미터, 보정)는 [reports/dixon_coles_backtest.md](reports/dixon_coles_backtest.md).

| 마켓 | 모델 | 빈도 기준선 |
|---|---|---|
| 1X2 | **0.9720** | 1.0621 |
| 오버/언더 2.5 | 0.6761 | 0.6862 |
| BTTS | 0.6929 | 0.6920 |

- 승무패는 기준선보다 확실히 낫고(정확도 54.0%, 홈승 확률 보정도 양호), 오버/언더는 미미하게, BTTS 는 기준선과 같습니다. 그래서 이 마켓들의 가격은 **Pinnacle 에 크게 의존**합니다.
- **아직 증명되지 않은 것**: bet365 에 실제로 걸었을 때 수익이 나는지(ROI)와 Pinnacle 마감 배당 대비 CLV. 이 개발 환경에서는 과거 배당 다운로드가 막혀 있어 계산하지 못했습니다. 아래 방법으로 직접 확인할 수 있습니다.

### 배당 백테스트 (ROI / CLV)

[football-data.co.uk](https://www.football-data.co.uk/englandm.php) 시즌 CSV 를 받아 넣으면 됩니다. `B365*`, `PS*`(Pinnacle), `PSC*`(Pinnacle 마감) 컬럼을 자동으로 읽습니다. 이 사이트가 막힌 네트워크(사내 프록시 등)라면 로컬 PC 에서 실행하세요.

```bash
python -m sssm fetch-history --league E0 --seasons 2122 2223 2324 2425   # data/history/ 에 저장
python -m sssm backtest --csv data/history/E0_*.csv --start 2023-08-01
```

결과에는 전략별(샤프+모델 / 샤프만 / 모델만) 배팅 수, 적중률, ROI, 평균 CLV 와 로그 손실이 가장 낮은 `sharp_weight` 가 나옵니다. **CLV 가 양수이고 ROI 가 수백 건 이상에서 양수일 때만** 이 전략을 믿으세요.

## 구조

```
sssm/
  odds.py       마진 제거(proportional/power/shin), EV, 켈리
  model/        Dixon-Coles 팀 전력 모델
  pricing.py    공정 확률 블렌딩 + 가치 선택지 필터
  parlay.py     조합 생성, 켈리 로그 성장률 정렬
  backtest.py   walk-forward 백테스트, ROI/CLV
  markets.py    마켓 키(1X2, H2H, BTTS, OU:라인, AH:라인)와 Fixture/Selection
  history.py    과거 결과·배당 CSV 로더, football-data.co.uk 다운로더
  sources/      API-Football, TheOddsAPI 어댑터
  pipeline.py   전체 연결
  cli.py        python -m sssm ...
webapp/app.py   Streamlit 대시보드
data/           EPL 2015-25 결과, 예시 경기·배당
tests/          pytest (배당 수학, 모델, 마켓, 조합, 어댑터, 백테스트)
reports/        백테스트 보고서
docs/           이전 조사 보고서
```

## 주의

분석 연구용입니다. 자동 배팅 기능은 없고 수익을 보장하지 않습니다. 배당에 마진이 있으므로 대부분의 선택지는 −EV 이며, 모델 확률의 오차가 EV 보다 클 수 있습니다. 감당 가능한 소액으로만 이용하세요.

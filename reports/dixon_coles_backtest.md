# Dixon-Coles 백테스트 (프리미어리그)

- 데이터: 2015/16~2024/25 경기 결과 (`data/history/pl_*.csv`, 배당 없음)
- 방법: 2022-08-01부터 7일 단위 walk-forward (각 시점 이전 경기만으로 재학습, 시간 감쇠 xi=0.0019 ≈ 반감기 1년)
- 재현: `python -m src.model.backtest` (약 9분), 경기별 예측은 `reports/backtest_results.csv`

| 지표 | 모델 | 기준선(학습기간 홈/무/원정 빈도) |
|---|---|---|
| 경기 수 | 1,137 (승격팀 등 미학습 팀 경기 제외) | |
| 1X2 log-loss | 0.977 | 1.062 |
| Brier | 0.579 | |
| 정확도 | 54.6% | |

## 한계
- 마감 배당이 없어 시장 대비 log-loss / EV(ROI) 평가는 아직 못 했다. 이 환경에서는 football-data.co.uk 접속이 막혀 있다.
  배당 CSV(`B365CH/CD/CA`)를 `data/history/`에 넣고 `--data "data/history/E0_*.csv"`로 다시 돌리면 `vs_market`이 자동 계산한다.
- 정규화 없는 MLE라 강팀 vs 약팀에서 확률이 과신 쪽으로 치우친다 (예: Man City vs Sheffield Utd 홈승 95%). 시장과 비교 전에 shrinkage 또는 xi 튜닝 필요.
- `data/__init__.py`의 하드코딩 전력값은 아직 이 모델로 교체하지 않았다.

# 과거 경기 데이터

`src/model/backtest.py` 가 읽는 시즌별 CSV 폴더.

- `pl_*.csv` — 프리미어리그 2015/16~2024/25 **결과만** (datasets/football-datasets, 배당 없음)
- 마감 배당 백테스트를 하려면 [football-data.co.uk](https://www.football-data.co.uk/data.php) 시즌 CSV
  (`B365CH/B365CD/B365CA` = bet365 마감 배당, 없으면 `B365H/D/A`, `PSC*` = Pinnacle 마감)를
  이 폴더에 넣거나 `python scripts/fetch_history.py` 로 받는다. 두 형식이 섞이면 배당 컬럼이 있는 파일만 배당 평가에 쓰이니
  배당 백테스트 때는 `--data "data/history/E0_*.csv"` 로 파일을 지정할 것.

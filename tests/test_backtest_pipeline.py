import json

import numpy as np
import pandas as pd

from sssm import backtest, history, pipeline
from sssm.cli import main


def test_walk_forward_on_bundled_results():
    df = history.load()
    rep = backtest.run(df[df["date"] < "2023-06-01"], start="2022-08-01")
    assert rep.n_matches > 300
    # 팀 전력 모델은 단순 빈도 기준선보다 승무패를 잘 맞혀야 한다
    assert rep.log_loss["1X2"]["model"] < rep.log_loss["1X2"]["baseline"]


def test_betting_simulation_with_odds(synthetic_league, tmp_path):
    rng = np.random.RandomState(1)
    df = synthetic_league.copy()
    n = len(df)
    for pre, margin in (("B365", 1.06), ("B365C", 1.05), ("PS", 1.02), ("PSC", 1.02)):
        p = rng.dirichlet([4, 2.5, 3], n)
        df[f"{pre}H"], df[f"{pre}D"], df[f"{pre}A"] = (1 / (p * margin)).T
    path = tmp_path / "odds.csv"
    df.rename(columns={"date": "Date", "home": "HomeTeam", "away": "AwayTeam", "hg": "FTHG", "ag": "FTAG"}).to_csv(path, index=False)
    loaded = history.load(path)
    assert history.has_odds(loaded)
    rep = backtest.run(loaded, start="2023-08-01", min_ev=0.0, min_train=100)
    assert {b["strategy"] for b in rep.betting} == {"sharp+model", "pinnacle only", "model only"}
    assert rep.best_sharp_weight is not None
    assert {"model", "bet365", "bet365_close", "pinnacle", "pinnacle_close"} <= set(rep.market_loss["1X2"])
    assert rep.parlays and all(p["bets"] > 0 for p in rep.parlays)
    assert rep.by_season
    b = rep.betting[0]
    assert b["roi_lo"] <= b["roi"] <= b["roi_hi"] and b["clv"] is not None and b["clv_b365"] is not None
    assert "ROI" in rep.to_text() and "조합" in rep.to_text()


def test_from_mirror_maps_to_football_data_columns():
    results = pd.DataFrame({"match_id": ["a", "b"], "season_code": [2324, 2324], "date": ["2023-08-11", "2023-08-12"],
                            "home_team": ["Burnley", "Arsenal"], "away_team": ["Man City", "Nott'm Forest"],
                            "fthg": [0, 2], "ftag": [3, 1]})
    odds = pd.DataFrame({"match_id": ["a", "b"], "bet365_1x2_home": [8.0, 1.2], "bet365_1x2_home_close": [9.0, 1.18],
                         "pinnacle_over25_close": [1.6, 1.7], "ladbrokes_1x2_home": [8.5, 1.2]})
    out = history.from_mirror(results, odds)
    assert list(out.columns) == ["Season", "Date", "HomeTeam", "AwayTeam", "FTHG", "FTAG", "B365H", "B365CH", "PC>2.5"]
    assert out["Season"].tolist() == ["2324", "2324"]
    assert out.loc[0, "B365CH"] == 9.0


def test_demo_pipeline_and_cli(tmp_path, capsys):
    rep = pipeline.run_file()
    assert {"1X2", "OU:2.5", "BTTS"} <= {s.market for s in rep.selections}  # 예시 파일의 마켓 키가 지원 목록과 맞아야 한다
    assert rep.value and rep.parlays
    assert all(s.ev >= 0.02 for s in rep.value)
    out = tmp_path / "r.json"
    main(["picks", "--source", "demo", "--out", str(out)])
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["parlays"] and data["notes"]
    assert "최강 조합" in capsys.readouterr().out


def test_download_history_writes_files_and_hides_nothing_on_error(tmp_path):
    class Resp:
        def __init__(self, status, content=b""):
            self.status_code, self.content, self.text = status, content, content.decode()

    class Sess:
        def __init__(self):
            self.urls = []

        def get(self, url, timeout=None):
            self.urls.append(url)
            return Resp(200, b"Date,HomeTeam\n") if "2425" in url else Resp(404, b"not found")

    s = Sess()
    paths = history.download("E0", ["2425"], tmp_path, s)
    assert s.urls == ["https://www.football-data.co.uk/mmz4281/2425/E0.csv"]
    assert paths == [tmp_path / "E0_2425.csv"] and paths[0].read_bytes().startswith(b"Date")
    import pytest

    with pytest.raises(RuntimeError, match="404"):
        history.download("E0", ["9999"], tmp_path, s)


def test_download_mirror_writes_football_data_format(tmp_path):
    files = {
        "results.csv": "match_id,season,season_code,date,home_team,away_team,fthg,ftag\n"
                       "a,2023-24,2324,2023-08-11,Burnley,Man City,0,3\n",
        "results_with_odds.csv": "match_id,bet365_1x2_home,bet365_1x2_draw,bet365_1x2_away,pinnacle_1x2_home\n"
                                 "a,8.0,5.0,1.4,8.5\n",
    }

    class Resp:
        def __init__(self, text):
            self.status_code, self.text, self.content = 200, text, text.encode()

    class Sess:
        def get(self, url, timeout=None):
            return Resp(files[url.rsplit("/", 1)[1]])

    paths = history.download_mirror(["2324"], tmp_path, Sess())
    assert paths == [tmp_path / "E0_2324.csv"]
    df = history.load(paths)
    assert df.loc[0, "home"] == "Burnley" and df.loc[0, "B365A"] == 1.4
    import pytest

    with pytest.raises(ValueError, match="2425"):
        history.download_mirror(["2425"], tmp_path, Sess())

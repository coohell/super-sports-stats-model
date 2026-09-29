import json

import numpy as np

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
    for pre, margin in (("B365", 1.06), ("PS", 1.02), ("PSC", 1.02)):
        p = rng.dirichlet([4, 2.5, 3], n)
        df[f"{pre}H"], df[f"{pre}D"], df[f"{pre}A"] = (1 / (p * margin)).T
    path = tmp_path / "odds.csv"
    df.rename(columns={"date": "Date", "home": "HomeTeam", "away": "AwayTeam", "hg": "FTHG", "ag": "FTAG"}).to_csv(path, index=False)
    loaded = history.load(path)
    assert history.has_odds(loaded)
    rep = backtest.run(loaded, start="2023-08-01", min_ev=0.0, min_train=100)
    assert {b["strategy"] for b in rep.betting} == {"sharp+model", "pinnacle only", "model only"}
    assert rep.best_sharp_weight is not None
    assert "ROI" in rep.to_text()


def test_demo_pipeline_and_cli(tmp_path, capsys):
    rep = pipeline.run_file()
    assert rep.value and rep.parlays
    assert all(s.ev >= 0.02 for s in rep.value)
    out = tmp_path / "r.json"
    main(["picks", "--source", "demo", "--out", str(out)])
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["parlays"] and data["notes"]
    assert "최강 조합" in capsys.readouterr().out

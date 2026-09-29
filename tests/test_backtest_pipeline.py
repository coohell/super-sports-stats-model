import json

import numpy as np
import pandas as pd
import pytest

from sssm import backtest, history, pipeline, tracking
from sssm.calibrate import shrink_from_history
from sssm.cli import main
from sssm.markets import Fixture
from sssm.pricing import PricingConfig


def synthetic_odds(n=500, generous=0.2, seed=3):
    """진짜 확률을 알고 있는 가상 시장. Pinnacle 은 정확, bet365 는 가끔 한 결과를 후하게 준다."""
    rng = np.random.RandomState(seed)
    rows, day = [], pd.Timestamp("2021-08-01")
    for i in range(n):
        lam, mu = rng.uniform(0.8, 2.0), rng.uniform(0.6, 1.6)
        hg, ag = rng.poisson(lam), rng.poisson(mu)
        from sssm import grid

        g = grid.dc_grid(lam, mu)
        p = np.array([grid.prob(g, "1X2", o) for o in ("home", "draw", "away")])
        b365 = 1 / (p * 1.06)
        if rng.rand() < generous:
            k = rng.randint(3)
            b365[k] = 1 / (p[k] * 0.92)
        r = {"Date": day.strftime("%Y-%m-%d"), "HomeTeam": f"H{i % 20}", "AwayTeam": f"A{(i * 7) % 20}", "FTHG": hg, "FTAG": ag}
        for pre, odds in (("B365", b365), ("PS", 1 / (p * 1.02)), ("PSC", 1 / (p * 1.02))):
            r[f"{pre}H"], r[f"{pre}D"], r[f"{pre}A"] = odds
        rows.append(r)
        if i % 5 == 4:
            day += pd.Timedelta(days=3)
    return pd.DataFrame(rows)


@pytest.fixture(scope="module")
def odds_csv(tmp_path_factory):
    path = tmp_path_factory.mktemp("h") / "E0_test.csv"
    synthetic_odds().to_csv(path, index=False)
    return path


def test_row_to_fixture_reads_open_and_close(odds_csv):
    df = history.load(odds_csv)
    assert history.has_odds(df)
    fx = history.row_to_fixture(df.iloc[0], {"bet365": "bet365", "pinnacle_close": "pinnacle"})
    assert set(fx.odds) == {"bet365", "pinnacle"}
    assert fx.odds["pinnacle"]["1X2"]["home"] == pytest.approx(df.iloc[0]["PSCH"])


def test_shrink_is_one_when_sharp_open_equals_close(odds_csv):
    est = shrink_from_history(history.load(odds_csv))
    assert est.shrink == pytest.approx(1.0, abs=1e-6)
    assert est.clv == pytest.approx(est.pred_ev, abs=1e-9)


def test_market_backtest_finds_the_planted_edge(odds_csv):
    df = history.load(odds_csv)
    res = backtest.run(df, start="2021-11-01", pricing=PricingConfig(shrink=0.8))
    table = res.table().set_index("strategy")
    assert set(table.index) == {s.name for s in backtest.default_strategies()}
    for name, row in table.iterrows():
        assert row["bets"] > 20, name
        assert row["clv"] > 0.03  # 후하게 준 가격만 골랐다
        assert row["roi_lo"] <= row["roi"] <= row["roi_hi"]
    assert res.shrink_used and res.shrink_used[0][1] == pytest.approx(1.0)  # 그 시점 이전 데이터로만 보정
    # 진짜 엣지가 +8% 여도 수십 건으로는 ROI 구간이 0 을 넓게 포함한다. 그래서 CLV 로 판단한다
    kelly = table.loc["단식 켈리"]
    assert kelly["roi_hi"] - kelly["roi_lo"] > 0.2
    assert kelly["pred_edge"] < kelly["clv"]  # shrink 0.8 은 진짜 엣지를 덜 믿는다
    assert "95% 구간" in res.to_text()


def test_backtest_uses_no_future_data(odds_csv):
    df = history.load(odds_csv)
    a = backtest.run(df[df["date"] < "2022-01-01"], start="2021-11-01", calibrate=False)
    b = backtest.run(df, start="2021-11-01", calibrate=False)
    ba = a.results[1].bets
    bb = b.results[1].bets
    bb = bb[bb["date"] < "2022-01-01"]
    assert len(ba) == len(bb) and np.allclose(ba["stake"], bb["stake"])


def test_demo_pipeline_and_cli(tmp_path, capsys):
    rep = pipeline.run_file()
    assert rep.value and rep.portfolio.bets
    assert all(s.edge >= 0.005 for s in rep.value)
    assert "오늘의 최강 조합" in rep.to_markdown()
    out = tmp_path / "r.json"
    main(["picks", "--source", "demo", "--out", str(out), "--bankroll", "500000"])
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["portfolio"]["bets"] and data["notes"]
    assert data["portfolio"]["bets"][0]["amount"] > 0
    assert (tmp_path / "r.md").exists()
    assert "최강 조합" in capsys.readouterr().out


def test_cli_backtest_and_sgp(odds_csv, capsys):
    main(["backtest", "--csv", str(odds_csv), "--start", "2021-11-01", "--max-legs", "2"])
    assert "최강 조합" in capsys.readouterr().out
    main(["sgp", "--fixture", "demo-1", "--legs", "1X2=home", "OU:2.5=over", "--odds", "3.0"])
    out = capsys.readouterr().out
    assert "상관 배수" in out and "EV" in out


def test_model_eval_on_bundled_results():
    from sssm.model.evaluate import evaluate

    df = history.load()
    rep = evaluate(df[df["date"] < "2023-06-01"], start="2022-08-01")
    assert rep.n_matches > 300
    assert rep.log_loss["1X2"]["model"] < rep.log_loss["1X2"]["baseline"]


def test_snapshots_detect_stale_bet365_and_ledger_clv(tmp_path):
    snaps, ledger = tmp_path / "snaps", tmp_path / "ledger.jsonl"
    b365 = {"home": 2.2, "draw": 3.4, "away": 3.4}
    old = Fixture("f1", "2026-10-01T15:00:00+00:00", "EPL", "H", "A",
                  {"bet365": {"1X2": b365}, "pinnacle": {"1X2": {"home": 2.3, "draw": 3.6, "away": 3.3}}})
    tracking.record_snapshot([old], snaps, ts="2026-10-01T09:00:00+00:00")
    new = Fixture("f1", old.kickoff, "EPL", "H", "A",
                  {"bet365": {"1X2": b365}, "pinnacle": {"1X2": {"home": 2.0, "draw": 4.0, "away": 4.0}}})
    moves = tracking.movements([new], tracking.load_snapshots(snaps))
    assert moves[("f1", "1X2", "home")]["stale"]  # 샤프는 홈 쪽으로 움직였는데 bet365 그대로
    assert not moves[("f1", "1X2", "away")]["stale"]

    rep = pipeline.analyze([new], None, "test", pipeline.Settings(pricing=PricingConfig(shrink=1.0)))
    tracking.log_bets(rep.portfolio.bets, 1_000_000, ledger, ts="2026-10-01T10:00:00+00:00")
    tracking.record_snapshot([new], snaps, ts="2026-10-01T14:55:00+00:00")
    rows = tracking.clv_report(ledger, snaps)
    assert rows and rows[0]["clv"] == pytest.approx(0.10, abs=1e-3)  # 2.2 x 0.5 - 1
    assert "CLV 계산 1/1건" in tracking.summarize_clv(rows)

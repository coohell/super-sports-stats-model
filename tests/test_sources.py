from sssm.sources.apifootball import parse_bets
from sssm.sources.theoddsapi import parse_event


def test_parse_apifootball_odds():
    item = {"fixture": {"id": 1}, "bookmakers": [{"id": 8, "name": "Bet365", "bets": [
        {"id": 1, "name": "Match Winner", "values": [
            {"value": "Home", "odd": "2.10"}, {"value": "Draw", "odd": "3.40"}, {"value": "Away", "odd": "3.60"}]},
        {"id": 5, "name": "Goals Over/Under", "values": [
            {"value": "Over 1.5", "odd": "1.30"}, {"value": "Over 2.5", "odd": "1.90"}, {"value": "Under 2.5", "odd": "1.95"}]},
        {"id": 8, "name": "Both Teams Score", "values": [{"value": "Yes", "odd": "1.80"}, {"value": "No", "odd": "2.00"}]},
    ]}]}
    out = parse_bets(item)
    assert out["1X2"] == {"home": 2.10, "draw": 3.40, "away": 3.60}
    assert out["OU2.5"] == {"over": 1.90, "under": 1.95}
    assert out["BTTS"] == {"yes": 1.80, "no": 2.00}


def test_parse_theodds_event():
    e = {"id": "x", "commence_time": "2026-10-01T09:00:00Z", "sport_title": "AFL", "home_team": "A", "away_team": "B",
         "bookmakers": [
             {"key": "bet365_au", "markets": [{"key": "h2h", "outcomes": [{"name": "A", "price": 1.8}, {"name": "B", "price": 2.05}]}]},
             {"key": "pinnacle", "markets": [{"key": "h2h", "outcomes": [{"name": "A", "price": 1.75}, {"name": "B", "price": 2.20}]}]},
             {"key": "sportsbet", "markets": []},
         ]}
    fx = parse_event(e)
    assert fx.market("bet365", "H2H") == {"home": 1.8, "away": 2.05}
    assert fx.market("pinnacle", "H2H") == {"home": 1.75, "away": 2.20}
    assert set(fx.odds) == {"bet365", "pinnacle"}

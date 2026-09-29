import logging

import pytest

from sssm.pricing import price_fixture, selections
from sssm.sources.apifootball import APIFootball, parse_bets
from sssm.sources.theoddsapi import TheOddsAPI, parse_event


class FakeResp:
    def __init__(self, payload, status=200, headers=None):
        self._payload, self.status_code = payload, status
        self.headers, self.text = headers or {}, str(payload)

    def json(self):
        return self._payload


class FakeSession:
    """routes: [(url 조건 함수, params -> FakeResp)] 첫 일치 사용. 호출은 calls 에 기록."""

    def __init__(self, routes):
        self.routes, self.calls = routes, []

    def get(self, url, params=None, headers=None, timeout=None):
        self.calls.append((url, dict(params or {})))
        for match, handler in self.routes:
            if match(url):
                return handler(dict(params or {}))
        raise AssertionError(f"unexpected request: {url}")


# ---------------- API-Football ----------------

def test_parse_apifootball_odds_with_multiple_totals_lines():
    item = {"fixture": {"id": 1}, "bookmakers": [{"id": 8, "name": "Bet365", "bets": [
        {"id": 1, "name": "Match Winner", "values": [
            {"value": "Home", "odd": "2.10"}, {"value": "Draw", "odd": "3.40"}, {"value": "Away", "odd": "3.60"}]},
        {"id": 5, "name": "Goals Over/Under", "values": [
            {"value": "Over 1.5", "odd": "1.30"}, {"value": "Under 1.5", "odd": "3.40"},
            {"value": "Over 2.5", "odd": "1.90"}, {"value": "Under 2.5", "odd": "1.95"},
            {"value": "Over 2.75", "odd": "2.05"}, {"value": "Under 2.75", "odd": "1.80"},  # 쿼터 라인도 지원
            {"value": "Over 3.5", "odd": "3.10"}]},  # Under 가 없는 라인은 제외
        {"id": 8, "name": "Both Teams Score", "values": [{"value": "Yes", "odd": "1.80"}, {"value": "No", "odd": "2.00"}]},
    ]}]}
    out = parse_bets(item)
    assert out["1X2"] == {"home": 2.10, "draw": 3.40, "away": 3.60}
    assert out["OU:1.5"] == {"over": 1.30, "under": 3.40}
    assert out["OU:2.5"] == {"over": 1.90, "under": 1.95}
    assert out["BTTS"] == {"yes": 1.80, "no": 2.00}
    assert out["OU:2.75"] == {"over": 2.05, "under": 1.80}
    assert set(out) == {"1X2", "OU:1.5", "OU:2.5", "OU:2.75", "BTTS"}


def _af_item(fid, bid, name, home_odd):
    return {"fixture": {"id": fid, "date": "d"}, "bookmakers": [{"id": bid, "name": name, "bets": [
        {"id": 1, "name": "Match Winner", "values": [{"value": "Home", "odd": home_odd},
                                                    {"value": "Draw", "odd": "3.5"},
                                                    {"value": "Away", "odd": "3.5"}]}]}]}


def _af_fixture(fid, home, away, status="NS"):
    return {"fixture": {"id": fid, "date": "2026-10-03T14:00:00+00:00", "status": {"short": status}},
            "league": {"name": "Premier League"}, "teams": {"home": {"name": home}, "away": {"name": away}}}


def _af_session(bookmakers, odds_pages, fixtures):
    def odds(p):
        pages = odds_pages[p["bookmaker"]]
        return FakeResp({"response": pages[p.get("page", 1) - 1], "paging": {"current": p.get("page", 1), "total": len(pages)}})

    return FakeSession([
        (lambda u: u.endswith("/odds/bookmakers"), lambda p: bookmakers()),
        (lambda u: u.endswith("/odds"), odds),
        (lambda u: u.endswith("/fixtures"), lambda p: FakeResp({"response": fixtures, "paging": {"current": 1, "total": 1}})),
    ])


def test_apifootball_resolves_ids_by_name_pages_and_skips_played_fixtures():
    # 기본값(8/4)과 다른 id 를 줘서 이름 조회 결과가 쓰이는지 확인
    sess = _af_session(
        bookmakers=lambda: FakeResp({"response": [{"id": 88, "name": "Bet365"}, {"id": 44, "name": "Pinnacle"}]}),
        odds_pages={88: [[_af_item(1, 88, "Bet365", "2.1")], [_af_item(2, 88, "Bet365", "2.2")]],
                    44: [[_af_item(1, 44, "Pinnacle", "2.0"), _af_item(2, 44, "Pinnacle", "2.0")]]},
        fixtures=[_af_fixture(1, "A", "B"), _af_fixture(2, "C", "D"), _af_fixture(3, "E", "F", status="FT")],
    )
    fxs = APIFootball(key="K", session=sess).upcoming(39, 2026, "2026-10-01", "2026-10-05")
    odds_calls = [p for u, p in sess.calls if u.endswith("/odds")]
    assert {p["bookmaker"] for p in odds_calls} == {88, 44}
    assert [p.get("page", 1) for p in odds_calls if p["bookmaker"] == 88] == [1, 2]
    by_id = {f.fixture_id: f for f in fxs}
    assert set(by_id) == {"1", "2"}  # 이미 끝난 경기는 제외
    assert (by_id["1"].home, by_id["2"].away) == ("A", "D")
    assert by_id["1"].odds["bet365"]["1X2"]["home"] == 2.1
    assert by_id["2"].odds["pinnacle"]["1X2"]["home"] == 2.0


def test_apifootball_lookup_failure_falls_back_with_warning(caplog):
    sess = _af_session(bookmakers=lambda: FakeResp({"message": "boom"}, status=500), odds_pages={}, fixtures=[])
    with caplog.at_level(logging.WARNING):
        ids = APIFootball(key="K", session=sess).bookmaker_ids(["bet365", "pinnacle"])
    assert ids == {"bet365": 8, "pinnacle": 4}
    assert "기본값" in caplog.text


def test_apifootball_missing_bookmaker_after_successful_lookup_raises():
    sess = _af_session(bookmakers=lambda: FakeResp({"response": [{"id": 1, "name": "Other"}]}), odds_pages={}, fixtures=[])
    with pytest.raises(RuntimeError, match="bet365"):
        APIFootball(key="K", session=sess).bookmaker_ids(["bet365"])


def test_apifootball_errors_field_raises():
    sess = FakeSession([(lambda u: True, lambda p: FakeResp({"errors": {"requests": "limit reached"}, "response": []}))])
    with pytest.raises(RuntimeError, match="limit"):
        APIFootball(key="K", session=sess).results(39, 2025)


def test_apifootball_requires_key(monkeypatch):
    monkeypatch.delenv("API_FOOTBALL_KEY", raising=False)
    monkeypatch.setattr("sssm.sources.apifootball.env", lambda name, default="": "")
    with pytest.raises(RuntimeError, match="API_FOOTBALL_KEY"):
        APIFootball()


# ---------------- TheOddsAPI ----------------

def _event(bm_key, markets, eid="e1"):
    return {"id": eid, "home_team": "A", "away_team": "B", "commence_time": "t", "sport_title": "AFL",
            "bookmakers": [{"key": bm_key, "markets": markets}]}


def _merge(*events):
    out = events[0]
    for e in events[1:]:
        out["bookmakers"] += e["bookmakers"]
    return out


def test_parse_theodds_h2h_totals_and_book_mapping():
    e = _merge(
        _event("bet365_au", [
            {"key": "h2h", "outcomes": [{"name": "A", "price": 1.8}, {"name": "B", "price": 2.05}]},
            {"key": "totals", "outcomes": [{"name": "Over", "price": 2.0, "point": 2.5}, {"name": "Under", "price": 1.8, "point": 2.5}]}]),
        _event("pinnacle", [{"key": "h2h", "outcomes": [{"name": "A", "price": 1.75}, {"name": "B", "price": 2.20}]}]),
        _event("sportsbet", []),
    )
    fx = parse_event(e)
    assert fx.market("bet365", "H2H") == {"home": 1.8, "away": 2.05}
    assert fx.market("bet365", "OU:2.5") == {"over": 2.0, "under": 1.8}
    assert fx.market("pinnacle", "H2H") == {"home": 1.75, "away": 2.20}
    assert set(fx.odds) == {"bet365", "pinnacle"}


def test_parse_theodds_draw_makes_1x2():
    fx = parse_event(_event("pinnacle", [{"key": "h2h", "outcomes": [
        {"name": "A", "price": 2.0}, {"name": "B", "price": 3.5}, {"name": "Draw", "price": 3.4}]}]))
    assert fx.market("pinnacle", "1X2") == {"home": 2.0, "draw": 3.4, "away": 3.5}


def test_spread_line_is_normalised_to_home_and_lines_are_not_mixed():
    e = _merge(
        _event("pinnacle", [{"key": "spreads", "outcomes": [
            {"name": "A", "price": 1.9, "point": -1.5}, {"name": "B", "price": 1.9, "point": 1.5}]}]),
        _event("bet365_au", [{"key": "spreads", "outcomes": [
            {"name": "A", "price": 2.0, "point": -2.5}, {"name": "B", "price": 1.8, "point": 2.5}]}]),
    )
    fx = parse_event(e)
    assert fx.market("pinnacle", "AH:-1.5") == {"home": 1.9, "away": 1.9}
    assert fx.market("bet365", "AH:-2.5") == {"home": 2.0, "away": 1.8}
    # AFL 은 스코어 격자로 핸디캡을 가격 매길 수 없어 아무것도 내지 않는다
    assert price_fixture(fx) is None


def test_spread_with_inconsistent_away_line_is_dropped():
    fx = parse_event(_event("pinnacle", [{"key": "spreads", "outcomes": [
        {"name": "A", "price": 1.9, "point": -1.5}, {"name": "B", "price": 1.9, "point": 2.5}]}]))
    assert fx.odds["pinnacle"] == {}


def test_integer_and_quarter_lines_are_kept():
    # 정수(적특)와 쿼터(반승/반패) 라인도 정산 규칙대로 가격을 매길 수 있다
    fx = parse_event(_event("pinnacle", [{"key": "totals", "outcomes": [
        {"name": "Over", "price": 1.9, "point": 3.0}, {"name": "Under", "price": 1.9, "point": 3.0},
        {"name": "Over", "price": 1.9, "point": 2.75}, {"name": "Under", "price": 1.9, "point": 2.75}]}]))
    assert set(fx.odds["pinnacle"]) == {"OU:3", "OU:2.75"}


def test_edge_from_theodds_uses_devigged_pinnacle():
    e = _merge(
        _event("pinnacle", [{"key": "h2h", "outcomes": [{"name": "A", "price": 2.0}, {"name": "B", "price": 2.0}]}]),
        _event("bet365_au", [{"key": "h2h", "outcomes": [{"name": "A", "price": 2.2}, {"name": "B", "price": 1.8}]}]),
    )
    sels = {s.outcome: s for s in selections(price_fixture(parse_event(e)))}
    assert sels["home"].ev == pytest.approx(0.10)  # 2.2 * 0.5 - 1
    assert sels["away"].ev == pytest.approx(-0.10)
    assert 0 < sels["home"].edge < sels["home"].ev  # shrink 가 엣지를 줄인다


def _theodds_events():
    return [_event("pinnacle", [{"key": "h2h", "outcomes": [{"name": "A", "price": 2.0}, {"name": "B", "price": 2.0}]}])]


def test_theodds_default_markets_skip_btts_and_capture_quota():
    sess = FakeSession([(lambda u: u.endswith("/sports/aussierules_afl/odds"),
                         lambda p: FakeResp(_theodds_events(), headers={"x-requests-remaining": "497"}))])
    client = TheOddsAPI(key="K", session=sess)
    client.upcoming("aussierules_afl", "bet365_au,pinnacle")
    assert len(sess.calls) == 1
    _, params = sess.calls[0]
    assert params["bookmakers"] == "bet365_au,pinnacle"
    assert params["markets"] == "h2h,spreads,totals"
    assert client.remaining == "497"


def test_theodds_btts_uses_per_event_endpoint_and_merges_into_fixture():
    btts_event = _event("pinnacle", [{"key": "btts", "outcomes": [{"name": "Yes", "price": 1.8}, {"name": "No", "price": 2.0}]}])
    sess = FakeSession([
        (lambda u: "/events/" in u, lambda p: FakeResp(btts_event)),
        (lambda u: u.endswith("/odds"), lambda p: FakeResp(_theodds_events())),
    ])
    fxs = TheOddsAPI(key="K", session=sess).upcoming("soccer_epl", "pinnacle", ("h2h", "btts"))
    assert any(u.endswith("/sports/soccer_epl/events/e1/odds") for u, _ in sess.calls)
    assert next(p for u, p in sess.calls if "/events/" in u)["markets"] == "btts"
    assert len(fxs) == 1
    assert set(fxs[0].odds["pinnacle"]) == {"H2H", "BTTS"}  # 한 경기로 병합됨


def test_theodds_rejects_unknown_market():
    with pytest.raises(ValueError, match="corners"):
        TheOddsAPI(key="K", session=FakeSession([])).upcoming("soccer_epl", markets=("corners",))


def test_http_error_does_not_leak_api_key():
    sess = FakeSession([(lambda u: True, lambda p: FakeResp({"message": "invalid key"}, status=401))])
    with pytest.raises(RuntimeError) as exc:
        TheOddsAPI(key="SECRETKEY", session=sess).upcoming("soccer_epl")
    assert "SECRETKEY" not in str(exc.value)
    assert "401" in str(exc.value)


def test_apifootball_multi_league_looks_up_bookmakers_once(monkeypatch):
    sess = _af_session(
        bookmakers=lambda: FakeResp({"response": [{"id": 8, "name": "Bet365"}, {"id": 4, "name": "Pinnacle"}]}),
        odds_pages={8: [[_af_item(1, 8, "Bet365", "2.1")]], 4: [[_af_item(1, 4, "Pinnacle", "2.0")]]},
        fixtures=[_af_fixture(1, "A", "B")],
    )
    monkeypatch.setattr("sssm.sources.apifootball.APIFootball.__init__",
                        lambda self, key=None, session=None: (setattr(self, "key", "K"), setattr(self, "http", sess))[0])
    from sssm import pipeline

    rep = pipeline.run_apifootball([39, 140], 2026, 2)
    assert rep.source == "api-football:39,140/2026"
    assert sum(u.endswith("/odds/bookmakers") for u, _ in sess.calls) == 1
    assert {p["league"] for u, p in sess.calls if u.endswith("/fixtures")} == {39, 140}

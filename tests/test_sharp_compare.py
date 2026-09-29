import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src", "collectors"))

import sharp_compare  # noqa: E402
from sharp_compare import (ApiFootballClient, TheOddsClient, compare, devig,  # noqa: E402
                           parse_apifootball, parse_theodds)


def test_devig_sums_to_one_and_removes_margin():
    for method in ("power", "proportional"):
        p = devig([1.90, 1.90], method)
        assert abs(sum(p) - 1) < 1e-9
        assert abs(p[0] - 0.5) < 1e-9


def test_devig_power_shifts_margin_to_longshot():
    prop = devig([1.5, 3.0, 6.0], "proportional")
    power = devig([1.5, 3.0, 6.0], "power")
    assert power[0] > prop[0]      # favourite gets more
    assert power[2] < prop[2]      # longshot gets less


def _event(bm_key, markets):
    return {"id": "e1", "home_team": "A", "away_team": "B", "commence_time": "t",
            "bookmakers": [{"key": bm_key, "markets": markets}]}


def test_theodds_h2h_and_totals_edge():
    pin = _event("pinnacle", [
        {"key": "h2h", "outcomes": [{"name": "A", "price": 2.0}, {"name": "B", "price": 2.0}]},
        {"key": "totals", "outcomes": [{"name": "Over", "price": 1.9, "point": 2.5},
                                        {"name": "Under", "price": 1.9, "point": 2.5}]},
    ])
    b365 = _event("bet365_au", [
        {"key": "h2h", "outcomes": [{"name": "A", "price": 2.2}, {"name": "B", "price": 1.8}]},
        {"key": "totals", "outcomes": [{"name": "Over", "price": 2.0, "point": 2.5},
                                        {"name": "Under", "price": 1.8, "point": 2.5}]},
    ])
    edges = compare(parse_theodds([pin, b365]))
    by = {(e.market, e.selection): e for e in edges}
    assert round(by[("h2h", "home")].ev, 4) == 0.10      # 2.2 * 0.5 - 1
    assert round(by[("totals", "over")].ev, 4) == 0.0    # 2.0 * 0.5 - 1
    assert by[("totals", "over")].line == 2.5
    assert edges[0].ev >= edges[-1].ev


def test_line_mismatch_is_not_compared():
    pin = _event("pinnacle", [{"key": "totals", "outcomes": [
        {"name": "Over", "price": 1.9, "point": 2.5}, {"name": "Under", "price": 1.9, "point": 2.5}]}])
    b365 = _event("bet365_au", [{"key": "totals", "outcomes": [
        {"name": "Over", "price": 2.0, "point": 3.5}, {"name": "Under", "price": 1.8, "point": 3.5}]}])
    assert compare(parse_theodds([pin, b365])) == []


def test_spread_line_normalised_to_home():
    pin = _event("pinnacle", [{"key": "spreads", "outcomes": [
        {"name": "A", "price": 1.9, "point": -1.5}, {"name": "B", "price": 1.9, "point": 1.5}]}])
    b365 = _event("bet365_au", [{"key": "spreads", "outcomes": [
        {"name": "A", "price": 2.0, "point": -1.5}, {"name": "B", "price": 1.8, "point": 1.5}]}])
    edges = compare(parse_theodds([pin, b365]))
    assert {e.line for e in edges} == {-1.5}
    assert len(edges) == 2


def test_apifootball_btts_and_h2h():
    def resp(bid, name, h2h, btts):
        return {"fixture": {"id": 1, "date": "d"}, "home_team": "A", "away_team": "B",
                "bookmakers": [{"id": bid, "name": name, "bets": [
                    {"name": "Match Winner", "values": [
                        {"value": "Home", "odd": h2h[0]}, {"value": "Draw", "odd": h2h[1]},
                        {"value": "Away", "odd": h2h[2]}]},
                    {"name": "Both Teams Score", "values": [
                        {"value": "Yes", "odd": btts[0]}, {"value": "No", "odd": btts[1]}]}]}]}
    quotes = parse_apifootball([resp(4, "Pinnacle", ["2.0", "4.0", "4.0"], ["1.9", "1.9"]),
                                resp(8, "Bet365", ["2.1", "3.8", "3.9"], ["2.0", "1.8"])])
    edges = compare(quotes, method="proportional")
    by = {(e.market, e.selection): e for e in edges}
    assert round(by[("h2h", "home")].ev, 4) == 0.05
    assert round(by[("btts", "yes")].ev, 4) == 0.0


# ---------------------------------------------------------------------------
# 네트워크 계층 (가짜 세션으로 요청 파라미터/페이징/에러 처리를 검증)
# ---------------------------------------------------------------------------

class FakeResp:
    def __init__(self, payload, status=200, headers=None):
        self._payload, self.status_code = payload, status
        self.headers, self.text = headers or {}, str(payload)

    def json(self):
        return self._payload


class FakeSession:
    """routes: [(url 조건 함수, params -> FakeResp)] 첫 일치 사용. 호출은 calls 에 기록"""

    def __init__(self, routes):
        self.routes, self.calls = routes, []

    def get(self, url, params=None, headers=None, timeout=None):
        self.calls.append((url, dict(params or {})))
        for match, handler in self.routes:
            if match(url):
                return handler(dict(params or {}))
        raise AssertionError(f"unexpected request: {url}")


def _theodds_events():
    return [_event("pinnacle", [{"key": "h2h", "outcomes": [
                {"name": "A", "price": 2.0}, {"name": "B", "price": 2.0}]}]),
            ]


def test_theodds_default_markets_skip_btts_and_capture_quota():
    sess = FakeSession([(lambda u: u.endswith("/sports/aussierules_afl/odds"),
                         lambda p: FakeResp(_theodds_events(), headers={"x-requests-remaining": "497"}))])
    client = TheOddsClient(api_key="K", session=sess)
    client.fetch("aussierules_afl", "bet365_au,pinnacle")
    assert len(sess.calls) == 1
    _, params = sess.calls[0]
    assert params["bookmakers"] == "bet365_au,pinnacle"
    assert params["markets"] == "h2h,spreads,totals"
    assert client.remaining == "497"


def test_theodds_btts_uses_per_event_endpoint():
    sess = FakeSession([
        (lambda u: "/events/" in u, lambda p: FakeResp(_theodds_events()[0])),
        (lambda u: u.endswith("/odds"), lambda p: FakeResp(_theodds_events())),
    ])
    TheOddsClient(api_key="K", session=sess).fetch("soccer_epl", "pinnacle", ("h2h", "btts"))
    urls = [u for u, _ in sess.calls]
    assert any(u.endswith("/sports/soccer_epl/events/e1/odds") for u in urls)
    btts_call = next(p for u, p in sess.calls if "/events/" in u)
    assert btts_call["markets"] == "btts"


def test_http_error_does_not_leak_api_key():
    sess = FakeSession([(lambda u: True, lambda p: FakeResp({"message": "invalid key"}, status=401))])
    with pytest.raises(RuntimeError) as exc:
        TheOddsClient(api_key="SECRETKEY", session=sess).fetch("soccer_epl")
    assert "SECRETKEY" not in str(exc.value)
    assert "401" in str(exc.value)


def _af_session(bookmakers, odds_pages, fixtures):
    """odds_pages: {bookmaker_id: [page1_response_list, page2_response_list, ...]}"""
    def odds(p):
        pages = odds_pages[p["bookmaker"]]
        return FakeResp({"response": pages[p["page"] - 1],
                         "paging": {"current": p["page"], "total": len(pages)}})
    return FakeSession([
        (lambda u: u.endswith("/odds/bookmakers"), lambda p: bookmakers()),
        (lambda u: u.endswith("/odds"), odds),
        (lambda u: u.endswith("/fixtures"), lambda p: FakeResp({"response": fixtures})),
    ])


def _af_item(fid, bm_id, bm_name, home_odd):
    return {"fixture": {"id": fid, "date": "d"}, "bookmakers": [{"id": bm_id, "name": bm_name, "bets": [
        {"name": "Match Winner", "values": [{"value": "Home", "odd": home_odd},
                                            {"value": "Draw", "odd": "3.5"},
                                            {"value": "Away", "odd": "3.5"}]}]}]}


def test_apifootball_resolves_ids_by_name_pages_and_attaches_teams():
    # 기본값(8/4)과 다른 ID 를 줘서 이름 조회 결과가 쓰이는지 확인
    sess = _af_session(
        bookmakers=lambda: FakeResp({"response": [{"id": 88, "name": "Bet365"}, {"id": 44, "name": "Pinnacle"}]}),
        odds_pages={88: [[_af_item(1, 88, "Bet365", "2.1")], [_af_item(2, 88, "Bet365", "2.2")]],
                    44: [[_af_item(1, 44, "Pinnacle", "2.0"), _af_item(2, 44, "Pinnacle", "2.0")]]},
        fixtures=[{"fixture": {"id": 1}, "teams": {"home": {"name": "A"}, "away": {"name": "B"}}},
                  {"fixture": {"id": 2}, "teams": {"home": {"name": "C"}, "away": {"name": "D"}}}],
    )
    quotes = ApiFootballClient(api_key="K", session=sess).fetch(39, 2026)
    odds_calls = [p for u, p in sess.calls if u.endswith("/odds")]
    assert {p["bookmaker"] for p in odds_calls} == {88, 44}
    assert [p["page"] for p in odds_calls if p["bookmaker"] == 88] == [1, 2]
    fx = next(p for u, p in sess.calls if u.endswith("/fixtures"))
    assert fx["ids"] == "1-2"
    edges = compare(quotes, method="proportional")
    home = {e.event_id: e for e in edges if e.selection == "home"}
    assert home["1"].home_team == "A" and home["2"].away_team == "D"
    assert round(home["1"].ev, 4) == round(2.1 * (1 / 2.0) / (1 / 2.0 + 2 / 3.5) - 1, 4)


def test_apifootball_lookup_failure_falls_back_with_warning(capsys):
    sess = _af_session(bookmakers=lambda: FakeResp({"message": "boom"}, status=500),
                       odds_pages={}, fixtures=[])
    ids = ApiFootballClient(api_key="K", session=sess).bookmaker_ids(["bet365", "pinnacle"])
    assert ids == {"bet365": 8, "pinnacle": 4}
    assert "경고" in capsys.readouterr().err


def test_apifootball_missing_bookmaker_after_successful_lookup_raises():
    sess = _af_session(bookmakers=lambda: FakeResp({"response": [{"id": 1, "name": "Other"}]}),
                       odds_pages={}, fixtures=[])
    with pytest.raises(RuntimeError, match="bet365"):
        ApiFootballClient(api_key="K", session=sess).bookmaker_ids(["bet365"])


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _stub_theodds(monkeypatch):
    seen = {}

    class Stub:
        remaining = "1"

        def fetch(self, sport, bookmakers, markets):
            seen.update(sport=sport, bookmakers=bookmakers, markets=list(markets))
            return []

    monkeypatch.setattr(sharp_compare, "TheOddsClient", Stub)
    return seen


def test_cli_theodds_defaults_use_bet365_au_and_skip_btts(monkeypatch):
    seen = _stub_theodds(monkeypatch)
    sharp_compare.main(["--source", "theodds", "--sport", "rugbyleague_nrl"])
    assert seen["bookmakers"] == "bet365_au,pinnacle"
    assert seen["markets"] == ["h2h", "spreads", "totals"]


def test_cli_custom_target_and_explicit_btts(monkeypatch):
    seen = _stub_theodds(monkeypatch)
    sharp_compare.main(["--source", "theodds", "--target", "draftkings", "--markets", "btts"])
    assert seen["bookmakers"] == "draftkings,pinnacle"
    assert seen["markets"] == ["btts"]


def test_cli_rejects_unknown_market(monkeypatch):
    _stub_theodds(monkeypatch)
    with pytest.raises(SystemExit):
        sharp_compare.main(["--source", "theodds", "--markets", "corners"])

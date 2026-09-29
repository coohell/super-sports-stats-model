"""과거 경기 CSV 로더.

두 형식을 읽는다.
1. 이 저장소 형식: date, home, away, hg, ag
2. football-data.co.uk 형식: Date, HomeTeam, AwayTeam, FTHG, FTAG 와 배당 컬럼
   (B365H/D/A, B365CH/CD/CA, PSH/D/A, PSCH/D/A, B365>2.5, B365C>2.5, P>2.5, PC>2.5 ...)
   https://www.football-data.co.uk/englandm.php 에서 시즌별 CSV 를 받을 수 있다.

football-data.co.uk 가 막힌 환경에서는 `fetch_epl()` 이 같은 데이터를 정리해 둔
GitHub 미러(AnishKhetani/premier-league-data)에서 받아 football-data 형식으로 바꿔
저장한다. 원 데이터의 권리는 football-data.co.uk 에 있으므로 저장소에는 넣지 않는다
(data/history/ 는 .gitignore).
"""
from __future__ import annotations

from pathlib import Path
from typing import Iterable, List, Optional, Union

import pandas as pd

from .config import ROOT

DEFAULT_RESULTS = ROOT / "data" / "epl_results_2021_2025.csv"
HISTORY_DIR = ROOT / "data" / "history"
MIRROR = "https://raw.githubusercontent.com/AnishKhetani/premier-league-data/main/data/processed"

ODDS_COLUMNS = {
    "B365H": ("bet365", "1X2", "home"), "B365D": ("bet365", "1X2", "draw"), "B365A": ("bet365", "1X2", "away"),
    "B365CH": ("bet365_close", "1X2", "home"), "B365CD": ("bet365_close", "1X2", "draw"),
    "B365CA": ("bet365_close", "1X2", "away"),
    "PSH": ("pinnacle", "1X2", "home"), "PSD": ("pinnacle", "1X2", "draw"), "PSA": ("pinnacle", "1X2", "away"),
    "PSCH": ("pinnacle_close", "1X2", "home"), "PSCD": ("pinnacle_close", "1X2", "draw"),
    "PSCA": ("pinnacle_close", "1X2", "away"),
    "B365>2.5": ("bet365", "OU2.5", "over"), "B365<2.5": ("bet365", "OU2.5", "under"),
    "B365C>2.5": ("bet365_close", "OU2.5", "over"), "B365C<2.5": ("bet365_close", "OU2.5", "under"),
    "P>2.5": ("pinnacle", "OU2.5", "over"), "P<2.5": ("pinnacle", "OU2.5", "under"),
    "PC>2.5": ("pinnacle_close", "OU2.5", "over"), "PC<2.5": ("pinnacle_close", "OU2.5", "under"),
}


def _parse_dates(s: pd.Series) -> pd.Series:
    iso = pd.to_datetime(s, format="%Y-%m-%d", errors="coerce")
    if iso.notna().all():
        return iso
    return pd.to_datetime(s, dayfirst=True, errors="coerce")


def load(paths: Union[str, Path, Iterable[Union[str, Path]]] = DEFAULT_RESULTS) -> pd.DataFrame:
    """CSV 들을 읽어 date, home, away, hg, ag (+ 있으면 배당 컬럼) 로 합친다."""
    if isinstance(paths, (str, Path)):
        paths = [paths]
    frames = []
    for p in paths:
        df = pd.read_csv(p, encoding_errors="replace")
        df = df.rename(columns={"Date": "date", "HomeTeam": "home", "AwayTeam": "away", "FTHG": "hg", "FTAG": "ag"})
        df = df.dropna(subset=["home", "away"])
        df["date"] = _parse_dates(df["date"].astype(str))
        keep = ["date", "home", "away", "hg", "ag"] + [c for c in ODDS_COLUMNS if c in df.columns]
        frames.append(df[keep])
    out = pd.concat(frames, ignore_index=True).sort_values("date").reset_index(drop=True)
    return out


def has_odds(df: pd.DataFrame) -> bool:
    return {"B365H", "PSH"}.issubset(df.columns)


# 미러 컬럼 -> football-data 컬럼
_MIRROR_COLUMNS = {
    "bet365_1x2_home": "B365H", "bet365_1x2_draw": "B365D", "bet365_1x2_away": "B365A",
    "bet365_1x2_home_close": "B365CH", "bet365_1x2_draw_close": "B365CD", "bet365_1x2_away_close": "B365CA",
    "pinnacle_1x2_home": "PSH", "pinnacle_1x2_draw": "PSD", "pinnacle_1x2_away": "PSA",
    "pinnacle_1x2_home_close": "PSCH", "pinnacle_1x2_draw_close": "PSCD", "pinnacle_1x2_away_close": "PSCA",
    "bet365_over25": "B365>2.5", "bet365_under25": "B365<2.5",
    "bet365_over25_close": "B365C>2.5", "bet365_under25_close": "B365C<2.5",
    "pinnacle_over25": "P>2.5", "pinnacle_under25": "P<2.5",
    "pinnacle_over25_close": "PC>2.5", "pinnacle_under25_close": "PC<2.5",
}


def from_mirror(results: pd.DataFrame, odds: pd.DataFrame) -> pd.DataFrame:
    """미러의 results / results_with_odds 표를 football-data 형식 한 표로 합친다."""
    res = results.rename(columns={"home_team": "HomeTeam", "away_team": "AwayTeam", "fthg": "FTHG", "ftag": "FTAG",
                                  "date": "Date", "season_code": "Season"})
    res = res[["match_id", "Season", "Date", "HomeTeam", "AwayTeam", "FTHG", "FTAG"]]
    od = odds[["match_id"] + [c for c in _MIRROR_COLUMNS if c in odds.columns]].rename(columns=_MIRROR_COLUMNS)
    out = res.merge(od, on="match_id", how="left").drop(columns="match_id")
    out["Season"] = out["Season"].astype(str).str.zfill(4)
    return out


def fetch_epl(dest: Path = HISTORY_DIR, first_season: str = "1516", base_url: str = MIRROR,
              timeout: float = 60.0) -> List[Path]:
    """EPL 결과+배당을 받아 dest/E0_<시즌>.csv 로 저장하고 경로들을 돌려준다."""
    import io

    import requests

    def get(name: str) -> pd.DataFrame:
        r = requests.get(f"{base_url}/{name}", timeout=timeout)
        r.raise_for_status()
        return pd.read_csv(io.StringIO(r.text), low_memory=False)

    df = from_mirror(get("results.csv"), get("results_with_odds.csv"))
    # 시즌 코드 "9394" 처럼 두 자리 연도라 정렬용으로 네 자리 시작 연도를 만든다
    start_year = df["Season"].str[:2].astype(int).map(lambda y: 1900 + y if y >= 90 else 2000 + y)
    fy = int(first_season[:2])
    df = df[start_year >= (1900 + fy if fy >= 90 else 2000 + fy)]
    dest.mkdir(parents=True, exist_ok=True)
    paths = []
    for season, g in df.groupby("Season", sort=True):
        p = dest / f"E0_{season}.csv"
        g.drop(columns="Season").to_csv(p, index=False)
        paths.append(p)
    return paths


def history_files(dest: Path = HISTORY_DIR) -> List[Path]:
    return sorted(dest.glob("E0_*.csv"))

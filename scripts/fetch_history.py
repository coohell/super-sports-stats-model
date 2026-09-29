"""
football-data.co.uk 에서 리그별 시즌 CSV(경기 결과 + bet365/Pinnacle 배당)를 data/history/ 로 내려받는다.
사내 프록시 등에서 football-data.co.uk 가 막혀 있으면 로컬 PC에서 실행하거나 CSV를 직접 넣으면 된다.

  python scripts/fetch_history.py --league E0 --seasons 1516 1617 1718 1819 1920 2021 2122 2223 2324 2425
"""
import argparse
import os

import requests

BASE = "https://www.football-data.co.uk/mmz4281/{season}/{league}.csv"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--league", default="E0", help="E0=EPL, E1=Championship, SP1=라리가, D1=분데스, I1=세리에A, F1=리그1")
    ap.add_argument("--seasons", nargs="+", default=["2122", "2223", "2324", "2425"])
    ap.add_argument("--out", default="data/history")
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    for s in a.seasons:
        r = requests.get(BASE.format(season=s, league=a.league), timeout=30)
        r.raise_for_status()
        path = os.path.join(a.out, f"{a.league}_{s}.csv")
        with open(path, "wb") as f:
            f.write(r.content)
        print("saved", path, len(r.content), "bytes")


if __name__ == "__main__":
    main()

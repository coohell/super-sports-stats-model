"""팀 이름 통일. 데이터 소스마다 같은 팀을 다르게 부른다."""
from __future__ import annotations

# API-Football / TheOddsAPI 이름 -> football-data.co.uk 이름
ALIASES = {
    "Manchester City": "Man City",
    "Manchester United": "Man United",
    "Newcastle United": "Newcastle",
    "Nottingham Forest": "Nott'm Forest",
    "Tottenham Hotspur": "Tottenham",
    "Wolverhampton Wanderers": "Wolves",
    "West Ham United": "West Ham",
    "Brighton and Hove Albion": "Brighton",
    "Brighton & Hove Albion": "Brighton",
    "Leicester City": "Leicester",
    "Leeds United": "Leeds",
    "Ipswich Town": "Ipswich",
    "Luton Town": "Luton",
    "Sheffield Utd": "Sheffield United",
    "AFC Bournemouth": "Bournemouth",
}


def norm(name: str) -> str:
    return ALIASES.get(name, name)

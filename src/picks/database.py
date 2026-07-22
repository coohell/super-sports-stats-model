"""
슈퍼픽킹 데이터베이스 모델
경기, 픽, 결과, 승률 추적
"""
import sqlite3
import os
from datetime import datetime, timedelta
from dataclasses import dataclass
from typing import List, Optional
import json

DB_PATH = os.environ.get("DB_PATH", "/tmp/superpicks.db")

@dataclass
class MatchPick:
    id: Optional[int]
    date: str
    sport: str
    league: str
    match_time: str
    home_team: str
    away_team: str
    home_odds: float
    draw_odds: float
    away_odds: float
    pick_selection: str  # 홈승/무승부/원정승
    pick_odds: float
    confidence: str  # 매우높음/높음/보통/낮음
    reasoning: str
    kelly_fraction: float
    ev: float
    edge: float
    roster_analysis: str = ""  # 로스터 분석
    recent_form: str = ""  # 최근 형태
    environment: str = ""  # 환경 요인
    created_at: str = ""
    status: str = "pending"  # pending/live/settled/void
    result: str = ""  # win/loss/push
    actual_score: str = ""
    profit: float = 0.0
    settled_at: str = ""

class PickDatabase:
    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path
        self.init_db()
    
    def init_db(self):
        os.makedirs(os.path.dirname(self.db_path) or "/tmp", exist_ok=True)
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        
        # 경기/픽 테이블
        c.execute('''
            CREATE TABLE IF NOT EXISTS picks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT NOT NULL,
                sport TEXT NOT NULL,
                league TEXT,
                match_time TEXT,
                home_team TEXT NOT NULL,
                away_team TEXT NOT NULL,
                home_odds REAL,
                draw_odds REAL,
                away_odds REAL,
                pick_selection TEXT NOT NULL,
                pick_odds REAL,
                confidence TEXT,
                reasoning TEXT,
                kelly_fraction REAL,
                ev REAL,
                edge REAL,
                roster_analysis TEXT,
                recent_form TEXT,
                environment TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                status TEXT DEFAULT 'pending',
                result TEXT,
                actual_score TEXT,
                profit REAL DEFAULT 0,
                settled_at TEXT
            )
        ''')
        
        # 일일 3픽 조합 테이블
        c.execute('''
            CREATE TABLE IF NOT EXISTS daily_combos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT NOT NULL UNIQUE,
                sport TEXT NOT NULL,
                pick1_id INTEGER,
                pick2_id INTEGER,
                pick3_id INTEGER,
                combo_odds REAL,
                confidence TEXT,
                result TEXT,
                profit REAL DEFAULT 0,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                settled_at TEXT
            )
        ''')
        
        # 성과 통계 테이블
        c.execute('''
            CREATE TABLE IF NOT EXISTS stats (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT,
                sport TEXT,
                total_picks INTEGER DEFAULT 0,
                wins INTEGER DEFAULT 0,
                losses INTEGER DEFAULT 0,
                pushes INTEGER DEFAULT 0,
                win_rate REAL DEFAULT 0,
                avg_odds REAL DEFAULT 0,
                total_profit REAL DEFAULT 0,
                roi REAL DEFAULT 0,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        conn.commit()
        conn.close()
    
    def save_pick(self, pick: MatchPick) -> int:
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute('''
            INSERT INTO picks 
            (date, sport, league, match_time, home_team, away_team,
             home_odds, draw_odds, away_odds, pick_selection, pick_odds,
             confidence, reasoning, kelly_fraction, ev, edge,
             roster_analysis, recent_form, environment, created_at, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            pick.date, pick.sport, pick.league, pick.match_time,
            pick.home_team, pick.away_team, pick.home_odds, pick.draw_odds,
            pick.away_odds, pick.pick_selection, pick.pick_odds, pick.confidence,
            pick.reasoning, pick.kelly_fraction, pick.ev, pick.edge,
            pick.roster_analysis, pick.recent_form, pick.environment,
            datetime.now().isoformat(), pick.status
        ))
        pick_id = c.lastrowid
        conn.commit()
        conn.close()
        return pick_id
    
    def get_today_picks(self, sport: str = None) -> List[MatchPick]:
        today = datetime.now().strftime("%Y-%m-%d")
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        
        if sport:
            c.execute('SELECT * FROM picks WHERE date = ? AND sport = ? ORDER BY created_at DESC',
                     (today, sport))
        else:
            c.execute('SELECT * FROM picks WHERE date = ? ORDER BY created_at DESC', (today,))
        
        rows = c.fetchall()
        conn.close()
        return self._rows_to_picks(rows)
    
    def get_picks_by_date(self, date: str, sport: str = None) -> List[MatchPick]:
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        
        if sport:
            c.execute('SELECT * FROM picks WHERE date = ? AND sport = ? ORDER BY match_time', (date, sport))
        else:
            c.execute('SELECT * FROM picks WHERE date = ? ORDER BY match_time', (date,))
        
        rows = c.fetchall()
        conn.close()
        return self._rows_to_picks(rows)
    
    def update_result(self, pick_id: int, result: str, actual_score: str, profit: float):
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute('''
            UPDATE picks SET result = ?, actual_score = ?, profit = ?, 
            status = 'settled', settled_at = ? WHERE id = ?
        ''', (result, actual_score, profit, datetime.now().isoformat(), pick_id))
        conn.commit()
        conn.close()
    
    def save_daily_combo(self, date: str, sport: str, pick_ids: List[int], combo_odds: float, confidence: str):
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute('''
            INSERT OR REPLACE INTO daily_combos 
            (date, sport, pick1_id, pick2_id, pick3_id, combo_odds, confidence)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (date, sport, pick_ids[0], pick_ids[1], pick_ids[2], combo_odds, confidence))
        conn.commit()
        conn.close()
    
    def get_stats(self, days: int = 30) -> dict:
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        
        since = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
        
        c.execute('''
            SELECT 
                COUNT(*) as total,
                SUM(CASE WHEN result = 'win' THEN 1 ELSE 0 END) as wins,
                SUM(CASE WHEN result = 'loss' THEN 1 ELSE 0 END) as losses,
                SUM(CASE WHEN result = 'push' THEN 1 ELSE 0 END) as pushes,
                SUM(profit) as total_profit,
                AVG(pick_odds) as avg_odds
            FROM picks 
            WHERE date >= ? AND status = 'settled'
        ''', (since,))
        
        row = c.fetchone()
        conn.close()
        
        total = row[0] or 0
        wins = row[1] or 0
        losses = row[2] or 0
        pushes = row[3] or 0
        profit = row[4] or 0
        avg_odds = row[5] or 0
        
        win_rate = (wins / (wins + losses) * 100) if (wins + losses) > 0 else 0
        roi = (profit / total * 100) if total > 0 else 0
        
        return {
            'total': total,
            'wins': wins,
            'losses': losses,
            'pushes': pushes,
            'win_rate': win_rate,
            'avg_odds': avg_odds,
            'total_profit': profit,
            'roi': roi
        }
    
    def _rows_to_picks(self, rows) -> List[MatchPick]:
        picks = []
        for row in rows:
            picks.append(MatchPick(
                id=row[0], date=row[1], sport=row[2], league=row[3], match_time=row[4],
                home_team=row[5], away_team=row[6], home_odds=row[7], draw_odds=row[8],
                away_odds=row[9], pick_selection=row[10], pick_odds=row[11],
                confidence=row[12], reasoning=row[13], kelly_fraction=row[14],
                ev=row[15], edge=row[16], roster_analysis=row[17],
                recent_form=row[18], environment=row[19], created_at=row[20],
                status=row[21], result=row[22], actual_score=row[23],
                profit=row[24], settled_at=row[25]
            ))
        return picks

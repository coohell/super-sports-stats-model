"""
뉴스 스크래퍼 - 경기 관련 뉴스 기사 수집
"""
import requests
from bs4 import BeautifulSoup
from typing import List, Dict, Optional
import urllib.parse
from datetime import datetime
import re


class NewsScraper:
    """경기 관련 뉴스 기사를 수집하는 스크래퍼"""
    
    def __init__(self):
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.0'
        }
    
    def search_naver_sports(self, query: str, max_results: int = 10) -> List[Dict]:
        """네이버 스포츠 뉴스 검색"""
        articles = []
        
        try:
            encoded_query = urllib.parse.quote(query)
            url = f"https://search.naver.com/search.naver?where=news&query={encoded_query}&sm=tab_jum"
            
            resp = requests.get(url, headers=self.headers, timeout=10)
            resp.raise_for_status()
            
            soup = BeautifulSoup(resp.text, 'html.parser')
            news_items = soup.select('.news_wrap')[:max_results]
            
            for item in news_items:
                title_tag = item.select_one('.news_tit')
                if title_tag:
                    title = title_tag.get_text(strip=True)
                    link = title_tag.get('href', '')
                    summary = item.select_one('.dsc_wrap')
                    summary_text = summary.get_text(strip=True) if summary else ''
                    
                    articles.append({
                        'source': 'naver',
                        'title': title,
                        'url': link,
                        'summary': summary_text,
                        'collected_at': datetime.now().isoformat()
                    })
                    
        except Exception as e:
            print(f"[뉴스 수집 오류] {e}")
            
        return articles
    
    def search_google_news(self, query: str, max_results: int = 10) -> List[Dict]:
        """구글 뉴스 RSS 검색"""
        articles = []
        
        try:
            encoded_query = urllib.parse.quote(query)
            url = f"https://news.google.com/rss/search?q={encoded_query}&hl=en-US&gl=US&ceid=US:en"
            
            resp = requests.get(url, headers=self.headers, timeout=10)
            resp.raise_for_status()
            
            soup = BeautifulSoup(resp.content, 'xml')
            items = soup.find_all('item')[:max_results]
            
            for item in items:
                title = item.find('title')
                link = item.find('link')
                pub_date = item.find('pubDate')
                description = item.find('description')
                
                if title and link:
                    articles.append({
                        'source': 'google',
                        'title': title.get_text(strip=True),
                        'url': link.get_text(strip=True),
                        'summary': description.get_text(strip=True) if description else '',
                        'published': pub_date.get_text(strip=True) if pub_date else '',
                        'collected_at': datetime.now().isoformat()
                    })
                    
        except Exception as e:
            print(f"[구글 뉴스 오류] {e}")
            
        return articles
    
    def collect_match_news(self, home_team: str, away_team: str, 
                          league: Optional[str] = None,
                          max_per_source: int = 10) -> Dict[str, List[Dict]]:
        """
        양팀 관련 뉴스를 한국어/영어 모두 수집
        """
        queries = [
            f"{home_team} {away_team} 경기",
            f"{home_team} {away_team} preview",
            f"{home_team} {away_team} match",
        ]
        
        if league:
            queries.append(f"{league} {home_team} {away_team}")
        
        all_articles = {
            'korean': [],
            'english': []
        }
        
        for query in queries:
            # 네이버 (한국어)
            kr_articles = self.search_naver_sports(query, max_per_source)
            all_articles['korean'].extend(kr_articles)
            
            # 구글 (영어)
            en_articles = self.search_google_news(query, max_per_source)
            all_articles['english'].extend(en_articles)
        
        # 중복 제거
        seen = set()
        for lang in all_articles:
            unique = []
            for art in all_articles[lang]:
                key = art['title'][:50]
                if key not in seen:
                    seen.add(key)
                    unique.append(art)
            all_articles[lang] = unique[:max_per_source]
        
        return all_articles
    
    def extract_key_info(self, articles: List[Dict]) -> Dict:
        """
        기사들에서 핵심 정보 추출 (간단한 키워드 기반)
        """
        text = ' '.join([a.get('title', '') + ' ' + a.get('summary', '') for a in articles])
        
        # 부상 관련 키워드
        injury_keywords = ['부상', 'injury', 'injured', 'out', 'doubt', 'absence', '결장']
        injuries = [kw for kw in injury_keywords if kw.lower() in text.lower()]
        
        # 전술/라인업 키워드
        lineup_keywords = ['라인업', '선발', 'lineup', 'starting XI', 'formation', '전술']
        lineup_mentions = [kw for kw in lineup_keywords if kw.lower() in text.lower()]
        
        # 분위기/동기부여
        mood_keywords = ['승리', '패배', '무승부', 'win', 'loss', 'draw', 'must win', '결승']
        mood = [kw for kw in mood_keywords if kw.lower() in text.lower()]
        
        return {
            'injury_mentions': bool(injuries),
            'lineup_mentions': bool(lineup_mentions),
            'mood_keywords': mood,
            'total_articles': len(articles)
        }


if __name__ == '__main__':
    scraper = NewsScraper()
    result = scraper.collect_match_news("Korea", "Czech", max_per_source=5)
    print(f"한국어 기사: {len(result['korean'])}개")
    print(f"영어 기사: {len(result['english'])}개")

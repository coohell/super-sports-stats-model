#!/usr/bin/env python3
"""
Super Sports Stats - 텔레그램 봇
필살승부 로직 탑재

사용법:
    1. .env 파일에 TELEGRAM_BOT_TOKEN=your_token 추가
    2. python telegram_bot/bot.py

명령어:
    /start - 시작
    /analyze 홈팀 원정팀 홈배당 무배당 원정배당 - 경기 분석
    /killpick 홈팀 원정팀 홈배당 무배당 원정배당 - 필살승부 (최고 픽 1개)
    /strategies 홈팀 원정팀 홈배당 무배당 원정배당 - 3가지 전략
    /help - 도움말
"""
import os
import sys
import logging
import asyncio
from pathlib import Path

# 부모 디렉토리 추가 (logic.py 임포트용)
sys.path.insert(0, str(Path(__file__).parent))

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    filters
)

from logic import KillPickEngine

# 로깅
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# 엔진 초기화
engine = KillPickEngine()


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """시작 메시지"""
    welcome = """
🏆 *슈퍼 스포츠 통계 모델 봇*

AI 기반 스포츠 경기 분석 & 필살승부 시스템

📋 *명령어:*
`/analyze 홈팀 원정팀 홈배당 무배당 원정배당` - 경기 분석
`/killpick 홈팀 원정팀 홈배당 무배당 원정배당` - 필살승부 (최고 픽)
`/strategies 홈팀 원정팀 홈배당 무배당 원정배당` - 3가지 전략
`/help` - 상세 도움말

💡 *예시:*
`/killpick 한국 체코 2.10 3.30 3.60`
`/analyze 맨시티 아스날 1.85 3.50 4.20`

⚠️ 본 봇은 데이터 분석 목적입니다. 스포츠토토는 소액으로 재미삼아 이용하세요.
"""
    await update.message.reply_text(welcome, parse_mode='Markdown')


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """도움말"""
    help_text = """
📖 *명령어 상세 설명*

🔍 `/analyze 홈팀 원정팀 홈배당 무배당 원정배당`
   → Poisson 기반 확률 분석 + 배당률 비교

⚔️ `/killpick 홈팀 원정팀 홈배당 무배당 원정배당`
   → 가장 확실한 *한 개* 픽만 추천
   → Kelly Criterion 기반 자금 관리 포함

🎯 `/strategies 홈팀 원정팀 홈배당 무배당 원정배당`
   → 신중 / 적정 / 공격 3가지 전략 모두 출력

*배당률 입력법:*
- 소수점 사용 (예: 2.10, 3.30, 3.60)
- Bet365, 배트맨 등 공식 배당률 입력

*필살승부 로직:*
1. Monte Carlo 5000회 시뮬레이션
2. 모델 확률 vs 배당률 암시확률 비교
3. EV(기대수익률) 계산
4. Kelly Criterion 자금 배분
5. 가장 높은 EV를 가진 픽 1개 선정
"""
    await update.message.reply_text(help_text, parse_mode='Markdown')


def _parse_args(args: list) -> tuple:
    """인자 파싱"""
    if len(args) < 5:
        return None
    
    try:
        home_team = args[0]
        away_team = args[1]
        home_odds = float(args[2])
        draw_odds = float(args[3])
        away_odds = float(args[4])
        return (home_team, away_team, home_odds, draw_odds, away_odds)
    except (ValueError, IndexError):
        return None


async def analyze(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """경기 분석"""
    args = context.args
    parsed = _parse_args(args)
    
    if not parsed:
        await update.message.reply_text(
            "❌ 인자가 부족합니다.\n"
            "사용법: `/analyze 홈팀 원정팀 홈배당 무배당 원정배당`\n"
            "예시: `/analyze 한국 체코 2.10 3.30 3.60`",
            parse_mode='Markdown'
        )
        return
    
    home_team, away_team, home_odds, draw_odds, away_odds = parsed
    
    # 분석 실행
    pick = engine.find_kill_pick(home_team, away_team, home_odds, draw_odds, away_odds)
    
    # 추가 확률 계산
    from logic import KillPickEngine as LPE
    temp_engine = LPE()
    implied = temp_engine.calculate_implied_probs(home_odds, draw_odds, away_odds)
    
    text = f"""
📊 *경기 분석: {home_team} vs {away_team}*

📈 *배당률:*
홈승: `{home_odds}` | 무: `{draw_odds}` | 원정승: `{away_odds}`

🧮 *암시확률 (Vig 제거):*
홈: `{implied['home']*100:.1f}%` | 무: `{implied['draw']*100:.1f}%` | 원정: `{implied['away']*100:.1f}%`

🏆 *모델 예측 확률:*
홈: `{pick.model_prob*100:.1f}%` | 선택: *{pick.selection_kr}*

📉 *엣지 (Edge):* `{pick.edge*100:+.1f}%p`
💰 *기대수익률 (EV):* `{pick.expected_value*100:+.1f}%`
📊 *Kelly 비율:* `{pick.kelly_fraction:.2f}`

📝 *분석:*
{pick.reasoning}

⚠️ 본 분석은 통계 모델 기반이며, 실제 결과를 보장하지 않습니다.
"""
    await update.message.reply_text(text, parse_mode='Markdown')


async def killpick(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """필살승부 - 최고의 픽 하나"""
    args = context.args
    parsed = _parse_args(args)
    
    if not parsed:
        await update.message.reply_text(
            "❌ 인자가 부족합니다.\n"
            "사용법: `/killpick 홈팀 원정팀 홈배당 무배당 원정배당`\n"
            "예시: `/killpick 한국 체코 2.10 3.30 3.60`",
            parse_mode='Markdown'
        )
        return
    
    home_team, away_team, home_odds, draw_odds, away_odds = parsed
    
    pick = engine.find_kill_pick(home_team, away_team, home_odds, draw_odds, away_odds)
    
    # 신뢰도 이모지
    conf_emoji = "🔥" if "매우 높음" in pick.confidence else \
                 "✅" if "높음" in pick.confidence else \
                 "⚠️" if "보통" in pick.confidence else "❌"
    
    text = f"""
⚔️ *필살승부*

🏟️ *{home_team} vs {away_team}*

🎯 *추천 픽:* *{pick.selection_kr}* @ `{pick.odds}`

📊 *확률 비교:*
모델: `{pick.model_prob*100:.1f}%` vs 배당: `{pick.implied_prob*100:.1f}%`
엣지: `+{pick.edge*100:.1f}%p`

💰 *기대수익률:* `{pick.expected_value*100:+.1f}%`
📈 *Kelly 비율:* `{pick.kelly_fraction:.2f}`
🛡️ *신뢰도:* {conf_emoji} {pick.confidence}

📝 *근거:*
{pick.reasoning}

💡 *자금 관리:*
총 자본의 `{pick.kelly_fraction*100:.1f}%` 배팅 권장
(예: 100만원 자본 → `{pick.kelly_fraction*1000000:,.0f}`원)

⚠️ 이 픽은 통계적 우위를 기반으로 합니다. 
무조건적인 승리를 보장하지 않습니다.
"""
    await update.message.reply_text(text, parse_mode='Markdown')


async def strategies(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """3가지 전략 모두 출력"""
    args = context.args
    parsed = _parse_args(args)
    
    if not parsed:
        await update.message.reply_text(
            "❌ 인자가 부족합니다.\n"
            "사용법: `/strategies 홈팀 원정팀 홈배당 무배당 원정배당`\n"
            "예시: `/strategies 한국 체코 2.10 3.30 3.60`",
            parse_mode='Markdown'
        )
        return
    
    home_team, away_team, home_odds, draw_odds, away_odds = parsed
    
    results = engine.generate_all_strategies(
        home_team, away_team, home_odds, draw_odds, away_odds
    )
    
    text = f"""
🎯 *{home_team} vs {away_team} - 3가지 전략*

📈 *배당률:* 홈 `{home_odds}` | 무 `{draw_odds}` | 원정 `{away_odds}`

"""
    
    for key in ['conservative', 'balanced', 'aggressive']:
        strat = results[key]
        text += f"\n*{strat['name']}*\n"
        
        if strat['picks']:
            for p in strat['picks']:
                text += f"  → `{p['selection']}` @ {p['odds']} "
                text += f"(확률 {p['prob']*100:.0f}%, EV {p['ev']*100:+.1f}%)\n"
        else:
            text += "  → 조건 미충족 (픽 없음)\n"
        
        text += f"  💡 최종: *{strat['recommendation']}*\n"
    
    text += "\n⚠️ 각 전략은 위험 수준에 따라 배팅 금액이 다릅니다."
    
    await update.message.reply_text(text, parse_mode='Markdown')


async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """에러 핸들러"""
    logger.error(f"Update {update} caused error {context.error}")
    if update and update.effective_message:
        await update.effective_message.reply_text(
            "⚠️ 오류가 발생했습니다. 명령어 형식을 확인해주세요.\n"
            "`/help` 로 도움말을 확인할 수 있습니다.",
            parse_mode='Markdown'
        )


def main():
    """봇 메인"""
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    
    if not token:
        print("❌ TELEGRAM_BOT_TOKEN 환경변수를 설정해주세요.")
        print("   export TELEGRAM_BOT_TOKEN='your_bot_token'")
        print("   또는 .env 파일에 TELEGRAM_BOT_TOKEN=your_token 추가")
        sys.exit(1)
    
    print("🤖 봇 시작 중...")
    
    application = Application.builder().token(token).build()
    
    # 핸들러 등록
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_cmd))
    application.add_handler(CommandHandler("analyze", analyze))
    application.add_handler(CommandHandler("killpick", killpick))
    application.add_handler(CommandHandler("strategies", strategies))
    
    # 에러 핸들러
    application.add_error_handler(error_handler)
    
    print("✅ 봇 실행 중! Ctrl+C로 종료")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == '__main__':
    main()

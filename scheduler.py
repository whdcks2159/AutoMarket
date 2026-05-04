import logging
from datetime import datetime, timedelta
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
import pytz

logger = logging.getLogger(__name__)
KST = pytz.timezone('Asia/Seoul')

HOLIDAYS_KR = set()  # 공휴일 데이터 — 운영 시 외부 API 또는 수동 업데이트


def is_trading_day_kr() -> bool:
    now = datetime.now(KST)
    if now.weekday() >= 5:
        return False
    date_str = now.strftime('%Y%m%d')
    return date_str not in HOLIDAYS_KR


def is_trading_day_us() -> bool:
    now = datetime.now(KST)
    return now.weekday() < 5


def run_strategy_for_account(account_id: int, strategy_name: str):
    from app import app
    with app.app_context():
        from models import Account
        from kis_api import KISClient
        from strategies import STRATEGY_MAP

        account = Account.query.get(account_id)
        if not account or not account.is_active:
            return
        if account.strategy != strategy_name:
            return

        try:
            kis = KISClient(account)
            strategy_cls = STRATEGY_MAP.get(strategy_name)
            if strategy_cls:
                strategy_cls(account, kis).run()
        except Exception as e:
            logger.error("account=%s strategy=%s error=%s", account_id, strategy_name, e)


def run_all_active_strategies(strategy_name: str):
    from app import app
    with app.app_context():
        from models import Account
        accounts = Account.query.filter_by(strategy=strategy_name, is_active=True).all()
        for account in accounts:
            run_strategy_for_account(account.id, strategy_name)


def run_all_active_strategies_market(strategy_name: str, market: str):
    from app import app
    with app.app_context():
        from models import Account
        accounts = Account.query.filter_by(
            strategy=strategy_name, is_active=True, market_type=market
        ).all()
        for account in accounts:
            run_strategy_for_account(account.id, strategy_name)


def run_screener_for_account(account_id: int, strategy_name: str, market: str):
    """스크리너 활성화된 계좌에 대해 종목 스캔 실행."""
    from app import app
    with app.app_context():
        from models import Account
        from kis_api import KISClient

        account = Account.query.get(account_id)
        if not account or not account.is_active or not account.screener_enabled:
            return
        if account.strategy != strategy_name:
            return

        try:
            kis = KISClient(account)
            if market == 'KR':
                from screener.korea_screener import KoreaScreener
                sc = KoreaScreener(account, kis)
                if strategy_name == 'golden_rsi':
                    sc.scan_golden_rsi()
                elif strategy_name == 'week52_high':
                    sc.scan_week52_high()
                elif strategy_name == 'volatility_breakout':
                    sc.scan_volatility_breakout()
            else:
                from screener.us_screener import USScreener
                sc = USScreener(account, kis)
                if strategy_name == 'dual_momentum':
                    sc.scan_dual_momentum()
                elif strategy_name == 'week52_high':
                    sc.scan_week52_high()
                elif strategy_name == 'volatility_breakout':
                    sc.scan_volatility_breakout()
        except Exception as e:
            logger.error("screener account=%s strategy=%s error=%s", account_id, strategy_name, e)


def run_all_active_screeners(strategy_name: str, market: str):
    from app import app
    with app.app_context():
        from models import Account
        accounts = Account.query.filter_by(
            strategy=strategy_name,
            is_active=True,
            screener_enabled=True,
            market_type=market,
        ).all()
        for account in accounts:
            run_screener_for_account(account.id, strategy_name, market)


def run_morning_scan_and_trade_kr(account_id: int, strategy_name: str):
    """스캔 → 즉시 매수: 한 계좌에 대해 스크리너 실행 후 바로 전략 실행."""
    from app import app
    with app.app_context():
        from models import Account
        from kis_api import KISClient
        from strategies import STRATEGY_MAP

        account = Account.query.get(account_id)
        if not account:
            logger.warning("계좌 없음 account_id=%s", account_id)
            return
        if not account.is_active:
            logger.warning("계좌 비활성화 account=%s(%s) — 대시보드에서 자동매매 ON 필요", account_id, getattr(account, 'name', ''))
            return
        if account.strategy != strategy_name:
            logger.warning("전략 불일치 account=%s 설정=%s 요청=%s", account_id, account.strategy, strategy_name)
            return

        logger.warning("스캔+매수 시작 account=%s(%s) strategy=%s", account_id, account.name, strategy_name)
        kis = KISClient(account)

        # 1단계: 전체 주식 스캔 (실패해도 매수는 진행 — 기본 종목 목록으로 fallback)
        try:
            from screener.korea_screener import KoreaScreener
            sc = KoreaScreener(account, kis)
            if strategy_name == 'golden_rsi':
                sc.scan_golden_rsi()
            elif strategy_name == 'week52_high':
                sc.scan_week52_high()
            elif strategy_name == 'volatility_breakout':
                sc.scan_volatility_breakout()
        except Exception as e:
            logger.error("스캔 실패 account=%s strategy=%s — 기본 종목으로 매수 진행: %s", account_id, strategy_name, e)

        # 2단계: 매수/매도 실행 (스캔 성공 여부와 무관하게 항상 실행)
        try:
            strategy_cls = STRATEGY_MAP.get(strategy_name)
            if strategy_cls:
                strategy_cls(account, kis).run()
            logger.info("매수/매도 완료 account=%s strategy=%s", account_id, strategy_name)
        except Exception as e:
            logger.error("매수/매도 실패 account=%s strategy=%s: %s", account_id, strategy_name, e, exc_info=True)


def run_all_morning_trade_kr(strategy_name: str):
    """모든 활성 국내주 계좌에 대해 스캔+매수 실행."""
    from app import app
    with app.app_context():
        from models import Account
        accounts = Account.query.filter_by(
            strategy=strategy_name, is_active=True, market_type='KR'
        ).all()
        logger.warning("전략=%s 대상 KR 활성 계좌 %d개", strategy_name, len(accounts))
        for account in accounts:
            run_morning_scan_and_trade_kr(account.id, strategy_name)


def job_morning_kr():
    """09:00 — 전체 주식 스캔 후 즉시 매수 (국내주 전략 공통)."""
    if not is_trading_day_kr():
        logger.warning("오늘은 휴장일 — 아침 매매 스킵")
        return
    logger.warning("아침 스캔+매수 시작 (국내주)")
    for strategy in ('golden_rsi', 'week52_high', 'volatility_breakout',
                     'bollinger_band', 'macd', 'turtle_trading'):
        run_all_morning_trade_kr(strategy)


def job_screener_us_morning():
    """미국주 스크리너 — 매일 장 시작 전 (23:00 KST = 오전 10:00 EST)."""
    if not is_trading_day_us():
        return
    logger.info("미국주 스크리너 실행")
    run_all_active_screeners('week52_high', 'US')
    run_all_active_screeners('volatility_breakout', 'US')


def job_screener_dual_momentum():
    """듀얼 모멘텀 스크리너 — 월초 첫 거래일."""
    now = datetime.now(KST)
    if now.day > 7:
        return
    first_trading = None
    for day in range(1, 8):
        d = now.replace(day=day)
        if d.weekday() < 5:
            first_trading = d.day
            break
    if now.day != first_trading:
        return
    logger.info("듀얼 모멘텀 스크리너 실행")
    run_all_active_screeners('dual_momentum', 'US')


def job_golden_rsi():
    if not is_trading_day_kr():
        logger.info("골든RSI: 오늘은 휴장일 — 스킵")
        return
    logger.info("골든RSI 전략 실행 시작")
    run_all_active_strategies('golden_rsi')


def job_week52_high():
    if not is_trading_day_kr():
        return
    logger.info("52주 신고가 전략 실행")
    run_all_active_strategies('week52_high')


def job_volatility_breakout():
    if not is_trading_day_kr():
        return
    logger.info("변동성 돌파 전략 실행 (5분 체크)")
    run_all_active_strategies('volatility_breakout')


def job_bollinger_close():
    if not is_trading_day_kr():
        return
    logger.info("볼린저 밴드 장 마감 체크")
    run_all_active_strategies_market('bollinger_band', 'KR')


def job_macd_kr_close():
    if not is_trading_day_kr():
        return
    logger.info("MACD 장 마감 체크 (국내주)")
    run_all_active_strategies_market('macd', 'KR')


def job_turtle_kr_close():
    if not is_trading_day_kr():
        return
    logger.info("터틀 트레이딩 장 마감 체크 (국내주)")
    run_all_active_strategies_market('turtle_trading', 'KR')


def job_value_investing_monthly():
    """매월 첫 거래일 08:50 — 가치투자 월간 리밸런싱."""
    now = datetime.now(KST)
    if now.day > 7:
        return
    first_trading = None
    for day in range(1, 8):
        d = now.replace(day=day)
        if d.weekday() < 5:
            first_trading = d.day
            break
    if now.day != first_trading:
        return
    if not is_trading_day_kr():
        return
    logger.info("가치투자 월간 리밸런싱 실행")
    run_all_active_strategies_market('value_investing', 'KR')


def job_macd_turtle_us():
    """23:30 — MACD / 터틀 트레이딩 미국주 전략."""
    if not is_trading_day_us():
        return
    logger.info("MACD/터틀 미국주 전략 실행")
    run_all_active_strategies_market('macd', 'US')
    run_all_active_strategies_market('turtle_trading', 'US')


def job_dual_momentum():
    now = datetime.now(KST)
    # 매월 첫 거래일 체크
    if now.day > 7:
        return
    # 이번 달 첫 번째 월~금 확인
    first_trading = None
    for day in range(1, 8):
        d = now.replace(day=day)
        if d.weekday() < 5:
            first_trading = d.day
            break
    if now.day != first_trading:
        return
    logger.info("듀얼 모멘텀 월간 리밸런싱 실행")
    run_all_active_strategies('dual_momentum')


def get_next_run_info(strategy_name: str) -> dict:
    """전략별 다음 실행 예정 시간을 반환합니다."""
    now = datetime.now(KST)

    def _next_trading_day(from_dt):
        d = from_dt + timedelta(days=1)
        while d.weekday() >= 5 or d.strftime('%Y%m%d') in HOLIDAYS_KR:
            d += timedelta(days=1)
        return d

    def _is_trading_now():
        return now.weekday() < 5 and now.strftime('%Y%m%d') not in HOLIDAYS_KR

    if strategy_name in ('golden_rsi', 'week52_high', 'bollinger_band', 'macd', 'turtle_trading', 'value_investing'):
        slots = [
            now.replace(hour=9, minute=0, second=0, microsecond=0),
            now.replace(hour=15, minute=20, second=0, microsecond=0),
        ]
        for t in slots:
            if t > now and _is_trading_now():
                label = '09:00 장 시작' if t.hour == 9 else '15:20 장 마감'
                return {'next_run': t.isoformat(), 'label': f"오늘 {label}", 'interval': '09:00 / 15:20 (거래일)'}
        next_day = _next_trading_day(now)
        t = next_day.replace(hour=9, minute=0, second=0, microsecond=0)
        return {'next_run': t.isoformat(), 'label': f"{next_day.strftime('%m/%d')} 09:00", 'interval': '09:00 / 15:20 (거래일)'}

    if strategy_name == 'volatility_breakout':
        open_t = now.replace(hour=9, minute=0, second=0, microsecond=0)
        close_t = now.replace(hour=15, minute=30, second=0, microsecond=0)
        if _is_trading_now() and open_t <= now < close_t:
            next_min = ((now.minute // 5) + 1) * 5
            next_run = now.replace(second=0, microsecond=0) + timedelta(minutes=(next_min - now.minute))
            if next_run <= close_t:
                secs = int((next_run - now).total_seconds())
                return {'next_run': next_run.isoformat(), 'label': f"약 {secs // 60}분 {secs % 60}초 후 ({next_run.strftime('%H:%M')})", 'interval': '5분마다 (09:00~15:30)'}
        if _is_trading_now() and now < open_t:
            return {'next_run': open_t.isoformat(), 'label': '오늘 09:00 장 시작', 'interval': '5분마다 (09:00~15:30)'}
        next_day = _next_trading_day(now)
        t = next_day.replace(hour=9, minute=0, second=0, microsecond=0)
        return {'next_run': t.isoformat(), 'label': f"{next_day.strftime('%m/%d')} 09:00", 'interval': '5분마다 (09:00~15:30)'}

    if strategy_name == 'dual_momentum':
        for day in range(1, 8):
            try:
                candidate = now.replace(day=day, hour=23, minute=30, second=0, microsecond=0)
            except ValueError:
                continue
            if candidate.weekday() < 5 and candidate > now:
                return {'next_run': candidate.isoformat(), 'label': f"이번 달 {day}일 23:30 (첫 거래일)", 'interval': '매월 첫 거래일 23:30'}
        if now.month == 12:
            next_month = now.replace(year=now.year + 1, month=1, day=1)
        else:
            next_month = now.replace(month=now.month + 1, day=1)
        for day in range(1, 8):
            try:
                candidate = next_month.replace(day=day, hour=23, minute=30, second=0, microsecond=0)
            except ValueError:
                continue
            if candidate.weekday() < 5:
                return {'next_run': candidate.isoformat(), 'label': f"다음 달 {candidate.strftime('%m/%d')} 23:30", 'interval': '매월 첫 거래일 23:30'}

    return {'next_run': None, 'label': '알 수 없음', 'interval': '-'}


def create_scheduler() -> BackgroundScheduler:
    scheduler = BackgroundScheduler(timezone=KST)

    # 국내주 아침: 09:00 전체 스캔+매수 (골든RSI, 52주 신고가)
    scheduler.add_job(job_morning_kr, CronTrigger(hour=9, minute=0, timezone=KST), id='morning_kr')

    # 국내주 장 마감: 15:20 매도 체크
    scheduler.add_job(job_golden_rsi, CronTrigger(hour=15, minute=20, timezone=KST), id='golden_rsi_close')
    scheduler.add_job(job_week52_high, CronTrigger(hour=15, minute=20, timezone=KST), id='week52_close')
    scheduler.add_job(job_bollinger_close, CronTrigger(hour=15, minute=20, timezone=KST), id='bollinger_close')
    scheduler.add_job(job_macd_kr_close, CronTrigger(hour=15, minute=20, timezone=KST), id='macd_kr_close')
    scheduler.add_job(job_turtle_kr_close, CronTrigger(hour=15, minute=20, timezone=KST), id='turtle_kr_close')

    # 변동성 돌파: 5분마다 09:00~15:30
    scheduler.add_job(
        job_volatility_breakout,
        CronTrigger(hour='9-15', minute='*/5', timezone=KST),
        id='volatility_5min',
    )

    # 듀얼 모멘텀: 매월 첫 거래일 23:30
    scheduler.add_job(job_dual_momentum, CronTrigger(hour=23, minute=30, timezone=KST), id='dual_momentum')

    # MACD / 터틀 미국주: 23:30
    scheduler.add_job(job_macd_turtle_us, CronTrigger(hour=23, minute=30, timezone=KST), id='macd_turtle_us')

    # 가치투자: 매월 첫 거래일 08:50
    scheduler.add_job(job_value_investing_monthly, CronTrigger(hour=8, minute=50, timezone=KST), id='value_investing_monthly')

    # 미국주 스크리너: 23:00
    scheduler.add_job(job_screener_us_morning, CronTrigger(hour=23, minute=0, timezone=KST), id='screener_us_morning')

    # 듀얼 모멘텀 스크리너: 월초 23:00
    scheduler.add_job(job_screener_dual_momentum, CronTrigger(hour=23, minute=0, timezone=KST), id='screener_dual_momentum')

    return scheduler

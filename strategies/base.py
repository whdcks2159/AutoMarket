from abc import ABC, abstractmethod
from datetime import datetime
import logging
import pytz

_KST = pytz.timezone('Asia/Seoul')


def _now_kst() -> datetime:
    return datetime.now(_KST).replace(tzinfo=None)


def _today_kst():
    return datetime.now(_KST).date()

logger = logging.getLogger(__name__)


class BaseStrategy(ABC):
    name: str = 'base'
    description: str = ''

    def __init__(self, account, kis_client):
        self.account = account
        self.kis = kis_client

    @abstractmethod
    def run(self):
        """전략 실행 — 매수/매도 시그널 생성 및 주문 실행."""
        pass

    def log_signal(self, message: str, event_type: str = 'SIGNAL'):
        from models import db, StrategyLog
        log = StrategyLog(
            account_id=self.account.id,
            event_type=event_type,
            new_strategy=self.name,
            message=f"[{self.name}] {message}",
            created_at=_now_kst(),
        )
        db.session.add(log)
        db.session.commit()
        logger.info("[account=%s][%s] %s", self.account.id, self.name, message)

    def record_trade(self, symbol: str, symbol_name: str, side: str,
                     quantity: int, price: float, order_result: dict = None,
                     error: str = None):
        from models import db, Trade
        status = 'FILLED' if (order_result and order_result.get('rt_cd') == '0') else 'FAILED'
        order_id = None
        if order_result:
            output = order_result.get('output', {})
            order_id = output.get('ODNO') or output.get('odno')

        trade = Trade(
            account_id=self.account.id,
            symbol=symbol,
            symbol_name=symbol_name,
            side=side,
            quantity=quantity,
            price=price,
            amount=price * quantity,
            strategy=self.name,
            order_id=order_id,
            status=status,
            error_message=error,
            executed_at=_now_kst(),
        )
        db.session.add(trade)
        db.session.commit()
        return trade

    def get_scan_symbols_kr(self, default_symbols: list) -> list:
        """오늘 스캔 결과가 있으면 사용, 없으면 기본 목록 반환."""
        from models import ScanResult
        from datetime import date, datetime
        today_start = datetime.combine(_today_kst(), datetime.min.time())
        max_n = getattr(self.account, 'screener_max_symbols', 5)
        results = (ScanResult.query
                   .filter_by(account_id=self.account.id, strategy=self.name, signal='BUY')
                   .filter(ScanResult.scanned_at >= today_start)
                   .order_by(ScanResult.scanned_at.desc())
                   .limit(max_n)
                   .all())
        return [r.ticker for r in results] if results else default_symbols

    def get_scan_symbols_us(self, default_symbols: list) -> list:
        """미국주 스크리너 심볼 반환 (ticker, exchange) 튜플 목록."""
        if not getattr(self.account, 'screener_enabled', False):
            return default_symbols
        from models import ScanResult
        from datetime import date, datetime
        today_start = datetime.combine(_today_kst(), datetime.min.time())
        results = (ScanResult.query
                   .filter_by(account_id=self.account.id, strategy=self.name, signal='BUY')
                   .filter(ScanResult.scanned_at >= today_start)
                   .order_by(ScanResult.scanned_at.desc())
                   .limit(self.account.screener_max_symbols)
                   .all())
        if not results:
            return default_symbols
        # ticker 형식: "AAPL|NAS"
        pairs = []
        for r in results:
            parts = r.ticker.split('|')
            if len(parts) == 2:
                pairs.append((parts[0], parts[1]))
        return pairs if pairs else default_symbols

    def check_daily_buy_limit(self) -> bool:
        """오늘 일일 매수 한도 초과 여부 확인. True=매수 가능."""
        if not getattr(self.account, 'screener_enabled', False):
            return True
        from models import Trade
        from datetime import date, datetime
        today_start = datetime.combine(_today_kst(), datetime.min.time())
        count = (Trade.query
                 .filter_by(account_id=self.account.id, side='BUY', status='FILLED')
                 .filter(Trade.executed_at >= today_start)
                 .count())
        return count < self.account.screener_daily_buy_limit

    def already_bought_today(self, symbol: str) -> bool:
        """오늘 이미 해당 종목을 매수했는지 확인 (중복 방지)."""
        if not getattr(self.account, 'screener_enabled', False):
            return False
        from models import Trade
        from datetime import date, datetime
        today_start = datetime.combine(_today_kst(), datetime.min.time())
        return (Trade.query
                .filter_by(account_id=self.account.id, symbol=symbol, side='BUY')
                .filter(Trade.executed_at >= today_start)
                .count()) > 0

    def screener_qty(self, price: float, ratio: float = 1.0, market: str = 'KR') -> int:
        """스크리너 활성화 시 per_symbol_limit 적용, 미활성 시 None 반환."""
        if not getattr(self.account, 'screener_enabled', False):
            return None
        limit = self.account.screener_per_symbol_limit * ratio
        if market == 'US':
            limit = limit / 1350
        return max(0, int(limit / price))

    @staticmethod
    def calc_rsi(closes: list, period: int = 14) -> float:
        if len(closes) < period + 1:
            return 50.0
        gains, losses = [], []
        for i in range(1, period + 1):
            delta = closes[-i] - closes[-(i + 1)]
            (gains if delta > 0 else losses).append(abs(delta))
        avg_gain = sum(gains) / period if gains else 0
        avg_loss = sum(losses) / period if losses else 1e-9
        rs = avg_gain / avg_loss
        return 100 - (100 / (1 + rs))

    @staticmethod
    def calc_sma(closes: list, period: int) -> float:
        if len(closes) < period:
            return 0.0
        return sum(closes[-period:]) / period

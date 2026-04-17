from abc import ABC, abstractmethod
from datetime import datetime
import logging

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
            executed_at=datetime.utcnow(),
        )
        db.session.add(trade)
        db.session.commit()
        return trade

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

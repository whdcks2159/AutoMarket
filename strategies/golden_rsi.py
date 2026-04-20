"""전략 1 — 골든크로스 + RSI (국내주 안정형)
매수: 5일선 > 20일선 골든크로스 AND RSI < 70
     OR RSI < 30 AND 5일선 > 20일선
매도: 5일선 < 20일선 데드크로스 AND RSI > 30
     OR RSI > 70
실행: 09:00 / 15:20
"""
import time
from .base import BaseStrategy


class GoldenRSIStrategy(BaseStrategy):
    name = 'golden_rsi'
    description = '골든크로스+RSI (국내 안정형)'

    SYMBOLS = ['005930', '000660', '035720', '035420', '207940']  # 기본 watchlist

    def run(self):
        self.log_signal("전략 실행 시작")
        holdings = self._get_holdings()
        symbols = self.get_scan_symbols_kr(self.SYMBOLS)

        for symbol in symbols:
            try:
                self._process(symbol, holdings)
            except Exception as e:
                self.log_signal(f"{symbol} 처리 오류: {e}", event_type='ERROR')
            time.sleep(1.0)

    def _get_holdings(self) -> dict:
        try:
            data = self.kis.get_balance_kr()
            output1 = data.get('output1', [])
            return {item['pdno']: int(item.get('hldg_qty', 0)) for item in output1}
        except Exception as e:
            self.log_signal(f"잔고 조회 실패: {e}", event_type='ERROR')
            return {}

    def _process(self, symbol: str, holdings: dict):
        ohlcv = self.kis.get_daily_ohlcv_kr(symbol, period=30)
        if len(ohlcv) < 21:
            self.log_signal(f"{symbol} 데이터 부족 ({len(ohlcv)}봉)", event_type='INFO')
            return

        closes = [float(row['stck_clpr']) for row in reversed(ohlcv)]
        sma5 = self.calc_sma(closes, 5)
        sma20 = self.calc_sma(closes, 20)
        rsi = self.calc_rsi(closes, 14)
        current_price = closes[-1]
        held_qty = holdings.get(symbol, 0)

        golden_cross = sma5 > sma20
        dead_cross = sma5 < sma20

        self.log_signal(
            f"{symbol} 분석 | 가격={current_price:,.0f} SMA5={sma5:.0f} SMA20={sma20:.0f} "
            f"RSI={rsi:.1f} 골든크로스={golden_cross} 보유={held_qty}",
            event_type='INFO'
        )

        # 매수 판단
        if held_qty == 0:
            should_buy = (golden_cross and rsi < 70) or (rsi < 30 and golden_cross)
            if should_buy:
                if not self.check_daily_buy_limit():
                    self.log_signal(f"일일 매수 한도 초과 — {symbol} 매수 스킵")
                    return
                if self.already_bought_today(symbol):
                    return
                qty = self.screener_qty(current_price) or self._calc_qty(current_price)
                if qty > 0:
                    self.log_signal(f"매수 시그널 {symbol} | 가격={current_price} RSI={rsi:.1f} SMA5={sma5:.0f} SMA20={sma20:.0f}")
                    try:
                        result = self.kis.order_with_retry(symbol, 'BUY', qty, current_price, 'KR')
                        self.record_trade(symbol, symbol, 'BUY', qty, current_price, result)
                    except Exception as e:
                        self.record_trade(symbol, symbol, 'BUY', qty, current_price, error=str(e))

        # 매도 판단
        elif held_qty > 0:
            should_sell = (dead_cross and rsi > 30) or (rsi > 70)
            if should_sell:
                self.log_signal(f"매도 시그널 {symbol} | 가격={current_price} RSI={rsi:.1f}")
                try:
                    result = self.kis.order_with_retry(symbol, 'SELL', held_qty, current_price, 'KR')
                    self.record_trade(symbol, symbol, 'SELL', held_qty, current_price, result)
                except Exception as e:
                    self.record_trade(symbol, symbol, 'SELL', held_qty, current_price, error=str(e))

    def _calc_qty(self, price: float) -> int:
        limit = self.account.investment_limit
        return max(0, int(limit * 0.2 / price))  # 투자한도의 20%씩 분산

"""전략 3 — 52주 신고가 모멘텀 (공격형)
매수: 현재가가 52주 신고가 돌파
매도: 매수가 대비 -10% 손절 OR 20일선 하향 이탈
실행: 09:00 / 15:20
"""
from .base import BaseStrategy


class Week52HighStrategy(BaseStrategy):
    name = 'week52_high'
    description = '52주 신고가 모멘텀 (공격형)'

    KR_SYMBOLS = ['005930', '000660', '035420', '051910', '006400']
    US_SYMBOLS = [('AAPL', 'NAS'), ('MSFT', 'NAS'), ('NVDA', 'NAS'), ('AMZN', 'NAS')]
    STOP_LOSS_RATE = 0.10
    SMA_PERIOD = 20

    def run(self):
        self.log_signal("52주 신고가 전략 실행")
        market = self.account.market_type

        if market == 'KR':
            holdings = self._get_holdings_kr()
            symbols = self.get_scan_symbols_kr(self.KR_SYMBOLS)
            for symbol in symbols:
                try:
                    self._process_kr(symbol, holdings)
                except Exception as e:
                    self.log_signal(f"{symbol} 오류: {e}", event_type='ERROR')
        else:
            holdings = self._get_holdings_us()
            symbol_pairs = self.get_scan_symbols_us(self.US_SYMBOLS)
            for symbol, excd in symbol_pairs:
                try:
                    self._process_us(symbol, excd, holdings)
                except Exception as e:
                    self.log_signal(f"{symbol} 오류: {e}", event_type='ERROR')

    def _process_kr(self, symbol: str, holdings: dict):
        ohlcv = self.kis.get_daily_ohlcv_kr(symbol, period=260)
        if len(ohlcv) < 60:
            return

        closes = [float(row['stck_clpr']) for row in reversed(ohlcv)]
        highs = [float(row['stck_hgpr']) for row in reversed(ohlcv)]
        current = closes[-1]
        week52_high = max(highs[-252:]) if len(highs) >= 252 else max(highs)
        sma20 = self.calc_sma(closes, self.SMA_PERIOD)
        held_qty = holdings.get(symbol, 0)

        if held_qty == 0 and current > week52_high * 0.999:
            if not self.check_daily_buy_limit():
                self.log_signal(f"일일 매수 한도 초과 — {symbol} 스킵")
                return
            if self.already_bought_today(symbol):
                return
            qty = self.screener_qty(current, 0.3) or self._calc_qty(current, 'KR')
            if qty > 0:
                self.log_signal(f"52주 신고가 돌파 매수 {symbol} | 현재={current} 신고가={week52_high:.0f}")
                try:
                    result = self.kis.order_with_retry(symbol, 'BUY', qty, current, 'KR')
                    self.record_trade(symbol, symbol, 'BUY', qty, current, result)
                except Exception as e:
                    self.record_trade(symbol, symbol, 'BUY', qty, current, error=str(e))

        elif held_qty > 0:
            buy_price = self._get_avg_buy_price_kr(symbol, holdings)
            stop_loss = buy_price * (1 - self.STOP_LOSS_RATE) if buy_price else 0
            below_sma = current < sma20

            if (stop_loss and current <= stop_loss) or below_sma:
                reason = "손절" if (stop_loss and current <= stop_loss) else "20일선 이탈"
                self.log_signal(f"매도 ({reason}) {symbol} | 현재={current}")
                try:
                    result = self.kis.order_with_retry(symbol, 'SELL', held_qty, current, 'KR')
                    self.record_trade(symbol, symbol, 'SELL', held_qty, current, result)
                except Exception as e:
                    self.record_trade(symbol, symbol, 'SELL', held_qty, current, error=str(e))

    def _process_us(self, symbol: str, excd: str, holdings: dict):
        ohlcv = self.kis.get_daily_ohlcv_us(symbol, excd, period=260)
        if len(ohlcv) < 60:
            return

        closes = [float(row['clos']) for row in reversed(ohlcv) if row.get('clos')]
        highs = [float(row['high']) for row in reversed(ohlcv) if row.get('high')]
        if not closes or not highs:
            return

        current = closes[-1]
        week52_high = max(highs[-252:]) if len(highs) >= 252 else max(highs)
        sma20 = self.calc_sma(closes, self.SMA_PERIOD)
        held_qty = holdings.get(symbol, 0)

        if held_qty == 0 and current > week52_high * 0.999:
            if not self.check_daily_buy_limit():
                self.log_signal(f"일일 매수 한도 초과 — {symbol} 스킵")
                return
            if self.already_bought_today(symbol):
                return
            qty = self.screener_qty(current, 0.3, 'US') or self._calc_qty(current, 'US')
            if qty > 0:
                self.log_signal(f"52주 신고가 돌파 매수 {symbol} | ${current} 신고가=${week52_high:.2f}")
                try:
                    result = self.kis.order_with_retry(symbol, 'BUY', qty, current, 'US', excd)
                    self.record_trade(symbol, symbol, 'BUY', qty, current, result)
                except Exception as e:
                    self.record_trade(symbol, symbol, 'BUY', qty, current, error=str(e))

        elif held_qty > 0 and current < sma20:
            self.log_signal(f"20일선 이탈 매도 {symbol} | ${current} SMA20=${sma20:.2f}")
            try:
                result = self.kis.order_with_retry(symbol, 'SELL', held_qty, current, 'US', excd)
                self.record_trade(symbol, symbol, 'SELL', held_qty, current, result)
            except Exception as e:
                self.record_trade(symbol, symbol, 'SELL', held_qty, current, error=str(e))

    def _get_holdings_kr(self) -> dict:
        try:
            data = self.kis.get_balance_kr()
            return {item['pdno']: int(item.get('hldg_qty', 0)) for item in data.get('output1', [])}
        except Exception as e:
            self.log_signal(f"국내 잔고 조회 실패: {e}", event_type='ERROR')
            return {}

    def _get_holdings_us(self) -> dict:
        try:
            data = self.kis.get_balance_us()
            return {item['ovrs_pdno']: int(item.get('ovrs_cblc_qty', 0)) for item in data.get('output1', [])}
        except Exception as e:
            self.log_signal(f"미국 잔고 조회 실패: {e}", event_type='ERROR')
            return {}

    def _get_avg_buy_price_kr(self, symbol: str, holdings: dict) -> float:
        try:
            data = self.kis.get_balance_kr()
            for item in data.get('output1', []):
                if item['pdno'] == symbol:
                    return float(item.get('pchs_avg_pric', 0))
        except Exception as e:
            self.log_signal(f"평균단가 조회 실패 {symbol}: {e}", event_type='ERROR')
        return 0.0

    def _calc_qty(self, price: float, market: str) -> int:
        limit = self.account.investment_limit
        if market == 'US':
            limit_usd = limit / 1350
            return max(0, int(limit_usd * 0.3 / price))
        return max(0, int(limit * 0.3 / price))

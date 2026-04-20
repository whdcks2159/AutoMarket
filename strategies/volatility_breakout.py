"""전략 4 — 변동성 돌파 (단타형)
목표가 = 당일 시가 + (전일 고가 - 전일 저가) * K
현재가 > 목표가 → 매수
갭 상승 3% 초과 → 스킵
장 마감 30분 전 강제 청산
K 자동 최적화 포함
실행: 5분마다
"""
import json
import os
from .base import BaseStrategy


class VolatilityBreakoutStrategy(BaseStrategy):
    name = 'volatility_breakout'
    description = '변동성 돌파 (단타형)'

    KR_SYMBOLS = ['005930', '000660', '035420', '051910', '006400']
    US_SYMBOLS = [('AAPL', 'NAS'), ('MSFT', 'NAS'), ('NVDA', 'NAS')]
    DEFAULT_K = 0.5
    MAX_K = 0.8
    MIN_K = 0.3
    GAP_SKIP_RATE = 0.03

    def run(self):
        import pytz
        from datetime import datetime
        now = datetime.now(pytz.timezone('Asia/Seoul')).replace(tzinfo=None)
        market = self.account.market_type

        if market == 'KR':
            kr_close = now.replace(hour=15, minute=20, second=0)
            kr_close_30 = now.replace(hour=14, minute=50, second=0)
            if now >= kr_close:
                return
            if now >= kr_close_30:
                self.log_signal("마감 30분 전 — 전량 청산")
                self._liquidate_all_kr()
                return
            self._run_kr()
        else:
            self._run_us(now)

    def _run_kr(self):
        k = self._get_k('KR')
        holdings = self._get_holdings_kr()
        symbols = self.get_scan_symbols_kr(self.KR_SYMBOLS)

        for symbol in symbols:
            try:
                time.sleep(1.0)
                ohlcv = self.kis.get_daily_ohlcv_kr(symbol, period=5)
                if len(ohlcv) < 2:
                    continue

                rows = list(reversed(ohlcv))
                today_open = float(rows[-1].get('stck_oprc', 0))
                prev_high = float(rows[-2].get('stck_hgpr', 0))
                prev_low = float(rows[-2].get('stck_lwpr', 0))
                prev_close = float(rows[-2].get('stck_clpr', 0))

                if today_open == 0 or prev_close == 0:
                    continue

                gap_rate = (today_open - prev_close) / prev_close
                if gap_rate > self.GAP_SKIP_RATE:
                    self.log_signal(f"{symbol} 갭 상승 {gap_rate:.1%} > 3% 스킵")
                    continue

                target_price = today_open + (prev_high - prev_low) * k
                price_data = self.kis.get_price_kr(symbol)
                current = float(price_data['output']['stck_prpr'])

                held_qty = holdings.get(symbol, 0)
                if held_qty == 0 and current >= target_price:
                    if not self.check_daily_buy_limit():
                        self.log_signal(f"일일 매수 한도 초과 — {symbol} 스킵")
                        break
                    if self.already_bought_today(symbol):
                        continue
                    qty = self.screener_qty(current, 0.5) or self._calc_qty(current, 'KR')
                    if qty > 0:
                        self.log_signal(f"변동성 돌파 매수 {symbol} | {current} >= 목표 {target_price:.0f} K={k}")
                        result = self.kis.order_with_retry(symbol, 'BUY', qty, current, 'KR')
                        self.record_trade(symbol, symbol, 'BUY', qty, current, result)
            except Exception as e:
                self.log_signal(f"{symbol} 오류: {e}", event_type='ERROR')

    def _run_us(self, now):
        from datetime import timezone
        k = self._get_k('US')
        holdings = self._get_holdings_us()

        symbol_pairs = self.get_scan_symbols_us(self.US_SYMBOLS)
        for symbol, excd in symbol_pairs:
            try:
                time.sleep(1.0)
                ohlcv = self.kis.get_daily_ohlcv_us(symbol, excd, period=5)
                if len(ohlcv) < 2:
                    continue
                rows = list(reversed(ohlcv))
                today_open = float(rows[-1].get('open', 0) or 0)
                prev_high = float(rows[-2].get('high', 0) or 0)
                prev_low = float(rows[-2].get('low', 0) or 0)
                prev_close = float(rows[-2].get('clos', 0) or 0)

                if today_open == 0 or prev_close == 0:
                    continue

                gap_rate = (today_open - prev_close) / prev_close
                if gap_rate > self.GAP_SKIP_RATE:
                    continue

                target_price = today_open + (prev_high - prev_low) * k
                price_data = self.kis.get_price_us(symbol, excd)
                current = float(price_data['output']['last'])

                held_qty = holdings.get(symbol, 0)
                if held_qty == 0 and current >= target_price:
                    if not self.check_daily_buy_limit():
                        self.log_signal(f"일일 매수 한도 초과 — {symbol} 스킵")
                        break
                    if self.already_bought_today(symbol):
                        continue
                    qty = self.screener_qty(current, 0.5, 'US') or self._calc_qty(current, 'US')
                    if qty > 0:
                        self.log_signal(f"변동성 돌파 매수 {symbol} | ${current} >= 목표 ${target_price:.2f}")
                        result = self.kis.order_with_retry(symbol, 'BUY', qty, current, 'US', excd)
                        self.record_trade(symbol, symbol, 'BUY', qty, current, result)
            except Exception as e:
                self.log_signal(f"{symbol} 오류: {e}", event_type='ERROR')

    def _liquidate_all_kr(self):
        holdings = self._get_holdings_kr()
        for symbol, qty in holdings.items():
            if qty > 0:
                try:
                    price_data = self.kis.get_price_kr(symbol)
                    price = float(price_data['output']['stck_prpr'])
                    result = self.kis.order_with_retry(symbol, 'SELL', qty, price, 'KR')
                    self.record_trade(symbol, symbol, 'SELL', qty, price, result)
                except Exception as e:
                    self.log_signal(f"{symbol} 청산 오류: {e}", event_type='ERROR')

    def _get_k(self, market: str) -> float:
        """최근 5일 수익률 기반 K 자동 최적화."""
        try:
            symbol = self.KR_SYMBOLS[0] if market == 'KR' else self.US_SYMBOLS[0][0]
            excd = None if market == 'KR' else self.US_SYMBOLS[0][1]
            ohlcv = (self.kis.get_daily_ohlcv_kr(symbol, 10)
                     if market == 'KR'
                     else self.kis.get_daily_ohlcv_us(symbol, excd, 10))
            if len(ohlcv) < 5:
                return self.DEFAULT_K

            best_k, best_ret = self.DEFAULT_K, -999.0
            for k_val in [i / 10 for i in range(3, 9)]:
                returns = []
                rows = list(reversed(ohlcv))
                for i in range(1, min(5, len(rows))):
                    if market == 'KR':
                        o = float(rows[i].get('stck_oprc', 0))
                        ph = float(rows[i - 1].get('stck_hgpr', 0))
                        pl = float(rows[i - 1].get('stck_lwpr', 0))
                        c = float(rows[i].get('stck_clpr', 0))
                    else:
                        o = float(rows[i].get('open', 0) or 0)
                        ph = float(rows[i - 1].get('high', 0) or 0)
                        pl = float(rows[i - 1].get('low', 0) or 0)
                        c = float(rows[i].get('clos', 0) or 0)
                    if o and ph and pl and c:
                        target = o + (ph - pl) * k_val
                        if c >= target:
                            returns.append((c - target) / target)
                if returns:
                    avg = sum(returns) / len(returns)
                    if avg > best_ret:
                        best_ret, best_k = avg, k_val
            return max(self.MIN_K, min(self.MAX_K, best_k))
        except Exception:
            return self.DEFAULT_K

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

    def _calc_qty(self, price: float, market: str) -> int:
        limit = self.account.investment_limit
        if market == 'US':
            limit_usd = limit / 1350
            return max(0, int(limit_usd * 0.5 / price))
        return max(0, int(limit * 0.5 / price))

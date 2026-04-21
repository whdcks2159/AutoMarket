"""전략 8 — 터틀 트레이딩 (리처드 데니스 1983, 국내/미국주)
시스템 1: 20일 신고가 돌파 → 매수
시스템 2: 55일 신고가 돌파 → 매수 (더 강한 신호)
10일 신저가 이탈 → 매도
ATR(14일) 기반 포지션 사이징
손절: 매수가 - 2 × ATR
실행: 09:00 / 15:20
"""
from typing import Optional
from .base import BaseStrategy


def calculate_atr(
    highs: list[float],
    lows: list[float],
    closes: list[float],
    period: int = 14,
) -> float:
    """Average True Range 계산."""
    if len(highs) < period + 1 or len(lows) < period + 1 or len(closes) < period + 1:
        if len(highs) >= 2:
            # 데이터 부족 시 단순 평균 고저 범위 사용
            return sum(h - l for h, l in zip(highs[-period:], lows[-period:])) / max(len(highs[-period:]), 1)
        return 0.0

    true_ranges: list[float] = []
    for i in range(1, period + 1):
        high = highs[-i]
        low = lows[-i]
        prev_close = closes[-(i + 1)]
        tr = max(high - low, abs(high - prev_close), abs(low - prev_close))
        true_ranges.append(tr)

    return sum(true_ranges) / period if true_ranges else 0.0


def calculate_position_size(
    capital: float,
    atr: float,
    risk_pct: float = 0.02,
) -> int:
    """ATR 기반 포지션 사이징 (자본의 2% 위험 허용).

    position_size = (capital × risk_pct) / (2 × ATR)
    """
    if atr <= 0 or capital <= 0:
        return 0
    return max(0, int((capital * risk_pct) / (2 * atr)))


def generate_signal(
    prices: list[float],
    highs: list[float],
    lows: list[float],
    closes: Optional[list[float]] = None,
    holding: bool = False,
    buy_price: Optional[float] = None,
    capital: float = 1_000_000.0,
) -> dict:
    """터틀 트레이딩 신호 생성.

    Returns:
        {"signal": BUY|SELL|HOLD, "reason", "atr", "stop_loss",
         "position_size", "system": 1|2}
    """
    closes = closes or prices
    base = {'signal': 'HOLD', 'reason': '', 'atr': 0.0, 'stop_loss': 0.0,
            'position_size': 0, 'system': 0}

    min_needed = 56  # 시스템 2 = 55일 신고가
    if len(prices) < min_needed or len(highs) < min_needed or len(lows) < 11:
        return {**base, 'reason': f'데이터 부족 (최소 {min_needed}개 필요)'}

    current = prices[-1]
    if current <= 0:
        return {**base, 'reason': '현재가 오류'}

    atr = calculate_atr(highs, lows, closes, period=14)
    stop_loss = buy_price - 2 * atr if (buy_price and buy_price > 0 and atr > 0) else 0.0
    pos_size = calculate_position_size(capital, atr)

    high_20 = max(highs[-21:-1]) if len(highs) >= 21 else 0
    high_55 = max(highs[-56:-1]) if len(highs) >= 56 else 0
    low_10 = min(lows[-11:-1]) if len(lows) >= 11 else float('inf')

    result = {
        'atr': round(atr, 2),
        'stop_loss': round(stop_loss, 2),
        'position_size': pos_size,
        'system': 0,
    }

    # 보유 중: 손절 또는 10일 신저가 이탈
    if holding and buy_price and buy_price > 0:
        if stop_loss > 0 and current <= stop_loss:
            return {'signal': 'SELL',
                    'reason': f'ATR 손절가 이탈 ({current:,.0f} <= {stop_loss:,.0f})', **result}
        if current < low_10:
            return {'signal': 'SELL',
                    'reason': f'10일 신저가 이탈 ({current:,.0f} < {low_10:,.0f})', **result}

    # 미보유: 매수 조건
    if not holding:
        if high_55 > 0 and current > high_55:
            return {'signal': 'BUY',
                    'reason': f'시스템2: 55일 신고가 돌파 ({current:,.0f} > {high_55:,.0f})',
                    **{**result, 'system': 2}}
        if high_20 > 0 and current > high_20:
            return {'signal': 'BUY',
                    'reason': f'시스템1: 20일 신고가 돌파 ({current:,.0f} > {high_20:,.0f})',
                    **{**result, 'system': 1}}

    return {'signal': 'HOLD', 'reason': '신고가 돌파 없음', **result}


class TurtleTradingStrategy(BaseStrategy):
    name = 'turtle_trading'
    description = '터틀 트레이딩 (추세 추종 시스템)'

    KR_SYMBOLS = ['005930', '000660', '035420', '005380', '051910', '207940']
    US_SYMBOLS = [('AAPL', 'NAS'), ('MSFT', 'NAS'), ('NVDA', 'NAS'), ('AMZN', 'NAS'), ('GOOGL', 'NAS')]

    def run(self):
        self.log_signal("터틀 트레이딩 전략 실행 시작")
        market = self.account.market_type
        if market == 'KR':
            self._run_kr()
        else:
            self._run_us()

    def _run_kr(self):
        holdings = self._get_holdings_kr()
        symbols = self.get_scan_symbols_kr(self.KR_SYMBOLS)
        for symbol in symbols:
            try:
                self._process_kr(symbol, holdings)
            except Exception as e:
                self.log_signal(f"{symbol} 처리 오류: {e}", event_type='ERROR')

    def _run_us(self):
        holdings = self._get_holdings_us()
        symbol_pairs = self.get_scan_symbols_us(self.US_SYMBOLS)
        for symbol, excd in symbol_pairs:
            try:
                self._process_us(symbol, excd, holdings)
            except Exception as e:
                self.log_signal(f"{symbol} 처리 오류: {e}", event_type='ERROR')

    def _get_holdings_kr(self) -> dict:
        try:
            data = self.kis.get_balance_kr()
            return {
                item['pdno']: {
                    'qty': int(item.get('hldg_qty', 0)),
                    'avg_price': float(item.get('pchs_avg_pric', 0)),
                }
                for item in data.get('output1', [])
            }
        except Exception:
            return {}

    def _get_holdings_us(self) -> dict:
        try:
            data = self.kis.get_balance_us()
            return {
                item['ovrs_pdno']: {
                    'qty': int(item.get('ovrs_cblc_qty', 0)),
                    'avg_price': float(item.get('frcr_pchs_amt1', 0)),
                }
                for item in data.get('output1', [])
            }
        except Exception:
            return {}

    def _process_kr(self, symbol: str, holdings: dict):
        ohlcv = self.kis.get_daily_ohlcv_kr(symbol, period=65)
        if len(ohlcv) < 57:
            return
        rows = list(reversed(ohlcv))
        closes = [float(r['stck_clpr']) for r in rows]
        highs = [float(r['stck_hgpr']) for r in rows]
        lows = [float(r['stck_lwpr']) for r in rows]
        self._execute(symbol, closes, highs, lows, holdings.get(symbol), 'KR')

    def _process_us(self, symbol: str, excd: str, holdings: dict):
        ohlcv = self.kis.get_daily_ohlcv_us(symbol, excd, period=65)
        if len(ohlcv) < 57:
            return
        rows = list(reversed(ohlcv))
        closes = [float(r.get('clos') or r.get('close', 0)) for r in rows]
        highs = [float(r.get('high', 0) or 0) for r in rows]
        lows = [float(r.get('low', 0) or 0) for r in rows]
        self._execute(symbol, closes, highs, lows, holdings.get(symbol), 'US', excd)

    def _execute(self, symbol: str, closes: list, highs: list, lows: list,
                 holding_info: Optional[dict], market: str, excd: str = 'NAS'):
        is_holding = bool(holding_info and holding_info.get('qty', 0) > 0)
        buy_price = holding_info.get('avg_price') if holding_info else None
        held_qty = holding_info.get('qty', 0) if holding_info else 0
        price = closes[-1]

        sig = generate_signal(
            closes, highs, lows, closes,
            holding=is_holding, buy_price=buy_price,
            capital=self.account.investment_limit,
        )

        if sig['signal'] == 'BUY' and not is_holding:
            if not self.check_daily_buy_limit():
                return
            if self.already_bought_today(symbol):
                return
            qty = (self.screener_qty(price, market=market)
                   or sig['position_size']
                   or self._calc_qty(price, market, 0.2))
            if qty > 0:
                self.log_signal(f"매수 {symbol} | {sig['reason']} | ATR={sig['atr']:,.0f}")
                try:
                    result = self.kis.order_with_retry(symbol, 'BUY', qty, price, market, excd)
                    self.record_trade(symbol, symbol, 'BUY', qty, price, result)
                except Exception as e:
                    self.record_trade(symbol, symbol, 'BUY', qty, price, error=str(e))

        elif sig['signal'] == 'SELL' and is_holding and held_qty > 0:
            self.log_signal(f"매도 {symbol} | {sig['reason']}")
            try:
                result = self.kis.order_with_retry(symbol, 'SELL', held_qty, price, market, excd)
                self.record_trade(symbol, symbol, 'SELL', held_qty, price, result)
            except Exception as e:
                self.record_trade(symbol, symbol, 'SELL', held_qty, price, error=str(e))



if __name__ == '__main__':
    import random
    rng = random.Random(99)

    n = 70
    closes = [50000.0]
    for _ in range(n - 1):
        closes.append(max(closes[-1] + rng.gauss(100, 500), 1000.0))
    highs = [c * rng.uniform(1.0, 1.03) for c in closes]
    lows = [c * rng.uniform(0.97, 1.0) for c in closes]

    atr = calculate_atr(highs, lows, closes)
    print(f"ATR={atr:,.2f}")

    pos = calculate_position_size(1_000_000, atr)
    print(f"포지션 사이즈={pos}주")

    sig = generate_signal(closes, highs, lows)
    print(f"신호: {sig['signal']} | {sig['reason']} | 시스템={sig['system']}")

    # 손절 케이스
    sig2 = generate_signal(closes[:-1] + [closes[-1] * 0.8], highs, lows,
                           holding=True, buy_price=closes[-1])
    print(f"손절: {sig2['signal']} | {sig2['reason']}")

    # 데이터 부족
    sig3 = generate_signal([100.0] * 10, [105.0] * 10, [95.0] * 10)
    print(f"데이터 부족: {sig3['signal']} | {sig3['reason']}")

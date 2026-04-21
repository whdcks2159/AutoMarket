"""전략 6 — MACD (국내/미국주 추세 추종)
12일 EMA - 26일 EMA = MACD선
MACD선의 9일 EMA = 시그널선
MACD선이 시그널선 상향 돌파 + 히스토그램 양전환 → 매수
MACD선이 시그널선 하향 돌파 + 히스토그램 음전환 → 매도
제로선 아래 골든크로스 → 강화 매수 신호
실행: 09:00 / 15:20
"""
from typing import Optional
from .base import BaseStrategy


def calculate_ema(prices: list[float], period: int) -> Optional[float]:
    """지수 이동평균(EMA) 계산."""
    if not prices or len(prices) < period or period <= 0:
        return None
    k = 2.0 / (period + 1)
    ema = sum(prices[:period]) / period  # 초기값: 단순 평균
    for price in prices[period:]:
        ema = price * k + ema * (1 - k)
    return ema


def _ema_series(prices: list[float], period: int) -> list[float]:
    """EMA 전체 시계열 반환 (히스토그램 방향 확인용)."""
    if len(prices) < period:
        return []
    k = 2.0 / (period + 1)
    series: list[float] = []
    ema = sum(prices[:period]) / period
    series.append(ema)
    for price in prices[period:]:
        ema = price * k + ema * (1 - k)
        series.append(ema)
    return series


def calculate_macd(
    prices: list[float],
    fast: int = 12,
    slow: int = 26,
    signal: int = 9,
) -> Optional[dict]:
    """MACD 계산.

    Returns:
        {"macd", "signal", "histogram", "trend": BULLISH|BEARISH} or None
    """
    if len(prices) < slow + signal:
        return None

    fast_emas = _ema_series(prices, fast)
    slow_emas = _ema_series(prices, slow)
    if not fast_emas or not slow_emas:
        return None

    # MACD선 = fast EMA - slow EMA (같은 길이로 맞춤)
    offset = len(fast_emas) - len(slow_emas)
    macd_line = [f - s for f, s in zip(fast_emas[offset:], slow_emas)]

    if len(macd_line) < signal:
        return None

    signal_emas = _ema_series(macd_line, signal)
    if not signal_emas:
        return None

    macd_val = macd_line[-1]
    signal_val = signal_emas[-1]
    histogram = macd_val - signal_val
    trend = 'BULLISH' if macd_val > 0 else 'BEARISH'

    return {
        'macd': round(macd_val, 4),
        'signal': round(signal_val, 4),
        'histogram': round(histogram, 4),
        'trend': trend,
        '_macd_prev': macd_line[-2] if len(macd_line) >= 2 else macd_val,
        '_signal_prev': signal_emas[-2] if len(signal_emas) >= 2 else signal_val,
        '_hist_prev': (macd_line[-2] - signal_emas[-2])
                      if len(macd_line) >= 2 and len(signal_emas) >= 2
                      else histogram,
    }


def generate_signal(prices: list[float]) -> dict:
    """MACD 신호 생성.

    Returns:
        {"signal": BUY|SELL|HOLD, "reason", "macd", "signal_line", "histogram"}
    """
    base = {'signal': 'HOLD', 'reason': '', 'macd': 0.0, 'signal_line': 0.0, 'histogram': 0.0}

    if not prices or len(prices) < 35:
        return {**base, 'reason': '데이터 부족 (최소 35개 필요)'}

    res = calculate_macd(prices)
    if not res:
        return {**base, 'reason': 'MACD 계산 실패'}

    macd = res['macd']
    sig_line = res['signal']
    hist = res['histogram']
    hist_prev = res['_hist_prev']
    macd_prev = res['_macd_prev']
    sig_prev = res['_signal_prev']

    out = {'macd': macd, 'signal_line': sig_line, 'histogram': hist}

    # 골든크로스: MACD가 시그널선 상향 돌파 + 히스토그램 양전환
    golden_cross = macd_prev < sig_prev and macd >= sig_line
    dead_cross = macd_prev > sig_prev and macd <= sig_line
    hist_positive = hist > 0 and hist_prev <= 0

    if golden_cross and hist_positive:
        strength = '강화 ' if res['trend'] == 'BEARISH' else ''  # 제로선 아래 골든크로스
        return {'signal': 'BUY', 'reason': f'{strength}MACD 골든크로스 (hist={hist:.4f})', **out}
    if golden_cross:
        return {'signal': 'BUY', 'reason': f'MACD 골든크로스 신호 (hist={hist:.4f})', **out}

    if dead_cross:
        return {'signal': 'SELL', 'reason': f'MACD 데드크로스 (hist={hist:.4f})', **out}

    return {'signal': 'HOLD', 'reason': f'MACD 대기 중 (hist={hist:.4f})', **out}


class MACDStrategy(BaseStrategy):
    name = 'macd'
    description = 'MACD (추세 추종형)'

    KR_SYMBOLS = ['005930', '000660', '035420', '051910', '006400', '207940', '005380']
    US_SYMBOLS = [('AAPL', 'NAS'), ('MSFT', 'NAS'), ('NVDA', 'NAS'), ('GOOGL', 'NAS'), ('AMZN', 'NAS')]

    def run(self):
        self.log_signal("MACD 전략 실행 시작")
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
            return {item['pdno']: int(item.get('hldg_qty', 0)) for item in data.get('output1', [])}
        except Exception:
            return {}

    def _get_holdings_us(self) -> dict:
        try:
            data = self.kis.get_balance_us()
            return {item['ovrs_pdno']: int(item.get('ovrs_cblc_qty', 0)) for item in data.get('output1', [])}
        except Exception:
            return {}

    def _process_kr(self, symbol: str, holdings: dict):
        ohlcv = self.kis.get_daily_ohlcv_kr(symbol, period=60)
        if len(ohlcv) < 36:
            return
        closes = [float(row['stck_clpr']) for row in reversed(ohlcv)]
        self._execute(symbol, closes, holdings.get(symbol, 0), 'KR')

    def _process_us(self, symbol: str, excd: str, holdings: dict):
        ohlcv = self.kis.get_daily_ohlcv_us(symbol, excd, period=60)
        if len(ohlcv) < 36:
            return
        closes = [float(row.get('clos') or row.get('close', 0)) for row in reversed(ohlcv)]
        self._execute(symbol, closes, holdings.get(symbol, 0), 'US', excd)

    def _execute(self, symbol: str, closes: list, held_qty: int, market: str, excd: str = 'NAS'):
        sig = generate_signal(closes)
        price = closes[-1]

        if sig['signal'] == 'BUY' and held_qty == 0:
            if not self.check_daily_buy_limit():
                return
            if self.already_bought_today(symbol):
                return
            qty = self.screener_qty(price, market=market) or self._calc_qty(price, market)
            if qty > 0:
                self.log_signal(f"매수 {symbol} | {sig['reason']} | 가격={price}")
                try:
                    result = self.kis.order_with_retry(symbol, 'BUY', qty, price, market, excd)
                    self.record_trade(symbol, symbol, 'BUY', qty, price, result)
                except Exception as e:
                    self.record_trade(symbol, symbol, 'BUY', qty, price, error=str(e))

        elif sig['signal'] == 'SELL' and held_qty > 0:
            self.log_signal(f"매도 {symbol} | {sig['reason']} | 가격={price}")
            try:
                result = self.kis.order_with_retry(symbol, 'SELL', held_qty, price, market, excd)
                self.record_trade(symbol, symbol, 'SELL', held_qty, price, result)
            except Exception as e:
                self.record_trade(symbol, symbol, 'SELL', held_qty, price, error=str(e))

    def _calc_qty(self, price: float, market: str) -> int:
        limit = self.account.investment_limit
        if market == 'US':
            return max(0, int(limit / 1350 * 0.2 / price))
        return max(0, int(limit * 0.2 / price))


if __name__ == '__main__':
    import random
    rng = random.Random(7)

    # 상승 추세 → 골든크로스 유도
    prices = []
    p = 50000.0
    for i in range(60):
        p += rng.gauss(200, 800)
        prices.append(max(p, 1000.0))

    res = calculate_macd(prices)
    print(f"MACD={res['macd']:.2f} Signal={res['signal']:.2f} Hist={res['histogram']:.2f} Trend={res['trend']}")

    sig = generate_signal(prices)
    print(f"신호: {sig['signal']} | {sig['reason']}")

    # 데이터 부족
    s2 = generate_signal([100.0] * 10)
    print(f"데이터 부족: {s2['signal']} | {s2['reason']}")

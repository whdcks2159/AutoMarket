"""전략 5 — 볼린저 밴드 (국내주 변동성 추적형)
20일 이동평균 ± 2 표준편차로 상단/하단 밴드 계산
하단 밴드 터치/이탈 (%B < 0.05) → 매수
상단 밴드 터치/이탈 (%B > 0.95) → 매도
거래량 급증 시 신호 강도 상향
실행: 09:00 / 15:20
"""
import math
from typing import Optional
from .base import BaseStrategy


def calculate_bollinger_bands(
    prices: list[float],
    period: int = 20,
    std_dev: float = 2.0,
) -> Optional[dict]:
    """볼린저 밴드 계산.

    Returns:
        {"upper", "middle", "lower", "bandwidth", "pct_b"} or None
    """
    if len(prices) < period or period <= 0:
        return None

    recent = prices[-period:]
    middle = sum(recent) / period
    variance = sum((p - middle) ** 2 for p in recent) / period
    std = math.sqrt(variance) if variance > 0 else 0.0

    upper = middle + std_dev * std
    lower = middle - std_dev * std
    bandwidth = (upper - lower) / middle if middle > 0 else 0.0
    band_range = upper - lower
    current = prices[-1]
    pct_b = (current - lower) / band_range if band_range > 0 else 0.5

    return {
        'upper': round(upper, 2),
        'middle': round(middle, 2),
        'lower': round(lower, 2),
        'bandwidth': round(bandwidth, 4),
        'pct_b': round(pct_b, 4),
    }


def generate_signal(
    prices: list[float],
    volumes: Optional[list[int]] = None,
) -> dict:
    """볼린저 밴드 신호 생성.

    Returns:
        {"signal": BUY|SELL|HOLD, "reason", "upper", "middle", "lower", "pct_b"}
    """
    base = {'signal': 'HOLD', 'reason': '', 'upper': 0.0, 'middle': 0.0, 'lower': 0.0, 'pct_b': 0.5}

    if not prices or len(prices) < 20:
        return {**base, 'reason': '데이터 부족 (최소 20개 필요)'}

    bands = calculate_bollinger_bands(prices)
    if not bands:
        return {**base, 'reason': '밴드 계산 실패'}

    pct_b = bands['pct_b']

    volume_surge = False
    if volumes and len(volumes) >= 20:
        recent_vols = [v for v in volumes[-20:-1] if v and v > 0]
        if recent_vols:
            avg_vol = sum(recent_vols) / len(recent_vols)
            volume_surge = avg_vol > 0 and (volumes[-1] or 0) > avg_vol * 2.0

    surge_str = ' + 거래량 급증' if volume_surge else ''

    if pct_b < 0:
        return {'signal': 'BUY', 'reason': f'하단 밴드 이탈 (%B={pct_b:.3f}){surge_str}', **bands}
    if pct_b < 0.05:
        return {'signal': 'BUY', 'reason': f'하단 밴드 근접 (%B={pct_b:.3f}){surge_str}', **bands}
    if pct_b > 1.0:
        return {'signal': 'SELL', 'reason': f'상단 밴드 이탈 (%B={pct_b:.3f})', **bands}
    if pct_b > 0.95:
        return {'signal': 'SELL', 'reason': f'상단 밴드 근접 (%B={pct_b:.3f})', **bands}
    return {'signal': 'HOLD', 'reason': f'밴드 중립 (%B={pct_b:.3f})', **bands}


class BollingerBandStrategy(BaseStrategy):
    name = 'bollinger_band'
    description = '볼린저 밴드 (변동성 추적형)'

    SYMBOLS = ['005930', '000660', '035420', '051910', '006400', '207940', '003550']

    def run(self):
        self.log_signal("볼린저 밴드 전략 실행 시작")
        holdings = self._get_holdings()
        symbols = self.get_scan_symbols_kr(self.SYMBOLS)

        for symbol in symbols:
            try:
                self._process(symbol, holdings)
            except Exception as e:
                self.log_signal(f"{symbol} 처리 오류: {e}", event_type='ERROR')

    def _get_holdings(self) -> dict:
        try:
            data = self.kis.get_balance_kr()
            return {item['pdno']: int(item.get('hldg_qty', 0)) for item in data.get('output1', [])}
        except Exception as e:
            self.log_signal(f"잔고 조회 실패: {e}", event_type='ERROR')
            return {}

    def _process(self, symbol: str, holdings: dict):
        ohlcv = self.kis.get_daily_ohlcv_kr(symbol, period=30)
        if len(ohlcv) < 21:
            return

        closes: list[float] = []
        volumes: list[int] = []
        for row in reversed(ohlcv):
            try:
                closes.append(float(row['stck_clpr']))
                volumes.append(int(row.get('acml_vol', 0) or 0))
            except (KeyError, ValueError, TypeError):
                pass

        if len(closes) < 20:
            return

        sig = generate_signal(closes, volumes)
        current_price = closes[-1]
        held_qty = holdings.get(symbol, 0)

        if sig['signal'] == 'BUY' and held_qty == 0:
            if not self.check_daily_buy_limit():
                self.log_signal(f"일일 매수 한도 초과 — {symbol} 스킵")
                return
            if self.already_bought_today(symbol):
                return
            qty = self.screener_qty(current_price) or self._calc_qty(current_price)
            if qty > 0:
                self.log_signal(f"매수 {symbol} | {sig['reason']} | 가격={current_price:,.0f}")
                try:
                    result = self.kis.order_with_retry(symbol, 'BUY', qty, current_price, 'KR')
                    self.record_trade(symbol, symbol, 'BUY', qty, current_price, result)
                except Exception as e:
                    self.record_trade(symbol, symbol, 'BUY', qty, current_price, error=str(e))

        elif sig['signal'] == 'SELL' and held_qty > 0:
            self.log_signal(f"매도 {symbol} | {sig['reason']} | 가격={current_price:,.0f}")
            try:
                result = self.kis.order_with_retry(symbol, 'SELL', held_qty, current_price, 'KR')
                self.record_trade(symbol, symbol, 'SELL', held_qty, current_price, result)
            except Exception as e:
                self.record_trade(symbol, symbol, 'SELL', held_qty, current_price, error=str(e))

    def _calc_qty(self, price: float) -> int:
        return max(0, int(self.account.investment_limit * 0.2 / price))


if __name__ == '__main__':
    import random
    rng = random.Random(42)

    prices = [50000 + rng.gauss(0, 1500) for _ in range(30)]
    sig = generate_signal(prices)
    print(f"[일반] {sig['signal']} | {sig['reason']} | %B={sig['pct_b']:.3f}")

    # 하단 이탈
    low = [50000.0] * 20 + [43000.0]
    s2 = generate_signal(low)
    print(f"[하단이탈] {s2['signal']} | %B={s2['pct_b']:.3f}")

    # 상단 이탈
    high = [50000.0] * 20 + [58000.0]
    s3 = generate_signal(high)
    print(f"[상단이탈] {s3['signal']} | %B={s3['pct_b']:.3f}")

    # 데이터 부족
    s4 = generate_signal([100.0, 200.0])
    print(f"[데이터부족] {s4['signal']} | {s4['reason']}")

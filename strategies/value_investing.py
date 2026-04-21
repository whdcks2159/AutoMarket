"""전략 7 — PER/PBR 가치투자 (국내주 월간 리밸런싱)
PER 10 이하 + PBR 1.0 이하 + ROE 10% 이상 → 저평가 매수 대상
목표가 = BPS × 적정 PBR(1.5)
손절: 매수가 대비 -15%
매월 첫 거래일 스크리닝 후 리밸런싱

KIS API 재무 데이터 조회 방법:
  - PER/PBR: FHKST01010100 (현재가 조회) output.per, output.pbr
  - BPS:      FHKST01010100 output.bps
  - ROE는 직접 제공되지 않아 EPS/BPS로 근사:
      ROE ≈ (EPS / BPS) × 100  (eps: output.eps, bps: output.bps)
실행: 매월 첫 거래일 08:50
"""
from typing import Optional
from .base import BaseStrategy

# 전통적 저PBR 가치주 후보 (기본 watchlist - 스크리너 미사용 시)
VALUE_SYMBOLS = [
    '005490',  # POSCO홀딩스
    '055550',  # 신한지주
    '105560',  # KB금융
    '086790',  # 하나금융지주
    '000270',  # 기아
    '005380',  # 현대차
    '010950',  # S-Oil
    '096770',  # SK이노베이션
    '003490',  # 대한항공
    '006800',  # 미래에셋증권
]

PER_THRESHOLD = 10.0
PBR_BUY_THRESHOLD = 1.0
PBR_SELL_THRESHOLD = 1.5   # 목표가 도달 PBR
ROE_THRESHOLD = 10.0
STOP_LOSS_RATE = 0.15       # 15% 손절


def calculate_intrinsic_value(bps: float, target_pbr: float = 1.5) -> float:
    """내재가치 = BPS × 적정 PBR."""
    if bps <= 0 or target_pbr <= 0:
        return 0.0
    return round(bps * target_pbr, 2)


def is_undervalued(per: float, pbr: float, roe: float) -> bool:
    """저평가 여부 판단."""
    if per <= 0 or pbr <= 0:
        return False
    return per <= PER_THRESHOLD and pbr <= PBR_BUY_THRESHOLD and roe >= ROE_THRESHOLD


def generate_signal(
    current_price: float,
    per: float,
    pbr: float,
    roe: float,
    bps: float,
    holding: bool = False,
    buy_price: Optional[float] = None,
) -> dict:
    """가치투자 신호 생성.

    Returns:
        {"signal": BUY|SELL|HOLD, "reason", "intrinsic_value",
         "upside_pct", "per", "pbr", "roe"}
    """
    intrinsic = calculate_intrinsic_value(bps)
    upside = (intrinsic - current_price) / current_price * 100 if current_price > 0 else 0.0

    base = {
        'intrinsic_value': intrinsic,
        'upside_pct': round(upside, 2),
        'per': per,
        'pbr': pbr,
        'roe': roe,
    }

    # 0 나누기 및 None 방지
    if current_price <= 0:
        return {'signal': 'HOLD', 'reason': '현재가 조회 불가', **base}

    # 보유 중 손절 체크
    if holding and buy_price and buy_price > 0:
        loss_rate = (current_price - buy_price) / buy_price
        if loss_rate <= -STOP_LOSS_RATE:
            return {'signal': 'SELL',
                    'reason': f'손절가 도달 ({loss_rate:.1%} / 기준 -{STOP_LOSS_RATE:.0%})',
                    **base}

    # 보유 중 목표가 도달 (PBR >= 1.5)
    if holding and pbr >= PBR_SELL_THRESHOLD:
        return {'signal': 'SELL',
                'reason': f'목표 PBR 도달 (PBR={pbr:.2f} >= {PBR_SELL_THRESHOLD})',
                **base}

    # 매수 조건
    if not holding and is_undervalued(per, pbr, roe):
        return {'signal': 'BUY',
                'reason': (f'저평가 매수 조건 충족 '
                           f'(PER={per:.1f}, PBR={pbr:.2f}, ROE={roe:.1f}%, '
                           f'목표가={intrinsic:,.0f})'),
                **base}

    return {'signal': 'HOLD',
            'reason': f'조건 미충족 (PER={per:.1f}, PBR={pbr:.2f}, ROE={roe:.1f}%)',
            **base}


class ValueInvestingStrategy(BaseStrategy):
    name = 'value_investing'
    description = 'PER/PBR 가치투자 (월간 리밸런싱)'

    def run(self):
        self.log_signal("가치투자 전략 실행 시작")
        holdings = self._get_holdings()
        symbols = self.get_scan_symbols_kr(VALUE_SYMBOLS)

        for symbol in symbols:
            try:
                self._process(symbol, holdings)
            except Exception as e:
                self.log_signal(f"{symbol} 처리 오류: {e}", event_type='ERROR')

    def _get_holdings(self) -> dict:
        try:
            data = self.kis.get_balance_kr()
            result = {}
            for item in data.get('output1', []):
                sym = item['pdno']
                result[sym] = {
                    'qty': int(item.get('hldg_qty', 0)),
                    'avg_price': float(item.get('pchs_avg_pric', 0)),
                }
            return result
        except Exception as e:
            self.log_signal(f"잔고 조회 실패: {e}", event_type='ERROR')
            return {}

    def _process(self, symbol: str, holdings: dict):
        # KIS API: 현재가 조회 (output.per, output.pbr, output.bps, output.eps 포함)
        try:
            price_data = self.kis.get_price_kr(symbol)
            output = price_data.get('output', {})
        except Exception as e:
            self.log_signal(f"{symbol} 현재가 조회 실패: {e}", event_type='ERROR')
            return

        try:
            current_price = float(output.get('stck_prpr', 0) or 0)
            per = float(output.get('per', 0) or 0)
            pbr = float(output.get('pbr', 0) or 0)
            bps = float(output.get('bps', 0) or 0)
            eps = float(output.get('eps', 0) or 0)
            # ROE ≈ EPS / BPS × 100 (KIS API에서 ROE 직접 미제공)
            roe = (eps / bps * 100) if bps > 0 else 0.0
        except (ValueError, TypeError):
            return

        if current_price <= 0:
            return

        holding_info = holdings.get(symbol)
        is_holding = bool(holding_info and holding_info.get('qty', 0) > 0)
        buy_price = holding_info.get('avg_price') if holding_info else None
        held_qty = holding_info.get('qty', 0) if holding_info else 0

        sig = generate_signal(current_price, per, pbr, roe, bps, is_holding, buy_price)

        if sig['signal'] == 'BUY' and not is_holding:
            if not self.check_daily_buy_limit():
                self.log_signal(f"일일 매수 한도 초과 — {symbol} 스킵")
                return
            if self.already_bought_today(symbol):
                return
            qty = self.screener_qty(current_price) or self._calc_qty(current_price, 'KR', 0.15)
            if qty > 0:
                self.log_signal(f"매수 {symbol} | {sig['reason']}")
                try:
                    result = self.kis.order_with_retry(symbol, 'BUY', qty, current_price, 'KR')
                    self.record_trade(symbol, symbol, 'BUY', qty, current_price, result)
                except Exception as e:
                    self.record_trade(symbol, symbol, 'BUY', qty, current_price, error=str(e))

        elif sig['signal'] == 'SELL' and is_holding and held_qty > 0:
            self.log_signal(f"매도 {symbol} | {sig['reason']}")
            try:
                result = self.kis.order_with_retry(symbol, 'SELL', held_qty, current_price, 'KR')
                self.record_trade(symbol, symbol, 'SELL', held_qty, current_price, result)
            except Exception as e:
                self.record_trade(symbol, symbol, 'SELL', held_qty, current_price, error=str(e))



if __name__ == '__main__':
    # 저평가 매수 케이스
    s1 = generate_signal(current_price=10000, per=8.0, pbr=0.7, roe=12.0, bps=15000)
    print(f"[저평가] {s1['signal']} | {s1['reason']}")
    print(f"  내재가치={s1['intrinsic_value']:,.0f} | 상승여력={s1['upside_pct']:.1f}%")

    # 목표가 도달 → 매도
    s2 = generate_signal(current_price=22000, per=15.0, pbr=1.6, roe=12.0,
                         bps=15000, holding=True, buy_price=10000)
    print(f"[목표도달] {s2['signal']} | {s2['reason']}")

    # 손절
    s3 = generate_signal(current_price=8400, per=8.0, pbr=0.6, roe=11.0,
                         bps=15000, holding=True, buy_price=10000)
    print(f"[손절] {s3['signal']} | {s3['reason']}")

    # 조건 미충족
    s4 = generate_signal(current_price=50000, per=25.0, pbr=3.0, roe=5.0, bps=20000)
    print(f"[미충족] {s4['signal']} | {s4['reason']}")

    # 엣지케이스: 현재가 0
    s5 = generate_signal(current_price=0, per=8.0, pbr=0.7, roe=12.0, bps=15000)
    print(f"[현재가0] {s5['signal']} | {s5['reason']}")

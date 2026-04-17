"""전략 2 — 듀얼 모멘텀 (미국주 중립형)
매월 첫 거래일 리밸런싱
상대 모멘텀: 등록 종목 중 90일 수익률 1위 선택
절대 모멘텀: 무위험 수익률(월 0.4%) 초과 시 매수
실행: 매월 첫 거래일 23:30 KST
"""
from .base import BaseStrategy


class DualMomentumStrategy(BaseStrategy):
    name = 'dual_momentum'
    description = '듀얼 모멘텀 (미국 중립형)'

    SYMBOLS = [
        ('SPY', 'NYS'), ('QQQ', 'NAS'), ('IWM', 'NYS'),
        ('EFA', 'NYS'), ('GLD', 'NYS'),
    ]
    RISK_FREE_MONTHLY = 0.004  # 무위험 수익률 월 0.4%

    def run(self):
        self.log_signal("듀얼 모멘텀 리밸런싱 시작")
        momentum_scores = {}

        for symbol, excd in self.SYMBOLS:
            try:
                score = self._calc_momentum(symbol, excd)
                if score is not None:
                    momentum_scores[symbol] = (score, excd)
                    self.log_signal(f"{symbol} 90일 수익률: {score:.2%}")
            except Exception as e:
                self.log_signal(f"{symbol} 모멘텀 계산 오류: {e}", event_type='ERROR')

        if not momentum_scores:
            self.log_signal("모멘텀 계산 불가 — 리밸런싱 스킵", event_type='ERROR')
            return

        best_symbol = max(momentum_scores, key=lambda s: momentum_scores[s][0])
        best_score, best_excd = momentum_scores[best_symbol]

        holdings = self._get_holdings_us()

        # 절대 모멘텀: 무위험 수익률(3개월) 초과 여부
        min_score = self.RISK_FREE_MONTHLY * 3
        if best_score > min_score:
            self._rebalance_to(best_symbol, best_excd, holdings)
        else:
            self.log_signal(f"절대 모멘텀 미충족({best_score:.2%} < {min_score:.2%}) — 전량 매도 후 현금 보유")
            self._sell_all(holdings)

    def _calc_momentum(self, symbol: str, excd: str) -> float | None:
        ohlcv = self.kis.get_daily_ohlcv_us(symbol, excd, period=100)
        if len(ohlcv) < 90:
            return None
        closes = [float(row['clos']) for row in reversed(ohlcv) if row.get('clos')]
        if len(closes) < 90 or closes[-90] == 0:
            return None
        return (closes[-1] - closes[-90]) / closes[-90]

    def _get_holdings_us(self) -> dict:
        try:
            data = self.kis.get_balance_us()
            output1 = data.get('output1', [])
            return {item['ovrs_pdno']: int(item.get('ovrs_cblc_qty', 0)) for item in output1}
        except Exception as e:
            self.log_signal(f"미국 잔고 조회 실패: {e}", event_type='ERROR')
            return {}

    def _rebalance_to(self, target: str, excd: str, holdings: dict):
        for symbol, qty in holdings.items():
            if symbol != target and qty > 0:
                self.log_signal(f"매도: {symbol} {qty}주")
                try:
                    price_data = self.kis.get_price_us(symbol, excd)
                    price = float(price_data['output']['last'])
                    result = self.kis.order_with_retry(symbol, 'SELL', qty, price, 'US', excd)
                    self.record_trade(symbol, symbol, 'SELL', qty, price, result)
                except Exception as e:
                    self.log_signal(f"{symbol} 매도 오류: {e}", event_type='ERROR')

        if holdings.get(target, 0) == 0:
            try:
                price_data = self.kis.get_price_us(target, excd)
                price = float(price_data['output']['last'])
                qty = int(self.account.investment_limit / price / 1350)  # KRW→USD 환산
                if qty > 0:
                    self.log_signal(f"매수: {target} {qty}주 @ ${price}")
                    result = self.kis.order_with_retry(target, 'BUY', qty, price, 'US', excd)
                    self.record_trade(target, target, 'BUY', qty, price, result)
            except Exception as e:
                self.log_signal(f"{target} 매수 오류: {e}", event_type='ERROR')

    def _sell_all(self, holdings: dict):
        for symbol, qty in holdings.items():
            if qty > 0:
                try:
                    price_data = self.kis.get_price_us(symbol)
                    price = float(price_data['output']['last'])
                    result = self.kis.order_with_retry(symbol, 'SELL', qty, price, 'US')
                    self.record_trade(symbol, symbol, 'SELL', qty, price, result)
                except Exception as e:
                    self.log_signal(f"{symbol} 전량 매도 오류: {e}", event_type='ERROR')

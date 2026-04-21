"""미국주 스크리너 — S&P500/NASDAQ100 종목 대상 전략별 신호 탐색"""
import time
import logging
import pytz
from datetime import datetime

_KST = pytz.timezone('Asia/Seoul')


def _now_kst() -> datetime:
    return datetime.now(_KST).replace(tzinfo=None)

logger = logging.getLogger(__name__)

MIN_PRICE_USD = 10.0    # 최소 주가 $10
MIN_VOLUME_US = 1_000_000  # 일평균 거래량 100만주 (mock에서는 미적용)


class USScreener:
    def __init__(self, account, kis_client):
        self.account = account
        self.kis = kis_client

    # ─── Public: 전략별 스캔 ────────────────────────────────────────────────────

    def scan_dual_momentum(self, top_n: int = None) -> list:
        """듀얼 모멘텀 — 90일 수익률 상위 top_n 종목 반환 [(ticker, exchange)]."""
        top_n = top_n or getattr(self.account, 'screener_max_symbols', 3)
        symbol_pairs = self._get_universe()
        scores = []

        for symbol, excd in symbol_pairs:
            try:
                score = self._calc_momentum(symbol, excd)
                if score is not None and score > 0.012:  # 무위험 수익률 3개월분 초과
                    scores.append({'symbol': symbol, 'excd': excd, 'score': score})
                time.sleep(1.0)
            except Exception as e:
                logger.warning("dual_momentum scan %s: %s", symbol, e)

        scores.sort(key=lambda x: x['score'], reverse=True)
        selected = scores[:top_n]
        self._save_results(
            selected,
            strategy='dual_momentum',
            make_reason=lambda r: f"90일 수익률 {r['score']:.2%}",
            make_ticker=lambda r: f"{r['symbol']}|{r['excd']}",
        )
        logger.info("듀얼 모멘텀 스캔: %d/%d 종목 선별", len(selected), len(symbol_pairs))
        return [(r['symbol'], r['excd']) for r in selected]

    def scan_week52_high(self, top_n: int = None) -> list:
        """52주 신고가 돌파 종목 탐색 → 돌파 강도 상위 top_n 반환."""
        top_n = top_n or getattr(self.account, 'screener_max_symbols', 3)
        symbol_pairs = self._get_universe()
        results = []

        for symbol, excd in symbol_pairs:
            try:
                signal = self._check_week52_high(symbol, excd)
                if signal:
                    results.append({'symbol': symbol, 'excd': excd, **signal})
                time.sleep(1.0)
            except Exception as e:
                logger.warning("week52 scan %s: %s", symbol, e)

        results.sort(key=lambda x: x.get('breakout_strength', 0), reverse=True)
        selected = results[:top_n]
        self._save_results(
            selected,
            strategy='week52_high',
            make_reason=lambda r: r.get('reason', ''),
            make_ticker=lambda r: f"{r['symbol']}|{r['excd']}",
        )
        logger.info("52주 신고가 스캔(US): %d/%d 신호", len(selected), len(symbol_pairs))
        return [(r['symbol'], r['excd']) for r in selected]

    def scan_volatility_breakout(self, top_n: int = None) -> list:
        """변동성 돌파 — S&P500 대상, 목표가 돌파 종목 반환."""
        top_n = top_n or getattr(self.account, 'screener_max_symbols', 5)
        symbol_pairs = self._get_universe()
        results = []

        for symbol, excd in symbol_pairs:
            try:
                signal = self._check_volatility_breakout(symbol, excd)
                if signal:
                    results.append({'symbol': symbol, 'excd': excd, **signal})
                time.sleep(1.0)
            except Exception as e:
                logger.warning("volatility scan %s: %s", symbol, e)

        results.sort(key=lambda x: x.get('breakout_pct', 0), reverse=True)
        selected = results[:top_n]
        self._save_results(
            selected,
            strategy='volatility_breakout',
            make_reason=lambda r: r.get('reason', ''),
            make_ticker=lambda r: f"{r['symbol']}|{r['excd']}",
        )
        logger.info("변동성 돌파 스캔(US): %d/%d 신호", len(selected), len(symbol_pairs))
        return [(r['symbol'], r['excd']) for r in selected]

    # ─── 유니버스 선택 ──────────────────────────────────────────────────────────

    def _get_universe(self) -> list:
        """screener_targets에 따라 종목 유니버스 반환."""
        from screener.sp500_list import SP500_SYMBOLS, NASDAQ100_SYMBOLS
        targets = (getattr(self.account, 'screener_targets', None) or 'SP500').split(',')
        universe = []
        seen = set()

        for t in targets:
            t = t.strip()
            if t == 'SP500':
                source = SP500_SYMBOLS
            elif t == 'NASDAQ100':
                source = NASDAQ100_SYMBOLS
            else:
                continue
            for pair in source:
                if pair[0] not in seen:
                    universe.append(pair)
                    seen.add(pair[0])

        return universe

    # ─── 신호 체크 ──────────────────────────────────────────────────────────────

    def _calc_momentum(self, symbol: str, excd: str) -> float | None:
        ohlcv = self.kis.get_daily_ohlcv_us(symbol, excd, period=100)
        if len(ohlcv) < 90:
            return None
        closes = []
        for row in reversed(ohlcv):
            try:
                v = row.get('clos') or row.get('close')
                if v:
                    closes.append(float(v))
            except (ValueError, TypeError):
                pass
        if len(closes) < 90 or closes[-90] == 0:
            return None
        return (closes[-1] - closes[-90]) / closes[-90]

    def _check_week52_high(self, symbol: str, excd: str) -> dict | None:
        ohlcv = self.kis.get_daily_ohlcv_us(symbol, excd, period=260)
        if len(ohlcv) < 60:
            return None

        closes, highs = [], []
        for row in reversed(ohlcv):
            try:
                c = row.get('clos') or row.get('close')
                h = row.get('high')
                if c:
                    closes.append(float(c))
                if h:
                    highs.append(float(h))
            except (ValueError, TypeError):
                pass

        if len(closes) < 60 or len(highs) < 60:
            return None

        current = closes[-1]
        if current < MIN_PRICE_USD:
            return None

        week52_high = max(highs[-252:]) if len(highs) >= 252 else max(highs)
        if current > week52_high * 0.999 and week52_high > 0:
            strength = (current - week52_high) / week52_high
            return {
                'signal': 'BUY',
                'reason': f'52주 신고가 돌파 (${current:.2f} >= ${week52_high:.2f})',
                'breakout_strength': strength,
            }
        return None

    def _check_volatility_breakout(self, symbol: str, excd: str) -> dict | None:
        ohlcv = self.kis.get_daily_ohlcv_us(symbol, excd, period=5)
        if len(ohlcv) < 2:
            return None

        rows = list(reversed(ohlcv))
        try:
            today_open = float(rows[-1].get('open', 0) or 0)
            prev_high = float(rows[-2].get('high', 0) or 0)
            prev_low = float(rows[-2].get('low', 0) or 0)
            prev_close = float(rows[-2].get('clos', 0) or rows[-2].get('close', 0) or 0)
        except (ValueError, TypeError):
            return None

        if today_open < MIN_PRICE_USD or prev_close == 0:
            return None

        gap_rate = (today_open - prev_close) / prev_close
        if gap_rate > 0.03:
            return None

        target = today_open + (prev_high - prev_low) * 0.5
        try:
            price_data = self.kis.get_price_us(symbol, excd)
            current = float(price_data['output']['last'])
        except (KeyError, ValueError, TypeError):
            return None

        if current >= target:
            breakout_pct = (current - target) / target if target else 0
            return {
                'signal': 'BUY',
                'reason': f'변동성 돌파 (${current:.2f} >= 목표 ${target:.2f})',
                'breakout_pct': breakout_pct,
            }
        return None

    # ─── DB 저장 ────────────────────────────────────────────────────────────────

    def _save_results(self, results: list, strategy: str,
                      make_reason, make_ticker):
        try:
            from models import db, ScanResult, WatchList
            now = _now_kst()
            for r in results:
                ticker_str = make_ticker(r)
                scan = ScanResult(
                    user_id=self.account.user_id,
                    account_id=self.account.id,
                    strategy=strategy,
                    ticker=ticker_str,
                    ticker_name=r.get('name', ''),
                    signal=r.get('signal', 'BUY'),
                    reason=make_reason(r),
                    scanned_at=now,
                )
                db.session.add(scan)

                base_ticker = ticker_str.split('|')[0]
                exists = WatchList.query.filter_by(
                    user_id=self.account.user_id,
                    ticker=base_ticker,
                    market='US',
                ).first()
                if not exists:
                    db.session.add(WatchList(
                        user_id=self.account.user_id,
                        ticker=base_ticker,
                        market='US',
                        added_by='auto',
                    ))
            db.session.commit()
        except Exception as e:
            logger.error("us_screener save_results error: %s", e)
            try:
                from models import db
                db.session.rollback()
            except Exception:
                pass

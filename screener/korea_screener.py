"""국내주 스크리너 — 코스피/코스닥 전체 종목 대상 전략별 신호 탐색"""
import time
import logging
import pytz
from datetime import datetime, date

_KST = pytz.timezone('Asia/Seoul')


def _now_kst() -> datetime:
    return datetime.now(_KST).replace(tzinfo=None)

logger = logging.getLogger(__name__)

MIN_VOLUME = 100_000   # 최소 거래량 10만주
MIN_MKTCAP = 500       # 최소 시가총액 500억 (단위: 억원)
SKIP_STATUS = {'55', '56', '57', '58', '59', '61', '62', '63'}  # 상한/하한/관리/정지


class KoreaScreener:
    def __init__(self, account, kis_client):
        self.account = account
        self.kis = kis_client

    # ─── Public: 전략별 스캔 ────────────────────────────────────────────────────

    def scan_golden_rsi(self, top_n: int = None) -> list:
        """골든크로스+RSI 신호 종목 탐색 → 거래량 상위 top_n 반환."""
        top_n = top_n or getattr(self.account, 'screener_max_symbols', 5)
        candidates = self._get_candidates()
        results = []

        for item in candidates:
            symbol = item['symbol']
            try:
                signal = self._check_golden_rsi(symbol)
                if signal:
                    results.append({**item, **signal})
                time.sleep(0.06)  # API 초당 ~16회 이하
            except Exception as e:
                logger.warning("golden_rsi scan %s: %s", symbol, e)

        results.sort(key=lambda x: x.get('volume', 0), reverse=True)
        selected = results[:top_n]
        self._save_results(selected, 'golden_rsi')
        logger.info("골든RSI 스캔 완료: %d/%d 신호 발생", len(selected), len(candidates))
        return [r['symbol'] for r in selected]

    def scan_week52_high(self, top_n: int = None) -> list:
        """52주 신고가 돌파 종목 탐색 → 돌파 강도 상위 top_n 반환."""
        top_n = top_n or getattr(self.account, 'screener_max_symbols', 3)
        candidates = self._get_candidates()
        results = []

        for item in candidates:
            symbol = item['symbol']
            try:
                signal = self._check_week52_high(symbol)
                if signal:
                    results.append({**item, **signal})
                time.sleep(0.06)
            except Exception as e:
                logger.warning("week52 scan %s: %s", symbol, e)

        results.sort(key=lambda x: x.get('breakout_strength', 0), reverse=True)
        selected = results[:top_n]
        self._save_results(selected, 'week52_high')
        logger.info("52주 신고가 스캔 완료: %d/%d 신호 발생", len(selected), len(candidates))
        return [r['symbol'] for r in selected]

    def scan_volatility_breakout(self, top_n: int = None) -> list:
        """변동성 돌파 목표가 돌파 종목 탐색 — KOSPI200 대상."""
        top_n = top_n or getattr(self.account, 'screener_max_symbols', 5)
        from screener.sp500_list import KOSPI200_SYMBOLS
        candidates = self._get_candidates(symbols_override=KOSPI200_SYMBOLS)
        results = []

        for item in candidates:
            symbol = item['symbol']
            try:
                signal = self._check_volatility_breakout(symbol)
                if signal:
                    results.append({**item, **signal})
                time.sleep(0.06)
            except Exception as e:
                logger.warning("volatility scan %s: %s", symbol, e)

        results.sort(key=lambda x: x.get('volume', 0), reverse=True)
        selected = results[:top_n]
        self._save_results(selected, 'volatility_breakout')
        logger.info("변동성 돌파 스캔 완료: %d/%d 신호 발생", len(selected), len(candidates))
        return [r['symbol'] for r in selected]

    # ─── 후보 종목 조회 ─────────────────────────────────────────────────────────

    def _get_candidates(self, symbols_override=None) -> list:
        """거래량 순위 API로 후보 종목 수집 후 1차 필터 적용."""
        if symbols_override:
            # 직접 지정 종목 목록 — 추가 필터 없이 통과
            return [{'symbol': s, 'volume': 0, 'mktcap': 9999, 'name': s}
                    for s in symbols_override]

        targets = (getattr(self.account, 'screener_targets', None) or 'KOSPI,KOSDAQ').split(',')
        candidates = []
        seen = set()

        for market in targets:
            market = market.strip()
            market_div = 'Q' if market == 'KOSDAQ' else 'J'
            try:
                stocks = self.kis.get_volume_rank_kr(market_div)
                for s in stocks:
                    symbol = (s.get('mksc_shrn_iscd') or s.get('stck_shrn_iscd', '')).strip()
                    if not symbol or symbol in seen:
                        continue

                    # 상한가/하한가/관리/정지 제외
                    status = s.get('iscd_stat_cls_code', '00')
                    if status in SKIP_STATUS:
                        continue

                    try:
                        volume = int(s.get('acml_vol', 0))
                        mktcap = float(s.get('hts_avls', 0))
                    except (ValueError, TypeError):
                        continue

                    if volume < MIN_VOLUME or mktcap < MIN_MKTCAP:
                        continue

                    seen.add(symbol)
                    candidates.append({
                        'symbol': symbol,
                        'name': s.get('hts_kor_isnm', symbol),
                        'volume': volume,
                        'mktcap': mktcap,
                    })
            except Exception as e:
                logger.warning("get_candidates %s: %s", market, e)

        return candidates

    # ─── 신호 체크 ──────────────────────────────────────────────────────────────

    def _check_golden_rsi(self, symbol: str) -> dict | None:
        from strategies.base import BaseStrategy
        ohlcv = self.kis.get_daily_ohlcv_kr(symbol, period=30)
        if len(ohlcv) < 21:
            return None

        closes = []
        for row in reversed(ohlcv):
            try:
                closes.append(float(row['stck_clpr']))
            except (KeyError, ValueError, TypeError):
                pass

        if len(closes) < 21:
            return None

        sma5 = BaseStrategy.calc_sma(closes, 5)
        sma20 = BaseStrategy.calc_sma(closes, 20)
        rsi = BaseStrategy.calc_rsi(closes, 14)

        if sma5 > sma20 and rsi < 70:
            return {'signal': 'BUY', 'reason': f'골든크로스+RSI({rsi:.1f})'}
        if rsi < 30 and sma5 > sma20:
            return {'signal': 'BUY', 'reason': f'RSI과매도({rsi:.1f})+골든크로스'}
        return None

    def _check_week52_high(self, symbol: str) -> dict | None:
        from strategies.base import BaseStrategy
        ohlcv = self.kis.get_daily_ohlcv_kr(symbol, period=260)
        if len(ohlcv) < 60:
            return None

        closes, highs = [], []
        for row in reversed(ohlcv):
            try:
                closes.append(float(row['stck_clpr']))
                highs.append(float(row['stck_hgpr']))
            except (KeyError, ValueError, TypeError):
                pass

        if len(closes) < 60 or len(highs) < 60:
            return None

        current = closes[-1]
        week52_high = max(highs[-252:]) if len(highs) >= 252 else max(highs)

        if current > week52_high * 0.999 and week52_high > 0:
            strength = (current - week52_high) / week52_high if week52_high else 0
            return {
                'signal': 'BUY',
                'reason': f'52주 신고가 돌파 ({current:,.0f} >= {week52_high:,.0f})',
                'breakout_strength': strength,
            }
        return None

    def _check_volatility_breakout(self, symbol: str) -> dict | None:
        ohlcv = self.kis.get_daily_ohlcv_kr(symbol, period=5)
        if len(ohlcv) < 2:
            return None

        rows = list(reversed(ohlcv))
        try:
            today_open = float(rows[-1].get('stck_oprc', 0) or 0)
            prev_high = float(rows[-2].get('stck_hgpr', 0) or 0)
            prev_low = float(rows[-2].get('stck_lwpr', 0) or 0)
            prev_close = float(rows[-2].get('stck_clpr', 0) or 0)
        except (ValueError, TypeError):
            return None

        if today_open == 0 or prev_close == 0:
            return None

        gap_rate = (today_open - prev_close) / prev_close
        if gap_rate > 0.03:
            return None

        k = 0.5
        target_price = today_open + (prev_high - prev_low) * k

        try:
            price_data = self.kis.get_price_kr(symbol)
            current = float(price_data['output']['stck_prpr'])
        except (KeyError, ValueError, TypeError):
            return None

        if current >= target_price:
            return {
                'signal': 'BUY',
                'reason': f'변동성 돌파 ({current:,.0f} >= 목표 {target_price:,.0f})',
            }
        return None

    # ─── DB 저장 ────────────────────────────────────────────────────────────────

    def _save_results(self, results: list, strategy: str):
        try:
            from models import db, ScanResult, WatchList
            now = _now_kst()
            for r in results:
                scan = ScanResult(
                    user_id=self.account.user_id,
                    account_id=self.account.id,
                    strategy=strategy,
                    ticker=r['symbol'],
                    signal=r.get('signal', 'BUY'),
                    reason=r.get('reason', ''),
                    scanned_at=now,
                )
                db.session.add(scan)

                # WatchList 중복 방지
                exists = WatchList.query.filter_by(
                    user_id=self.account.user_id,
                    ticker=r['symbol'],
                    market='KR',
                ).first()
                if not exists:
                    db.session.add(WatchList(
                        user_id=self.account.user_id,
                        ticker=r['symbol'],
                        market='KR',
                        added_by='auto',
                    ))
            db.session.commit()
        except Exception as e:
            logger.error("save_results error: %s", e)
            try:
                from models import db
                db.session.rollback()
            except Exception:
                pass

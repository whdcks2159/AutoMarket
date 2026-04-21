import os
import json
import base64
import hashlib
import logging
import time
import requests
from datetime import datetime, timedelta
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.backends import default_backend

from config import Config

logger = logging.getLogger(__name__)


def _raise_for_status(resp):
    if not resp.ok:
        body = resp.text[:300]
        logger.error("KIS API 오류 %s %s → %s: %s",
                     resp.request.method, resp.url, resp.status_code, body)
        raise requests.HTTPError(
            f"{resp.status_code} {resp.reason} | KIS: {body}",
            response=resp,
        )


def _get_with_retry(url, headers, params, timeout=10, max_retries=3) -> requests.Response:
    """초당 거래건수 초과(EGW00201) 시 backoff 후 재시도."""
    delay = 1.0
    for attempt in range(max_retries):
        resp = requests.get(url, headers=headers, params=params, timeout=timeout)
        if resp.ok:
            body = resp.json()
            if body.get('msg_cd') == 'EGW00201':
                logger.warning("KIS 레이트 리밋 (EGW00201), %.1f초 후 재시도 (%d/%d)", delay, attempt + 1, max_retries)
                time.sleep(delay)
                delay *= 2
                continue
            return resp
        # 500 이고 EGW00201 인 경우
        try:
            body = resp.json()
            if body.get('msg_cd') == 'EGW00201':
                logger.warning("KIS 레이트 리밋 500 (EGW00201), %.1f초 후 재시도 (%d/%d)", delay, attempt + 1, max_retries)
                time.sleep(delay)
                delay *= 2
                continue
        except Exception:
            pass
        return resp
    return resp


# ─── AES-256 암호화/복호화 ─────────────────────────────────────────────────────

def _get_key() -> bytes:
    key = Config.ENCRYPTION_KEY.encode('utf-8')
    return hashlib.sha256(key).digest()


def encrypt(plaintext: str) -> str:
    key = _get_key()
    iv = os.urandom(16)
    padded = _pad(plaintext.encode('utf-8'))
    cipher = Cipher(algorithms.AES(key), modes.CBC(iv), backend=default_backend())
    enc = cipher.encryptor()
    ct = enc.update(padded) + enc.finalize()
    return base64.b64encode(iv + ct).decode('utf-8')


def decrypt(ciphertext: str) -> str:
    key = _get_key()
    raw = base64.b64decode(ciphertext.encode('utf-8'))
    iv, ct = raw[:16], raw[16:]
    cipher = Cipher(algorithms.AES(key), modes.CBC(iv), backend=default_backend())
    dec = cipher.decryptor()
    return _unpad(dec.update(ct) + dec.finalize()).decode('utf-8')


def _pad(data: bytes) -> bytes:
    pad_len = 16 - (len(data) % 16)
    return data + bytes([pad_len] * pad_len)


def _unpad(data: bytes) -> bytes:
    return data[:-data[-1]]


# ─── KIS API 클라이언트 ────────────────────────────────────────────────────────

class KISClient:
    def __init__(self, account):
        self.account = account
        self.app_key = decrypt(account.encrypted_app_key)
        self.app_secret = decrypt(account.encrypted_app_secret)
        self.account_number = account.account_number
        self.account_product = account.account_product
        self.mock_mode = getattr(account, 'is_mock', True)
        self.base_url = (
            'https://openapivts.koreainvestment.com:29443'
            if self.mock_mode else
            'https://openapi.koreainvestment.com:9443'
        )
        self._access_token = None

    # ─── 토큰 관리 ──────────────────────────────────────────────────────────────

    def get_access_token(self) -> str:
        now = datetime.utcnow()
        if (self.account.kis_access_token
                and self.account.kis_token_expires_at
                and self.account.kis_token_expires_at > now):
            return self.account.kis_access_token

        url = f"{self.base_url}/oauth2/tokenP"
        body = {
            "grant_type": "client_credentials",
            "appkey": self.app_key,
            "appsecret": self.app_secret,
        }
        resp = requests.post(url, json=body, timeout=10)
        _raise_for_status(resp)
        data = resp.json()
        token = data['access_token']

        # DB 갱신
        from models import db
        self.account.kis_access_token = token
        self.account.kis_token_expires_at = now + timedelta(hours=23)
        db.session.commit()
        return token

    def _headers(self, tr_id: str, extra: dict = None) -> dict:
        h = {
            "content-type": "application/json; charset=utf-8",
            "authorization": f"Bearer {self.get_access_token()}",
            "appkey": self.app_key,
            "appsecret": self.app_secret,
            "tr_id": tr_id,
            "custtype": "P",
        }
        if extra:
            h.update(extra)
        return h

    # ─── 시세 조회 ──────────────────────────────────────────────────────────────

    def get_price_kr(self, symbol: str) -> dict:
        if self.mock_mode:
            ohlcv = _mock_ohlcv_kr(symbol, 3)
            price = ohlcv[-1]['stck_clpr'] if ohlcv else '50000'
            return {'output': {'stck_prpr': price, 'stck_oprc': price, 'stck_hgpr': price, 'stck_lwpr': price}}
        url = f"{self.base_url}/uapi/domestic-stock/v1/quotations/inquire-price"
        tr_id = "FHKST01010100"
        params = {"fid_cond_mrkt_div_code": "J", "fid_input_iscd": symbol}
        resp = requests.get(url, headers=self._headers(tr_id), params=params, timeout=10)
        _raise_for_status(resp)
        return resp.json()

    def get_price_us(self, symbol: str, exchange: str = "NAS") -> dict:
        if self.mock_mode:
            ohlcv = _mock_ohlcv_us(symbol, 3)
            price = ohlcv[-1]['clos'] if ohlcv else '100.0'
            return {'output': {'last': price, 'open': price, 'high': price, 'low': price}}
        url = f"{self.base_url}/uapi/overseas-price/v1/quotations/price"
        tr_id = "HHDFS00000300"
        params = {"AUTH": "", "EXCD": exchange, "SYMB": symbol}
        resp = requests.get(url, headers=self._headers(tr_id), params=params, timeout=10)
        _raise_for_status(resp)
        return resp.json()

    def get_daily_ohlcv_kr(self, symbol: str, period: int = 120) -> list:
        if self.mock_mode:
            return _mock_ohlcv_kr(symbol, period)
        import pytz
        from datetime import timedelta
        kst = pytz.timezone('Asia/Seoul')
        end_dt = datetime.now(kst)
        start_dt = end_dt - timedelta(days=max(period * 2, 365))
        url = f"{self.base_url}/uapi/domestic-stock/v1/quotations/inquire-daily-itemchartprice"
        tr_id = "FHKST03010100"
        params = {
            "fid_cond_mrkt_div_code": "J",
            "fid_input_iscd": symbol,
            "fid_org_adj_prc": "0",
            "fid_period_div_code": "D",
            "fid_input_date_1": start_dt.strftime("%Y%m%d"),
            "fid_input_date_2": end_dt.strftime("%Y%m%d"),
        }
        resp = _get_with_retry(url, headers=self._headers(tr_id), params=params, timeout=10)
        _raise_for_status(resp)
        return resp.json().get('output2', [])

    def get_daily_ohlcv_us(self, symbol: str, exchange: str = "NAS", period: int = 120) -> list:
        if self.mock_mode:
            return _mock_ohlcv_us(symbol, period)
        url = f"{self.base_url}/uapi/overseas-price/v1/quotations/dailyprice"
        tr_id = "HHDFS76240000"
        params = {
            "AUTH": "",
            "EXCD": exchange,
            "SYMB": symbol,
            "GUBN": "0",
            "BYMD": "",
            "MODP": "1",
        }
        resp = _get_with_retry(url, headers=self._headers(tr_id), params=params, timeout=10)
        _raise_for_status(resp)
        return resp.json().get('output2', [])

    # ─── 스크리너 조회 ──────────────────────────────────────────────────────────

    def get_volume_rank_kr(self, market_div: str = 'J') -> list:
        """거래량 순위 상위 종목 조회 (J=KOSPI, Q=KOSDAQ)"""
        if self.mock_mode:
            return _mock_volume_rank_kr(market_div)

        url = f"{self.base_url}/uapi/domestic-stock/v1/quotations/volume-rank"
        tr_id = "FHPST01710000"
        scr_div = "20172" if market_div == 'Q' else "20171"
        params = {
            "fid_cond_mrkt_div_code": market_div,
            "fid_cond_scr_div_code": scr_div,
            "fid_input_iscd": "0000",
            "fid_rank_sort_cls_code": "0",
            "fid_input_cnt_1": "0",
            "fid_prc_cls_code": "1",
            "fid_trgt_cls_code": "111111111",
            "fid_trgt_exls_cls_code": "0000000000",
            "fid_div_cls_code": "0",
            "fid_vol_cnt": "100000",
        }
        resp = requests.get(url, headers=self._headers(tr_id), params=params, timeout=15)
        _raise_for_status(resp)
        return resp.json().get('output', [])

    # ─── 잔고 조회 ──────────────────────────────────────────────────────────────

    def get_balance_kr(self) -> dict:
        if self.mock_mode:
            return {"output1": [], "output2": {"dnca_tot_amt": "0", "tot_evlu_amt": "0"}, "rt_cd": "0", "msg_cd": "MOCK", "msg1": "MOCK MODE"}
        url = f"{self.base_url}/uapi/domestic-stock/v1/trading/inquire-balance"
        tr_id = "TTTC8434R"
        params = {
            "CANO": self.account_number[:8],
            "ACNT_PRDT_CD": self.account_product,
            "AFHR_FLPR_YN": "N",
            "OFL_YN": "",
            "INQR_DVSN": "02",
            "UNPR_DVSN": "01",
            "FUND_STTL_ICLD_YN": "N",
            "FNCG_AMT_AUTO_RDPT_YN": "N",
            "PRCS_DVSN": "01",
            "CTX_AREA_FK100": "",
            "CTX_AREA_NK100": "",
        }
        resp = requests.get(url, headers=self._headers(tr_id), params=params, timeout=10)
        _raise_for_status(resp)
        return resp.json()

    def get_balance_us(self) -> dict:
        if self.mock_mode:
            return {"output1": [], "output2": {"ovrs_tot_pfls": "0", "tot_evlu_pfls_amt": "0"}, "rt_cd": "0", "msg_cd": "MOCK", "msg1": "MOCK MODE"}
        # 보유주식 잔고
        url = f"{self.base_url}/uapi/overseas-stock/v1/trading/inquire-balance"
        params = {
            "CANO": self.account_number[:8],
            "ACNT_PRDT_CD": self.account_product,
            "OVRS_EXCG_CD": "NASD",
            "TR_CRCY_CD": "USD",
            "CTX_AREA_FK200": "",
            "CTX_AREA_NK200": "",
        }
        resp = requests.get(url, headers=self._headers("TTTS3012R"), params=params, timeout=10)
        _raise_for_status(resp)
        holdings = resp.json()

        # 외화 예수금 조회
        cash_url = f"{self.base_url}/uapi/overseas-stock/v1/trading/inquire-present-balance"
        cash_params = {
            "CANO": self.account_number[:8],
            "ACNT_PRDT_CD": self.account_product,
            "WCRC_FRCR_DVSN_CD": "02",
            "NATN_CD": "840",
            "TR_MKET_CD": "00",
            "INQR_DVSN_CD": "00",
        }
        try:
            cash_resp = requests.get(cash_url, headers=self._headers("CTRP6504R"), params=cash_params, timeout=10)
            _raise_for_status(cash_resp)
            cash_data = cash_resp.json()
            output3 = cash_data.get('output3', {})
            if isinstance(output3, list):
                row = output3[0] if output3 else {}
            else:
                row = output3 or {}
            holdings['frcr_dncl_amt_2'] = row.get('tot_dncl_amt', '0')    # USD 예수금
            holdings['frcr_evlu_amt2'] = row.get('frcr_evlu_tota', '0')   # USD 주식 평가액
        except Exception as e:
            logger.warning("외화 예수금 조회 실패: %s", e)
            holdings['frcr_dncl_amt_2'] = '0'
            holdings['frcr_evlu_amt2'] = '0'

        return holdings

    # ─── 주문 ───────────────────────────────────────────────────────────────────

    def order_kr(self, symbol: str, side: str, quantity: int, price: int = 0) -> dict:
        url = f"{self.base_url}/uapi/domestic-stock/v1/trading/order-cash"
        if side == 'BUY':
            tr_id = "VTTC0802U" if self.mock_mode else "TTTC0802U"
        else:
            tr_id = "VTTC0801U" if self.mock_mode else "TTTC0801U"

        body = {
            "CANO": self.account_number[:8],
            "ACNT_PRDT_CD": self.account_product,
            "PDNO": symbol,
            "ORD_DVSN": "01" if price == 0 else "00",
            "ORD_QTY": str(quantity),
            "ORD_UNPR": str(price),
        }
        resp = requests.post(url, headers=self._headers(tr_id), json=body, timeout=10)
        _raise_for_status(resp)
        return resp.json()

    def order_us(self, symbol: str, exchange: str, side: str, quantity: int, price: float = 0) -> dict:
        url = f"{self.base_url}/uapi/overseas-stock/v1/trading/order"
        if side == 'BUY':
            tr_id = "VTTT1002U" if self.mock_mode else "TTTT1002U"
        else:
            tr_id = "VTTT1006U" if self.mock_mode else "TTTT1006U"

        body = {
            "CANO": self.account_number[:8],
            "ACNT_PRDT_CD": self.account_product,
            "OVRS_EXCG_CD": exchange,
            "PDNO": symbol,
            "ORD_DVSN": "00",
            "ORD_QTY": str(quantity),
            "OVRS_ORD_UNPR": str(price),
            "ORD_SVR_DVSN_CD": "0",
        }
        resp = requests.post(url, headers=self._headers(tr_id), json=body, timeout=10)
        _raise_for_status(resp)
        return resp.json()

    def get_stock_info_kr(self, symbol: str) -> dict:
        """종목 기본 정보 (시가총액 포함) — 스크리너 필터용"""
        if self.mock_mode:
            mock_info = {
                '005930': {'hts_avls': '4485000', 'acml_vol': '15000000', 'stck_prpr': '75000'},
                '000660': {'hts_avls': '1050000', 'acml_vol': '8000000', 'stck_prpr': '145000'},
                '035420': {'hts_avls': '280000', 'acml_vol': '2000000', 'stck_prpr': '190000'},
            }
            return {'output': mock_info.get(symbol, {'hts_avls': '600000', 'acml_vol': '150000', 'stck_prpr': '50000'})}
        url = f"{self.base_url}/uapi/domestic-stock/v1/quotations/inquire-price"
        tr_id = "FHKST01010100"
        params = {"fid_cond_mrkt_div_code": "J", "fid_input_iscd": symbol}
        resp = requests.get(url, headers=self._headers(tr_id), params=params, timeout=10)
        _raise_for_status(resp)
        return resp.json()

    def order_with_retry(self, symbol: str, side: str, quantity: int,
                         price: float = 0, market: str = 'KR',
                         exchange: str = 'NAS', max_retry: int = 3) -> dict:
        last_err = None
        for attempt in range(1, max_retry + 1):
            try:
                if market == 'KR':
                    return self.order_kr(symbol, side, quantity, int(price))
                else:
                    return self.order_us(symbol, exchange, side, quantity, price)
            except Exception as e:
                last_err = e
                import time
                time.sleep(2 ** attempt)
        raise last_err


# ─── 모의 데이터 ────────────────────────────────────────────────────────────────

def _mock_ohlcv_kr(symbol: str, period: int = 120) -> list:
    """국내주 일봉 모의 데이터 — 실제 API처럼 최신 날짜가 index 0."""
    import random
    rng = random.Random(hash(symbol) % 10000)
    base = {'005930': 75000, '000660': 145000, '005380': 210000}.get(symbol, 50000)
    rows = []
    price = base * 0.80  # 과거는 낮은 가격 → 상승 추세로 골든크로스 유도
    for i in range(period):  # 0 = 가장 오래된 날, period-1 = 가장 최근
        price = price * 1.0015 * (1 + rng.uniform(-0.008, 0.012))
        price = max(price, 100)
        high = price * (1 + rng.uniform(0.001, 0.018))
        low = price * (1 - rng.uniform(0.001, 0.018))
        rows.append({
            'stck_bsop_date': f'202501{(i % 28) + 1:02d}',
            'stck_oprc': str(int(price * 0.999)),
            'stck_hgpr': str(int(high)),
            'stck_lwpr': str(int(low)),
            'stck_clpr': str(int(price)),
            'acml_vol': str(rng.randint(500000, 5000000)),
        })
    rows.reverse()  # 최신 날짜가 index 0 (실제 KIS API 순서)
    return rows


def _mock_ohlcv_us(symbol: str, period: int = 120) -> list:
    """미국주 일봉 모의 데이터 — 최신 날짜가 index 0."""
    import random
    rng = random.Random(hash(symbol) % 20000)
    base = {'AAPL': 185.0, 'MSFT': 420.0, 'NVDA': 875.0, 'AMZN': 185.0}.get(symbol, 100.0)
    rows = []
    price = base * 0.70
    for i in range(period):
        price = price * 1.002 * (1 + rng.uniform(-0.01, 0.015))
        price = max(price, 1.0)
        high = price * (1 + rng.uniform(0.001, 0.025))
        low = price * (1 - rng.uniform(0.001, 0.025))
        rows.append({
            'bass_dt': f'202501{(i % 28) + 1:02d}',
            'open': f'{price * 0.999:.2f}',
            'high': f'{high:.2f}',
            'low': f'{low:.2f}',
            'clos': f'{price:.2f}',
            'tvol': str(rng.randint(1000000, 20000000)),
        })
    rows.reverse()  # 최신 날짜가 index 0
    return rows


def _mock_volume_rank_kr(market_div: str = 'J') -> list:
    kospi = [
        {'mksc_shrn_iscd': '005930', 'hts_kor_isnm': '삼성전자', 'acml_vol': '15000000', 'stck_prpr': '75000', 'hts_avls': '4485000', 'iscd_stat_cls_code': '00'},
        {'mksc_shrn_iscd': '000660', 'hts_kor_isnm': 'SK하이닉스', 'acml_vol': '8000000', 'stck_prpr': '145000', 'hts_avls': '1050000', 'iscd_stat_cls_code': '00'},
        {'mksc_shrn_iscd': '005380', 'hts_kor_isnm': '현대차', 'acml_vol': '2500000', 'stck_prpr': '210000', 'hts_avls': '450000', 'iscd_stat_cls_code': '00'},
        {'mksc_shrn_iscd': '000270', 'hts_kor_isnm': '기아', 'acml_vol': '3500000', 'stck_prpr': '92000', 'hts_avls': '370000', 'iscd_stat_cls_code': '00'},
        {'mksc_shrn_iscd': '051910', 'hts_kor_isnm': 'LG화학', 'acml_vol': '1500000', 'stck_prpr': '330000', 'hts_avls': '310000', 'iscd_stat_cls_code': '00'},
        {'mksc_shrn_iscd': '006400', 'hts_kor_isnm': '삼성SDI', 'acml_vol': '1200000', 'stck_prpr': '290000', 'hts_avls': '290000', 'iscd_stat_cls_code': '00'},
        {'mksc_shrn_iscd': '207940', 'hts_kor_isnm': '삼성바이오로직스', 'acml_vol': '800000', 'stck_prpr': '780000', 'hts_avls': '500000', 'iscd_stat_cls_code': '00'},
        {'mksc_shrn_iscd': '105560', 'hts_kor_isnm': 'KB금융', 'acml_vol': '1200000', 'stck_prpr': '65000', 'hts_avls': '250000', 'iscd_stat_cls_code': '00'},
        {'mksc_shrn_iscd': '055550', 'hts_kor_isnm': '신한지주', 'acml_vol': '1000000', 'stck_prpr': '48000', 'hts_avls': '230000', 'iscd_stat_cls_code': '00'},
        {'mksc_shrn_iscd': '066570', 'hts_kor_isnm': 'LG전자', 'acml_vol': '900000', 'stck_prpr': '95000', 'hts_avls': '200000', 'iscd_stat_cls_code': '00'},
        {'mksc_shrn_iscd': '012330', 'hts_kor_isnm': '현대모비스', 'acml_vol': '700000', 'stck_prpr': '230000', 'hts_avls': '280000', 'iscd_stat_cls_code': '00'},
        {'mksc_shrn_iscd': '028260', 'hts_kor_isnm': '삼성물산', 'acml_vol': '600000', 'stck_prpr': '165000', 'hts_avls': '300000', 'iscd_stat_cls_code': '00'},
        {'mksc_shrn_iscd': '068270', 'hts_kor_isnm': '셀트리온', 'acml_vol': '1800000', 'stck_prpr': '175000', 'hts_avls': '200000', 'iscd_stat_cls_code': '00'},
        {'mksc_shrn_iscd': '035720', 'hts_kor_isnm': '카카오', 'acml_vol': '3000000', 'stck_prpr': '42000', 'hts_avls': '180000', 'iscd_stat_cls_code': '00'},
        {'mksc_shrn_iscd': '035420', 'hts_kor_isnm': 'NAVER', 'acml_vol': '2000000', 'stck_prpr': '180000', 'hts_avls': '280000', 'iscd_stat_cls_code': '00'},
    ]
    kosdaq = [
        {'mksc_shrn_iscd': '247540', 'hts_kor_isnm': '에코프로비엠', 'acml_vol': '2000000', 'stck_prpr': '180000', 'hts_avls': '120000', 'iscd_stat_cls_code': '00'},
        {'mksc_shrn_iscd': '086520', 'hts_kor_isnm': '에코프로', 'acml_vol': '1500000', 'stck_prpr': '90000', 'hts_avls': '80000', 'iscd_stat_cls_code': '00'},
        {'mksc_shrn_iscd': '091990', 'hts_kor_isnm': '셀트리온헬스케어', 'acml_vol': '1000000', 'stck_prpr': '70000', 'hts_avls': '90000', 'iscd_stat_cls_code': '00'},
        {'mksc_shrn_iscd': '196170', 'hts_kor_isnm': '알테오젠', 'acml_vol': '800000', 'stck_prpr': '220000', 'hts_avls': '75000', 'iscd_stat_cls_code': '00'},
        {'mksc_shrn_iscd': '141080', 'hts_kor_isnm': '레고켐바이오', 'acml_vol': '600000', 'stck_prpr': '95000', 'hts_avls': '55000', 'iscd_stat_cls_code': '00'},
    ]
    return kospi if market_div == 'J' else kosdaq

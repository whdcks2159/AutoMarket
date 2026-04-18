import os
import json
import base64
import hashlib
import requests
from datetime import datetime, timedelta
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.backends import default_backend

from config import Config


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
        self.mock_mode = Config.MOCK_MODE
        self.base_url = Config.KIS_BASE_URL
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
        resp.raise_for_status()
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
        url = f"{self.base_url}/uapi/domestic-stock/v1/quotations/inquire-price"
        tr_id = "VTTC8434R" if self.mock_mode else "FHKST01010100"
        params = {"fid_cond_mrkt_div_code": "J", "fid_input_iscd": symbol}
        resp = requests.get(url, headers=self._headers(tr_id), params=params, timeout=10)
        resp.raise_for_status()
        return resp.json()

    def get_price_us(self, symbol: str, exchange: str = "NAS") -> dict:
        url = f"{self.base_url}/uapi/overseas-price/v1/quotations/price"
        tr_id = "HHDFS00000300"
        params = {"AUTH": "", "EXCD": exchange, "SYMB": symbol}
        resp = requests.get(url, headers=self._headers(tr_id), params=params, timeout=10)
        resp.raise_for_status()
        return resp.json()

    def get_daily_ohlcv_kr(self, symbol: str, period: int = 120) -> list:
        url = f"{self.base_url}/uapi/domestic-stock/v1/quotations/inquire-daily-price"
        tr_id = "FHKST01010400"
        end_date = datetime.now().strftime('%Y%m%d')
        params = {
            "fid_cond_mrkt_div_code": "J",
            "fid_input_iscd": symbol,
            "fid_org_adj_prc": "0",
            "fid_period_div_code": "D",
        }
        resp = requests.get(url, headers=self._headers(tr_id), params=params, timeout=10)
        resp.raise_for_status()
        return resp.json().get('output2', [])

    def get_daily_ohlcv_us(self, symbol: str, exchange: str = "NAS", period: int = 120) -> list:
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
        resp = requests.get(url, headers=self._headers(tr_id), params=params, timeout=10)
        resp.raise_for_status()
        return resp.json().get('output2', [])

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
        resp.raise_for_status()
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
        resp.raise_for_status()
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
            cash_resp.raise_for_status()
            cash_data = cash_resp.json()
            output3 = cash_data.get('output3', [{}])
            frcr_cash = output3[0].get('frcr_dncl_amt_2', '0') if output3 else '0'
            holdings['frcr_dncl_amt_2'] = frcr_cash
        except Exception:
            holdings['frcr_dncl_amt_2'] = '0'

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
        resp.raise_for_status()
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
        resp.raise_for_status()
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

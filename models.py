from datetime import datetime
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()


class User(db.Model):
    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True)
    google_id = db.Column(db.String(128), unique=True, nullable=False)
    email = db.Column(db.String(256), unique=True, nullable=False)
    name = db.Column(db.String(128))
    picture = db.Column(db.String(512))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    accounts = db.relationship('Account', backref='user', lazy='dynamic', cascade='all, delete-orphan')

    def to_dict(self):
        return {'id': self.id, 'email': self.email, 'name': self.name, 'picture': self.picture}


class Account(db.Model):
    __tablename__ = 'accounts'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    name = db.Column(db.String(128), nullable=False)
    account_number = db.Column(db.String(64), nullable=False)
    account_product = db.Column(db.String(8), default='01')

    # AES-256 암호화 저장
    encrypted_app_key = db.Column(db.Text, nullable=False)
    encrypted_app_secret = db.Column(db.Text, nullable=False)

    # 캐시된 KIS 접근 토큰
    kis_access_token = db.Column(db.Text)
    kis_token_expires_at = db.Column(db.DateTime)

    strategy = db.Column(db.String(64))  # golden_rsi, dual_momentum, week52_high, volatility_breakout
    is_active = db.Column(db.Boolean, default=False)
    is_mock = db.Column(db.Boolean, default=False)  # True=모의투자, False=실계좌
    investment_limit = db.Column(db.Float, default=1000000.0)
    market_type = db.Column(db.String(8), default='KR')  # KR or US

    # 스크리너 설정
    screener_enabled = db.Column(db.Boolean, default=False)
    screener_targets = db.Column(db.String(128), default='KOSPI,KOSDAQ')  # 쉼표 구분
    screener_max_symbols = db.Column(db.Integer, default=5)
    screener_per_symbol_limit = db.Column(db.Float, default=500000.0)
    screener_daily_buy_limit = db.Column(db.Integer, default=3)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    trades = db.relationship('Trade', backref='account', lazy='dynamic', cascade='all, delete-orphan')
    strategy_logs = db.relationship('StrategyLog', backref='account', lazy='dynamic', cascade='all, delete-orphan')
    scan_results = db.relationship('ScanResult', backref='account', lazy='dynamic', cascade='all, delete-orphan')

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'account_number': self.account_number,
            'strategy': self.strategy,
            'is_active': self.is_active,
            'is_mock': self.is_mock,
            'investment_limit': self.investment_limit,
            'market_type': self.market_type,
            'screener_enabled': self.screener_enabled,
            'screener_targets': self.screener_targets,
            'screener_max_symbols': self.screener_max_symbols,
            'screener_per_symbol_limit': self.screener_per_symbol_limit,
            'screener_daily_buy_limit': self.screener_daily_buy_limit,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }


class Trade(db.Model):
    __tablename__ = 'trades'

    id = db.Column(db.Integer, primary_key=True)
    account_id = db.Column(db.Integer, db.ForeignKey('accounts.id'), nullable=False)
    symbol = db.Column(db.String(16), nullable=False)
    symbol_name = db.Column(db.String(64))
    side = db.Column(db.String(4), nullable=False)  # BUY or SELL
    quantity = db.Column(db.Integer, nullable=False)
    price = db.Column(db.Float, nullable=False)
    amount = db.Column(db.Float)
    strategy = db.Column(db.String(64))
    order_id = db.Column(db.String(64))
    status = db.Column(db.String(16), default='PENDING')  # PENDING, FILLED, FAILED
    error_message = db.Column(db.Text)
    executed_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id,
            'symbol': self.symbol,
            'symbol_name': self.symbol_name,
            'side': self.side,
            'quantity': self.quantity,
            'price': self.price,
            'amount': self.amount,
            'strategy': self.strategy,
            'status': self.status,
            'executed_at': self.executed_at.isoformat() if self.executed_at else None,
        }


class ScanResult(db.Model):
    __tablename__ = 'scan_results'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    account_id = db.Column(db.Integer, db.ForeignKey('accounts.id'), nullable=False)
    strategy = db.Column(db.String(64), nullable=False)
    ticker = db.Column(db.String(16), nullable=False)
    signal = db.Column(db.String(16))  # BUY, WATCH
    reason = db.Column(db.Text)
    scanned_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id,
            'strategy': self.strategy,
            'ticker': self.ticker,
            'signal': self.signal,
            'reason': self.reason,
            'scanned_at': self.scanned_at.isoformat() if self.scanned_at else None,
        }


class WatchList(db.Model):
    __tablename__ = 'watchlist'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    ticker = db.Column(db.String(16), nullable=False)
    market = db.Column(db.String(8), default='KR')  # KR or US
    added_by = db.Column(db.String(16), default='manual')  # auto or manual
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id,
            'ticker': self.ticker,
            'market': self.market,
            'added_by': self.added_by,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }


class StrategyLog(db.Model):
    __tablename__ = 'strategy_logs'

    id = db.Column(db.Integer, primary_key=True)
    account_id = db.Column(db.Integer, db.ForeignKey('accounts.id'), nullable=False)
    event_type = db.Column(db.String(32))  # STRATEGY_CHANGE, SIGNAL, ERROR, INFO
    old_strategy = db.Column(db.String(64))
    new_strategy = db.Column(db.String(64))
    switch_mode = db.Column(db.String(16))  # clean or soft
    message = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id,
            'event_type': self.event_type,
            'old_strategy': self.old_strategy,
            'new_strategy': self.new_strategy,
            'switch_mode': self.switch_mode,
            'message': self.message,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }

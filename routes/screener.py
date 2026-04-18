from flask import Blueprint, request, jsonify
from datetime import datetime, date
from models import db, Account, ScanResult, WatchList
from routes.auth import login_required, current_user

screener_bp = Blueprint('screener', __name__, url_prefix='/api/screener')


def _owned_account(account_id: int) -> Account:
    from flask import abort
    user = current_user()
    account = Account.query.get_or_404(account_id)
    if account.user_id != user.id:
        abort(403)
    return account


# ── 스크리너 설정 조회/수정 ──────────────────────────────────────────────────

@screener_bp.route('/config/<int:account_id>', methods=['GET'])
@login_required
def get_config(account_id):
    account = _owned_account(account_id)
    return jsonify({
        'screener_enabled': account.screener_enabled,
        'screener_targets': account.screener_targets,
        'screener_max_symbols': account.screener_max_symbols,
        'screener_per_symbol_limit': account.screener_per_symbol_limit,
        'screener_daily_buy_limit': account.screener_daily_buy_limit,
    })


@screener_bp.route('/config/<int:account_id>', methods=['PUT'])
@login_required
def update_config(account_id):
    account = _owned_account(account_id)
    data = request.get_json() or {}

    if 'screener_enabled' in data:
        account.screener_enabled = bool(data['screener_enabled'])
    if 'screener_targets' in data:
        account.screener_targets = data['screener_targets']
    if 'screener_max_symbols' in data:
        v = int(data['screener_max_symbols'])
        account.screener_max_symbols = max(1, min(10, v))
    if 'screener_per_symbol_limit' in data:
        account.screener_per_symbol_limit = float(data['screener_per_symbol_limit'])
    if 'screener_daily_buy_limit' in data:
        v = int(data['screener_daily_buy_limit'])
        account.screener_daily_buy_limit = max(1, min(20, v))

    db.session.commit()
    return jsonify({'message': '스크리너 설정이 저장되었습니다.', **{
        'screener_enabled': account.screener_enabled,
        'screener_targets': account.screener_targets,
        'screener_max_symbols': account.screener_max_symbols,
        'screener_per_symbol_limit': account.screener_per_symbol_limit,
        'screener_daily_buy_limit': account.screener_daily_buy_limit,
    }})


# ── 스캔 결과 조회 ───────────────────────────────────────────────────────────

@screener_bp.route('/results/<int:account_id>', methods=['GET'])
@login_required
def get_results(account_id):
    account = _owned_account(account_id)
    limit = request.args.get('limit', 50, type=int)
    strategy = request.args.get('strategy')
    today_only = request.args.get('today', 'false').lower() == 'true'

    q = ScanResult.query.filter_by(account_id=account.id)
    if strategy:
        q = q.filter_by(strategy=strategy)
    if today_only:
        today_start = datetime.combine(date.today(), datetime.min.time())
        q = q.filter(ScanResult.scanned_at >= today_start)

    results = q.order_by(ScanResult.scanned_at.desc()).limit(limit).all()
    return jsonify([r.to_dict() for r in results])


# ── 수동 스캔 실행 ──────────────────────────────────────────────────────────

@screener_bp.route('/scan/<int:account_id>', methods=['POST'])
@login_required
def run_scan(account_id):
    account = _owned_account(account_id)
    data = request.get_json() or {}
    strategy = data.get('strategy', account.strategy)

    if not strategy:
        return jsonify({'error': '전략이 설정되지 않았습니다.'}), 400

    try:
        from kis_api import KISClient
        kis = KISClient(account)

        if account.market_type == 'KR':
            from screener.korea_screener import KoreaScreener
            screener = KoreaScreener(account, kis)
            if strategy == 'golden_rsi':
                symbols = screener.scan_golden_rsi()
            elif strategy == 'week52_high':
                symbols = screener.scan_week52_high()
            elif strategy == 'volatility_breakout':
                symbols = screener.scan_volatility_breakout()
            else:
                return jsonify({'error': f'{strategy}은 국내주 전략이 아닙니다.'}), 400
            return jsonify({'strategy': strategy, 'market': 'KR', 'symbols': symbols, 'count': len(symbols)})
        else:
            from screener.us_screener import USScreener
            screener = USScreener(account, kis)
            if strategy == 'dual_momentum':
                pairs = screener.scan_dual_momentum()
            elif strategy == 'week52_high':
                pairs = screener.scan_week52_high()
            elif strategy == 'volatility_breakout':
                pairs = screener.scan_volatility_breakout()
            else:
                return jsonify({'error': f'{strategy}은 미국주 전략이 아닙니다.'}), 400
            symbols = [f"{s}|{e}" for s, e in pairs]
            return jsonify({'strategy': strategy, 'market': 'US', 'symbols': symbols, 'count': len(symbols)})

    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ── 관심 종목(WatchList) ─────────────────────────────────────────────────────

@screener_bp.route('/watchlist', methods=['GET'])
@login_required
def get_watchlist():
    user = current_user()
    market = request.args.get('market')
    q = WatchList.query.filter_by(user_id=user.id)
    if market:
        q = q.filter_by(market=market.upper())
    items = q.order_by(WatchList.created_at.desc()).all()
    return jsonify([w.to_dict() for w in items])


@screener_bp.route('/watchlist', methods=['POST'])
@login_required
def add_watchlist():
    user = current_user()
    data = request.get_json() or {}
    ticker = (data.get('ticker') or '').strip().upper()
    market = (data.get('market') or 'KR').upper()

    if not ticker:
        return jsonify({'error': 'ticker 필드가 필요합니다.'}), 400

    existing = WatchList.query.filter_by(user_id=user.id, ticker=ticker, market=market).first()
    if existing:
        return jsonify({'error': '이미 등록된 종목입니다.'}), 409

    item = WatchList(user_id=user.id, ticker=ticker, market=market, added_by='manual')
    db.session.add(item)
    db.session.commit()
    return jsonify(item.to_dict()), 201


@screener_bp.route('/watchlist/<int:item_id>', methods=['DELETE'])
@login_required
def delete_watchlist(item_id):
    user = current_user()
    item = WatchList.query.get_or_404(item_id)
    if item.user_id != user.id:
        from flask import abort
        abort(403)
    db.session.delete(item)
    db.session.commit()
    return jsonify({'message': '삭제되었습니다.'})

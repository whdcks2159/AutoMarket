from flask import Blueprint, request, jsonify, session, abort
from models import db, Account, StrategyLog
from kis_api import encrypt, decrypt, KISClient
from routes.auth import login_required, current_user
from strategies import STRATEGY_MAP

account_bp = Blueprint('account', __name__, url_prefix='/api/accounts')


def _owned_account(account_id: int) -> Account:
    user = current_user()
    account = Account.query.get_or_404(account_id)
    if account.user_id != user.id:
        abort(403)
    return account


@account_bp.route('', methods=['GET'])
@login_required
def list_accounts():
    user = current_user()
    accounts = Account.query.filter_by(user_id=user.id).all()
    return jsonify([a.to_dict() for a in accounts])


@account_bp.route('', methods=['POST'])
@login_required
def create_account():
    user = current_user()
    data = request.get_json()
    required = ['name', 'account_number', 'app_key', 'app_secret']
    for field in required:
        if not data.get(field):
            return jsonify({'error': f'{field} 필드가 필요합니다.'}), 400

    account = Account(
        user_id=user.id,
        name=data['name'],
        account_number=data['account_number'],
        account_product=data.get('account_product', '01'),
        encrypted_app_key=encrypt(data['app_key']),
        encrypted_app_secret=encrypt(data['app_secret']),
        strategy=data.get('strategy'),
        investment_limit=float(data.get('investment_limit', 1000000)),
        market_type=data.get('market_type', 'KR'),
    )
    db.session.add(account)
    db.session.commit()
    return jsonify(account.to_dict()), 201


@account_bp.route('/<int:account_id>', methods=['GET'])
@login_required
def get_account(account_id):
    return jsonify(_owned_account(account_id).to_dict())


@account_bp.route('/<int:account_id>', methods=['PUT'])
@login_required
def update_account(account_id):
    account = _owned_account(account_id)
    data = request.get_json()

    if 'name' in data:
        account.name = data['name']
    if 'investment_limit' in data:
        account.investment_limit = float(data['investment_limit'])
    if 'market_type' in data:
        account.market_type = data['market_type']
    if 'app_key' in data and data['app_key']:
        account.encrypted_app_key = encrypt(data['app_key'])
    if 'app_secret' in data and data['app_secret']:
        account.encrypted_app_secret = encrypt(data['app_secret'])

    db.session.commit()
    return jsonify(account.to_dict())


@account_bp.route('/<int:account_id>', methods=['DELETE'])
@login_required
def delete_account(account_id):
    account = _owned_account(account_id)
    db.session.delete(account)
    db.session.commit()
    return jsonify({'message': '삭제되었습니다.'})


@account_bp.route('/<int:account_id>/toggle', methods=['POST'])
@login_required
def toggle_active(account_id):
    account = _owned_account(account_id)
    if account.is_active and not account.strategy:
        return jsonify({'error': '전략을 먼저 설정하세요.'}), 400
    account.is_active = not account.is_active
    db.session.commit()
    return jsonify({'is_active': account.is_active})


@account_bp.route('/<int:account_id>/strategy', methods=['POST'])
@login_required
def change_strategy(account_id):
    account = _owned_account(account_id)
    data = request.get_json()
    new_strategy = data.get('strategy')
    mode = data.get('mode', 'soft')  # clean or soft

    if new_strategy not in STRATEGY_MAP:
        return jsonify({'error': '유효하지 않은 전략입니다.'}), 400

    old_strategy = account.strategy

    if mode == 'clean' and account.is_active:
        try:
            kis = KISClient(account)
            _sell_all_holdings(account, kis)
        except Exception as e:
            return jsonify({'error': f'보유 종목 매도 실패: {e}'}), 500

    account.strategy = new_strategy
    db.session.commit()

    log = StrategyLog(
        account_id=account.id,
        event_type='STRATEGY_CHANGE',
        old_strategy=old_strategy,
        new_strategy=new_strategy,
        switch_mode=mode,
        message=f"전략 변경: {old_strategy} → {new_strategy} ({mode} 스위치)",
    )
    db.session.add(log)
    db.session.commit()

    return jsonify({'strategy': account.strategy, 'mode': mode})


@account_bp.route('/<int:account_id>/balance', methods=['GET'])
@login_required
def get_balance(account_id):
    account = _owned_account(account_id)
    try:
        kis = KISClient(account)
        if account.market_type == 'KR':
            data = kis.get_balance_kr()
        else:
            data = kis.get_balance_us()
        return jsonify(data)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@account_bp.route('/<int:account_id>/trades', methods=['GET'])
@login_required
def get_trades(account_id):
    account = _owned_account(account_id)
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    trades = account.trades.order_by(db.text('executed_at DESC')).paginate(page=page, per_page=per_page)
    return jsonify({
        'trades': [t.to_dict() for t in trades.items],
        'total': trades.total,
        'pages': trades.pages,
        'page': page,
    })


@account_bp.route('/<int:account_id>/logs', methods=['GET'])
@login_required
def get_logs(account_id):
    account = _owned_account(account_id)
    logs = account.strategy_logs.order_by(db.text('created_at DESC')).limit(50).all()
    return jsonify([l.to_dict() for l in logs])


def _sell_all_holdings(account: Account, kis: KISClient):
    if account.market_type == 'KR':
        data = kis.get_balance_kr()
        for item in data.get('output1', []):
            qty = int(item.get('hldg_qty', 0))
            if qty > 0:
                symbol = item['pdno']
                price = float(item.get('prpr', 0))
                kis.order_with_retry(symbol, 'SELL', qty, price, 'KR')
    else:
        data = kis.get_balance_us()
        for item in data.get('output1', []):
            qty = int(item.get('ovrs_cblc_qty', 0))
            if qty > 0:
                symbol = item['ovrs_pdno']
                price = float(item.get('now_pric2', 0))
                kis.order_with_retry(symbol, 'SELL', qty, price, 'US')
